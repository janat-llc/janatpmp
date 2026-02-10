"""Main page layout — contextual sidebar, center tabs, Claude chat."""
import gradio as gr
import pandas as pd
from db.operations import (
    list_items, get_item, create_item, update_item, delete_item,
    list_tasks, get_task, create_task, update_task,
)
from tabs.tab_database import build_database_tab


# --- Constants ---

PROJECT_TYPES = ["project", "epic", "book", "website", "milestone"]

DOMAINS = [
    "", "literature", "janatpmp", "janat", "atlas", "meax",
    "janatavern", "amphitheatre", "nexusweaver", "websites",
    "social", "speaking", "life"
]

ALL_TYPES = [
    "project", "epic", "feature", "component", "milestone",
    "book", "chapter", "section",
    "website", "page", "deployment",
    "social_campaign", "speaking_event", "life_area"
]

STATUSES = [
    "not_started", "planning", "in_progress", "blocked",
    "review", "completed", "shipped", "archived"
]

TASK_STATUSES = [
    "pending", "processing", "blocked", "review",
    "completed", "failed", "retry", "dlq"
]

TASK_TYPES = [
    "agent_story", "user_story", "subtask",
    "research", "review", "documentation"
]

ASSIGNEES = ["unassigned", "agent", "claude", "mat", "janus"]

PRIORITIES = ["urgent", "normal", "background"]

INITIAL_CHAT = [{
    "role": "assistant",
    "content": (
        "I'm connected with 22 database tools. "
        "Ask me to create items, update tasks, or check project status."
    ),
}]


# --- Data helpers ---

def _fmt(value: str) -> str:
    """Convert 'not_started' to 'Not Started'."""
    return value.replace("_", " ").title() if value else ""


def _load_projects(domain: str = "", status: str = "") -> list:
    """Fetch project-scope items as list of dicts for card rendering."""
    items = list_items(domain=domain, status=status, limit=100)
    return [i for i in items if i.get("entity_type") in PROJECT_TYPES]


def _children_df(parent_id: str) -> pd.DataFrame:
    """Fetch child items for a given parent."""
    children = list_items(parent_id=parent_id, limit=100)
    if not children:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": c["id"][:8],
        "Title": c["title"],
        "Type": _fmt(c["entity_type"]),
        "Status": _fmt(c["status"]),
        "Priority": c["priority"],
    } for c in children])


def _all_items_df() -> pd.DataFrame:
    """Fetch all items for the List View tab."""
    items = list_items(limit=200)
    if not items:
        return pd.DataFrame(columns=["ID", "Title", "Domain", "Type", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": item["id"][:8],
        "Title": item["title"],
        "Domain": _fmt(item.get("domain", "")),
        "Type": _fmt(item.get("entity_type", "")),
        "Status": _fmt(item.get("status", "")),
        "Priority": item.get("priority", 3),
    } for item in items])


def _load_tasks(status: str = "", assigned_to: str = "") -> list:
    """Fetch tasks as list of dicts for card rendering."""
    return list_tasks(status=status, assigned_to=assigned_to, limit=100)


def _all_tasks_df() -> pd.DataFrame:
    """Fetch all tasks for the List View."""
    tasks = list_tasks(limit=200)
    if not tasks:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Assigned", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": t["id"][:8],
        "Title": t["title"],
        "Type": _fmt(t.get("task_type", "")),
        "Assigned": _fmt(t.get("assigned_to", "")),
        "Status": _fmt(t.get("status", "")),
        "Priority": _fmt(t.get("priority", "")),
    } for t in tasks])


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
    chat_history = gr.State(list(INITIAL_CHAT))

    # === RIGHT SIDEBAR (chat — always visible) ===
    with gr.Sidebar(position="right"):
        gr.Markdown("### Claude")
        chatbot = gr.Chatbot(value=list(INITIAL_CHAT), height=500, label="Chat")
        chat_input = gr.Textbox(
            placeholder="Ask Claude anything...",
            show_label=False, interactive=True, max_lines=3,
        )

    # === CENTER TABS (defined before left sidebar so render can reference them) ===
    with gr.Tabs():
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
            gr.Markdown("### Knowledge Base")
            gr.Markdown("*Document browser coming in Phase 3.*")

        # --- Admin tab ---
        admin_components = build_database_tab()

    # === LEFT SIDEBAR (contextual — defined after center so it can reference components) ===
    with gr.Sidebar():
        @gr.render(inputs=[active_tab, projects_state, tasks_state])
        def render_left(tab, projects, tasks):
            if tab == "Projects":
                gr.Markdown("### Projects")
                with gr.Row():
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
                            f"{p['title']}\n{_fmt(p.get('status', ''))}  ·  {_fmt(p.get('entity_type', '')).upper()}",
                            key=f"proj-{p['id'][:8]}",
                            size="sm",
                        )
                        def on_card_click(p_id=p["id"]):
                            return p_id
                        btn.click(on_card_click, outputs=[selected_project_id], api_visibility="private")

                new_item_btn = gr.Button("+ New Item", variant="primary", key="new-item-btn")

                # Wiring (inside render — components created here)
                def _refresh_projects(domain, status):
                    return _load_projects(domain, status)
                domain_filter.change(_refresh_projects, inputs=[domain_filter, status_filter], outputs=[projects_state], api_visibility="private")
                status_filter.change(_refresh_projects, inputs=[domain_filter, status_filter], outputs=[projects_state], api_visibility="private")
                refresh_btn.click(_refresh_projects, inputs=[domain_filter, status_filter], outputs=[projects_state], api_visibility="private")

                new_item_btn.click(
                    lambda: ("## New Item", gr.Column(visible=False), gr.Column(visible=True)),
                    outputs=[detail_header, detail_section, create_section],
                    api_visibility="private",
                )

            elif tab == "Work":
                gr.Markdown("### Work Queue")
                with gr.Row():
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
                            f"{t['title']}\n{_fmt(t.get('status', ''))}  ·  {_fmt(t.get('assigned_to', '')).upper()}",
                            key=f"task-{t['id'][:8]}",
                            size="sm",
                        )
                        def on_task_click(t_id=t["id"]):
                            return t_id
                        btn.click(on_task_click, outputs=[selected_task_id], api_visibility="private")

                new_task_btn = gr.Button("+ New Task", variant="primary", key="new-task-btn")

                # Wiring
                def _refresh_tasks(status, assigned):
                    return _load_tasks(status, assigned)
                work_status_filter.change(_refresh_tasks, inputs=[work_status_filter, work_assignee_filter], outputs=[tasks_state], api_visibility="private")
                work_assignee_filter.change(_refresh_tasks, inputs=[work_status_filter, work_assignee_filter], outputs=[tasks_state], api_visibility="private")
                work_refresh_btn.click(_refresh_tasks, inputs=[work_status_filter, work_assignee_filter], outputs=[tasks_state], api_visibility="private")

                new_task_btn.click(
                    lambda: ("## New Task", gr.Column(visible=False), gr.Column(visible=True)),
                    outputs=[work_header, work_detail_section, work_create_section],
                    api_visibility="private",
                )

            elif tab == "Knowledge":
                gr.Markdown("### Knowledge Base")
                gr.Markdown("*Coming in Phase 3*")

            elif tab == "Admin":
                gr.Markdown("### Quick Settings")
                from services.settings import get_setting, set_setting
                from services.chat import PROVIDER_PRESETS

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
                )
                sidebar_model.change(_save_model, inputs=[sidebar_model], api_visibility="private")
                sidebar_api_key.change(_save_api_key, inputs=[sidebar_api_key], api_visibility="private")
                sidebar_base_url.change(_save_base_url, inputs=[sidebar_base_url], api_visibility="private")

    # === TAB TRACKING ===
    projects_tab.select(lambda: "Projects", outputs=[active_tab], api_visibility="private")
    work_tab.select(lambda: "Work", outputs=[active_tab], api_visibility="private")
    knowledge_tab.select(lambda: "Knowledge", outputs=[active_tab], api_visibility="private")
    admin_components['tab'].select(lambda: "Admin", outputs=[active_tab], api_visibility="private")

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
            _fmt(item.get("entity_type", "")),
            _fmt(item.get("domain", "")),
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
            _fmt(task.get("task_type", "")),
            _fmt(task.get("priority", "")),
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

    # === CHAT WIRING ===

    def _handle_chat(message, history):
        if not message.strip():
            return history, history, ""
        from services.chat import chat
        updated = chat(message, history)
        return updated, updated, ""

    chat_input.submit(
        _handle_chat,
        inputs=[chat_input, chat_history],
        outputs=[chatbot, chat_history, chat_input],
        api_visibility="private",
    )


