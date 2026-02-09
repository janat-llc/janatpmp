"""Items tab -- Browse, filter, and create work items."""
import gradio as gr
import pandas as pd
from db.operations import list_items, create_item


def _format_display(value: str) -> str:
    """Convert enum values like 'social_campaign' to 'Social Campaign'."""
    return value.replace("_", " ").title() if value else ""


def _items_to_df(domain="", status="") -> pd.DataFrame:
    """Fetch items and return as display DataFrame."""
    items = list_items(domain=domain, status=status, limit=100)
    if not items:
        return pd.DataFrame(columns=["ID", "Title", "Domain", "Type", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": item['id'][:8],
        "Title": item['title'],
        "Domain": _format_display(item['domain']),
        "Type": _format_display(item['entity_type']),
        "Status": _format_display(item['status']),
        "Priority": item['priority']
    } for item in items])


def _handle_create(entity_type, domain, title, description, status, priority, parent_id):
    """Create item, return status message + refreshed table + cleared fields."""
    if not title.strip():
        return "Title is required", _items_to_df(), gr.update(), gr.update(), gr.update()
    item_id = create_item(
        entity_type=entity_type, domain=domain,
        title=title.strip(),
        description=description.strip() if description else "",
        status=status, priority=int(priority),
        parent_id=parent_id.strip() if parent_id else ""
    )
    return (
        f"Created: {item_id[:8]}",
        _items_to_df(),
        gr.update(value=""),  # clear title
        gr.update(value=""),  # clear description
        gr.update(value=""),  # clear parent_id
    )


def build_items_tab():
    """Build the Items tab. Returns items_table component."""
    with gr.Tab("Items"):
        with gr.Row():
            # Left: Table with filters
            with gr.Column(scale=2):
                gr.Markdown("### Items")
                with gr.Row():
                    domain_filter = gr.Dropdown(
                        label="Domain",
                        choices=["", "literature", "janatpmp", "janat", "atlas", "meax",
                                 "janatavern", "amphitheatre", "nexusweaver", "websites",
                                 "social", "speaking", "life"],
                        value=""
                    )
                    status_filter = gr.Dropdown(
                        label="Status",
                        choices=["", "not_started", "planning", "in_progress", "blocked",
                                 "review", "completed", "shipped", "archived"],
                        value=""
                    )
                    refresh_btn = gr.Button("Refresh", variant="secondary", size="sm")

                items_table = gr.DataFrame(
                    value=_items_to_df(),
                    interactive=False
                )

            # Right: Create form
            with gr.Column(scale=1):
                gr.Markdown("### Create Item")
                entity_type = gr.Dropdown(
                    label="Type",
                    choices=["project", "epic", "feature", "component", "milestone",
                             "book", "chapter", "section",
                             "website", "page", "deployment",
                             "social_campaign", "speaking_event", "life_area"],
                    value="project"
                )
                domain = gr.Dropdown(
                    label="Domain",
                    choices=["literature", "janatpmp", "janat", "atlas", "meax",
                             "janatavern", "amphitheatre", "nexusweaver", "websites",
                             "social", "speaking", "life"],
                    value="janatpmp"
                )
                title = gr.Textbox(label="Title", placeholder="Item title...")
                description = gr.Textbox(label="Description", lines=3, placeholder="Optional...")
                status = gr.Dropdown(
                    label="Status",
                    choices=["not_started", "planning", "in_progress", "blocked",
                             "review", "completed", "shipped", "archived"],
                    value="not_started"
                )
                priority = gr.Slider(label="Priority", minimum=1, maximum=5, step=1, value=3)
                parent_id = gr.Textbox(label="Parent ID", placeholder="Optional parent...")
                create_btn = gr.Button("Create Item", variant="primary")
                status_msg = gr.Textbox(label="Status", interactive=False)

        # Wiring -- auto-filter on dropdown change, Refresh for MCP changes
        filter_inputs = [domain_filter, status_filter]
        domain_filter.change(_items_to_df, inputs=filter_inputs, outputs=[items_table], api_visibility="private")
        status_filter.change(_items_to_df, inputs=filter_inputs, outputs=[items_table], api_visibility="private")
        refresh_btn.click(_items_to_df, inputs=filter_inputs, outputs=[items_table], api_visibility="private")
        create_btn.click(
            _handle_create,
            inputs=[entity_type, domain, title, description, status, priority, parent_id],
            outputs=[status_msg, items_table, title, description, parent_id],
            api_visibility="private"
        )

    return items_table
