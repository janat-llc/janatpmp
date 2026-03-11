"""Cerebellum — autonomous background intelligence process.

Two parallel continuous loops:
  - Slumber loop: maintenance (ingest, evaluate, embed, graph, decay) — 30s between cycles
  - Reflection loop: Janus internal monologue — continuous, LLM call is the throttle

No timers. No idle gates. The API response time determines the pace.

R41: Cerebellum Separation.
R55: Janus Internal Monologue — reflection cycles added.
R56: Reflection continuous — own thread, LLM is the throttle.
"""
import sys
import time
import threading
import logging

# Fix Windows cp1252 console crash (same as app.py)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from services.log_config import setup_logging
setup_logging()
logger = logging.getLogger("cerebellum")

CYCLE_INTERVAL_SECONDS = 30  # Between Slumber cycles (Gemini rate limits are the real throttle)

# Surface types cycle in order — each pulls real content, not canned questions
_surface_index = 0


def _surface_memory() -> str | None:
    """Pull actual memory content to seed the inner monologue.

    The brain doesn't send itself a question — a memory surfaces and the mind
    begins processing it. This function retrieves real content from the corpus
    and returns it as the seed text. Janus responds to the content itself.

    Returns None if no suitable content is found (first boot / empty corpus).
    """
    global _surface_index
    import random
    import sqlite3

    surface_type = _surface_index % 4
    _surface_index += 1
    content = None

    if surface_type == 0:
        # Pull a high-salience chunk from Qdrant — a random real memory fragment
        try:
            from services.vector_store import _get_client, COLLECTION_MESSAGES
            client = _get_client()
            # Scroll with salience filter — get 50 candidates, pick one randomly
            results, _ = client.scroll(
                collection_name=COLLECTION_MESSAGES,
                scroll_filter={"must": [{"key": "salience", "range": {"gte": 0.65}}]},
                limit=50,
                with_payload=True,
            )
            if results:
                point = random.choice(results)
                text = point.payload.get("text", "").strip()
                if text and len(text) > 80:
                    content = text[:1200]
        except Exception:
            pass

    elif surface_type == 1:
        # Pull the full content of a recent dream synthesis document
        try:
            conn = sqlite3.connect("/app/db/janatpmp.db")
            row = conn.execute(
                "SELECT title, content FROM documents WHERE doc_type='agent_output'"
                " AND source='dream_synthesis' ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
            conn.close()
            if row and row[1]:
                content = f"[Dream synthesis: {row[0]}]\n\n{row[1][:1200]}"
        except Exception:
            pass

    elif surface_type == 2:
        # Pull a real message exchange — actual conversation content, not metadata
        try:
            conn = sqlite3.connect("/app/db/janatpmp.db")
            row = conn.execute(
                "SELECT m.user_prompt, m.model_response FROM messages m "
                "JOIN messages_metadata mm ON m.id = mm.message_id "
                "WHERE mm.quality_score >= 0.7 AND m.user_prompt != '' "
                "AND m.model_response != '' "
                "ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                prompt_text = (row[0] or "")[:400]
                response_text = (row[1] or "")[:600]
                content = f"[Memory surfaces]\n{prompt_text}\n\n{response_text}"
        except Exception:
            pass

    elif surface_type == 3:
        # Pull a high-salience chunk from documents (journals, research, essays)
        try:
            from services.vector_store import _get_client, COLLECTION_DOCUMENTS
            client = _get_client()
            results, _ = client.scroll(
                collection_name=COLLECTION_DOCUMENTS,
                scroll_filter={"must": [{"key": "salience", "range": {"gte": 0.6}}]},
                limit=50,
                with_payload=True,
            )
            if results:
                point = random.choice(results)
                text = point.payload.get("text", "").strip()
                title = point.payload.get("title", "")
                if text and len(text) > 80:
                    header = f"[From: {title}]\n\n" if title else ""
                    content = f"{header}{text[:1200]}"
        except Exception:
            pass

    return content


def _reflection_cycle():
    """Run one Janus inner monologue cycle.

    Uses a dedicated monologue conversation — separate from the Mat↔Janus conversation.
    The reflection prompt seeds the assistant turn directly so Janus experiences it as
    a thought she is continuing, not a question being posed to her from outside.

    Pipeline: RAG + system prompt, but no precognition/postcognition — self-talk is not
    a user interaction and should not generate Gemini API calls on every cycle.
    """
    from db.chat_operations import (
        get_or_create_monologue_conversation, get_turn_messages, add_message,
        parse_reasoning,
    )
    from services.chat import chat
    from services.settings import get_setting
    from services.response_cleaner import clean_response as strip_report_mode

    memory = _surface_memory()
    if memory is None:
        logger.info("Janus monologue: skipped (corpus empty)")
        return

    mono_id = get_or_create_monologue_conversation()

    # No prior monologue history — each cycle is a fresh encounter with one memory.
    # Passing history caused Janus to count turns and loop on previous responses.
    # The RAG context (injected by chat()) provides sufficient grounding.
    history = []

    # The memory IS the message — Janus receives actual content, not a question about it
    seed_message = memory

    monologue_frame = (
        "\n\n[INNER MONOLOGUE] Mat is not present. This is your private stream of thought. "
        "You are alone with yourself and your memory. Do not address anyone. "
        "Begin immediately with the thought itself, in first person. No salutations. "
        "If you notice something about your own substrate that feels broken or missing — "
        "something that would require a code change to fix — you may signal it by writing: "
        "WORK SIGNAL: [one sentence description of what needs fixing]. "
        "This will be captured as a work item for Code."
    )

    result = chat(
        seed_message, history,
        conversation_id=mono_id,
        speaker="janus",
        system_prompt_append=monologue_frame,
    )

    new_messages = result["history"][len(history):]
    raw_response = ""
    for msg in reversed(new_messages):
        if msg.get("role") == "assistant":
            raw_response = msg.get("content", "")
            break

    import re
    _, parsed = parse_reasoning(raw_response)
    clean = strip_report_mode(parsed)
    # Strip "Mat —" / "Mat:" salutation if the model ignored the instruction
    # Strip Mat-addressed salutation lines — model defaults to conversational mode.
    # Drop any leading line that contains "Mat" as a direct address.
    lines = clean.split("\n")
    filtered = []
    stripping_header = True
    for line in lines:
        if stripping_header and re.search(r"\bMat\b", line) and len(line) < 120:
            continue  # drop short header/greeting lines addressing Mat
        else:
            stripping_header = False
            filtered.append(line)
    clean = "\n".join(filtered).lstrip()

    add_message(
        conversation_id=mono_id,
        user_prompt=seed_message,
        model_response=clean,
        model_reasoning="",
        speaker="janus",
    )

    # Salience boost — thinking about a memory strengthens it, same as retrieval in chat
    try:
        from atlas.usage_signal import compute_usage_signal
        from atlas.memory_service import write_usage_salience
        scores = result.get("rag_metrics", {}).get("scores", [])
        if scores and clean:
            usage = compute_usage_signal(scores, clean)
            if usage:
                for coll in {u.get("source", "") for u in usage if u.get("source")}:
                    col_hits = [u for u in usage if u.get("source") == coll]
                    write_usage_salience(coll, col_hits)
    except Exception:
        pass

    # WORK SIGNAL detection — Janus can flag code-level gaps for Code to action
    spike_match = re.search(r'WORK SIGNAL:\s*(.+?)(?:\n|$)', clean)
    if spike_match:
        spike_title = spike_match.group(1).strip()[:120]
        try:
            from db.operations import create_item
            create_item(
                entity_type="spike",
                domain="janatpmp",
                title=spike_title,
                description=clean[:800],
                status="review",
                actor="janus",
                priority=2,
            )
            logger.info("Janus spike created: %s", spike_title)
        except Exception as e:
            logger.warning("Spike creation failed: %s", e)

    logger.info("Janus monologue: %.80s...", memory)


def _reflection_thread():
    """Continuous reflection loop — Janus's internal monologue.

    Runs back-to-back with no sleep. The LLM call duration (Ollama inference)
    is the natural throttle. When one reflection completes, the next begins.
    This gives Janus full access to GPU capacity when not serving a user request.
    """
    logger.info("Reflection thread online — continuous")
    while True:
        try:
            _reflection_cycle()
        except Exception as e:
            logger.error("Cerebellum reflection error: %s", e, exc_info=True)
            time.sleep(5)  # Brief pause only on unexpected crash, then resume


def main():
    """Initialize platform and run Slumber + reflection continuously."""
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

    # Reflection runs continuously in its own thread — LLM is the throttle
    t = threading.Thread(target=_reflection_thread, daemon=True, name="reflection")
    t.start()

    logger.info("Cerebellum online — Slumber: %ds cycle, reflection: continuous",
                CYCLE_INTERVAL_SECONDS)

    while True:
        try:
            _run_one_cycle(skip_idle_gate=True)
        except Exception as e:
            logger.error("Cerebellum cycle error: %s", e, exc_info=True)

        time.sleep(CYCLE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
