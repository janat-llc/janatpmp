"""Main page layout — left sidebar, right sidebar, center tabs."""
import gradio as gr
import pandas as pd
from db.operations import (
    list_items, get_item, create_item, update_item, delete_item,
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


# --- Page builder ---

def build_page():
    """Build the complete JANATPMP single-page layout.

    Must be called from within a `with gr.Blocks():` context.
    Creates left sidebar, right sidebar, and center tabs with all event wiring.
    """
    # State
    selected_id = gr.State("")
    projects_state = gr.State(_load_projects())

    # ===== LEFT SIDEBAR =====
    with gr.Sidebar():
        gr.Markdown("### Projects")

        with gr.Row():
            domain_filter = gr.Dropdown(
                label="Domain", choices=DOMAINS, value="",
                scale=1, min_width=100
            )
            status_filter = gr.Dropdown(
                label="Status", choices=[""] + STATUSES, value="",
                scale=1, min_width=100
            )

        refresh_btn = gr.Button("Refresh", variant="secondary", size="sm")

        @gr.render(inputs=projects_state)
        def render_project_cards(projects):
            if not projects:
                gr.Markdown("*No projects yet.*")
                return
            for p in projects:
                btn = gr.Button(
                    f"{p['title']}\n{_fmt(p.get('status', ''))}  ·  {_fmt(p.get('entity_type', '')).upper()}",
                    key=f"proj-{p['id'][:8]}",
                    size="sm",
                )
                def on_card_click(p_id=p["id"]):
                    return p_id
                btn.click(on_card_click, outputs=[selected_id], api_visibility="private")

        new_item_btn = gr.Button("+ New Item", variant="primary")

    # ===== RIGHT SIDEBAR =====
    with gr.Sidebar(position="right"):
        gr.Markdown("### Claude")
        gr.Markdown("*Connected via MCP*")
        chatbot = gr.Chatbot(
            value=[{
                "role": "assistant",
                "content": (
                    "I'm connected via MCP with 22 tools. "
                    "Ask me to create items, update tasks, or check project status."
                ),
            }],
            height=500,
            label="Chat",
        )
        chat_input = gr.Textbox(
            placeholder="Chat coming soon...",
            label="",
            interactive=False,
        )

    # ===== CENTER CONTENT (main body) =====
    with gr.Tabs():
        with gr.Tab("Projects"):
            with gr.Tabs():
                with gr.Tab("Detail"):
                    detail_header = gr.Markdown(
                        "*Select a project from the sidebar, or create a new item.*"
                    )

                    # --- Detail view (shown when a project is selected) ---
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
                            save_msg = gr.Textbox(label="", interactive=False, scale=2)

                        gr.Markdown("#### Child Items")
                        children_table = gr.DataFrame(
                            value=pd.DataFrame(
                                columns=["ID", "Title", "Type", "Status", "Priority"]
                            ),
                            interactive=False,
                        )

                    # --- Create form (shown when "+ New Item" is clicked) ---
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
                            create_msg = gr.Textbox(label="", interactive=False, scale=2)

                with gr.Tab("List View"):
                    gr.Markdown("### All Items")
                    all_items_table = gr.DataFrame(
                        value=_all_items_df(),
                        interactive=False,
                    )
                    all_refresh_btn = gr.Button("Refresh All", variant="secondary", size="sm")

        with gr.Tab("Work"):
            gr.Markdown("### Work Queue")
            gr.Markdown("*Kanban board coming in Phase 2.*")

        with gr.Tab("Knowledge"):
            gr.Markdown("### Knowledge Base")
            gr.Markdown("*Document browser coming in Phase 3.*")

        build_database_tab()

    # ===== EVENT WIRING =====

    filter_inputs = [domain_filter, status_filter]

    def _refresh_projects(domain, status):
        return _load_projects(domain, status)

    domain_filter.change(
        _refresh_projects, inputs=filter_inputs, outputs=[projects_state],
        api_visibility="private"
    )
    status_filter.change(
        _refresh_projects, inputs=filter_inputs, outputs=[projects_state],
        api_visibility="private"
    )
    refresh_btn.click(
        _refresh_projects, inputs=filter_inputs, outputs=[projects_state],
        api_visibility="private"
    )

    # -- "+ New Item" button toggles to create form --
    def _show_create_form():
        return (
            "## New Item",
            gr.Column(visible=False),
            gr.Column(visible=True),
        )

    new_item_btn.click(
        _show_create_form,
        outputs=[detail_header, detail_section, create_section],
        api_visibility="private",
    )

    # -- Card click loads detail (hides create form) --
    def _load_detail(item_id):
        """Load item detail when selection changes."""
        if not item_id:
            return (
                "*Select a project from the sidebar, or create a new item.*",
                gr.Column(visible=False),
                gr.Column(visible=False),
                "", "", "", "", "", 3, "", "", "",
                pd.DataFrame(columns=["ID", "Title", "Type", "Status", "Priority"]),
            )

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

    selected_id.change(
        _load_detail,
        inputs=[selected_id],
        outputs=[
            detail_header, detail_section, create_section,
            detail_id_display, detail_title, detail_status,
            detail_type, detail_domain, detail_priority,
            detail_created, detail_desc, save_msg,
            children_table,
        ],
        api_visibility="private",
    )

    # -- Save changes --
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
        inputs=[selected_id, detail_title, detail_status, detail_priority, detail_desc],
        outputs=[save_msg],
        api_visibility="private",
    )

    # -- List View refresh --
    all_refresh_btn.click(
        _all_items_df, outputs=[all_items_table], api_visibility="private"
    )

    # -- Create item (auto-selects new item afterward) --
    def _on_create(entity_type, domain, title, desc, status, priority, parent_id,
                   filter_domain, filter_status):
        if not title.strip():
            return "Title is required", gr.skip(), gr.skip()
        item_id = create_item(
            entity_type=entity_type, domain=domain,
            title=title.strip(),
            description=desc.strip() if desc else "",
            status=status, priority=int(priority),
            parent_id=parent_id.strip() if parent_id else "",
        )
        return (
            f"Created {item_id[:8]}",
            _load_projects(filter_domain, filter_status),
            item_id,
        )

    create_btn.click(
        _on_create,
        inputs=[
            new_type, new_domain, new_title, new_desc,
            new_status, new_priority, new_parent,
            domain_filter, status_filter,
        ],
        outputs=[create_msg, projects_state, selected_id],
        api_visibility="private",
    )
