"""JANATPMP v1.0 — Gradio Blocks application."""

import gradio as gr
from db.operations import (
    init_database,
    # All operations exposed via gr.api() for MCP
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats, get_schema_info,
    backup_database, reset_database, restore_database, list_backups,
)
from tabs import build_items_tab, build_tasks_tab, build_documents_tab, build_database_tab

# Initialize database BEFORE building UI
init_database()

# Build the application
with gr.Blocks(title="JANATPMP") as demo:
    gr.Markdown("# JANATPMP")

    with gr.Tabs():
        items_table = build_items_tab()
        tasks_table = build_tasks_tab()
        docs_table = build_documents_tab()
        db_components = build_database_tab()

    # Expose ALL operations as MCP tools
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
    gr.api(search_items)
    gr.api(search_documents)
    gr.api(create_relationship)
    gr.api(get_relationships)
    gr.api(get_stats)
    gr.api(get_schema_info)
    gr.api(backup_database)
    gr.api(reset_database)
    gr.api(restore_database)
    gr.api(list_backups)

if __name__ == "__main__":
    demo.launch(mcp_server=True, theme=gr.themes.Soft())
