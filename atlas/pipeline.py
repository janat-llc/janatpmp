"""ATLAS pipeline — DECOMMISSIONED reranker orchestration.

DECOMMISSIONED (R49): vLLM reranker container removed. This module is retained
for import compatibility only. The rerank_and_write_salience() function is never
called in production (rerank=False everywhere). RAG scoring is now handled by
composite scoring in services/chat.py: cosine × temporal × salience_factor.
"""

import logging

from atlas.config import RAG_ANN_CANDIDATES, RAG_RETURN_TOP
from atlas.reranking_service import rerank
from atlas.memory_service import write_salience

logger = logging.getLogger(__name__)


def rerank_and_write_salience(
    query: str,
    candidates: list[dict],
    collection: str,
    limit: int = RAG_RETURN_TOP,
) -> list[dict]:
    """Rerank ANN candidates and write salience back to Qdrant.

    Args:
        query: The search query text.
        candidates: ANN search results (dicts with 'id', 'text', 'score', etc.).
        collection: Qdrant collection the candidates came from.
        limit: Number of results to return after reranking.

    Returns:
        Top-limit candidates reordered by rerank score.
    """
    if not candidates:
        return candidates

    try:
        reranked = rerank(query, candidates)
    except Exception as e:
        logger.warning("Reranker unavailable, returning ANN results: %s", e)
        return candidates[:limit]

    # Write salience back (async-safe, non-blocking on failure)
    try:
        write_salience(collection, reranked)
    except Exception as e:
        logger.debug("Salience write-back failed: %s", e)

    return reranked[:limit]
