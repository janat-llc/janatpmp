"""Sovereign Chat page — standalone Gradio Blocks app for /chat route.

Three-panel layout:
- Left sidebar: RAG/Chat metrics dashboard (per-turn + cumulative)
- Center: Chatbot + input + New Chat + status
- Right sidebar: Per-turn parameters (top) + Global defaults (bottom)

Can run standalone: python pages/chat.py
"""

import json
import re
import gradio as gr
from db.chat_operations import (
    create_conversation, parse_reasoning, add_message,
    add_message_metadata, update_message_metadata,
)
from services.chat import chat, PROVIDER_PRESETS, fetch_ollama_models, _EMPTY_RAG_METRICS, _EMPTY_TOKEN_COUNTS


def _sanitize_tool_call_xml(text: str) -> str:
    """Convert <tool_call> XML to visible markdown.

    Some models emit raw XML tool calls instead of using the function calling
    API. Gradio's markdown renderer strips unknown XML tags, leaving an empty
    chat bubble. This converts them to readable content.
    """
    if not text or "<tool_call>" not in text:
        return text

    calls = []
    for match in re.finditer(
        r'<function=(\w+)>(.*?)</function>',
        text,
        re.DOTALL,
    ):
        fn_name = match.group(1)
        params_block = match.group(2).strip()
        params = []
        for pm in re.finditer(
            r'<parameter=(\w+)>\s*(.*?)\s*</parameter>',
            params_block,
            re.DOTALL,
        ):
            params.append(f'{pm.group(1)}="{pm.group(2).strip()}"')
        param_str = ", ".join(params) if params else ""
        calls.append(f"`{fn_name}({param_str})`")

    if calls:
        call_list = ", ".join(calls)
        return (
            f"I wanted to call {call_list} to find that information, "
            f"but tool execution was not available for this response. "
            f"The knowledge you're asking about may not be in my current RAG context."
        )

    # Fallback: just wrap the raw XML in a code block so it's visible
    return f"```xml\n{text.strip()}\n```"

from services.settings import get_setting, set_setting
from shared.constants import DEFAULT_CHAT_HISTORY
from shared.data_helpers import _load_most_recent_chat, _load_chat_session
from shared.chat_service import (
    set_active_conversation_id,
    get_chat_config,
)


# ---------------------------------------------------------------------------
# Chat handler (self-contained — does NOT import from tabs/tab_chat.py)
# ---------------------------------------------------------------------------

def _handle_send(message, history, conv_id, provider, model,
                 temperature, top_p, max_tokens, system_append, metrics):
    """Process a chat message: inference → triplet persistence → metrics → UI update.

    Returns (display_history, api_history, cleared_input,
             conv_id, turn_metrics).
    """
    if not message.strip():
        return history, history, "", conv_id, gr.skip()

    # Reset Slumber Cycle idle timer
    try:
        from services.slumber import touch_activity
        touch_activity()
    except Exception:
        pass

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
        result = chat(
            message, history,
            provider_override=provider, model_override=model,
            temperature=temperature, top_p=top_p,
            max_tokens=int(max_tokens), system_prompt_append=system_append,
        )
        updated = result["history"]
        rag_metrics = result.get("rag_metrics", dict(_EMPTY_RAG_METRICS))
        token_counts = result.get("token_counts", dict(_EMPTY_TOKEN_COUNTS))

        # Extract final model response (skip tool-use status messages)
        raw_response = ""
        for msg in reversed(updated):
            if msg.get("role") == "assistant" and not msg.get("content", "").startswith("Using `"):
                raw_response = msg.get("content", "")
                break

        reasoning, clean_response = parse_reasoning(raw_response)

        # Sanitize <tool_call> XML that some models emit as plain text
        # (Gradio markdown strips unknown XML tags → empty chat bubble)
        clean_response = _sanitize_tool_call_xml(clean_response)

        # Decompose reasoning tokens from completion_tokens when provider
        # doesn't report them separately (Ollama lumps <think> + response).
        # Proportional split by text length — same model, same tokenizer,
        # so chars-per-token ratio is consistent across both segments.
        if reasoning and token_counts.get("reasoning", 0) == 0:
            completion = token_counts.get("response", 0)
            reasoning_len = len(reasoning)
            response_len = len(clean_response or raw_response)
            total_len = reasoning_len + response_len
            if completion > 0 and total_len > 0:
                est_reasoning = int(completion * reasoning_len / total_len)
                token_counts["reasoning"] = est_reasoning
                token_counts["response"] = completion - est_reasoning
            else:
                # Fallback: rough estimate when provider reports no tokens at all
                token_counts["reasoning"] = max(1, reasoning_len // 4)
            token_counts["total"] = (
                token_counts.get("prompt", 0)
                + token_counts.get("reasoning", 0)
                + token_counts.get("response", 0)
            )

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

        # Persist cognitive telemetry metadata
        if msg_id:
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
            )

            # Usage signal: estimate which RAG hits the model actually used
            try:
                from atlas.usage_signal import compute_usage_signal
                from atlas.memory_service import write_usage_salience
                scores = rag_metrics.get("scores", [])
                if scores and (clean_response or raw_response):
                    usage = compute_usage_signal(scores, clean_response or raw_response)
                    if usage:
                        # Update metadata with usage scores
                        update_message_metadata(msg_id, rag_scores=json.dumps(usage))
                        # Write usage-based salience back to Qdrant
                        for collection in {u.get("source", "") for u in usage if u.get("source")}:
                            col_hits = [u for u in usage if u.get("source") == collection]
                            write_usage_salience(collection, col_hits)
            except Exception:
                pass  # Graceful degradation — usage signal is non-critical

            # Live memory: synchronous embed + fire-and-forget INFORMED_BY edges
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
                pass  # Graceful degradation — embed-on-write is non-critical

        # Accumulate cumulative tokens
        prev_cum = metrics.get("cumulative_tokens", dict(_EMPTY_TOKEN_COUNTS))
        new_cum = {
            "prompt": prev_cum.get("prompt", 0) + token_counts.get("prompt", 0),
            "reasoning": prev_cum.get("reasoning", 0) + token_counts.get("reasoning", 0),
            "response": prev_cum.get("response", 0) + token_counts.get("response", 0),
            "total": prev_cum.get("total", 0) + token_counts.get("total", 0),
        }
        new_metrics = {
            "rag_metrics": rag_metrics,
            "token_counts": token_counts,
            "timings": timings,
            "cumulative_tokens": new_cum,
            "turn_count": metrics.get("turn_count", 0) + 1,
        }

        return display_history, api_history, "", conv_id, new_metrics
    except Exception as e:
        error_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": f"Error: {str(e)}"},
        ]
        return error_history, error_history, "", conv_id, gr.skip()


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def build_chat_page():
    """Build the Sovereign Chat page layout. Call inside a gr.Blocks context."""

    # --- Load initial state (build-time snapshot — overwritten per-session by timer) ---
    initial = _load_chat_session()
    if initial["conv_id"]:
        set_active_conversation_id(initial["conv_id"])

    config = get_chat_config()
    current_provider = config["provider"]
    current_model = config["model"]

    # --- States ---
    chat_history = gr.State(list(initial["api_history"]))
    active_conv_id = gr.State(initial["conv_id"])
    provider_state = gr.State(current_provider)
    model_state = gr.State(current_model)
    temperature_state = gr.State(config["temperature"])
    top_p_state = gr.State(config["top_p"])
    max_tokens_state = gr.State(config["max_tokens"])
    system_append_state = gr.State("")

    # Metrics state — updated after each send, drives left sidebar render
    turn_metrics = gr.State({
        "rag_metrics": dict(_EMPTY_RAG_METRICS),
        "token_counts": dict(_EMPTY_TOKEN_COUNTS),
        "cumulative_tokens": dict(_EMPTY_TOKEN_COUNTS),
        "turn_count": 0,
    })

    # === LEFT SIDEBAR — Metrics Dashboard ===
    with gr.Sidebar(position="left"):
        gr.Markdown("### Chat Metrics")

        @gr.render(inputs=[turn_metrics])
        def render_metrics(metrics):
            tc = metrics.get("turn_count", 0)
            rag = metrics.get("rag_metrics", {})
            tok = metrics.get("token_counts", {})
            cum = metrics.get("cumulative_tokens", {})

            gr.Markdown(f"**Turn {tc}**" if tc > 0 else "*No messages yet*")

            if tc > 0:
                # RAG Retrieval — funnel summary
                gr.Markdown("#### RAG Retrieval")
                hits_used = rag.get("hits_used", 0)
                hit_count = rag.get("hit_count", 0)
                rejected_count = len(rag.get("rejected", []))
                collections = rag.get("collections_searched", [])
                avg_rerank = rag.get("avg_rerank_score", 0.0)
                avg_sal = rag.get("avg_salience", 0.0)

                synthesized = rag.get("synthesized", False)
                synth_label = " (synthesized)" if synthesized else ""

                gr.Markdown(
                    f"Hits: **{hits_used}** used / {hit_count} retrieved"
                    + (f" ({rejected_count} rejected)" if rejected_count else "")
                    + synth_label
                    + f"\n\nCollections: {', '.join(collections) if collections else 'none'}"
                    + f"\n\nAvg rerank: **{avg_rerank:.3f}**"
                    + f"\n\nAvg salience: **{avg_sal:.3f}**"
                )

                # Accordion 1: RAG Context Injected — the exact text fed to the model
                context_text = rag.get("context_text", "")
                accordion_label = "Synthesized Context" if synthesized else "Context Injected"
                with gr.Accordion(accordion_label, open=False):
                    if context_text:
                        gr.Textbox(
                            value=context_text, lines=8, max_lines=25,
                            interactive=False, show_label=False,
                            key="rag-context-text",
                        )
                    else:
                        gr.Markdown("*No context injected this turn*")

                # Show raw chunks if synthesis was used (for comparison)
                if synthesized:
                    raw_context = rag.get("raw_context_text", "")
                    if raw_context:
                        with gr.Accordion("Raw Chunks (pre-synthesis)", open=False):
                            gr.Textbox(
                                value=raw_context, lines=6, max_lines=20,
                                interactive=False, show_label=False,
                                key="rag-raw-context",
                            )

                # Accordion 2: RAG Provenance — used hits with text previews
                scores = rag.get("scores", [])
                if scores:
                    with gr.Accordion(f"Provenance ({len(scores)} hits)", open=False):
                        for i, s in enumerate(scores):
                            source_badge = "MSG" if s.get("source") == "messages" else "DOC"
                            title = (s.get("title", "") or "untitled")[:60]
                            conv_title = s.get("source_conversation_title", "")
                            created = (s.get("created_at", "") or "")[:10]
                            preview = (s.get("text_preview", "") or "")[:150]
                            rerank_s = s.get("rerank_score", 0)
                            sal_s = s.get("salience", 0)
                            ann_s = s.get("ann_score", 0)

                            line = f"**{i+1}. [{source_badge}]** {title}"
                            if conv_title:
                                line += f"\n\n*{conv_title[:50]}*"
                            if created:
                                line += f" ({created})"
                            line += f"\n\nrerank: {rerank_s:.3f} | sal: {sal_s:.3f} | ann: {ann_s:.3f}"
                            if preview:
                                line += f"\n\n> {preview}..."
                            gr.Markdown(line, key=f"hit-{i}")

                # Accordion 3: Rejected Candidates — considered but below threshold
                rejected = rag.get("rejected", [])
                if rejected:
                    with gr.Accordion(f"Rejected ({len(rejected)})", open=False):
                        for i, s in enumerate(rejected):
                            title = (s.get("title", "") or "untitled")[:40]
                            reason = s.get("reject_reason", "below threshold")
                            rerank_s = s.get("rerank_score", 0)
                            gr.Markdown(
                                f"~~{i+1}. {title}~~ — {reason}",
                                key=f"rejected-{i}",
                            )

                # Latency
                timings = metrics.get("timings", {})
                if timings.get("total", 0) > 0:
                    gr.Markdown("#### Latency")
                    gr.Markdown(
                        f"Total: **{timings.get('total', 0):,}** ms\n\n"
                        f"RAG: **{timings.get('rag', 0):,}** ms\n\n"
                        f"Inference: **{timings.get('inference', 0):,}** ms"
                    )

                # Token counts — this turn
                gr.Markdown("#### Tokens (this turn)")
                gr.Markdown(
                    f"Prompt: **{tok.get('prompt', 0):,}**\n\n"
                    f"Reasoning: **{tok.get('reasoning', 0):,}**\n\n"
                    f"Response: **{tok.get('response', 0):,}**\n\n"
                    f"Total: **{tok.get('total', 0):,}**"
                )

                # Cumulative tokens
                gr.Markdown("#### Tokens (session)")
                gr.Markdown(
                    f"Prompt: **{cum.get('prompt', 0):,}**\n\n"
                    f"Reasoning: **{cum.get('reasoning', 0):,}**\n\n"
                    f"Response: **{cum.get('response', 0):,}**\n\n"
                    f"Total: **{cum.get('total', 0):,}**"
                )

    # === RIGHT SIDEBAR — Session Parameters ===
    with gr.Sidebar(position="right"):
        gr.Markdown("### Session")
        new_chat_btn = gr.Button("New", variant="secondary", size="sm")
        cfg_provider = gr.Dropdown(
            choices=["anthropic", "gemini", "ollama"],
            value=current_provider,
            label="Provider", interactive=True,
        )
        _ollama_preset = PROVIDER_PRESETS.get("ollama", {})
        if current_provider == "ollama":
            _model_choices = fetch_ollama_models() or [_ollama_preset.get("default_model", "")]
        else:
            _model_choices = PROVIDER_PRESETS.get(current_provider, {}).get("models", [])
        cfg_model = gr.Dropdown(
            choices=_model_choices,
            value=current_model,
            label="Model", interactive=True, allow_custom_value=True,
        )
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
            label="Session Instructions",
            placeholder="Additional instructions for this session...",
            lines=3, interactive=True,
        )

    # === CENTER PANEL — Tabs: Chat + Settings ===
    with gr.Tabs():
        # --- Chat Tab ---
        with gr.Tab("Chat"):
            chatbot = gr.Chatbot(
                value=list(initial["display_history"]),
                show_label=False,
                buttons=["copy"],
                elem_id="chat-page-chatbot",
            )

            chat_input = gr.Textbox(
                placeholder="Ask anything... (Enter to send, Shift+Enter for newline)",
                show_label=False,
                interactive=True,
                max_lines=5,
            )

        # --- Settings Tab (Platform / User level) ---
        with gr.Tab("Settings"):
            gr.Markdown("### Platform Defaults")
            gr.Markdown("*Persisted to DB. Used as defaults when entering Chat and by sidebar chats on other pages.*")

            global_provider = gr.Dropdown(
                choices=["anthropic", "gemini", "ollama"],
                value=current_provider,
                label="Default Provider", interactive=True,
            )
            global_model = gr.Dropdown(
                choices=_model_choices,
                value=current_model,
                label="Default Model", interactive=True, allow_custom_value=True,
            )
            with gr.Row():
                global_temperature = gr.Slider(
                    label="Default Temperature", minimum=0.0, maximum=2.0,
                    step=0.1, value=config["temperature"], interactive=True,
                )
                global_top_p = gr.Slider(
                    label="Default Top P", minimum=0.0, maximum=1.0,
                    step=0.05, value=config["top_p"], interactive=True,
                )
            global_max_tokens = gr.Slider(
                label="Default Max Tokens", minimum=256, maximum=16384,
                step=256, value=config["max_tokens"], interactive=True,
            )

            gr.Markdown("---")
            gr.Markdown("### System Instructions")
            gr.Markdown("*Base system prompt for all chat interactions. Like Memory in Claude — persistent context.*")
            global_system_prompt = gr.Textbox(
                value=get_setting("chat_system_prompt"),
                label="System Prompt",
                placeholder="You are a helpful assistant specialized in...",
                lines=8, interactive=True,
            )

            gr.Markdown("---")
            gr.Markdown("### RAG Configuration")
            rag_threshold = gr.Slider(
                label="Score Threshold", minimum=0.0, maximum=1.0,
                step=0.05, value=float(get_setting("rag_score_threshold") or "0.3"),
                interactive=True,
            )
            rag_max_chunks = gr.Slider(
                label="Max Chunks", minimum=1, maximum=20,
                step=1, value=int(get_setting("rag_max_chunks") or "10"),
                interactive=True,
            )

            gr.Markdown("---")
            gr.Markdown("### RAG Synthesizer")
            gr.Markdown(
                "*Compresses raw RAG chunks into coherent context before "
                "sending to the chat model. Ollama = free local, Gemini = cloud.*"
            )
            _synth_provider = get_setting("rag_synthesizer_provider") or "ollama"
            rag_synth_provider = gr.Dropdown(
                choices=["ollama", "gemini"],
                value=_synth_provider,
                label="Synthesizer Backend", interactive=True,
            )
            _synth_model = get_setting("rag_synthesizer_model") or "qwen3:1.7b"
            rag_synth_model = gr.Dropdown(
                choices=["qwen3:1.7b", "qwen3:4b", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
                value=_synth_model,
                label="Synthesizer Model", interactive=True, allow_custom_value=True,
            )
            rag_synth_api_key = gr.Textbox(
                value=get_setting("rag_synthesizer_api_key"),
                label="Gemini API Key (only needed for Gemini backend)",
                type="password", interactive=True,
                placeholder="Enter Google AI API key...",
            )

    # === PER-SESSION INIT (one-shot timer — loads fresh data from DB) ===
    session_load_timer = gr.Timer(value=0.5, active=True)

    def _init_session():
        """Reload most recent conversation from DB per session (fires once)."""
        session = _load_chat_session()
        if session["conv_id"]:
            set_active_conversation_id(session["conv_id"])
        metrics = {
            "rag_metrics": dict(_EMPTY_RAG_METRICS),
            "token_counts": dict(_EMPTY_TOKEN_COUNTS),
            "timings": session.get("last_timings", {"rag": 0, "inference": 0, "total": 0}),
            "cumulative_tokens": session["token_totals"],
            "turn_count": session["turn_count"],
        }
        return (
            list(session["display_history"]),
            list(session["api_history"]),
            session["conv_id"],
            metrics,
            gr.Timer(active=False),
        )

    session_load_timer.tick(
        _init_session,
        outputs=[chatbot, chat_history, active_conv_id, turn_metrics, session_load_timer],
        api_visibility="private",
    )

    # === EVENT WIRING ===

    # --- New Chat ---
    def _new_chat():
        set_active_conversation_id("")
        empty_metrics = {
            "rag_metrics": dict(_EMPTY_RAG_METRICS),
            "token_counts": dict(_EMPTY_TOKEN_COUNTS),
            "cumulative_tokens": dict(_EMPTY_TOKEN_COUNTS),
            "turn_count": 0,
        }
        return "", list(DEFAULT_CHAT_HISTORY), list(DEFAULT_CHAT_HISTORY), empty_metrics
    new_chat_btn.click(
        _new_chat,
        outputs=[active_conv_id, chatbot, chat_history, turn_metrics],
        api_visibility="private",
    )

    # --- Chat send ---
    _send_inputs = [
        chat_input, chat_history, active_conv_id,
        provider_state, model_state,
        temperature_state, top_p_state, max_tokens_state,
        system_append_state, turn_metrics,
    ]
    _send_outputs = [
        chatbot, chat_history, chat_input,
        active_conv_id, turn_metrics,
    ]

    chat_input.submit(
        _handle_send, inputs=_send_inputs, outputs=_send_outputs,
        api_visibility="private",
    )

    # --- Session config changes → state only (no DB writes) ---
    def _on_provider_change(provider):
        """Update session provider — refresh model list but don't persist."""
        preset = PROVIDER_PRESETS.get(provider, {})
        if provider == "ollama":
            models = fetch_ollama_models() or [preset.get("default_model", "")]
        else:
            models = preset.get("models", [])
        default_model = models[0] if models else preset.get("default_model", "")
        return gr.Dropdown(choices=models, value=default_model), provider, default_model

    cfg_provider.change(
        _on_provider_change, inputs=[cfg_provider],
        outputs=[cfg_model, provider_state, model_state],
        api_visibility="private",
    )
    cfg_model.change(
        lambda m: m, inputs=[cfg_model], outputs=[model_state],
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

    # --- Settings tab: Platform defaults → persist to DB ---
    def _on_global_provider_change(provider):
        """Update global default provider — persist to DB and refresh model list."""
        set_setting("chat_provider", provider)
        preset = PROVIDER_PRESETS.get(provider, {})
        if provider == "ollama":
            models = fetch_ollama_models() or [preset.get("default_model", "")]
        else:
            models = preset.get("models", [])
        default_model = models[0] if models else preset.get("default_model", "")
        set_setting("chat_model", default_model)
        return gr.Dropdown(choices=models, value=default_model)

    global_provider.change(
        _on_global_provider_change, inputs=[global_provider],
        outputs=[global_model],
        api_visibility="private",
    )
    global_model.change(
        lambda m: set_setting("chat_model", m),
        inputs=[global_model],
        api_visibility="private",
    )
    global_temperature.change(
        lambda v: set_setting("chat_temperature", str(v)),
        inputs=[global_temperature],
        api_visibility="private",
    )
    global_top_p.change(
        lambda v: set_setting("chat_top_p", str(v)),
        inputs=[global_top_p],
        api_visibility="private",
    )
    global_max_tokens.change(
        lambda v: set_setting("chat_max_tokens", str(int(v))),
        inputs=[global_max_tokens],
        api_visibility="private",
    )
    global_system_prompt.change(
        lambda v: set_setting("chat_system_prompt", v),
        inputs=[global_system_prompt],
        api_visibility="private",
    )
    rag_threshold.change(
        lambda v: set_setting("rag_score_threshold", str(v)),
        inputs=[rag_threshold],
        api_visibility="private",
    )
    rag_max_chunks.change(
        lambda v: set_setting("rag_max_chunks", str(int(v))),
        inputs=[rag_max_chunks],
        api_visibility="private",
    )
    rag_synth_provider.change(
        lambda v: set_setting("rag_synthesizer_provider", v),
        inputs=[rag_synth_provider],
        api_visibility="private",
    )
    rag_synth_model.change(
        lambda v: set_setting("rag_synthesizer_model", v),
        inputs=[rag_synth_model],
        api_visibility="private",
    )
    rag_synth_api_key.change(
        lambda v: set_setting("rag_synthesizer_api_key", v),
        inputs=[rag_synth_api_key],
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
