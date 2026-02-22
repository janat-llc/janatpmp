"""Slumber Cycle — background evaluation during idle periods.

When the system is idle (no chat activity for IDLE_THRESHOLD seconds), the
Slumber Cycle wakes up and evaluates messages that lack quality scores.
It extracts keywords, scores reasoning quality via heuristics, and updates
messages_metadata records.

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

logger = logging.getLogger(__name__)

# --- Configuration (overridden by settings DB at runtime) ---
IDLE_THRESHOLD_SECONDS = 300   # 5 minutes of no chat activity
EVAL_BATCH_SIZE = 20           # Messages per cycle
CYCLE_INTERVAL_SECONDS = 60    # Check idle state every minute

_last_activity = time.monotonic()
_slumber_thread = None

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


def _evaluate_batch():
    """Evaluate a batch of messages without quality scores."""
    from db.operations import get_connection
    from db.chat_operations import update_message_metadata

    batch_size = _get_batch_size()

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
        return

    evaluated = 0
    for row in rows:
        msg_id = row["message_id"]
        user_prompt = row["user_prompt"] or ""
        model_response = row["model_response"] or ""
        model_reasoning = row["model_reasoning"] or ""

        # Score reasoning quality
        quality = _score_heuristic(user_prompt, model_response, model_reasoning)

        # Extract keywords from prompt + response
        combined_text = f"{user_prompt} {model_response}"
        keywords = _extract_keywords(combined_text, top_n=10)

        # Update metadata
        update_message_metadata(
            message_id=msg_id,
            quality_score=quality,
            keywords=json.dumps(keywords),
        )
        evaluated += 1

    logger.info("Slumber cycle: evaluated %d messages", evaluated)


def _slumber_cycle():
    """Background thread that runs evaluation during idle periods."""
    while True:
        time.sleep(CYCLE_INTERVAL_SECONDS)
        if not _is_idle():
            continue
        try:
            _evaluate_batch()
        except Exception as e:
            logger.error("Slumber cycle error: %s", e)


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
