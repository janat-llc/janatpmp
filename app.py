"""JANATPMP — Multipage Gradio application with MCP server.

Hybrid architecture: monolith at / (Projects, Work, Knowledge, Admin)
plus Sovereign Chat at /chat via demo.route().
"""

import sys
import logging

# Fix Windows cp1252 console crash on Gradio's emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from services.log_config import setup_logging, cleanup_old_logs
setup_logging()
logger = logging.getLogger(__name__)

import gradio as gr
from db.operations import (
    init_database, cleanup_cdc_outbox,
    # MCP-exposed operations
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats, get_schema_info,
    backup_database, reset_database, restore_database, list_backups,
    get_domains, get_domain, create_domain, update_domain,
)
from db.chat_operations import (
    create_conversation, get_conversation, get_conversation_by_uri,
    list_conversations, update_conversation, delete_conversation,
    search_conversations, add_message, get_messages,
)
from services.claude_import import import_conversations_json
from services.vector_store import (
    search as vector_search, search_all as vector_search_all,
    recreate_collections,
)
from services.bulk_embed import embed_all_documents, embed_all_messages, embed_all_domains
from pages.projects import build_page
from pages import chat as chat_page
from janat_theme import JanatTheme, JANAT_CSS

# Initialize database and settings BEFORE building UI
init_database()
from services.settings import init_settings
init_settings()
cleanup_old_logs()
cleanup_cdc_outbox()
logger.info("Database and settings initialized")

# Initialize vector store collections (safe if Qdrant not running)
try:
    from services.vector_store import ensure_collections
    ensure_collections()
except Exception:
    logger.warning("Qdrant not available -- vector search disabled")

# Branded header HTML — shared across all pages via route.
# JavaScript auto-highlights the active page link based on current URL.
JANAT_HEADER = """
<div id="janat-header-bar" style="display:flex; align-items:center; justify-content:space-between;
            padding:10px 20px; border-bottom:1px solid #1a1a1a; background:#000;">
    <div style="display:flex; align-items:center; gap:24px;">
        <a href="/" style="text-decoration:none;">
            <span style="font-family:'Orbitron',sans-serif; font-size:1.4rem;
                         font-weight:700; color:#00FFFF; letter-spacing:0.15em;">
                JANATPMP
            </span>
        </a>
        <nav id="janat-nav" style="display:flex; gap:16px; align-items:center;">
            <a href="/" data-path="/"
               style="font-family:'Rajdhani',sans-serif; font-size:0.95rem; font-weight:600;
                      text-decoration:none; letter-spacing:0.05em;">Dashboard</a>
            <a href="/chat" data-path="/chat"
               style="font-family:'Rajdhani',sans-serif; font-size:0.95rem; font-weight:600;
                      text-decoration:none; letter-spacing:0.05em;">Chat</a>
        </nav>
    </div>
    <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-family:'Rajdhani',sans-serif; font-size:0.75rem;
                     color:#808080; letter-spacing:0.05em;">
            Powered by
        </span>
        <img src="/gradio_api/file=assets/janat_logo_bold_transparent.png"
             alt="Janat" style="height:28px; width:auto; opacity:0.85;" />
    </div>
</div>
<script>
(function() {
    var path = window.location.pathname.replace(/\\/$/, '') || '/';
    document.querySelectorAll('#janat-nav a').forEach(function(a) {
        var linkPath = a.getAttribute('data-path');
        if (path === linkPath || (linkPath === '/' && path === '')) {
            a.style.color = '#00FFFF';
        } else {
            a.style.color = '#808080';
        }
        a.onmouseover = function() { this.style.color = '#00FFFF'; };
        a.onmouseout = function() {
            var p = window.location.pathname.replace(/\\/$/, '') || '/';
            this.style.color = (this.getAttribute('data-path') === p) ? '#00FFFF' : '#808080';
        };
    });
})();
</script>
"""

# Build multipage application
with gr.Blocks(title="JANATPMP") as demo:
    gr.HTML(JANAT_HEADER, elem_id="janat-header")
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

    # Domain operations (R8)
    gr.api(get_domains)
    gr.api(get_domain)
    gr.api(create_domain)
    gr.api(update_domain)

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

    # RAG pipeline (R9: ATLAS two-stage search + embedding)
    gr.api(vector_search)
    gr.api(vector_search_all)
    gr.api(embed_all_documents)
    gr.api(embed_all_messages)
    gr.api(embed_all_domains)
    gr.api(recreate_collections)

# --- Sovereign Chat route (outside main Blocks context) ---
with demo.route("Chat", "/chat"):
    gr.HTML(JANAT_HEADER, elem_id="janat-header")
    chat_page.build_chat_page()

if __name__ == "__main__":
    demo.launch(
        mcp_server=True,
        server_name="0.0.0.0",
        theme=JanatTheme(),
        css=JANAT_CSS,
        allowed_paths=["assets"],
    )
