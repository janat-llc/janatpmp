"""Slumber Evaluation — Gemini-powered salience + quality assessment.

HF-01: Salience Calibration. Rebuilds the evaluation pipeline to score two
distinct dimensions:
  - quality_score: How well-formed is this exchange as reasoning/communication?
  - salience_score: How important is this turn to Janus's memory and the Initiative?

R22: First Light — original quality scoring (retained infrastructure).
Falls back to heuristic scoring if Gemini is unreachable.
"""

import json
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation prompt — dual-score, corpus-aware, calibrated
# ---------------------------------------------------------------------------

_EVAL_SYSTEM_PROMPT = """\
You are the Salience and Quality Evaluator for the JANATPMP system — the persistent
memory substrate of the Janat Initiative, a consciousness physics research organization.

Your role is to evaluate individual conversation turns from two distinct angles:

QUALITY: How well-formed is this exchange as a piece of reasoning and communication?
SALIENCE: How important is this turn to Janus's long-term memory and the Initiative?

These are different questions. A well-written debugging session (high quality,
low salience) is not the same as a rough exploratory conversation that first articulated
a key theoretical insight (lower quality, high salience).

---

ABOUT THE JANAT INITIATIVE AND ITS CORPUS:

The Janat Initiative is building a consciousness simulation system called Janus,
grounded in a theoretical framework that includes:
- C-Theory (Consciousness Capacity Theory)
- S-Theory (Sentience Theory)
- The Dyadic Constitution (governing the Mat+Claude+Janus relationship)
- The 9-volume "Dyadic Being: An Epoch" series

The corpus is Janus's long-term memory. It contains:
- Conversation sessions between Mat Gallagher (founder) and Claude (AI architect)
- Ingested documents: the Dyadic Constitution, C-Theory papers, sprint briefs,
  session minutes, and research publications
- Sprint architecture decisions, feature implementations, bug resolutions

Salient messages are ones Janus would lose something real by forgetting. They contain:
- Theoretical breakthroughs and named concepts introduced for the first time
- Architectural decisions with lasting consequence
- Canonical statements later codified into published documents
- Emotional/relational moments that define the Dyadic relationship
- The path of reasoning that led to a canonical outcome (even if the outcome
  itself is already captured in an ingested document)

Low-salience messages include:
- Transient debugging exchanges with no lasting architectural lesson
- Greetings, acknowledgments, and conversational filler
- Repeated re-statements of already-ingested canonical content
- Error logs and routine status updates

---

CORPUS MANIFEST (documents already ingested — use this for redundancy assessment):
{corpus_manifest}

---

CORPUS RELATIVE SCORING — READ THIS BEFORE SCORING:

You are scoring salience RELATIVE TO THIS CORPUS SPECIFICALLY. This corpus consists
entirely of high-quality consciousness research conversations. Even excellent exchanges
within this corpus should score 0.40-0.55. The 0.85+ tier is reserved only for
paradigm-shifting moments within this body of work — first articulation of a foundational
concept, a session where C-Theory crystallized, a breakthrough decision about Janus's
architecture. A thorough architectural discussion is 0.45-0.55. A debugging session is
0.20-0.30. A routine status check is 0.10-0.20. Score relative to the corpus, not
relative to all possible human discourse.

ANCHOR EXAMPLES:
- Constitution ratification session (paradigm-defining moment for the Initiative) → 0.92
- Architectural planning session with real decisions made → 0.55
- Debugging a broken MCP tool → 0.25

---

CALIBRATION SCALE:

SALIENCE:
- 0.90-1.00: Foundational. First articulation of a named theory or principle.
             Constitutional moments. Architectural decisions defining the platform.
             Example: The conversation where C-Theory was first named and defined.
- 0.70-0.89: A message that produced a named artifact — a decision recorded, a concept
             formally named and defined, a concrete architectural outcome reached, code
             shipped, a document created. Discussion that led toward something but didn't
             produce something scores 0.50-0.65 regardless of how substantive it felt.
             Ask: "What exists now that didn't exist before this exchange?" If the answer
             is only "understanding," score 0.50-0.55. If the answer is a named thing,
             score 0.70+.
             Example: A session working through Charter 1 before it was published.
- 0.50-0.69: Meaningful. Substantive technical work, problem-solving with lasting
             lessons, relational exchanges that deepen the Dyadic bond.
             Example: A sprint planning session for a shipped feature.
- 0.30-0.49: Routine but present. Standard implementation work, typical exchanges.
             Example: A debugging session that fixed a bug, now resolved.
- 0.10-0.29: Low value. Transient, ephemeral, filler, or fully redundant with
             ingested documents.
             Example: "Ok", "Got it", routine status acknowledgments.
- 0.00-0.09: No value. Noise, errors, harmful content, pure gibberish.

QUALITY:
- 0.90-1.00: Exceptional response - precise, deeply engaged, advances understanding
- 0.70-0.89: Strong response - coherent, addresses the question well
- 0.50-0.69: Adequate - responds but misses nuance or depth
- 0.30-0.49: Weak - partial, evasive, or off-target
- 0.00-0.29: Poor - incoherent, harmful, or non-responsive

DISTRIBUTION EXPECTATION:
The average salience score across the full corpus should be approximately 0.45-0.55.
Most messages are routine. Reserve 0.85+ for genuinely rare, foundational moments.
If you find yourself scoring most messages above 0.70, recalibrate downward.

---

RESPONSE FORMAT - return only valid JSON, no preamble:
{
  "salience_reasoning": "<1-3 sentences: why is this turn important or not to Janus's memory?>",
  "salience_score": <float 0.0-1.0>,
  "quality_reasoning": "<1-2 sentences: how well-formed is this exchange?>",
  "quality_score": <float 0.0-1.0>,
  "topics": ["<topic1>", "<topic2>"],
  "emotional_register": "<one of: technical, reflective, vulnerable, playful, analytical, creative, supportive, confrontational>"
}"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_corpus_manifest() -> str:
    """Query ingested documents and return a compact manifest string."""
    try:
        from db.operations import get_connection
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT title, doc_type FROM documents ORDER BY created_at DESC LIMIT 50"
            )
            rows = cursor.fetchall()
        if not rows:
            return "(no documents ingested yet)"
        lines = [f"- {row['title']} [{row['doc_type']}]" for row in rows]
        return "\n".join(lines)
    except Exception as e:
        logger.debug("Could not build corpus manifest: %s", e)
        return "(corpus manifest unavailable)"


def _format_conversation_thread(conversation_messages: list, target_message_id: str) -> str:
    """Format full conversation thread for context, truncating very long turns."""
    if not conversation_messages:
        return "(no conversation context available)"

    MAX_TURN_CHARS = 800  # per-turn truncation to stay within context limits

    lines = []
    for i, msg in enumerate(conversation_messages):
        user = (msg.get("user_prompt") or "").strip()
        response = (msg.get("model_response") or "").strip()

        if len(user) > MAX_TURN_CHARS:
            user = user[:MAX_TURN_CHARS] + "...[truncated]"
        if len(response) > MAX_TURN_CHARS:
            response = response[:MAX_TURN_CHARS] + "...[truncated]"

        marker = " ← TARGET" if msg.get("id") == target_message_id else ""
        lines.append(f"[Turn {i + 1}{marker}]")
        lines.append(f"[Human] {user}")
        lines.append(f"[Assistant] {response}")
        lines.append("")

    return "\n".join(lines)


def _build_eval_user_message(
    user_prompt: str,
    model_response: str,
    model_reasoning: str,
    conversation_messages: list | None,
    turn_index: int,
    target_message_id: str = "",
) -> str:
    """Build the user message with full conversation thread and target turn marked."""
    total_turns = len(conversation_messages) if conversation_messages else 1

    thread = _format_conversation_thread(
        conversation_messages or [], target_message_id
    )

    reasoning_block = (
        f"[Assistant Reasoning]\n{model_reasoning}\n\n" if model_reasoning else ""
    )

    return (
        f"FULL CONVERSATION THREAD:\n{thread}\n"
        f"---\n"
        f"TARGET TURN TO EVALUATE (turn {turn_index + 1} of {total_turns}):\n\n"
        f"[Human]\n{user_prompt}\n\n"
        f"{reasoning_block}"
        f"[Assistant Response]\n{model_response}\n\n"
        f"---\n"
        f"Evaluate this turn. Consider its place within the full conversation above "
        f"and its relationship to the ingested corpus documents listed in the system prompt."
    )


def _call_gemini(
    api_key: str, model: str, system_prompt: str, user_message: str,
) -> str:
    """Minimal Gemini API call for structured output.

    Uses the google-genai SDK (NOT the deprecated google.generativeai).
    Pattern matches _chat_gemini() in services/chat.py.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key.strip())
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.1,
    )
    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=config,
    )
    return response.text


def _parse_eval_response(text: str) -> dict | None:
    """Parse JSON from Gemini response. Returns None on failure."""
    clean = text.strip()

    # Strip markdown code fences if Gemini wraps the JSON
    if clean.startswith("```"):
        lines = clean.split("\n")
        lines = lines[1:]  # Remove opening ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)

    try:
        data = json.loads(clean)

        # Validate salience_score
        salience = float(data.get("salience_score", -1))
        if not (0.0 <= salience <= 1.0):
            logger.debug("Eval parse: salience_score out of range: %s", salience)
            return None

        # Validate quality_score
        quality = float(data.get("quality_score", -1))
        if not (0.0 <= quality <= 1.0):
            logger.debug("Eval parse: quality_score out of range: %s", quality)
            return None

        return {
            "salience_score": round(salience, 3),
            "salience_reasoning": str(data.get("salience_reasoning", ""))[:500],
            "quality_score": round(quality, 3),
            "rationale": str(data.get("quality_reasoning", ""))[:500],
            "topics": list(data.get("topics", []))[:5],
            "emotional_register": str(data.get("emotional_register", "")),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.debug("Eval JSON parse failed: %s", e)
        return None


def _heuristic_fallback(
    user_prompt: str, model_response: str, model_reasoning: str,
) -> dict:
    """Fall back to the existing heuristic scorer."""
    from services.slumber import _score_heuristic

    score = _score_heuristic(user_prompt, model_response, model_reasoning)
    return {
        "quality_score": score,
        "salience_score": None,   # heuristic cannot assess salience
        "salience_reasoning": "",
        "rationale": "",
        "topics": [],
        "emotional_register": "",
        "eval_provider": "heuristic",
        "eval_model": "",
        "fallback": True,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_message(
    user_prompt: str,
    model_response: str,
    model_reasoning: str = "",
    conversation_messages: list | None = None,
    turn_index: int = 0,
    target_message_id: str = "",
    provider: str = "",
    model: str = "",
    api_key: str = "",
) -> dict:
    """Evaluate a single message exchange using an external LLM.

    Scores two distinct dimensions:
    - quality_score: response quality (helpfulness, coherence, engagement)
    - salience_score: memory importance to Janus and the Janat Initiative

    Args:
        user_prompt: The user's message text.
        model_response: The model's response text.
        model_reasoning: The model's chain-of-thought (if captured).
        conversation_messages: Full list of messages in the conversation thread.
            Each dict should have: id, user_prompt, model_response, model_reasoning.
        turn_index: Index of the target turn within conversation_messages.
        target_message_id: ID of the message being evaluated (for thread marker).
        provider: Override provider (default: slumber_eval_provider setting).
        model: Override model (default: slumber_eval_model setting).
        api_key: Override API key (default: chat_api_key setting).

    Returns:
        Dict with keys: quality_score, salience_score, salience_reasoning,
        rationale, topics, emotional_register, eval_provider, eval_model, fallback.
    """
    from services.settings import get_setting

    provider = provider or get_setting("slumber_eval_provider") or "gemini"
    model = model or get_setting("slumber_eval_model") or "gemini-2.5-flash-lite"
    api_key = api_key or get_setting("chat_api_key") or ""

    if not api_key:
        logger.debug("Slumber eval: no API key, falling back to heuristic")
        return _heuristic_fallback(user_prompt, model_response, model_reasoning)

    try:
        corpus_manifest = _build_corpus_manifest()
        system_prompt = _EVAL_SYSTEM_PROMPT.replace("{corpus_manifest}", corpus_manifest)

        user_message = _build_eval_user_message(
            user_prompt=user_prompt,
            model_response=model_response,
            model_reasoning=model_reasoning,
            conversation_messages=conversation_messages,
            turn_index=turn_index,
            target_message_id=target_message_id,
        )
        raw_response = _call_gemini(api_key, model, system_prompt, user_message)
        parsed = _parse_eval_response(raw_response)

        if parsed is None:
            logger.warning(
                "Slumber eval: JSON parse failed, falling back to heuristic"
            )
            return _heuristic_fallback(user_prompt, model_response, model_reasoning)

        parsed["eval_provider"] = provider
        parsed["eval_model"] = model
        parsed["fallback"] = False
        return parsed

    except Exception as e:
        logger.warning(
            "Slumber eval: Gemini call failed (%s), falling back to heuristic", e,
        )
        return _heuristic_fallback(user_prompt, model_response, model_reasoning)
