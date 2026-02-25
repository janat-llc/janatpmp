"""Knowledge page — the memory front-end.

Sovereign page at /knowledge with 4 tabs:
  Memory      — unified conversation + document browser
  Connections — entity relationship viewer
  Pipeline    — ingestion, embedding, graph operations
  Synthesis   — placeholder for R19 Memory node review

Three-panel layout:
  Left sidebar: context/navigation per active tab
  Center: content, detail views, controls
  Right sidebar: Janus quick-chat (shared/chat_sidebar.py)

Can run standalone: python pages/knowledge.py

Deep link hook (future, not implemented):
  /knowledge?conv=abc123 → load conversation abc123 in center
  Center content is driven by selected_item_id state, which could be
  initialized from URL query params via gr.Request in a future sprint.
"""

import logging
import gradio as gr
import pandas as pd
from db.operations import (
    get_document, create_document, get_stats,
    search_items, search_documents,
    get_relationships, create_relationship,
)
from db.chat_operations import (
    list_conversations, get_messages, delete_conversation,
)
from shared.constants import DOC_TYPES, DOC_SOURCES
from shared.formatting import fmt_enum
from shared.data_helpers import _load_documents, _all_docs_df, _msgs_to_history
from shared.chat_sidebar import build_chat_sidebar, wire_chat_sidebar
from tabs.tab_knowledge import (
    _load_conv_stats, _load_conv_list,
    _run_search, _lookup_connections, _on_conn_create,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _browse_memory(type_filter, search_query):
    """Load memory items based on type filter and optional search query.

    Returns list of dicts with keys: id, title, kind, source, date, snippet.
    """
    results = []

    if search_query and search_query.strip():
        q = search_query.strip()
        # FTS search across items and documents
        if type_filter in ("All", "Documents"):
            try:
                docs = search_documents(q, limit=30)
                for d in docs:
                    results.append({
                        "id": d["id"], "kind": "document",
                        "title": d.get("title", "Untitled"),
                        "source": fmt_enum(d.get("doc_type", "")),
                        "date": (d.get("created_at") or "")[:16],
                        "snippet": (d.get("content") or "")[:120],
                    })
            except Exception as e:
                logger.warning("Document search failed: %s", e)

        if type_filter in ("All", "Conversations"):
            try:
                from db.chat_operations import search_conversations
                convs = search_conversations(q, limit=30)
                for c in convs:
                    results.append({
                        "id": c["id"], "kind": "conversation",
                        "title": c.get("title", "Untitled"),
                        "source": fmt_enum(c.get("source", "")),
                        "date": (c.get("updated_at") or "")[:16],
                        "snippet": f"{c.get('message_count', 0)} messages",
                    })
            except Exception as e:
                logger.warning("Conversation search failed: %s", e)
    else:
        # Browse mode — recent items
        if type_filter in ("All", "Conversations"):
            try:
                convs = list_conversations(limit=50, active_only=False)
                for c in convs:
                    results.append({
                        "id": c["id"], "kind": "conversation",
                        "title": c.get("title", "Untitled"),
                        "source": fmt_enum(c.get("source", "")),
                        "date": (c.get("updated_at") or "")[:16],
                        "snippet": f"{c.get('message_count', 0)} messages",
                    })
            except Exception as e:
                logger.warning("Conversation list failed: %s", e)

        if type_filter in ("All", "Documents"):
            try:
                docs = _load_documents()
                for d in docs:
                    results.append({
                        "id": d["id"], "kind": "document",
                        "title": d.get("title", "Untitled"),
                        "source": fmt_enum(d.get("doc_type", "")),
                        "date": (d.get("created_at") or "")[:16],
                        "snippet": (d.get("content") or "")[:120],
                    })
            except Exception as e:
                logger.warning("Document list failed: %s", e)

    # Sort by date descending
    results.sort(key=lambda r: r.get("date", ""), reverse=True)
    return results


def _load_pipeline_health():
    """Load pipeline health stats for the Pipeline tab sidebar."""
    health = {}
    try:
        stats = get_stats()
        health["conversations"] = stats.get("conversations", 0)
        health["documents"] = stats.get("total_documents", 0)
        health["messages"] = stats.get("messages", 0)
    except Exception:
        health["conversations"] = health["documents"] = health["messages"] = 0

    try:
        from db.operations import get_connection
        with get_connection() as conn:
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            embedded_count = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE embedded_at IS NOT NULL"
            ).fetchone()[0]
        health["chunks_total"] = chunk_count
        health["chunks_embedded"] = embedded_count
    except Exception:
        health["chunks_total"] = health["chunks_embedded"] = 0

    try:
        from db.file_registry_ops import get_file_registry_stats
        reg_stats = get_file_registry_stats()
        health["files_tracked"] = reg_stats.get("total_files", 0)
    except Exception:
        health["files_tracked"] = 0

    try:
        from graph.graph_service import graph_stats
        g = graph_stats()
        health["graph_nodes"] = g.get("total_nodes", 0)
        health["graph_edges"] = g.get("total_relationships", 0)
    except Exception:
        health["graph_nodes"] = health["graph_edges"] = 0

    return health


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def build_knowledge_page():
    """Build the sovereign Knowledge page layout. Call inside a gr.Blocks context."""

    # === STATES ===
    active_tab = gr.State("Memory")
    selected_item_id = gr.State("")
    selected_item_type = gr.State("")  # "conversation" or "document"
    memory_items_state = gr.State([])
    pipeline_health_state = gr.State({})
    slumber_status_state = gr.State({})
    slumber_timer = gr.Timer(value=10.0, active=True)

    # === RIGHT SIDEBAR (Janus quick-chat) ===
    chatbot, chat_input, chat_history, sidebar_conv_id = build_chat_sidebar()

    # === CENTER TABS ===
    with gr.Tabs(elem_id="knowledge-tabs") as knowledge_tabs:

        # ---------------------------------------------------------------
        # TAB 1: Memory (unified conversation + document browser)
        # ---------------------------------------------------------------
        with gr.Tab("Memory") as memory_tab:
            with gr.Row():
                # --- Left panel: browse/search ---
                with gr.Column(scale=1, min_width=300):
                    gr.Markdown("### Browse Memory")
                    mem_type_filter = gr.Dropdown(
                        label="Type",
                        choices=["All", "Conversations", "Documents"],
                        value="All", interactive=True,
                    )
                    mem_search_input = gr.Textbox(
                        label="Search",
                        placeholder="Search conversations and documents...",
                        interactive=True,
                    )
                    mem_search_btn = gr.Button("Search", variant="primary", size="sm")
                    mem_result_list = gr.DataFrame(
                        headers=["Title", "Type", "Source", "Date", "ID"],
                        datatype=["str", "str", "str", "str", "str"],
                        interactive=False,
                        wrap=True,
                        label="Results",
                    )

                # --- Right panel: detail view ---
                with gr.Column(scale=2):
                    mem_detail_header = gr.Markdown(
                        "*Select a conversation or document from the left to view it.*"
                    )

                    # Conversation viewer
                    with gr.Column(visible=False) as mem_conv_section:
                        mem_conv_viewer = gr.Chatbot(
                            label="Conversation",
                            height=500,
                        )
                        with gr.Row():
                            mem_conv_delete_btn = gr.Button(
                                "Delete Conversation", variant="stop", size="sm"
                            )
                            mem_conv_status = gr.Textbox(
                                show_label=False, interactive=False, scale=2
                            )

                    # Document viewer
                    with gr.Column(visible=False) as mem_doc_section:
                        with gr.Row():
                            mem_doc_title = gr.Textbox(
                                label="Title", interactive=False, scale=3
                            )
                            mem_doc_type = gr.Textbox(
                                label="Type", interactive=False, scale=1
                            )
                            mem_doc_source = gr.Textbox(
                                label="Source", interactive=False, scale=1
                            )
                        mem_doc_content = gr.Textbox(
                            label="Content", lines=15, interactive=False,
                        )
                        with gr.Accordion("Metadata", open=False):
                            with gr.Row():
                                mem_doc_id = gr.Textbox(
                                    label="ID", interactive=False
                                )
                                mem_doc_path = gr.Textbox(
                                    label="File Path", interactive=False
                                )
                                mem_doc_created = gr.Textbox(
                                    label="Created", interactive=False
                                )

                    # Document creation form
                    with gr.Accordion("+ New Document", open=False):
                        with gr.Row():
                            new_doc_type = gr.Dropdown(
                                label="Type", choices=DOC_TYPES,
                                value="session_notes", scale=1
                            )
                            new_doc_source = gr.Dropdown(
                                label="Source", choices=DOC_SOURCES,
                                value="manual", scale=1
                            )
                        new_doc_title = gr.Textbox(
                            label="Title", placeholder="Document title..."
                        )
                        new_doc_content = gr.Textbox(
                            label="Content", lines=8,
                            placeholder="Document content..."
                        )
                        with gr.Row():
                            doc_create_btn = gr.Button("Create", variant="primary")
                            doc_create_msg = gr.Textbox(
                                show_label=False, interactive=False, scale=2
                            )

        # ---------------------------------------------------------------
        # TAB 2: Connections
        # ---------------------------------------------------------------
        with gr.Tab("Connections") as connections_tab:
            with gr.Row():
                # --- Left panel: filters ---
                with gr.Column(scale=1, min_width=280):
                    gr.Markdown("### Entity Connections")
                    conn_entity_type = gr.Dropdown(
                        choices=["item", "task", "document", "conversation"],
                        value="item", label="Entity Type",
                    )
                    conn_entity_id = gr.Textbox(
                        label="Entity ID",
                        placeholder="Paste full ID or 8-char prefix...",
                    )
                    conn_lookup_btn = gr.Button("Look Up", variant="primary")

                # --- Right panel: results ---
                with gr.Column(scale=2):
                    connections_table = gr.DataFrame(
                        value=pd.DataFrame(
                            columns=[
                                "Relationship", "Direction",
                                "Connected Type", "Connected ID", "Strength"
                            ]
                        ),
                        label="Connections",
                        interactive=False,
                    )
                    with gr.Accordion("+ Add Connection", open=False):
                        with gr.Row():
                            conn_target_type = gr.Dropdown(
                                choices=["item", "task", "document"],
                                value="item", label="Target Type", scale=1
                            )
                            conn_target_id = gr.Textbox(
                                label="Target ID",
                                placeholder="Target entity ID...",
                                scale=2,
                            )
                        conn_rel_type = gr.Dropdown(
                            choices=[
                                "blocks", "enables", "informs", "references",
                                "implements", "documents", "depends_on",
                                "parent_of", "attached_to"
                            ],
                            value="references", label="Relationship Type",
                        )
                        with gr.Row():
                            conn_create_btn = gr.Button(
                                "Create Connection", variant="primary"
                            )
                            conn_create_msg = gr.Textbox(
                                show_label=False, interactive=False, scale=2
                            )

        # ---------------------------------------------------------------
        # TAB 3: Pipeline (ingestion, embedding, graph)
        # ---------------------------------------------------------------
        with gr.Tab("Pipeline") as pipeline_tab:
            with gr.Row():
                # --- Left panel: health summary ---
                with gr.Column(scale=1, min_width=280):
                    gr.Markdown("### Pipeline Health")
                    pipeline_health_display = gr.JSON(
                        label="Status", value={}
                    )
                    pipeline_refresh_btn = gr.Button(
                        "Refresh Stats", variant="secondary", size="sm"
                    )

                # --- Right panel: controls ---
                with gr.Column(scale=2):
                    # Ingestion section
                    with gr.Accordion("Content Ingestion", open=True):
                        gr.Markdown(
                            "Import conversations and documents from external sources."
                        )
                        from services.settings import get_setting as _get_setting
                        ingestion_claude_dir = gr.Textbox(
                            label="Claude Export Directory",
                            value=_get_setting("claude_export_json_dir"),
                            placeholder="/app/imports/claude",
                            interactive=True,
                        )
                        ingestion_google_dir = gr.Textbox(
                            label="Google AI Studio Directory",
                            value=_get_setting("ingestion_google_ai_dir"),
                            placeholder="/app/imports/google_ai",
                            interactive=True,
                        )
                        ingestion_markdown_dir = gr.Textbox(
                            label="Markdown / Text Directory",
                            value=_get_setting("ingestion_markdown_dir"),
                            placeholder="/app/imports/markdown",
                            interactive=True,
                        )
                        with gr.Row():
                            save_ingestion_btn = gr.Button(
                                "Save Paths", variant="primary"
                            )
                            ingestion_save_status = gr.Textbox(
                                show_label=False, interactive=False, scale=2
                            )

                        gr.Markdown("---")
                        gr.Markdown("#### Run Ingestion")
                        with gr.Row():
                            ingest_claude_btn = gr.Button(
                                "Ingest Claude", variant="primary"
                            )
                            ingest_google_btn = gr.Button(
                                "Ingest Google AI", variant="primary"
                            )
                            ingest_markdown_btn = gr.Button(
                                "Ingest Markdown/Text", variant="primary"
                            )
                        ingestion_result = gr.JSON(
                            label="Ingestion Results", value={}
                        )

                        gr.Markdown("---")
                        gr.Markdown("#### Auto-Ingestion")
                        scan_btn = gr.Button(
                            "Scan & Ingest Now", variant="primary"
                        )
                        scan_result = gr.JSON(label="Scan Result", value={})

                        gr.Markdown("#### File Registry")

                        def _load_registry_stats():
                            try:
                                from db.file_registry_ops import get_file_registry_stats
                                return get_file_registry_stats()
                            except Exception:
                                return {}

                        def _load_recent_files():
                            try:
                                from db.file_registry_ops import list_registered_files
                                files = list_registered_files(limit=20)
                                if not files:
                                    return pd.DataFrame()
                                return pd.DataFrame([{
                                    "filename": f["filename"],
                                    "type": f["ingestion_type"],
                                    "status": f["status"],
                                    "entities": f["entity_count"],
                                    "ingested": f["ingested_at"],
                                } for f in files])
                            except Exception:
                                return pd.DataFrame()

                        registry_stats = gr.JSON(
                            label="Registry Stats",
                            value=_load_registry_stats(),
                        )
                        registry_table = gr.DataFrame(
                            label="Recent Files",
                            value=_load_recent_files(),
                            interactive=False,
                        )

                    # Embedding section
                    with gr.Accordion("Embedding & Chunking", open=False):
                        gr.Markdown(
                            "**R16 Chunking:** Run chunking first to split long "
                            "messages/documents into focused chunks, then embed."
                        )
                        with gr.Row():
                            chunk_msgs_btn = gr.Button(
                                "Chunk All Messages", variant="secondary"
                            )
                            chunk_docs_btn = gr.Button(
                                "Chunk All Documents", variant="secondary"
                            )
                        with gr.Row():
                            embed_docs_btn = gr.Button(
                                "Embed All Documents", variant="primary"
                            )
                            embed_msgs_btn = gr.Button(
                                "Embed All Messages", variant="primary"
                            )
                        with gr.Row():
                            embed_items_btn = gr.Button(
                                "Embed All Items", variant="primary"
                            )
                            embed_tasks_btn = gr.Button(
                                "Embed All Tasks", variant="primary"
                            )
                        embed_status = gr.JSON(
                            label="Embedding / Chunking Status", value={}
                        )

                    # Graph section
                    with gr.Accordion("Knowledge Graph", open=False):
                        gr.Markdown(
                            "Neo4j knowledge graph — entity relationships, "
                            "identity graph, structural edges."
                        )
                        graph_stats_display = gr.JSON(
                            label="Graph Stats", value={}
                        )
                        with gr.Row():
                            graph_stats_btn = gr.Button(
                                "Refresh Graph Stats", variant="secondary"
                            )
                            backfill_btn = gr.Button(
                                "Backfill Graph", variant="primary"
                            )
                            seed_identity_btn = gr.Button(
                                "Seed Identity Graph", variant="primary"
                            )
                        graph_op_status = gr.JSON(
                            label="Graph Operation Result", value={}
                        )

        # ---------------------------------------------------------------
        # TAB 4: Synthesis (placeholder for R19)
        # ---------------------------------------------------------------
        with gr.Tab("Synthesis") as synthesis_tab:
            gr.Markdown("### Synthesis — Coming in R19")
            gr.Markdown(
                "Slumber Memory node review, evidence chains, source attribution.\n\n"
                "Left sidebar will show Memory nodes grouped by identity "
                "(Mat / Janus). Center will show selected memory with its "
                "evidence chain (EVIDENCED_BY edges to source messages)."
            )

    # === LEFT SIDEBAR ===
    with gr.Sidebar(position="left"):
        @gr.render(inputs=[active_tab, memory_items_state, pipeline_health_state, slumber_status_state])
        def render_left(tab, memory_items, pipeline_health, slumber_status):
            if tab == "Memory":
                gr.Markdown("### Memory Browser")
                stats_text = _load_conv_stats()
                gr.Markdown(stats_text, key="mem-stats")

                if not memory_items:
                    gr.Markdown(
                        "*Use the search box or select a type filter above "
                        "to browse memory.*",
                        key="mem-empty",
                    )
                else:
                    for item in memory_items[:50]:
                        kind_label = "Conv" if item["kind"] == "conversation" else "Doc"
                        btn = gr.Button(
                            f"{item['title'][:60]}\n{kind_label} · {item['source']} · {item['date']}",
                            key=f"mem-{item['id'][:12]}",
                            size="sm",
                        )

                        def on_item_click(
                            item_id=item["id"], item_kind=item["kind"]
                        ):
                            return item_id, item_kind

                        btn.click(
                            on_item_click,
                            outputs=[selected_item_id, selected_item_type],
                            api_visibility="private",
                            key=f"mem-click-{item['id'][:12]}",
                        )

            elif tab == "Connections":
                gr.Markdown("### Connections")
                gr.Markdown(
                    "Look up relationships for any entity. "
                    "Use the controls in the center panel.",
                    key="conn-help",
                )

            elif tab == "Pipeline":
                gr.Markdown("### Pipeline Health")
                h = pipeline_health or {}
                gr.Markdown(
                    f"**Files Tracked:** {h.get('files_tracked', 0):,}",
                    key="pipe-files",
                )
                gr.Markdown(
                    f"**Chunks:** {h.get('chunks_total', 0):,} "
                    f"({h.get('chunks_embedded', 0):,} embedded)",
                    key="pipe-chunks",
                )
                gr.Markdown(
                    f"**Graph:** {h.get('graph_nodes', 0):,} nodes, "
                    f"{h.get('graph_edges', 0):,} edges",
                    key="pipe-graph",
                )

                # Slumber Cycle status (R22: First Light)
                gr.Markdown("---", key="pipe-slumber-sep")
                gr.Markdown("### Slumber Cycle", key="pipe-slumber-hdr")
                s = slumber_status or {}
                state = s.get("state", "idle")
                if state == "idle":
                    gr.Markdown("**Status:** Idle", key="pipe-slumber-st")
                else:
                    gr.Markdown(
                        f"**Status:** {state.title()}...",
                        key="pipe-slumber-st",
                    )
                if s.get("last_cycle_at"):
                    gr.Markdown(
                        f"**Last cycle:** {s['last_cycle_at'][:19]}",
                        key="pipe-slumber-ts",
                    )
                if s.get("total_evaluated", 0) > 0:
                    method = s.get("eval_method", "heuristic")
                    gr.Markdown(
                        f"**Evaluated:** {s['total_evaluated']:,} ({method})",
                        key="pipe-slumber-ev",
                    )
                if s.get("error"):
                    gr.Markdown(
                        f"**Error:** {s['error'][:100]}",
                        key="pipe-slumber-err",
                    )

            elif tab == "Synthesis":
                gr.Markdown("### Synthesis")
                gr.Markdown(
                    "Coming in R19 — Memory node browser by identity",
                    key="synth-placeholder",
                )

    # === EVENT WIRING ===

    # --- Tab tracking ---
    memory_tab.select(
        lambda: "Memory", outputs=[active_tab], api_visibility="private"
    )
    connections_tab.select(
        lambda: "Connections", outputs=[active_tab], api_visibility="private"
    )
    pipeline_tab.select(
        lambda: "Pipeline", outputs=[active_tab], api_visibility="private"
    )
    synthesis_tab.select(
        lambda: "Synthesis", outputs=[active_tab], api_visibility="private"
    )

    # --- Memory tab: browse + search ---
    def _do_browse(type_filter, search_query):
        items = _browse_memory(type_filter, search_query)
        rows = [[
            i["title"][:60], i["kind"].title(), i["source"], i["date"], i["id"]
        ] for i in items]
        return items, rows

    mem_search_btn.click(
        _do_browse,
        inputs=[mem_type_filter, mem_search_input],
        outputs=[memory_items_state, mem_result_list],
        api_visibility="private",
    )
    mem_search_input.submit(
        _do_browse,
        inputs=[mem_type_filter, mem_search_input],
        outputs=[memory_items_state, mem_result_list],
        api_visibility="private",
    )
    mem_type_filter.change(
        _do_browse,
        inputs=[mem_type_filter, mem_search_input],
        outputs=[memory_items_state, mem_result_list],
        api_visibility="private",
    )

    # Load initial browse on page load equivalent — trigger on first render
    memory_tab.select(
        lambda: _do_browse("All", ""),
        outputs=[memory_items_state, mem_result_list],
        api_visibility="private",
    )

    # --- Memory tab: detail loading ---
    def _load_memory_detail(item_id, item_type):
        if not item_id:
            return (
                "*Select a conversation or document from the left to view it.*",
                gr.Column(visible=False), gr.Column(visible=False),
                [], "", "", "", "", "", "", "",
            )

        if item_type == "conversation":
            msgs = get_messages(item_id)
            history = _msgs_to_history(msgs)
            return (
                f"### Conversation ({len(msgs)} messages)",
                gr.Column(visible=True), gr.Column(visible=False),
                history, "", "", "", "", "", "", "",
            )
        elif item_type == "document":
            doc = get_document(item_id)
            if not doc:
                return (
                    "*Document not found.*",
                    gr.Column(visible=False), gr.Column(visible=False),
                    [], "", "", "", "", "", "", "",
                )
            return (
                f"### {doc.get('title', 'Untitled')}",
                gr.Column(visible=False), gr.Column(visible=True),
                [],
                doc.get("title", ""),
                fmt_enum(doc.get("doc_type", "")),
                fmt_enum(doc.get("source", "")),
                doc.get("content", "") or "",
                item_id,
                doc.get("file_path", "") or "",
                (doc.get("created_at") or "")[:16],
            )
        return (
            "*Unknown item type.*",
            gr.Column(visible=False), gr.Column(visible=False),
            [], "", "", "", "", "", "", "",
        )

    selected_item_id.change(
        _load_memory_detail,
        inputs=[selected_item_id, selected_item_type],
        outputs=[
            mem_detail_header,
            mem_conv_section, mem_doc_section,
            mem_conv_viewer,
            mem_doc_title, mem_doc_type, mem_doc_source,
            mem_doc_content, mem_doc_id, mem_doc_path, mem_doc_created,
        ],
        api_visibility="private",
    )

    # Also load from table row click
    def _on_result_select(evt: gr.SelectData, df):
        if evt.index:
            row = evt.index[0]
            item_id = df.iloc[row, 4]  # ID column
            item_kind = df.iloc[row, 1].lower()  # Type column
            return item_id, item_kind
        return "", ""

    mem_result_list.select(
        _on_result_select,
        inputs=[mem_result_list],
        outputs=[selected_item_id, selected_item_type],
        api_visibility="private",
    )

    # --- Memory tab: conversation delete ---
    def _delete_conv(item_id, item_type):
        if item_type != "conversation" or not item_id:
            return "Select a conversation to delete."
        delete_conversation(item_id)
        return "Conversation deleted."

    mem_conv_delete_btn.click(
        _delete_conv,
        inputs=[selected_item_id, selected_item_type],
        outputs=[mem_conv_status],
        api_visibility="private",
    )

    # --- Memory tab: document creation ---
    def _on_doc_create(doc_type, source, title, content):
        if not title.strip():
            return "Title is required"
        doc_id = create_document(
            doc_type=doc_type,
            source=source,
            title=title.strip(),
            content=content.strip() if content else "",
        )
        return f"Created document {doc_id[:8]}"

    doc_create_btn.click(
        _on_doc_create,
        inputs=[new_doc_type, new_doc_source, new_doc_title, new_doc_content],
        outputs=[doc_create_msg],
        api_visibility="private",
    )

    # --- Connections tab ---
    conn_lookup_btn.click(
        _lookup_connections,
        inputs=[conn_entity_type, conn_entity_id],
        outputs=[connections_table],
        api_visibility="private",
    )
    conn_create_btn.click(
        _on_conn_create,
        inputs=[
            conn_entity_type, conn_entity_id,
            conn_target_type, conn_target_id, conn_rel_type,
        ],
        outputs=[conn_create_msg],
        api_visibility="private",
    )

    # --- Pipeline tab: ingestion paths ---
    def _save_ingestion_paths(claude_dir, google_dir, md_dir):
        from services.settings import set_setting
        set_setting("claude_export_json_dir", claude_dir.strip())
        set_setting("ingestion_google_ai_dir", google_dir.strip())
        set_setting("ingestion_markdown_dir", md_dir.strip())
        return "Ingestion paths saved."

    save_ingestion_btn.click(
        _save_ingestion_paths,
        inputs=[ingestion_claude_dir, ingestion_google_dir, ingestion_markdown_dir],
        outputs=[ingestion_save_status],
        api_visibility="private",
    )

    # --- Pipeline tab: run ingestion ---
    def _ingest_claude(directory):
        if not directory.strip():
            return {"error": "Claude export directory is empty."}
        try:
            from services.claude_import import import_conversations_directory
            return import_conversations_directory(directory.strip())
        except Exception as e:
            return {"error": str(e)}

    def _ingest_google(directory):
        if not directory.strip():
            return {"error": "Google AI directory is empty."}
        try:
            from services.ingestion.orchestrator import ingest_google_ai_conversations
            return ingest_google_ai_conversations(directory.strip())
        except Exception as e:
            return {"error": str(e)}

    def _ingest_markdown(directory):
        if not directory.strip():
            return {"error": "Markdown directory is empty."}
        try:
            from services.ingestion.orchestrator import ingest_markdown_documents
            return ingest_markdown_documents(directory.strip())
        except Exception as e:
            return {"error": str(e)}

    ingest_claude_btn.click(
        _ingest_claude, inputs=[ingestion_claude_dir],
        outputs=[ingestion_result], api_visibility="private",
    )
    ingest_google_btn.click(
        _ingest_google, inputs=[ingestion_google_dir],
        outputs=[ingestion_result], api_visibility="private",
    )
    ingest_markdown_btn.click(
        _ingest_markdown, inputs=[ingestion_markdown_dir],
        outputs=[ingestion_result], api_visibility="private",
    )

    # --- Pipeline tab: auto-scan ---
    def _run_scan():
        try:
            from services.auto_ingest import scan_and_ingest
            return scan_and_ingest(auto_embed=True, source="manual")
        except Exception as e:
            return {"error": str(e)}

    def _refresh_registry():
        return _load_registry_stats(), _load_recent_files()

    scan_click = scan_btn.click(
        _run_scan, outputs=[scan_result], api_visibility="private",
    )
    scan_click.then(
        _refresh_registry, outputs=[registry_stats, registry_table],
        api_visibility="private",
    )

    # --- Pipeline tab: embedding ---
    def _chunk_msgs():
        try:
            from services.bulk_embed import chunk_all_messages
            return chunk_all_messages()
        except Exception as e:
            return {"error": str(e)}

    def _chunk_docs():
        try:
            from services.bulk_embed import chunk_all_documents
            return chunk_all_documents()
        except Exception as e:
            return {"error": str(e)}

    def _embed_docs():
        try:
            from services.bulk_embed import embed_all_documents
            return embed_all_documents()
        except Exception as e:
            return {"error": str(e)}

    def _embed_msgs():
        try:
            from services.bulk_embed import embed_all_messages
            return embed_all_messages()
        except Exception as e:
            return {"error": str(e)}

    def _embed_items():
        try:
            from services.bulk_embed import embed_all_items
            return embed_all_items()
        except Exception as e:
            return {"error": str(e)}

    def _embed_tasks():
        try:
            from services.bulk_embed import embed_all_tasks
            return embed_all_tasks()
        except Exception as e:
            return {"error": str(e)}

    chunk_msgs_btn.click(
        _chunk_msgs, outputs=[embed_status], api_visibility="private"
    )
    chunk_docs_btn.click(
        _chunk_docs, outputs=[embed_status], api_visibility="private"
    )
    embed_docs_btn.click(
        _embed_docs, outputs=[embed_status], api_visibility="private"
    )
    embed_msgs_btn.click(
        _embed_msgs, outputs=[embed_status], api_visibility="private"
    )
    embed_items_btn.click(
        _embed_items, outputs=[embed_status], api_visibility="private"
    )
    embed_tasks_btn.click(
        _embed_tasks, outputs=[embed_status], api_visibility="private"
    )

    # --- Pipeline tab: graph ---
    def _get_graph_stats():
        try:
            from graph.graph_service import graph_stats
            return graph_stats()
        except Exception as e:
            return {"error": str(e)}

    def _run_backfill():
        try:
            from graph.cdc_consumer import backfill_graph
            return backfill_graph()
        except Exception as e:
            return {"error": str(e)}

    def _run_seed_identity():
        try:
            from graph.cdc_consumer import seed_identity_graph
            return seed_identity_graph()
        except Exception as e:
            return {"error": str(e)}

    graph_stats_btn.click(
        _get_graph_stats, outputs=[graph_stats_display],
        api_visibility="private",
    )
    backfill_btn.click(
        _run_backfill, outputs=[graph_op_status], api_visibility="private",
    )
    seed_identity_btn.click(
        _run_seed_identity, outputs=[graph_op_status],
        api_visibility="private",
    )

    # --- Pipeline tab: health refresh ---
    def _refresh_pipeline():
        return _load_pipeline_health()

    pipeline_refresh_btn.click(
        _refresh_pipeline, outputs=[pipeline_health_display],
        api_visibility="private",
    )
    pipeline_tab.select(
        _refresh_pipeline, outputs=[pipeline_health_state],
        api_visibility="private",
    )

    # === SLUMBER STATUS POLLING (R22) ===
    def _poll_slumber():
        from services.slumber import get_slumber_status
        return get_slumber_status()

    slumber_timer.tick(
        _poll_slumber, outputs=[slumber_status_state],
        api_visibility="private",
    )

    # === WIRE CHAT SIDEBAR ===
    wire_chat_sidebar(chat_input, chatbot, chat_history, sidebar_conv_id)


# ---------------------------------------------------------------------------
# Standalone testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from db.operations import init_database
    from services.settings import init_settings
    init_database()
    init_settings()

    with gr.Blocks(title="JANATPMP — Knowledge") as demo:
        build_knowledge_page()

    demo.launch(server_name="0.0.0.0", server_port=7862, show_error=True)
