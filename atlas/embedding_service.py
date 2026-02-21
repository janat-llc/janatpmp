"""ATLAS embedding service — Qwen3-Embedding-4B via Ollama.

HTTP client to Ollama's OpenAI-compatible /v1/embeddings endpoint.
No GPU, no model loading, no VRAM management in the core container.
"""

import logging

from openai import OpenAI

from atlas.config import OLLAMA_EMBED_URL, EMBEDDING_MODEL, EMBEDDING_DIM, QUERY_INSTRUCTION

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    """Lazy-init OpenAI client pointing at Ollama embed endpoint."""
    global _client
    if _client is None:
        _client = OpenAI(api_key="ollama", base_url=f"{OLLAMA_EMBED_URL}/v1")
        logger.info("Embedding client: %s -> %s", EMBEDDING_MODEL, OLLAMA_EMBED_URL)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed document passages for storage (asymmetric document encoding).

    No instruction prefix — documents are encoded as-is per Qwen3 protocol.

    Args:
        texts: List of text passages to embed.

    Returns:
        List of embedding vectors (EMBEDDING_DIM each).
    """
    response = _get_client().embeddings.create(
        model=EMBEDDING_MODEL, input=texts,
    )
    # Truncate to EMBEDDING_DIM if model returns higher-dim (Matryoshka safety)
    return [item.embedding[:EMBEDDING_DIM] for item in response.data]


def embed_query(query: str) -> list[float]:
    """Embed a search query for retrieval (asymmetric query encoding).

    Prepends Qwen3's instruction prefix for query-document asymmetry.

    Args:
        query: The search query text.

    Returns:
        Single embedding vector (EMBEDDING_DIM).
    """
    response = _get_client().embeddings.create(
        model=EMBEDDING_MODEL, input=[QUERY_INSTRUCTION + query],
    )
    return response.data[0].embedding[:EMBEDDING_DIM]
