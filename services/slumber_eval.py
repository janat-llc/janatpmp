"""Slumber Evaluation — Gemini-powered message quality assessment.

R22: First Light. Replaces heuristic scoring with genuine comprehension.
Called by the Slumber Cycle's evaluate sub-cycle during idle periods.
Falls back to heuristic scoring if Gemini is unreachable.
"""

import json
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation prompt — tight, structured, deterministic
# ---------------------------------------------------------------------------

_EVAL_SYSTEM_PROMPT = """\
You are an evaluation engine for a consciousness research platform.
Assess the quality of this AI response to a human message.

Return ONLY valid JSON with these fields:
- quality_score: float 0.0-1.0 (0=incoherent/harmful, 0.5=adequate, 1.0=exceptional)
- rationale: 1-2 sentence explanation
- topics: array of 1-5 topic strings
- emotional_register: one of [technical, reflective, vulnerable, playful, \
analytical, creative, supportive, confrontational]

Scoring criteria:
- Does the response address what the human actually asked?
- Is the reasoning coherent (if present)?
- Does the response demonstrate genuine engagement vs boilerplate?
- Is the depth proportional to the complexity of the question?
- For emotional/relational exchanges: does the response show appropriate sensitivity?"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_eval_user_message(
    user_prompt: str, model_response: str, model_reasoning: str,
) -> str:
    """Build the user message containing the exchange to evaluate."""
    return (
        f"[Human Message]\n{user_prompt}\n\n"
        f"[Model Reasoning]\n{model_reasoning or 'None captured'}\n\n"
        f"[Model Response]\n{model_response}"
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
        score = float(data.get("quality_score", -1))
        if not (0.0 <= score <= 1.0):
            return None
        return {
            "quality_score": round(score, 3),
            "rationale": str(data.get("rationale", ""))[:500],
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
    provider: str = "",
    model: str = "",
    api_key: str = "",
) -> dict:
    """Evaluate a single message exchange using an external LLM.

    Args:
        user_prompt: The user's message text.
        model_response: The model's response text.
        model_reasoning: The model's chain-of-thought (if captured).
        provider: Override provider (default: slumber_eval_provider setting).
        model: Override model (default: slumber_eval_model setting).
        api_key: Override API key (default: chat_api_key setting).

    Returns:
        Dict with keys: quality_score, rationale, topics,
        emotional_register, eval_provider, eval_model, fallback.
    """
    from services.settings import get_setting

    provider = provider or get_setting("slumber_eval_provider") or "gemini"
    model = model or get_setting("slumber_eval_model") or "gemini-2.5-flash-lite"
    api_key = api_key or get_setting("chat_api_key") or ""

    if not api_key:
        logger.debug("Slumber eval: no API key, falling back to heuristic")
        return _heuristic_fallback(user_prompt, model_response, model_reasoning)

    try:
        user_message = _build_eval_user_message(
            user_prompt, model_response, model_reasoning,
        )
        raw_response = _call_gemini(
            api_key, model, _EVAL_SYSTEM_PROMPT, user_message,
        )
        parsed = _parse_eval_response(raw_response)

        if parsed is None:
            logger.warning(
                "Slumber eval: JSON parse failed, falling back to heuristic"
            )
            return _heuristic_fallback(
                user_prompt, model_response, model_reasoning,
            )

        parsed["eval_provider"] = provider
        parsed["eval_model"] = model
        parsed["fallback"] = False
        return parsed

    except Exception as e:
        logger.warning(
            "Slumber eval: Gemini call failed (%s), falling back to heuristic", e,
        )
        return _heuristic_fallback(user_prompt, model_response, model_reasoning)
