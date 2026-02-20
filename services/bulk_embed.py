"""Bulk embed existing JANATPMP data into Qdrant.

Run once to backfill, then incremental embedding happens via CDC or on-create.
GPU-accelerated with batch processing, progress logging, and checkpoint support.
"""

import logging
import time
import torch
from qdrant_client.models import PointStruct
from db.operations import get_connection
from services.embedding import embed_passages
from services.vector_store import (
    ensure_collections, point_exists, upsert_batch,
    COLLECTION_DOCUMENTS, COLLECTION_MESSAGES,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 4
# Conservative limit: the VL model's attention is O(n²) in sequence length.
# 8000 chars ≈ 2000 tokens — well within the 8192 token max with safety margin.
MAX_TEXT_CHARS = 8_000


def embed_all_documents() -> dict:
    """Embed all documents with content into the Qdrant documents collection.

    Queries all documents with non-trivial content (>10 chars), embeds in
    GPU-accelerated batches, and upserts into janatpmp_documents. Supports
    checkpoint resume — skips documents already in Qdrant.

    Returns:
        Dict with keys: embedded (int), skipped (int), errors (list[str]),
        elapsed_seconds (float).
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []
    start_time = time.time()

    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT id, title, doc_type, source, content, created_at
            FROM documents
            WHERE content IS NOT NULL AND length(content) > 10
        """)
        rows = cursor.fetchall()

    total = len(rows)
    logger.info("Bulk embed documents: %d candidates", total)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        texts = []
        valid_rows = []

        for row in batch:
            if point_exists(COLLECTION_DOCUMENTS, row["id"]):
                skipped += 1
                continue
            content = row["content"]
            if len(content) > MAX_TEXT_CHARS:
                content = content[:MAX_TEXT_CHARS]
            texts.append(content)
            valid_rows.append(row)

        if not texts:
            continue

        try:
            vectors = embed_passages(texts)
            points = [
                PointStruct(
                    id=row["id"],
                    vector=vec,
                    payload={
                        "text": row["content"],
                        "title": row["title"] or "",
                        "doc_type": row["doc_type"] or "",
                        "source": row["source"] or "",
                        "created_at": row["created_at"] or "",
                    },
                )
                for row, vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_DOCUMENTS, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed failed at offset %d: %s", batch_start, e)
            errors.append(f"batch@{batch_start}: {str(e)}")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        processed = embedded + skipped + len(errors)
        if processed > 0 and processed % 100 < BATCH_SIZE:
            elapsed = time.time() - start_time
            logger.info("Documents: %d/%d (%.1fs elapsed)", processed, total, elapsed)

    elapsed = time.time() - start_time
    logger.info("Bulk embed documents: %d embedded, %d skipped, %d errors (%.1fs)",
                embedded, skipped, len(errors), elapsed)
    return {"embedded": embedded, "skipped": skipped, "errors": errors,
            "elapsed_seconds": round(elapsed, 1)}


def embed_all_messages() -> dict:
    """Embed all conversation messages into the Qdrant messages collection.

    Combines user_prompt + model_response as 'Q: ... A: ...' text,
    skips messages with less than 20 chars of content. GPU-accelerated
    with batch processing and checkpoint resume.

    Returns:
        Dict with keys: embedded (int), skipped (int), errors (list[str]),
        elapsed_seconds (float).
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []
    start_time = time.time()

    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT m.id, m.conversation_id, m.sequence,
                   m.user_prompt, m.model_response,
                   c.title as conv_title
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.user_prompt != '' OR m.model_response != ''
        """)
        rows = cursor.fetchall()

    total = len(rows)
    logger.info("Bulk embed messages: %d candidates", total)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        texts = []
        valid_rows = []

        for row in batch:
            text = f"Q: {row['user_prompt']}\nA: {row['model_response']}"
            if len(text.strip()) < 20:
                skipped += 1
                continue
            if point_exists(COLLECTION_MESSAGES, row["id"]):
                skipped += 1
                continue
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS]
            texts.append(text)
            valid_rows.append((row, text))

        if not texts:
            continue

        try:
            vectors = embed_passages(texts)
            points = [
                PointStruct(
                    id=row["id"],
                    vector=vec,
                    payload={
                        "text": text,
                        "conversation_id": row["conversation_id"],
                        "conv_title": row["conv_title"] or "",
                        "sequence": row["sequence"],
                    },
                )
                for (row, text), vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_MESSAGES, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed failed at offset %d: %s", batch_start, e)
            errors.append(f"batch@{batch_start}: {str(e)}")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        processed = embedded + skipped + len(errors)
        if processed > 0 and processed % 100 < BATCH_SIZE:
            elapsed = time.time() - start_time
            logger.info("Messages: %d/%d (%.1fs elapsed)", processed, total, elapsed)

    elapsed = time.time() - start_time
    logger.info("Bulk embed messages: %d embedded, %d skipped, %d errors (%.1fs)",
                embedded, skipped, len(errors), elapsed)
    return {"embedded": embedded, "skipped": skipped, "errors": errors,
            "elapsed_seconds": round(elapsed, 1)}


def embed_all_domains() -> dict:
    """Embed all domain descriptions into the Qdrant documents collection.

    Queries all domains with non-empty descriptions, embeds each description,
    and upserts into janatpmp_documents with entity_type='domain' metadata.

    Returns:
        Dict with keys: embedded (int), skipped (int), errors (list[str]),
        elapsed_seconds (float).
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []
    start_time = time.time()

    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT id, name, display_name, description
            FROM domains
            WHERE description IS NOT NULL AND length(description) > 10
        """)
        rows = cursor.fetchall()

    total = len(rows)
    logger.info("Bulk embed domains: %d candidates", total)

    texts = []
    valid_rows = []
    for row in rows:
        if point_exists(COLLECTION_DOCUMENTS, row["id"]):
            skipped += 1
            continue
        texts.append(row["description"])
        valid_rows.append(row)

    if texts:
        try:
            vectors = embed_passages(texts)
            points = [
                PointStruct(
                    id=row["id"],
                    vector=vec,
                    payload={
                        "text": row["description"],
                        "entity_type": "domain",
                        "name": row["name"] or "",
                        "display_name": row["display_name"] or "",
                        "title": row["display_name"] or row["name"],
                    },
                )
                for row, vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_DOCUMENTS, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed domains failed: %s", e)
            errors.append(f"domains: {str(e)}")

    elapsed = time.time() - start_time
    logger.info("Bulk embed domains: %d embedded, %d skipped, %d errors (%.1fs)",
                embedded, skipped, len(errors), elapsed)
    return {"embedded": embedded, "skipped": skipped, "errors": errors,
            "elapsed_seconds": round(elapsed, 1)}
