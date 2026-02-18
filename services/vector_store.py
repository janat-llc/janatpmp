"""Qdrant vector store operations for JANATPMP RAG pipeline.

Collections:
- janatpmp_documents: Embedded document chunks
- janatpmp_messages: Embedded conversation messages
"""

import logging
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
)
from services.embedding import embed_passages, embed_query

logger = logging.getLogger(__name__)

QDRANT_URL = "http://janatpmp-qdrant:6333"  # Docker DNS (service name in docker-compose)
VECTOR_DIM = 2048
COLLECTION_DOCUMENTS = "janatpmp_documents"
COLLECTION_MESSAGES = "janatpmp_messages"

_client = None


def _get_client() -> QdrantClient:
    """Lazy-load Qdrant client."""
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=30)
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


def search(query: str, collection: str = COLLECTION_DOCUMENTS, limit: int = 5) -> list[dict]:
    """Semantic search across a collection.

    Args:
        query: Natural language search query.
        collection: Which collection to search.
        limit: Max results to return.

    Returns:
        List of dicts with keys: id, score, text, and all metadata fields.
    """
    client = _get_client()
    query_vector = embed_query(query)

    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "id": str(hit.id),
            "score": hit.score,
            **hit.payload,
        }
        for hit in results.points
    ]


def search_all(query: str, limit: int = 5) -> list[dict]:
    """Search across ALL collections, merged and sorted by score.

    Args:
        query: Natural language search query.
        limit: Max results per collection (total may be up to 2x limit).

    Returns:
        List of dicts with source_collection field added, sorted by score desc.
    """
    docs = search(query, COLLECTION_DOCUMENTS, limit)
    for d in docs:
        d["source_collection"] = "documents"

    msgs = search(query, COLLECTION_MESSAGES, limit)
    for m in msgs:
        m["source_collection"] = "messages"

    combined = docs + msgs
    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined[:limit]
