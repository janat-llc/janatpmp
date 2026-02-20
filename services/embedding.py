"""Embedding service — delegates to atlas.embedding_service.

Thin shim preserving the embed_passages() / embed_query() interface that
services/vector_store.py and services/bulk_embed.py already import.
The atlas module owns the model; this module provides the stable interface.
"""

import logging

from atlas.embedding_service import get_embedder, release_embedder

logger = logging.getLogger(__name__)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed document passages for storage.

    Args:
        texts: List of text passages to embed.

    Returns:
        List of embedding vectors (2048-dim each).
    """
    return get_embedder().embed_texts(texts)


def embed_query(query: str) -> list[float]:
    """Embed a search query for retrieval.

    Args:
        query: The search query text.

    Returns:
        Single embedding vector (2048-dim).
    """
    return get_embedder().embed_query(query)
