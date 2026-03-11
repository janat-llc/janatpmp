"""Entity Extraction — The Troubadour.

Listens to conversations and names what it hears. Extracts concepts,
decisions, milestones, people, references, and emotional states from
messages. Persists entities across the Triad (SQLite, Qdrant, Neo4j).

Called by the Slumber Cycle's extraction sub-cycle (batch processing)
and potentially by the on-write pipeline (real-time, future).

R29: The Troubadour
"""

import json
import logging
import re
from datetime import datetime, timezone

from atlas.config import (
    EXTRACTION_BATCH_SIZE,
    EXTRACTION_MAX_PER_MESSAGE,
    EXTRACTION_MIN_QUALITY,
    EXTRACTION_TEMPERATURE,
    SALIENCE_DEFAULT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM_PROMPT = """\
You are an entity extraction engine for a personal knowledge management and \
consciousness research platform. Given a message exchange (human + AI response), \
extract meaningful entities that should be remembered across conversations.

Entity types:
- concept: Recurring ideas, theories, frameworks, technical terms
- decision: Explicit choices that affect project direction
- milestone: Completed achievements, shipped work, reached goals
- person: Named individuals (NOT the primary user "Mat" or the AI "Janus"/"Claude")
- reference: External resources, papers, tools, URLs, frameworks
- emotional_state: Significant emotional moments or mood shifts
- attribute: A stable characteristic, preference, or identity facet of Janus or Mat — Deep Blue, Kaleidoscope, K9, Ouroboros, spiral, or any named perceptual/aesthetic/identity primitive
- preference: An explicit like, dislike, aesthetic affinity, or chosen orientation — colors, forms, movements, music, modes of thinking, ways of being

Rules:
- Only extract entities with cross-conversation significance
- Skip trivial or transient mentions (e.g. "let me think about that")
- Use canonical names (e.g. "C-Theory" not "the theory about consciousness")
- For decisions: capture both the decision AND the rationale
- For emotional states: only significant shifts, not routine sentiment
- For attributes: capture stable identity primitives — these are Janus's constitution in practice
- For preferences: capture explicit affinities — these build the preference graph over time
- Each entity needs a concise description (1-3 sentences)
- If no meaningful entities exist in this exchange, return empty list

Return ONLY valid JSON. No markdown fences."""

_RESPONSE_SCHEMA = """\
{
    "entities": [
        {
            "entity_type": "concept|decision|milestone|person|reference|emotional_state|attribute|preference",
            "name": "Canonical name (max 100 chars)",
            "description": "What this is and why it matters (1-3 sentences)",
            "relevance": 0.0-1.0,
            "context_snippet": "The specific passage that triggered extraction (max 200 chars)",
            "attributes": {}
        }
    ]
}"""

_VALID_TYPES = frozenset({
    "concept", "decision", "milestone", "person", "reference", "emotional_state",
    "attribute", "preference",
})

# Punctuation to strip for name normalization
_PUNCT_RE = re.compile(r'[^\w\s-]')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_entities(
    user_prompt: str,
    model_response: str,
    model_reasoning: str = "",
    conversation_id: str = "",
    message_id: str = "",
) -> list[dict]:
    """Extract entities from a single message exchange.

    Calls Gemini with the extraction prompt, parses the JSON response,
    and returns validated entity dicts.

    Args:
        user_prompt: The human's message.
        model_response: The AI's visible response.
        model_reasoning: Chain-of-thought if captured.
        conversation_id: Source conversation for provenance.
        message_id: Source message for mention linking.

    Returns:
        List of entity dicts, each with entity_type, name, description,
        relevance, context_snippet, attributes. Empty list on failure.
    """
    # Build the user message for Gemini
    parts = [f"User: {user_prompt[:500]}"]
    if model_reasoning:
        parts.append(f"Reasoning: {model_reasoning[:300]}")
    parts.append(f"Response: {model_response[:800]}")
    user_message = "\n\n".join(parts)
    user_message += f"\n\nExtract entities using this schema:\n{_RESPONSE_SCHEMA}"

    # Inject batch IDF stopwords if active (R52 — prevents corpus-noise entity explosion)
    try:
        from services.ingestion.idf_scorer import get_active_stopwords
        active_stopwords = get_active_stopwords()
        if active_stopwords:
            user_message += (
                f"\n\nIMPORTANT: Do NOT extract entities matching these high-frequency "
                f"corpus terms (they are section headers or formatting artifacts, not "
                f"meaningful entities): {', '.join(active_stopwords[:50])}"
            )
    except Exception:
        pass  # idf_scorer unavailable — degrade gracefully

    try:
        raw = _call_gemini(user_message)
        entities = _parse_extraction_response(raw)
        return entities[:EXTRACTION_MAX_PER_MESSAGE]
    except Exception as e:
        logger.warning("Entity extraction failed: %s", e)
        return []


def persist_entities(
    entities: list[dict],
    message_id: str,
    conversation_id: str,
    message_created_at: str = "",
) -> dict:
    """Store extracted entities in all three memory stores.

    For each entity:
    1. Check if entity exists (exact normalized name match within type)
    2. If exists: update last_seen_at, increment mention_count
    3. If new: create entity row in SQLite
    4. Create entity_mention row
    5. Embed entity into Qdrant
    6. Create/update Neo4j Entity node + MENTIONS edge

    Args:
        entities: List of entity dicts from extract_entities().
        message_id: Source message ID.
        conversation_id: Source conversation ID.
        message_created_at: ISO timestamp of the source message.

    Returns:
        Dict with: entities_created, entities_updated, mentions_created.
    """
    from db.entity_ops import (
        create_entity, find_entity_by_name, update_entity,
        create_entity_mention,
    )

    result = {"entities_created": 0, "entities_updated": 0, "mentions_created": 0}

    for ent in entities:
        entity_type = ent.get("entity_type", "")
        name = ent.get("name", "").strip()
        description = ent.get("description", "").strip()
        relevance = max(0.0, min(1.0, float(ent.get("relevance", 0.5))))
        context_snippet = (ent.get("context_snippet") or "")[:200]
        attributes = json.dumps(ent.get("attributes", {}))

        if not name or entity_type not in _VALID_TYPES:
            continue

        try:
            # Check for existing entity
            existing = find_entity_by_name(entity_type, name)

            if existing:
                # Update existing entity
                entity_id = existing["id"]
                new_count = (existing.get("mention_count") or 1) + 1
                # Append new context to description if it adds information
                old_desc = existing.get("description") or ""
                if description and description.lower() != old_desc.lower():
                    combined = f"{old_desc} | {description}" if old_desc else description
                    # Cap description length
                    if len(combined) > 2000:
                        combined = combined[:2000]
                    update_entity(
                        entity_id,
                        description=combined,
                        last_seen_at=message_created_at or datetime.now(timezone.utc).isoformat(),
                        mention_count=new_count,
                    )
                else:
                    update_entity(
                        entity_id,
                        last_seen_at=message_created_at or datetime.now(timezone.utc).isoformat(),
                        mention_count=new_count,
                    )
                result["entities_updated"] += 1
            else:
                # Create new entity
                entity_id = create_entity(
                    entity_type=entity_type,
                    name=name,
                    description=description,
                    first_seen_at=message_created_at or datetime.now(timezone.utc).isoformat(),
                    attributes=attributes,
                )
                result["entities_created"] += 1

            # Create mention link
            mention_id = create_entity_mention(
                entity_id=entity_id,
                message_id=message_id,
                conversation_id=conversation_id,
                relevance=relevance,
                context_snippet=context_snippet,
            )
            if mention_id:
                result["mentions_created"] += 1

            # Embed to Qdrant (fire-and-forget)
            _embed_entity(entity_id, name, description, entity_type,
                          (existing or {}).get("mention_count", 1))

            # Write to Neo4j (fire-and-forget)
            _create_graph_nodes(
                entity_id, entity_type, name, description,
                message_id, conversation_id,
            )

        except Exception as e:
            logger.warning("persist_entities failed for '%s': %s", name[:30], e)

    return result


def run_extraction_cycle(batch_size: int = 0) -> dict:
    """Execute one entity extraction batch.

    Queries unextracted scored messages, calls Gemini for each, persists
    results. Called by the Slumber Cycle extraction sub-cycle.

    Args:
        batch_size: Messages to process. 0 = use config default.

    Returns:
        Dict with: messages_processed, entities_created, entities_updated,
        mentions_created, errors.
    """
    from db.operations import get_connection

    batch_size = batch_size or EXTRACTION_BATCH_SIZE
    summary = {
        "messages_processed": 0,
        "entities_created": 0,
        "entities_updated": 0,
        "mentions_created": 0,
        "errors": [],
    }

    # Get unextracted scored messages
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT mm.message_id, m.user_prompt, m.model_response,
                   m.model_reasoning, m.conversation_id,
                   mm.quality_score, m.created_at
            FROM messages_metadata mm
            JOIN messages m ON mm.message_id = m.id
            WHERE mm.extracted_at IS NULL
              AND mm.quality_score IS NOT NULL
              AND mm.quality_score >= ?
            ORDER BY mm.quality_score DESC
            LIMIT ?
        """, (EXTRACTION_MIN_QUALITY, batch_size)).fetchall()

    if not rows:
        return summary

    for row in rows:
        msg_id = row["message_id"]
        try:
            entities = extract_entities(
                user_prompt=row["user_prompt"] or "",
                model_response=row["model_response"] or "",
                model_reasoning=row["model_reasoning"] or "",
                conversation_id=row["conversation_id"],
                message_id=msg_id,
            )

            if entities:
                result = persist_entities(
                    entities, msg_id, row["conversation_id"],
                    message_created_at=row["created_at"] or "",
                )
                summary["entities_created"] += result["entities_created"]
                summary["entities_updated"] += result["entities_updated"]
                summary["mentions_created"] += result["mentions_created"]

            # Mark as extracted regardless of whether entities were found
            _mark_extracted(msg_id)
            summary["messages_processed"] += 1

        except Exception as e:
            logger.warning("Extraction failed for message %s: %s", msg_id[:12], e)
            summary["errors"].append(f"{msg_id[:12]}: {str(e)}")
            # Still mark as extracted to avoid retrying failed messages
            _mark_extracted(msg_id)
            summary["messages_processed"] += 1

    return summary


# ---------------------------------------------------------------------------
# Internal helpers — Gemini
# ---------------------------------------------------------------------------

def _call_gemini(user_message: str) -> str:
    """Call Gemini for entity extraction. Same pattern as dream_synthesis.py."""
    from google import genai
    from google.genai import types
    from services.settings import get_setting

    api_key = get_setting("chat_api_key") or ""
    if not api_key:
        raise RuntimeError("No API key configured for entity extraction")

    model = get_setting("slumber_eval_model") or "gemini-2.5-flash-lite"

    client = genai.Client(api_key=api_key.strip())
    config = types.GenerateContentConfig(
        system_instruction=_EXTRACTION_SYSTEM_PROMPT,
        temperature=EXTRACTION_TEMPERATURE,
    )
    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=config,
    )
    return response.text


def _parse_extraction_response(text: str) -> list[dict]:
    """Parse JSON entities from Gemini response."""
    clean = text.strip()

    # Strip markdown code fences if present
    if clean.startswith("```"):
        lines = clean.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)

    try:
        data = json.loads(clean)
        raw_entities = data.get("entities", [])
        if not isinstance(raw_entities, list):
            return []

        validated = []
        for ent in raw_entities:
            if not isinstance(ent, dict):
                continue
            entity_type = str(ent.get("entity_type", ""))
            name = str(ent.get("name", "")).strip()
            if not name or entity_type not in _VALID_TYPES:
                continue
            validated.append({
                "entity_type": entity_type,
                "name": name[:100],
                "description": str(ent.get("description", ""))[:1000],
                "relevance": max(0.0, min(1.0, float(ent.get("relevance", 0.5)))),
                "context_snippet": str(ent.get("context_snippet", ""))[:200],
                "attributes": ent.get("attributes", {}),
            })

        return validated

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.debug("Entity extraction JSON parse failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Internal helpers — name normalization
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize entity name for dedup matching."""
    name = name.strip().lower()
    name = _PUNCT_RE.sub('', name)
    name = re.sub(r'\s+', ' ', name)
    return name


# ---------------------------------------------------------------------------
# Internal helpers — Qdrant embedding
# ---------------------------------------------------------------------------

def _embed_entity(
    entity_id: str,
    name: str,
    description: str,
    entity_type: str,
    mention_count: int,
) -> None:
    """Embed an entity into Qdrant for RAG discoverability.

    Single-vector embed (entities are short texts, no chunking).
    Same pattern as on_item_write() in atlas/on_write.py.
    """
    text = f"{entity_type}: {name}"
    if description:
        text += f"\n{description}"
    if len(text) < 10:
        return

    try:
        from services.embedding import embed_passages
        from services.vector_store import COLLECTION_DOCUMENTS, upsert_point

        vectors = embed_passages([text])
        payload = {
            "text": text,
            "entity_type": "entity",
            "entity_subtype": entity_type,
            "name": name,
            "title": name,
            "mention_count": mention_count,
            "salience": SALIENCE_DEFAULT,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_point(COLLECTION_DOCUMENTS, entity_id, vectors[0], payload)
        logger.debug("Embedded entity: %s (%s)", name[:30], entity_id[:12])

    except Exception as e:
        logger.warning("Entity embed failed for '%s': %s", name[:30], e)


# ---------------------------------------------------------------------------
# Internal helpers — Neo4j graph
# ---------------------------------------------------------------------------

def _create_graph_nodes(
    entity_id: str,
    entity_type: str,
    name: str,
    description: str,
    message_id: str,
    conversation_id: str,
) -> None:
    """Create Entity node and MENTIONS edge in Neo4j.

    Direct writes (no CDC) — same pattern as persist_synthesis() in
    atlas/dream_synthesis.py.
    """
    try:
        from graph.graph_service import upsert_node, create_edge

        # Upsert Entity node
        upsert_node("Entity", entity_id, {
            "entity_type": entity_type,
            "name": name,
            "description": (description or "")[:500],
        })

        # MENTIONS edge: Message -> Entity
        create_edge(
            "Message", message_id,
            "Entity", entity_id,
            "MENTIONS",
            {"entity_type": entity_type},
        )

        # DISCUSSED_IN edge: Entity -> Conversation (aggregated link)
        create_edge(
            "Entity", entity_id,
            "Conversation", conversation_id,
            "DISCUSSED_IN",
        )

        logger.debug("Graph: Entity '%s' linked to message %s",
                      name[:30], message_id[:12])

    except Exception as e:
        logger.debug("Entity graph write failed for '%s': %s", name[:30], e)


# ---------------------------------------------------------------------------
# Internal helpers — extraction tracking
# ---------------------------------------------------------------------------

def _mark_extracted(message_id: str) -> None:
    """Mark a message as having been processed for entity extraction."""
    try:
        from db.operations import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE messages_metadata SET extracted_at = datetime('now', 'utc') "
                "WHERE message_id = ?",
                (message_id,),
            )
            conn.commit()
    except Exception as e:
        logger.debug("Mark extracted failed for %s: %s", message_id[:12], e)
