"""ATLAS reranking service — Qwen3-Reranker-0.6B via vLLM.

HTTP client to vLLM's /v1/score endpoint. Returns 0-1 probability scores
(not unbounded logits like the previous Nemotron VL reranker).
"""

import logging

import httpx

from atlas.config import VLLM_RERANK_URL, RERANKER_MODEL

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> httpx.Client:
    """Lazy-init httpx client for vLLM score endpoint."""
    global _client
    if _client is None:
        _client = httpx.Client(base_url=VLLM_RERANK_URL, timeout=30.0)
        logger.info("Reranker client: %s -> %s", RERANKER_MODEL, VLLM_RERANK_URL)
    return _client


def rerank(query: str, candidates: list[dict]) -> list[dict]:
    """Rerank candidates by cross-encoder relevance score.

    Qwen3-Reranker returns 0-1 probability scores via vLLM /v1/score.

    Args:
        query: The search query.
        candidates: List of dicts, each must have 'text' key with content.
            Other keys (id, score, metadata) are preserved.

    Returns:
        Candidates reordered by rerank_score (descending), with
        'rerank_score' field added to each dict (0.0 to 1.0).
    """
    if not candidates:
        return candidates

    texts = [c.get("text", "") for c in candidates]
    response = _get_client().post("/v1/score", json={
        "model": RERANKER_MODEL,
        "text_1": query,
        "text_2": texts,
    })
    response.raise_for_status()
    scores = {item["index"]: item["score"] for item in response.json()["data"]}

    for i, candidate in enumerate(candidates):
        candidate["rerank_score"] = scores.get(i, 0.0)

    return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
