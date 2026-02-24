"""Bulk embed existing JANATPMP data into Qdrant.

Run once to backfill, then incremental embedding happens via on_write or CDC.
Embedding is done via Ollama HTTP API — no in-process GPU needed.

R16: Messages and documents are now chunked before embedding. Run chunk_all_*
first to populate the chunks table, then embed_all_* reads from chunks.
Items, tasks, and domains remain single-vector (short texts, no chunking needed).
"""

import logging
import time
from qdrant_client.models import PointStruct
from db.operations import get_connection
from services.embedding import embed_passages
from services.vector_store import (
    ensure_collections, existing_point_ids, upsert_batch,
    COLLECTION_DOCUMENTS, COLLECTION_MESSAGES,
)

logger = logging.getLogger(__name__)

from atlas.config import MAX_TEXT_CHARS, SALIENCE_DEFAULT

BATCH_SIZE = 32
# Ollama handles batching server-side. HTTP overhead is the bottleneck,
# so larger client-side batches reduce round-trips.


def _generate_point_id(entity_id: str, chunk_index: int, chunk_total: int) -> str:
    """Generate Qdrant point ID for a chunk.

    Single-chunk entities use the raw entity_id (backward compatible).
    Multi-chunk entities use {entity_id}_c{index:03d}.
    """
    if chunk_total <= 1:
        return entity_id
    return f"{entity_id}_c{chunk_index:03d}"


# ---------------------------------------------------------------------------
# Chunking operations — populate chunks table (run before embed_all_*)
# ---------------------------------------------------------------------------


def chunk_all_messages() -> dict:
    """Populate the chunks table for all messages that haven't been chunked yet.

    Reads messages from the database, runs the chunking engine on each,
    and inserts chunk records into the chunks table. Checkpoint: skips
    messages that already have chunks. Run this before embed_all_messages()
    to enable chunk-level embedding.

    Returns:
        Dict with keys: chunked (int), chunks_created (int), skipped (int),
        errors (int), elapsed_seconds (float).
    """
    from atlas.chunking import chunk_message
    from services.settings import get_setting

    max_chars = int(get_setting("chunk_max_chars") or 2500)
    threshold = int(get_setting("chunk_threshold") or 3000)

    chunked = 0
    chunks_created = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT m.id, m.user_prompt, m.model_response
            FROM messages m
            WHERE (m.user_prompt != '' OR m.model_response != '')
            AND NOT EXISTS (
                SELECT 1 FROM chunks c
                WHERE c.entity_type = 'message' AND c.entity_id = m.id
            )
        """).fetchall()

    total = len(rows)
    logger.info("Chunk all messages: %d candidates", total)

    for row in rows:
        text = f"Q: {row['user_prompt']}\nA: {row['model_response']}"
        if len(text) < 20:
            skipped += 1
            continue

        try:
            chunks = chunk_message(
                row["user_prompt"], row["model_response"],
                max_chars=max_chars, threshold=threshold,
            )
            if not chunks:
                skipped += 1
                continue

            chunk_total = len(chunks)
            with get_connection() as conn:
                for chunk in chunks:
                    point_id = _generate_point_id(
                        row["id"], chunk["index"], chunk_total,
                    )
                    conn.execute(
                        """INSERT OR IGNORE INTO chunks
                           (entity_type, entity_id, chunk_index, chunk_text,
                            char_start, char_end, position, point_id)
                           VALUES ('message', ?, ?, ?, ?, ?, ?, ?)""",
                        (row["id"], chunk["index"], chunk["text"],
                         chunk["char_start"], chunk["char_end"],
                         chunk["position"], point_id),
                    )
                conn.commit()

            chunked += 1
            chunks_created += chunk_total
        except Exception as e:
            logger.warning("Chunk failed for message %s: %s",
                           row["id"][:12], e)
            errors += 1

        processed = chunked + skipped + errors
        if processed > 0 and processed % 500 == 0:
            elapsed = time.time() - start_time
            logger.info("Chunking messages: %d/%d (%.1fs)",
                        processed, total, elapsed)

    elapsed = time.time() - start_time
    logger.info(
        "Chunk all messages: %d chunked (%d chunks), %d skipped, "
        "%d errors (%.1fs)",
        chunked, chunks_created, skipped, errors, elapsed,
    )
    return {
        "chunked": chunked,
        "chunks_created": chunks_created,
        "skipped": skipped,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
    }


def chunk_all_documents() -> dict:
    """Populate the chunks table for all documents that haven't been chunked yet.

    Reads documents from the database, runs the chunking engine on each,
    and inserts chunk records into the chunks table. Checkpoint: skips
    documents that already have chunks. Run this before embed_all_documents()
    to enable chunk-level embedding.

    Returns:
        Dict with keys: chunked (int), chunks_created (int), skipped (int),
        errors (int), elapsed_seconds (float).
    """
    from atlas.chunking import chunk_document
    from services.settings import get_setting

    max_chars = int(get_setting("chunk_max_chars") or 2500)
    threshold = int(get_setting("chunk_threshold") or 3000)

    chunked = 0
    chunks_created = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT d.id, d.title, d.content
            FROM documents d
            WHERE d.content IS NOT NULL AND length(d.content) > 10
            AND NOT EXISTS (
                SELECT 1 FROM chunks c
                WHERE c.entity_type = 'document' AND c.entity_id = d.id
            )
        """).fetchall()

    total = len(rows)
    logger.info("Chunk all documents: %d candidates", total)

    for row in rows:
        try:
            chunks = chunk_document(
                row["content"], title=row["title"] or "",
                max_chars=max_chars, threshold=threshold,
            )
            if not chunks:
                skipped += 1
                continue

            chunk_total = len(chunks)
            with get_connection() as conn:
                for chunk in chunks:
                    point_id = _generate_point_id(
                        row["id"], chunk["index"], chunk_total,
                    )
                    conn.execute(
                        """INSERT OR IGNORE INTO chunks
                           (entity_type, entity_id, chunk_index, chunk_text,
                            char_start, char_end, position, point_id)
                           VALUES ('document', ?, ?, ?, ?, ?, ?, ?)""",
                        (row["id"], chunk["index"], chunk["text"],
                         chunk["char_start"], chunk["char_end"],
                         chunk["position"], point_id),
                    )
                conn.commit()

            chunked += 1
            chunks_created += chunk_total
        except Exception as e:
            logger.warning("Chunk failed for document %s: %s",
                           row["id"][:12], e)
            errors += 1

        processed = chunked + skipped + errors
        if processed > 0 and processed % 100 == 0:
            elapsed = time.time() - start_time
            logger.info("Chunking documents: %d/%d (%.1fs)",
                        processed, total, elapsed)

    elapsed = time.time() - start_time
    logger.info(
        "Chunk all documents: %d chunked (%d chunks), %d skipped, "
        "%d errors (%.1fs)",
        chunked, chunks_created, skipped, errors, elapsed,
    )
    return {
        "chunked": chunked,
        "chunks_created": chunks_created,
        "skipped": skipped,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
    }


# ---------------------------------------------------------------------------
# Embedding operations — embed from chunks table (R16)
# ---------------------------------------------------------------------------


def embed_all_documents() -> dict:
    """Embed all document chunks into the Qdrant documents collection.

    R16: Reads from the chunks table (populated by chunk_all_documents or
    ingestion pipelines). Checkpoint: only embeds chunks where embedded_at
    IS NULL. Falls back to legacy per-document embedding for documents
    that haven't been chunked yet.

    Returns:
        Dict with keys: embedded (int), skipped (int), errors (list[str]),
        elapsed_seconds (float).
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []
    start_time = time.time()

    # --- Phase 1: Embed from chunks table (R16) ---
    with get_connection() as conn:
        chunk_rows = conn.execute("""
            SELECT c.id as chunk_id, c.entity_id as doc_id, c.chunk_index,
                   c.chunk_text, c.point_id, c.position,
                   COUNT(*) OVER (PARTITION BY c.entity_id) as chunk_total,
                   d.title, d.doc_type, d.source, d.created_at
            FROM chunks c
            JOIN documents d ON c.entity_id = d.id
            WHERE c.entity_type = 'document' AND c.embedded_at IS NULL
            ORDER BY c.entity_id, c.chunk_index
        """).fetchall()

    chunk_count = len(chunk_rows)
    if chunk_count:
        logger.info("Bulk embed document chunks: %d candidates", chunk_count)

    for batch_start in range(0, chunk_count, BATCH_SIZE):
        batch = chunk_rows[batch_start:batch_start + BATCH_SIZE]
        texts = [row["chunk_text"] for row in batch]

        try:
            vectors = embed_passages(texts)
            points = []
            for row, vec in zip(batch, vectors):
                payload = {
                    "text": row["chunk_text"],
                    "parent_document_id": row["doc_id"],
                    "chunk_index": row["chunk_index"],
                    "chunk_total": row["chunk_total"],
                    "chunk_position": row["position"],
                    "title": row["title"] or "",
                    "doc_type": row["doc_type"] or "",
                    "source": row["source"] or "",
                    "created_at": row["created_at"] or "",
                    "salience": SALIENCE_DEFAULT,
                    "entity_type": "document",
                }
                points.append(PointStruct(
                    id=row["point_id"], vector=vec, payload=payload,
                ))
            upsert_batch(COLLECTION_DOCUMENTS, points)

            # Mark chunks as embedded
            with get_connection() as conn:
                chunk_ids = [row["chunk_id"] for row in batch]
                placeholders = ",".join("?" * len(chunk_ids))
                conn.execute(
                    f"UPDATE chunks SET embedded_at = datetime('now') "
                    f"WHERE id IN ({placeholders})",
                    chunk_ids,
                )
                conn.commit()

            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed doc chunks failed at offset %d: %s",
                         batch_start, e)
            errors.append(f"chunk_batch@{batch_start}: {str(e)}")

        if embedded > 0 and embedded % 100 < BATCH_SIZE:
            elapsed = time.time() - start_time
            logger.info("Document chunks: %d/%d (%.1fs elapsed)",
                        embedded, chunk_count, elapsed)

    # --- Phase 2: Legacy fallback for unchunked documents ---
    with get_connection() as conn:
        legacy_rows = conn.execute("""
            SELECT d.id, d.title, d.doc_type, d.source, d.content, d.created_at
            FROM documents d
            WHERE d.content IS NOT NULL AND length(d.content) > 10
            AND NOT EXISTS (
                SELECT 1 FROM chunks c
                WHERE c.entity_type = 'document' AND c.entity_id = d.id
            )
        """).fetchall()

    legacy_total = len(legacy_rows)
    if legacy_total:
        logger.info("Legacy embed documents (no chunks): %d candidates",
                     legacy_total)

    for batch_start in range(0, legacy_total, BATCH_SIZE):
        batch = legacy_rows[batch_start:batch_start + BATCH_SIZE]
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
                        "entity_type": "document",
                    },
                )
                for row, vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_DOCUMENTS, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Legacy batch embed docs failed at offset %d: %s",
                         batch_start, e)
            errors.append(f"legacy_batch@{batch_start}: {str(e)}")

    elapsed = time.time() - start_time
    logger.info("Bulk embed documents: %d embedded, %d skipped, %d errors (%.1fs)",
                embedded, skipped, len(errors), elapsed)
    return {"embedded": embedded, "skipped": skipped, "errors": errors,
            "elapsed_seconds": round(elapsed, 1)}


def embed_all_messages() -> dict:
    """Embed all message chunks into the Qdrant messages collection.

    R16: Reads from the chunks table (populated by chunk_all_messages or
    the on-write pipeline). Checkpoint: only embeds chunks where embedded_at
    IS NULL. Falls back to legacy per-message embedding for messages that
    haven't been chunked yet.

    Returns:
        Dict with keys: embedded (int), skipped (int), errors (list[str]),
        elapsed_seconds (float).
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []
    start_time = time.time()

    # --- Phase 1: Embed from chunks table (R16) ---
    with get_connection() as conn:
        chunk_rows = conn.execute("""
            SELECT c.id as chunk_id, c.entity_id as message_id, c.chunk_index,
                   c.chunk_text, c.point_id, c.position,
                   COUNT(*) OVER (PARTITION BY c.entity_id) as chunk_total,
                   m.conversation_id, m.sequence, m.created_at,
                   m.provider, m.model,
                   conv.title as conv_title
            FROM chunks c
            JOIN messages m ON c.entity_id = m.id
            LEFT JOIN conversations conv ON m.conversation_id = conv.id
            WHERE c.entity_type = 'message' AND c.embedded_at IS NULL
            ORDER BY c.entity_id, c.chunk_index
        """).fetchall()

    chunk_count = len(chunk_rows)
    if chunk_count:
        logger.info("Bulk embed message chunks: %d candidates", chunk_count)

    for batch_start in range(0, chunk_count, BATCH_SIZE):
        batch = chunk_rows[batch_start:batch_start + BATCH_SIZE]
        texts = [row["chunk_text"] for row in batch]

        try:
            vectors = embed_passages(texts)
            points = []
            for row, vec in zip(batch, vectors):
                payload = {
                    "text": row["chunk_text"],
                    "parent_message_id": row["message_id"],
                    "chunk_index": row["chunk_index"],
                    "chunk_total": row["chunk_total"],
                    "chunk_position": row["position"],
                    "conversation_id": row["conversation_id"],
                    "conv_title": row["conv_title"] or "",
                    "sequence": row["sequence"],
                    "created_at": row["created_at"] or "",
                    "provider": row["provider"] or "",
                    "model": row["model"] or "",
                    "salience": SALIENCE_DEFAULT,
                    "entity_type": "message",
                }
                points.append(PointStruct(
                    id=row["point_id"], vector=vec, payload=payload,
                ))

            upsert_batch(COLLECTION_MESSAGES, points)

            # Mark chunks as embedded
            with get_connection() as conn:
                chunk_ids = [row["chunk_id"] for row in batch]
                placeholders = ",".join("?" * len(chunk_ids))
                conn.execute(
                    f"UPDATE chunks SET embedded_at = datetime('now') "
                    f"WHERE id IN ({placeholders})",
                    chunk_ids,
                )
                conn.commit()

            embedded += len(points)
        except Exception as e:
            logger.error("Batch embed message chunks failed at offset %d: %s",
                         batch_start, e)
            errors.append(f"chunk_batch@{batch_start}: {str(e)}")

        if embedded > 0 and embedded % 100 < BATCH_SIZE:
            elapsed = time.time() - start_time
            logger.info("Message chunks: %d/%d (%.1fs elapsed)",
                        embedded, chunk_count, elapsed)

    # --- Phase 2: Legacy fallback for unchunked messages ---
    with get_connection() as conn:
        legacy_rows = conn.execute("""
            SELECT m.id, m.conversation_id, m.sequence,
                   m.user_prompt, m.model_response,
                   m.created_at, m.provider, m.model,
                   c.title as conv_title
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE (m.user_prompt != '' OR m.model_response != '')
            AND NOT EXISTS (
                SELECT 1 FROM chunks ch
                WHERE ch.entity_type = 'message' AND ch.entity_id = m.id
            )
        """).fetchall()

    legacy_total = len(legacy_rows)
    if legacy_total:
        logger.info("Legacy embed messages (no chunks): %d candidates",
                     legacy_total)

    for batch_start in range(0, legacy_total, BATCH_SIZE):
        batch = legacy_rows[batch_start:batch_start + BATCH_SIZE]
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
                        "salience": SALIENCE_DEFAULT,
                        "entity_type": "message",
                    },
                )
                for (row, text), vec in zip(valid_rows, vectors)
            ]
            upsert_batch(COLLECTION_MESSAGES, points)
            embedded += len(points)
        except Exception as e:
            logger.error("Legacy batch embed msgs failed at offset %d: %s",
                         batch_start, e)
            errors.append(f"legacy_batch@{batch_start}: {str(e)}")

    elapsed = time.time() - start_time
    logger.info("Bulk embed messages: %d embedded, %d skipped, %d errors (%.1fs)",
                embedded, skipped, len(errors), elapsed)
    return {"embedded": embedded, "skipped": skipped, "errors": errors,
            "elapsed_seconds": round(elapsed, 1)}


# ---------------------------------------------------------------------------
# Single-vector embedding (items, tasks, domains — short texts, no chunking)
# ---------------------------------------------------------------------------


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
