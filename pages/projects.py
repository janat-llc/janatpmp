"""Projects page layout — Projects + Work tabs with contextual sidebar."""
import gradio as gr
import pandas as pd
from db.operations import (
    get_item, create_item, update_item,
    get_task, create_task, update_task,
    get_domains,
)
from shared.constants import (
    ALL_TYPES, STATUSES,
    TASK_STATUSES, TASK_TYPES, ASSIGNEES, PRIORITIES,
)
from shared.formatting import fmt_enum
from shared.data_helpers import (
    _load_projects, _children_df, _all_items_df,
    _load_tasks, _all_tasks_df,
)
from shared.chat_sidebar import build_chat_sidebar, wire_chat_sidebar
from components.kanban_board import KanbanBoard, build_board_data


def _domain_choices(include_blank: bool = True) -> list[str]:
    """Load active domain names for UI dropdowns."""
    domains = get_domains(active_only=True)
    names = [d["name"] for d in domains]
    return ([""] + names) if include_blank else names


# --- Page builder ---

def build_page():
    """Build the Projects page layout.

    Must be called from within a `with gr.Blocks():` context.
    Creates contextual left sidebar, right chat sidebar, and center tabs
    for Projects and Work.
    """
    # === STATES ===
    active_tab = gr.State("Projects")
    selected_project_id = gr.State("")
    selected_task_id = gr.State("")
    projects_state = gr.State(_load_projects())
    tasks_state = gr.State(_load_tasks())

    # === RIGHT SIDEBAR — Janat quick-chat (shared) ===
    chatbot, chat_input, chat_history, sidebar_conv_id = build_chat_sidebar()

    # === CENTER TABS (defined before left sidebar so render can reference them) ===
    with gr.Tabs(elem_id="main-tabs") as main_tabs:
        # --- Projects tab ---
        with gr.Tab("Projects", id="main-projects") as projects_tab:
            with gr.Tabs(selected="projects-list-view") as projects_sub_tabs:
                with gr.Tab("Detail", id="projects-detail"):
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
                            new_domain = gr.Dropdown(label="Domain", choices=_domain_choices(include_blank=False), value="janatpmp", scale=1)
                            new_status = gr.Dropdown(label="Status", choices=STATUSES, value="not_started", scale=1)
                        new_title = gr.Textbox(label="Title", placeholder="Project title...")
                        new_desc = gr.Textbox(label="Description", lines=3, placeholder="Optional...")
                        with gr.Row():
                            new_priority = gr.Slider(label="Priority", minimum=1, maximum=5, step=1, value=3, scale=2)
                            new_parent = gr.Textbox(label="Parent ID", placeholder="Optional...", scale=1)
                        with gr.Row():
                            create_btn = gr.Button("Create", variant="primary")
                            create_msg = gr.Textbox(show_label=False, interactive=False, scale=2)

                with gr.Tab("List View", id="projects-list-view"):
                    gr.Markdown("### All Items")
                    all_items_table = gr.DataFrame(
                        value=_all_items_df(),
                        interactive=False,
                    )
                    all_refresh_btn = gr.Button("Refresh All", variant="secondary", size="sm")

        # --- Work tab ---
        with gr.Tab("Work", id="main-work") as work_tab:
            with gr.Tabs() as work_sub_tabs:
                with gr.Tab("Detail", id="work-detail"):
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

                with gr.Tab("List View", id="work-list-view"):
                    gr.Markdown("### All Tasks")
                    all_tasks_table = gr.DataFrame(
                        value=_all_tasks_df(),
                        interactive=False,
                    )
                    work_list_refresh = gr.Button("Refresh All", variant="secondary", size="sm")

                with gr.Tab("Kanban", id="work-kanban"):
                    kanban = KanbanBoard()
                    kanban_timer = gr.Timer(30)

    # === LEFT SIDEBAR (contextual — defined after center so it can reference components) ===
    with gr.Sidebar():
        @gr.render(inputs=[active_tab, projects_state, tasks_state, selected_project_id])
        def render_left(tab, projects, tasks, sel_proj_id):
            if tab == "Projects":
                gr.Markdown("### Projects")
                with gr.Row(key="proj-filter-row"):
                    domain_filter = gr.Dropdown(
                        label="Domain", choices=_domain_choices(include_blank=True), value="",
                        key="domain-filter", scale=1, min_width=100,
                    )
                    status_filter = gr.Dropdown(
                        label="Status", choices=[""] + STATUSES, value="",
                        key="status-filter", scale=1, min_width=100,
                    )
                refresh_btn = gr.Button("Refresh", variant="secondary", size="sm", key="proj-refresh")

                # Filter archived projects from sidebar (still visible in List View)
                visible = [p for p in projects if p.get("status") != "archived"]
                if not visible:
                    gr.Markdown("*No active projects.*")
                else:
                    for p in visible:
                        is_selected = (p["id"] == sel_proj_id)
                        btn = gr.Button(
                            f"{p['title']}\n{fmt_enum(p.get('status', ''))}  ·  {fmt_enum(p.get('domain', '')).upper()}",
                            key=f"proj-{p['id'][:8]}",
                            size="sm",
                            variant="primary" if is_selected else "secondary",
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

    # === TAB TRACKING ===
    projects_tab.select(lambda: "Projects", outputs=[active_tab], api_visibility="private")
    work_tab.select(lambda: "Work", outputs=[active_tab], api_visibility="private")

    # === PROJECT EVENT WIRING ===

    def _load_detail(item_id):
        """Load item detail when selection changes — auto-switches to Detail tab."""
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
            gr.Tabs(selected="projects-detail"),
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
            projects_sub_tabs,
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

    # === KANBAN WIRING ===

    kanban_timer.tick(
        fn=lambda v: build_board_data(
            v.get("view_mode", "items") if isinstance(v, dict) else "items",
            v.get("filters") if isinstance(v, dict) else None,
        ),
        inputs=[kanban],
        outputs=[kanban],
        api_visibility="private",
    )

    def _on_kanban_select(board_val):
        """Handle card selection from Kanban — route to item or task detail."""
        if not isinstance(board_val, dict):
            return gr.skip(), gr.skip(), gr.skip(), gr.skip()
        card_id = board_val.get("selected_card", "")
        view_mode = board_val.get("view_mode", "items")
        if not card_id:
            return gr.skip(), gr.skip(), gr.skip(), gr.skip()
        if view_mode == "tasks":
            # Task detail is in Work tab — stay here, switch to Detail sub-tab
            return "", card_id, gr.Tabs(selected="work-detail"), gr.skip()
        else:
            # Item detail is in Projects tab — switch main tab to Projects
            return card_id, "", gr.skip(), gr.Tabs(selected="main-projects")

    kanban.select(
        fn=_on_kanban_select,
        inputs=[kanban],
        outputs=[selected_project_id, selected_task_id, work_sub_tabs, main_tabs],
        api_visibility="private",
    )

    # === CHAT WIRING (shared sidebar) ===
    wire_chat_sidebar(chat_input, chatbot, chat_history, sidebar_conv_id)
