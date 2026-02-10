"""JANATPMP — Single-page Gradio application with MCP server."""

import sys

# Fix Windows cp1252 console crash on Gradio's emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import gradio as gr
from db.operations import (
    init_database,
    # MCP-exposed operations
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats, get_schema_info,
    backup_database, reset_database, restore_database, list_backups,
)
from pages.projects import build_page

# Initialize database and settings BEFORE building UI
init_database()
from services.settings import init_settings
init_settings()

# Build single-page application
with gr.Blocks(title="JANATPMP") as demo:
    build_page()

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
    demo.launch(
        mcp_server=True,
        server_name="0.0.0.0",
        theme=gr.themes.Soft(),
        css="""
            .sidebar.right .sidebar-content { padding: 8px 12px !important; }
            .sidebar.right .message-row { max-width: 100% !important; }
        """,
    )
