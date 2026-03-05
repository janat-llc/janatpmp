"""Cerebellum — autonomous background intelligence process.

Runs the Slumber Cycle continuously in its own container, independent of
the Gradio UI process. No idle gate — always processing. Status is
persisted to SQLite so the core process can read it via get_slumber_status().

R41: Cerebellum Separation.
"""
import sys
import time
import logging

# Fix Windows cp1252 console crash (same as app.py)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from services.log_config import setup_logging
setup_logging()
logger = logging.getLogger("cerebellum")

CYCLE_INTERVAL_SECONDS = 30  # Between cycles (Gemini rate limits are the real throttle)


def main():
    """Initialize platform and run Slumber cycles continuously."""
    from services.startup import initialize_core
    initialize_core()

    # Initialize Qdrant (vector ops needed by propagate, prune, ingest)
    try:
        from services.vector_store import ensure_collections
        ensure_collections()
    except Exception:
        logger.warning("Qdrant not available — vector features disabled")

    # Initialize Neo4j (graph ops needed by relate, weave, co-occur, extract)
    try:
        from graph.graph_service import ensure_schema
        ensure_schema()
        from graph.cdc_consumer import start_cdc_consumer
        start_cdc_consumer()
    except Exception:
        logger.warning("Neo4j not available — graph features disabled")

    # Restore cycle counters from previous run
    from services.slumber import _restore_counters_from_db, _run_one_cycle
    _restore_counters_from_db()

    logger.info("Cerebellum online — autonomous processing starting "
                "(cycle interval: %ds)", CYCLE_INTERVAL_SECONDS)

    while True:
        try:
            _run_one_cycle(skip_idle_gate=True)
        except Exception as e:
            logger.error("Cerebellum cycle error: %s", e, exc_info=True)
        time.sleep(CYCLE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
