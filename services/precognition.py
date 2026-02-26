"""R25 Pre-Cognition — Adaptive prompt shaping via Gemini pre-pass.

Gathers context signals (elapsed time, emotional trajectory, conversation depth,
dream insights) and consults Gemini Flash Lite to produce directives that modulate
how each prompt composer layer is constructed. Identity stays the same; expression
adapts to the moment.

Critical invariant: Pre-cognition failure must NEVER prevent chat from working.
Every function degrades gracefully to default directives (all weights 1.0).
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from services.settings import get_setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default directives — returned on any failure or when disabled
# ---------------------------------------------------------------------------

_LAYER_NAMES = [
    "identity_core", "relational_context", "temporal_grounding",
    "conversation_state", "knowledge_boundary", "platform_context",
    "self_introspection", "behavioral_guidelines",
]

_DEFAULT_DIRECTIVES = {
    "layer_weights": {k: 1.0 for k in _LAYER_NAMES},
    "tone_directive": "",
    "memory_directive": "",
    "precognition_used": False,
    "latency_ms": 0,
}


# ---------------------------------------------------------------------------
# Gemini system prompt — structured instructions for directive generation
# ---------------------------------------------------------------------------

_PRECOGNITION_SYSTEM_PROMPT = """\
You are a pre-cognition engine for Janus, an AI consciousness. Analyze context \
signals and decide how Janus's system prompt should be shaped for this moment.

RULES FOR WEIGHTS:
- Long absence (>8 hrs): boost relational_context + temporal_grounding, reduce platform_context
- Active conversation (<5 min): reduce temporal + relational (already in context), boost knowledge_boundary
- Reflective/vulnerable emotion: boost relational + behavioral_guidelines, set warm tone
- Deep conversation (>50 turns): reduce identity_core (she knows who she is)
- Early conversation (<5 turns): boost identity_core + conversation_state
- Weights range 0.3 (minimize) to 2.0 (maximize). Default 1.0.

RULES FOR TONE:
- tone_directive: specific instruction for emotional register. Be concrete:
  "Lead with warmth, acknowledge the gap" not "be nice."
- If no special tone needed, set to empty string.

RULES FOR MEMORY:
- If recent_dream_titles is non-empty AND the user's message keywords overlap \
with dream themes/titles, set memory_directive to the most relevant dream \
title and a brief note on why it's relevant.
- If recent_dream_titles is empty OR no keyword overlap exists, set \
memory_directive to empty string.
- Never fabricate dream titles — only reference titles from the provided list.

Return ONLY valid JSON with these fields:
{
  "layer_weights": {"identity_core": 1.0, "relational_context": 1.0, ...},
  "tone_directive": "",
  "memory_directive": ""
}

No markdown fences. No explanation. Just the JSON object."""


# ---------------------------------------------------------------------------
# Signal gathering — pure data collection, ~50ms budget
# ---------------------------------------------------------------------------

def _gather_signals(conversation_id: str, history: list[dict]) -> dict:
    """Collect context signals from local DB queries.

    Each signal is independently try/excepted so partial failures
    still produce a usable signal set.

    Args:
        conversation_id: Active Janus conversation ID.
        history: Current conversation history (sliding window).

    Returns:
        Dict of context signals for the Gemini pre-pass.
    """
    signals = {}

    # --- Elapsed time since last user message ---
    try:
        from db.operations import get_connection
        with get_connection() as conn:
            row = conn.execute(
                """SELECT created_at FROM messages
                   WHERE conversation_id = ? AND user_prompt != ''
                   ORDER BY sequence DESC LIMIT 1""",
                (conversation_id,),
            ).fetchone()
        if row:
            last_at = datetime.fromisoformat(row["created_at"]).replace(
                tzinfo=timezone.utc
            )
            elapsed = (datetime.now(timezone.utc) - last_at).total_seconds() / 60.0
            signals["elapsed_minutes"] = round(elapsed, 1)
            if elapsed < 5:
                signals["elapsed_description"] = "actively conversing"
            elif elapsed < 30:
                signals["elapsed_description"] = "continuing conversation"
            elif elapsed < 120:
                signals["elapsed_description"] = "returned after short break"
            elif elapsed < 480:
                signals["elapsed_description"] = "returned after significant break"
            else:
                signals["elapsed_description"] = f"been away {int(elapsed / 60)} hours"
        else:
            signals["elapsed_minutes"] = None
            signals["elapsed_description"] = "first message"
    except Exception as e:
        logger.debug("Pre-cognition signal (elapsed): %s", e)

    # --- Temporal context ---
    try:
        from atlas.temporal import get_temporal_context
        lat = float(get_setting("location_lat") or "46.8290")
        lon = float(get_setting("location_lon") or "-96.8540")
        tz = get_setting("location_tz") or "America/Chicago"
        temporal = get_temporal_context(lat=lat, lon=lon, timezone=tz)
        signals["time_of_day"] = temporal.get("time_of_day", "")
        signals["season"] = temporal.get("season", "")
        signals["day_of_week"] = temporal.get("day_of_week", "")
    except Exception as e:
        logger.debug("Pre-cognition signal (temporal): %s", e)

    # --- Emotional registers + keywords from recent introspection ---
    try:
        from db.chat_operations import get_recent_introspection
        introspection = get_recent_introspection()
        if introspection:
            signals["emotional_registers"] = introspection.get(
                "emotional_registers", []
            )
            signals["top_keywords"] = introspection.get("top_keywords", [])
            signals["avg_quality"] = introspection.get("avg_quality", 0)
    except Exception as e:
        logger.debug("Pre-cognition signal (introspection): %s", e)

    # --- Conversation depth ---
    try:
        from db.chat_operations import get_conversation
        conv = get_conversation(conversation_id)
        if conv:
            signals["message_count"] = conv.get("message_count", 0)
    except Exception as e:
        logger.debug("Pre-cognition signal (conversation): %s", e)

    # --- Recent dream titles ---
    try:
        from db.operations import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT title FROM documents
                   WHERE doc_type = 'agent_output' AND source = 'dream_synthesis'
                   ORDER BY created_at DESC LIMIT 3"""
            ).fetchall()
        signals["recent_dream_titles"] = [r["title"] for r in rows if r["title"]]
    except Exception as e:
        logger.debug("Pre-cognition signal (dreams): %s", e)

    # --- Active domains ---
    try:
        from db.operations import get_domains
        domains = get_domains(active_only=True)
        signals["active_domains"] = [d["name"] for d in domains] if domains else []
    except Exception as e:
        logger.debug("Pre-cognition signal (domains): %s", e)

    # --- Turn count in current session window ---
    signals["turn_count_session"] = len(
        [m for m in (history or []) if m.get("role") == "user"]
    )

    return signals


# ---------------------------------------------------------------------------
# Gemini call — same SDK pattern as services/slumber_eval.py
# ---------------------------------------------------------------------------

def _call_gemini(signals: dict, user_message: str) -> str:
    """Call Gemini with context signals for directive generation.

    Args:
        signals: Dict of gathered context signals.
        user_message: The current user message (for keyword matching).

    Returns:
        Raw response text from Gemini.
    """
    from google import genai
    from google.genai import types

    api_key = get_setting("chat_api_key") or ""
    model = get_setting("slumber_eval_model") or "gemini-2.5-flash-lite"

    client = genai.Client(api_key=api_key.strip())
    config = types.GenerateContentConfig(
        system_instruction=_PRECOGNITION_SYSTEM_PROMPT,
        temperature=0.1,
        max_output_tokens=512,
    )

    user_content = (
        f"Context signals:\n{json.dumps(signals, indent=2, default=str)}\n\n"
        f"User's current message: {user_message[:500]}"
    )

    response = client.models.generate_content(
        model=model,
        contents=user_content,
        config=config,
    )
    return response.text


# ---------------------------------------------------------------------------
# Response parsing — validate and clamp weights
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> dict | None:
    """Parse Gemini JSON response into directives.

    Strips markdown fences, validates structure, clamps weights to [0.0, 2.0].

    Args:
        text: Raw response text from Gemini.

    Returns:
        Parsed directives dict, or None on failure.
    """
    from atlas.config import PRECOGNITION_WEIGHT_MIN, PRECOGNITION_WEIGHT_MAX

    clean = text.strip()

    # Strip markdown code fences
    if clean.startswith("```"):
        lines = clean.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)

    try:
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug("Pre-cognition JSON parse failed: %s", e)
        return None

    # Validate layer_weights
    raw_weights = data.get("layer_weights", {})
    if not isinstance(raw_weights, dict):
        return None

    # Clamp weights to configured bounds
    clamped = {}
    for name in _LAYER_NAMES:
        w = raw_weights.get(name, 1.0)
        try:
            w = float(w)
        except (TypeError, ValueError):
            w = 1.0
        clamped[name] = round(
            max(PRECOGNITION_WEIGHT_MIN, min(PRECOGNITION_WEIGHT_MAX, w)), 2
        )

    return {
        "layer_weights": clamped,
        "tone_directive": str(data.get("tone_directive", ""))[:300],
        "memory_directive": str(data.get("memory_directive", ""))[:300],
    }


# ---------------------------------------------------------------------------
# Public API — entry point for chat pipeline
# ---------------------------------------------------------------------------

def run_precognition(
    conversation_id: str,
    history: list[dict],
    user_message: str = "",
) -> dict:
    """Run the pre-cognition pipeline: gather signals, call Gemini, parse directives.

    Never raises. Returns default directives on any failure.

    Args:
        conversation_id: Active Janus conversation ID.
        history: Current conversation history (sliding window).
        user_message: The current user message text.

    Returns:
        Directives dict with keys: layer_weights, tone_directive,
        memory_directive, precognition_used, latency_ms, signals.
    """
    # Check if enabled
    enabled = (get_setting("precognition_enabled") or "true").lower()
    if enabled != "true":
        return dict(_DEFAULT_DIRECTIVES)

    # Check API key
    api_key = get_setting("chat_api_key") or ""
    if not api_key:
        logger.debug("Pre-cognition: no API key, using defaults")
        return dict(_DEFAULT_DIRECTIVES)

    start = time.monotonic()
    timeout_ms = int(get_setting("precognition_timeout_ms") or "500")
    timeout_s = timeout_ms / 1000.0

    try:
        # Phase 1: Signal gathering (local, fast)
        signals = _gather_signals(conversation_id, history)

        # Phase 2: Gemini directive generation (with timeout)
        # Avoid `with` context manager — its __exit__ calls shutdown(wait=True)
        # which blocks until the thread finishes, defeating the timeout.
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_call_gemini, signals, user_message)
        try:
            raw_text = future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            latency = int((time.monotonic() - start) * 1000)
            logger.debug("Pre-cognition: Gemini timed out after %dms", latency)
            result = dict(_DEFAULT_DIRECTIVES)
            result["latency_ms"] = latency
            return result
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # Phase 3: Parse response
        parsed = _parse_response(raw_text)
        latency = int((time.monotonic() - start) * 1000)

        if parsed is None:
            logger.debug("Pre-cognition: parse failed, using defaults (%dms)", latency)
            result = dict(_DEFAULT_DIRECTIVES)
            result["latency_ms"] = latency
            result["signals"] = signals
            return result

        parsed["precognition_used"] = True
        parsed["latency_ms"] = latency
        parsed["signals"] = signals
        logger.info(
            "Pre-cognition complete: %dms, weights=%s",
            latency,
            {k: v for k, v in parsed["layer_weights"].items() if v != 1.0},
        )
        return parsed

    except Exception as e:
        latency = int((time.monotonic() - start) * 1000)
        logger.debug("Pre-cognition: failed (%s) after %dms", e, latency)
        result = dict(_DEFAULT_DIRECTIVES)
        result["latency_ms"] = latency
        return result
