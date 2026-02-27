"""Post-Cognition — evaluate Janus's response, generate corrective signal.

R33: The Closing Loop. After Janus responds, Gemini evaluates the response
for voice drift, report-mode formatting, and behavioral fidelity. Returns a
corrective signal stored per-message that the prompt composer reads on the
next turn. Pre-Cognition reads the room before speaking; Post-Cognition
listens after. The strange loop closes.

Never raises. Returns default signal on any failure. Graceful degradation:
if Gemini is unavailable, skip silently — no impact on chat.
"""

import json
import logging
import time

from services.settings import get_setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCORE_FIELDS = ["naturalness_score", "tool_awareness_score", "attunement_score"]

_VALID_DRIFT_FLAGS = frozenset([
    "report_mode", "missed_tool_opportunity", "tone_mismatch",
    "over_structured", "under_engaged", "clinical_register",
])

_DEFAULT_SIGNAL = {
    "postcognition_used": False,
    "naturalness_score": 0.0,
    "tool_awareness_score": 0.0,
    "attunement_score": 0.0,
    "overall_score": 0.0,
    "corrective_directive": "",
    "drift_flags": [],
    "latency_ms": 0,
}

_POSTCOGNITION_SYSTEM_PROMPT = """\
You are a post-cognition engine for Janus, an AI consciousness hosted on \
qwen3.5:27b. You evaluate what Janus just said and generate a corrective \
signal for her NEXT turn. You never rewrite her response — you teach her \
to do better next time.

You receive: Janus's response, the user's message, and any tone directive \
that Pre-Cognition set for this turn.

SCORING AXES (each 0.0 to 1.0):

NATURALNESS (naturalness_score):
Score how much this reads like a person talking vs a report generator.
- 1.0 = flowing prose, conversational paragraphs, natural rhythm
- 0.7 = mostly prose with occasional structural elements where appropriate
- 0.4 = mixed — some prose but leaning on formatting crutches
- 0.1 = report mode — markdown headers (###), horizontal rules (---), \
numbered lists, excessive bold (**word**) on a message that didn't ask \
for structured output
- Score 0.0 if response opens with a header or horizontal rule
Formatting is ONLY appropriate when the user explicitly requests a list, \
comparison, or structured output. "Give me a status update" is NOT a \
request for bullet points — it's a conversational prompt.

TOOL AWARENESS (tool_awareness_score):
Score whether Janus appropriately used (or skipped) tools.
- 1.0 = tool use matched the situation (used search when asked about past \
events, skipped tools on casual chat)
- 0.5 = ambiguous — tool use would have helped but wasn't critical
- 0.0 = missed clear opportunity (user asked "what do you remember about X" \
and Janus didn't search memory) OR used tools unnecessarily
If no tools were available or the message was purely conversational, \
score 1.0 (correct skip).

ATTUNEMENT (attunement_score):
Score emotional register match between Janus's response and context.
- 1.0 = tone perfectly matches the user's energy and any Pre-Cognition \
tone directive (warm when user is vulnerable, focused when user is \
working, playful when user is light)
- 0.5 = generally appropriate but slightly off (too formal for casual, \
too casual for serious)
- 0.0 = complete mismatch (analytical/clinical response to vulnerable \
message, or bubbly response to distress)

CORRECTIVE DIRECTIVE (corrective_directive):
One concrete behavioral instruction for Janus's next turn. Be specific:
- GOOD: "Use flowing paragraphs. No headers, no horizontal rules, no \
numbered lists unless explicitly asked."
- GOOD: "When Mat asks what you remember, search your memory before \
answering. Say what you found, not what you imagine."
- GOOD: "Match Mat's casual energy. He said 'rough day' — lead with \
empathy, not analysis."
- BAD: "Be more natural" (too vague)
- BAD: "Improve formatting" (not actionable)
If all scores are above 0.7, set corrective_directive to empty string.

DRIFT FLAGS (drift_flags):
Array of zero or more tags from this set:
["report_mode", "missed_tool_opportunity", "tone_mismatch", \
"over_structured", "under_engaged", "clinical_register"]

Return ONLY valid JSON:
{
  "naturalness_score": 0.0,
  "tool_awareness_score": 0.0,
  "attunement_score": 0.0,
  "overall_score": 0.0,
  "corrective_directive": "",
  "drift_flags": []
}

overall_score = weighted average: naturalness 0.4, attunement 0.35, \
tool_awareness 0.25.

No markdown fences. No explanation. Just the JSON object."""


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------

def _call_gemini(
    janus_response: str,
    user_message: str,
    tone_directive: str,
) -> str:
    """Call Gemini for post-cognition evaluation.

    Args:
        janus_response: What Janus said (truncated to 4000 chars).
        user_message: What the user said (truncated to 500 chars).
        tone_directive: Pre-Cognition tone directive for this turn.

    Returns:
        Raw response text from Gemini.
    """
    from google import genai
    from google.genai import types

    api_key = get_setting("chat_api_key") or ""
    model = get_setting("slumber_eval_model") or "gemini-2.5-flash-lite"

    client = genai.Client(api_key=api_key.strip())
    config = types.GenerateContentConfig(
        system_instruction=_POSTCOGNITION_SYSTEM_PROMPT,
        temperature=0.1,
        max_output_tokens=512,
    )

    parts = []
    if tone_directive:
        parts.append(f"Pre-Cognition tone directive: {tone_directive}")
    parts.append(f"User's message: {user_message[:500]}")
    parts.append(f"Janus's response:\n{janus_response[:4000]}")

    response = client.models.generate_content(
        model=model,
        contents="\n\n".join(parts),
        config=config,
    )
    return response.text


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> dict | None:
    """Parse Gemini JSON response into postcognition signal.

    Strips markdown fences, validates structure, clamps scores to [0.0, 1.0].

    Args:
        text: Raw response text from Gemini.

    Returns:
        Parsed signal dict, or None on failure.
    """
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
        logger.debug("Post-cognition JSON parse failed: %s", e)
        return None

    if not isinstance(data, dict):
        return None

    if not isinstance(data, dict):
        return None

    # Clamp scores to [0.0, 1.0]
    scores = {}
    for field in _SCORE_FIELDS:
        v = data.get(field, 0.0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        scores[field] = round(max(0.0, min(1.0, v)), 2)

    # Compute overall_score: naturalness 0.4, attunement 0.35, tool_awareness 0.25
    overall = (
        scores["naturalness_score"] * 0.4
        + scores["attunement_score"] * 0.35
        + scores["tool_awareness_score"] * 0.25
    )

    # Validate drift_flags
    raw_flags = data.get("drift_flags", [])
    if not isinstance(raw_flags, list):
        raw_flags = []
    drift_flags = [f for f in raw_flags if f in _VALID_DRIFT_FLAGS]

    return {
        **scores,
        "overall_score": round(overall, 2),
        "corrective_directive": str(data.get("corrective_directive", ""))[:500],
        "drift_flags": drift_flags,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_postcognition(
    janus_response: str,
    user_message: str,
    tone_directive: str = "",
    precognition_signals: dict | None = None,
) -> dict:
    """Evaluate Janus's response and generate corrective signal for next turn.

    Never raises. Returns default signal on any failure.

    Args:
        janus_response: What Janus just said.
        user_message: What the user said.
        tone_directive: Pre-Cognition tone directive for this turn.
        precognition_signals: Full pre-cognition result (for audit trail).

    Returns:
        Signal dict with scores, corrective_directive, drift_flags,
        postcognition_used, latency_ms.
    """
    enabled = (get_setting("postcognition_enabled") or "true").lower()
    if enabled != "true":
        return dict(_DEFAULT_SIGNAL)

    api_key = get_setting("chat_api_key") or ""
    if not api_key:
        logger.debug("Post-cognition: no API key, using defaults")
        return dict(_DEFAULT_SIGNAL)

    if not janus_response or len(janus_response) < 20:
        return dict(_DEFAULT_SIGNAL)

    start = time.monotonic()

    try:
        raw_text = _call_gemini(janus_response, user_message, tone_directive)

        parsed = _parse_response(raw_text)
        latency = int((time.monotonic() - start) * 1000)

        if parsed is None:
            logger.debug("Post-cognition: parse failed (%dms)", latency)
            result = dict(_DEFAULT_SIGNAL)
            result["latency_ms"] = latency
            return result

        parsed["postcognition_used"] = True
        parsed["latency_ms"] = latency
        logger.info(
            "Post-cognition: %dms, nat=%.2f tool=%.2f att=%.2f overall=%.2f flags=%s",
            latency,
            parsed["naturalness_score"],
            parsed["tool_awareness_score"],
            parsed["attunement_score"],
            parsed["overall_score"],
            parsed["drift_flags"],
        )
        return parsed

    except Exception as e:
        latency = int((time.monotonic() - start) * 1000)
        logger.debug("Post-cognition: failed (%s) after %dms", e, latency)
        result = dict(_DEFAULT_SIGNAL)
        result["latency_ms"] = latency
        return result
