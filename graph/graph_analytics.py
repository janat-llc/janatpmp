"""Graph analytics via Neo4j GDS — centrality computation (R50: Foundation Lock).

Uses the Graph Data Science plugin to compute entity centrality metrics.
Cross-references SQLite for conversation coverage and salience context.
"""

import logging
from db.operations import get_connection
from graph.graph_service import _get_driver

logger = logging.getLogger(__name__)


def compute_centrality(metric: str = "betweenness", limit: int = 10) -> list[dict]:
    """Compute entity centrality scores using Neo4j GDS.

    Projects Entity nodes with MENTIONS and CO_OCCURS_WITH relationships,
    runs the requested centrality algorithm, and cross-references SQLite
    for conversation coverage and average salience per entity.

    Args:
        metric: Centrality algorithm — "betweenness" or "degree". Default "betweenness".
        limit: Maximum number of top-ranked entities to return. Default 10.

    Returns:
        List of dicts ordered by score descending, each containing:
        - entity_name: str — entity display name
        - entity_id: str — entity UUID
        - score: float — centrality score (rounded to 6 decimal places)
        - conversation_count: int — distinct conversations the entity appears in
        - avg_salience: float — mean salience_score of messages mentioning this entity
        Returns empty list if GDS is unavailable or the projection fails.
    """
    if metric not in ("betweenness", "degree"):
        logger.warning(f"compute_centrality: unsupported metric '{metric}' — use betweenness or degree")
        return []

    gds_proc = "gds.betweenness.stream" if metric == "betweenness" else "gds.degree.stream"

    graph_name = f"janat_centrality_{metric}"
    try:
        driver = _get_driver()
        with driver.session() as session:
            # GDS 2.x requires named graph projections — drop stale projection if present
            exists = session.run(
                "CALL gds.graph.exists($name) YIELD exists", name=graph_name
            ).single()["exists"]
            if exists:
                session.run("CALL gds.graph.drop($name) YIELD graphName", name=graph_name)

            # Project Entity nodes with MENTIONS + CO_OCCURS_WITH (undirected)
            session.run(
                """
                CALL gds.graph.project(
                    $name,
                    'Entity',
                    {
                        MENTIONS:      {orientation: 'UNDIRECTED'},
                        CO_OCCURS_WITH: {orientation: 'UNDIRECTED'}
                    }
                )
                """,
                name=graph_name,
            )

            # Run algorithm on the named projection
            result = session.run(
                f"""
                CALL {gds_proc}($name)
                YIELD nodeId, score
                RETURN gds.util.asNode(nodeId).name AS name,
                       gds.util.asNode(nodeId).id   AS entity_id,
                       score
                ORDER BY score DESC
                LIMIT $limit
                """,
                name=graph_name,
                limit=limit,
            )
            neo4j_rows = [
                {"name": r["name"], "entity_id": r["entity_id"], "score": r["score"]}
                for r in result
            ]

            # Always clean up the in-memory projection
            session.run("CALL gds.graph.drop($name) YIELD graphName", name=graph_name)
    except Exception as e:
        logger.warning(f"GDS centrality unavailable (metric={metric}): {e}")
        # Best-effort cleanup
        try:
            driver = _get_driver()
            with driver.session() as s:
                s.run("CALL gds.graph.drop($name) YIELD graphName", name=graph_name)
        except Exception:
            pass
        return []

    if not neo4j_rows:
        return []

    # Cross-reference SQLite for conversation_count and avg_salience
    names = [r["name"] for r in neo4j_rows]
    placeholders = ",".join("?" * len(names))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT e.name,
                   e.id,
                   COUNT(DISTINCT em.conversation_id) AS conversation_count,
                   AVG(mm.salience_score)              AS avg_salience
            FROM entities e
            LEFT JOIN entity_mentions em ON em.entity_id = e.id
            LEFT JOIN messages_metadata mm ON mm.message_id = em.message_id
            WHERE e.name IN ({placeholders})
            GROUP BY e.id
            """,
            names,
        ).fetchall()
    sqlite_map = {r["name"]: dict(r) for r in rows}

    return [
        {
            "entity_name": r["name"],
            "entity_id": r["entity_id"] or sqlite_map.get(r["name"], {}).get("id", ""),
            "score": round(r["score"], 6),
            "conversation_count": sqlite_map.get(r["name"], {}).get("conversation_count", 0) or 0,
            "avg_salience": round(sqlite_map.get(r["name"], {}).get("avg_salience") or 0.0, 3),
        }
        for r in neo4j_rows
    ]
