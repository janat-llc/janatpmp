"""On-write pipeline — synchronous embed + fire-and-forget graph edges.

Called after every add_message() across all three chat surfaces.
Fans out to Qdrant (synchronous embed) and Neo4j (INFORMED_BY edges).

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
    """Synchronous embed + fire-and-forget INFORMED_BY edges.

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


def _embed(
    message_id: str,
    conversation_id: str,
    user_prompt: str,
    model_response: str,
    sequence: int | None,
    provider: str,
    model: str,
) -> None:
    """Synchronous: embed the message into Qdrant for immediate retrieval."""
    text = f"Q: {user_prompt}\nA: {model_response}"
    if len(text) < 20:
        return

    try:
        from services.vector_store import upsert_message
        from db.chat_operations import get_conversation

        # Get conversation title and message created_at for temporal payloads
        conv_title = ""
        try:
            conv = get_conversation(conversation_id)
            if conv:
                conv_title = conv.get("title", "")
        except Exception:
            pass

        # Get sequence and created_at if not provided
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

        payload = {
            "conversation_id": conversation_id,
            "conv_title": conv_title,
            "sequence": sequence or 0,
            "created_at": created_at,
            "provider": provider,
            "model": model,
            "salience": SALIENCE_DEFAULT,
        }

        upsert_message(message_id, text, payload)
        logger.debug("on_write embed: %s -> Qdrant", message_id[:12])

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
