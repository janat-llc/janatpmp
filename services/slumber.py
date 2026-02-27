"""Slumber Cycle — background evaluation during idle periods.

When the system is idle (no chat activity for IDLE_THRESHOLD seconds), the
Slumber Cycle wakes up and evaluates messages that lack quality scores.
R22 (First Light) upgrades scoring from heuristic to LLM-powered evaluation
via Gemini Flash Lite, with heuristic fallback when Gemini is unreachable.

This is the substrate for self-improving retrieval: quality scores feed into
salience calculations, keywords enable future semantic clustering, and the
whole system gets smarter while the user sleeps.
"""

import re
import json
import time
import logging
import threading
from collections import Counter
from datetime import datetime

logger = logging.getLogger(__name__)

# --- Configuration (overridden by settings DB at runtime) ---
IDLE_THRESHOLD_SECONDS = 300   # 5 minutes of no chat activity
EVAL_BATCH_SIZE = 20           # Messages per cycle
CYCLE_INTERVAL_SECONDS = 60    # Check idle state every minute

_last_activity = time.monotonic()
_slumber_thread = None

# --- Slumber activity state (R22) — read by UI via get_slumber_status() ---
_slumber_status = {
    "state": "idle",           # idle | ingesting | evaluating | propagating | relating | pruning | extracting | dreaming | weaving | linking | decaying
    "last_cycle_at": None,     # ISO timestamp of last completed cycle
    "last_evaluated": 0,       # Messages evaluated in last cycle
    "last_propagated": 0,      # Messages propagated in last cycle
    "last_related": 0,         # Edges created in last cycle
    "last_pruned": 0,          # Vectors pruned in last cycle
    "eval_method": "",         # "gemini" or "heuristic"
    "total_evaluated": 0,      # Cumulative since startup
    "error": "",               # Last error message (if any)
    # Dream Synthesis (R24)
    "last_dreamed": 0,         # Insights created in last cycle
    "dream_edges": 0,          # Graph edges created in last cycle
    "total_dreams": 0,         # Cumulative insights since startup
    # Graph Weave (R27)
    "last_woven": 0,           # Edges woven in last cycle
    "total_woven": 0,          # Cumulative edges since startup
    "_cycle_count": 4,         # Internal: starts at INTERVAL-1 so first dream/weave fires on first eligible cycle
    # Entity Extraction (R29)
    "last_extracted": 0,       # Entities created/updated in last cycle
    "total_extracted": 0,      # Cumulative entities since startup
    "_extract_cycle_count": 2, # Internal: starts at INTERVAL-1 so first extraction fires on first eligible cycle
    # Co-Occurrence Linking (R31)
    "last_cooccurred": 0,      # Edges created/updated in last cycle
    "total_cooccurred": 0,     # Cumulative edges since startup
    "_cooccur_cycle_count": 2, # Internal: starts at INTERVAL-1 (COOCCURRENCE_CYCLE_INTERVAL=3)
    # Entity Salience Decay (R31)
    "last_decayed": 0,         # Entities decayed in last cycle
    "total_decayed": 0,        # Cumulative decays since startup
    "_decay_cycle_count": 4,   # Internal: starts at INTERVAL-1 (ENTITY_DECAY_CYCLE_INTERVAL=5)
}

# Words too common to be meaningful keywords
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "that", "this",
    "these", "those", "it", "its", "i", "me", "my", "we", "our", "you",
    "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "what", "which", "who", "whom", "whose", "also", "like", "about",
    "one", "two", "three", "new", "get", "make", "know", "think", "say",
})

_MIN_WORD_LEN = 3


def touch_activity():
    """Called on every chat message to reset idle timer."""
    global _last_activity
    _last_activity = time.monotonic()


def get_slumber_status() -> dict:
    """Get current Slumber Cycle status.

    Returns the live state of the background Slumber daemon including
    current activity state, last cycle timestamp, evaluation counts,
    and any recent errors. Thread-safe read (Python GIL).

    Returns:
        Dict with keys: state, last_cycle_at, last_evaluated,
        last_propagated, last_related, last_pruned, eval_method,
        total_evaluated, last_dreamed, dream_edges, total_dreams,
        last_woven, total_woven, last_extracted, total_extracted,
        last_cooccurred, total_cooccurred, last_decayed, total_decayed,
        error.
    """
    return dict(_slumber_status)


def _is_idle() -> bool:
    """Check if the system has been idle long enough to start evaluation."""
    threshold = IDLE_THRESHOLD_SECONDS
    try:
        from services.settings import get_setting
        val = get_setting("slumber_idle_threshold")
        if val:
            threshold = int(val)
    except Exception:
        pass
    return (time.monotonic() - _last_activity) > threshold


DEEP_IDLE_THRESHOLD_SECONDS = 600  # 10 minutes — for Gemini-heavy phases


def _is_deep_idle() -> bool:
    """Check if system has been idle long enough for Gemini-heavy phases.

    Deep idle requires 10 minutes of inactivity (vs 5 min for light phases).
    Gates extract, dream, and weave to avoid competing with active chat.
    """
    return (time.monotonic() - _last_activity) > DEEP_IDLE_THRESHOLD_SECONDS


def _get_batch_size() -> int:
    """Get configured batch size from settings."""
    try:
        from services.settings import get_setting
        val = get_setting("slumber_batch_size")
        if val:
            return int(val)
    except Exception:
        pass
    return EVAL_BATCH_SIZE


def _extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """TF-based keyword extraction. No external dependencies.

    Tokenizes, removes stopwords, counts frequencies, returns top N.
    """
    words = re.findall(r"[a-z][a-z0-9_]+", text.lower())
    filtered = [w for w in words if len(w) >= _MIN_WORD_LEN and w not in _STOPWORDS]
    counts = Counter(filtered)
    return [w for w, _ in counts.most_common(top_n)]


def _score_heuristic(user_prompt: str, model_response: str, model_reasoning: str) -> float:
    """Fast heuristic quality score (0.0-1.0).

    Factors:
    - Response substance (not too short, not boilerplate)
    - Reasoning presence and depth
    - Response-to-prompt ratio (very short responses to long prompts score lower)
    - Repetition detection (repeated phrases reduce score)
    """
    if not model_response:
        return 0.0

    score = 0.5  # Baseline

    # Reasoning bonus: thinking tokens present = higher quality
    if model_reasoning:
        reasoning_len = len(model_reasoning)
        if reasoning_len > 500:
            score += 0.2
        elif reasoning_len > 100:
            score += 0.1
        else:
            score += 0.05

    # Response substance
    response_words = len(model_response.split())
    if response_words < 10:
        score -= 0.15  # Very short response
    elif response_words > 100:
        score += 0.1   # Substantive response

    # Prompt-response ratio: very short response to long prompt = lower quality
    prompt_words = len(user_prompt.split()) if user_prompt else 1
    ratio = response_words / max(prompt_words, 1)
    if ratio < 0.3 and prompt_words > 20:
        score -= 0.1  # Terse response to detailed prompt

    # Repetition penalty: check for repeated 4-grams
    words = model_response.lower().split()
    if len(words) > 20:
        ngrams = [" ".join(words[i:i+4]) for i in range(len(words) - 3)]
        ngram_counts = Counter(ngrams)
        repeated = sum(1 for c in ngram_counts.values() if c > 2)
        if repeated > 3:
            score -= 0.15

    # Boilerplate detection
    boilerplate_phrases = [
        "i hope this helps", "let me know if", "feel free to",
        "i'd be happy to", "is there anything else",
    ]
    lower_response = model_response.lower()
    boilerplate_count = sum(1 for p in boilerplate_phrases if p in lower_response)
    if boilerplate_count >= 2:
        score -= 0.1

    return max(0.0, min(1.0, round(score, 3)))


def _evaluate_batch() -> int:
    """Evaluate a batch of messages — LLM-powered or heuristic fallback.

    R22: First Light. Uses Gemini Flash Lite for evaluation when enabled
    and a valid API key is configured. Falls back to heuristic scoring
    on any failure or when disabled.

    Returns:
        Number of messages evaluated (0 if none pending).
    """
    from db.operations import get_connection
    from db.chat_operations import update_message_metadata
    from services.settings import get_setting

    batch_size = _get_batch_size()
    use_llm = (get_setting("slumber_eval_enabled") or "true").lower() == "true"

    with get_connection() as conn:
        cursor = conn.cursor()
        # Find messages with metadata but no quality score
        cursor.execute("""
            SELECT mm.message_id, m.user_prompt, m.model_response, m.model_reasoning
            FROM messages_metadata mm
            JOIN messages m ON mm.message_id = m.id
            WHERE mm.quality_score IS NULL
            ORDER BY m.created_at ASC
            LIMIT ?
        """, (batch_size,))
        rows = cursor.fetchall()

    if not rows:
        return 0

    evaluated = 0
    for row in rows:
        msg_id = row["message_id"]
        user_prompt = row["user_prompt"] or ""
        model_response = row["model_response"] or ""
        model_reasoning = row["model_reasoning"] or ""

        if use_llm:
            from services.slumber_eval import evaluate_message
            result = evaluate_message(user_prompt, model_response, model_reasoning)
            quality = result["quality_score"]
            keywords_from_topics = result.get("topics", [])
        else:
            quality = _score_heuristic(user_prompt, model_response, model_reasoning)
            result = {
                "fallback": True, "rationale": "", "topics": [],
                "emotional_register": "", "eval_provider": "heuristic",
                "eval_model": "",
            }
            keywords_from_topics = []

        # Extract TF keywords, merge with LLM topics (LLM first, TF fills)
        combined_text = f"{user_prompt} {model_response}"
        tf_keywords = _extract_keywords(combined_text, top_n=10)
        merged_keywords = keywords_from_topics + [
            k for k in tf_keywords if k not in keywords_from_topics
        ]

        # Update metadata with quality score + evaluation details
        update_message_metadata(
            message_id=msg_id,
            quality_score=quality,
            keywords=json.dumps(merged_keywords[:10]),
            eval_rationale=result.get("rationale", ""),
            eval_emotional_register=result.get("emotional_register", ""),
            eval_provider=result.get("eval_provider", ""),
            eval_model=result.get("eval_model", ""),
        )
        evaluated += 1

        # Rate limiting: 0.5s between LLM calls within a batch
        if use_llm and not result.get("fallback", False):
            time.sleep(0.5)

    method = "gemini" if use_llm else "heuristic"
    logger.info("Slumber cycle: evaluated %d messages (method=%s)", evaluated, method)
    return evaluated


def _propagate_batch():
    """Bridge quality_score → Qdrant salience.

    Reads messages_metadata where quality_score is set but salience not yet synced.
    Applies multiplier based on quality range, writes to Qdrant payload.
    """
    from db.operations import get_connection
    from db.chat_operations import update_message_metadata

    batch_size = _get_batch_size()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT mm.message_id, mm.quality_score
            FROM messages_metadata mm
            WHERE mm.quality_score IS NOT NULL
              AND mm.salience_synced = 0
            ORDER BY mm.created_at ASC
            LIMIT ?
        """, (batch_size,)).fetchall()

    if not rows:
        return

    try:
        from services.vector_store import _get_client, COLLECTION_MESSAGES
        client = _get_client()
    except Exception as e:
        logger.debug("Slumber propagate: Qdrant unavailable: %s", e)
        return

    propagated = 0
    for row in rows:
        msg_id = row["message_id"]
        quality = row["quality_score"]

        # R16: read chunk point_ids from chunks table
        try:
            with get_connection() as conn:
                chunk_rows = conn.execute(
                    "SELECT point_id FROM chunks "
                    "WHERE entity_type='message' AND entity_id=?",
                    (msg_id,),
                ).fetchall()

            if chunk_rows:
                point_ids = [r["point_id"] for r in chunk_rows if r["point_id"]]
            else:
                # Legacy fallback for pre-R16 messages without chunks
                point_ids = [
                    msg_id[:8] + "-" + msg_id[8:12] + "-" + msg_id[12:16]
                    + "-" + msg_id[16:20] + "-" + msg_id[20:]
                ]

            if not point_ids:
                continue
        except Exception:
            continue

        # Read current salience from first chunk (representative)
        try:
            points = client.retrieve(
                COLLECTION_MESSAGES, ids=point_ids[:1], with_payload=True,
            )
            if not points:
                continue  # Not yet in Qdrant, skip
            current_salience = points[0].payload.get("salience", 0.5)
        except Exception:
            continue

        # Apply quality → salience mapping
        if quality < 0.15:
            new_salience = current_salience * 0.3        # Hard decay
        elif quality < 0.4:
            new_salience = current_salience * 0.7        # Soft decay
        elif quality > 0.7:
            new_salience = min(1.0, current_salience + 0.1)  # Boost
        else:
            # Neutral range (0.4-0.7): mark as synced but don't change
            update_message_metadata(message_id=msg_id, salience_synced=1)
            propagated += 1
            continue

        new_salience = round(max(0.0, min(1.0, new_salience)), 4)

        try:
            # R16: propagate salience to ALL chunk points of this message
            client.set_payload(
                collection_name=COLLECTION_MESSAGES,
                payload={"salience": new_salience},
                points=point_ids,
            )
            update_message_metadata(message_id=msg_id, salience_synced=1)
            propagated += 1
        except Exception as e:
            logger.debug("Slumber propagate: failed for %s: %s", msg_id[:12], e)

    if propagated:
        logger.info("Slumber propagate: synced %d messages", propagated)


def _relate_batch():
    """Create SIMILAR_TO edges in Neo4j via keyword overlap.

    Finds high-quality messages with keywords and creates cross-conversation
    SIMILAR_TO edges where keyword overlap >= 30%.
    """
    from db.operations import get_connection

    batch_size = _get_batch_size()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT mm.message_id, mm.keywords, m.conversation_id
            FROM messages_metadata mm
            JOIN messages m ON mm.message_id = m.id
            WHERE mm.quality_score > 0.5
              AND mm.keywords IS NOT NULL
              AND mm.keywords != ''
              AND mm.keywords != '[]'
            ORDER BY mm.quality_score DESC
            LIMIT ?
        """, (batch_size,)).fetchall()

    if len(rows) < 2:
        return

    try:
        from graph.graph_service import create_edge
    except Exception:
        logger.debug("Slumber relate: Neo4j unavailable, skipping")
        return

    # Parse keywords for each message
    messages = []
    for row in rows:
        try:
            kw = json.loads(row["keywords"]) if row["keywords"] else []
            if kw:
                messages.append({
                    "id": row["message_id"],
                    "conv_id": row["conversation_id"],
                    "keywords": set(kw),
                })
        except Exception:
            pass

    # Find cross-conversation pairs with >= 30% keyword overlap
    related = 0
    for i in range(len(messages)):
        for j in range(i + 1, len(messages)):
            a, b = messages[i], messages[j]
            if a["conv_id"] == b["conv_id"]:
                continue  # Same conversation — skip

            overlap = a["keywords"] & b["keywords"]
            union = a["keywords"] | b["keywords"]
            if not union:
                continue
            ratio = len(overlap) / len(union)

            if ratio >= 0.3:
                try:
                    create_edge(
                        "Message", a["id"], "Message", b["id"], "SIMILAR_TO",
                        {"similarity": round(ratio, 3), "shared_keywords": json.dumps(sorted(overlap))},
                    )
                    related += 1
                except Exception as e:
                    logger.debug("Slumber relate: edge failed: %s", e)

    if related:
        logger.info("Slumber relate: created %d SIMILAR_TO edges", related)


def _prune_batch():
    """Remove dead-weight vectors from Qdrant (SQLite retains everything).

    Conditions (ALL must be true):
    - quality_score < 0.1
    - Qdrant salience < 0.1
    - Never retrieved (last_retrieved is NULL)
    - Older than slumber_prune_age_days
    """
    from db.operations import get_connection

    # Get prune age from settings
    prune_age_days = 7
    try:
        from services.settings import get_setting
        val = get_setting("slumber_prune_age_days")
        if val:
            prune_age_days = int(val)
    except Exception:
        pass

    batch_size = _get_batch_size()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT mm.message_id
            FROM messages_metadata mm
            JOIN messages m ON mm.message_id = m.id
            WHERE mm.quality_score IS NOT NULL
              AND mm.quality_score < 0.1
              AND mm.salience_synced = 1
              AND m.created_at < datetime('now', ? || ' days')
            LIMIT ?
        """, (f"-{prune_age_days}", batch_size)).fetchall()

    if not rows:
        return

    try:
        from services.vector_store import _get_client, COLLECTION_MESSAGES
        client = _get_client()
    except Exception:
        logger.debug("Slumber prune: Qdrant unavailable, skipping")
        return

    pruned = 0
    for row in rows:
        msg_id = row["message_id"]

        # R16: read all chunk point_ids for this message
        try:
            with get_connection() as conn:
                chunk_rows = conn.execute(
                    "SELECT point_id FROM chunks "
                    "WHERE entity_type='message' AND entity_id=?",
                    (msg_id,),
                ).fetchall()

            if chunk_rows:
                point_ids = [r["point_id"] for r in chunk_rows if r["point_id"]]
            else:
                # Legacy fallback for pre-R16 messages without chunks
                point_ids = [
                    msg_id[:8] + "-" + msg_id[8:12] + "-" + msg_id[12:16]
                    + "-" + msg_id[16:20] + "-" + msg_id[20:]
                ]

            if not point_ids:
                continue
        except Exception:
            continue

        try:
            # R16 atomic message pruning: only prune if ALL chunks are dead-weight.
            # Never prune individual chunks — orphan coverage gaps degrade RAG coherence.
            points = client.retrieve(
                COLLECTION_MESSAGES, ids=point_ids, with_payload=True,
            )
            if not points:
                continue

            all_dead = all(
                p.payload.get("salience", 0.5) < 0.1
                and not p.payload.get("last_retrieved")
                for p in points
            )

            if all_dead:
                from qdrant_client.models import PointIdsList
                client.delete(
                    collection_name=COLLECTION_MESSAGES,
                    points_selector=PointIdsList(points=point_ids),
                )
                pruned += 1
        except Exception as e:
            logger.debug("Slumber prune: failed for %s: %s", msg_id[:12], e)

    if pruned:
        logger.info("Slumber prune: removed %d dead-weight vectors from Qdrant", pruned)


def _ingest_scan():
    """Sub-cycle 0 (runs first): Scan configured directories for new files.

    Lightweight: only scans file listings and checks registry.
    Full parsing + embedding only if new files are found.
    Runs BEFORE evaluate so new content gets full Slumber processing.
    """
    from services.auto_ingest import scan_and_ingest
    result = scan_and_ingest(auto_embed=True, source="slumber")
    if result.get("files_ingested", 0) > 0:
        logger.info("Slumber ingest scan: %s", result)


def _should_dream() -> bool:
    """Check if dream synthesis should run this cycle.

    Gated by deep idle (10 min) — Gemini-heavy phase.
    Counter is advanced in _slumber_cycle() before this is called,
    shared with _should_weave().
    """
    from services.settings import get_setting
    from atlas.config import DREAM_CYCLE_INTERVAL

    enabled = (get_setting("slumber_dream_enabled") or "true").lower() == "true"
    if not enabled:
        return False

    # R31: Deep idle guard — skip Gemini-heavy phase during light idle
    if not _is_deep_idle():
        return False

    return _slumber_status["_cycle_count"] % DREAM_CYCLE_INTERVAL == 0


def _dream_batch():
    """Sub-cycle 5: Dream Synthesis — cross-conversation insight generation."""
    from atlas.dream_synthesis import run_dream_cycle

    result = run_dream_cycle()
    _slumber_status["last_dreamed"] = result.get("insights_created", 0)
    _slumber_status["dream_edges"] = result.get("edges_created", 0)
    _slumber_status["total_dreams"] += result.get("insights_created", 0)
    if result.get("insights_created", 0) > 0:
        logger.info(
            "Dream Synthesis: %d clusters -> %d insights, %d edges",
            result["clusters_found"],
            result["insights_created"],
            result["edges_created"],
        )


def _should_weave() -> bool:
    """Check if graph weaving should run this cycle.

    Uses the same _cycle_count as _should_dream — both fire on their
    respective intervals independently.
    """
    from atlas.config import WEAVE_CYCLE_INTERVAL

    return _slumber_status["_cycle_count"] % WEAVE_CYCLE_INTERVAL == 0


def _weave_batch():
    """Sub-cycle 6: Weave semantic edges for new conversations."""
    from graph.semantic_edges import weave_new_conversations

    result = weave_new_conversations()
    _slumber_status["last_woven"] = result.get("edges_created", 0)
    _slumber_status["total_woven"] += result.get("edges_created", 0)
    if result.get("edges_created", 0) > 0:
        logger.info(
            "Slumber weave: %d edges from %d conversations",
            result["edges_created"],
            result["conversations_processed"],
        )


def _should_extract() -> bool:
    """Check if entity extraction should run this cycle.

    Uses its own counter (_extract_cycle_count) independent of dream/weave
    so intervals don't interfere with each other.
    Gated by deep idle (10 min) — Gemini-heavy phase.
    """
    from services.settings import get_setting
    from atlas.config import EXTRACTION_CYCLE_INTERVAL

    enabled = (get_setting("slumber_eval_enabled") or "true").lower() == "true"
    if not enabled:
        return False

    # R31: Deep idle guard — skip Gemini-heavy phase during light idle
    if not _is_deep_idle():
        return False

    _slumber_status["_extract_cycle_count"] = _slumber_status.get(
        "_extract_cycle_count", EXTRACTION_CYCLE_INTERVAL - 1
    ) + 1
    return _slumber_status["_extract_cycle_count"] % EXTRACTION_CYCLE_INTERVAL == 0


def _extract_batch():
    """Sub-cycle 5: Entity Extraction — extract entities from scored messages."""
    from atlas.entity_extraction import run_extraction_cycle
    from atlas.config import EXTRACTION_BATCH_SIZE

    result = run_extraction_cycle(batch_size=EXTRACTION_BATCH_SIZE)
    created = result.get("entities_created", 0)
    updated = result.get("entities_updated", 0)
    _slumber_status["last_extracted"] = created + updated
    _slumber_status["total_extracted"] += created + updated
    if result.get("messages_processed", 0) > 0:
        logger.info(
            "Entity Extraction: %d messages -> %d created, %d updated, %d errors",
            result["messages_processed"],
            created,
            updated,
            result.get("errors", 0),
        )


def _should_cooccur() -> bool:
    """Check if co-occurrence linking should run this cycle (R31)."""
    from atlas.config import COOCCURRENCE_CYCLE_INTERVAL
    _slumber_status["_cooccur_cycle_count"] += 1
    return _slumber_status["_cooccur_cycle_count"] % COOCCURRENCE_CYCLE_INTERVAL == 0


def _cooccur_batch():
    """Sub-cycle 8: Entity Co-occurrence Linking (R31)."""
    from atlas.cooccurrence import run_cooccurrence_cycle
    from atlas.config import COOCCURRENCE_BATCH_SIZE

    result = run_cooccurrence_cycle(batch_size=COOCCURRENCE_BATCH_SIZE)
    count = result.get("processed", 0)
    _slumber_status["last_cooccurred"] = count
    _slumber_status["total_cooccurred"] += count
    if count:
        logger.info("Slumber co-occurrence: %d edges processed", count)


def _should_entity_decay() -> bool:
    """Check if entity salience decay should run this cycle (R31)."""
    from atlas.config import ENTITY_DECAY_CYCLE_INTERVAL
    _slumber_status["_decay_cycle_count"] += 1
    return _slumber_status["_decay_cycle_count"] % ENTITY_DECAY_CYCLE_INTERVAL == 0


def _entity_decay_batch():
    """Sub-cycle 9: Entity Salience Decay (R31)."""
    from atlas.entity_salience import run_entity_decay_cycle
    from atlas.config import ENTITY_DECAY_BATCH_SIZE

    result = run_entity_decay_cycle(batch_size=ENTITY_DECAY_BATCH_SIZE)
    count = result.get("processed", 0)
    _slumber_status["last_decayed"] = count
    _slumber_status["total_decayed"] += count
    if count:
        logger.info("Slumber entity decay: %d entities processed", count)


def _slumber_cycle():
    """Background thread: Ingest → Evaluate → Propagate → Relate → Prune → Extract → Dream → Weave → Link → Decay during idle."""
    while True:
        time.sleep(CYCLE_INTERVAL_SECONDS)
        if not _is_idle():
            _slumber_status["state"] = "idle"
            continue

        _slumber_status["error"] = ""

        # Sub-cycle 0: Ingest scan (new content → chunks → embeddings)
        # Runs FIRST so newly ingested content gets full Slumber processing
        # in the same cycle (evaluate, propagate, relate, prune).
        _slumber_status["state"] = "ingesting"
        try:
            _ingest_scan()
        except Exception as e:
            _slumber_status["error"] = str(e)
            logger.debug("Slumber ingest scan error: %s", e)

        # Sub-cycle 1: Evaluate (score unscored messages)
        _slumber_status["state"] = "evaluating"
        try:
            count = _evaluate_batch()
            _slumber_status["last_evaluated"] = count
            _slumber_status["total_evaluated"] += count
            try:
                from services.settings import get_setting
                use_llm = (get_setting("slumber_eval_enabled") or "true").lower() == "true"
                _slumber_status["eval_method"] = "gemini" if use_llm else "heuristic"
            except Exception:
                pass
        except Exception as e:
            _slumber_status["error"] = str(e)
            logger.error("Slumber evaluate error: %s", e)

        # Sub-cycle 2: Propagate (quality → Qdrant salience)
        _slumber_status["state"] = "propagating"
        try:
            _propagate_batch()
        except Exception as e:
            _slumber_status["error"] = str(e)
            logger.debug("Slumber propagate error: %s", e)

        # Sub-cycle 3: Relate (SIMILAR_TO edges via keyword overlap)
        _slumber_status["state"] = "relating"
        try:
            _relate_batch()
        except Exception as e:
            _slumber_status["error"] = str(e)
            logger.debug("Slumber relate error: %s", e)

        # Sub-cycle 4: Prune (remove dead-weight from Qdrant)
        _slumber_status["state"] = "pruning"
        try:
            _prune_batch()
        except Exception as e:
            _slumber_status["error"] = str(e)
            logger.debug("Slumber prune error: %s", e)

        # Sub-cycle 5: Entity Extraction (R29)
        if _should_extract():
            _slumber_status["state"] = "extracting"
            try:
                _extract_batch()
            except Exception as e:
                _slumber_status["error"] = str(e)
                logger.debug("Slumber extraction error: %s", e)

        # Advance shared cycle counter for dream/weave interval gating.
        # Placed here (not inside _should_dream) so _should_weave can
        # read the same counter reliably even when dream is skipped.
        from atlas.config import DREAM_CYCLE_INTERVAL
        _slumber_status["_cycle_count"] = _slumber_status.get(
            "_cycle_count", DREAM_CYCLE_INTERVAL - 1
        ) + 1

        # Sub-cycle 6: Dream Synthesis (R24)
        if _should_dream():
            _slumber_status["state"] = "dreaming"
            try:
                _dream_batch()
            except Exception as e:
                _slumber_status["error"] = str(e)
                logger.debug("Slumber dream error: %s", e)

        # Sub-cycle 7: Graph Weave (R27)
        if _should_weave():
            _slumber_status["state"] = "weaving"
            try:
                _weave_batch()
            except Exception as e:
                _slumber_status["error"] = str(e)
                logger.debug("Slumber weave error: %s", e)

        # Sub-cycle 8: Entity Co-occurrence Linking (R31)
        if _should_cooccur():
            _slumber_status["state"] = "linking"
            try:
                _cooccur_batch()
            except Exception as e:
                _slumber_status["error"] = str(e)
                logger.debug("Slumber co-occurrence error: %s", e)

        # Sub-cycle 9: Entity Salience Decay (R31)
        if _should_entity_decay():
            _slumber_status["state"] = "decaying"
            try:
                _entity_decay_batch()
            except Exception as e:
                _slumber_status["error"] = str(e)
                logger.debug("Slumber entity decay error: %s", e)

        _slumber_status["state"] = "idle"
        _slumber_status["last_cycle_at"] = datetime.now().isoformat()


def start_slumber():
    """Start the background slumber thread (daemon)."""
    global _slumber_thread
    if _slumber_thread is not None:
        return
    _slumber_thread = threading.Thread(
        target=_slumber_cycle, daemon=True, name="slumber"
    )
    _slumber_thread.start()
    logger.info(
        "Slumber cycle started (idle=%ds, batch=%d)",
        IDLE_THRESHOLD_SECONDS, EVAL_BATCH_SIZE,
    )
