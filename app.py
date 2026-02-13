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
from db.chat_operations import (
    create_conversation, get_conversation, get_conversation_by_uri,
    list_conversations, update_conversation, delete_conversation,
    search_conversations, add_message, get_messages,
)
from services.claude_import import import_conversations_json
from services.vector_store import search as vector_search, search_all as vector_search_all
from services.bulk_embed import embed_all_documents, embed_all_messages
from pages.projects import build_page

# Initialize database and settings BEFORE building UI
init_database()
from services.settings import init_settings
init_settings()

# Initialize vector store collections (safe if Qdrant not running)
try:
    from services.vector_store import ensure_collections
    ensure_collections()
except Exception:
    print("Qdrant not available -- vector search disabled")

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

    # Chat operations (Phase 4B)
    gr.api(create_conversation)
    gr.api(get_conversation)
    gr.api(list_conversations)
    gr.api(update_conversation)
    gr.api(delete_conversation)
    gr.api(search_conversations)
    gr.api(add_message)
    gr.api(get_messages)
    gr.api(get_conversation_by_uri)

    # Import pipeline (Phase 5)
    gr.api(import_conversations_json)

    # RAG pipeline (Phase 5 Layer 2)
    gr.api(vector_search)
    gr.api(vector_search_all)
    gr.api(embed_all_documents)
    gr.api(embed_all_messages)

if __name__ == "__main__":
    demo.launch(
        mcp_server=True,
        server_name="0.0.0.0",
        theme=gr.themes.Soft(),
        css="""
            .sidebar.right .sidebar-content { padding: 4px 6px !important; }
            .sidebar.right .message-row { max-width: 100% !important; }
            .sidebar.right .chatbot { padding: 0 !important; }
            .sidebar.right .message { padding: 6px 8px !important; max-width: 100% !important; }
            .sidebar.right .bubble-wrap { padding: 0 !important; }
            .sidebar.right .wrapper { padding: 0 !important; }
        """,
    )
