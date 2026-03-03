"""Cognition Persistence — Write system/* messages from all chat surfaces.

Single helper called by all three chat surfaces (tab sidebar, sovereign chat,
MCP chat_with_janus) to persist cognition signals as first-class messages.

System messages are written BEFORE the turn triplet so they get sequence N,
and the turn gets sequence N+1. This ensures chronological ordering.

Failure in this module NEVER blocks chat. All operations are try/except.

R35: Intent Engine — Cognition as Conversation Participant
"""

import logging

logger = logging.getLogger(__name__)


def persist_cognition_messages(
    conversation_id: str,
    engine_result=None,
    precog_directives: dict | None = None,
) -> list[str]:
    """Write system/intent (and optionally system/precognition) messages.

    Called by all three chat surfaces after chat() returns but before
    the turn triplet is persisted via add_message().

    Args:
        conversation_id: The active conversation ID.
        engine_result: EngineResult from intent_engine.process() (may be None).
        precog_directives: Pre-cognition directive dict (may be None).

    Returns:
        List of created message IDs (may be empty on failure or no-op).
    """
    created_ids = []

    # 1. Persist system/intent signal
    if engine_result and getattr(engine_result, "system_message_content", ""):
        try:
            from db.chat_operations import add_system_message
            from atlas.on_write import on_message_write

            msg_id = add_system_message(
                conversation_id,
                role="system/intent",
                content=engine_result.system_message_content,
            )
            if msg_id:
                created_ids.append(msg_id)
                # Embed for RAG searchability (role-aware — no Q:/A: wrapper)
                on_message_write(
                    message_id=msg_id,
                    conversation_id=conversation_id,
                    user_prompt=engine_result.system_message_content,
                    model_response="",
                    role="system/intent",
                )
        except Exception as e:
            logger.debug("cognition_persistence: system/intent failed: %s", e)

    # 2. Persist system/precognition signal
    if precog_directives and precog_directives.get("precognition_used"):
        try:
            import json
            from db.chat_operations import add_system_message
            from atlas.on_write import on_message_write

            precog_content = json.dumps({
                "memory_directive": precog_directives.get("memory_directive", ""),
                "tone_directive": precog_directives.get("tone_directive", ""),
                "layer_weights": precog_directives.get("layer_weights", {}),
            }, separators=(",", ":"))

            msg_id = add_system_message(
                conversation_id,
                role="system/precognition",
                content=precog_content,
            )
            if msg_id:
                created_ids.append(msg_id)
                on_message_write(
                    message_id=msg_id,
                    conversation_id=conversation_id,
                    user_prompt=precog_content,
                    model_response="",
                    role="system/precognition",
                )
        except Exception as e:
            logger.debug("cognition_persistence: system/precognition failed: %s", e)

    return created_ids
