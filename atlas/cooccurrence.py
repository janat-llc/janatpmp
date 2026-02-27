"""Entity co-occurrence linking — discover entity-to-entity relationships.

Scans entity mentions for co-occurrence within the same message.
When two entities are mentioned together, creates or strengthens a
CO_OCCURS_WITH edge between them. This transforms the entity graph
from isolated stars into a connected web.

Uses a watermark to process only new mentions since the last run.
First run backfills all existing mentions.

R31: The Web
"""

import logging

from atlas.config import COOCCURRENCE_BATCH_SIZE, COOCCURRENCE_MIN_SHARED

logger = logging.getLogger(__name__)


def run_cooccurrence_cycle(batch_size: int = 0) -> dict:
    """Find co-occurring entities and create/strengthen CO_OCCURS_WITH edges.

    Queries entity_mentions for pairs of entities that share messages.
    Uses a watermark (stored in settings) to only process new mentions
    since the last run. On first run, scans all mentions.

    Args:
        batch_size: Max entity pairs to process. 0 = config default.

    Returns:
        Dict with keys: processed, errors, new_edges, watermark.
    """
    batch_size = batch_size or COOCCURRENCE_BATCH_SIZE

    from db.operations import get_connection
    from services.settings import get_setting, set_setting

    # Read watermark — 0 on first run processes everything.
    # Uses rowid (monotonically increasing) instead of hex id (random).
    watermark = int(get_setting("cooccurrence_watermark") or "0")

    result = {"processed": 0, "errors": 0, "new_edges": 0, "watermark": watermark}

    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT a.entity_id AS entity_a, b.entity_id AS entity_b,
                       COUNT(DISTINCT a.message_id) AS shared_messages,
                       MAX(a.rowid, b.rowid) AS max_mention_rowid
                FROM entity_mentions a
                JOIN entity_mentions b
                    ON a.message_id = b.message_id
                    AND a.entity_id < b.entity_id
                WHERE a.rowid > ? OR b.rowid > ?
                GROUP BY a.entity_id, b.entity_id
                HAVING shared_messages >= ?
                ORDER BY shared_messages DESC
                LIMIT ?
                """,
                (watermark, watermark, COOCCURRENCE_MIN_SHARED, batch_size),
            ).fetchall()

        if not rows:
            return result

    except Exception as e:
        logger.debug("Co-occurrence query failed: %s", e)
        result["errors"] = 1
        return result

    # Write edges to Neo4j
    try:
        from graph.graph_service import merge_cooccurrence_edge
    except Exception as e:
        logger.debug("Graph service unavailable for co-occurrence: %s", e)
        result["errors"] = 1
        return result

    max_rowid = watermark
    for row in rows:
        entity_a = row["entity_a"]
        entity_b = row["entity_b"]
        shared = row["shared_messages"]
        mention_rowid = row["max_mention_rowid"]

        try:
            merge_cooccurrence_edge(entity_a, entity_b, shared)
            result["processed"] += 1

            # Track highest rowid for watermark
            if mention_rowid > max_rowid:
                max_rowid = mention_rowid

        except Exception as e:
            logger.debug("Co-occurrence edge failed for %s↔%s: %s",
                         entity_a[:12], entity_b[:12], e)
            result["errors"] += 1

    # Update watermark
    if max_rowid > watermark:
        try:
            set_setting("cooccurrence_watermark", str(max_rowid))
            result["watermark"] = max_rowid
        except Exception as e:
            logger.debug("Failed to update co-occurrence watermark: %s", e)

    if result["processed"]:
        logger.info("Co-occurrence linking: %d edges processed (%d errors)",
                     result["processed"], result["errors"])

    return result


def get_cooccurrence_neighbors(entity_id: str, limit: int = 5) -> list[dict]:
    """Get entities that co-occur with the given entity.

    Queries Neo4j for CO_OCCURS_WITH neighbors, returning them sorted
    by weight (shared message count) descending.

    Args:
        entity_id: The entity ID to find neighbors for.
        limit: Maximum neighbors to return.

    Returns:
        List of dicts with keys: id, name, entity_type, weight.
        Empty list if Neo4j is unavailable or no neighbors exist.
    """
    try:
        from graph.graph_service import _get_driver
        from atlas.config import NEO4J_DATABASE

        driver = _get_driver()
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(
                "MATCH (e:Entity {id: $entity_id})-[r:CO_OCCURS_WITH]-(other:Entity) "
                "RETURN other.id AS id, other.name AS name, "
                "other.entity_type AS entity_type, r.weight AS weight "
                "ORDER BY r.weight DESC LIMIT $limit",
                entity_id=entity_id, limit=limit,
            )
            return [dict(record) for record in result]

    except Exception as e:
        logger.debug("Co-occurrence neighbor query failed for %s: %s",
                     entity_id[:12], e)
        return []
