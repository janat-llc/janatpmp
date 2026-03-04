"""Auto-Ingestion Scanner — startup + Slumber file discovery and ingestion.

R17: Walks configured directories, compares files against the file_registry table,
ingests new/changed files automatically. Source files are never touched.

Progress tracking covers ALL phases — scanning, parsing, chunking, and embedding.
The embed phase is the long pole (~20 min for 30K chunks); progress must answer
"how far along?" for that phase specifically.
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from db.operations import get_connection
from services.settings import get_setting

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Progress Tracking (in-memory, transient — reset per run)
# ---------------------------------------------------------------------------

_current_progress: dict = {
    "status": "idle",
    "current_phase": "",
    "phase_detail": "",
    "files_found": 0,
    "files_processed": 0,
    "files_skipped": 0,
    "files_failed": 0,
    "embed_progress": {},
    "errors": [],
    "started_at": "",
    "elapsed_seconds": 0.0,
}


def _reset_progress() -> None:
    """Reset progress tracker for a new run."""
    _current_progress.update({
        "status": "idle",
        "current_phase": "",
        "phase_detail": "",
        "files_found": 0,
        "files_processed": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "embed_progress": {},
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "elapsed_seconds": 0.0,
    })


def _update_progress(*, status: str = "", current_phase: str = "",
                     phase_detail: str = "", embed_progress: dict | None = None,
                     started_at: float | None = None) -> None:
    """Update progress tracker fields."""
    if status:
        _current_progress["status"] = status
    if current_phase:
        _current_progress["current_phase"] = current_phase
    if phase_detail:
        _current_progress["phase_detail"] = phase_detail
    if embed_progress is not None:
        _current_progress["embed_progress"] = embed_progress
    if started_at is not None:
        _current_progress["elapsed_seconds"] = round(time.time() - started_at, 1)


def get_ingestion_progress() -> dict:
    """Return current ingestion run progress.

    Tracks ALL phases — scanning, parsing, chunking, and embedding.
    The embed phase is the long pole (~20 min for 30K chunks); progress
    must answer "how far along?" for that phase specifically.

    Returns:
        Dict with status, current_phase, phase_detail, files_found,
        files_processed, files_skipped, files_failed, embed_progress,
        errors, started_at, elapsed_seconds.
    """
    return dict(_current_progress)


# ---------------------------------------------------------------------------
# File Registry Operations
# ---------------------------------------------------------------------------

def _compute_file_hash(file_path: str | Path) -> str:
    """SHA-256 hash of raw file bytes (4KB chunked reads)."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            h.update(block)
    return h.hexdigest()


def is_file_registered(file_path: str, content_hash: str) -> bool:
    """Check if file has been ingested with matching content hash.

    Returns True if file_path exists AND content_hash matches (skip).
    Returns False if file_path not found OR hash differs (needs ingestion).
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT content_hash FROM file_registry WHERE file_path = ?",
            (file_path,)
        ).fetchone()
    if row is None:
        return False
    return row["content_hash"] == content_hash


def register_file(file_path: str, content_hash: str, file_size: int,
                  ingestion_type: str, entity_type: str = "",
                  entity_count: int = 0, status: str = "ingested",
                  error_message: str = "") -> None:
    """Record a processed file in the registry.

    Uses INSERT OR REPLACE so hash-change re-ingestions update the existing row.

    Args:
        file_path: Absolute path to the file.
        content_hash: SHA-256 hash of file bytes.
        file_size: File size in bytes.
        ingestion_type: One of 'claude', 'google_ai', 'markdown'.
        entity_type: 'conversation' or 'document'.
        entity_count: Number of records created from this file.
        status: 'ingested', 'failed', or 'skipped'.
        error_message: Error details (empty on success).
    """
    filename = Path(file_path).name
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO file_registry
               (file_path, filename, content_hash, file_size,
                ingestion_type, entity_type, entity_count, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(file_path) DO UPDATE SET
                   content_hash = excluded.content_hash,
                   file_size = excluded.file_size,
                   entity_count = excluded.entity_count,
                   status = excluded.status,
                   error_message = excluded.error_message,
                   ingested_at = datetime('now')""",
            (file_path, filename, content_hash, file_size,
             ingestion_type, entity_type, entity_count, status, error_message)
        )
        conn.commit()


def _update_file_hash(file_path: str, content_hash: str, file_size: int) -> None:
    """Silently update hash for a file whose re-ingestion produced zero new entities.

    This handles hash-change re-ingestion safety: if the parser skipped everything
    (UUID dedup caught it all), just refresh the hash without counting it as a new
    ingestion. Prevents misleading "5 files ingested" logs.
    """
    with get_connection() as conn:
        conn.execute(
            """UPDATE file_registry
               SET content_hash = ?, file_size = ?, ingested_at = datetime('now')
               WHERE file_path = ?""",
            (content_hash, file_size, file_path)
        )
        conn.commit()


def get_file_registry_stats() -> dict:
    """File registry statistics.

    Returns:
        Dict with total_files, by_type, by_status, total_entities_created,
        last_ingestion_at, oldest_file, newest_file.
    """
    with get_connection() as conn:
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

        last_row = conn.execute(
            "SELECT MAX(ingested_at) FROM file_registry"
        ).fetchone()
        last_ingestion = last_row[0] if last_row else None

        oldest_row = conn.execute(
            "SELECT MIN(ingested_at) FROM file_registry"
        ).fetchone()
        oldest = oldest_row[0] if oldest_row else None

        newest_row = conn.execute(
            "SELECT MAX(ingested_at) FROM file_registry"
        ).fetchone()
        newest = newest_row[0] if newest_row else None

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
    """List files in the registry with optional filters.

    Args:
        ingestion_type: Filter by type ('claude', 'google_ai', 'markdown'). Empty = all.
        status: Filter by status ('ingested', 'failed', 'skipped'). Empty = all.
        limit: Max rows to return.

    Returns:
        List of file registry dicts.
    """
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

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Per-Type Directory Scanners
# ---------------------------------------------------------------------------

def _scan_claude_dir(directory: str) -> dict:
    """Scan Claude export directory for conversations*.json files.

    Returns:
        Dict with files_ingested, files_skipped, files_failed,
        conversations_created, total_messages, errors.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        logger.debug("Claude dir not found: %s", directory)
        return {"files_ingested": 0, "files_skipped": 0, "files_failed": 0,
                "conversations_created": 0, "total_messages": 0, "errors": []}

    files = sorted(dir_path.glob("conversations*.json"))
    if not files:
        return {"files_ingested": 0, "files_skipped": 0, "files_failed": 0,
                "conversations_created": 0, "total_messages": 0, "errors": []}

    from services.claude_import import import_conversations_json

    ingested = 0
    skipped = 0
    failed = 0
    total_convs = 0
    total_msgs = 0
    errors: list[str] = []

    for f in files:
        file_str = str(f)
        file_hash = _compute_file_hash(f)
        file_size = f.stat().st_size

        # Check registry
        with get_connection() as conn:
            row = conn.execute(
                "SELECT content_hash, entity_count FROM file_registry WHERE file_path = ?",
                (file_str,)
            ).fetchone()

        if row is not None and row["content_hash"] == file_hash:
            skipped += 1
            _current_progress["files_skipped"] += 1
            continue

        hash_changed = row is not None  # Path exists but hash differs

        try:
            _update_progress(phase_detail=f"Parsing {f.name}")
            result = import_conversations_json(file_str, skip_existing=True)
            conv_count = result.get("imported", 0)
            msg_count = result.get("total_messages", 0)

            if hash_changed and conv_count == 0:
                # Hash-change re-ingestion safety: parser skipped everything
                # (UUID dedup). Just update hash silently.
                _update_file_hash(file_str, file_hash, file_size)
                skipped += 1
                _current_progress["files_skipped"] += 1
                logger.debug("Hash refresh (no new entities): %s", f.name)
            else:
                register_file(
                    file_path=file_str,
                    content_hash=file_hash,
                    file_size=file_size,
                    ingestion_type="claude",
                    entity_type="conversation",
                    entity_count=conv_count,
                    status="ingested",
                )
                ingested += 1
                total_convs += conv_count
                total_msgs += msg_count
                _current_progress["files_processed"] += 1

            errors.extend(result.get("errors", []))
        except Exception as e:
            logger.error("Claude file failed %s: %s", f.name, e)
            register_file(
                file_path=file_str,
                content_hash=file_hash,
                file_size=file_size,
                ingestion_type="claude",
                entity_type="conversation",
                status="failed",
                error_message=str(e)[:200],
            )
            failed += 1
            _current_progress["files_failed"] += 1
            errors.append(f"{f.name}: {str(e)[:80]}")

    return {
        "files_ingested": ingested,
        "files_skipped": skipped,
        "files_failed": failed,
        "conversations_created": total_convs,
        "total_messages": total_msgs,
        "errors": errors,
    }


def _scan_google_ai_dir(directory: str) -> dict:
    """Scan Google AI directory for *.json files.

    Returns:
        Dict with files_ingested, files_skipped, files_failed,
        conversations_created, total_messages, errors.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        logger.debug("Google AI dir not found: %s", directory)
        return {"files_ingested": 0, "files_skipped": 0, "files_failed": 0,
                "conversations_created": 0, "total_messages": 0, "errors": []}

    files = sorted(dir_path.glob("*.json"))
    if not files:
        return {"files_ingested": 0, "files_skipped": 0, "files_failed": 0,
                "conversations_created": 0, "total_messages": 0, "errors": []}

    from services.ingestion.orchestrator import ingest_google_ai_conversations

    # Google AI orchestrator processes the whole directory at once.
    # Check if ANY files are new/changed before triggering the full pipeline.
    new_files = []
    for f in files:
        file_str = str(f)
        file_hash = _compute_file_hash(f)
        if not is_file_registered(file_str, file_hash):
            new_files.append((f, file_hash))

    if not new_files:
        return {"files_ingested": 0, "files_skipped": len(files),
                "files_failed": 0, "conversations_created": 0,
                "total_messages": 0, "errors": []}

    try:
        _update_progress(phase_detail=f"Parsing {len(new_files)} Google AI files")
        result = ingest_google_ai_conversations(directory, auto_embed=False)
        convs_imported = result.get("imported", 0)
        msgs = result.get("total_messages", 0)

        # Register all new files
        for f, file_hash in new_files:
            file_size = f.stat().st_size
            entity_count = convs_imported // max(len(new_files), 1)
            register_file(
                file_path=str(f),
                content_hash=file_hash,
                file_size=file_size,
                ingestion_type="google_ai",
                entity_type="conversation",
                entity_count=entity_count,
                status="ingested",
            )

        _current_progress["files_processed"] += len(new_files)
        return {
            "files_ingested": len(new_files),
            "files_skipped": len(files) - len(new_files),
            "files_failed": 0,
            "conversations_created": convs_imported,
            "total_messages": msgs,
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error("Google AI ingestion failed: %s", e)
        _current_progress["files_failed"] += len(new_files)
        return {
            "files_ingested": 0,
            "files_skipped": len(files) - len(new_files),
            "files_failed": len(new_files),
            "conversations_created": 0,
            "total_messages": 0,
            "errors": [f"Google AI dir: {str(e)[:100]}"],
        }


def _scan_markdown_dir(directory: str) -> dict:
    """Scan markdown/text directory for *.md and *.txt files.

    Returns:
        Dict with files_ingested, files_skipped, files_failed,
        documents_created, errors.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        logger.debug("Markdown dir not found: %s", directory)
        return {"files_ingested": 0, "files_skipped": 0, "files_failed": 0,
                "documents_created": 0, "errors": []}

    files = sorted(list(dir_path.glob("*.md")) + list(dir_path.glob("*.txt")))
    if not files:
        return {"files_ingested": 0, "files_skipped": 0, "files_failed": 0,
                "documents_created": 0, "errors": []}

    from services.ingestion.orchestrator import ingest_markdown_documents

    # Markdown orchestrator processes the whole directory at once.
    new_files = []
    for f in files:
        file_str = str(f)
        file_hash = _compute_file_hash(f)
        if not is_file_registered(file_str, file_hash):
            new_files.append((f, file_hash))

    if not new_files:
        return {"files_ingested": 0, "files_skipped": len(files),
                "files_failed": 0, "documents_created": 0, "errors": []}

    try:
        _update_progress(phase_detail=f"Parsing {len(new_files)} markdown files")
        result = ingest_markdown_documents(directory, auto_embed=False)
        docs_imported = result.get("imported", 0)

        # Register all new files
        for f, file_hash in new_files:
            file_size = f.stat().st_size
            entity_count = docs_imported // max(len(new_files), 1)
            register_file(
                file_path=str(f),
                content_hash=file_hash,
                file_size=file_size,
                ingestion_type="markdown",
                entity_type="document",
                entity_count=entity_count,
                status="ingested",
            )

        _current_progress["files_processed"] += len(new_files)
        return {
            "files_ingested": len(new_files),
            "files_skipped": len(files) - len(new_files),
            "files_failed": 0,
            "documents_created": docs_imported,
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error("Markdown ingestion failed: %s", e)
        _current_progress["files_failed"] += len(new_files)
        return {
            "files_ingested": 0,
            "files_skipped": len(files) - len(new_files),
            "files_failed": len(new_files),
            "documents_created": 0,
            "errors": [f"Markdown dir: {str(e)[:100]}"],
        }


# ---------------------------------------------------------------------------
# Watched Files — living docs that update in place on change
# ---------------------------------------------------------------------------

# Repo-root files Janus should always have current knowledge of.
# Paths are relative to the app root (/app in Docker).
_WATCHED_FILES = ["CLAUDE.md", "README.md"]


def _scan_watched_files() -> dict:
    """Ingest or update watched repo-root files as documents.

    Unlike directory scanners, watched files use UPDATE semantics:
    if the document already exists and content changed, the document
    content is updated in place and old chunks are deleted so the
    embed phase picks up the new text.

    Returns:
        Dict with files_ingested, files_updated, files_skipped.
    """
    from services.ingestion.markdown_ingest import ingest_markdown
    from db.operations import create_document, get_connection
    from db.chunk_operations import delete_chunks

    app_root = Path(__file__).resolve().parent.parent
    ingested = 0
    updated = 0
    skipped = 0

    for filename in _WATCHED_FILES:
        file_path = app_root / filename
        if not file_path.is_file():
            continue

        file_str = str(file_path)
        file_hash = _compute_file_hash(file_path)
        file_size = file_path.stat().st_size

        # Check registry — skip if hash unchanged
        if is_file_registered(file_str, file_hash):
            skipped += 1
            continue

        # Parse the file
        parsed = ingest_markdown(file_str)
        if not parsed:
            continue

        title = parsed["title"]
        content = parsed["content"]

        # Check if a document with this title already exists
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM documents WHERE title = ?", (title,)
            ).fetchone()

        if row:
            # UPDATE existing document content + re-chunk
            doc_id = row["id"]
            with get_connection() as conn:
                conn.execute(
                    "UPDATE documents SET content = ?, updated_at = datetime('now') WHERE id = ?",
                    (content, doc_id),
                )
                conn.commit()
            # Delete old chunks so embed phase re-processes
            delete_chunks("document", doc_id)
            updated += 1
            logger.info("Watched file updated: %s (doc %s)", filename, doc_id[:8])
        else:
            # CREATE new document
            create_document(
                doc_type="file",
                source="upload",
                title=title,
                content=content,
                actor="imported",
            )
            ingested += 1
            logger.info("Watched file ingested: %s", filename)

        # Register / update in file registry
        register_file(
            file_path=file_str,
            content_hash=file_hash,
            file_size=file_size,
            ingestion_type="markdown",
            entity_type="document",
            entity_count=1,
            status="ingested",
        )

    if ingested or updated:
        logger.info("Watched files: %d ingested, %d updated, %d unchanged",
                     ingested, updated, skipped)

    return {"files_ingested": ingested, "files_updated": updated, "files_skipped": skipped}


# ---------------------------------------------------------------------------
# Auto-Import Platform Export (empty DB recovery)
# ---------------------------------------------------------------------------

def _auto_import_export() -> dict:
    """Auto-import newest platform export if DB is empty and export is recent.

    Trigger: items table has 0 rows AND newest export within threshold.
    Called at top of scan_and_ingest(), before external file scanning.
    Once items exist (after import or manual creation), never re-triggers.

    Returns:
        {"imported": True, "file": str, "result": str} on success,
        {"imported": False, "reason": str} otherwise.
    """
    # 1. Quick check: does the DB already have items?
    with get_connection() as conn:
        item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    if item_count > 0:
        return {"imported": False, "reason": "DB already has items"}

    # 2. Find newest platform export
    exports_dir = Path(__file__).resolve().parent.parent / "db" / "exports"
    if not exports_dir.is_dir():
        return {"imported": False, "reason": "No exports directory"}

    export_files = sorted(
        exports_dir.glob("platform_export_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not export_files:
        return {"imported": False, "reason": "No export files found"}

    newest = export_files[0]

    # 3. Check if newest is within threshold
    threshold_hours = int(get_setting("auto_import_threshold_hours") or "24")
    age_seconds = time.time() - newest.stat().st_mtime
    age_hours = age_seconds / 3600
    if age_hours > threshold_hours:
        return {
            "imported": False,
            "reason": f"Newest export is {age_hours:.1f}h old (threshold: {threshold_hours}h)",
        }

    # 4. Import the export
    logger.info("Auto-importing platform export: %s (%.1fh old)", newest.name, age_hours)
    try:
        from db.operations import import_platform_data
        result = import_platform_data(str(newest))
        logger.info("Auto-import result: %s", result)
    except Exception as e:
        logger.warning("Auto-import failed: %s", e)
        return {"imported": False, "reason": f"Import failed: {e}"}

    # 5. Embed imported items + tasks (populate Qdrant vectors)
    try:
        from services.bulk_embed import embed_all_items, embed_all_tasks, embed_all_domains
        embed_all_domains()
        embed_all_items()
        embed_all_tasks()
    except Exception as e:
        logger.warning("Auto-import embed failed (non-fatal): %s", e)

    return {"imported": True, "file": newest.name, "result": result}


# ---------------------------------------------------------------------------
# Scanner Core
# ---------------------------------------------------------------------------

def scan_and_ingest(auto_embed: bool = True, source: str = "startup") -> dict:
    """Scan all configured directories, ingest new files, optionally embed.

    Called at app startup and optionally during Slumber idle cycles.

    Pipeline:
        1. Read directory settings (claude, google_ai, markdown)
        2. For each directory: list files, check registry, ingest new ones
        3. If any new content and auto_embed=True:
           chunk_all_messages → chunk_all_documents →
           embed_all_messages → embed_all_documents
        4. Return summary stats

    Args:
        auto_embed: Whether to chunk + embed after ingestion. Default True.
        source: Caller identifier for logging ('startup' or 'slumber').

    Returns:
        Dict with files_found, files_ingested, files_skipped, files_failed,
        conversations_created, documents_created, embed_result, elapsed_seconds.
    """
    start_time = time.time()
    _reset_progress()

    # Phase 0: Auto-import platform export if DB is empty
    _update_progress(status="scanning", current_phase="export_check",
                     phase_detail="Checking for platform exports")
    export_result = _auto_import_export()
    if export_result.get("imported"):
        logger.info("Auto-imported platform export: %s", export_result["file"])

    _update_progress(status="scanning", current_phase="init",
                     phase_detail="Reading directory settings")

    # Read configured directories
    claude_dir = get_setting("claude_export_json_dir") or ""
    google_ai_dir = get_setting("ingestion_google_ai_dir") or ""
    markdown_dir = get_setting("ingestion_markdown_dir") or ""

    logger.info("Auto-ingest [%s]: claude=%s, google_ai=%s, markdown=%s",
                source, claude_dir, google_ai_dir, markdown_dir)

    total_ingested = 0
    total_skipped = 0
    total_failed = 0
    total_convs = 0
    total_docs = 0
    total_msgs = 0
    all_errors: list[str] = []

    # --- Scan Claude directory ---
    if claude_dir:
        _update_progress(status="ingesting", current_phase="claude",
                         phase_detail="Scanning Claude exports")
        claude_result = _scan_claude_dir(claude_dir)
        total_ingested += claude_result["files_ingested"]
        total_skipped += claude_result["files_skipped"]
        total_failed += claude_result["files_failed"]
        total_convs += claude_result.get("conversations_created", 0)
        total_msgs += claude_result.get("total_messages", 0)
        all_errors.extend(claude_result.get("errors", []))

    # --- Scan Google AI directory ---
    if google_ai_dir:
        _update_progress(status="ingesting", current_phase="google_ai",
                         phase_detail="Scanning Google AI exports")
        gai_result = _scan_google_ai_dir(google_ai_dir)
        total_ingested += gai_result["files_ingested"]
        total_skipped += gai_result["files_skipped"]
        total_failed += gai_result["files_failed"]
        total_convs += gai_result.get("conversations_created", 0)
        total_msgs += gai_result.get("total_messages", 0)
        all_errors.extend(gai_result.get("errors", []))

    # --- Scan Markdown directory ---
    if markdown_dir:
        _update_progress(status="ingesting", current_phase="markdown",
                         phase_detail="Scanning markdown files")
        md_result = _scan_markdown_dir(markdown_dir)
        total_ingested += md_result["files_ingested"]
        total_skipped += md_result["files_skipped"]
        total_failed += md_result["files_failed"]
        total_docs += md_result.get("documents_created", 0)
        all_errors.extend(md_result.get("errors", []))

    # --- Scan watched files (CLAUDE.md, README.md) ---
    _update_progress(status="ingesting", current_phase="watched_files",
                     phase_detail="Checking repo root docs")
    watched_result = _scan_watched_files()
    total_ingested += watched_result["files_ingested"]
    total_docs += watched_result["files_ingested"] + watched_result["files_updated"]
    total_skipped += watched_result["files_skipped"]

    _current_progress["files_found"] = total_ingested + total_skipped + total_failed

    # --- Chunk + Embed if new content was ingested or updated ---
    has_new_content = total_ingested > 0 or watched_result["files_updated"] > 0
    embed_result = {}
    if auto_embed and has_new_content:
        try:
            from services.bulk_embed import (
                chunk_all_messages, chunk_all_documents,
                embed_all_messages, embed_all_documents,
            )

            # Phase 1: Chunk messages
            _update_progress(status="chunking", current_phase="chunk_messages",
                             phase_detail="Chunking new messages", started_at=start_time)
            chunk_msg = chunk_all_messages()
            logger.info("Auto-ingest chunk messages: %s", chunk_msg)

            # Phase 2: Chunk documents
            _update_progress(status="chunking", current_phase="chunk_documents",
                             phase_detail="Chunking new documents",
                             embed_progress=chunk_msg, started_at=start_time)
            chunk_doc = chunk_all_documents()
            logger.info("Auto-ingest chunk documents: %s", chunk_doc)

            # Phase 3: Embed messages (long pole — can take 20+ min)
            _update_progress(status="embedding", current_phase="embed_messages",
                             phase_detail="Embedding message chunks",
                             embed_progress=chunk_doc, started_at=start_time)
            embed_msg = embed_all_messages()
            logger.info("Auto-ingest embed messages: %s", embed_msg)

            # Phase 4: Embed documents
            _update_progress(status="embedding", current_phase="embed_documents",
                             phase_detail="Embedding document chunks",
                             embed_progress=embed_msg, started_at=start_time)
            embed_doc = embed_all_documents()
            logger.info("Auto-ingest embed documents: %s", embed_doc)

            embed_result = {
                "chunk_messages": chunk_msg,
                "chunk_documents": chunk_doc,
                "embed_messages": embed_msg,
                "embed_documents": embed_doc,
            }
            _update_progress(status="complete", embed_progress=embed_doc,
                             started_at=start_time)

        except Exception as e:
            logger.warning("Auto-ingest embed failed: %s", e)
            all_errors.append(f"Embed: {str(e)[:100]}")
            _update_progress(status="complete", started_at=start_time)
    else:
        _update_progress(status="complete", started_at=start_time)

    elapsed = round(time.time() - start_time, 1)
    _current_progress["elapsed_seconds"] = elapsed
    _current_progress["errors"] = all_errors

    summary = {
        "export_imported": export_result if export_result.get("imported") else None,
        "files_found": total_ingested + total_skipped + total_failed,
        "files_ingested": total_ingested,
        "files_skipped": total_skipped,
        "files_failed": total_failed,
        "conversations_created": total_convs,
        "documents_created": total_docs,
        "total_messages": total_msgs,
        "embed_result": embed_result,
        "errors": all_errors,
        "elapsed_seconds": elapsed,
    }

    if total_ingested > 0 or total_failed > 0:
        logger.info("Auto-ingest [%s] complete: %s", source, summary)
    else:
        logger.debug("Auto-ingest [%s]: nothing new", source)

    return summary
