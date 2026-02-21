"""Embedding service — delegates to atlas.embedding_service.

Thin shim preserving the embed_passages() / embed_query() interface that
services/vector_store.py and services/bulk_embed.py already import.
The atlas module owns the HTTP client; this module provides the stable interface.
"""

import logging

from atlas.embedding_service import embed_texts, embed_query as _embed_query

logger = logging.getLogger(__name__)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed document passages for storage.

    Args:
        texts: List of text passages to embed.

    Returns:
        List of embedding vectors (1024-dim each).
    """
    return embed_texts(texts)


def embed_query(query: str) -> list[float]:
    """Embed a search query for retrieval.

    Args:
        query: The search query text.

    Returns:
        Single embedding vector (1024-dim).
    """
    return _embed_query(query)
