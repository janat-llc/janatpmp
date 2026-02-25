"""Graph-aware RAG ranking — boost candidates using Neo4j topology.

Given RAG candidates from Qdrant + FTS, consult SIMILAR_TO edges to boost
chunks from conversations in the query's topic neighborhood. Additive scoring:
graph can promote borderline candidates above threshold but can't make
irrelevant content appear relevant.

R21: The Strange Loop
"""

import logging
from collections import defaultdict

from atlas.config import (
    GRAPH_BOOST_FACTOR,
    GRAPH_TOPIC_CONVERSATIONS,
    NEO4J_DATABASE,
)

logger = logging.getLogger(__name__)

_NEIGHBORHOOD_CYPHER = """\
MATCH (c:Conversation {id: $conv_id})-[r:SIMILAR_TO]-(neighbor:Conversation)
RETURN neighbor.id AS neighbor_id, r.score AS score
ORDER BY r.score DESC
LIMIT 10
"""


def _get_neighborhood(seed_conv_ids: list[str]) -> dict[str, float]:
    """Query Neo4j for SIMILAR_TO neighbors of seed conversations.

    Args:
        seed_conv_ids: Conversation IDs to traverse from.

    Returns:
        Dict mapping neighbor conversation_id to its max edge score
        across all seed traversals. Excludes seed IDs themselves.
    """
    from graph.graph_service import _get_driver

    neighborhood: dict[str, float] = {}
    seed_set = set(seed_conv_ids)

    try:
        driver = _get_driver()
        with driver.session(database=NEO4J_DATABASE) as session:
            for conv_id in seed_conv_ids:
                result = session.run(_NEIGHBORHOOD_CYPHER, conv_id=conv_id)
                for record in result:
                    nid = record["neighbor_id"]
                    score = record["score"] or 0.0
                    if nid and nid not in seed_set:
                        neighborhood[nid] = max(neighborhood.get(nid, 0.0), score)
    except Exception as e:
        logger.debug("Graph neighborhood query failed: %s", e)

    return neighborhood


def compute_graph_affinity(
    candidates: list[dict],
    boost_factor: float = 0.0,
) -> tuple[list[dict], dict]:
    """Boost RAG candidates using graph topology.

    Groups candidates by conversation_id, identifies the top-N source
    conversations, queries Neo4j for their SIMILAR_TO neighbors, and
    applies an additive score boost to candidates from neighboring
    conversations.

    Args:
        candidates: RAG results from Qdrant + FTS merge. Each dict should
            have 'conversation_id' (or 'source_conversation_id') and 'score'.
        boost_factor: Multiplier for SIMILAR_TO edge score bonus. 0 uses default.

    Returns:
        Tuple of (modified candidates list with 'graph_boost' field added,
        trace dict for cognition introspection).
    """
    factor = boost_factor if boost_factor > 0 else GRAPH_BOOST_FACTOR

    trace: dict = {
        "seed_conversations": [],
        "neighborhood_size": 0,
        "neighborhood": {},
        "candidates_boosted": 0,
        "candidates_total": len(candidates),
    }

    if not candidates:
        return candidates, trace

    # Step 1: Group candidates by conversation_id, compute mean score per conversation
    conv_scores: dict[str, list[float]] = defaultdict(list)
    conv_titles: dict[str, str] = {}
    for c in candidates:
        conv_id = c.get("conversation_id") or c.get("source_conversation_id") or ""
        if conv_id:
            score = c.get("score", 0.0)
            conv_scores[conv_id].append(score)
            if conv_id not in conv_titles:
                conv_titles[conv_id] = c.get("conv_title", c.get("title", ""))

    # Step 2: Pick top-N conversations by mean score as seeds
    conv_means = [
        (cid, sum(scores) / len(scores))
        for cid, scores in conv_scores.items()
    ]
    conv_means.sort(key=lambda x: x[1], reverse=True)
    seed_ids = [cid for cid, _ in conv_means[:GRAPH_TOPIC_CONVERSATIONS]]

    trace["seed_conversations"] = [
        {"id": cid, "title": conv_titles.get(cid, ""), "mean_score": round(ms, 4)}
        for cid, ms in conv_means[:GRAPH_TOPIC_CONVERSATIONS]
    ]

    if not seed_ids:
        return candidates, trace

    # Step 3: Query Neo4j for SIMILAR_TO neighbors
    neighborhood = _get_neighborhood(seed_ids)
    trace["neighborhood_size"] = len(neighborhood)
    trace["neighborhood"] = {k: round(v, 4) for k, v in neighborhood.items()}

    if not neighborhood:
        return candidates, trace

    # Step 4: Apply additive boost to candidates from neighboring conversations
    boosted_count = 0
    for c in candidates:
        conv_id = c.get("conversation_id") or c.get("source_conversation_id") or ""
        edge_score = neighborhood.get(conv_id, 0.0)
        if edge_score > 0:
            boost = edge_score * factor
            c["score"] = c.get("score", 0.0) + boost
            c["graph_boost"] = round(boost, 4)
            boosted_count += 1
        else:
            c["graph_boost"] = 0.0

    trace["candidates_boosted"] = boosted_count

    # Step 5: Re-sort by boosted score
    candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    logger.info(
        "Graph ranking: %d seeds, %d neighbors, %d/%d candidates boosted (factor=%.2f)",
        len(seed_ids), len(neighborhood), boosted_count, len(candidates), factor,
    )

    return candidates, trace
