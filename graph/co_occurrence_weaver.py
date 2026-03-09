"""Conversation-level CO_OCCURS_WITH weaving — entity bridge formation.

Extends the message-scope co-occurrence system (atlas/cooccurrence.py) with
conversation-scope weaving. Two entities that appear in the same conversation
(even in different messages) get a CO_OCCURS_WITH edge weighted by the total
number of conversations where they co-occur across the corpus.

This is the bridge mechanism for EXP-001 Phase 4 — connecting the Genesis
Block crystal to the main knowledge graph.

R51: CO_OCCURS_WITH Crystallization
"""

import logging

from db.operations import get_connection
from graph.graph_service import merge_cooccurrence_edge
from services.settings import get_setting, set_setting

logger = logging.getLogger(__name__)

# Minimum total shared conversations to create an edge (per R51 brief)
MIN_SHARED_CONVERSATIONS = 2


def weave_conversation_cooccurrences(
    conversation_id: str,
    min_shared_conversations: int = MIN_SHARED_CONVERSATIONS,
) -> dict:
    """Create CO_OCCURS_WITH edges for entities sharing a conversation.

    Two-phase approach: first finds entity pairs in the given conversation,
    then for each pair counts their TOTAL shared conversations across the
    entire corpus. Weight is set to the corpus-wide total so re-runs are
    idempotent and weight always reflects true co-occurrence frequency.

    Only pairs meeting min_shared_conversations threshold get edges —
    single-conversation noise is excluded by default (threshold=2).

    Args:
        conversation_id: The conversation ID to process.
        min_shared_conversations: Minimum total shared conversations
            required to create an edge. Default 2 (per R51 brief).

    Returns:
        Dict with keys:
        - conversation_id: str — the conversation processed
        - entities_found: int — distinct entities in this conversation
        - pairs_found: int — entity pairs found in this conversation
        - edges_created: int — CO_OCCURS_WITH edges written to Neo4j
        - errors: int — edges that failed to write
    """
    result = {
        "conversation_id": conversation_id,
        "entities_found": 0,
        "pairs_found": 0,
        "edges_created": 0,
        "errors": 0,
    }

    try:
        with get_connection() as conn:
            # Single batch query: find entity pairs in this conversation AND
            # count their total shared conversations across the entire corpus.
            # Uses the entity set of this conversation as a filter, then
            # counts co-occurrences corpus-wide. O(index scans) vs O(n²) subqueries.
            rows = conn.execute(
                """
                SELECT a.entity_id AS entity_a,
                       b.entity_id AS entity_b,
                       COUNT(DISTINCT a.conversation_id) AS total_convs
                FROM entity_mentions a
                JOIN entity_mentions b
                    ON a.conversation_id = b.conversation_id
                    AND a.entity_id < b.entity_id
                WHERE a.entity_id IN (
                    SELECT DISTINCT entity_id FROM entity_mentions WHERE conversation_id = ?
                )
                AND b.entity_id IN (
                    SELECT DISTINCT entity_id FROM entity_mentions WHERE conversation_id = ?
                )
                GROUP BY a.entity_id, b.entity_id
                HAVING total_convs >= ?
                """,
                (conversation_id, conversation_id, min_shared_conversations),
            ).fetchall()

            # Count distinct entities for reporting
            entity_count = conn.execute(
                "SELECT COUNT(DISTINCT entity_id) FROM entity_mentions WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            result["entities_found"] = entity_count

            # All pairs from this conversation (before threshold filter)
            pair_count = conn.execute(
                """
                SELECT COUNT(DISTINCT a.entity_id || '|' || b.entity_id)
                FROM entity_mentions a
                JOIN entity_mentions b
                    ON a.conversation_id = b.conversation_id
                    AND a.entity_id < b.entity_id
                WHERE a.conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()[0]
            result["pairs_found"] = pair_count

            if not rows:
                return result

            for row in rows:
                entity_a = row["entity_a"]
                entity_b = row["entity_b"]
                total_convs = row["total_convs"]
                try:
                    merge_cooccurrence_edge(entity_a, entity_b, total_convs)
                    result["edges_created"] += 1
                except Exception as e:
                    logger.debug(
                        "CO_OCCURS_WITH edge failed %s↔%s: %s",
                        entity_a[:12], entity_b[:12], e,
                    )
                    result["errors"] += 1

    except Exception as e:
        logger.warning("weave_conversation_cooccurrences failed for %s: %s", conversation_id[:12], e)
        result["errors"] += 1

    if result["edges_created"] > 0:
        logger.debug(
            "Conversation %s: %d pairs → %d CO_OCCURS_WITH edges",
            conversation_id[:12], result["pairs_found"], result["edges_created"],
        )

    return result


def weave_all_conversations(limit: int = 100, offset: int = 0) -> dict:
    """Batch conversation-scope CO_OCCURS_WITH weaving with watermark.

    Processes conversations that have entity mentions since the last run,
    using a rowid watermark stored in settings as 'conv_cooccurrence_watermark'.
    On first run (watermark=0), processes all conversations with entity mentions.

    Safe to call repeatedly — watermark advances after each batch, and
    weave_conversation_cooccurrences() is idempotent (weight = total corpus count).

    Args:
        limit: Maximum conversations to process in this call. Default 100.
        offset: Unused — kept for API symmetry with other batch tools. The
            watermark provides incremental processing across calls.

    Returns:
        Dict with keys:
        - conversations_processed: int — number of conversations weaved
        - total_edges: int — CO_OCCURS_WITH edges written across all conversations
        - total_pairs: int — entity pairs evaluated
        - errors: int — conversations or edges that failed
        - watermark: int — new watermark value after this batch
    """
    result = {
        "conversations_processed": 0,
        "total_edges": 0,
        "total_pairs": 0,
        "errors": 0,
        "watermark": 0,
    }

    watermark = int(get_setting("conv_cooccurrence_watermark") or "0")
    result["watermark"] = watermark

    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT c.rowid, c.id
                FROM conversations c
                JOIN entity_mentions em ON em.conversation_id = c.id
                WHERE c.rowid > ?
                ORDER BY c.rowid
                LIMIT ?
                """,
                (watermark, limit),
            ).fetchall()
    except Exception as e:
        logger.warning("weave_all_conversations query failed: %s", e)
        result["errors"] += 1
        return result

    if not rows:
        logger.debug("weave_all_conversations: no new conversations since watermark=%d", watermark)
        return result

    max_rowid = watermark
    for row in rows:
        conv_rowid = row["rowid"]
        conv_id = row["id"]

        conv_result = weave_conversation_cooccurrences(conv_id)
        result["conversations_processed"] += 1
        result["total_edges"] += conv_result["edges_created"]
        result["total_pairs"] += conv_result["pairs_found"]
        result["errors"] += conv_result["errors"]

        if conv_rowid > max_rowid:
            max_rowid = conv_rowid

    # Advance watermark
    if max_rowid > watermark:
        try:
            set_setting("conv_cooccurrence_watermark", str(max_rowid))
            result["watermark"] = max_rowid
        except Exception as e:
            logger.warning("Failed to update conv_cooccurrence_watermark: %s", e)

    logger.info(
        "weave_all_conversations: %d conversations → %d CO_OCCURS_WITH edges (%d errors)",
        result["conversations_processed"], result["total_edges"], result["errors"],
    )

    return result
