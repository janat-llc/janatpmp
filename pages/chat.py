"""Sovereign Chat page — standalone Gradio Blocks app for /chat route.

Three-panel layout:
- Left sidebar: Conversation list with search, New Chat button
- Center: Chatbot + input + collapsed config accordion
- No right sidebar (chat IS the main panel)

Can run standalone: python pages/chat.py
"""

import json
import gradio as gr
from db.chat_operations import (
    create_conversation, get_messages, list_conversations,
    update_conversation, delete_conversation, parse_reasoning, add_message,
)
from services.chat import chat, PROVIDER_PRESETS, fetch_ollama_models
from services.settings import get_setting, set_setting
from shared.constants import DEFAULT_CHAT_HISTORY
from shared.data_helpers import _msgs_to_history, _load_most_recent_chat
from shared.chat_service import (
    get_active_conversation_id, set_active_conversation_id,
    get_chat_config,
)


# ---------------------------------------------------------------------------
# Chat handler (self-contained — does NOT import from tabs/tab_chat.py)
# ---------------------------------------------------------------------------

def _handle_send(message, history, conv_id, provider, model,
                 temperature, top_p, max_tokens, system_append):
    """Process a chat message: inference → triplet persistence → UI update.

    Returns (display_history, api_history, cleared_input,
             conv_id, conversations_list, status_markdown).
    """
    if not message.strip():
        return history, history, "", conv_id, gr.skip(), "*Ready*"

    # Auto-create conversation on first message
    if not conv_id:
        title = message.strip()[:50]
        conv_id = create_conversation(
            provider=provider, model=model,
            system_prompt_append=system_append,
            temperature=temperature, top_p=top_p,
            max_tokens=int(max_tokens), title=title,
        )

    # Update module-level active conversation pointer
    set_active_conversation_id(conv_id)

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

        # Build separate display and API histories
        display_history = [dict(m) for m in updated]
        api_history = [dict(m) for m in updated]
        for i in range(len(updated) - 1, -1, -1):
            if updated[i].get("role") == "assistant" and updated[i].get("content") == raw_response:
                api_history[i] = {"role": "assistant", "content": clean_response or raw_response}
                if reasoning and clean_response:
                    formatted = (
                        f"<details><summary>Thinking</summary>\n\n"
                        f"{reasoning}\n\n</details>\n\n{clean_response}"
                    )
                    display_history[i] = {"role": "assistant", "content": formatted}
                else:
                    display_history[i] = {"role": "assistant", "content": clean_response or raw_response}
                break

        # Collect tool names used
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


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def build_chat_page():
    """Build the Sovereign Chat page layout. Call inside a gr.Blocks context."""

    # --- Load initial state ---
    initial_conv_id, initial_history = _load_most_recent_chat()
    if initial_conv_id:
        set_active_conversation_id(initial_conv_id)

    config = get_chat_config()
    current_provider = config["provider"]
    current_model = config["model"]

    # --- States ---
    chat_history = gr.State(list(initial_history))
    active_conv_id = gr.State(initial_conv_id)
    conversations_state = gr.State(list_conversations(limit=30))
    conv_search_query = gr.State("")
    provider_state = gr.State(current_provider)
    model_state = gr.State(current_model)
    temperature_state = gr.State(config["temperature"])
    top_p_state = gr.State(config["top_p"])
    max_tokens_state = gr.State(config["max_tokens"])
    system_append_state = gr.State("")

    # === LEFT SIDEBAR — Conversation list ===
    with gr.Sidebar(position="left"):
        gr.Markdown("### Conversations")

        @gr.render(inputs=[conversations_state, active_conv_id, conv_search_query])
        def render_conv_list(conversations, active_id, search_q):
            conv_search_input = gr.Textbox(
                placeholder="Search by title... (Enter)",
                show_label=False, key="conv-search",
                value=search_q, max_lines=1,
            )
            new_chat_btn = gr.Button("+ New Chat", variant="primary", size="sm", key="new-chat-btn")

            if not conversations:
                gr.Markdown("*No conversations found.*")
            else:
                for conv in conversations:
                    title = (conv.get("title") or "New Chat")[:40]
                    date = (conv.get("updated_at") or "")[:10]
                    is_active = conv["id"] == active_id
                    with gr.Row(key=f"convrow-{conv['id'][:8]}"):
                        conv_btn = gr.Button(
                            f"{title}\n{date}",
                            key=f"conv-{conv['id'][:8]}",
                            size="sm",
                            variant="primary" if is_active else "secondary",
                            scale=4,
                        )
                        del_btn = gr.Button(
                            "X", key=f"del-{conv['id'][:8]}",
                            size="sm", variant="stop", scale=0, min_width=32,
                        )

                    # Load conversation on click
                    def on_conv_click(c_id=conv["id"]):
                        msgs = get_messages(c_id)
                        history = _msgs_to_history(msgs) or list(DEFAULT_CHAT_HISTORY)
                        set_active_conversation_id(c_id)
                        return c_id, history, history
                    conv_btn.click(
                        on_conv_click,
                        outputs=[active_conv_id, chatbot, chat_history],
                        api_visibility="private",
                        key=f"conv-click-{conv['id'][:8]}",
                    )

                    # Delete conversation
                    def on_delete(c_id=conv["id"], was_active=(conv["id"] == active_id)):
                        delete_conversation(c_id)
                        new_convs = list_conversations(limit=30)
                        if was_active:
                            set_active_conversation_id("")
                            return new_convs, "", list(DEFAULT_CHAT_HISTORY), list(DEFAULT_CHAT_HISTORY)
                        return new_convs, gr.skip(), gr.skip(), gr.skip()
                    del_btn.click(
                        on_delete,
                        outputs=[conversations_state, active_conv_id, chatbot, chat_history],
                        api_visibility="private",
                        key=f"del-click-{conv['id'][:8]}",
                    )

                    # Rename for active conversation
                    if is_active:
                        with gr.Row(key=f"rename-{conv['id'][:8]}"):
                            rename_input = gr.Textbox(
                                value=conv.get("title") or "",
                                show_label=False, key=f"ren-inp-{conv['id'][:8]}",
                                scale=3, max_lines=1,
                            )
                            rename_btn = gr.Button(
                                "Save", key=f"ren-btn-{conv['id'][:8]}",
                                size="sm", variant="secondary", scale=1,
                            )

                        def on_rename(new_title, c_id=conv["id"]):
                            if new_title.strip():
                                update_conversation(c_id, title=new_title.strip())
                            return list_conversations(limit=30)
                        rename_btn.click(
                            on_rename,
                            inputs=[rename_input],
                            outputs=[conversations_state],
                            api_visibility="private",
                            key=f"ren-click-{conv['id'][:8]}",
                        )

            # Search handler
            def _search_convs(query):
                if query and query.strip():
                    return list_conversations(limit=100, title_filter=query.strip()), query
                return list_conversations(limit=30), ""
            conv_search_input.submit(
                _search_convs,
                inputs=[conv_search_input],
                outputs=[conversations_state, conv_search_query],
                api_visibility="private",
                key="conv-search-submit",
            )

            # New chat handler
            def _new_chat():
                set_active_conversation_id("")
                return "", list(DEFAULT_CHAT_HISTORY), list(DEFAULT_CHAT_HISTORY), list_conversations(limit=30)
            new_chat_btn.click(
                _new_chat,
                outputs=[active_conv_id, chatbot, chat_history, conversations_state],
                api_visibility="private",
                key="new-chat-click",
            )

    # === CENTER PANEL — Chatbot + input + config ===
    chatbot = gr.Chatbot(
        value=list(initial_history),
        show_label=False,
        buttons=["copy"],
        scale=1,
        min_height=500,
        elem_id="chat-page-chatbot",
    )

    chat_input = gr.Textbox(
        placeholder="Ask anything... (Enter to send, Shift+Enter for newline)",
        show_label=False,
        interactive=True,
        max_lines=5,
    )

    chat_status = gr.Markdown("*Ready*")

    # --- Configuration accordion (collapsed by default) ---
    with gr.Accordion("Configuration", open=False):
        with gr.Row():
            cfg_provider = gr.Dropdown(
                choices=["anthropic", "gemini", "ollama"],
                value=current_provider,
                label="Provider", interactive=True, scale=1,
            )
            _ollama_preset = PROVIDER_PRESETS.get("ollama", {})
            if current_provider == "ollama":
                _model_choices = fetch_ollama_models() or [_ollama_preset.get("default_model", "")]
            else:
                _model_choices = PROVIDER_PRESETS.get(current_provider, {}).get("models", [])
            cfg_model = gr.Dropdown(
                choices=_model_choices,
                value=current_model,
                label="Model", interactive=True, allow_custom_value=True, scale=2,
            )
        with gr.Row():
            cfg_temperature = gr.Slider(
                label="Temperature", minimum=0.0, maximum=2.0,
                step=0.1, value=config["temperature"], interactive=True,
            )
            cfg_top_p = gr.Slider(
                label="Top P", minimum=0.0, maximum=1.0,
                step=0.05, value=config["top_p"], interactive=True,
            )
            cfg_max_tokens = gr.Slider(
                label="Max Tokens", minimum=256, maximum=16384,
                step=256, value=config["max_tokens"], interactive=True,
            )
        cfg_system_append = gr.Textbox(
            label="System Prompt (session)",
            placeholder="Additional instructions for this conversation...",
            lines=2, interactive=True,
        )

    # === EVENT WIRING ===

    # --- Chat send ---
    _send_inputs = [
        chat_input, chat_history, active_conv_id,
        provider_state, model_state,
        temperature_state, top_p_state, max_tokens_state,
        system_append_state,
    ]
    _send_outputs = [
        chatbot, chat_history, chat_input,
        active_conv_id, conversations_state, chat_status,
    ]

    chat_input.submit(
        _handle_send, inputs=_send_inputs, outputs=_send_outputs,
        api_visibility="private",
    )

    # --- Config changes → state + DB persistence ---
    def _on_provider_change(provider):
        set_setting("chat_provider", provider)
        preset = PROVIDER_PRESETS.get(provider, {})
        if provider == "ollama":
            models = fetch_ollama_models() or [preset.get("default_model", "")]
        else:
            models = preset.get("models", [])
        default_model = models[0] if models else preset.get("default_model", "")
        set_setting("chat_model", default_model)
        return gr.Dropdown(choices=models, value=default_model), provider, default_model

    cfg_provider.change(
        _on_provider_change, inputs=[cfg_provider],
        outputs=[cfg_model, provider_state, model_state],
        api_visibility="private",
    )
    cfg_model.change(
        lambda m: (set_setting("chat_model", m), m)[-1],
        inputs=[cfg_model], outputs=[model_state],
        api_visibility="private",
    )
    cfg_temperature.change(
        lambda v: v, inputs=[cfg_temperature], outputs=[temperature_state],
        api_visibility="private",
    )
    cfg_top_p.change(
        lambda v: v, inputs=[cfg_top_p], outputs=[top_p_state],
        api_visibility="private",
    )
    cfg_max_tokens.change(
        lambda v: int(v), inputs=[cfg_max_tokens], outputs=[max_tokens_state],
        api_visibility="private",
    )
    cfg_system_append.change(
        lambda v: v, inputs=[cfg_system_append], outputs=[system_append_state],
        api_visibility="private",
    )


# ---------------------------------------------------------------------------
# Standalone testing — only builds its own Blocks when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from db.operations import init_database
    from services.settings import init_settings
    init_database()
    init_settings()

    with gr.Blocks(title="JANATPMP — Chat") as demo:
        build_chat_page()

    demo.launch(server_name="0.0.0.0", server_port=7861, show_error=True)
