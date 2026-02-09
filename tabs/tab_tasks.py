"""Tasks tab -- Browse, filter, and create tasks."""
import gradio as gr
import pandas as pd
from db.operations import list_tasks, create_task


def _format_display(value: str) -> str:
    """Convert enum values like 'agent_story' to 'Agent Story'."""
    return value.replace("_", " ").title() if value else ""


def _tasks_to_df(status="", assigned="") -> pd.DataFrame:
    """Fetch tasks and return as display DataFrame."""
    tasks = list_tasks(status=status, assigned_to=assigned, limit=100)
    if not tasks:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Assigned", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": task['id'][:8],
        "Title": task['title'],
        "Type": _format_display(task['task_type']),
        "Assigned": _format_display(task['assigned_to']),
        "Status": _format_display(task['status']),
        "Priority": _format_display(task['priority'])
    } for task in tasks])


def _handle_create(task_type, title, description, assigned_to, target_item_id, priority, agent_instructions):
    """Create task, return status message + refreshed table + cleared fields."""
    if not title.strip():
        return "Title is required", _tasks_to_df(), gr.update(), gr.update(), gr.update(), gr.update()
    task_id = create_task(
        task_type=task_type,
        title=title.strip(),
        description=description.strip() if description else "",
        assigned_to=assigned_to,
        target_item_id=target_item_id.strip() if target_item_id else "",
        priority=priority,
        agent_instructions=agent_instructions.strip() if agent_instructions else ""
    )
    return (
        f"Created: {task_id[:8]}",
        _tasks_to_df(),
        gr.update(value=""),  # clear title
        gr.update(value=""),  # clear description
        gr.update(value=""),  # clear target_item_id
        gr.update(value=""),  # clear agent_instructions
    )


def build_tasks_tab():
    """Build the Tasks tab. Returns tasks_table component."""
    with gr.Tab("Tasks"):
        with gr.Row():
            # Left: Table with filters
            with gr.Column(scale=2):
                gr.Markdown("### Tasks")
                with gr.Row():
                    status_filter = gr.Dropdown(
                        label="Status",
                        choices=["", "pending", "processing", "blocked", "review",
                                 "completed", "failed", "retry", "dlq"],
                        value=""
                    )
                    assigned_filter = gr.Dropdown(
                        label="Assigned To",
                        choices=["", "agent", "claude", "mat", "janus", "unassigned"],
                        value=""
                    )
                    refresh_btn = gr.Button("Refresh", variant="secondary", size="sm")

                tasks_table = gr.DataFrame(
                    value=_tasks_to_df(),
                    interactive=False
                )

            # Right: Create form
            with gr.Column(scale=1):
                gr.Markdown("### Create Task")
                task_type = gr.Dropdown(
                    label="Type",
                    choices=["agent_story", "user_story", "subtask", "research",
                             "review", "documentation"],
                    value="user_story"
                )
                title = gr.Textbox(label="Title", placeholder="Task title...")
                description = gr.Textbox(label="Description", lines=3, placeholder="Task description...")
                assigned_to = gr.Dropdown(
                    label="Assigned To",
                    choices=["unassigned", "agent", "claude", "mat", "janus"],
                    value="unassigned"
                )
                target_item_id = gr.Textbox(label="Target Item ID", placeholder="Optional item ID...")
                priority = gr.Dropdown(
                    label="Priority",
                    choices=["urgent", "normal", "background"],
                    value="normal"
                )
                agent_instructions = gr.Textbox(label="Agent Instructions", lines=3, placeholder="Optional...")
                create_btn = gr.Button("Create Task", variant="primary")
                status_msg = gr.Textbox(label="Status", interactive=False)

        # Wiring -- auto-filter on dropdown change, Refresh for MCP changes
        filter_inputs = [status_filter, assigned_filter]
        status_filter.change(_tasks_to_df, inputs=filter_inputs, outputs=[tasks_table], api_visibility="private")
        assigned_filter.change(_tasks_to_df, inputs=filter_inputs, outputs=[tasks_table], api_visibility="private")
        refresh_btn.click(_tasks_to_df, inputs=filter_inputs, outputs=[tasks_table], api_visibility="private")
        create_btn.click(
            _handle_create,
            inputs=[task_type, title, description, assigned_to, target_item_id, priority, agent_instructions],
            outputs=[status_msg, tasks_table, title, description, target_item_id, agent_instructions],
            api_visibility="private"
        )

    return tasks_table
