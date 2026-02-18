"""Main page layout — contextual sidebar, center tabs, Claude chat."""
import json
import gradio as gr
import pandas as pd
from db.operations import (
    list_items, get_item, create_item, update_item, delete_item,
    list_tasks, get_task, create_task, update_task,
    list_documents, get_document, create_document,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats,
)
from tabs.tab_database import build_database_tab
from services.claude_export import (
    get_conversations as get_export_conversations,
    get_conversation_messages,
    get_export_stats,
    ingest_from_directory,
    is_configured as is_export_configured,
)
from services.settings import get_setting, set_setting
from services.chat import PROVIDER_PRESETS
from db.chat_operations import (
    create_conversation, get_conversation, list_conversations,
    update_conversation, delete_conversation, add_message, get_messages,
    parse_reasoning, search_conversations,
)
from services.claude_import import import_conversations_json
from shared.constants import (
    PROJECT_TYPES, DOMAINS, ALL_TYPES, STATUSES,
    TASK_STATUSES, TASK_TYPES, ASSIGNEES, PRIORITIES,
    DOC_TYPES, DOC_SOURCES, DEFAULT_CHAT_HISTORY,
)
from shared.formatting import fmt_enum, entity_list_to_df


# --- Data helpers ---


def _load_projects(domain: str = "", status: str = "") -> list:
    """Fetch project-scope items as list of dicts for card rendering."""
    items = list_items(domain=domain, status=status, limit=100)
    return [i for i in items if i.get("entity_type") in PROJECT_TYPES]


def _children_df(parent_id: str) -> pd.DataFrame:
    """Fetch child items for a given parent."""
    children = list_items(parent_id=parent_id, limit=100)
    return entity_list_to_df(children, [
        ("ID", "id:id"), ("Title", "title"), ("Type", "fmt:entity_type"),
        ("Status", "fmt:status"), ("Priority", "priority"),
    ])


def _all_items_df() -> pd.DataFrame:
    """Fetch all items for the List View tab."""
    items = list_items(limit=200)
    return entity_list_to_df(items, [
        ("ID", "id:id"), ("Title", "title"), ("Domain", "fmt:domain"),
        ("Type", "fmt:entity_type"), ("Status", "fmt:status"), ("Priority", "priority"),
    ])


def _load_tasks(status: str = "", assigned_to: str = "") -> list:
    """Fetch tasks as list of dicts for card rendering."""
    return list_tasks(status=status, assigned_to=assigned_to, limit=100)


def _all_tasks_df() -> pd.DataFrame:
    """Fetch all tasks for the List View."""
    tasks = list_tasks(limit=200)
    return entity_list_to_df(tasks, [
        ("ID", "id:id"), ("Title", "title"), ("Type", "fmt:task_type"),
        ("Assigned", "fmt:assigned_to"), ("Status", "fmt:status"), ("Priority", "fmt:priority"),
    ])


def _load_documents(doc_type: str = "", source: str = "") -> list:
    """Fetch documents as list of dicts for sidebar card rendering."""
    return list_documents(doc_type=doc_type, source=source, limit=100)


def _all_docs_df() -> pd.DataFrame:
    """Fetch all documents for the List View."""
    docs = list_documents(limit=200)
    return entity_list_to_df(docs, [
        ("ID", "id:id"), ("Title", "title"), ("Type", "fmt:doc_type"),
        ("Source", "fmt:source"), ("Created", "date:created_at"),
    ])


def _msgs_to_history(msgs: list[dict]) -> list[dict]:
    """Convert DB message rows to chat display history with reasoning."""
    history = []
    for m in msgs:
        history.append({"role": "user", "content": m["user_prompt"]})
        resp = m.get("model_response", "")
        reasoning = m.get("model_reasoning", "")
        if resp:
            if reasoning:
                formatted = (
                    f"<details><summary>Thinking</summary>\n\n"
                    f"{reasoning}\n\n</details>\n\n{resp}"
                )
                history.append({"role": "assistant", "content": formatted})
            else:
                history.append({"role": "assistant", "content": resp})
    return history


def _load_most_recent_chat() -> tuple[str, list[dict]]:
    """Load most recent conversation for Chat tab initialization."""
    convs = list_conversations(limit=1)
    if not convs:
        return "", list(DEFAULT_CHAT_HISTORY)
    conv_id = convs[0]["id"]
    msgs = get_messages(conv_id)
    if not msgs:
        return conv_id, list(DEFAULT_CHAT_HISTORY)
    history = _msgs_to_history(msgs)
    return conv_id, history if history else list(DEFAULT_CHAT_HISTORY)


# --- Page builder ---

def build_page():
    """Build the complete JANATPMP single-page layout.

    Must be called from within a `with gr.Blocks():` context.
    Creates contextual left sidebar, right chat sidebar, and center tabs.
    """
    # === STATES ===
    active_tab = gr.State("Projects")
    selected_project_id = gr.State("")
    selected_task_id = gr.State("")
    projects_state = gr.State(_load_projects())
    tasks_state = gr.State(_load_tasks())
    selected_doc_id = gr.State("")
    docs_state = gr.State(_load_documents())
    _initial_conv_id, _initial_chat_history = _load_most_recent_chat()
    chat_history = gr.State(list(_initial_chat_history))
    chat_tab_history = gr.State(_initial_chat_history)
    active_conversation_id = gr.State(_initial_conv_id)
    conversations_state = gr.State(list_conversations(limit=30))
    conv_search_query = gr.State("")
    selected_knowledge_conv_id = gr.State("")
    chat_tab_provider_state = gr.State("ollama")
    chat_tab_model_state = gr.State(PROVIDER_PRESETS.get("ollama", {}).get("default_model", "nemotron-3-nano:latest"))
    chat_tab_temperature = gr.State(0.7)
    chat_tab_top_p = gr.State(0.9)
    chat_tab_max_tokens = gr.State(8192)
    chat_tab_system_append = gr.State("")

    # === RIGHT SIDEBAR (conditional — Janat chat or Chat Settings) ===
    with gr.Sidebar(position="right"):
        # Section A: Janat quick-chat (visible on all tabs except Chat)
        with gr.Column() as right_chat_section:
            gr.Markdown("### Janat")
            chatbot = gr.Chatbot(
                value=list(_initial_chat_history), height=500,
                show_label=False, buttons=[],
            )
            chat_input = gr.Textbox(
                placeholder="What should We do?",
                show_label=False, interactive=True, max_lines=5, lines=5,
            )
        # Section B: Chat Settings (visible only on Chat tab)
        with gr.Column(visible=False) as right_settings_section:
            gr.Markdown("### Chat Settings")
            rs_provider = gr.Dropdown(
                choices=["anthropic", "gemini", "ollama"],
                value="ollama", label="Provider", interactive=True,
            )
            rs_model = gr.Dropdown(
                choices=PROVIDER_PRESETS.get("ollama", {}).get("models", []),
                value=PROVIDER_PRESETS.get("ollama", {}).get("default_model", ""),
                label="Model", interactive=True, allow_custom_value=True,
            )
            rs_temperature = gr.Slider(
                label="Temperature", minimum=0.0, maximum=2.0,
                step=0.1, value=0.7, interactive=True,
            )
            rs_top_p = gr.Slider(
                label="Top P", minimum=0.0, maximum=1.0,
                step=0.05, value=0.9, interactive=True,
            )
            rs_max_tokens = gr.Slider(
                label="Max Tokens", minimum=256, maximum=16384,
                step=256, value=8192, interactive=True,
            )
            rs_system_append = gr.Textbox(
                label="System Prompt (session)",
                placeholder="Additional instructions for this conversation...",
                lines=3, interactive=True,
            )

    # === CENTER TABS (defined before left sidebar so render can reference them) ===
    with gr.Tabs() as main_tabs:
        # --- Projects tab ---
        with gr.Tab("Projects") as projects_tab:
            with gr.Tabs():
                with gr.Tab("Detail"):
                    detail_header = gr.Markdown(
                        "*Select a project from the sidebar, or create a new item.*"
                    )

                    with gr.Column(visible=False) as detail_section:
                        detail_id_display = gr.Textbox(
                            label="ID", interactive=False, max_lines=1
                        )
                        with gr.Row():
                            detail_title = gr.Textbox(label="Title", interactive=True, scale=3)
                            detail_status = gr.Dropdown(
                                label="Status", choices=STATUSES, interactive=True, scale=1
                            )
                            detail_priority = gr.Slider(
                                label="Priority", minimum=1, maximum=5,
                                step=1, interactive=True, scale=1
                            )
                        with gr.Row():
                            detail_type = gr.Textbox(label="Type", interactive=False)
                            detail_domain = gr.Textbox(label="Domain", interactive=False)
                            detail_created = gr.Textbox(label="Created", interactive=False)

                        detail_desc = gr.Textbox(
                            label="Description", lines=4, interactive=True
                        )

                        with gr.Row():
                            save_btn = gr.Button("Save Changes", variant="primary")
                            save_msg = gr.Textbox(show_label=False, interactive=False, scale=2)

                        gr.Markdown("#### Child Items")
                        children_table = gr.DataFrame(
                            value=pd.DataFrame(
                                columns=["ID", "Title", "Type", "Status", "Priority"]
                            ),
                            interactive=False,
                        )

                    with gr.Column(visible=False) as create_section:
                        with gr.Row():
                            new_type = gr.Dropdown(label="Type", choices=ALL_TYPES, value="project", scale=1)
                            new_domain = gr.Dropdown(label="Domain", choices=DOMAINS[1:], value="janatpmp", scale=1)
                            new_status = gr.Dropdown(label="Status", choices=STATUSES, value="not_started", scale=1)
                        new_title = gr.Textbox(label="Title", placeholder="Project title...")
                        new_desc = gr.Textbox(label="Description", lines=3, placeholder="Optional...")
                        with gr.Row():
                            new_priority = gr.Slider(label="Priority", minimum=1, maximum=5, step=1, value=3, scale=2)
                            new_parent = gr.Textbox(label="Parent ID", placeholder="Optional...", scale=1)
                        with gr.Row():
                            create_btn = gr.Button("Create", variant="primary")
                            create_msg = gr.Textbox(show_label=False, interactive=False, scale=2)

                with gr.Tab("List View"):
                    gr.Markdown("### All Items")
                    all_items_table = gr.DataFrame(
                        value=_all_items_df(),
                        interactive=False,
                    )
                    all_refresh_btn = gr.Button("Refresh All", variant="secondary", size="sm")

        # --- Work tab ---
        with gr.Tab("Work") as work_tab:
            with gr.Tabs():
                with gr.Tab("Detail"):
                    work_header = gr.Markdown(
                        "*Select a task from the sidebar, or create a new task.*"
                    )

                    with gr.Column(visible=False) as work_detail_section:
                        work_id_display = gr.Textbox(
                            label="ID", interactive=False, max_lines=1
                        )
                        with gr.Row():
                            work_title = gr.Textbox(label="Title", interactive=False, scale=3)
                            work_status = gr.Dropdown(
                                label="Status", choices=TASK_STATUSES, interactive=True, scale=1
                            )
                            work_assigned = gr.Dropdown(
                                label="Assigned To", choices=ASSIGNEES, interactive=True, scale=1
                            )
                        with gr.Row():
                            work_type = gr.Textbox(label="Type", interactive=False)
                            work_priority = gr.Textbox(label="Priority", interactive=False)
                            work_target = gr.Textbox(label="Target Item", interactive=False)

                        work_desc = gr.Textbox(
                            label="Description", lines=3, interactive=False
                        )
                        work_instructions = gr.Textbox(
                            label="Agent Instructions", lines=3, interactive=False
                        )

                        with gr.Row():
                            work_save_btn = gr.Button("Save Changes", variant="primary")
                            work_save_msg = gr.Textbox(show_label=False, interactive=False, scale=2)

                    with gr.Column(visible=False) as work_create_section:
                        with gr.Row():
                            new_task_type = gr.Dropdown(label="Type", choices=TASK_TYPES, value="user_story", scale=1)
                            new_task_assigned = gr.Dropdown(label="Assigned To", choices=ASSIGNEES, value="unassigned", scale=1)
                            new_task_priority = gr.Dropdown(label="Priority", choices=PRIORITIES, value="normal", scale=1)
                        new_task_title = gr.Textbox(label="Title", placeholder="Task title...")
                        new_task_desc = gr.Textbox(label="Description", lines=3, placeholder="Optional...")
                        new_task_target = gr.Textbox(label="Target Item ID", placeholder="Optional...")
                        new_task_instructions = gr.Textbox(label="Agent Instructions", lines=2, placeholder="Optional...")
                        with gr.Row():
                            work_create_btn = gr.Button("Create Task", variant="primary")
                            work_create_msg = gr.Textbox(show_label=False, interactive=False, scale=2)

                with gr.Tab("List View"):
                    gr.Markdown("### All Tasks")
                    all_tasks_table = gr.DataFrame(
                        value=_all_tasks_df(),
                        interactive=False,
                    )
                    work_list_refresh = gr.Button("Refresh All", variant="secondary", size="sm")

        # --- Knowledge tab ---
        with gr.Tab("Knowledge") as knowledge_tab:
            with gr.Tabs():
                # --- Documents sub-tab ---
                with gr.Tab("Documents"):
                    doc_header = gr.Markdown(
                        "*Select a document from the sidebar, or create a new one.*"
                    )

                    with gr.Column(visible=False) as doc_detail_section:
                        doc_id_display = gr.Textbox(
                            label="ID", interactive=False, max_lines=1
                        )
                        with gr.Row():
                            doc_title = gr.Textbox(
                                label="Title", interactive=True, scale=3
                            )
                            doc_type_display = gr.Textbox(
                                label="Type", interactive=False, scale=1
                            )
                            doc_source_display = gr.Textbox(
                                label="Source", interactive=False, scale=1
                            )

                        doc_content = gr.Textbox(
                            label="Content", lines=15, interactive=False,
                        )

                        with gr.Accordion("Metadata", open=False):
                            with gr.Row():
                                doc_file_path = gr.Textbox(
                                    label="File Path", interactive=False
                                )
                                doc_created = gr.Textbox(
                                    label="Created", interactive=False
                                )

                    # --- Create Document form ---
                    with gr.Column(visible=False) as doc_create_section:
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
                            label="Content", lines=10,
                            placeholder="Document content..."
                        )
                        with gr.Row():
                            doc_create_btn = gr.Button("Create", variant="primary")
                            doc_cancel_btn = gr.Button("Cancel", variant="secondary")
                            doc_create_msg = gr.Textbox(
                                show_label=False, interactive=False, scale=2
                            )

                # --- Documents List View sub-tab ---
                with gr.Tab("List View"):
                    gr.Markdown("### All Documents")
                    all_docs_table = gr.DataFrame(
                        value=_all_docs_df(), interactive=False,
                    )
                    docs_refresh_btn = gr.Button(
                        "Refresh All", variant="secondary", size="sm"
                    )

                # --- Search sub-tab ---
                with gr.Tab("Search"):
                    gr.Markdown("### Universal Search")
                    gr.Markdown("Search across all items and documents using full-text search.")
                    with gr.Row():
                        search_input = gr.Textbox(
                            label="Search Query",
                            placeholder='e.g. "consciousness" or "gradio deploy"',
                            scale=4,
                        )
                        search_btn = gr.Button("Search", variant="primary", scale=1)

                    search_items_results = gr.DataFrame(
                        value=pd.DataFrame(
                            columns=["ID", "Title", "Domain", "Type", "Status"]
                        ),
                        label="Items",
                        interactive=False,
                    )
                    search_docs_results = gr.DataFrame(
                        value=pd.DataFrame(
                            columns=["ID", "Title", "Type", "Source", "Created"]
                        ),
                        label="Documents",
                        interactive=False,
                    )

                # --- Connections sub-tab ---
                with gr.Tab("Connections"):
                    gr.Markdown("### Entity Connections")
                    gr.Markdown("View relationships for any item, task, or document.")
                    with gr.Row():
                        conn_entity_type = gr.Dropdown(
                            choices=["item", "task", "document"],
                            value="item", label="Entity Type", scale=1
                        )
                        conn_entity_id = gr.Textbox(
                            label="Entity ID",
                            placeholder="Paste full ID or 8-char prefix...",
                            scale=2,
                        )
                        conn_lookup_btn = gr.Button("Look Up", variant="primary", scale=1)
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
                            conn_create_btn = gr.Button("Create Connection", variant="primary")
                            conn_create_msg = gr.Textbox(
                                show_label=False, interactive=False, scale=2
                            )

                # --- Conversations sub-tab ---
                with gr.Tab("Conversations"):
                    conv_configured = is_export_configured()

                    if not conv_configured:
                        gr.Markdown(
                            "### Claude Export Not Configured\n\n"
                            "Set `claude_export_db_path` and `claude_export_json_dir` "
                            "in **Admin > Settings** to enable conversation browsing."
                        )

                    with gr.Row():
                        with gr.Column(scale=1):
                            # Stats
                            conv_stats_md = gr.Markdown("*Loading stats...*")

                            # Ingest controls (legacy claude_export.db)
                            with gr.Accordion("Import / Refresh", open=False):
                                gr.Markdown(
                                    "Import conversations from your Claude export JSON files. "
                                    "Uses INSERT OR REPLACE — safe to re-run."
                                )
                                conv_ingest_btn = gr.Button(
                                    "Ingest from Export Directory", variant="primary"
                                )
                                conv_ingest_status = gr.Textbox(
                                    show_label=False, interactive=False
                                )

                            # Import conversations.json into JANATPMP triplet schema
                            with gr.Accordion("Import conversations.json", open=False):
                                gr.Markdown(
                                    "Upload a Claude export `conversations.json` to import "
                                    "into JANATPMP's conversations + messages tables. "
                                    "Existing conversations (by UUID) are skipped."
                                )
                                conv_json_upload = gr.File(
                                    label="conversations.json",
                                    file_types=[".json"],
                                )
                                conv_import_btn = gr.Button(
                                    "Import to JANATPMP", variant="primary"
                                )
                                conv_import_status = gr.Textbox(
                                    show_label=False, interactive=False
                                )

                            # Conversation list (JANATPMP data)
                            gr.Markdown("### Conversations")
                            conv_list = gr.DataFrame(
                                headers=["Title", "Source", "Msgs", "Updated", "ID"],
                                datatype=["str", "str", "number", "str", "str"],
                                interactive=False,
                                wrap=True,
                            )
                            with gr.Row():
                                conv_open_chat_btn = gr.Button(
                                    "Open in Chat", variant="primary", size="sm"
                                )
                                conv_delete_btn = gr.Button(
                                    "Delete Selected", variant="stop", size="sm"
                                )
                                conv_refresh_list_btn = gr.Button(
                                    "Refresh", variant="secondary", size="sm"
                                )
                            conv_action_status = gr.Textbox(
                                show_label=False, interactive=False
                            )

                        with gr.Column(scale=2):
                            conv_viewer = gr.Chatbot(
                                label="Conversation Viewer",
                                height=600,
                            )

        # --- Chat tab ---
        with gr.Tab("Chat", id="chat") as chat_tab:
            chat_tab_chatbot = gr.Chatbot(
                value=_initial_chat_history,
                height=600,
                label="Chat",
            )
            chat_tab_input = gr.Textbox(
                placeholder="Ask anything... (Enter to send, Shift+Enter for newline)",
                show_label=False,
                interactive=True,
                max_lines=5,
            )
            chat_tab_status = gr.Markdown("*Ready*")

        # --- Admin tab ---
        admin_components = build_database_tab()

    # === LEFT SIDEBAR (contextual — defined after center so it can reference components) ===
    with gr.Sidebar():
        @gr.render(inputs=[active_tab, projects_state, tasks_state, docs_state, conversations_state, active_conversation_id, conv_search_query])
        def render_left(tab, projects, tasks, docs, conversations, active_conv_id, search_q):
            if tab == "Projects":
                gr.Markdown("### Projects")
                with gr.Row(key="proj-filter-row"):
                    domain_filter = gr.Dropdown(
                        label="Domain", choices=DOMAINS, value="",
                        key="domain-filter", scale=1, min_width=100,
                    )
                    status_filter = gr.Dropdown(
                        label="Status", choices=[""] + STATUSES, value="",
                        key="status-filter", scale=1, min_width=100,
                    )
                refresh_btn = gr.Button("Refresh", variant="secondary", size="sm", key="proj-refresh")

                if not projects:
                    gr.Markdown("*No projects yet.*")
                else:
                    for p in projects:
                        btn = gr.Button(
                            f"{p['title']}\n{fmt_enum(p.get('status', ''))}  ·  {fmt_enum(p.get('entity_type', '')).upper()}",
                            key=f"proj-{p['id'][:8]}",
                            size="sm",
                        )
                        def on_card_click(p_id=p["id"]):
                            return p_id
                        btn.click(on_card_click, outputs=[selected_project_id], api_visibility="private", key=f"proj-click-{p['id'][:8]}")

                new_item_btn = gr.Button("+ New Item", variant="primary", key="new-item-btn")

                # Wiring (inside render — components created here)
                def _refresh_projects(domain, status):
                    return _load_projects(domain, status)
                domain_filter.change(_refresh_projects, inputs=[domain_filter, status_filter], outputs=[projects_state], api_visibility="private", key="domain-filter-change")
                status_filter.change(_refresh_projects, inputs=[domain_filter, status_filter], outputs=[projects_state], api_visibility="private", key="status-filter-change")
                refresh_btn.click(_refresh_projects, inputs=[domain_filter, status_filter], outputs=[projects_state], api_visibility="private", key="proj-refresh-click")

                new_item_btn.click(
                    lambda: ("## New Item", gr.Column(visible=False), gr.Column(visible=True)),
                    outputs=[detail_header, detail_section, create_section],
                    api_visibility="private",
                    key="new-item-click",
                )

            elif tab == "Work":
                gr.Markdown("### Work Queue")
                with gr.Row(key="work-filter-row"):
                    work_status_filter = gr.Dropdown(
                        label="Status", choices=[""] + TASK_STATUSES, value="",
                        key="work-status-filter", scale=1, min_width=100,
                    )
                    work_assignee_filter = gr.Dropdown(
                        label="Assigned", choices=[""] + ASSIGNEES, value="",
                        key="work-assignee-filter", scale=1, min_width=100,
                    )
                work_refresh_btn = gr.Button("Refresh", variant="secondary", size="sm", key="work-refresh")

                if not tasks:
                    gr.Markdown("*No tasks yet.*")
                else:
                    for t in tasks:
                        btn = gr.Button(
                            f"{t['title']}\n{fmt_enum(t.get('status', ''))}  ·  {fmt_enum(t.get('assigned_to', '')).upper()}",
                            key=f"task-{t['id'][:8]}",
                            size="sm",
                        )
                        def on_task_click(t_id=t["id"]):
                            return t_id
                        btn.click(on_task_click, outputs=[selected_task_id], api_visibility="private", key=f"task-click-{t['id'][:8]}")

                new_task_btn = gr.Button("+ New Task", variant="primary", key="new-task-btn")

                # Wiring
                def _refresh_tasks(status, assigned):
                    return _load_tasks(status, assigned)
                work_status_filter.change(_refresh_tasks, inputs=[work_status_filter, work_assignee_filter], outputs=[tasks_state], api_visibility="private", key="work-status-change")
                work_assignee_filter.change(_refresh_tasks, inputs=[work_status_filter, work_assignee_filter], outputs=[tasks_state], api_visibility="private", key="work-assignee-change")
                work_refresh_btn.click(_refresh_tasks, inputs=[work_status_filter, work_assignee_filter], outputs=[tasks_state], api_visibility="private", key="work-refresh-click")

                new_task_btn.click(
                    lambda: ("## New Task", gr.Column(visible=False), gr.Column(visible=True)),
                    outputs=[work_header, work_detail_section, work_create_section],
                    api_visibility="private",
                    key="new-task-click",
                )

            elif tab == "Knowledge":
                gr.Markdown("### Documents")
                with gr.Row(key="doc-filter-row"):
                    doc_type_filter = gr.Dropdown(
                        label="Type", choices=[""] + DOC_TYPES, value="",
                        key="doc-type-filter", scale=1, min_width=100,
                    )
                    doc_source_filter = gr.Dropdown(
                        label="Source", choices=[""] + DOC_SOURCES, value="",
                        key="doc-source-filter", scale=1, min_width=100,
                    )
                docs_sidebar_refresh = gr.Button(
                    "Refresh", variant="secondary", size="sm", key="docs-refresh"
                )

                if not docs:
                    gr.Markdown("*No documents yet.*")
                else:
                    for d in docs:
                        btn = gr.Button(
                            f"{d['title']}\n{fmt_enum(d.get('doc_type', ''))}  ·  {fmt_enum(d.get('source', '')).upper()}",
                            key=f"doc-{d['id'][:8]}",
                            size="sm",
                        )
                        def on_doc_click(d_id=d["id"]):
                            return d_id
                        btn.click(
                            on_doc_click, outputs=[selected_doc_id],
                            api_visibility="private",
                            key=f"doc-click-{d['id'][:8]}",
                        )

                new_doc_btn = gr.Button(
                    "+ New Document", variant="primary", key="new-doc-btn"
                )

                # Wiring (inside render)
                def _refresh_docs(dtype, source):
                    return _load_documents(dtype, source)
                doc_type_filter.change(
                    _refresh_docs,
                    inputs=[doc_type_filter, doc_source_filter],
                    outputs=[docs_state], api_visibility="private",
                    key="doc-type-change",
                )
                doc_source_filter.change(
                    _refresh_docs,
                    inputs=[doc_type_filter, doc_source_filter],
                    outputs=[docs_state], api_visibility="private",
                    key="doc-source-change",
                )
                docs_sidebar_refresh.click(
                    _refresh_docs,
                    inputs=[doc_type_filter, doc_source_filter],
                    outputs=[docs_state], api_visibility="private",
                    key="docs-refresh-click",
                )

                new_doc_btn.click(
                    lambda: (
                        "## New Document",
                        gr.Column(visible=False),
                        gr.Column(visible=True),
                        "",                   # clear title
                        "",                   # clear content
                        "",                   # clear status message
                        "session_notes",      # reset type dropdown
                        "manual",             # reset source dropdown
                    ),
                    outputs=[
                        doc_header, doc_detail_section, doc_create_section,
                        new_doc_title, new_doc_content, doc_create_msg,
                        new_doc_type, new_doc_source,
                    ],
                    api_visibility="private",
                    key="new-doc-click",
                )

            elif tab == "Chat":
                gr.Markdown("### Conversations")
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
                        title = (conv.get('title') or 'New Chat')[:40]
                        date = (conv.get('updated_at') or '')[:10]
                        is_active = conv['id'] == active_conv_id
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

                        # Click to load conversation
                        def on_conv_click(c_id=conv["id"]):
                            msgs = get_messages(c_id)
                            history = _msgs_to_history(msgs) or list(DEFAULT_CHAT_HISTORY)
                            return c_id, history, history
                        conv_btn.click(
                            on_conv_click,
                            outputs=[active_conversation_id, chat_tab_chatbot, chat_tab_history],
                            api_visibility="private",
                            key=f"conv-click-{conv['id'][:8]}",
                        )

                        # Delete handler
                        def on_delete(c_id=conv["id"], was_active=(conv['id'] == active_conv_id)):
                            delete_conversation(c_id)
                            new_convs = list_conversations(limit=30)
                            if was_active:
                                return new_convs, "", list(DEFAULT_CHAT_HISTORY), list(DEFAULT_CHAT_HISTORY)
                            return new_convs, gr.skip(), gr.skip(), gr.skip()
                        del_btn.click(
                            on_delete,
                            outputs=[conversations_state, active_conversation_id, chat_tab_chatbot, chat_tab_history],
                            api_visibility="private",
                            key=f"del-click-{conv['id'][:8]}",
                        )

                        # Rename (only for active conversation)
                        if is_active:
                            with gr.Row(key=f"rename-{conv['id'][:8]}"):
                                rename_input = gr.Textbox(
                                    value=conv.get('title') or '',
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
                    return "", list(DEFAULT_CHAT_HISTORY), list(DEFAULT_CHAT_HISTORY), list_conversations(limit=30)
                new_chat_btn.click(
                    _new_chat,
                    outputs=[active_conversation_id, chat_tab_chatbot, chat_tab_history, conversations_state],
                    api_visibility="private",
                    key="new-chat-click",
                )

            elif tab == "Admin":
                gr.Markdown("### Quick Settings")

                current_provider = get_setting("chat_provider")
                current_model = get_setting("chat_model")
                current_key = get_setting("chat_api_key")
                current_url = get_setting("chat_base_url")

                preset = PROVIDER_PRESETS.get(current_provider, {})

                sidebar_provider = gr.Dropdown(
                    choices=["anthropic", "gemini", "ollama"],
                    value=current_provider,
                    label="Provider",
                    key="admin-provider",
                    interactive=True,
                )
                sidebar_model = gr.Dropdown(
                    choices=preset.get("models", []),
                    value=current_model,
                    label="Model",
                    key="admin-model",
                    allow_custom_value=True,
                    interactive=True,
                )
                sidebar_api_key = gr.Textbox(
                    value=current_key,
                    label="API Key",
                    type="password",
                    placeholder="sk-ant-... or AIza...",
                    key="admin-api-key",
                    interactive=True,
                    visible=preset.get("needs_api_key", True),
                )
                sidebar_base_url = gr.Textbox(
                    value=current_url,
                    label="Base URL",
                    key="admin-base-url",
                    interactive=True,
                    visible=(current_provider == "ollama"),
                )

                def _save_provider(provider):
                    set_setting("chat_provider", provider)
                    p = PROVIDER_PRESETS.get(provider, {})
                    default_model = p.get("default_model", "")
                    set_setting("chat_model", default_model)
                    return (
                        gr.Dropdown(choices=p.get("models", []), value=default_model),
                        gr.Textbox(visible=p.get("needs_api_key", True)),
                        gr.Textbox(visible=(provider == "ollama")),
                    )

                def _save_model(model):
                    set_setting("chat_model", model)

                def _save_api_key(key):
                    set_setting("chat_api_key", key)

                def _save_base_url(url):
                    set_setting("chat_base_url", url)

                sidebar_provider.change(
                    _save_provider,
                    inputs=[sidebar_provider],
                    outputs=[sidebar_model, sidebar_api_key, sidebar_base_url],
                    api_visibility="private",
                    key="admin-provider-change",
                )
                sidebar_model.change(_save_model, inputs=[sidebar_model], api_visibility="private", key="admin-model-change")
                sidebar_api_key.change(_save_api_key, inputs=[sidebar_api_key], api_visibility="private", key="admin-apikey-change")
                sidebar_base_url.change(_save_base_url, inputs=[sidebar_base_url], api_visibility="private", key="admin-baseurl-change")

    # === TAB TRACKING (with right sidebar visibility toggle) ===
    _tab_outputs = [active_tab, right_chat_section, right_settings_section]
    projects_tab.select(
        lambda: ("Projects", gr.Column(visible=True), gr.Column(visible=False)),
        outputs=_tab_outputs, api_visibility="private",
    )
    work_tab.select(
        lambda: ("Work", gr.Column(visible=True), gr.Column(visible=False)),
        outputs=_tab_outputs, api_visibility="private",
    )
    knowledge_tab.select(
        lambda: ("Knowledge", gr.Column(visible=True), gr.Column(visible=False)),
        outputs=_tab_outputs, api_visibility="private",
    )
    chat_tab.select(
        lambda: ("Chat", gr.Column(visible=False), gr.Column(visible=True)),
        outputs=_tab_outputs, api_visibility="private",
    )
    admin_components['tab'].select(
        lambda: ("Admin", gr.Column(visible=True), gr.Column(visible=False)),
        outputs=_tab_outputs, api_visibility="private",
    )

    # === RIGHT SIDEBAR SETTINGS WIRING ===
    def _rs_sync_provider(provider):
        preset = PROVIDER_PRESETS.get(provider, {})
        models = preset.get("models", [])
        default = preset.get("default_model", models[0] if models else "")
        return gr.Dropdown(choices=models, value=default), provider, default

    rs_provider.change(
        _rs_sync_provider,
        inputs=[rs_provider],
        outputs=[rs_model, chat_tab_provider_state, chat_tab_model_state],
        api_visibility="private",
    )
    rs_model.change(lambda m: m, inputs=[rs_model], outputs=[chat_tab_model_state], api_visibility="private")
    rs_temperature.change(lambda v: v, inputs=[rs_temperature], outputs=[chat_tab_temperature], api_visibility="private")
    rs_top_p.change(lambda v: v, inputs=[rs_top_p], outputs=[chat_tab_top_p], api_visibility="private")
    rs_max_tokens.change(lambda v: int(v), inputs=[rs_max_tokens], outputs=[chat_tab_max_tokens], api_visibility="private")
    rs_system_append.change(lambda v: v, inputs=[rs_system_append], outputs=[chat_tab_system_append], api_visibility="private")

    # === PROJECT EVENT WIRING ===

    def _load_detail(item_id):
        """Load item detail when selection changes."""
        if not item_id:
            return gr.skip()
        item = get_item(item_id)
        if not item:
            return gr.skip()
        return (
            f"## {item['title']}",
            gr.Column(visible=True),
            gr.Column(visible=False),
            item_id,
            item.get("title", ""),
            item.get("status", ""),
            fmt_enum(item.get("entity_type", "")),
            fmt_enum(item.get("domain", "")),
            item.get("priority", 3),
            item.get("created_at", "")[:16] if item.get("created_at") else "",
            item.get("description", "") or "",
            "",
            _children_df(item_id),
        )

    selected_project_id.change(
        _load_detail,
        inputs=[selected_project_id],
        outputs=[
            detail_header, detail_section, create_section,
            detail_id_display, detail_title, detail_status,
            detail_type, detail_domain, detail_priority,
            detail_created, detail_desc, save_msg,
            children_table,
        ],
        api_visibility="private",
    )

    def _on_save(item_id, title, status, priority, description):
        if not item_id:
            return "No item selected"
        update_item(
            item_id=item_id,
            title=title,
            status=status,
            priority=int(priority),
            description=description,
        )
        return f"Saved {item_id[:8]}"

    save_btn.click(
        _on_save,
        inputs=[selected_project_id, detail_title, detail_status, detail_priority, detail_desc],
        outputs=[save_msg],
        api_visibility="private",
    )

    all_refresh_btn.click(
        _all_items_df, outputs=[all_items_table], api_visibility="private"
    )

    def _on_create(entity_type, domain, title, desc, status, priority, parent_id):
        if not title.strip():
            return "Title is required", gr.skip(), gr.skip()
        item_id = create_item(
            entity_type=entity_type, domain=domain,
            title=title.strip(),
            description=desc.strip() if desc else "",
            status=status, priority=int(priority),
            parent_id=parent_id.strip() if parent_id else "",
        )
        return f"Created {item_id[:8]}", _load_projects(), item_id

    create_btn.click(
        _on_create,
        inputs=[new_type, new_domain, new_title, new_desc, new_status, new_priority, new_parent],
        outputs=[create_msg, projects_state, selected_project_id],
        api_visibility="private",
    )

    # === WORK EVENT WIRING ===

    def _load_task_detail(task_id):
        """Load task detail when selection changes."""
        if not task_id:
            return gr.skip()
        task = get_task(task_id)
        if not task:
            return gr.skip()
        return (
            f"## {task['title']}",
            gr.Column(visible=True),
            gr.Column(visible=False),
            task_id,
            task.get("title", ""),
            task.get("status", ""),
            task.get("assigned_to", ""),
            fmt_enum(task.get("task_type", "")),
            fmt_enum(task.get("priority", "")),
            task.get("target_item_id", "")[:8] if task.get("target_item_id") else "",
            task.get("description", "") or "",
            task.get("agent_instructions", "") or "",
            "",
        )

    selected_task_id.change(
        _load_task_detail,
        inputs=[selected_task_id],
        outputs=[
            work_header, work_detail_section, work_create_section,
            work_id_display, work_title, work_status,
            work_assigned, work_type, work_priority,
            work_target, work_desc, work_instructions,
            work_save_msg,
        ],
        api_visibility="private",
    )

    def _on_task_save(task_id, status, assigned_to):
        if not task_id:
            return "No task selected"
        update_task(task_id=task_id, status=status, assigned_to=assigned_to)
        return f"Saved {task_id[:8]}"

    work_save_btn.click(
        _on_task_save,
        inputs=[selected_task_id, work_status, work_assigned],
        outputs=[work_save_msg],
        api_visibility="private",
    )

    work_list_refresh.click(
        _all_tasks_df, outputs=[all_tasks_table], api_visibility="private"
    )

    def _on_task_create(task_type, assigned_to, priority, title, desc, target, instructions):
        if not title.strip():
            return "Title is required", gr.skip(), gr.skip()
        task_id = create_task(
            task_type=task_type,
            title=title.strip(),
            description=desc.strip() if desc else "",
            assigned_to=assigned_to,
            target_item_id=target.strip() if target else "",
            priority=priority,
            agent_instructions=instructions.strip() if instructions else "",
        )
        return f"Created {task_id[:8]}", _load_tasks(), task_id

    work_create_btn.click(
        _on_task_create,
        inputs=[
            new_task_type, new_task_assigned, new_task_priority,
            new_task_title, new_task_desc, new_task_target, new_task_instructions,
        ],
        outputs=[work_create_msg, tasks_state, selected_task_id],
        api_visibility="private",
    )

    # === KNOWLEDGE EVENT WIRING ===

    # Document detail loading
    def _load_doc_detail(doc_id):
        """Load document detail when selection changes."""
        if not doc_id:
            return gr.skip()
        doc = get_document(doc_id)
        if not doc:
            return gr.skip()
        return (
            f"## {doc['title']}",
            gr.Column(visible=True),
            gr.Column(visible=False),
            doc_id,
            doc.get("title", ""),
            fmt_enum(doc.get("doc_type", "")),
            fmt_enum(doc.get("source", "")),
            doc.get("content", "") or "",
            doc.get("file_path", "") or "",
            doc.get("created_at", "")[:16] if doc.get("created_at") else "",
        )

    selected_doc_id.change(
        _load_doc_detail,
        inputs=[selected_doc_id],
        outputs=[
            doc_header, doc_detail_section, doc_create_section,
            doc_id_display, doc_title, doc_type_display,
            doc_source_display, doc_content,
            doc_file_path, doc_created,
        ],
        api_visibility="private",
    )

    # Document creation
    def _on_doc_create(doc_type, source, title, content):
        if not title.strip():
            return "Title is required", gr.skip(), gr.skip()
        doc_id = create_document(
            doc_type=doc_type,
            source=source,
            title=title.strip(),
            content=content.strip() if content else "",
        )
        return f"Created {doc_id[:8]}", _load_documents(), doc_id

    doc_create_btn.click(
        _on_doc_create,
        inputs=[new_doc_type, new_doc_source, new_doc_title, new_doc_content],
        outputs=[doc_create_msg, docs_state, selected_doc_id],
        api_visibility="private",
    )

    # Document list refresh
    docs_refresh_btn.click(
        _all_docs_df, outputs=[all_docs_table], api_visibility="private"
    )

    # Universal search
    def _run_search(query):
        if not query or not query.strip():
            empty_items = pd.DataFrame(
                columns=["ID", "Title", "Domain", "Type", "Status"]
            )
            empty_docs = pd.DataFrame(
                columns=["ID", "Title", "Type", "Source", "Created"]
            )
            return empty_items, empty_docs

        q = query.strip()

        # Search items via FTS5
        try:
            items = search_items(q, limit=50)
        except Exception:
            items = []
        if items:
            items_df = pd.DataFrame([{
                "ID": i["id"][:8],
                "Title": i["title"],
                "Domain": fmt_enum(i.get("domain", "")),
                "Type": fmt_enum(i.get("entity_type", "")),
                "Status": fmt_enum(i.get("status", "")),
            } for i in items])
        else:
            items_df = pd.DataFrame(
                columns=["ID", "Title", "Domain", "Type", "Status"]
            )

        # Search documents via FTS5
        try:
            found_docs = search_documents(q, limit=50)
        except Exception:
            found_docs = []
        if found_docs:
            docs_df = pd.DataFrame([{
                "ID": d["id"][:8],
                "Title": d["title"],
                "Type": fmt_enum(d.get("doc_type", "")),
                "Source": fmt_enum(d.get("source", "")),
                "Created": d.get("created_at", "")[:16] if d.get("created_at") else "",
            } for d in found_docs])
        else:
            docs_df = pd.DataFrame(
                columns=["ID", "Title", "Type", "Source", "Created"]
            )

        return items_df, docs_df

    search_btn.click(
        _run_search,
        inputs=[search_input],
        outputs=[search_items_results, search_docs_results],
        api_visibility="private",
    )
    search_input.submit(
        _run_search,
        inputs=[search_input],
        outputs=[search_items_results, search_docs_results],
        api_visibility="private",
    )

    # Connections lookup
    def _lookup_connections(entity_type, entity_id):
        if not entity_id or not entity_id.strip():
            return pd.DataFrame(
                columns=["Relationship", "Direction", "Connected Type", "Connected ID", "Strength"]
            )

        eid = entity_id.strip()
        rels = get_relationships(entity_type=entity_type, entity_id=eid)

        if not rels:
            return pd.DataFrame(
                columns=["Relationship", "Direction", "Connected Type", "Connected ID", "Strength"]
            )

        rows = []
        for r in rels:
            if r["source_id"] == eid:
                rows.append({
                    "Relationship": fmt_enum(r["relationship_type"]),
                    "Direction": "-> outgoing",
                    "Connected Type": r["target_type"],
                    "Connected ID": r["target_id"][:8],
                    "Strength": r.get("strength", "hard"),
                })
            else:
                rows.append({
                    "Relationship": fmt_enum(r["relationship_type"]),
                    "Direction": "<- incoming",
                    "Connected Type": r["source_type"],
                    "Connected ID": r["source_id"][:8],
                    "Strength": r.get("strength", "hard"),
                })
        return pd.DataFrame(rows)

    conn_lookup_btn.click(
        _lookup_connections,
        inputs=[conn_entity_type, conn_entity_id],
        outputs=[connections_table],
        api_visibility="private",
    )

    # Create connection
    def _on_conn_create(source_type, source_id, target_type, target_id, rel_type):
        if not source_id.strip() or not target_id.strip():
            return "Both entity ID and target ID are required"
        try:
            rel_id = create_relationship(
                source_type=source_type,
                source_id=source_id.strip(),
                target_type=target_type,
                target_id=target_id.strip(),
                relationship_type=rel_type,
            )
            return f"Created connection {rel_id[:8]}"
        except Exception as e:
            return f"Error: {str(e)}"

    conn_create_btn.click(
        _on_conn_create,
        inputs=[
            conn_entity_type, conn_entity_id,
            conn_target_type, conn_target_id, conn_rel_type,
        ],
        outputs=[conn_create_msg],
        api_visibility="private",
    )

    # Document cancel button
    doc_cancel_btn.click(
        lambda: (
            "*Select a document from the sidebar, or create a new one.*",
            gr.Column(visible=False),   # hide detail
            gr.Column(visible=False),   # hide create form
            "",                         # clear create message
            "",                         # clear title field
            "",                         # clear content field
        ),
        outputs=[
            doc_header, doc_detail_section, doc_create_section,
            doc_create_msg, new_doc_title, new_doc_content,
        ],
        api_visibility="private",
    )

    # --- Conversations sub-tab wiring ---

    def _load_conv_stats():
        stats = get_stats()
        convs = stats.get("conversations", 0)
        msgs = stats.get("messages", 0)
        return (
            f"**{convs:,}** conversations · "
            f"**{msgs:,}** messages"
        )

    def _load_conv_list():
        convs = list_conversations(limit=500, active_only=False)
        return [[
            c.get("title", ""),
            fmt_enum(c.get("source", "")),
            c.get("message_count", 0),
            (c.get("updated_at") or "")[:16],
            c["id"],
        ] for c in convs]

    def _load_selected_conversation(evt: gr.SelectData, df):
        if evt.index:
            row = evt.index[0]
            conv_id = df.iloc[row, 4]  # ID column
            msgs = get_messages(conv_id)
            history = _msgs_to_history(msgs)
            return history, conv_id
        return [], ""

    def _run_ingest():
        json_dir = get_setting("claude_export_json_dir")
        if not json_dir:
            return "Error: claude_export_json_dir not set in Settings."
        return ingest_from_directory(json_dir)

    # Load stats and list when Knowledge tab is selected
    knowledge_tab.select(
        _load_conv_stats, outputs=[conv_stats_md], api_visibility="private"
    )
    knowledge_tab.select(
        _load_conv_list, outputs=[conv_list], api_visibility="private"
    )

    # Conversation selection -> preview in viewer + store ID
    conv_list.select(
        _load_selected_conversation, inputs=[conv_list],
        outputs=[conv_viewer, selected_knowledge_conv_id], api_visibility="private"
    )

    # Open in Chat button
    def _open_in_chat(conv_id):
        if not conv_id:
            return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), "No conversation selected."
        msgs = get_messages(conv_id)
        history = _msgs_to_history(msgs) or list(DEFAULT_CHAT_HISTORY)
        convs = list_conversations(limit=30)
        return (
            conv_id,                       # active_conversation_id
            history,                       # chat_tab_chatbot
            history,                       # chat_tab_history
            convs,                         # conversations_state
            "Chat",                        # active_tab
            gr.Tabs(selected="chat"),      # main_tabs
            "",                            # conv_action_status
        )

    conv_open_chat_btn.click(
        _open_in_chat,
        inputs=[selected_knowledge_conv_id],
        outputs=[
            active_conversation_id, chat_tab_chatbot, chat_tab_history,
            conversations_state, active_tab, main_tabs, conv_action_status,
        ],
        api_visibility="private",
    )

    # Delete selected conversation from Knowledge tab
    def _delete_knowledge_conv(conv_id):
        if not conv_id:
            return "No conversation selected.", gr.skip()
        delete_conversation(conv_id)
        convs = list_conversations(limit=30)
        return f"Deleted conversation.", convs

    conv_delete_btn.click(
        _delete_knowledge_conv,
        inputs=[selected_knowledge_conv_id],
        outputs=[conv_action_status, conversations_state],
        api_visibility="private",
    ).then(
        _load_conv_list, outputs=[conv_list], api_visibility="private"
    ).then(
        _load_conv_stats, outputs=[conv_stats_md], api_visibility="private"
    )

    # Refresh list button
    conv_refresh_list_btn.click(
        _load_conv_list, outputs=[conv_list], api_visibility="private"
    ).then(
        _load_conv_stats, outputs=[conv_stats_md], api_visibility="private"
    )

    # Ingest button
    conv_ingest_btn.click(
        _run_ingest, outputs=[conv_ingest_status], api_visibility="private"
    ).then(
        _load_conv_stats, outputs=[conv_stats_md], api_visibility="private"
    ).then(
        _load_conv_list, outputs=[conv_list], api_visibility="private"
    )

    # Import conversations.json button
    def _run_import(file):
        if file is None:
            return "No file selected.", gr.skip()
        result = import_conversations_json(file.name)
        errors = result["errors"]
        msg = (
            f"{result['imported']} conversations imported, "
            f"{result['skipped']} skipped, "
            f"{result['total_messages']} messages"
        )
        if errors:
            msg += f"\n{len(errors)} errors: {errors[0]}"
        convs = list_conversations(limit=30)
        return msg, convs

    conv_import_btn.click(
        _run_import,
        inputs=[conv_json_upload],
        outputs=[conv_import_status, conversations_state],
        api_visibility="private",
    ).then(
        _load_conv_stats, outputs=[conv_stats_md], api_visibility="private"
    ).then(
        _load_conv_list, outputs=[conv_list], api_visibility="private"
    )

    # === CHAT WIRING ===

    def _handle_chat(message, history):
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

    chat_input.submit(
        _handle_chat,
        inputs=[chat_input, chat_history],
        outputs=[chatbot, chat_history, chat_input],
        api_visibility="private",
    )

    # === CHAT TAB WIRING ===
    # Provider/model/settings are in the right sidebar when on Chat tab.
    # Sidebar components sync to chat_tab_*_state variables.
    # Handler uses override params (no temp DB setting changes).

    def _handle_chat_tab(message, history, conv_id, provider, model,
                         temperature, top_p, max_tokens, system_append):
        """Chat tab handler — persists conversations with triplet schema."""
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
                model_reasoning=reasoning,
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

    _chat_tab_inputs = [
        chat_tab_input, chat_tab_history, active_conversation_id,
        chat_tab_provider_state, chat_tab_model_state,
        chat_tab_temperature, chat_tab_top_p, chat_tab_max_tokens,
        chat_tab_system_append,
    ]
    _chat_tab_outputs = [
        chat_tab_chatbot, chat_tab_history, chat_tab_input,
        active_conversation_id, conversations_state, chat_tab_status,
    ]

    chat_tab_input.submit(
        _handle_chat_tab,
        inputs=_chat_tab_inputs,
        outputs=_chat_tab_outputs,
        api_visibility="private",
    )

