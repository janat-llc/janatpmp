"""ATLAS pipeline — orchestrates embed → rerank → salience write-back.

Two-stage retrieval: ANN search produces candidates, cross-encoder reranker
reorders them, salience signal is written back to Qdrant.
"""

import logging

from atlas.config import RERANK_CANDIDATES, RERANK_RETURN
from atlas.reranking_service import get_reranker, release_reranker
from atlas.memory_service import write_salience

logger = logging.getLogger(__name__)


def rerank_and_write_salience(
    query: str,
    candidates: list[dict],
    collection: str,
    limit: int = RERANK_RETURN,
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
        reranker = get_reranker()
        reranked = reranker.rerank(query, candidates)
    except Exception as e:
        logger.warning("Reranker unavailable, returning ANN results: %s", e)
        return candidates[:limit]
    finally:
        release_reranker()

    # Write salience back (async-safe, non-blocking on failure)
    try:
        write_salience(collection, reranked)
    except Exception as e:
        logger.debug("Salience write-back failed: %s", e)

    return reranked[:limit]
