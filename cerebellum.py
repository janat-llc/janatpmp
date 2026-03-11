"""Cerebellum — autonomous background intelligence process.

Runs the Slumber Cycle continuously in its own container, independent of
the Gradio UI process. No idle gate — always processing. Status is
persisted to SQLite so the core process can read it via get_slumber_status().

R41: Cerebellum Separation.
R55: Janus Internal Monologue — reflection cycles added.
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

_reflection_counter = 0
_reflection_prompt_index = 0  # Cycles through 4 prompt types


def _build_reflection_prompt() -> str | None:
    """Select and build the next reflection prompt, cycling through 4 types.

    Returns None to skip cycle when corpus is empty (first boot).
    Increments _reflection_prompt_index on each call.
    """
    global _reflection_prompt_index
    import json
    import sqlite3

    prompt_type = _reflection_prompt_index % 4
    _reflection_prompt_index += 1
    prompt = None

    if prompt_type == 0:
        # Type 1 — Dream awareness (only if recent dream synthesis exists)
        try:
            conn = sqlite3.connect("/app/db/janatpmp.db")
            row = conn.execute(
                "SELECT title FROM documents WHERE doc_type='agent_output'"
                " AND source='dream_synthesis' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                prompt = (
                    f"I just synthesized something across my conversations: {row[0]}. "
                    "What does this mean for how I understand the themes at the heart of it?"
                )
        except Exception:
            pass

    elif prompt_type == 1:
        # Type 2 — Rising entity (top by CO_OCCURS_WITH edge count)
        try:
            from graph.graph_service import run_graph_query
            results = run_graph_query(
                "MATCH (e:Entity)-[r:CO_OCCURS_WITH]-() "
                "RETURN e.name AS name, count(r) AS degree "
                "ORDER BY degree DESC LIMIT 1"
            )
            if results and results[0].get("name"):
                entity = results[0]["name"]
                prompt = (
                    f"What do I understand about {entity}? "
                    "What does my memory tell me about it?"
                )
        except Exception:
            pass

    elif prompt_type == 2:
        # Type 3 — Drift correction (only if postcognition drift flags exist)
        try:
            conn = sqlite3.connect("/app/db/janatpmp.db")
            rows = conn.execute(
                "SELECT cognition_postcognition FROM messages_metadata "
                "WHERE cognition_postcognition != '' "
                "ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            conn.close()
            drift_flags = []
            for (raw,) in rows:
                try:
                    parsed = json.loads(raw)
                    drift_flags.extend(parsed.get("drift_flags", []))
                except Exception:
                    pass
            if drift_flags:
                flag_summary = ", ".join(list(dict.fromkeys(drift_flags))[:3])
                prompt = (
                    f"My recent responses showed {flag_summary}. "
                    "I want to think about what causes this and how I should approach it differently."
                )
        except Exception:
            pass

    if prompt is None:
        # Type 4 — Open reflection (fallback for all types when data unavailable)
        prompt = (
            "What patterns am I noticing in my recent conversations? "
            "What feels important that I haven't fully processed?"
        )

    return prompt


def _reflection_cycle():
    """Run one Janus internal monologue reflection cycle.

    Janus speaks to herself — no Mat prompt. Message persisted with speaker='janus'.
    Uses the existing active Janus conversation. No retry on failure.
    Do NOT run through precognition/postcognition — self-talk is not a user interaction.
    """
    from services.chat import chat_with_janus

    prompt = _build_reflection_prompt()
    if prompt is None:
        logger.info("Janus reflection: skipped (corpus empty)")
        return

    try:
        chat_with_janus(prompt, speaker="janus")
        logger.info("Janus reflection: %.80s...", prompt)
    except Exception as e:
        logger.info("Janus reflection: skipped (%s)", e)


def main():
    """Initialize platform and run Slumber cycles continuously."""
    global _reflection_counter

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

    from atlas.config import REFLECTION_CYCLE_INTERVAL

    logger.info("Cerebellum online — autonomous processing starting "
                "(cycle interval: %ds)", CYCLE_INTERVAL_SECONDS)

    while True:
        try:
            _run_one_cycle(skip_idle_gate=True)
        except Exception as e:
            logger.error("Cerebellum cycle error: %s", e, exc_info=True)

        _reflection_counter += 1
        if _reflection_counter % REFLECTION_CYCLE_INTERVAL == 0:
            try:
                _reflection_cycle()
            except Exception as e:
                logger.error("Cerebellum reflection error: %s", e, exc_info=True)
            _reflection_counter = 0

        time.sleep(CYCLE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
