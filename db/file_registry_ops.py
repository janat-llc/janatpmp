"""File Registry MCP tools — query and search ingested file records.

R17: Exposes file registry as queryable state for MCP clients.
Thin layer over the file_registry table — all writes go through
services/auto_ingest.py.
"""

import logging
from db.operations import get_connection

logger = logging.getLogger(__name__)


def get_file_registry_stats() -> dict:
    """Get file registry statistics showing ingestion totals and breakdowns.

    Returns:
        Dict with total_files, by_type (claude/google_ai/markdown counts),
        by_status (ingested/failed/skipped counts), total_entities_created,
        last_ingestion_at, oldest_file, newest_file.
    """
    with get_connection() as conn:
        # Check if table exists (graceful on fresh DB before migration)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_registry'"
        ).fetchone()
        if not tables:
            return {"total_files": 0, "by_type": {}, "by_status": {},
                    "total_entities_created": 0, "last_ingestion_at": None,
                    "oldest_file": None, "newest_file": None}

        total = conn.execute("SELECT COUNT(*) FROM file_registry").fetchone()[0]

        by_type = {}
        for row in conn.execute(
            "SELECT ingestion_type, COUNT(*) as cnt FROM file_registry GROUP BY ingestion_type"
        ).fetchall():
            by_type[row["ingestion_type"]] = row["cnt"]

        by_status = {}
        for row in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM file_registry GROUP BY status"
        ).fetchall():
            by_status[row["status"]] = row["cnt"]

        total_entities = conn.execute(
            "SELECT COALESCE(SUM(entity_count), 0) FROM file_registry"
        ).fetchone()[0]

        last_ingestion = conn.execute(
            "SELECT MAX(ingested_at) FROM file_registry"
        ).fetchone()[0]

        oldest = conn.execute(
            "SELECT MIN(ingested_at) FROM file_registry"
        ).fetchone()[0]

        newest = conn.execute(
            "SELECT MAX(ingested_at) FROM file_registry"
        ).fetchone()[0]

    return {
        "total_files": total,
        "by_type": by_type,
        "by_status": by_status,
        "total_entities_created": total_entities,
        "last_ingestion_at": last_ingestion,
        "oldest_file": oldest,
        "newest_file": newest,
    }


def list_registered_files(ingestion_type: str = "", status: str = "",
                          limit: int = 50) -> list[dict]:
    """List files in the ingestion registry with optional filters.

    Args:
        ingestion_type: Filter by type ('claude', 'google_ai', 'markdown'). Empty = all.
        status: Filter by status ('ingested', 'failed', 'skipped'). Empty = all.
        limit: Max rows to return (default 50).

    Returns:
        List of file registry record dicts with id, file_path, filename,
        content_hash, file_size, ingestion_type, entity_type, entity_count,
        status, error_message, ingested_at, created_at.
    """
    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_registry'"
        ).fetchone()
        if not tables:
            return []

        query = "SELECT * FROM file_registry WHERE 1=1"
        params: list = []
        if ingestion_type:
            query += " AND ingestion_type = ?"
            params.append(ingestion_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY ingested_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def search_file_registry(query: str, limit: int = 20) -> list[dict]:
    """Search file registry by filename pattern using LIKE matching.

    Args:
        query: Search string (matched against filename with wildcards).
        limit: Max rows to return (default 20).

    Returns:
        List of matching file registry record dicts.
    """
    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_registry'"
        ).fetchone()
        if not tables:
            return []

        rows = conn.execute(
            "SELECT * FROM file_registry WHERE filename LIKE ? ORDER BY ingested_at DESC LIMIT ?",
            (f"%{query}%", limit)
        ).fetchall()
    return [dict(row) for row in rows]
