"""Graph-based retrieval — walk entity edges to pull source messages.

When entity routing identifies a referenced entity, use MENTIONS and
DISCUSSED_IN edges in Neo4j to retrieve the actual source messages
and conversation context. This is a retrieval source, not a re-ranker.

R30: Entity-Aware RAG Routing
"""

import logging

logger = logging.getLogger(__name__)


def retrieve_entity_sources(
    entity_ids: list[str],
    max_messages_per_entity: int = 5,
    max_total: int = 10,
) -> tuple[list[dict], dict]:
    """Walk graph edges from entities to source messages.

    For each entity, queries Neo4j for (Message)-[:MENTIONS]->(Entity)
    edges, then pulls the actual message text from SQLite. Returns
    source messages as retrieval candidates alongside a trace dict
    for the Cognition Tab.

    Args:
        entity_ids: Entity IDs from entity routing matches.
        max_messages_per_entity: Max source messages per entity.
        max_total: Max total messages returned across all entities.

    Returns:
        Tuple of:
        - List of source message dicts with text, conversation_id, message_id
        - Trace dict for Cognition Tab
    """
    trace = {
        "entity_ids_queried": list(entity_ids),
        "messages_retrieved": 0,
        "conversations_touched": 0,
    }

    if not entity_ids:
        return [], trace

    try:
        from graph.graph_service import graph_query
    except Exception as e:
        logger.debug("Graph service unavailable for retrieval: %s", e)
        return [], trace

    all_message_ids: list[tuple[str, str]] = []  # (message_id, entity_id)
    conversation_ids: set[str] = set()

    for entity_id in entity_ids:
        try:
            # Edge direction: (Message)-[:MENTIONS]->(Entity)
            # Entity IDs are hex strings from randomblob(16) — safe to inline
            cypher = (
                f"MATCH (msg:Message)-[:MENTIONS]->(e:Entity {{id: '{entity_id}'}}) "
                f"RETURN msg.id AS message_id "
                f"LIMIT {max_messages_per_entity}"
            )
            rows = graph_query(cypher)
            if isinstance(rows, list) and rows and "error" in rows[0]:
                logger.debug("Graph query error: %s", rows[0].get("error"))
                continue

            for row in rows:
                msg_id = row.get("message_id")
                if msg_id:
                    all_message_ids.append((msg_id, entity_id))

        except Exception as e:
            logger.debug("Graph retrieval failed for entity %s: %s",
                         entity_id[:12], e)

    if not all_message_ids:
        return [], trace

    # Deduplicate and cap at max_total
    seen_ids: set[str] = set()
    unique_ids: list[tuple[str, str]] = []
    for msg_id, ent_id in all_message_ids:
        if msg_id not in seen_ids:
            seen_ids.add(msg_id)
            unique_ids.append((msg_id, ent_id))
    unique_ids = unique_ids[:max_total]

    # Pull message text from SQLite
    try:
        from db.chat_operations import get_message
    except ImportError:
        logger.debug("chat_operations.get_message not available")
        return [], trace

    messages: list[dict] = []
    for msg_id, ent_id in unique_ids:
        try:
            msg = get_message(msg_id)
            if not msg:
                logger.debug("Message %s not found in SQLite", msg_id[:12])
                continue

            # Prefer model_response for context, fall back to user_prompt
            text = msg.get("model_response") or msg.get("user_prompt") or ""
            if not text or len(text) < 20:
                continue

            conv_id = msg.get("conversation_id", "")
            if conv_id:
                conversation_ids.add(conv_id)

            messages.append({
                "message_id": msg_id,
                "text": text,
                "conversation_id": conv_id,
                "source": "graph_retrieval",
                "entity_id": ent_id,
            })
        except Exception as e:
            logger.debug("Failed to fetch message %s: %s", msg_id[:12], e)

    trace["messages_retrieved"] = len(messages)
    trace["conversations_touched"] = len(conversation_ids)

    return messages, trace
