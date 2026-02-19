"""
Database operations for JANATPMP.
CRUD functions for Items, Tasks, Documents, and Relationships.
Each function has proper docstrings and type hints for MCP tool generation.
"""

import sqlite3
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
from shared.exceptions import DomainNotFoundError

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent / "janatpmp.db"


@contextmanager
def get_connection():
    """Get database connection with proper settings."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Initialize database schema if tables don't exist.
    Safe to call multiple times. Cleans orphaned WAL/journal files.
    Also creates the settings table and seeds defaults."""
    schema_path = Path(__file__).parent / "schema.sql"

    # Clean orphaned WAL files if DB was deleted but journals remain
    if not DB_PATH.exists():
        for suffix in ['-wal', '-shm', '-journal']:
            p = Path(str(DB_PATH) + suffix)
            if p.exists():
                p.unlink()

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
        )
        if cursor.fetchone() is None:
            schema_sql = schema_path.read_text(encoding="utf-8")
            conn.executescript(schema_sql)
        else:
            # Ensure settings table exists on existing databases (idempotent DDL)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '',
                    is_secret INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS settings_updated_at AFTER UPDATE ON settings
                BEGIN
                    UPDATE settings SET updated_at = datetime('now') WHERE key = NEW.key;
                END
            """)
            conn.execute("""
                INSERT OR IGNORE INTO schema_version (version, description)
                VALUES ('0.2.0', 'Add settings table for persistent configuration')
            """)
            conn.commit()

            # Migration 0.3.0: conversations + messages tables
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
            )
            if cursor.fetchone() is None:
                migration_path = Path(__file__).parent / "migrations" / "0.3.0_conversations.sql"
                if migration_path.exists():
                    migration_sql = migration_path.read_text(encoding="utf-8")
                    conn.executescript(migration_sql)

            # Migration 0.4.0: app_logs table
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='app_logs'"
            )
            if cursor.fetchone() is None:
                migration_path = Path(__file__).parent / "migrations" / "0.4.0_app_logs.sql"
                if migration_path.exists():
                    migration_sql = migration_path.read_text(encoding="utf-8")
                    conn.executescript(migration_sql)

            # Migration 0.4.1: messages FTS UPDATE trigger
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name='messages_fts_update'"
            )
            if cursor.fetchone() is None:
                migration_path = Path(__file__).parent / "migrations" / "0.4.1_messages_fts_update.sql"
                if migration_path.exists():
                    migration_sql = migration_path.read_text(encoding="utf-8")
                    conn.executescript(migration_sql)

            # Migration 0.4.2: domains as first-class entity
            # Guard on schema_version (not domains table) so partial prior runs re-execute
            cursor = conn.execute(
                "SELECT version FROM schema_version WHERE version='0.4.2'"
            )
            if cursor.fetchone() is None:
                migration_path = Path(__file__).parent / "migrations" / "0.4.2_domains_table.sql"
                if migration_path.exists():
                    migration_sql = migration_path.read_text(encoding="utf-8")
                    conn.executescript(migration_sql)


def cleanup_cdc_outbox(days: int = 90) -> int:
    """Delete processed CDC outbox entries older than the given number of days.

    Args:
        days: Delete entries older than this many days. Defaults to 90.

    Returns:
        Number of rows deleted.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """DELETE FROM cdc_outbox
               WHERE processed_qdrant = 1 AND processed_neo4j = 1
                 AND created_at < datetime('now', ? || ' days')""",
            (f"-{days}",)
        )
        conn.commit()
        deleted = cursor.rowcount
    if deleted:
        logger.info("CDC outbox cleanup: deleted %d entries older than %d days", deleted, days)
    return deleted


# =============================================================================
# DOMAINS CRUD
# =============================================================================

# Neo4j: When graph layer is implemented, domains become top-level nodes.
# All items relate upward to their domain node.
# Domain nodes carry the same metadata as this table.
# CDC outbox handles the sync trigger — no additional code needed here.

def create_domain(
    name: str,
    display_name: str,
    description: str = "",
    color: str = ""
) -> str:
    """Create a new domain.

    Args:
        name: Unique domain identifier (lowercase, no spaces — e.g. 'becoming')
        display_name: Human-readable name (e.g. 'Becoming')
        description: Purpose and scope of this domain
        color: Optional hex color for UI display

    Returns:
        The ID of the created domain
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO domains (name, display_name, description, color)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            display_name,
            description if description else None,
            color if color else None,
        ))
        conn.commit()
        cursor.execute("SELECT id FROM domains WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_domain(name: str) -> dict:
    """Get a single domain by name.

    Args:
        name: The unique domain name (e.g. 'janatpmp', 'becoming')

    Returns:
        Dict with domain data or empty dict if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM domains WHERE name = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_domains(active_only: bool = True) -> list:
    """List all domains with metadata.

    Args:
        active_only: If true, return only active domains. If false, return all domains.

    Returns:
        List of domain dicts with id, name, display_name, description, color, is_active
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM domains WHERE is_active = 1 ORDER BY name")
        else:
            cursor.execute("SELECT * FROM domains ORDER BY is_active DESC, name")
        return [dict(row) for row in cursor.fetchall()]


def update_domain(
    name: str,
    display_name: str = "",
    description: str = "",
    color: str = "",
    is_active: int = -1
) -> str:
    """Update a domain's metadata.

    Args:
        name: The domain name to update (required, used as lookup key)
        display_name: New display name (empty string = no change)
        description: New description (empty string = no change)
        color: New color hex (empty string = no change)
        is_active: Set active status (1=active, 0=inactive, -1=no change)

    Returns:
        Status message confirming the update
    """
    updates = []
    params = []
    if display_name:
        updates.append("display_name = ?")
        params.append(display_name)
    if description:
        updates.append("description = ?")
        params.append(description)
    if color:
        updates.append("color = ?")
        params.append(color)
    if is_active >= 0:
        updates.append("is_active = ?")
        params.append(is_active)

    if not updates:
        return "No changes specified"

    params.append(name)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE domains SET {', '.join(updates)} WHERE name = ?",
            params,
        )
        conn.commit()
    return f"Domain '{name}' updated"


# Initialize on import
init_database()


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
    priority: int = 3
) -> str:
    """
    Create a new item in the database.

    Args:
        entity_type: Type of item (project, epic, feature, component, book, chapter, etc.)
        domain: Domain name — must exist in the domains table (use list_domains to see valid options)
        title: Title of the item
        description: Optional description
        status: Status (not_started, planning, in_progress, blocked, review, completed, shipped, archived)
        parent_id: Optional parent item ID for hierarchy
        priority: Priority 1-5 (1=highest, 5=lowest)

    Returns:
        The ID of the created item

    Raises:
        DomainNotFoundError: If the domain does not exist in the domains table
    """
    # Validate domain exists (active or inactive — is_active is for UI filtering only)
    domain_record = get_domain(domain)
    if not domain_record:
        raise DomainNotFoundError(
            f"Domain '{domain}' does not exist. Use create_domain() first."
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO items (entity_type, domain, title, description, status, parent_id, priority, attributes)
            VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
        """, (
            entity_type,
            domain,
            title,
            description if description else None,
            status,
            parent_id if parent_id else None,
            priority,
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
    priority: int = 0
) -> str:
    """
    Update an existing item.

    Args:
        item_id: The item ID to update
        title: New title (optional, empty string = no change)
        description: New description (optional)
        status: New status (optional)
        priority: New priority 1-5 (optional, 0 = no change)

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
    content: str = ""
) -> str:
    """
    Create a new document.

    Args:
        doc_type: Type (conversation, file, artifact, research, agent_output, session_notes, code)
        source: Source (claude_exporter, upload, agent, generated, manual)
        title: Document title
        content: Document content

    Returns:
        The ID of the created document
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (doc_type, source, title, content)
            VALUES (?, ?, ?, ?)
        """, (
            doc_type,
            source,
            title,
            content if content else None,
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
    # Wrap in double quotes so FTS5 treats special chars (. * - etc.) as literals
    safe_query = '"' + query.replace('"', '""') + '"'
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT items.* FROM items
            JOIN items_fts ON items.id = items_fts.id
            WHERE items_fts MATCH ?
            LIMIT ?
        """, (safe_query, limit))
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
    # Wrap in double quotes so FTS5 treats special chars (. * - etc.) as literals
    safe_query = '"' + query.replace('"', '""') + '"'
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT documents.id, documents.doc_type, documents.source, documents.title,
                   documents.file_path, documents.conversation_uri, documents.created_at
            FROM documents
            JOIN documents_fts ON documents.id = documents_fts.id
            WHERE documents_fts MATCH ?
            LIMIT ?
        """, (safe_query, limit))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# DATABASE LIFECYCLE
# =============================================================================

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
BACKUPS_DIR = Path(__file__).parent / "backups"


def backup_database() -> str:
    """
    Create a timestamped backup of the current database.
    Backups are stored in the db/backups/ directory.

    Returns:
        The backup filename, or error message if backup failed
    """
    if not DB_PATH.exists():
        return "No database file to backup"

    BACKUPS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"janatpmp_backup_{timestamp}.db"
    backup_path = BACKUPS_DIR / backup_name

    try:
        shutil.copy2(str(DB_PATH), str(backup_path))
        return backup_name
    except Exception as e:
        logger.warning("Backup failed: %s", e)
        return f"Backup failed: {e}"


def reset_database() -> str:
    """
    Reset the database to a clean state. Drops all tables and recreates
    the schema from db/schema.sql. All data will be lost.
    Creates a timestamped backup before resetting.

    Returns:
        Status message with backup filename if created, or confirmation of reset
    """
    backup_msg = ""

    # Backup if database exists and has data
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        backup_result = backup_database()
        if not backup_result.startswith("Backup failed"):
            backup_msg = f" Backup saved as {backup_result}"

    # Delete existing database AND journal files
    for suffix in ['', '-wal', '-shm', '-journal']:
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()

    # Recreate from schema
    schema_sql = SCHEMA_PATH.read_text()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.executescript(schema_sql)
    finally:
        conn.close()

    if backup_msg:
        return f"Database reset.{backup_msg}"
    return "Database reset to clean state."


def restore_database(backup_name: str = "") -> str:
    """
    Restore database from a backup. If no backup_name is specified,
    restores the most recent backup.

    Args:
        backup_name: Name of backup file to restore (optional, defaults to most recent)

    Returns:
        Status message confirming restore, or error if no backups found
    """
    if not BACKUPS_DIR.exists():
        return "No backups found"

    if backup_name:
        backup_path = BACKUPS_DIR / backup_name
    else:
        # Find most recent backup
        backups = sorted(BACKUPS_DIR.glob("janatpmp_backup_*.db"), reverse=True)
        if not backups:
            return "No backups found"
        backup_path = backups[0]
        backup_name = backup_path.name

    if not backup_path.exists():
        return f"Backup '{backup_name}' not found"

    try:
        shutil.copy2(str(backup_path), str(DB_PATH))
        return f"Restored from {backup_name}"
    except Exception as e:
        logger.warning("Restore failed: %s", e)
        return f"Restore failed: {e}"


def list_backups() -> list:
    """
    List all available database backups.

    Returns:
        List of dicts with backup name, size in bytes, and created timestamp
    """
    if not BACKUPS_DIR.exists():
        return []

    backups = []
    for f in sorted(BACKUPS_DIR.glob("janatpmp_backup_*.db"), reverse=True):
        stat = f.stat()
        backups.append({
            "name": f.name,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
    return backups


# =============================================================================
# CONTEXT SNAPSHOT (internal — used by chat.py, NOT exposed via MCP)
# =============================================================================

def get_context_snapshot() -> str:
    """Build a context string of active items and pending tasks for system prompt injection.

    Returns a formatted string summarizing:
    - Active/in-progress items (title, domain, status)
    - Pending/processing tasks (title, assigned_to, status)

    This is injected into the chat system prompt so the AI has project awareness
    without the user needing to ask "what projects exist?" every conversation.
    """
    with get_connection() as conn:
        # Active items (not completed/archived/shipped)
        items = conn.execute(
            """SELECT title, domain, status, entity_type, priority
               FROM items
               WHERE status NOT IN ('completed', 'shipped', 'archived')
               ORDER BY priority ASC, updated_at DESC
               LIMIT 20""",
        ).fetchall()

        # Pending/active tasks
        tasks = conn.execute(
            """SELECT title, assigned_to, status, priority
               FROM tasks
               WHERE status IN ('pending', 'processing', 'blocked', 'review')
               ORDER BY
                   CASE priority WHEN 'urgent' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                   created_at DESC
               LIMIT 20""",
        ).fetchall()

    lines = []
    if items:
        lines.append(f"Active Items ({len(items)}):")
        for i in items:
            lines.append(f"  - [{i['domain']}] {i['title']} ({i['status']}, P{i['priority']})")
    else:
        lines.append("No active items.")

    if tasks:
        lines.append(f"\nPending Tasks ({len(tasks)}):")
        for t in tasks:
            assigned = t['assigned_to'] if t['assigned_to'] != 'unassigned' else 'unassigned'
            lines.append(f"  - {t['title']} ({t['status']}, {assigned})")
    else:
        lines.append("\nNo pending tasks.")

    return "\n".join(lines)


