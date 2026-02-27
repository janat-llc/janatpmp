"""Entity-aware routing — detect entity references and inject structured context.

When a user query references a known entity, pull the entity's synthesized
description and recent source messages. This structured context is injected
into the RAG pipeline before vector search, giving Janus pre-built knowledge
about concepts, decisions, and people.

R30: Entity-Aware RAG Routing
"""

import logging
import math
import re
from dataclasses import dataclass, field

from atlas.config import (
    ENTITY_CONFIDENCE_THRESHOLD,
    ENTITY_CONTEXT_BUDGET,
    ENTITY_MAX_MATCHES,
    ENTITY_MAX_SNIPPETS,
)

logger = logging.getLogger(__name__)

_ENTITY_TYPES = [
    "concept", "decision", "milestone", "person", "reference", "emotional_state",
]

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "i", "me", "my", "you", "your", "we", "our", "they", "them", "their",
    "he", "she", "it", "his", "her", "its", "who", "what", "which",
    "that", "this", "these", "those", "how", "when", "where", "why",
    "not", "no", "nor", "but", "and", "or", "if", "then", "so",
    "of", "in", "on", "at", "to", "for", "with", "by", "from",
    "about", "into", "through", "during", "before", "after",
    "up", "out", "off", "over", "under", "again", "further",
    "just", "also", "very", "really", "much", "more", "most",
    "all", "any", "some", "each", "every", "both",
    "tell", "know", "think", "said", "like", "get",
})


@dataclass
class EntityMatch:
    """A matched entity with its structured context."""
    entity_id: str
    name: str
    entity_type: str
    description: str
    mention_count: int
    confidence: float
    source_snippets: list[str] = field(default_factory=list)


@dataclass
class EntityRoutingResult:
    """Result of entity detection on a user message."""
    entities_found: list[EntityMatch]
    structured_context: str
    total_chars: int
    trace: dict


def _extract_candidates(message: str) -> list[str]:
    """Extract entity name candidates from a user message.

    Strategy (fast, no LLM):
    1. Capitalized multi-word phrases: "Dream Synthesis", "C-Theory"
    2. Quoted strings: 'preference annealing'
    3. Known patterns: *-Theory, R+digits
    4. Single capitalized words (not sentence-starters)
    5. Fallback: top 3 longest non-stopword terms
    """
    candidates = []
    seen = set()

    def _add(term: str) -> None:
        normalized = term.strip()
        key = normalized.lower()
        if key and key not in seen and len(key) > 1 and key not in _STOPWORDS:
            seen.add(key)
            candidates.append(normalized)

    # 1. Capitalized multi-word phrases (2+ words, at least one uppercase start)
    for m in re.finditer(r'\b([A-Z][a-zA-Z]*(?:[\s-][A-Z][a-zA-Z]*)+)\b', message):
        _add(m.group(1))

    # 2. Quoted strings
    for m in re.finditer(r"""['"]([^'"]{2,50})['"]""", message):
        _add(m.group(1))

    # 3. Known suffix patterns: X-Theory, X-Model, X-Framework
    for m in re.finditer(r'\b(\w+-(?:Theory|Model|Framework|Pattern|Cycle|Loop))\b',
                         message, re.IGNORECASE):
        _add(m.group(1))

    # 4. Sprint references: R29, R30
    for m in re.finditer(r'\b(R\d{1,3})\b', message):
        _add(m.group(1))

    # 5. Single capitalized words that aren't sentence-starters
    #    Split on sentence boundaries, skip first word of each sentence
    sentences = re.split(r'[.!?]\s+', message)
    for sentence in sentences:
        words = sentence.split()
        for word in words[1:]:  # skip first word (sentence starter)
            clean = re.sub(r'[^\w-]', '', word)
            if clean and clean[0].isupper() and len(clean) > 2:
                _add(clean)

    # 6. Fallback: if no candidates yet, take top 3 longest non-stopword terms
    if not candidates:
        words = re.findall(r'\b\w+\b', message)
        content_words = [w for w in words if w.lower() not in _STOPWORDS and len(w) > 2]
        content_words.sort(key=len, reverse=True)
        for w in content_words[:3]:
            _add(w)

    return candidates


def _lookup_candidate(candidate: str) -> list[EntityMatch]:
    """Look up a candidate term against the entity database.

    First tries exact name match across all types (sub-ms).
    Falls back to FTS5 search if no exact match.
    """
    from db.entity_ops import find_entity_by_name, get_entity, search_entities

    matches = []

    # Try exact match across all entity types
    for entity_type in _ENTITY_TYPES:
        result = find_entity_by_name(entity_type, candidate)
        if result:
            entity = get_entity(result["id"])
            snippets = [
                m.get("context_snippet", "")
                for m in entity.get("mentions", [])[:ENTITY_MAX_SNIPPETS]
                if m.get("context_snippet")
            ]
            matches.append(EntityMatch(
                entity_id=entity["id"],
                name=entity["name"],
                entity_type=entity["entity_type"],
                description=entity.get("description", ""),
                mention_count=entity.get("mention_count", 1),
                confidence=0.95,
                source_snippets=snippets,
            ))
            return matches  # exact match found, no need for FTS

    # FTS fallback
    fts_results = search_entities(candidate, limit=3)
    for result in fts_results:
        name_lower = result.get("name", "").lower()
        cand_lower = candidate.lower()

        if name_lower == cand_lower:
            similarity = 0.9
        elif cand_lower in name_lower or name_lower in cand_lower:
            similarity = 0.6
        else:
            similarity = 0.4

        mention_count = result.get("mention_count", 1)
        confidence = similarity * min(1.0, math.log(mention_count + 1) / 3.0)
        confidence = min(confidence, 0.9)  # cap FTS at 0.9

        if confidence >= ENTITY_CONFIDENCE_THRESHOLD:
            # Fetch full entity for mention snippets
            entity = get_entity(result["id"])
            snippets = [
                m.get("context_snippet", "")
                for m in entity.get("mentions", [])[:ENTITY_MAX_SNIPPETS]
                if m.get("context_snippet")
            ]
            matches.append(EntityMatch(
                entity_id=result["id"],
                name=result.get("name", ""),
                entity_type=result.get("entity_type", ""),
                description=result.get("description", ""),
                mention_count=mention_count,
                confidence=round(confidence, 2),
                source_snippets=snippets,
            ))

    return matches


def detect_entities(message: str, max_entities: int = 0) -> EntityRoutingResult:
    """Detect entity references in a user message.

    Fast path (no LLM): extract candidates via regex, look up against
    entities_fts and find_entity_by_name, score and rank matches.

    Args:
        message: The user's message text.
        max_entities: Maximum entities to return. 0 = config default.

    Returns:
        EntityRoutingResult with matched entities and pre-built context.
    """
    max_entities = max_entities or ENTITY_MAX_MATCHES
    candidates = _extract_candidates(message)

    all_matches: list[EntityMatch] = []
    seen_ids: set[str] = set()

    for candidate in candidates:
        try:
            matches = _lookup_candidate(candidate)
            for match in matches:
                if match.entity_id not in seen_ids:
                    seen_ids.add(match.entity_id)
                    all_matches.append(match)
        except Exception as e:
            logger.debug("Entity lookup failed for '%s': %s", candidate, e)

    # Sort by confidence descending, take top-N
    all_matches.sort(key=lambda m: m.confidence, reverse=True)
    top_matches = all_matches[:max_entities]

    # Build structured context
    structured_context = build_entity_context(top_matches)

    trace = {
        "candidates_extracted": candidates,
        "entities_matched": [
            {
                "entity_id": m.entity_id,
                "name": m.name,
                "entity_type": m.entity_type,
                "confidence": m.confidence,
                "mention_count": m.mention_count,
            }
            for m in top_matches
        ],
        "structured_context_chars": len(structured_context),
    }

    return EntityRoutingResult(
        entities_found=top_matches,
        structured_context=structured_context,
        total_chars=len(structured_context),
        trace=trace,
    )


def build_entity_context(matches: list[EntityMatch],
                         budget: int = 0) -> str:
    """Build structured context string from entity matches.

    Args:
        matches: Scored entity matches from detect_entities().
        budget: Maximum characters for the context block. 0 = config default.

    Returns:
        Formatted context string for injection into system prompt.
    """
    if not matches:
        return ""

    budget = budget or ENTITY_CONTEXT_BUDGET
    lines = ["\n## Known Context\n"]
    chars = len(lines[0])

    for match in matches:
        header = (
            f"**{match.name}** ({match.entity_type}, "
            f"referenced {match.mention_count} times):\n"
        )
        desc = match.description or "(no description)"
        block = header + desc + "\n"

        # Add source snippets if available
        if match.source_snippets:
            block += "\nRecent context:\n"
            for snippet in match.source_snippets[:ENTITY_MAX_SNIPPETS]:
                block += f'- "{snippet}"\n'

        block += "\n"

        if chars + len(block) > budget:
            # Try to fit at least the header + description
            short_block = header + desc[:200] + "...\n\n"
            if chars + len(short_block) <= budget:
                lines.append(short_block)
            break

        lines.append(block)
        chars += len(block)

    return "".join(lines)
