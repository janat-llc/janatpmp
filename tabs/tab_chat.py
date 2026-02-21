"""Chat handler functions — sidebar quick-chat and full Chat tab."""
import json
import gradio as gr
from db.chat_operations import (
    create_conversation, add_message, parse_reasoning,
    list_conversations,
)
from shared.constants import DEFAULT_CHAT_HISTORY


def _handle_chat(message, history):
    """Handle sidebar quick-chat message submission.

    Returns (display_history, api_history, cleared_input).
    Display history has reasoning in collapsible accordion;
    API history has clean response only to prevent model mimicry.
    """
    if not message.strip():
        return history, history, ""
    from services.chat import chat
    updated = chat(message, history)

    # Split display vs API history (keep <details> out of API history
    # so model doesn't mimic HTML formatting on subsequent turns)
    display = [dict(m) for m in updated]
    api = [dict(m) for m in updated]
    if updated and updated[-1].get("role") == "assistant":
        raw = updated[-1].get("content", "")
        reasoning, clean = parse_reasoning(raw)
        api[-1] = {"role": "assistant", "content": clean or raw}
        if reasoning and clean:
            formatted = (
                f"<details><summary>Thinking</summary>\n\n"
                f"{reasoning}\n\n</details>\n\n{clean}"
            )
            display[-1] = {"role": "assistant", "content": formatted}
        else:
            display[-1] = {"role": "assistant", "content": clean or raw}

    return display, api, ""


def _handle_chat_tab(message, history, conv_id, provider, model,
                     temperature, top_p, max_tokens, system_append):
    """Chat tab handler — persists conversations with triplet schema.

    Returns (display_history, api_history, cleared_input,
             conv_id, conversations_list, status_markdown).
    """
    if not message.strip():
        return history, history, "", conv_id, gr.skip(), "*Ready*"

    from services.chat import chat

    # Auto-create conversation on first message
    if not conv_id:
        title = message.strip()[:50]
        conv_id = create_conversation(
            provider=provider, model=model,
            system_prompt_append=system_append,
            temperature=temperature, top_p=top_p,
            max_tokens=int(max_tokens), title=title,
        )

    try:
        updated = chat(
            message, history,
            provider_override=provider, model_override=model,
            temperature=temperature, top_p=top_p,
            max_tokens=int(max_tokens), system_prompt_append=system_append,
        )

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

        add_message(
            conversation_id=conv_id,
            user_prompt=message,
            model_reasoning=reasoning or None,
            model_response=clean_response or raw_response,
            provider=provider, model=model,
            tools_called=json.dumps(tools_used),
        )

        convs = list_conversations(limit=30)
        status = f"*{provider} / {model}*"
        return display_history, api_history, "", conv_id, convs, status
    except Exception as e:
        error_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": f"Error: {str(e)}"},
        ]
        return error_history, error_history, "", conv_id, gr.skip(), f"*Error: {str(e)[:80]}*"
