"""On-write pipeline — synchronous chunk + embed + fire-and-forget graph edges.

Called after every add_message() across all three chat surfaces.
Fans out to Qdrant (synchronous embed) and Neo4j (INFORMED_BY edges).

R16: Messages are now chunked before embedding. Each chunk gets its own
Qdrant point with a composite ID ({message_id} for single-chunk,
{message_id}_c{NNN} for multi-chunk). Chunk records are persisted to the
SQLite chunks table for tracking, FTS, and Slumber Cycle operations.

The embed path is synchronous (~100-300ms) to ensure success criterion #1:
the message is immediately retrievable by RAG on the next turn.

The relate path is fire-and-forget — Neo4j being down must never block chat.
Structural edges (BELONGS_TO, FOLLOWS) are handled by the CDC consumer.
This module ONLY creates INFORMED_BY edges (requires rag_hits).
"""

import logging

from atlas.config import SALIENCE_DEFAULT

logger = logging.getLogger(__name__)


def on_message_write(
    message_id: str,
    conversation_id: str,
    user_prompt: str,
    model_response: str,
    sequence: int | None = None,
    provider: str = "",
    model: str = "",
    rag_hits: list[dict] | None = None,
) -> None:
    """Synchronous chunk + embed + fire-and-forget INFORMED_BY edges.

    Args:
        message_id: The persisted message ID from add_message().
        conversation_id: Parent conversation ID.
        user_prompt: The user's message text.
        model_response: The model's response text (clean, no reasoning).
        sequence: Message sequence number (queries DB if None).
        provider: Chat provider name.
        model: Chat model name.
        rag_hits: List of RAG score dicts from _build_rag_context().
    """
    _embed(message_id, conversation_id, user_prompt, model_response,
           sequence, provider, model)
    _relate(message_id, rag_hits)


def _generate_point_id(message_id: str, chunk_index: int, chunk_total: int) -> str:
    """Generate Qdrant point ID for a chunk.

    Single-chunk messages use the raw message_id (backward compatible).
    Multi-chunk messages use {message_id}_c{index:03d}.
    """
    if chunk_total <= 1:
        return message_id
    return f"{message_id}_c{chunk_index:03d}"


def _get_message_context(
    message_id: str,
    conversation_id: str,
    sequence: int | None,
) -> tuple[str, str, int]:
    """Fetch conversation title, created_at, and sequence from DB.

    Returns:
        Tuple of (conv_title, created_at, sequence).
    """
    from db.chat_operations import get_conversation

    conv_title = ""
    try:
        conv = get_conversation(conversation_id)
        if conv:
            conv_title = conv.get("title", "")
    except Exception:
        pass

    created_at = ""
    if sequence is None:
        try:
            from db.operations import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT sequence, created_at FROM messages WHERE id = ?",
                    (message_id,),
                ).fetchone()
                if row:
                    sequence = row["sequence"]
                    created_at = row["created_at"]
        except Exception:
            sequence = 0
    if not created_at:
        try:
            from db.operations import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT created_at FROM messages WHERE id = ?",
                    (message_id,),
                ).fetchone()
                if row:
                    created_at = row["created_at"]
        except Exception:
            pass

    return conv_title, created_at, sequence or 0


def _insert_chunks(message_id: str, chunks: list[dict], point_ids: list[str]) -> None:
    """Persist chunk records to SQLite chunks table."""
    try:
        from db.operations import get_connection
        with get_connection() as conn:
            for chunk, point_id in zip(chunks, point_ids):
                conn.execute(
                    """INSERT OR IGNORE INTO chunks
                       (entity_type, entity_id, chunk_index, chunk_text,
                        char_start, char_end, position, point_id, embedded_at)
                       VALUES ('message', ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (message_id, chunk["index"], chunk["text"],
                     chunk["char_start"], chunk["char_end"],
                     chunk["position"], point_id),
                )
    except Exception as e:
        logger.warning("on_write chunk insert failed for %s: %s", message_id[:12], e)


def _embed(
    message_id: str,
    conversation_id: str,
    user_prompt: str,
    model_response: str,
    sequence: int | None,
    provider: str,
    model: str,
) -> None:
    """Synchronous: chunk and embed the message into Qdrant."""
    text = f"Q: {user_prompt}\nA: {model_response}"
    if len(text) < 20:
        return

    try:
        from atlas.chunking import chunk_message
        from services.embedding import embed_passages
        from services.vector_store import upsert_point
        from services.settings import get_setting

        # Read chunk settings
        max_chars = int(get_setting("chunk_max_chars") or 2500)
        threshold = int(get_setting("chunk_threshold") or 3000)

        # Chunk the message
        chunks = chunk_message(
            user_prompt, model_response,
            max_chars=max_chars, threshold=threshold,
        )
        if not chunks:
            return

        # Fetch conversation context
        conv_title, created_at, seq = _get_message_context(
            message_id, conversation_id, sequence,
        )

        # Generate point IDs
        chunk_total = len(chunks)
        point_ids = [
            _generate_point_id(message_id, c["index"], chunk_total)
            for c in chunks
        ]

        # Embed all chunks in one batch call
        chunk_texts = [c["text"] for c in chunks]
        vectors = embed_passages(chunk_texts)

        # Build base payload (shared across chunks)
        base_payload = {
            "parent_message_id": message_id,
            "conversation_id": conversation_id,
            "conv_title": conv_title,
            "sequence": seq,
            "created_at": created_at,
            "provider": provider,
            "model": model,
            "salience": SALIENCE_DEFAULT,
            "entity_type": "message",
        }

        # Upsert each chunk to Qdrant
        from services.vector_store import COLLECTION_MESSAGES
        for chunk, vector, point_id in zip(chunks, vectors, point_ids):
            payload = {
                **base_payload,
                "text": chunk["text"],
                "chunk_index": chunk["index"],
                "chunk_total": chunk_total,
                "chunk_position": chunk["position"],
            }
            upsert_point(COLLECTION_MESSAGES, point_id, vector, payload)

        # Persist chunk records to SQLite
        _insert_chunks(message_id, chunks, point_ids)

        logger.debug(
            "on_write embed: %s -> %d chunk(s) in Qdrant",
            message_id[:12], chunk_total,
        )

    except Exception as e:
        logger.warning("on_write embed failed for %s: %s", message_id[:12], e)


def _relate(message_id: str, rag_hits: list[dict] | None) -> None:
    """Fire-and-forget: create INFORMED_BY edges in Neo4j."""
    if not rag_hits:
        return

    try:
        from graph.graph_service import create_edge

        for hit in rag_hits:
            hit_id = hit.get("id")
            if not hit_id:
                continue

            source = hit.get("source", "")
            to_label = "Document" if "document" in source.lower() else "Message"

            props = {}
            if hit.get("rerank_score"):
                props["rerank_score"] = hit["rerank_score"]
            if hit.get("salience"):
                props["salience"] = hit["salience"]

            create_edge("Message", message_id, to_label, hit_id, "INFORMED_BY", props)

        logger.debug("on_write relate: %s -> %d INFORMED_BY edges",
                      message_id[:12], len([h for h in rag_hits if h.get("id")]))

    except Exception as e:
        logger.debug("on_write relate skipped for %s: %s", message_id[:12], e)
