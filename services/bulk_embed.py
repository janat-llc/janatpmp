"""Bulk embed existing JANATPMP data into Qdrant.

Run once to backfill, then incremental embedding happens via CDC or on-create.
Embedding is done via Ollama HTTP API — no in-process GPU needed.
"""

import logging
import time
from qdrant_client.models import PointStruct
from db.operations import get_connection
from services.embedding import embed_passages
from services.vector_store import (
    ensure_collections, point_exists, existing_point_ids, upsert_batch,
    COLLECTION_DOCUMENTS, COLLECTION_MESSAGES,
)

logger = logging.getLogger(__name__)

from atlas.config import MAX_TEXT_CHARS

BATCH_SIZE = 32
# Ollama handles batching server-side. HTTP overhead is the bottleneck,
# so larger client-side batches reduce round-trips.


def embed_all_documents() -> dict:
    """Embed all documents with content into the Qdrant documents collection.

    Queries all documents with non-trivial content (>10 chars), embeds in
    batches via Ollama, and upserts into janatpmp_documents. Supports
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
        batch_ids = [row["id"] for row in batch]
        already_embedded = existing_point_ids(COLLECTION_DOCUMENTS, batch_ids)
        texts = []
        valid_rows = []

        for row in batch:
            if row["id"] in already_embedded:
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
    skips messages with less than 20 chars of content. Batch processing
    via Ollama with checkpoint resume.

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
                   m.created_at, m.provider, m.model,
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
        batch_ids = [row["id"] for row in batch]
        already_embedded = existing_point_ids(COLLECTION_MESSAGES, batch_ids)
        texts = []
        valid_rows = []

        for row in batch:
            text = f"Q: {row['user_prompt']}\nA: {row['model_response']}"
            if len(text.strip()) < 20:
                skipped += 1
                continue
            if row["id"] in already_embedded:
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
                        "created_at": row["created_at"] or "",
                        "provider": row["provider"] or "",
                        "model": row["model"] or "",
                        "salience": 0.5,
                        "entity_type": "message",
                    },
                )
                for (row, text), vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_MESSAGES, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed failed at offset %d: %s", batch_start, e)
            errors.append(f"batch@{batch_start}: {str(e)}")

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

    all_ids = [row["id"] for row in rows]
    already_embedded = existing_point_ids(COLLECTION_DOCUMENTS, all_ids)
    texts = []
    valid_rows = []
    for row in rows:
        if row["id"] in already_embedded:
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


def embed_all_items() -> dict:
    """Embed all items (projects, features, etc.) into the Qdrant documents collection.

    Combines entity_type, title, and description as embeddable text. Items are
    stored in janatpmp_documents with entity_type='item' metadata, making them
    discoverable via RAG search alongside documents, messages, and domains.

    Supports checkpoint resume — skips items already in Qdrant.

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
            SELECT id, entity_type, domain, title, description, status, priority
            FROM items
            WHERE title IS NOT NULL AND length(title) > 0
        """)
        rows = cursor.fetchall()

    total = len(rows)
    logger.info("Bulk embed items: %d candidates", total)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        batch_ids = [row["id"] for row in batch]
        already_embedded = existing_point_ids(COLLECTION_DOCUMENTS, batch_ids)
        texts = []
        valid_rows = []

        for row in batch:
            if row["id"] in already_embedded:
                skipped += 1
                continue
            text = f"{row['entity_type']}: {row['title']}"
            desc = row["description"]
            if desc:
                text += f"\n{desc}"
            if len(text) < 10:
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
                        "entity_type": "item",
                        "item_type": row["entity_type"] or "",
                        "title": row["title"] or "",
                        "domain": row["domain"] or "",
                        "status": row["status"] or "",
                        "priority": row["priority"],
                    },
                )
                for (row, text), vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_DOCUMENTS, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed items failed at offset %d: %s", batch_start, e)
            errors.append(f"batch@{batch_start}: {str(e)}")

        processed = embedded + skipped + len(errors)
        if processed > 0 and processed % 100 < BATCH_SIZE:
            elapsed = time.time() - start_time
            logger.info("Items: %d/%d (%.1fs elapsed)", processed, total, elapsed)

    elapsed = time.time() - start_time
    logger.info("Bulk embed items: %d embedded, %d skipped, %d errors (%.1fs)",
                embedded, skipped, len(errors), elapsed)
    return {"embedded": embedded, "skipped": skipped, "errors": errors,
            "elapsed_seconds": round(elapsed, 1)}


def embed_all_tasks() -> dict:
    """Embed all tasks into the Qdrant documents collection.

    Combines title, description, and agent instructions as embeddable text.
    Tasks are stored in janatpmp_documents with entity_type='task' metadata,
    making them discoverable via RAG search.

    Supports checkpoint resume — skips tasks already in Qdrant.

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
            SELECT id, task_type, title, description, assigned_to, status,
                   agent_instructions
            FROM tasks
            WHERE title IS NOT NULL AND length(title) > 0
        """)
        rows = cursor.fetchall()

    total = len(rows)
    logger.info("Bulk embed tasks: %d candidates", total)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        batch_ids = [row["id"] for row in batch]
        already_embedded = existing_point_ids(COLLECTION_DOCUMENTS, batch_ids)
        texts = []
        valid_rows = []

        for row in batch:
            if row["id"] in already_embedded:
                skipped += 1
                continue
            text = f"Task: {row['title']}"
            desc = row["description"]
            if desc:
                text += f"\n{desc}"
            instructions = row["agent_instructions"]
            if instructions:
                text += f"\n{instructions}"
            if len(text) < 10:
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
                        "entity_type": "task",
                        "task_type": row["task_type"] or "",
                        "title": row["title"] or "",
                        "assigned_to": row["assigned_to"] or "",
                        "status": row["status"] or "",
                    },
                )
                for (row, text), vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_DOCUMENTS, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed tasks failed at offset %d: %s", batch_start, e)
            errors.append(f"batch@{batch_start}: {str(e)}")

        processed = embedded + skipped + len(errors)
        if processed > 0 and processed % 100 < BATCH_SIZE:
            elapsed = time.time() - start_time
            logger.info("Tasks: %d/%d (%.1fs elapsed)", processed, total, elapsed)

    elapsed = time.time() - start_time
    logger.info("Bulk embed tasks: %d embedded, %d skipped, %d errors (%.1fs)",
                embedded, skipped, len(errors), elapsed)
    return {"embedded": embedded, "skipped": skipped, "errors": errors,
            "elapsed_seconds": round(elapsed, 1)}
