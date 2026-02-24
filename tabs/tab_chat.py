"""Chat handler functions — sidebar quick-chat."""
import json
from db.chat_operations import (
    add_message, parse_reasoning,
    get_or_create_janus_conversation,
)
from services.settings import get_setting
from shared.data_helpers import _windowed_api_history


def _handle_chat(message, history, sidebar_conv_id=""):
    """Handle sidebar quick-chat message submission with full persistence.

    Returns (display_history, api_history, cleared_input, sidebar_conv_id).
    Display history has reasoning in collapsible accordion;
    API history has clean response only to prevent model mimicry.
    """
    if not message.strip():
        return history, history, "", sidebar_conv_id
    try:
        from services.slumber import touch_activity
        touch_activity()
    except Exception:
        pass
    from services.chat import chat

    # Janus fallback — always have a conversation
    if not sidebar_conv_id:
        sidebar_conv_id = get_or_create_janus_conversation()

    # Apply sliding window — send only last N turns to LLM
    window = int(get_setting("janus_context_messages") or "10")
    api_window = _windowed_api_history(history, window)

    result = chat(message, api_window)

    # Reconstruct full history: original + new messages from this turn
    new_messages = result["history"][len(api_window):]
    updated = list(history) + new_messages

    # Split display vs API history (keep <details> out of API history
    # so model doesn't mimic HTML formatting on subsequent turns)
    display = [dict(m) for m in updated]
    api = [dict(m) for m in updated]
    raw_response = ""
    reasoning = ""
    clean = ""
    if updated and updated[-1].get("role") == "assistant":
        raw_response = updated[-1].get("content", "")
        reasoning, clean = parse_reasoning(raw_response)
        api[-1] = {"role": "assistant", "content": clean or raw_response}
        if reasoning and clean:
            formatted = (
                f"<details><summary>Thinking</summary>\n\n"
                f"{reasoning}\n\n</details>\n\n{clean}"
            )
            display[-1] = {"role": "assistant", "content": formatted}
        else:
            display[-1] = {"role": "assistant", "content": clean or raw_response}

    # Persist triplet
    token_counts = result.get("token_counts", {"prompt": 0, "reasoning": 0, "response": 0, "total": 0})
    rag_metrics = result.get("rag_metrics", {"hit_count": 0, "hits_used": 0, "collections_searched": [], "scores": []})
    timings = result.get("timings", {"rag": 0, "inference": 0, "total": 0})

    msg_id = add_message(
        conversation_id=sidebar_conv_id,
        user_prompt=message,
        model_reasoning=reasoning or None,
        model_response=clean or raw_response,
        tokens_prompt=token_counts.get("prompt", 0),
        tokens_reasoning=token_counts.get("reasoning", 0),
        tokens_response=token_counts.get("response", 0),
    )

    if msg_id:
        from db.chat_operations import add_message_metadata
        add_message_metadata(
            message_id=msg_id,
            latency_total_ms=timings.get("total", 0),
            latency_rag_ms=timings.get("rag", 0),
            latency_inference_ms=timings.get("inference", 0),
            rag_hit_count=rag_metrics.get("hit_count", 0),
            rag_hits_used=rag_metrics.get("hits_used", 0),
            rag_collections=json.dumps(rag_metrics.get("collections_searched", [])),
            rag_avg_rerank=rag_metrics.get("avg_rerank_score", 0.0),
            rag_avg_salience=rag_metrics.get("avg_salience", 0.0),
            rag_scores=json.dumps(rag_metrics.get("scores", [])),
            system_prompt_length=result.get("system_prompt_length", 0),
            rag_context_text=rag_metrics.get("context_text", ""),
            rag_synthesized=1 if rag_metrics.get("synthesized") else 0,
        )

        # Live memory: embed + INFORMED_BY edges
        try:
            from atlas.on_write import on_message_write
            on_message_write(
                message_id=msg_id,
                conversation_id=sidebar_conv_id,
                user_prompt=message,
                model_response=clean or raw_response,
                rag_hits=rag_metrics.get("scores", []),
            )
        except Exception:
            pass

    return display, api, "", sidebar_conv_id


