"""R32 Register Mining — autonomous conversational register extraction.

Mines the conversation corpus for register exemplars via Gemini evaluation.
Same Prefect Pattern as all other Slumber phases: checkpointed, idle-aware,
batched, watermarked, gracefully degrading.

Three public functions:
- run_register_mining_cycle(): Slumber sub-cycle entry point
- search_register_exemplars(): Qdrant search for prompt composer
- run_register_mining_cycle() is also exposed as MCP tool for diagnostics
"""

import json
import logging
from datetime import datetime, timezone

from atlas.config import REGISTER_MINING_MIN_QUALITY
from db.operations import get_connection
from services.settings import get_setting, set_setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation Prompt — this is where register quality lives
# ---------------------------------------------------------------------------

REGISTER_EVAL_PROMPT = """\
You are evaluating a conversational AI's response for authenticity of voice.

A human named Mat sent this message:
"{user_prompt}"

An AI companion named Janus responded:
"{model_response}"

Evaluate Janus's response on these dimensions:

1. Does this sound like a person talking to someone they care about deeply, \
or does it sound like a system generating a report?
2. Does the response match Mat's energy and register? If he's warm, is she \
warm back? If he's casual, is she casual? Or does she pivot to structure \
regardless of his tone?
3. Look for specific phrases that feel authentic — natural language, personal \
warmth, playfulness, genuine curiosity. Quote them.
4. Look for specific phrases that feel performed or clinical — bullet points \
where conversation was called for, hedging language ("I should note..."), \
meta-commentary about her own capabilities, unsolicited status reports. \
Quote them.
5. Does she answer the actual question or emotional need, or does she \
redirect into a formatted briefing?

Return a JSON object with these fields:
- "register_label": one of "warm", "neutral", "clinical"
- "register_score": float 0.0-1.0 (1.0 = perfectly natural and present)
- "authentic_phrases": list of quoted phrases that feel genuine (max 3)
- "performed_phrases": list of quoted phrases that feel robotic (max 3)
- "rationale": 1-2 sentences explaining your assessment
- "topics": list of topic tags for this exchange (max 3)

Return ONLY the JSON object, no other text.
"""

_RELATIONAL_INTENTS = {"greeting", "emotional", "farewell", "continuation"}


# ---------------------------------------------------------------------------
# Gemini Evaluator
# ---------------------------------------------------------------------------

def _call_gemini(user_prompt: str, model_response: str) -> str:
    """Call Gemini for register evaluation."""
    from google import genai
    from google.genai import types

    api_key = get_setting("chat_api_key") or ""
    if not api_key:
        raise RuntimeError("No API key configured for register mining")

    provider = get_setting("register_mining_provider") or "gemini"
    model = get_setting("register_mining_model") or "gemini-2.5-flash-lite"

    prompt = REGISTER_EVAL_PROMPT.format(
        user_prompt=user_prompt[:2000],
        model_response=model_response[:3000],
    )

    client = genai.Client(api_key=api_key.strip())
    config = types.GenerateContentConfig(
        temperature=0.1,
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text


def _parse_eval_response(text: str) -> dict | None:
    """Parse JSON from Gemini register evaluation response."""
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
        label = str(data.get("register_label", ""))
        if label not in ("warm", "neutral", "clinical"):
            return None
        score = float(data.get("register_score", -1))
        if not (0.0 <= score <= 1.0):
            return None
        return {
            "register_label": label,
            "register_score": round(score, 3),
            "authentic_phrases": list(data.get("authentic_phrases", []))[:3],
            "performed_phrases": list(data.get("performed_phrases", []))[:3],
            "rationale": str(data.get("rationale", ""))[:500],
            "topics": list(data.get("topics", []))[:3],
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.debug("Register eval JSON parse failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Exemplar Storage
# ---------------------------------------------------------------------------

def _store_exemplar(
    message_id: str,
    eval_result: dict,
    user_prompt: str,
    model_response: str,
    evaluator_model: str,
) -> str | None:
    """Store register exemplar in SQLite and embed in Qdrant.

    Returns exemplar ID on success, None on failure.
    """
    import uuid
    exemplar_id = uuid.uuid4().hex

    # SQLite: source of truth
    try:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO register_exemplars
                   (id, message_id, register_label, register_score,
                    rationale, authentic_phrases, performed_phrases,
                    topics, evaluator_model, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    exemplar_id,
                    message_id,
                    eval_result["register_label"],
                    eval_result["register_score"],
                    eval_result["rationale"],
                    json.dumps(eval_result["authentic_phrases"]),
                    json.dumps(eval_result["performed_phrases"]),
                    json.dumps(eval_result["topics"]),
                    evaluator_model,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    except Exception as e:
        logger.warning("Register exemplar SQLite write failed: %s", e)
        return None

    # Qdrant: search index — embed for semantic retrieval
    try:
        from services.embedding import embed_passages
        from services.vector_store import COLLECTION_DOCUMENTS, upsert_point

        # Embed on combined text for vector similarity
        embed_text = f"{user_prompt} {model_response}"
        vectors = embed_passages([embed_text])

        payload = {
            "text": embed_text[:500],  # Short preview
            "doc_type": "register_exemplar",
            "register_label": eval_result["register_label"],
            "register_score": eval_result["register_score"],
            "authentic_phrases": eval_result["authentic_phrases"],
            "performed_phrases": eval_result["performed_phrases"],
            "rationale": eval_result["rationale"],
            "topics": eval_result["topics"],
            "user_prompt": user_prompt[:500],
            "model_response": model_response[:1000],
            "message_id": message_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_point(COLLECTION_DOCUMENTS, exemplar_id, vectors[0], payload)
        logger.debug("Register exemplar embedded: %s (%s)",
                      exemplar_id[:12], eval_result["register_label"])

    except Exception as e:
        logger.warning("Register exemplar Qdrant embed failed: %s", e)
        # SQLite write succeeded — exemplar exists but not searchable

    return exemplar_id


# ---------------------------------------------------------------------------
# Mining Cycle (Slumber Entry Point)
# ---------------------------------------------------------------------------

def run_register_mining_cycle(batch_size: int = 10) -> dict:
    """Run one register mining cycle — evaluate messages for register quality.

    Called by Slumber sub-cycle 10. Reads messages after watermark, classifies
    intent retroactively, evaluates relational messages via Gemini, stores
    exemplars in SQLite + Qdrant.

    Args:
        batch_size: Maximum messages to process per cycle.

    Returns:
        Dict with processed, warm, neutral, clinical, errors counts.
    """
    from services.intent_router import classify_intent

    watermark = int(get_setting("register_mining_watermark") or "0")
    min_quality = REGISTER_MINING_MIN_QUALITY
    evaluator_model = get_setting("register_mining_model") or "gemini-2.5-flash-lite"

    # Query messages after watermark with quality gate
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT m.rowid, m.id, m.user_prompt, m.model_response,
                          m.sequence
                   FROM messages m
                   JOIN messages_metadata mm ON mm.message_id = m.id
                   WHERE m.rowid > ?
                     AND m.user_prompt IS NOT NULL AND m.user_prompt != ''
                     AND m.model_response IS NOT NULL AND m.model_response != ''
                     AND mm.quality_score >= ?
                   ORDER BY m.rowid ASC
                   LIMIT ?""",
                (watermark, min_quality, batch_size * 3),  # Over-fetch for intent filter
            ).fetchall()
    except Exception as e:
        logger.warning("Register mining query failed: %s", e)
        return {"processed": 0, "errors": 1}

    if not rows:
        return {"processed": 0, "warm": 0, "neutral": 0, "clinical": 0,
                "errors": 0}

    processed = 0
    counts = {"warm": 0, "neutral": 0, "clinical": 0}
    errors = 0
    max_rowid = watermark

    for row in rows:
        rowid = row["rowid"]
        max_rowid = max(max_rowid, rowid)

        if processed >= batch_size:
            break

        user_prompt = row["user_prompt"]
        model_response = row["model_response"]
        sequence = row["sequence"] or 1

        # Retroactive intent classification (regex, <5ms)
        intent_result = classify_intent(
            user_prompt, conversation_turn_count=sequence)
        if intent_result.intent.value not in _RELATIONAL_INTENTS:
            continue

        # Evaluate via Gemini
        try:
            raw_text = _call_gemini(user_prompt, model_response)
            eval_result = _parse_eval_response(raw_text)
            if eval_result is None:
                errors += 1
                continue

            # Store exemplar
            exemplar_id = _store_exemplar(
                row["id"], eval_result, user_prompt, model_response,
                evaluator_model)
            if exemplar_id:
                processed += 1
                label = eval_result["register_label"]
                counts[label] = counts.get(label, 0) + 1
            else:
                errors += 1

        except Exception as e:
            logger.debug("Register mining eval failed for %s: %s",
                         row["id"][:12], e)
            errors += 1

    # Advance watermark
    if max_rowid > watermark:
        set_setting("register_mining_watermark", str(max_rowid))

    result = {"processed": processed, "errors": errors, **counts}
    if processed:
        logger.info("Register mining cycle: %s", result)
    return result


# ---------------------------------------------------------------------------
# Exemplar Search (Prompt Composer)
# ---------------------------------------------------------------------------

def search_register_exemplars(query: str, limit: int = 3) -> list[dict]:
    """Search mined register exemplars by semantic similarity.

    Used by prompt composer to inject demonstrated voice examples for
    relational intents. Returns exemplars with separate user_prompt and
    model_response payload fields.

    Args:
        query: Search query (typically the current user message).
        limit: Maximum exemplars to return.

    Returns:
        List of dicts with id, score, register_label, register_score,
        user_prompt, model_response, and other payload fields.
    """
    try:
        from services.embedding import embed_passages
        from services.vector_store import COLLECTION_DOCUMENTS
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        vectors = embed_passages([query])
        if not vectors:
            return []

        from services.vector_store import _get_client
        client = _get_client()
        hits = client.search(
            collection_name=COLLECTION_DOCUMENTS,
            query_vector=vectors[0],
            limit=limit,
            query_filter=Filter(must=[
                FieldCondition(
                    key="doc_type",
                    match=MatchValue(value="register_exemplar"),
                ),
            ]),
        )
        return [{"id": h.id, "score": h.score, **h.payload} for h in hits]

    except Exception as e:
        logger.debug("Register exemplar search failed: %s", e)
        return []
