"""MCP Tool Registry — all 89 functions exposed via gr.api().

Centralizes imports so app.py only needs one import line.
Grouped by category for readability. Each function MUST have
Google-style docstrings (Gradio uses them for MCP tool descriptions).
"""

# --- Core CRUD (db/operations.py) — 25 functions ---
from db.operations import (
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_sprint_view,
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

# --- Evaluation backfill (R24) — 1 function ---
from db.chat_operations import backfill_message_metadata

# --- Janus continuous chat + stream (R14/R17) — 4 functions ---
from db.chat_operations import (
    get_or_create_janus_conversation, archive_janus_conversation,
    get_conversation_stream, get_janus_stream,
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

# --- Knowledge graph (R13: Neo4j) — 5 functions ---
from graph.graph_service import graph_query, graph_neighbors, graph_stats
from graph.graph_analytics import compute_centrality as compute_graph_centrality
from graph.cdc_consumer import backfill_graph, seed_identity_graph
# --- Semantic edge generation (R20: Graph Awakening) — 1 function ---
from graph.semantic_edges import weave_conversation_graph

# --- File registry + auto-ingestion + temporal context (R17) — 5 functions ---
from db.file_registry_ops import (
    get_file_registry_stats, list_registered_files, search_file_registry,
)
from services.auto_ingest import get_ingestion_progress
from atlas.temporal import get_temporal_context
# --- Entity extraction (R29: The Troubadour) — 3 functions ---
from db.entity_ops import list_entities, get_entity, search_entities
# --- Entity merge (R47: Entity Merge Infrastructure) — 2 functions ---
from services.entity_merge import merge_entities, batch_merge_from_map
# --- Knowledge state + register mining (R32: The Mirror) — 3 functions ---
from db.chat_operations import get_knowledge_state
from atlas.register_mining import search_register_exemplars, run_register_mining_cycle
# --- Chat pipeline (R28: diagnostic MCP endpoint) — 1 function ---
from services.chat import chat_with_janus
# --- Slumber status (R22: First Light) — 1 function ---
from services.slumber import get_slumber_status
# --- System status (R48: System Observability) — 1 function ---
from services.system_status import get_system_status
# --- Backfill orchestrator (R26: The Waking Mind) — 3 functions ---
from services.backfill_orchestrator import (
    get_backfill_progress, cancel_backfill, run_backfill,
)


ALL_MCP_TOOLS: list = [
    # --- Projects page: items + tasks CRUD (15) ---
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    search_items,
    create_relationship, get_relationships,
    get_sprint_view,
    get_domains, get_domain, create_domain, update_domain,

    # --- Knowledge page: memory + connections + pipeline (34) ---
    # Memory (conversations, documents, search)
    create_document, get_document, list_documents, search_documents,
    create_conversation, get_conversation, list_conversations,
    update_conversation, delete_conversation, search_conversations,
    add_message, get_messages, get_conversation_by_uri,
    add_message_metadata, get_message_metadata,
    # Janus lifecycle
    get_or_create_janus_conversation, archive_janus_conversation,
    get_conversation_stream, get_janus_stream,
    # Pipeline (ingestion, embedding, chunking, graph)
    import_conversations_json, import_conversations_directory,
    ingest_google_ai_conversations, ingest_markdown_documents,
    vector_search, vector_search_all, recreate_collections,
    chunk_all_messages, chunk_all_documents,
    embed_all_documents, embed_all_messages, embed_all_domains,
    embed_all_items, embed_all_tasks,
    get_chunks, get_chunk_stats, search_chunks, delete_chunks,
    graph_query, graph_neighbors, graph_stats,
    backfill_graph, seed_identity_graph, weave_conversation_graph,
    get_file_registry_stats, list_registered_files, search_file_registry,
    get_ingestion_progress,
    # Entity extraction (R29: The Troubadour)
    list_entities, get_entity, search_entities,
    # Entity merge (R47: Entity Merge Infrastructure)
    merge_entities, batch_merge_from_map,

    # --- Admin page: operations + platform (6) ---
    get_stats, get_schema_info,
    backup_database, reset_database, restore_database, list_backups,
    export_platform_data, import_platform_data,

    # --- Cross-cutting: chat pipeline + temporal context + slumber status + backfill (7) ---
    chat_with_janus,
    get_temporal_context,
    get_slumber_status,
    backfill_message_metadata,
    get_backfill_progress,
    cancel_backfill,
    run_backfill,

    # --- Knowledge state + register mining (R32: The Mirror) — 3 functions ---
    get_knowledge_state,
    search_register_exemplars,
    run_register_mining_cycle,

    # --- System observability (R48) — 1 function ---
    get_system_status,

    # --- Graph analytics (R50: GDS centrality) — 1 function ---
    compute_graph_centrality,
]
