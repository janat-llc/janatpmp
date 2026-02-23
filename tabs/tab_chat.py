"""Chat handler functions — sidebar quick-chat and full Chat tab."""
import json
import gradio as gr
from db.chat_operations import (
    add_message, parse_reasoning,
    list_conversations, get_or_create_janus_conversation,
)
from services.settings import get_setting
from shared.constants import DEFAULT_CHAT_HISTORY
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


def _handle_chat_tab(message, history, conv_id, provider, model,
                     temperature, top_p, max_tokens, system_append):
    """Chat tab handler — persists conversations with triplet schema.

    Returns (display_history, api_history, cleared_input,
             conv_id, conversations_list, status_markdown).
    """
    if not message.strip():
        return history, history, "", conv_id, gr.skip(), "*Ready*"

    try:
        from services.slumber import touch_activity
        touch_activity()
    except Exception:
        pass
    from services.chat import chat

    # Janus fallback — always have a conversation
    if not conv_id:
        conv_id = get_or_create_janus_conversation()

    try:
        # Apply sliding window — send only last N turns to LLM
        window = int(get_setting("janus_context_messages") or "10")
        api_window = _windowed_api_history(history, window)

        result = chat(
            message, api_window,
            provider_override=provider, model_override=model,
            temperature=temperature, top_p=top_p,
            max_tokens=int(max_tokens), system_prompt_append=system_append,
        )

        # Reconstruct full history: original + new messages from this turn
        new_messages = result["history"][len(api_window):]
        updated = list(history) + new_messages

        # Extract final model response (skip tool-use status messages)
        raw_response = ""
        for msg in reversed(updated):
            if msg.get("role") == "assistant" and not msg.get("content", "").startswith("Using `"):
                raw_response = msg.get("content", "")
                break

        reasoning, clean_response = parse_reasoning(raw_response)

        # Build separate display and API histories:
        # - display_history: reasoning in collapsible accordion + clean response
        # - api_history: clean response only (no tags, no <details> — prevents
        #   the model from mimicking HTML formatting on subsequent turns)
        display_history = [dict(m) for m in updated]
        api_history = [dict(m) for m in updated]
        for i in range(len(updated) - 1, -1, -1):
            if updated[i].get("role") == "assistant" and updated[i].get("content") == raw_response:
                # API history: clean response only
                api_history[i] = {"role": "assistant", "content": clean_response or raw_response}
                # Display history: reasoning accordion + clean response
                if reasoning and clean_response:
                    formatted = (
                        f"<details><summary>Thinking</summary>\n\n"
                        f"{reasoning}\n\n</details>\n\n{clean_response}"
                    )
                    display_history[i] = {"role": "assistant", "content": formatted}
                else:
                    display_history[i] = {"role": "assistant", "content": clean_response or raw_response}
                break

        # Collect tool names used in this turn
        tools_used = []
        for msg in updated[len(history):]:
            content = msg.get("content", "")
            if msg.get("role") == "assistant" and content.startswith("Using `") and "`" in content[6:]:
                tool_name = content.split("`")[1]
                if tool_name:
                    tools_used.append(tool_name)

        token_counts = result.get("token_counts", {"prompt": 0, "reasoning": 0, "response": 0, "total": 0})
        rag_metrics = result.get("rag_metrics", {"hit_count": 0, "hits_used": 0, "collections_searched": [], "scores": []})
        timings = result.get("timings", {"rag": 0, "inference": 0, "total": 0})

        msg_id = add_message(
            conversation_id=conv_id,
            user_prompt=message,
            model_reasoning=reasoning or None,
            model_response=clean_response or raw_response,
            provider=provider, model=model,
            tools_called=json.dumps(tools_used),
            tokens_prompt=token_counts.get("prompt", 0),
            tokens_reasoning=token_counts.get("reasoning", 0),
            tokens_response=token_counts.get("response", 0),
        )

        # Cognitive telemetry + live memory (parity with Sovereign Chat)
        if msg_id:
            from db.chat_operations import add_message_metadata, update_message_metadata
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

            # Usage signal
            try:
                from atlas.usage_signal import compute_usage_signal
                from atlas.memory_service import write_usage_salience
                scores = rag_metrics.get("scores", [])
                if scores and (clean_response or raw_response):
                    usage = compute_usage_signal(scores, clean_response or raw_response)
                    if usage:
                        update_message_metadata(msg_id, rag_scores=json.dumps(usage))
                        for collection in {u.get("source", "") for u in usage if u.get("source")}:
                            col_hits = [u for u in usage if u.get("source") == collection]
                            write_usage_salience(collection, col_hits)
            except Exception:
                pass

            # Live memory: embed + INFORMED_BY edges
            try:
                from atlas.on_write import on_message_write
                on_message_write(
                    message_id=msg_id,
                    conversation_id=conv_id,
                    user_prompt=message,
                    model_response=clean_response or raw_response,
                    provider=provider, model=model,
                    rag_hits=rag_metrics.get("scores", []),
                )
            except Exception:
                pass

        convs = list_conversations(limit=30)
        status = f"*{provider} / {model}*"
        return display_history, api_history, "", conv_id, convs, status
    except Exception as e:
        error_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": f"Error: {str(e)}"},
        ]
        return error_history, error_history, "", conv_id, gr.skip(), f"*Error: {str(e)[:80]}*"
