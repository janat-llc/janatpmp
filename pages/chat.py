"""Sovereign Chat page — standalone Gradio Blocks app for /chat route.

Three-panel layout:
- Left sidebar: RAG observability (provenance, context, rejected candidates)
- Center: Chat + Overview (charts) + Settings tabs
- Right sidebar: Session controls + session metrics (turns, latency, tokens)

Can run standalone: python pages/chat.py
"""

import json
import gradio as gr
import pandas as pd
from db.chat_operations import (
    parse_reasoning, add_message,
    add_message_metadata, update_message_metadata,
    get_or_create_janus_conversation, archive_janus_conversation,
)
from services.chat import chat, PROVIDER_PRESETS, fetch_ollama_models, _EMPTY_RAG_METRICS, _EMPTY_TOKEN_COUNTS, _sanitize_tool_call_output
from services.settings import get_setting, set_setting
from shared.constants import DEFAULT_CHAT_HISTORY
from shared.data_helpers import _load_most_recent_chat, _load_chat_session, _load_conversation_metrics, _windowed_api_history
from shared.chat_service import (
    set_active_conversation_id,
    get_chat_config,
)


# ---------------------------------------------------------------------------
# Chat handler (self-contained — does NOT import from tabs/tab_chat.py)
# ---------------------------------------------------------------------------

def _handle_send(message, history, conv_id, provider, model,
                 temperature, top_p, max_tokens, metrics):
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

    # Janus fallback — always have a conversation
    if not conv_id:
        conv_id = get_or_create_janus_conversation()

    # Update module-level active conversation pointer
    set_active_conversation_id(conv_id)

    try:
        # Apply sliding window — send only last N turns to LLM
        window = int(get_setting("janus_context_messages") or "10")
        api_window = _windowed_api_history(history, window)

        result = chat(
            message, api_window,
            provider_override=provider, model_override=model,
            temperature=temperature, top_p=top_p,
            max_tokens=int(max_tokens),
        )

        # Reconstruct full history: original + new messages from this turn
        new_messages = result["history"][len(api_window):]
        updated = list(history) + new_messages
        rag_metrics = result.get("rag_metrics", dict(_EMPTY_RAG_METRICS))
        token_counts = result.get("token_counts", dict(_EMPTY_TOKEN_COUNTS))

        # Extract final model response (skip tool-use status messages)
        raw_response = ""
        for msg in reversed(updated):
            if msg.get("role") == "assistant" and not msg.get("content", "").startswith("Using `"):
                raw_response = msg.get("content", "")
                break

        reasoning, clean_response = parse_reasoning(raw_response)

        # Sanitize hallucinated tool call syntax (XML or JSON) —
        # safety net in case models emit tool calls despite not receiving tools
        clean_response = _sanitize_tool_call_output(clean_response)

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
                system_prompt_length=result.get("system_prompt_length", 0),
                rag_context_text=rag_metrics.get("context_text", ""),
                rag_synthesized=1 if rag_metrics.get("synthesized") else 0,
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
            "system_prompt_length": result.get("system_prompt_length", 0),
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
                # Pipeline overview
                sp_len = metrics.get("system_prompt_length", 0)
                if sp_len:
                    gr.Markdown(f"System prompt: **{sp_len:,}** chars")

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

    # === RIGHT SIDEBAR — Session Parameters ===
    with gr.Sidebar(position="right"):
        gr.Markdown("### Real-time")
        archive_btn = gr.Button("Archive Chapter", variant="secondary", size="sm")
        cfg_context_window = gr.Number(
            label="LLM Context Turns",
            value=int(get_setting("janus_context_messages") or "10"),
            minimum=1, maximum=50,
            step=1, interactive=True,
            info="Recent turns sent to LLM (RAG handles the rest)",
        )
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
        gr.Markdown("---")

        @gr.render(inputs=[turn_metrics])
        def render_session_metrics(metrics):
            tc = metrics.get("turn_count", 0)
            if tc < 1:
                gr.Markdown("*No metrics yet*", key="rsm-empty")
                return

            gr.Markdown(f"**Turn {tc}**", key="rsm-turn")

            # Latency — compact single line
            timings = metrics.get("timings", {})
            total_ms = timings.get("total", 0)
            if total_ms > 0:
                rag_ms = timings.get("rag", 0)
                inf_ms = timings.get("inference", 0)
                gr.Markdown(
                    f"Latency: **{total_ms:,}** ms "
                    f"(RAG {rag_ms:,} + LLM {inf_ms:,})",
                    key="rsm-latency",
                )

            # Turn tokens — compact single line
            tok = metrics.get("token_counts", {})
            p, r, o = tok.get("prompt", 0), tok.get("reasoning", 0), tok.get("response", 0)
            gr.Markdown(
                f"Tokens: P {p:,} / R {r:,} / O {o:,}",
                key="rsm-tokens",
            )

            # Session cumulative — in accordion
            cum = metrics.get("cumulative_tokens", {})
            cum_total = cum.get("total", 0)
            if cum_total > 0:
                with gr.Accordion(f"Session: {cum_total:,} tokens", open=False):
                    gr.Markdown(
                        f"Prompt: {cum.get('prompt', 0):,}\n\n"
                        f"Reasoning: {cum.get('reasoning', 0):,}\n\n"
                        f"Response: {cum.get('response', 0):,}",
                        key="rsm-cum-detail",
                    )

    # === CENTER PANEL — Tabs: Chat + Overview + Settings ===
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

        # --- Overview Tab (Charts + Metrics Dashboard) ---
        with gr.Tab("Overview"):
            @gr.render(inputs=[turn_metrics, active_conv_id])
            def render_overview(metrics, conv_id):
                tc = metrics.get("turn_count", 0)
                if not conv_id or tc < 1:
                    gr.Markdown(
                        "*Send a message to see metrics...*\n\n"
                        "Charts will appear here after your first conversation turn, "
                        "showing RAG pipeline health, latency breakdowns, and token usage.",
                        key="overview-empty",
                    )
                    return

                # Load historical per-turn data from DB
                history = _load_conversation_metrics(conv_id)
                if len(history) < 1:
                    gr.Markdown("*No metric data available for this conversation.*", key="overview-nodata")
                    return

                df = pd.DataFrame(history)

                # --- Row 1: RAG Pipeline Health ---
                gr.Markdown("### RAG Pipeline", key="ov-rag-title")
                with gr.Row():
                    with gr.Column():
                        # RAG Funnel — retrieved vs used per turn
                        funnel_df = pd.melt(
                            df[["turn", "rag_hit_count", "rag_hits_used"]].rename(
                                columns={"rag_hit_count": "Retrieved", "rag_hits_used": "Used"}
                            ),
                            id_vars=["turn"], var_name="Stage", value_name="Count",
                        )
                        gr.BarPlot(
                            value=funnel_df, x="turn", y="Count", color="Stage",
                            title="RAG Funnel per Turn",
                            x_title="Turn", y_title="Chunks",
                            color_map={"Retrieved": "#4d4d4d", "Used": "#00FFFF"},
                            key="ov-rag-funnel",
                        )
                        gr.Markdown(
                            "*Retrieved = ANN candidates after reranking. "
                            "Used = chunks that passed the score threshold and were "
                            "injected into the prompt.*",
                            key="ov-rag-funnel-tip",
                        )
                    with gr.Column():
                        # Retrieval Quality Trend — avg rerank + salience over turns
                        quality_df = pd.melt(
                            df[["turn", "avg_rerank", "avg_salience"]].rename(
                                columns={"avg_rerank": "Rerank", "avg_salience": "Salience"}
                            ),
                            id_vars=["turn"], var_name="Score", value_name="Value",
                        )
                        gr.LinePlot(
                            value=quality_df, x="turn", y="Value", color="Score",
                            title="Retrieval Quality Trend",
                            x_title="Turn", y_title="Score (0-1)",
                            color_map={"Rerank": "#00FFFF", "Salience": "#730073"},
                            key="ov-quality-trend",
                        )
                        gr.Markdown(
                            "*Rerank = cross-encoder relevance score. "
                            "Salience = accumulated memory importance. "
                            "Rising trends = memory is learning what matters.*",
                            key="ov-quality-tip",
                        )

                # --- Row 2: Performance ---
                gr.Markdown("### Performance", key="ov-perf-title")
                with gr.Row():
                    with gr.Column():
                        # Latency breakdown — RAG vs Inference per turn
                        latency_df = pd.melt(
                            df[["turn", "latency_rag", "latency_inference"]].rename(
                                columns={"latency_rag": "RAG", "latency_inference": "Inference"}
                            ),
                            id_vars=["turn"], var_name="Phase", value_name="ms",
                        )
                        gr.BarPlot(
                            value=latency_df, x="turn", y="ms", color="Phase",
                            title="Latency Breakdown",
                            x_title="Turn", y_title="Milliseconds",
                            color_map={"RAG": "#330033", "Inference": "#00FFFF"},
                            key="ov-latency",
                        )
                        gr.Markdown(
                            "*RAG = vector search + reranking + synthesis. "
                            "Inference = LLM generation time. "
                            "Spikes in RAG may indicate complex queries or slow reranker.*",
                            key="ov-latency-tip",
                        )
                    with gr.Column():
                        # Cumulative token usage — running totals
                        cum_df = df[["turn", "tokens_prompt", "tokens_reasoning", "tokens_response"]].copy()
                        cum_df["Prompt"] = cum_df["tokens_prompt"].cumsum()
                        cum_df["Reasoning"] = cum_df["tokens_reasoning"].cumsum()
                        cum_df["Response"] = cum_df["tokens_response"].cumsum()
                        cum_melt = pd.melt(
                            cum_df[["turn", "Prompt", "Reasoning", "Response"]],
                            id_vars=["turn"], var_name="Type", value_name="Tokens",
                        )
                        gr.LinePlot(
                            value=cum_melt, x="turn", y="Tokens", color="Type",
                            title="Cumulative Token Usage",
                            x_title="Turn", y_title="Running Total",
                            color_map={"Prompt": "#808080", "Reasoning": "#730073", "Response": "#00FFFF"},
                            key="ov-cum-tokens",
                        )
                        gr.Markdown(
                            "*Prompt tokens grow as conversation history accumulates. "
                            "Steep climb = approaching context window limits. "
                            "Reasoning = how much the model 'thinks' before answering.*",
                            key="ov-cum-tip",
                        )

                # --- Row 3: Token Economy + Quality ---
                gr.Markdown("### Token Economy", key="ov-tokens-title")
                with gr.Row():
                    with gr.Column():
                        # Token distribution per turn
                        tok_df = pd.melt(
                            df[["turn", "tokens_prompt", "tokens_reasoning", "tokens_response"]].rename(
                                columns={
                                    "tokens_prompt": "Prompt",
                                    "tokens_reasoning": "Reasoning",
                                    "tokens_response": "Response",
                                }
                            ),
                            id_vars=["turn"], var_name="Type", value_name="Tokens",
                        )
                        gr.BarPlot(
                            value=tok_df, x="turn", y="Tokens", color="Type",
                            title="Token Distribution per Turn",
                            x_title="Turn", y_title="Tokens",
                            color_map={"Prompt": "#808080", "Reasoning": "#730073", "Response": "#00FFFF"},
                            key="ov-tok-dist",
                        )
                        gr.Markdown(
                            "*High reasoning ratio = the model is 'thinking hard'. "
                            "Growing prompt tokens = conversation history expanding. "
                            "P = prompt, R = reasoning/thinking, O = output/response.*",
                            key="ov-tok-tip",
                        )
                    with gr.Column():
                        # Quality score trend (from Slumber Cycle)
                        has_quality = df["quality_score"].notna().any()
                        if has_quality:
                            q_df = df[df["quality_score"].notna()][["turn", "quality_score"]].copy()
                            gr.LinePlot(
                                value=q_df, x="turn", y="quality_score",
                                title="Quality Score Trend",
                                x_title="Turn", y_title="Score (0-1)",
                                key="ov-quality-score",
                            )
                            gr.Markdown(
                                "*Slumber Cycle's async quality evaluation. "
                                "Scores reflect response relevance, coherence, "
                                "and information density. Higher = better.*",
                                key="ov-quality-score-tip",
                            )
                        else:
                            gr.Markdown(
                                "### Quality Scores\n\n"
                                "*Quality scores are populated by the Slumber Cycle "
                                "(background evaluation daemon). Scores will appear "
                                "after the system has been idle for a few minutes.*",
                                key="ov-quality-pending",
                            )

                # --- Session Summary ---
                gr.Markdown("---", key="ov-divider")
                cum = metrics.get("cumulative_tokens", {})
                tok = metrics.get("token_counts", {})
                timings = metrics.get("timings", {})
                with gr.Row():
                    with gr.Column():
                        gr.Markdown(
                            f"**Session:** {tc} turns | "
                            f"{cum.get('total', 0):,} total tokens",
                            key="ov-session-summary",
                        )
                    with gr.Column():
                        gr.Markdown(
                            f"**Last turn:** {timings.get('total', 0):,} ms | "
                            f"P {tok.get('prompt', 0):,} / R {tok.get('reasoning', 0):,} / O {tok.get('response', 0):,}",
                            key="ov-last-turn-summary",
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
            gr.Markdown("### RAG Configuration")
            rag_threshold = gr.Slider(
                label="ANN Score Threshold", minimum=0.0, maximum=1.0,
                step=0.05, value=float(get_setting("rag_score_threshold") or "0.3"),
                interactive=True,
                info="Fallback threshold when reranker unavailable",
            )
            rag_rerank_threshold = gr.Slider(
                label="Rerank Threshold", minimum=0.0, maximum=1.0,
                step=0.05, value=float(get_setting("rag_rerank_threshold") or "0.3"),
                interactive=True,
                info="Cross-encoder relevance cutoff (0-1)",
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

            gr.Markdown("---")
            gr.Markdown("### Credentials")
            gr.Markdown("*API key and base URL for the chat provider. Ollama needs no key.*")
            _current_key = get_setting("chat_api_key")
            _current_url = get_setting("chat_base_url")
            _needs_key = PROVIDER_PRESETS.get(current_provider, {}).get("needs_api_key", True)
            global_api_key = gr.Textbox(
                value=_current_key,
                label="API Key",
                type="password", interactive=True,
                placeholder="sk-ant-... or AIza...",
                visible=_needs_key,
            )
            global_base_url = gr.Textbox(
                value=_current_url,
                label="Base URL (Ollama)",
                interactive=True,
                placeholder="http://ollama:11434/v1",
                visible=(current_provider == "ollama"),
            )

            gr.Markdown("---")
            gr.Markdown("### Ollama")
            gr.Markdown("*Context window and model persistence for local inference.*")
            with gr.Row():
                global_num_ctx = gr.Number(
                    label="Context Window (num_ctx)",
                    value=int(get_setting("ollama_num_ctx")),
                    precision=0, interactive=True,
                )
                global_keep_alive = gr.Textbox(
                    label="Keep Alive",
                    value=get_setting("ollama_keep_alive"),
                    placeholder="5m", interactive=True,
                )

    # === PER-SESSION INIT (one-shot timer — loads fresh data from DB) ===
    session_load_timer = gr.Timer(value=0.5, active=True)

    def _init_session():
        """Reload most recent conversation + config from DB per session (fires once)."""
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
        # Refresh provider/model from DB so changes take effect on page refresh
        fresh_config = get_chat_config()
        fresh_provider = fresh_config["provider"]
        if fresh_provider == "ollama":
            fresh_models = fetch_ollama_models() or ["qwen3-vl:8b"]
        else:
            fresh_models = PROVIDER_PRESETS.get(fresh_provider, {}).get("models", [])
        fresh_model = fresh_config["model"]
        return (
            list(session["display_history"]),
            list(session["api_history"]),
            session["conv_id"],
            metrics,
            gr.Timer(active=False),
            gr.Dropdown(choices=["anthropic", "gemini", "ollama"], value=fresh_provider),
            gr.Dropdown(choices=fresh_models, value=fresh_model),
            fresh_provider,
            fresh_model,
        )

    session_load_timer.tick(
        _init_session,
        outputs=[chatbot, chat_history, active_conv_id, turn_metrics, session_load_timer,
                 cfg_provider, cfg_model, provider_state, model_state],
        api_visibility="private",
    )

    # === EVENT WIRING ===

    # --- Archive Chapter ---
    def _archive_chapter(conv_id):
        if not conv_id:
            return gr.skip(), gr.skip(), gr.skip(), gr.skip()
        new_id = archive_janus_conversation(conv_id)
        set_active_conversation_id(new_id)
        empty_metrics = {
            "rag_metrics": dict(_EMPTY_RAG_METRICS),
            "token_counts": dict(_EMPTY_TOKEN_COUNTS),
            "cumulative_tokens": dict(_EMPTY_TOKEN_COUNTS),
            "turn_count": 0,
        }
        return new_id, list(DEFAULT_CHAT_HISTORY), list(DEFAULT_CHAT_HISTORY), empty_metrics
    archive_btn.click(
        _archive_chapter,
        inputs=[active_conv_id],
        outputs=[active_conv_id, chatbot, chat_history, turn_metrics],
        api_visibility="private",
    )

    # --- Chat send ---
    _send_inputs = [
        chat_input, chat_history, active_conv_id,
        provider_state, model_state,
        temperature_state, top_p_state, max_tokens_state,
        turn_metrics,
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
    cfg_context_window.change(
        lambda v: set_setting("janus_context_messages", str(int(v))),
        inputs=[cfg_context_window],
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
        return (
            gr.Dropdown(choices=models, value=default_model),
            gr.Textbox(visible=preset.get("needs_api_key", True)),
            gr.Textbox(visible=(provider == "ollama")),
        )

    global_provider.change(
        _on_global_provider_change, inputs=[global_provider],
        outputs=[global_model, global_api_key, global_base_url],
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
    rag_threshold.change(
        lambda v: set_setting("rag_score_threshold", str(v)),
        inputs=[rag_threshold],
        api_visibility="private",
    )
    rag_rerank_threshold.change(
        lambda v: set_setting("rag_rerank_threshold", str(v)),
        inputs=[rag_rerank_threshold],
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
    global_api_key.change(
        lambda v: set_setting("chat_api_key", v),
        inputs=[global_api_key],
        api_visibility="private",
    )
    global_base_url.change(
        lambda v: set_setting("chat_base_url", v),
        inputs=[global_base_url],
        api_visibility="private",
    )
    global_num_ctx.change(
        lambda v: set_setting("ollama_num_ctx", str(int(v))),
        inputs=[global_num_ctx],
        api_visibility="private",
    )
    global_keep_alive.change(
        lambda v: set_setting("ollama_keep_alive", v.strip()),
        inputs=[global_keep_alive],
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
