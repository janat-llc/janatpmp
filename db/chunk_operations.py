"""Chunk operations — CRUD and statistics for the chunks table.

R16: Provides MCP-exposed tools for chunk management, search, and statistics.
"""

import logging
from db.operations import get_connection

logger = logging.getLogger(__name__)


def get_chunks(entity_type: str, entity_id: str) -> list[dict]:
    """Get all chunks for a specific entity (message or document).

    Args:
        entity_type: Type of entity — 'message' or 'document'.
        entity_id: The ID of the parent message or document.

    Returns:
        List of chunk dicts with id, chunk_index, chunk_text (first 200 chars),
        char_start, char_end, position, point_id, embedded_at.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, chunk_index, substr(chunk_text, 1, 200) as chunk_preview,
                   char_start, char_end, position, point_id, embedded_at, created_at
            FROM chunks
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY chunk_index
        """, (entity_type, entity_id)).fetchall()

    return [dict(row) for row in rows]


def get_chunk_stats() -> dict:
    """Get chunking statistics across the platform.

    Returns:
        Dict with total_chunks, message_chunks, document_chunks,
        messages_chunked, documents_chunked, avg_chunks_per_message,
        avg_chunks_per_document, embedded_count, unembedded_count.
    """
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        msg_chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE entity_type = 'message'"
        ).fetchone()[0]
        doc_chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE entity_type = 'document'"
        ).fetchone()[0]
        msgs_chunked = conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM chunks WHERE entity_type = 'message'"
        ).fetchone()[0]
        docs_chunked = conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM chunks WHERE entity_type = 'document'"
        ).fetchone()[0]
        embedded = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedded_at IS NOT NULL"
        ).fetchone()[0]
        unembedded = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedded_at IS NULL"
        ).fetchone()[0]

    return {
        "total_chunks": total,
        "message_chunks": msg_chunks,
        "document_chunks": doc_chunks,
        "messages_chunked": msgs_chunked,
        "documents_chunked": docs_chunked,
        "avg_chunks_per_message": round(msg_chunks / max(msgs_chunked, 1), 1),
        "avg_chunks_per_document": round(doc_chunks / max(docs_chunked, 1), 1),
        "embedded_count": embedded,
        "unembedded_count": unembedded,
    }


def search_chunks(query: str, entity_type: str = "", limit: int = 10) -> list[dict]:
    """Full-text search on chunk content via FTS5.

    Args:
        query: Search query string.
        entity_type: Optional filter — 'message' or 'document'. Empty for both.
        limit: Maximum results to return (default 10).

    Returns:
        List of chunk dicts with id, entity_type, entity_id, chunk_preview,
        chunk_index, position, point_id.
    """
    import re
    from services.chat import _FTS_STOP_WORDS

    raw_terms = re.sub(r'[^\w\s]', '', query).split()
    meaningful = [t for t in raw_terms if t.lower() not in _FTS_STOP_WORDS and len(t) > 1]
    if not meaningful:
        return []

    fts_query = " AND ".join(f'"{t}"' for t in meaningful)

    sql = """
        SELECT c.id, c.entity_type, c.entity_id,
               substr(c.chunk_text, 1, 200) as chunk_preview,
               c.chunk_index, c.position, c.point_id
        FROM chunks c
        JOIN chunks_fts fts ON fts.id = c.id
        WHERE chunks_fts MATCH ?
    """
    params = [fts_query]

    if entity_type:
        sql += " AND c.entity_type = ?"
        params.append(entity_type)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def delete_chunks(entity_type: str, entity_id: str) -> str:
    """Delete all chunks for a specific entity, allowing re-chunking.

    Removes chunk records from SQLite. Qdrant points are NOT deleted —
    they will be overwritten on re-embed, or cleaned up by recreate_collections.

    Args:
        entity_type: Type of entity — 'message' or 'document'.
        entity_id: The ID of the parent message or document.

    Returns:
        Status message with count of deleted chunks.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM chunks WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )
        conn.commit()
        count = cursor.rowcount

    return f"Deleted {count} chunks for {entity_type} {entity_id[:12]}"
