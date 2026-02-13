"""Embedding service using NVIDIA Llama-Nemotron-Embed-1B-v2.

Provides document embedding and query embedding with asymmetric encoding.
Model is loaded lazily on first use and cached for the process lifetime.
"""

from sentence_transformers import SentenceTransformer

_model = None


def _get_model() -> SentenceTransformer:
    """Lazy-load the embedding model (first call downloads ~2GB)."""
    global _model
    if _model is None:
        _model = SentenceTransformer(
            "nvidia/llama-nemotron-embed-1b-v2",
            trust_remote_code=True,
        )
    return _model


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed document passages for storage.

    Args:
        texts: List of text passages to embed.

    Returns:
        List of embedding vectors (2048-dim each).
    """
    model = _get_model()
    embeddings = model.encode(texts, prompt_name="document")
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a search query for retrieval.

    Args:
        query: The search query text.

    Returns:
        Single embedding vector (2048-dim).
    """
    model = _get_model()
    embedding = model.encode([query], prompt_name="query")
    return embedding[0].tolist()
