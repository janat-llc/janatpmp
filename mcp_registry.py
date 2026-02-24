"""MCP Tool Registry — all functions exposed via gr.api().

Centralizes imports so app.py only needs one import line.
Grouped by category for readability. Each function MUST have
Google-style docstrings (Gradio uses them for MCP tool descriptions).
"""

# --- Core CRUD (db/operations.py) — 24 functions ---
from db.operations import (
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats, get_schema_info,
    backup_database, reset_database, restore_database, list_backups,
    get_domains, get_domain, create_domain, update_domain,
    export_platform_data, import_platform_data,
)

# --- Chat operations (Phase 4B) — 9 functions ---
from db.chat_operations import (
    create_conversation, get_conversation, get_conversation_by_uri,
    list_conversations, update_conversation, delete_conversation,
    search_conversations, add_message, get_messages,
)

# --- Cognitive telemetry (R12) — 2 functions ---
from db.chat_operations import add_message_metadata, get_message_metadata

# --- Janus continuous chat (R14) — 2 functions ---
from db.chat_operations import (
    get_or_create_janus_conversation, archive_janus_conversation,
)

# --- Import pipelines (Phase 5) — 2 functions ---
from services.claude_import import (
    import_conversations_json, import_conversations_directory,
)

# --- RAG pipeline (R9: ATLAS two-stage search + embedding) — 10 functions ---
from services.vector_store import (
    search as vector_search, search_all as vector_search_all,
    recreate_collections,
)
from services.bulk_embed import (
    chunk_all_messages, chunk_all_documents,
    embed_all_documents, embed_all_messages, embed_all_domains,
    embed_all_items, embed_all_tasks,
)

# --- Content ingestion (Phase 6A) — 2 functions ---
from services.ingestion.orchestrator import (
    ingest_google_ai_conversations,
    ingest_markdown_documents,
)

# --- Chunk operations (R16) — 4 functions ---
from db.chunk_operations import (
    get_chunks, get_chunk_stats, search_chunks, delete_chunks,
)

# --- Knowledge graph (R13: Neo4j) — 4 functions ---
from graph.graph_service import graph_query, graph_neighbors, graph_stats
from graph.cdc_consumer import backfill_graph

# --- File registry + auto-ingestion + temporal context (R17) — 5 functions ---
from db.file_registry_ops import (
    get_file_registry_stats, list_registered_files, search_file_registry,
)
from services.auto_ingest import get_ingestion_progress
from atlas.temporal import get_temporal_context


ALL_MCP_TOOLS: list = [
    # Core CRUD (24)
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats, get_schema_info,
    backup_database, reset_database, restore_database, list_backups,
    export_platform_data, import_platform_data,
    # Domains (4)
    get_domains, get_domain, create_domain, update_domain,
    # Chat (9)
    create_conversation, get_conversation, list_conversations,
    update_conversation, delete_conversation, search_conversations,
    add_message, get_messages, get_conversation_by_uri,
    # Cognitive telemetry (2)
    add_message_metadata, get_message_metadata,
    # Janus (2)
    get_or_create_janus_conversation, archive_janus_conversation,
    # Import (2)
    import_conversations_json, import_conversations_directory,
    # RAG + Embedding (10)
    vector_search, vector_search_all,
    chunk_all_messages, chunk_all_documents,
    embed_all_documents, embed_all_messages, embed_all_domains,
    embed_all_items, embed_all_tasks,
    recreate_collections,
    # Content Ingestion (2)
    ingest_google_ai_conversations, ingest_markdown_documents,
    # Chunks (4)
    get_chunks, get_chunk_stats, search_chunks, delete_chunks,
    # Graph (4)
    graph_query, graph_neighbors, graph_stats, backfill_graph,
    # File Registry + Temporal (5)
    get_file_registry_stats, list_registered_files, search_file_registry,
    get_ingestion_progress, get_temporal_context,
]
