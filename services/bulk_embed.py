"""Bulk embed existing JANATPMP data into Qdrant.

Run once to backfill, then incremental embedding happens via CDC or on-create.
"""

from db.operations import get_connection
from services.vector_store import ensure_collections, upsert_document, upsert_message


def embed_all_documents() -> dict:
    """Embed all documents from the documents table.

    Returns:
        Dict with keys: embedded, skipped, errors.
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []

    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT id, title, doc_type, source, content, created_at
            FROM documents
            WHERE content IS NOT NULL AND length(content) > 10
        """)
        rows = cursor.fetchall()

    for row in rows:
        try:
            upsert_document(
                doc_id=row["id"],
                text=row["content"],
                metadata={
                    "title": row["title"] or "",
                    "doc_type": row["doc_type"] or "",
                    "source": row["source"] or "",
                    "created_at": row["created_at"] or "",
                },
            )
            embedded += 1
        except Exception as e:
            errors.append(f"{row['id']}: {str(e)[:80]}")

    return {"embedded": embedded, "skipped": skipped, "errors": errors}


def embed_all_messages() -> dict:
    """Embed all conversation messages.

    Returns:
        Dict with keys: embedded, skipped, errors.
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []

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

    for row in rows:
        try:
            text = f"Q: {row['user_prompt']}\nA: {row['model_response']}"
            if len(text.strip()) < 20:
                skipped += 1
                continue

            upsert_message(
                message_id=row["id"],
                text=text,
                metadata={
                    "conversation_id": row["conversation_id"],
                    "conv_title": row["conv_title"] or "",
                    "sequence": row["sequence"],
                },
            )
            embedded += 1
        except Exception as e:
            errors.append(f"{row['id']}: {str(e)[:80]}")

    return {"embedded": embedded, "skipped": skipped, "errors": errors}
