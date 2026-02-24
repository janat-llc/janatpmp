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
    except Exception:
        logger.warning("Qdrant not available -- vector search disabled")

    # Slumber Cycle daemon (background cognitive telemetry)
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
