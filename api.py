"""
JANATPMP API Layer - Re-exports all database operations.
All functions are exposed via gr.api() in app.py for MCP tool access.
"""

from db.operations import (
    # Items
    create_item, get_item, list_items, update_item, delete_item,
    # Tasks
    create_task, get_task, list_tasks, update_task,
    # Documents
    create_document, get_document, list_documents,
    # Relationships
    create_relationship, get_relationships,
    # Schema & Stats
    get_schema_info, get_stats,
    # Search
    search_items, search_documents
)

__all__ = [
    'create_item', 'get_item', 'list_items', 'update_item', 'delete_item',
    'create_task', 'get_task', 'list_tasks', 'update_task',
    'create_document', 'get_document', 'list_documents',
    'create_relationship', 'get_relationships',
    'get_schema_info', 'get_stats',
    'search_items', 'search_documents'
]
