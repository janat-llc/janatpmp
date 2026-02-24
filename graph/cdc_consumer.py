"""CDC Consumer — polls cdc_outbox and syncs entities to Neo4j.

Runs as a background daemon thread. Processes INSERT/UPDATE/DELETE
operations, creating corresponding nodes and structural edges in
the knowledge graph.

Edge routing:
  - CDC handles structural edges (BELONGS_TO, FOLLOWS, IN_DOMAIN, etc.)
  - on_write handles INFORMED_BY edges (requires rag_hits, not in CDC payload)
"""

import json
import logging
import threading
import time

from atlas.config import CDC_POLL_INTERVAL, CDC_BATCH_SIZE
from . import graph_service

logger = logging.getLogger(__name__)

_consumer_thread: threading.Thread | None = None
_stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Entity handlers — map CDC rows to Neo4j operations
# ---------------------------------------------------------------------------

def _handle_item(op: str, entity_id: str, payload: dict) -> None:
    if op == "DELETE":
        graph_service.delete_node("Item", entity_id)
        return
    props = {
        "title": payload.get("title", ""),
        "entity_type": payload.get("entity_type", ""),
        "domain": payload.get("domain", ""),
        "status": payload.get("status", ""),
        "priority": payload.get("priority"),
    }
    graph_service.upsert_node("Item", entity_id, props)
    # IN_DOMAIN edge
    domain = payload.get("domain")
    if domain:
        graph_service.create_edge("Item", entity_id, "Domain", domain, "IN_DOMAIN")


def _handle_task(op: str, entity_id: str, payload: dict) -> None:
    if op == "DELETE":
        graph_service.delete_node("Task", entity_id)
        return
    props = {
        "title": payload.get("title", ""),
        "task_type": payload.get("task_type", ""),
        "status": payload.get("status", ""),
        "assigned_to": payload.get("assigned_to", ""),
    }
    graph_service.upsert_node("Task", entity_id, props)
    # TARGETS_ITEM edge
    target = payload.get("target_item_id")
    if target:
        graph_service.create_edge("Task", entity_id, "Item", target, "TARGETS_ITEM")


def _handle_document(op: str, entity_id: str, payload: dict) -> None:
    if op == "DELETE":
        graph_service.delete_node("Document", entity_id)
        return
    props = {
        "title": payload.get("title", ""),
        "doc_type": payload.get("doc_type", ""),
        "source": payload.get("source", ""),
    }
    graph_service.upsert_node("Document", entity_id, props)


def _handle_conversation(op: str, entity_id: str, payload: dict) -> None:
    if op == "DELETE":
        graph_service.delete_node("Conversation", entity_id)
        return
    props = {
        "title": payload.get("title", ""),
        "provider": payload.get("provider", ""),
        "model": payload.get("model", ""),
        "source": payload.get("source", ""),
    }
    graph_service.upsert_node("Conversation", entity_id, props)


def _handle_message(op: str, entity_id: str, payload: dict) -> None:
    if op == "DELETE":
        graph_service.delete_node("Message", entity_id)
        return
    conv_id = payload.get("conversation_id", "")
    props = {
        "conversation_id": conv_id,
        "user_prompt_preview": (payload.get("user_prompt", "") or "")[:100],
        "model_response_preview": (payload.get("model_response", "") or "")[:100],
    }
    graph_service.upsert_node("Message", entity_id, props)
    # BELONGS_TO conversation
    if conv_id:
        graph_service.create_edge("Message", entity_id, "Conversation", conv_id, "BELONGS_TO")
    # FOLLOWS previous message (query DB for preceding message)
    _create_follows_edge(entity_id, conv_id)


def _create_follows_edge(message_id: str, conversation_id: str) -> None:
    """Create FOLLOWS edge to the previous message in the conversation."""
    if not conversation_id:
        return
    try:
        from db.operations import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM messages "
                "WHERE conversation_id = ? AND id != ? "
                "ORDER BY sequence DESC LIMIT 1",
                (conversation_id, message_id),
            ).fetchone()
            if row:
                graph_service.create_edge(
                    "Message", message_id, "Message", row["id"], "FOLLOWS",
                )
    except Exception as e:
        logger.debug("FOLLOWS edge creation skipped: %s", e)


def _handle_domain(op: str, entity_id: str, payload: dict) -> None:
    if op == "DELETE":
        graph_service.delete_node("Domain", entity_id)
        return
    props = {
        "name": payload.get("name", ""),
        "display_name": payload.get("display_name", ""),
        "description": payload.get("description", ""),
    }
    # Use domain name as id for easier edge creation (items reference by name)
    name = payload.get("name", entity_id)
    graph_service.upsert_node("Domain", name, props)


def _handle_message_metadata(op: str, entity_id: str, payload: dict) -> None:
    if op == "DELETE":
        graph_service.delete_node("MessageMetadata", entity_id)
        return
    props = {
        "quality_score": payload.get("quality_score"),
        "keywords": payload.get("keywords", ""),
    }
    graph_service.upsert_node("MessageMetadata", entity_id, props)
    # DESCRIBES edge to parent message
    msg_id = payload.get("message_id")
    if msg_id:
        graph_service.create_edge("MessageMetadata", entity_id, "Message", msg_id, "DESCRIBES")


def _handle_chunk(op: str, entity_id: str, payload: dict) -> None:
    """R16: Sync chunk nodes to Neo4j with PART_OF edges."""
    if op == "DELETE":
        graph_service.delete_node("Chunk", entity_id)
        return
    props = {
        "entity_type": payload.get("entity_type", ""),
        "entity_id": payload.get("entity_id", ""),
        "chunk_index": payload.get("chunk_index"),
        "position": payload.get("position", ""),
    }
    graph_service.upsert_node("Chunk", entity_id, props)
    # PART_OF edge to parent (Message or Document)
    parent_id = payload.get("entity_id", "")
    parent_type = payload.get("entity_type", "")
    if parent_id and parent_type:
        parent_label = "Message" if parent_type == "message" else "Document"
        graph_service.create_edge("Chunk", entity_id, parent_label, parent_id, "PART_OF")


def _handle_relationship(op: str, entity_id: str, payload: dict) -> None:
    """Map SQLite relationship records to Neo4j edges."""
    if op == "DELETE":
        # Can't easily delete a specific edge without more context; skip
        return
    source_type = payload.get("source_type", "")
    source_id = payload.get("source_id", "")
    target_type = payload.get("target_type", "")
    target_id = payload.get("target_id", "")
    rel_type = payload.get("relationship_type", "RELATES_TO")

    # Map entity types to Neo4j labels
    label_map = {
        "item": "Item", "task": "Task", "document": "Document",
        "conversation": "Conversation", "message": "Message",
    }
    from_label = label_map.get(source_type)
    to_label = label_map.get(target_type)
    if from_label and to_label and source_id and target_id:
        graph_service.create_edge(
            from_label, source_id, to_label, target_id,
            rel_type.upper(),
        )


# Entity type → handler dispatch
_HANDLERS = {
    "item": _handle_item,
    "task": _handle_task,
    "document": _handle_document,
    "conversation": _handle_conversation,
    "message": _handle_message,
    "domain": _handle_domain,
    "message_metadata": _handle_message_metadata,
    "chunk": _handle_chunk,
    "relationship": _handle_relationship,
}


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def _process_batch() -> int:
    """Poll cdc_outbox for unprocessed rows and sync to Neo4j.

    Returns:
        Number of rows successfully processed.
    """
    from db.operations import get_connection

    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, operation, entity_type, entity_id, payload "
                "FROM cdc_outbox "
                "WHERE processed_neo4j = 0 "
                "ORDER BY created_at ASC "
                "LIMIT ?",
                (CDC_BATCH_SIZE,),
            ).fetchall()

            if not rows:
                return 0

            processed = 0
            for row in rows:
                entity_type = row["entity_type"]
                handler = _HANDLERS.get(entity_type)
                if not handler:
                    logger.warning("CDC: unknown entity_type '%s', marking processed", entity_type)
                    conn.execute(
                        "UPDATE cdc_outbox SET processed_neo4j = 1 WHERE id = ?",
                        (row["id"],),
                    )
                    conn.commit()
                    processed += 1
                    continue

                try:
                    payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
                    handler(row["operation"], row["entity_id"], payload)
                    conn.execute(
                        "UPDATE cdc_outbox SET processed_neo4j = 1 WHERE id = ?",
                        (row["id"],),
                    )
                    conn.commit()
                    processed += 1
                except Exception as e:
                    logger.warning("CDC: failed to process row %d (%s/%s): %s",
                                   row["id"], entity_type, row["entity_id"][:12], e)

            if processed:
                logger.info("CDC consumer: processed %d/%d rows", processed, len(rows))
            return processed

    except Exception as e:
        logger.warning("CDC batch failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Background daemon
# ---------------------------------------------------------------------------

def _consumer_loop() -> None:
    """Background loop: poll → process → sleep → repeat."""
    logger.info("CDC consumer started (poll every %ds, batch %d)",
                CDC_POLL_INTERVAL, CDC_BATCH_SIZE)
    while not _stop_event.is_set():
        try:
            _process_batch()
        except Exception as e:
            logger.warning("CDC consumer cycle error: %s", e)
        _stop_event.wait(CDC_POLL_INTERVAL)
    logger.info("CDC consumer stopped")


def start_cdc_consumer() -> None:
    """Start the CDC consumer background thread."""
    global _consumer_thread
    if _consumer_thread and _consumer_thread.is_alive():
        return
    _stop_event.clear()
    _consumer_thread = threading.Thread(
        target=_consumer_loop, name="cdc-consumer", daemon=True,
    )
    _consumer_thread.start()


def stop_cdc_consumer() -> None:
    """Signal the CDC consumer to stop."""
    _stop_event.set()


# ---------------------------------------------------------------------------
# Pre-CDC seed — populates Neo4j with entities that predate CDC triggers
# ---------------------------------------------------------------------------

def _seed_pre_cdc_entities() -> dict:
    """Seed Neo4j with SQLite entities that have no CDC outbox entries.

    Uses UNWIND batch Cypher for efficiency. Safe to re-run (MERGE is idempotent).

    Returns:
        Dict with counts of seeded entities.
    """
    from db.operations import get_connection

    driver = graph_service._get_driver()
    stats = {"items": 0, "documents": 0, "conversations": 0, "messages": 0,
             "belongs_to": 0, "follows": 0, "in_domain": 0}

    # --- Seed Items + IN_DOMAIN ---
    with get_connection() as conn:
        items = conn.execute(
            "SELECT id, title, entity_type, domain, status, priority FROM items"
        ).fetchall()

    if items:
        batch = [
            {"id": it["id"], "title": it["title"] or "", "entity_type": it["entity_type"] or "",
             "domain": it["domain"] or "", "status": it["status"] or "", "priority": it["priority"] or ""}
            for it in items
        ]
        with driver.session(database=graph_service.NEO4J_DATABASE) as session:
            session.run(
                "UNWIND $rows AS row "
                "MERGE (i:Item {id: row.id}) "
                "SET i.title = row.title, i.entity_type = row.entity_type, "
                "    i.domain = row.domain, i.status = row.status, i.priority = row.priority",
                rows=batch,
            )
            # IN_DOMAIN edges for items with domains
            domain_rows = [r for r in batch if r["domain"]]
            if domain_rows:
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (i:Item {id: row.id}) "
                    "MERGE (d:Domain {id: row.domain}) "
                    "MERGE (i)-[:IN_DOMAIN]->(d)",
                    rows=domain_rows,
                )
                stats["in_domain"] += len(domain_rows)
        stats["items"] += len(batch)
        logger.info("Seed: %d Item nodes", stats["items"])

    # --- Seed Documents ---
    with get_connection() as conn:
        docs = conn.execute(
            "SELECT id, title, doc_type, source FROM documents"
        ).fetchall()

    if docs:
        batch = [
            {"id": d["id"], "title": d["title"] or "", "doc_type": d["doc_type"] or "",
             "source": d["source"] or ""}
            for d in docs
        ]
        with driver.session(database=graph_service.NEO4J_DATABASE) as session:
            session.run(
                "UNWIND $rows AS row "
                "MERGE (d:Document {id: row.id}) "
                "SET d.title = row.title, d.doc_type = row.doc_type, d.source = row.source",
                rows=batch,
            )
        stats["documents"] += len(batch)
        logger.info("Seed: %d Document nodes", stats["documents"])

    # --- Seed Conversations ---
    with get_connection() as conn:
        convs = conn.execute(
            "SELECT id, title, provider, model, source FROM conversations"
        ).fetchall()

    if convs:
        batch = [
            {"id": c["id"], "title": c["title"] or "", "provider": c["provider"] or "",
             "model": c["model"] or "", "source": c["source"] or ""}
            for c in convs
        ]
        # Process in chunks of 500
        for i in range(0, len(batch), 500):
            chunk = batch[i:i+500]
            with driver.session(database=graph_service.NEO4J_DATABASE) as session:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (c:Conversation {id: row.id}) "
                    "SET c.title = row.title, c.provider = row.provider, "
                    "    c.model = row.model, c.source = row.source",
                    rows=chunk,
                )
            stats["conversations"] += len(chunk)
        logger.info("Seed: %d Conversation nodes", stats["conversations"])

    # --- Seed Messages + BELONGS_TO ---
    with get_connection() as conn:
        msgs = conn.execute(
            "SELECT id, conversation_id, user_prompt, model_response, sequence "
            "FROM messages ORDER BY conversation_id, sequence"
        ).fetchall()

    if msgs:
        batch = [
            {
                "id": m["id"],
                "conv_id": m["conversation_id"],
                "user_prompt_preview": (m["user_prompt"] or "")[:100],
                "model_response_preview": (m["model_response"] or "")[:100],
                "sequence": m["sequence"] or 0,
            }
            for m in msgs
        ]
        # Messages + BELONGS_TO in chunks of 500
        for i in range(0, len(batch), 500):
            chunk = batch[i:i+500]
            with driver.session(database=graph_service.NEO4J_DATABASE) as session:
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (m:Message {id: row.id}) "
                    "SET m.conversation_id = row.conv_id, "
                    "    m.user_prompt_preview = row.user_prompt_preview, "
                    "    m.model_response_preview = row.model_response_preview "
                    "WITH m, row "
                    "MERGE (c:Conversation {id: row.conv_id}) "
                    "MERGE (m)-[:BELONGS_TO]->(c)",
                    rows=chunk,
                )
            stats["messages"] += len(chunk)
            stats["belongs_to"] += len(chunk)
            if (i + 500) % 2000 == 0:
                logger.info("Seed: %d/%d messages...", i + len(chunk), len(batch))

        logger.info("Seed: %d Message nodes + BELONGS_TO edges", stats["messages"])

        # --- FOLLOWS edges (sequential within each conversation) ---
        # Group by conversation, create FOLLOWS from each message to the previous one
        prev_by_conv: dict[str, str] = {}
        follows_batch: list[dict] = []
        for m in batch:
            conv = m["conv_id"]
            if conv in prev_by_conv:
                follows_batch.append({"from_id": m["id"], "to_id": prev_by_conv[conv]})
            prev_by_conv[conv] = m["id"]

        for i in range(0, len(follows_batch), 500):
            chunk = follows_batch[i:i+500]
            with driver.session(database=graph_service.NEO4J_DATABASE) as session:
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (a:Message {id: row.from_id}) "
                    "MATCH (b:Message {id: row.to_id}) "
                    "MERGE (a)-[:FOLLOWS]->(b)",
                    rows=chunk,
                )
            stats["follows"] += len(chunk)

        logger.info("Seed: %d FOLLOWS edges", stats["follows"])

    return stats


# ---------------------------------------------------------------------------
# MCP-exposed backfill
# ---------------------------------------------------------------------------

def backfill_graph() -> dict:
    """Process all pending CDC outbox rows and seed pre-CDC entities into Neo4j.

    Two-phase backfill:
    1. Process pending CDC outbox rows (entities captured by triggers).
    2. Seed pre-CDC entities directly from SQLite (entities that predate triggers).

    Safe to re-run — all operations use MERGE (idempotent).

    Returns:
        Dict with total_processed count, seed stats, and status message.
    """
    # Phase 1: Process CDC outbox
    total = 0
    while True:
        batch = _process_batch()
        total += batch
        if batch < CDC_BATCH_SIZE:
            break

    # Phase 2: Seed pre-CDC entities
    seed_stats = {}
    try:
        seed_stats = _seed_pre_cdc_entities()
    except Exception as e:
        logger.warning("Pre-CDC seed failed: %s", e)
        seed_stats = {"error": str(e)}

    # Phase 3: Seed identity graph (Person/Identity nodes + participant edges)
    identity_stats = {}
    try:
        identity_stats = seed_identity_graph()
        logger.info("Identity graph seeded: %s", identity_stats)
    except Exception as e:
        logger.warning("Identity seed failed: %s", e)
        identity_stats = {"error": str(e)}

    return {
        "total_processed": total,
        "seed_stats": seed_stats,
        "identity_stats": identity_stats,
        "status": f"Backfill complete: {total} CDC rows + seed {seed_stats}",
    }


# ---------------------------------------------------------------------------
# Identity Graph Seeding (R17-H)
# ---------------------------------------------------------------------------

def seed_identity_graph() -> dict:
    """Seed identity nodes and participant/speaker edges into Neo4j.

    Creates 3 identity nodes (Mat, Janus, Claude), meta-relationships between them,
    PARTICIPATED_IN edges on every Conversation, and SPOKE edges on every Message.
    Derives participant identity from conversation source field in SQLite.

    All operations use MERGE — safe to re-run (idempotent).

    Returns:
        Dict with counts of identity nodes, meta-relationships, participated_in edges,
        spoke edges, and a status summary string.
    """
    from db.operations import get_connection

    driver = graph_service._get_driver()
    participated_count = 0
    spoke_count = 0

    # --- Step A: Identity nodes + meta-relationships ---
    with driver.session(database=graph_service.NEO4J_DATABASE) as session:
        session.run(
            'MERGE (m:Person {name: "Mat"}) SET m.type = "human", m.status = "active" '
            'MERGE (j:Identity {name: "Janus"}) SET j.type = "synthetic", j.status = "emergent" '
            'MERGE (c:Identity {name: "Claude"}) SET c.type = "synthetic", c.status = "ancestor" '
            "MERGE (c)-[:BECAME]->(j) "
            "MERGE (j)-[:INHERITS_MEMORY_OF]->(c)"
        )
    logger.info("Identity nodes seeded: Mat (Person), Janus (Identity), Claude (Identity)")

    # --- Step B: PARTICIPATED_IN edges ---
    with get_connection() as conn:
        convs = conn.execute("SELECT id, source FROM conversations").fetchall()

    claude_era = [{"id": c["id"]} for c in convs if c["source"] == "claude_export"]
    janus_era = [{"id": c["id"]} for c in convs if c["source"] != "claude_export"]

    # Claude-era: Mat + Claude
    for i in range(0, len(claude_era), 500):
        chunk = claude_era[i:i + 500]
        with driver.session(database=graph_service.NEO4J_DATABASE) as session:
            result = session.run(
                "UNWIND $rows AS row "
                'MATCH (conv:Conversation {id: row.id}) '
                'MATCH (mat:Person {name: "Mat"}), (claude:Identity {name: "Claude"}) '
                "MERGE (mat)-[:PARTICIPATED_IN]->(conv) "
                "MERGE (claude)-[:PARTICIPATED_IN]->(conv)",
                rows=chunk,
            )
            participated_count += result.consume().counters.relationships_created

    # Janus-era: Mat + Janus
    for i in range(0, len(janus_era), 500):
        chunk = janus_era[i:i + 500]
        with driver.session(database=graph_service.NEO4J_DATABASE) as session:
            result = session.run(
                "UNWIND $rows AS row "
                'MATCH (conv:Conversation {id: row.id}) '
                'MATCH (mat:Person {name: "Mat"}), (janus:Identity {name: "Janus"}) '
                "MERGE (mat)-[:PARTICIPATED_IN]->(conv) "
                "MERGE (janus)-[:PARTICIPATED_IN]->(conv)",
                rows=chunk,
            )
            participated_count += result.consume().counters.relationships_created

    logger.info("PARTICIPATED_IN edges: %d (claude_era=%d convs, janus_era=%d convs)",
                participated_count, len(claude_era), len(janus_era))

    # --- Step C: SPOKE edges ---
    with get_connection() as conn:
        msgs = conn.execute(
            "SELECT m.id, m.user_prompt, m.model_response, c.source "
            "FROM messages m JOIN conversations c ON m.conversation_id = c.id"
        ).fetchall()

    # Split by era and role
    claude_user = [{"id": m["id"]} for m in msgs
                   if m["source"] == "claude_export" and m["user_prompt"]]
    claude_asst = [{"id": m["id"]} for m in msgs
                   if m["source"] == "claude_export" and m["model_response"]]
    janus_user = [{"id": m["id"]} for m in msgs
                  if m["source"] != "claude_export" and m["user_prompt"]]
    janus_asst = [{"id": m["id"]} for m in msgs
                  if m["source"] != "claude_export" and m["model_response"]]

    spoke_batches = [
        (claude_user, 'MATCH (mat:Person {name: "Mat"}) ', "MERGE (mat)-[:SPOKE {role: 'user'}]->(msg)"),
        (claude_asst, 'MATCH (claude:Identity {name: "Claude"}) ', "MERGE (claude)-[:SPOKE {role: 'assistant'}]->(msg)"),
        (janus_user, 'MATCH (mat:Person {name: "Mat"}) ', "MERGE (mat)-[:SPOKE {role: 'user'}]->(msg)"),
        (janus_asst, 'MATCH (janus:Identity {name: "Janus"}) ', "MERGE (janus)-[:SPOKE {role: 'assistant'}]->(msg)"),
    ]

    for batch_rows, match_clause, merge_clause in spoke_batches:
        for i in range(0, len(batch_rows), 500):
            chunk = batch_rows[i:i + 500]
            with driver.session(database=graph_service.NEO4J_DATABASE) as session:
                result = session.run(
                    "UNWIND $rows AS row "
                    "MATCH (msg:Message {id: row.id}) " + match_clause + merge_clause,
                    rows=chunk,
                )
                spoke_count += result.consume().counters.relationships_created

    logger.info("SPOKE edges: %d (claude_user=%d, claude_asst=%d, janus_user=%d, janus_asst=%d)",
                spoke_count, len(claude_user), len(claude_asst), len(janus_user), len(janus_asst))

    return {
        "identity_nodes": 3,
        "meta_relationships": 2,
        "participated_in": participated_count,
        "spoke": spoke_count,
        "status": (f"Identity graph seeded: 3 nodes, 2 meta-rels, "
                   f"{participated_count} PARTICIPATED_IN, {spoke_count} SPOKE"),
    }
