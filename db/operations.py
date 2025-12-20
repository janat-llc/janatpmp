"""
Database operations for JANATPMP.
CRUD functions for Items, Tasks, Documents, and Relationships.
Each function has proper docstrings and type hints for MCP tool generation.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

# Database path
DB_PATH = Path(__file__).parent / "janatpmp.db"


@contextmanager
def get_connection():
    """Get database connection with proper settings."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# =============================================================================
# ITEMS CRUD
# =============================================================================

def create_item(
    entity_type: str,
    domain: str,
    title: str,
    description: str = "",
    status: str = "not_started",
    parent_id: str = "",
    priority: int = 3,
    attributes: str = "{}"
) -> str:
    """
    Create a new item in the database.

    Args:
        entity_type: Type of item (project, epic, feature, component, book, chapter, etc.)
        domain: Domain this belongs to (literature, janatpmp, janat, atlas, meax, etc.)
        title: Title of the item
        description: Optional description
        status: Status (not_started, planning, in_progress, blocked, review, completed, shipped, archived)
        parent_id: Optional parent item ID for hierarchy
        priority: Priority 1-5 (1=highest, 5=lowest)
        attributes: JSON string of domain-specific attributes

    Returns:
        The ID of the created item
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO items (entity_type, domain, title, description, status, parent_id, priority, attributes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_type,
            domain,
            title,
            description if description else None,
            status,
            parent_id if parent_id else None,
            priority,
            attributes
        ))
        conn.commit()

        # Get the generated ID
        cursor.execute("SELECT id FROM items WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_item(item_id: str) -> dict:
    """
    Get a single item by ID.

    Args:
        item_id: The unique item ID

    Returns:
        Dict with item data or empty dict if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}


def list_items(
    domain: str = "",
    status: str = "",
    entity_type: str = "",
    parent_id: str = "",
    limit: int = 100
) -> list:
    """
    List items with optional filters.

    Args:
        domain: Filter by domain (optional)
        status: Filter by status (optional)
        entity_type: Filter by entity type (optional)
        parent_id: Filter by parent ID (optional)
        limit: Maximum number of items to return

    Returns:
        List of item dicts
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM items WHERE 1=1"
        params = []

        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if status:
            query += " AND status = ?"
            params.append(status)
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        if parent_id:
            query += " AND parent_id = ?"
            params.append(parent_id)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_item(
    item_id: str,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: int = 0,
    attributes: str = ""
) -> str:
    """
    Update an existing item.

    Args:
        item_id: The item ID to update
        title: New title (optional, empty string = no change)
        description: New description (optional)
        status: New status (optional)
        priority: New priority 1-5 (optional, 0 = no change)
        attributes: New attributes JSON (optional)

    Returns:
        Success message or error
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        updates = []
        params = []

        if title:
            updates.append("title = ?")
            params.append(title)
        if description:
            updates.append("description = ?")
            params.append(description)
        if status:
            updates.append("status = ?")
            params.append(status)
        if priority > 0:
            updates.append("priority = ?")
            params.append(priority)
        if attributes:
            updates.append("attributes = ?")
            params.append(attributes)

        if not updates:
            return "No updates provided"

        params.append(item_id)
        query = f"UPDATE items SET {', '.join(updates)} WHERE id = ?"

        cursor.execute(query, params)
        conn.commit()

        return f"Updated item {item_id}" if cursor.rowcount > 0 else f"Item {item_id} not found"


def delete_item(item_id: str) -> str:
    """
    Delete an item by ID.

    Args:
        item_id: The item ID to delete

    Returns:
        Success message or error
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        return f"Deleted item {item_id}" if cursor.rowcount > 0 else f"Item {item_id} not found"


# =============================================================================
# TASKS CRUD
# =============================================================================

def create_task(
    task_type: str,
    title: str,
    description: str = "",
    assigned_to: str = "unassigned",
    target_item_id: str = "",
    priority: str = "normal",
    agent_instructions: str = ""
) -> str:
    """
    Create a new task.

    Args:
        task_type: Type (agent_story, user_story, subtask, research, review, documentation)
        title: Task title
        description: Task description
        assigned_to: Assignee (agent, claude, mat, janus, unassigned)
        target_item_id: Optional item this task is working on
        priority: Priority (urgent, normal, background)
        agent_instructions: Detailed instructions for agent execution

    Returns:
        The ID of the created task
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (task_type, title, description, assigned_to, target_item_id, priority, agent_instructions)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task_type,
            title,
            description if description else None,
            assigned_to,
            target_item_id if target_item_id else None,
            priority,
            agent_instructions if agent_instructions else None
        ))
        conn.commit()

        cursor.execute("SELECT id FROM tasks WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_task(task_id: str) -> dict:
    """
    Get a single task by ID.

    Args:
        task_id: The unique task ID

    Returns:
        Dict with task data or empty dict if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}


def list_tasks(
    status: str = "",
    assigned_to: str = "",
    task_type: str = "",
    target_item_id: str = "",
    limit: int = 100
) -> list:
    """
    List tasks with optional filters.

    Args:
        status: Filter by status (pending, processing, blocked, review, completed, failed, retry, dlq)
        assigned_to: Filter by assignee
        task_type: Filter by task type
        target_item_id: Filter by target item
        limit: Maximum number of tasks to return

    Returns:
        List of task dicts
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if assigned_to:
            query += " AND assigned_to = ?"
            params.append(assigned_to)
        if task_type:
            query += " AND task_type = ?"
            params.append(task_type)
        if target_item_id:
            query += " AND target_item_id = ?"
            params.append(target_item_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_task(
    task_id: str,
    status: str = "",
    assigned_to: str = "",
    output: str = ""
) -> str:
    """
    Update a task.

    Args:
        task_id: The task ID to update
        status: New status (optional)
        assigned_to: New assignee (optional)
        output: Task output as JSON string (optional)

    Returns:
        Success message or error
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "processing":
                updates.append("started_at = datetime('now')")
            elif status == "completed":
                updates.append("completed_at = datetime('now')")
        if assigned_to:
            updates.append("assigned_to = ?")
            params.append(assigned_to)
        if output:
            updates.append("output = ?")
            params.append(output)

        if not updates:
            return "No updates provided"

        params.append(task_id)
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"

        cursor.execute(query, params)
        conn.commit()

        return f"Updated task {task_id}" if cursor.rowcount > 0 else f"Task {task_id} not found"


# =============================================================================
# DOCUMENTS CRUD
# =============================================================================

def create_document(
    doc_type: str,
    source: str,
    title: str,
    content: str = "",
    file_path: str = "",
    conversation_uri: str = ""
) -> str:
    """
    Create a new document.

    Args:
        doc_type: Type (conversation, file, artifact, research, agent_output, session_notes, code)
        source: Source (claude_exporter, upload, agent, generated, manual)
        title: Document title
        content: Document content
        file_path: Optional file path
        conversation_uri: Optional conversation URI (for claude_exporter imports)

    Returns:
        The ID of the created document
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (doc_type, source, title, content, file_path, conversation_uri)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            doc_type,
            source,
            title,
            content if content else None,
            file_path if file_path else None,
            conversation_uri if conversation_uri else None
        ))
        conn.commit()

        cursor.execute("SELECT id FROM documents WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_document(document_id: str) -> dict:
    """
    Get a single document by ID.

    Args:
        document_id: The unique document ID

    Returns:
        Dict with document data or empty dict if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}


def list_documents(
    doc_type: str = "",
    source: str = "",
    limit: int = 100
) -> list:
    """
    List documents with optional filters.

    Args:
        doc_type: Filter by document type
        source: Filter by source
        limit: Maximum number of documents to return

    Returns:
        List of document dicts
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT id, doc_type, source, title, file_path, conversation_uri, created_at FROM documents WHERE 1=1"
        params = []

        if doc_type:
            query += " AND doc_type = ?"
            params.append(doc_type)
        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# RELATIONSHIPS CRUD
# =============================================================================

def create_relationship(
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relationship_type: str,
    strength: str = "hard"
) -> str:
    """
    Create a relationship between entities.

    Args:
        source_type: Source entity type (item, task, document)
        source_id: Source entity ID
        target_type: Target entity type (item, task, document)
        target_id: Target entity ID
        relationship_type: Type (blocks, enables, informs, references, implements, documents, depends_on, parent_of, attached_to)
        strength: Relationship strength (hard, soft)

    Returns:
        The ID of the created relationship
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO relationships (source_type, source_id, target_type, target_id, relationship_type, strength)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (source_type, source_id, target_type, target_id, relationship_type, strength))
        conn.commit()

        cursor.execute("SELECT id FROM relationships WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_relationships(
    entity_type: str = "",
    entity_id: str = "",
    relationship_type: str = ""
) -> list:
    """
    Get relationships for an entity.

    Args:
        entity_type: Entity type to search for (item, task, document)
        entity_id: Entity ID to search for
        relationship_type: Filter by relationship type (optional)

    Returns:
        List of relationship dicts (both as source and target)
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT * FROM relationships
            WHERE (source_type = ? AND source_id = ?)
               OR (target_type = ? AND target_id = ?)
        """
        params = [entity_type, entity_id, entity_type, entity_id]

        if relationship_type:
            query += " AND relationship_type = ?"
            params.append(relationship_type)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# SCHEMA & STATS
# =============================================================================

def get_schema_info() -> dict:
    """
    Get complete database schema information for visualization.

    Returns:
        Dict with tables, columns, indexes, and triggers
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get tables
        cursor.execute("""
            SELECT name, sql FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'
            ORDER BY name
        """)
        tables = {}
        for row in cursor.fetchall():
            table_name = row['name']
            # Get columns for each table
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [{'name': col['name'], 'type': col['type'], 'notnull': col['notnull']}
                      for col in cursor.fetchall()]
            tables[table_name] = {'columns': columns}

        # Get indexes
        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
        indexes = [{'name': row['name'], 'table': row['tbl_name']} for row in cursor.fetchall()]

        # Get triggers
        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'")
        triggers = [{'name': row['name'], 'table': row['tbl_name']} for row in cursor.fetchall()]

        return {
            'tables': tables,
            'indexes': indexes,
            'triggers': triggers
        }


def get_stats() -> dict:
    """
    Get database statistics.

    Returns:
        Dict with counts for items, tasks, documents, relationships
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        stats = {}

        # Items by domain
        cursor.execute("SELECT domain, COUNT(*) as count FROM items GROUP BY domain")
        stats['items_by_domain'] = {row['domain']: row['count'] for row in cursor.fetchall()}

        # Items by status
        cursor.execute("SELECT status, COUNT(*) as count FROM items GROUP BY status")
        stats['items_by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}

        # Tasks by status
        cursor.execute("SELECT status, COUNT(*) as count FROM tasks GROUP BY status")
        stats['tasks_by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}

        # Documents by type
        cursor.execute("SELECT doc_type, COUNT(*) as count FROM documents GROUP BY doc_type")
        stats['documents_by_type'] = {row['doc_type']: row['count'] for row in cursor.fetchall()}

        # Totals
        cursor.execute("SELECT COUNT(*) FROM items")
        stats['total_items'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tasks")
        stats['total_tasks'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM documents")
        stats['total_documents'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM relationships")
        stats['total_relationships'] = cursor.fetchone()[0]

        return stats


def search_items(query: str, limit: int = 50) -> list:
    """
    Full-text search across items.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        List of matching items
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT items.* FROM items
            JOIN items_fts ON items.id = items_fts.id
            WHERE items_fts MATCH ?
            LIMIT ?
        """, (query, limit))
        return [dict(row) for row in cursor.fetchall()]


def search_documents(query: str, limit: int = 50) -> list:
    """
    Full-text search across documents.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        List of matching documents (without full content)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT documents.id, documents.doc_type, documents.source, documents.title,
                   documents.file_path, documents.conversation_uri, documents.created_at
            FROM documents
            JOIN documents_fts ON documents.id = documents_fts.id
            WHERE documents_fts MATCH ?
            LIMIT ?
        """, (query, limit))
        return [dict(row) for row in cursor.fetchall()]
