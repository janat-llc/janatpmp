"""On-write pipeline — synchronous chunk + embed + fire-and-forget graph edges.

Called after every add_message() across all three chat surfaces.
Fans out to Qdrant (synchronous embed) and Neo4j (INFORMED_BY edges).

R16: Messages are now chunked before embedding. Each chunk gets its own
Qdrant point with a composite ID ({message_id} for single-chunk,
{message_id}_c{NNN} for multi-chunk). Chunk records are persisted to the
SQLite chunks table for tracking, FTS, and Slumber Cycle operations.

The embed path is synchronous (~100-300ms) to ensure success criterion #1:
the message is immediately retrievable by RAG on the next turn.

The relate path is fire-and-forget — Neo4j being down must never block chat.
Structural edges (BELONGS_TO, FOLLOWS) are handled by the CDC consumer.
This module ONLY creates INFORMED_BY edges (requires rag_hits).
"""

import logging

from atlas.config import SALIENCE_DEFAULT

logger = logging.getLogger(__name__)


def on_message_write(
    message_id: str,
    conversation_id: str,
    user_prompt: str,
    model_response: str,
    sequence: int | None = None,
    provider: str = "",
    model: str = "",
    rag_hits: list[dict] | None = None,
    role: str = "turn",
) -> None:
    """Synchronous chunk + embed + fire-and-forget INFORMED_BY edges.

    Args:
        message_id: The persisted message ID from add_message().
        conversation_id: Parent conversation ID.
        user_prompt: The user's message text.
        model_response: The model's response text (clean, no reasoning).
        sequence: Message sequence number (queries DB if None).
        provider: Chat provider name.
        model: Chat model name.
        rag_hits: List of RAG score dicts from _build_rag_context().
        role: Message role — 'turn' for chat, 'system/*' for cognition signals.
    """
    _embed(message_id, conversation_id, user_prompt, model_response,
           sequence, provider, model, role=role)
    # Only create INFORMED_BY edges for turn messages (not cognition signals)
    if role == "turn":
        _relate(message_id, rag_hits)


def _generate_point_id(message_id: str, chunk_index: int, chunk_total: int) -> str:
    """Generate Qdrant point ID for a chunk.

    Qdrant collections that contain UUID-typed points reject non-UUID strings.
    Since bare 32-char hex entity_ids are auto-parsed as UUIDs by Qdrant,
    multi-chunk IDs must also be valid UUIDs.

    Single-chunk messages use the raw message_id (backward compatible).
    Multi-chunk messages use UUID v5 derived from message_id + chunk_index
    (deterministic: same input always produces the same UUID).
    """
    if chunk_total <= 1:
        return message_id
    import uuid
    namespace = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    return str(uuid.uuid5(namespace, f"{message_id}_c{chunk_index:03d}"))


def _get_message_context(
    message_id: str,
    conversation_id: str,
    sequence: int | None,
) -> tuple[str, str, int]:
    """Fetch conversation title, created_at, and sequence from DB.

    Returns:
        Tuple of (conv_title, created_at, sequence).
    """
    from db.chat_operations import get_conversation

    conv_title = ""
    try:
        conv = get_conversation(conversation_id)
        if conv:
            conv_title = conv.get("title", "")
    except Exception:
        pass

    created_at = ""
    if sequence is None:
        try:
            from db.operations import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT sequence, created_at FROM messages WHERE id = ?",
                    (message_id,),
                ).fetchone()
                if row:
                    sequence = row["sequence"]
                    created_at = row["created_at"]
        except Exception:
            sequence = 0
    if not created_at:
        try:
            from db.operations import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT created_at FROM messages WHERE id = ?",
                    (message_id,),
                ).fetchone()
                if row:
                    created_at = row["created_at"]
        except Exception:
            pass

    return conv_title, created_at, sequence or 0


def _insert_chunks_for(
    entity_type: str,
    entity_id: str,
    chunks: list[dict],
    point_ids: list[str],
) -> None:
    """Persist chunk records to SQLite chunks table.

    Args:
        entity_type: 'message' or 'document'.
        entity_id: The parent entity ID.
        chunks: List of chunk dicts from atlas/chunking.py.
        point_ids: Corresponding Qdrant point IDs.
    """
    try:
        from db.operations import get_connection
        with get_connection() as conn:
            for chunk, point_id in zip(chunks, point_ids):
                conn.execute(
                    """INSERT OR IGNORE INTO chunks
                       (entity_type, entity_id, chunk_index, chunk_text,
                        char_start, char_end, position, point_id, embedded_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (entity_type, entity_id, chunk["index"], chunk["text"],
                     chunk["char_start"], chunk["char_end"],
                     chunk["position"], point_id),
                )
            conn.commit()
    except Exception as e:
        logger.warning("on_write chunk insert failed for %s: %s", entity_id[:12], e)


def _embed(
    message_id: str,
    conversation_id: str,
    user_prompt: str,
    model_response: str,
    sequence: int | None,
    provider: str,
    model: str,
    role: str = "turn",
) -> None:
    """Synchronous: chunk and embed the message into Qdrant."""
    # System messages use content-only text (no Q:/A: wrapper)
    if role.startswith("system/"):
        text = user_prompt
        entity_type_label = "cognition"
    else:
        text = f"Q: {user_prompt}\nA: {model_response}"
        entity_type_label = "message"

    if len(text) < 20:
        return

    try:
        from atlas.chunking import chunk_message
        from services.embedding import embed_passages
        from services.vector_store import upsert_point
        from services.settings import get_setting

        # Read chunk settings
        max_chars = int(get_setting("chunk_max_chars") or 2500)
        threshold = int(get_setting("chunk_threshold") or 3000)

        # Chunk the message
        chunks = chunk_message(
            user_prompt, model_response,
            max_chars=max_chars, threshold=threshold,
        )
        if not chunks:
            return

        # Fetch conversation context
        conv_title, created_at, seq = _get_message_context(
            message_id, conversation_id, sequence,
        )

        # Generate point IDs
        chunk_total = len(chunks)
        point_ids = [
            _generate_point_id(message_id, c["index"], chunk_total)
            for c in chunks
        ]

        # Embed all chunks in one batch call
        chunk_texts = [c["text"] for c in chunks]
        vectors = embed_passages(chunk_texts)

        # Build base payload (shared across chunks)
        base_payload = {
            "parent_message_id": message_id,
            "conversation_id": conversation_id,
            "conv_title": conv_title,
            "sequence": seq,
            "created_at": created_at,
            "provider": provider,
            "model": model,
            "salience": SALIENCE_DEFAULT,
            "entity_type": entity_type_label,
        }

        # Upsert each chunk to Qdrant
        from services.vector_store import COLLECTION_MESSAGES
        for chunk, vector, point_id in zip(chunks, vectors, point_ids):
            payload = {
                **base_payload,
                "text": chunk["text"],
                "chunk_index": chunk["index"],
                "chunk_total": chunk_total,
                "chunk_position": chunk["position"],
            }
            upsert_point(COLLECTION_MESSAGES, point_id, vector, payload)

        # Persist chunk records to SQLite
        _insert_chunks_for("message", message_id, chunks, point_ids)

        logger.debug(
            "on_write embed: %s -> %d chunk(s) in Qdrant",
            message_id[:12], chunk_total,
        )

    except Exception as e:
        logger.warning("on_write embed failed for %s: %s", message_id[:12], e)


def _relate(message_id: str, rag_hits: list[dict] | None) -> None:
    """Fire-and-forget: create INFORMED_BY edges in Neo4j."""
    if not rag_hits:
        return

    try:
        from graph.graph_service import create_edge

        for hit in rag_hits:
            hit_id = hit.get("id")
            if not hit_id:
                continue

            source = hit.get("source", "")
            to_label = "Document" if "document" in source.lower() else "Message"

            props = {}
            if hit.get("rerank_score"):
                props["rerank_score"] = hit["rerank_score"]
            if hit.get("salience"):
                props["salience"] = hit["salience"]

            create_edge("Message", message_id, to_label, hit_id, "INFORMED_BY", props)

        logger.debug("on_write relate: %s -> %d INFORMED_BY edges",
                      message_id[:12], len([h for h in rag_hits if h.get("id")]))

    except Exception as e:
        logger.debug("on_write relate skipped for %s: %s", message_id[:12], e)


# ---------------------------------------------------------------------------
# R27: On-write hooks for non-message entities
# ---------------------------------------------------------------------------


def on_document_write(
    document_id: str,
    title: str,
    content: str,
    doc_type: str = "",
    source: str = "",
) -> None:
    """Synchronous chunk + embed a document into Qdrant.

    Called after create_document() to make the document immediately
    retrievable via RAG search. Follows the same try/except isolation
    pattern as on_message_write() — Qdrant/Ollama being down never
    blocks document creation.

    Args:
        document_id: The persisted document ID from create_document().
        title: Document title.
        content: Document content text.
        doc_type: Document type (file, artifact, research, etc.).
        source: Document source (upload, agent, manual, etc.).
    """
    if len(content) < 20:
        return

    try:
        from datetime import datetime, timezone

        from atlas.chunking import chunk_document
        from services.embedding import embed_passages
        from services.settings import get_setting
        from services.vector_store import COLLECTION_DOCUMENTS, upsert_point

        max_chars = int(get_setting("chunk_max_chars") or 2500)
        threshold = int(get_setting("chunk_threshold") or 3000)

        chunks = chunk_document(
            content, title=title or "",
            max_chars=max_chars, threshold=threshold,
        )
        if not chunks:
            return

        chunk_total = len(chunks)
        point_ids = [
            _generate_point_id(document_id, c["index"], chunk_total)
            for c in chunks
        ]

        chunk_texts = [c["text"] for c in chunks]
        vectors = embed_passages(chunk_texts)

        now_iso = datetime.now(timezone.utc).isoformat()
        base_payload = {
            "parent_document_id": document_id,
            "title": title or "",
            "doc_type": doc_type,
            "source": source,
            "created_at": now_iso,
            "salience": SALIENCE_DEFAULT,
            "entity_type": "document",
        }

        for chunk, vector, point_id in zip(chunks, vectors, point_ids):
            payload = {
                **base_payload,
                "text": chunk["text"],
                "chunk_index": chunk["index"],
                "chunk_total": chunk_total,
                "chunk_position": chunk["position"],
            }
            upsert_point(COLLECTION_DOCUMENTS, point_id, vector, payload)

        _insert_chunks_for("document", document_id, chunks, point_ids)

        logger.debug(
            "on_write embed document: %s -> %d chunk(s) in Qdrant",
            document_id[:12], chunk_total,
        )

    except Exception as e:
        logger.warning("on_write embed document failed for %s: %s",
                        document_id[:12], e)


def on_item_write(
    item_id: str,
    entity_type: str,
    domain: str,
    title: str,
    description: str = "",
) -> None:
    """Embed an item into Qdrant for immediate RAG discoverability.

    Items are short texts — no chunking needed, single vector each.
    Payload matches embed_all_items() in services/bulk_embed.py.

    Args:
        item_id: The persisted item ID from create_item().
        entity_type: Item type (project, epic, feature, etc.).
        domain: Domain name.
        title: Item title.
        description: Optional item description.
    """
    text = f"{entity_type}: {title}"
    if description:
        text += f"\n{description}"
    if len(text) < 10:
        return

    try:
        from datetime import datetime, timezone

        from services.embedding import embed_passages
        from services.vector_store import COLLECTION_DOCUMENTS, upsert_point

        vectors = embed_passages([text])
        payload = {
            "text": text,
            "entity_type": "item",
            "item_type": entity_type,
            "title": title or "",
            "domain": domain or "",
            "status": "not_started",
            "priority": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_point(COLLECTION_DOCUMENTS, item_id, vectors[0], payload)

        logger.debug("on_write embed item: %s", item_id[:12])

    except Exception as e:
        logger.warning("on_write embed item failed for %s: %s",
                        item_id[:12], e)


def on_task_write(
    task_id: str,
    task_type: str,
    title: str,
    description: str = "",
    agent_instructions: str = "",
) -> None:
    """Embed a task into Qdrant for immediate RAG discoverability.

    Tasks are short texts — no chunking needed, single vector each.
    Payload matches embed_all_tasks() in services/bulk_embed.py.

    Args:
        task_id: The persisted task ID from create_task().
        task_type: Task type (agent_story, research, etc.).
        title: Task title.
        description: Optional task description.
        agent_instructions: Optional detailed instructions.
    """
    text = f"Task: {title}"
    if description:
        text += f"\n{description}"
    if agent_instructions:
        text += f"\n{agent_instructions}"
    if len(text) < 10:
        return

    try:
        from datetime import datetime, timezone

        from services.embedding import embed_passages
        from services.vector_store import COLLECTION_DOCUMENTS, upsert_point

        vectors = embed_passages([text])
        payload = {
            "text": text,
            "entity_type": "task",
            "task_type": task_type or "",
            "title": title or "",
            "assigned_to": "",
            "status": "not_started",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_point(COLLECTION_DOCUMENTS, task_id, vectors[0], payload)

        logger.debug("on_write embed task: %s", task_id[:12])

    except Exception as e:
        logger.warning("on_write embed task failed for %s: %s",
                        task_id[:12], e)
