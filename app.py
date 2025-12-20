import gradio as gr
import pandas as pd
from db.operations import (
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    create_relationship, get_relationships,
    get_schema_info, get_stats,
    search_items, search_documents
)


def app_interface():
    # --- Event Handlers ---
    def get_items_dataframe(domain_filter="", status_filter=""):
        """Get items as DataFrame for display."""
        items = list_items(
            domain=domain_filter if domain_filter else "",
            status=status_filter if status_filter else "",
            limit=100
        )
        if not items:
            return pd.DataFrame(columns=["Title", "Domain", "Type", "Status", "Priority"])

        data = []
        for item in items:
            data.append({
                "Title": item['title'],
                "Domain": item['domain'],
                "Type": item['entity_type'],
                "Status": item['status'],
                "Priority": item['priority']
            })
        return pd.DataFrame(data)

    def get_tasks_dataframe(status_filter=""):
        """Get tasks as DataFrame for display."""
        tasks = list_tasks(
            status=status_filter if status_filter else "",
            limit=100
        )
        if not tasks:
            return pd.DataFrame(columns=["Title", "Type", "Assigned", "Status", "Priority"])

        data = []
        for task in tasks:
            data.append({
                "Title": task['title'],
                "Type": task['task_type'],
                "Assigned": task['assigned_to'],
                "Status": task['status'],
                "Priority": task['priority']
            })
        return pd.DataFrame(data)

    def load_stats():
        """Load database statistics."""
        stats = get_stats()
        return (
            stats.get('total_items', 0),
            stats.get('total_tasks', 0),
            stats.get('total_documents', 0)
        )

    def load_items():
        return get_items_dataframe()

    def load_tasks():
        return get_tasks_dataframe()

    # --- UI Components ---
    with gr.Blocks(title="JANATPMP") as demo:
        # Header
        with gr.Row():
            gr.Markdown("# JANATPMP v0.1 Alpha")

        with gr.Row():
            # LEFT PANEL (Stats)
            with gr.Column(scale=1):
                with gr.Accordion("Stats & Observability", open=True):
                    stat_items = gr.Number(label="Total Items", value=0, interactive=False)
                    stat_tasks = gr.Number(label="Total Tasks", value=0, interactive=False)
                    stat_docs = gr.Number(label="Total Documents", value=0, interactive=False)

            # MIDDLE PANEL (Main Content)
            with gr.Column(scale=3):
                with gr.Tabs():
                    with gr.Tab("Items"):
                        gr.Markdown("### Project Items")
                        gr.Markdown("Items across all 12 domains")

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
                            filter_btn = gr.Button("Filter", variant="primary")

                        items_table = gr.DataFrame(
                            headers=["Title", "Domain", "Type", "Status", "Priority"],
                            interactive=False,
                            label="Items"
                        )

                    with gr.Tab("Tasks"):
                        gr.Markdown("### Task Queue")
                        gr.Markdown("Work items for agents and users")

                        tasks_table = gr.DataFrame(
                            headers=["Title", "Type", "Assigned", "Status", "Priority"],
                            interactive=False,
                            label="Tasks"
                        )

                    with gr.Tab("Database"):
                        gr.Markdown("# Database Operations")
                        gr.Markdown("Database tools exposed via MCP for Claude Desktop")

                        # Expose all database operations as API/MCP tools
                        gr.api(create_item)
                        gr.api(get_item)
                        gr.api(list_items)
                        gr.api(update_item)
                        gr.api(delete_item)

                        gr.api(create_task)
                        gr.api(get_task)
                        gr.api(list_tasks)
                        gr.api(update_task)

                        gr.api(create_document)
                        gr.api(get_document)
                        gr.api(list_documents)

                        gr.api(create_relationship)
                        gr.api(get_relationships)

                        gr.api(get_schema_info)
                        gr.api(get_stats)
                        gr.api(search_items)
                        gr.api(search_documents)

                        gr.Markdown("## MCP Tools Available")
                        gr.Markdown("All database operations are now accessible via Claude Desktop at:")
                        gr.Markdown("`http://localhost:7860/gradio_api/mcp/`")

            # RIGHT PANEL (Actions)
            with gr.Column(scale=1):
                with gr.Accordion("Quick Actions", open=True):
                    gr.Markdown("## Actions")
                    gr.Markdown("_Quick actions coming soon_")

                    with gr.Group():
                        gr.Button("Refresh Data")
                        gr.Button("Export Report")

        # --- Wiring ---
        filter_btn.click(
            get_items_dataframe,
            inputs=[domain_filter, status_filter],
            outputs=[items_table]
        )

        # Load initial data on app load
        demo.load(load_items, outputs=[items_table])
        demo.load(load_tasks, outputs=[tasks_table])
        demo.load(load_stats, outputs=[stat_items, stat_tasks, stat_docs])

    return demo

if __name__ == "__main__":
    demo = app_interface()
    demo.launch(mcp_server=True)
