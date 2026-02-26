"""Entity operations — CRUD for extracted entities and mentions.

R29: The Troubadour. Provides MCP-exposed tools for entity management,
search, and mention tracking. Entities are extracted from messages by
the Slumber Cycle's extraction sub-cycle.
"""

import json
import logging
from db.operations import get_connection

logger = logging.getLogger(__name__)


def create_entity(
    entity_type: str,
    name: str,
    description: str = "",
    first_seen_at: str = "",
    attributes: str = "{}",
) -> str:
    """Create a new extracted entity.

    Args:
        entity_type: One of: concept, decision, milestone, person, reference, emotional_state.
        name: Canonical name for the entity.
        description: Synthesized description (1-3 sentences).
        first_seen_at: ISO timestamp of earliest source message.
        attributes: JSON string of type-specific fields.

    Returns:
        The generated entity ID.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO entities (entity_type, name, description, first_seen_at,
                                  last_seen_at, attributes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entity_type, name, description,
            first_seen_at or None,
            first_seen_at or None,
            attributes,
        ))
        conn.commit()
        rowid = cursor.lastrowid
        cursor.execute("SELECT id FROM entities WHERE rowid = ?", (rowid,))
        row = cursor.fetchone()
        return row["id"] if row else ""


def get_entity(entity_id: str) -> dict:
    """Get a single entity by ID with its recent mentions.

    Args:
        entity_id: The unique entity ID.

    Returns:
        Dict with entity data and a 'mentions' list of recent mentions
        (up to 20), each with message_id, conversation_id, relevance,
        context_snippet, created_at. Empty dict if not found.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return {}

        entity = dict(row)

        mentions = conn.execute("""
            SELECT em.message_id, em.conversation_id, em.relevance,
                   em.context_snippet, em.created_at,
                   c.title as conversation_title
            FROM entity_mentions em
            LEFT JOIN conversations c ON em.conversation_id = c.id
            WHERE em.entity_id = ?
            ORDER BY em.created_at DESC
            LIMIT 20
        """, (entity_id,)).fetchall()

        entity["mentions"] = [dict(m) for m in mentions]
        return entity


def list_entities(entity_type: str = "", limit: int = 50) -> list[dict]:
    """List entities with optional type filter.

    Args:
        entity_type: Filter by type (concept, decision, milestone, person,
                     reference, emotional_state). Empty for all types.
        limit: Maximum results (default 50).

    Returns:
        List of entity dicts ordered by mention_count descending.
    """
    sql = "SELECT * FROM entities WHERE 1=1"
    params = []

    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)

    sql += " ORDER BY mention_count DESC, updated_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def search_entities(query: str, entity_type: str = "", limit: int = 20) -> list[dict]:
    """Full-text search across entities by name and description.

    Args:
        query: Search query string.
        entity_type: Optional type filter. Empty for all types.
        limit: Maximum results (default 20).

    Returns:
        List of matching entity dicts with id, entity_type, name,
        description (first 300 chars), mention_count, first_seen_at,
        last_seen_at.
    """
    import re

    raw_terms = re.sub(r'[^\w\s]', '', query).split()
    meaningful = [t for t in raw_terms if len(t) > 1]
    if not meaningful:
        return []

    fts_query = " AND ".join(f'"{t}"' for t in meaningful)

    sql = """
        SELECT e.id, e.entity_type, e.name,
               substr(e.description, 1, 300) as description,
               e.mention_count, e.first_seen_at, e.last_seen_at,
               e.created_at
        FROM entities e
        JOIN entities_fts fts ON fts.rowid = e.rowid
        WHERE entities_fts MATCH ?
    """
    params = [fts_query]

    if entity_type:
        sql += " AND e.entity_type = ?"
        params.append(entity_type)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def update_entity(
    entity_id: str,
    description: str = "",
    last_seen_at: str = "",
    mention_count: int = 0,
    attributes: str = "",
) -> str:
    """Update an existing entity.

    Args:
        entity_id: The entity to update.
        description: New description (empty = no change).
        last_seen_at: New last_seen_at timestamp (empty = no change).
        mention_count: New mention count (0 = no change).
        attributes: New attributes JSON (empty = no change).

    Returns:
        Status message.
    """
    updates = []
    params = []

    if description:
        updates.append("description = ?")
        params.append(description)
    if last_seen_at:
        updates.append("last_seen_at = ?")
        params.append(last_seen_at)
    if mention_count > 0:
        updates.append("mention_count = ?")
        params.append(mention_count)
    if attributes:
        updates.append("attributes = ?")
        params.append(attributes)

    if not updates:
        return "No updates provided"

    params.append(entity_id)
    sql = f"UPDATE entities SET {', '.join(updates)} WHERE id = ?"

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        if cursor.rowcount == 0:
            return f"Entity {entity_id[:12]} not found"

    return f"Updated entity {entity_id[:12]}"


def create_entity_mention(
    entity_id: str,
    message_id: str,
    conversation_id: str,
    relevance: float = 0.5,
    context_snippet: str = "",
) -> str:
    """Link an entity to a source message.

    Args:
        entity_id: The entity being mentioned.
        message_id: The message that mentions the entity.
        conversation_id: The conversation containing the message.
        relevance: How central the entity is to the message (0.0-1.0).
        context_snippet: The passage that triggered extraction (max 200 chars).

    Returns:
        The generated mention ID, or empty string if duplicate.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO entity_mentions
                    (entity_id, message_id, conversation_id, relevance, context_snippet)
                VALUES (?, ?, ?, ?, ?)
            """, (
                entity_id, message_id, conversation_id,
                max(0.0, min(1.0, relevance)),
                (context_snippet or "")[:200],
            ))
            conn.commit()
            if cursor.rowcount == 0:
                return ""  # Duplicate
            rowid = cursor.lastrowid
            cursor.execute("SELECT id FROM entity_mentions WHERE rowid = ?", (rowid,))
            row = cursor.fetchone()
            return row["id"] if row else ""
        except Exception as e:
            logger.warning("create_entity_mention failed: %s", e)
            return ""


def find_entity_by_name(entity_type: str, name: str) -> dict:
    """Find an entity by exact normalized name match within a type.

    Args:
        entity_type: The entity type to search within.
        name: The name to match (case-insensitive, stripped).

    Returns:
        Entity dict if found, empty dict otherwise.
    """
    normalized = name.strip().lower()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM entities WHERE entity_type = ? AND LOWER(TRIM(name)) = ?",
            (entity_type, normalized),
        ).fetchone()
    return dict(row) if row else {}


def get_entity_stats() -> dict:
    """Get entity extraction statistics.

    Returns:
        Dict with total_entities, counts by type, total_mentions,
        messages_extracted count.
    """
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]

        type_counts = {}
        rows = conn.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM entities GROUP BY entity_type"
        ).fetchall()
        for row in rows:
            type_counts[row["entity_type"]] = row["cnt"]

        total_mentions = conn.execute(
            "SELECT COUNT(*) FROM entity_mentions"
        ).fetchone()[0]

        messages_extracted = conn.execute(
            "SELECT COUNT(*) FROM messages_metadata WHERE extracted_at IS NOT NULL"
        ).fetchone()[0]

    return {
        "total_entities": total,
        "by_type": type_counts,
        "total_mentions": total_mentions,
        "messages_extracted": messages_extracted,
    }
