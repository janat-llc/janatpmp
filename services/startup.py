"""Platform startup — initialization sequence for JANATPMP.

Strict ordering:
  1. initialize_core()       — DB, settings, cleanup, Janus (BLOCKING, fast)
  2. initialize_services()   — Qdrant, Slumber, Neo4j (optional, graceful degrade)
  3. start_auto_ingest()     — background thread for scan_and_ingest (non-blocking)
  4. is_auto_ingest_complete() — poll status for UI banner
"""

import logging
import threading

logger = logging.getLogger(__name__)

# --- Module-level state for background auto-ingest ---
_ingest_thread: threading.Thread | None = None
_ingest_complete: bool = False
_ingest_result: dict = {}
_ingest_error: str = ""


def _auto_restore_platform_data() -> None:
    """Auto-import the latest platform export if items table is empty.

    After a DB reset, conversations/documents are re-ingested via auto_ingest,
    but items/tasks/relationships need to come from platform exports. This checks
    db/exports/ for the most recent export and imports it if the items table is empty.
    """
    from pathlib import Path

    try:
        from db.operations import get_connection, import_platform_data

        with get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        if count > 0:
            return  # Items exist, no restore needed

        exports_dir = Path("/app/db/exports")
        if not exports_dir.exists():
            return

        exports = sorted(exports_dir.glob("platform_export_*.json"), reverse=True)
        if not exports:
            return

        latest = exports[0]
        result = import_platform_data(str(latest))
        logger.info("Auto-restored platform data from %s: %s", latest.name, result)
    except Exception as e:
        logger.warning("Auto-restore platform data failed: %s", e)


def _fix_imported_message_timestamps() -> None:
    """One-time fix: set messages.created_at from parent conversation dates.

    The Claude import pipeline didn't set created_at on message INSERT,
    so all 8,591+ imported messages got datetime('now') — the import
    timestamp. This sets them to their parent conversation's created_at.
    Idempotent — safe to run multiple times (no-op if already fixed).
    """
    try:
        from db.operations import get_connection

        with get_connection() as conn:
            # Check if any messages still have the wrong timestamp pattern
            # (all messages in a conversation having the exact same date as
            # the import date, different from the conversation's created_at)
            broken = conn.execute(
                "SELECT COUNT(*) FROM messages m "
                "JOIN conversations c ON m.conversation_id = c.id "
                "WHERE c.source IN ('claude_export', 'imported') "
                "AND date(m.created_at) <> date(c.created_at)"
            ).fetchone()[0]

            if broken == 0:
                return  # Already fixed

            conn.execute(
                "UPDATE messages SET created_at = ("
                "  SELECT c.created_at FROM conversations c"
                "  WHERE c.id = messages.conversation_id"
                ") WHERE conversation_id IN ("
                "  SELECT id FROM conversations"
                "  WHERE source IN ('claude_export', 'imported')"
                ")"
            )
            conn.commit()
            logger.info("Fixed %d imported message timestamps", broken)
    except Exception as e:
        logger.warning("Fix imported message timestamps failed: %s", e)


def initialize_core() -> None:
    """Initialize database, settings, cleanup, and Janus conversation.

    BLOCKING. Must complete before UI can build (reads from SQLite at build time).
    Typical time: <1 second on warm DB.
    """
    from db.operations import init_database, cleanup_cdc_outbox
    from services.settings import init_settings
    from services.log_config import cleanup_old_logs
    from db.chat_operations import get_or_create_janus_conversation

    init_database()
    init_settings()
    cleanup_old_logs()
    cleanup_cdc_outbox()
    get_or_create_janus_conversation()

    # Auto-restore platform data if items table is empty and exports exist
    _auto_restore_platform_data()

    # Bootstrap metadata rows so Slumber can evaluate imported messages
    from db.chat_operations import backfill_message_metadata
    total_created = 0
    while True:
        result = backfill_message_metadata(batch_size=1000)
        created = int(result.split()[1]) if result.startswith("Created") else 0
        total_created += created
        if created == 0:
            break
    if total_created:
        logger.info("Metadata bootstrap: created %d rows", total_created)

    # R40: Rebuild FTS indexes if out of sync (imported messages may have gaps)
    from db.chat_operations import rebuild_messages_fts, rebuild_documents_fts
    fts_msg = rebuild_messages_fts()
    if "Rebuilt" in fts_msg:
        logger.info("FTS: %s", fts_msg)
    fts_doc = rebuild_documents_fts()
    if "Rebuilt" in fts_doc:
        logger.info("FTS: %s", fts_doc)

    logger.info("Core initialized: database, settings, Janus conversation")


def initialize_services() -> None:
    """Initialize optional services — Qdrant, Slumber, Neo4j.

    Each service is isolated in try/except for graceful degradation.
    These are independent and can fail without blocking the app.
    """
    # Qdrant vector store collections
    try:
        from services.vector_store import ensure_collections
        ensure_collections()

        # R19 Bootstrap lifecycle: check if Qdrant is populated
        from services.vector_store import _get_client, COLLECTION_MESSAGES
        from services.settings import set_setting
        client = _get_client()
        info = client.get_collection(COLLECTION_MESSAGES)
        if info.points_count == 0:
            set_setting("janus_lifecycle_state", "configuring")
            logger.info("Bootstrap: Qdrant empty, state -> configuring")
    except Exception:
        logger.warning("Qdrant not available -- vector search disabled")

    # Slumber Cycle daemon (background cognitive telemetry)
    # R41: When cerebellum container handles Slumber, skip in-process daemon
    import os
    if os.getenv("CEREBELLUM_EXTERNAL", "").lower() == "true":
        logger.info("Slumber daemon skipped — handled by cerebellum container")
    else:
        from services.slumber import start_slumber
        start_slumber()

    # Neo4j graph schema + CDC consumer
    try:
        from graph.graph_service import ensure_schema
        ensure_schema()
        from graph.cdc_consumer import start_cdc_consumer
        start_cdc_consumer()
        logger.info("Neo4j graph service and CDC consumer started")
    except Exception:
        logger.warning("Neo4j not available -- graph features disabled")


def start_auto_ingest() -> None:
    """Launch auto-ingest in a background daemon thread.

    Pattern follows services/slumber.py start_slumber(): module-level guard,
    daemon thread, try/except isolation. The thread runs scan_and_ingest()
    once and exits. UI polls via is_auto_ingest_complete().
    """
    global _ingest_thread
    if _ingest_thread is not None:
        return

    def _run_ingest():
        global _ingest_complete, _ingest_result, _ingest_error
        try:
            from services.auto_ingest import scan_and_ingest
            _ingest_result = scan_and_ingest(auto_embed=True, source="startup")
            logger.info("Background auto-ingest complete: %s", _ingest_result)

            # R19 Bootstrap lifecycle: configuring → sleeping after ingest
            from services.settings import get_setting, set_setting
            if get_setting("janus_lifecycle_state") == "configuring":
                set_setting("janus_lifecycle_state", "sleeping")
                logger.info("Bootstrap: ingest complete, state -> sleeping")
        except Exception as e:
            _ingest_error = str(e)
            logger.warning("Background auto-ingest failed: %s", e)
        finally:
            _ingest_complete = True

    _ingest_thread = threading.Thread(
        target=_run_ingest, daemon=True, name="auto-ingest-startup",
    )
    _ingest_thread.start()
    logger.info("Background auto-ingest thread started")


def is_auto_ingest_complete() -> bool:
    """Check if the background auto-ingest has finished.

    Returns True when the background thread has exited (success or failure).
    Returns True if start_auto_ingest() was never called.
    """
    if _ingest_thread is None:
        return True
    return _ingest_complete
