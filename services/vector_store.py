"""Qdrant vector store operations for JANATPMP RAG pipeline.

Collections:
- janatpmp_documents: Embedded document chunks
- janatpmp_messages: Embedded conversation messages

Search uses a two-stage pipeline (R9):
1. ANN search (embedder) → top-k candidates
2. Cross-encoder reranker → reordered results + salience write-back
"""

import os
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
)
from services.embedding import embed_passages, embed_query
from atlas.config import RERANK_CANDIDATES

logger = logging.getLogger(__name__)

VECTOR_DIM = 2048
COLLECTION_DOCUMENTS = "janatpmp_documents"
COLLECTION_MESSAGES = "janatpmp_messages"

_client = None


def _get_qdrant_url() -> str:
    """Resolve Qdrant URL: env var > settings > default."""
    env_url = os.environ.get("QDRANT_URL")
    if env_url:
        return env_url
    try:
        from services.settings import get_setting
        return get_setting("qdrant_url") or "http://janatpmp-qdrant:6333"
    except Exception:
        return "http://janatpmp-qdrant:6333"


def _get_client() -> QdrantClient:
    """Lazy-load Qdrant client."""
    global _client
    if _client is None:
        url = _get_qdrant_url()
        logger.info("Connecting to Qdrant at %s", url)
        _client = QdrantClient(url=url, timeout=30)
    return _client


def ensure_collections():
    """Create collections if they don't exist. Safe to call multiple times."""
    client = _get_client()
    existing = [c.name for c in client.get_collections().collections]

    for name in [COLLECTION_DOCUMENTS, COLLECTION_MESSAGES]:
        if name not in existing:
            logger.info("Creating Qdrant collection: %s", name)
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=VECTOR_DIM,
                    distance=Distance.COSINE,
                ),
            )


def recreate_collections() -> str:
    """Drop and recreate all Qdrant collections at correct dimensions.

    WARNING: This destroys all existing embeddings. Use when switching
    embedding models (different vector space) or resetting the vector store.
    Re-run embed_all_documents(), embed_all_messages(), embed_all_domains()
    after calling this.

    Returns:
        Status message confirming recreation.
    """
    client = _get_client()
    existing = [c.name for c in client.get_collections().collections]
    recreated = []

    for name in [COLLECTION_DOCUMENTS, COLLECTION_MESSAGES]:
        if name in existing:
            client.delete_collection(name)
            logger.info("Deleted Qdrant collection: %s", name)
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=VECTOR_DIM,
                distance=Distance.COSINE,
            ),
        )
        recreated.append(name)
        logger.info("Created Qdrant collection: %s (%d-dim, cosine)", name, VECTOR_DIM)

    return f"Recreated collections: {', '.join(recreated)} at {VECTOR_DIM} dimensions"


def upsert_document(doc_id: str, text: str, metadata: dict):
    """Embed and store a document chunk.

    Args:
        doc_id: Unique document ID (from JANATPMP documents table).
        text: The text content to embed.
        metadata: Dict with keys like doc_type, title, source, created_at.
    """
    client = _get_client()
    vectors = embed_passages([text])

    client.upsert(
        collection_name=COLLECTION_DOCUMENTS,
        points=[PointStruct(
            id=doc_id,
            vector=vectors[0],
            payload={"text": text, **metadata},
        )],
    )


def upsert_message(message_id: str, text: str, metadata: dict):
    """Embed and store a conversation message.

    Args:
        message_id: Unique message identifier.
        text: Combined user_prompt + model_response text.
        metadata: Dict with conversation_id, sequence, etc.
    """
    client = _get_client()
    vectors = embed_passages([text])

    client.upsert(
        collection_name=COLLECTION_MESSAGES,
        points=[PointStruct(
            id=message_id,
            vector=vectors[0],
            payload={"text": text, **metadata},
        )],
    )


def upsert_batch(collection: str, points: list[PointStruct]):
    """Upsert a batch of pre-embedded points into a collection.

    Args:
        collection: Target Qdrant collection name.
        points: List of PointStruct with id, vector, and payload.
    """
    client = _get_client()
    client.upsert(collection_name=collection, points=points)


def point_exists(collection: str, point_id: str) -> bool:
    """Check if a point exists in a Qdrant collection.

    Args:
        collection: Qdrant collection name.
        point_id: The point ID to check.

    Returns:
        True if the point exists, False otherwise.
    """
    client = _get_client()
    try:
        result = client.retrieve(collection, [point_id])
        return len(result) > 0
    except Exception:
        return False


def search(query: str, collection: str = COLLECTION_DOCUMENTS,
           limit: int = 5, rerank: bool = True) -> list[dict]:
    """Semantic search across a collection with optional reranking.

    Two-stage pipeline: ANN search produces candidates, then cross-encoder
    reranker reorders them and writes salience back to Qdrant.

    Args:
        query: Natural language search query.
        collection: Which collection to search.
        limit: Max results to return.
        rerank: If True, apply cross-encoder reranking (default). Set False
            for bulk operations or when reranker is not needed.

    Returns:
        List of dicts with keys: id, score, text, and all metadata fields.
        When reranked, also includes rerank_score.
    """
    client = _get_client()
    query_vector = embed_query(query)

    # Wider ANN net when reranking (retrieve more candidates for reranker to score)
    ann_limit = RERANK_CANDIDATES if rerank else limit

    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=ann_limit,
        with_payload=True,
    )

    candidates = [
        {
            "id": str(hit.id),
            "score": hit.score,
            **hit.payload,
        }
        for hit in results.points
    ]

    if rerank and candidates:
        try:
            from atlas.pipeline import rerank_and_write_salience
            candidates = rerank_and_write_salience(query, candidates, collection, limit)
        except Exception as e:
            logger.warning("Reranker unavailable, returning ANN results: %s", e)
            candidates = candidates[:limit]
    else:
        candidates = candidates[:limit]

    return candidates


def search_all(query: str, limit: int = 5, rerank: bool = True) -> list[dict]:
    """Search across ALL collections, merged and sorted by relevance.

    Two-stage pipeline applied per-collection, then merged. When reranking,
    results are sorted by rerank_score; otherwise by ANN score.

    Args:
        query: Natural language search query.
        limit: Max results per collection (total may be up to 2x limit).
        rerank: If True, apply cross-encoder reranking (default).

    Returns:
        List of dicts with source_collection field added, sorted by score desc.
    """
    docs = search(query, COLLECTION_DOCUMENTS, limit, rerank=rerank)
    for d in docs:
        d["source_collection"] = "documents"

    msgs = search(query, COLLECTION_MESSAGES, limit, rerank=rerank)
    for m in msgs:
        m["source_collection"] = "messages"

    combined = docs + msgs
    sort_key = "rerank_score" if rerank else "score"
    combined.sort(key=lambda x: x.get(sort_key, 0), reverse=True)
    return combined[:limit]
