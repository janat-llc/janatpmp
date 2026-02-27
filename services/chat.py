"""Chat service — Multi-provider AI chat with self-query tools for JANATPMP.

Supported providers:
- anthropic: Claude models (Opus 4, Sonnet 4, Haiku) — native tool use (MCP clients)
- gemini: Google Gemini models (Flash, Pro) — function calling (MCP clients)
- ollama: Local models via OpenAI-compatible API — self-query tools for active retrieval

R32: Ollama in-app chat now has 6 read-only self-query tools (search_memories,
search_entities, get_entity, get_cooccurrence_neighbors, graph_neighbors,
search_conversations). RAG still provides passive context; tools add active
retrieval on demand. Database CRUD tools remain MCP-only (external clients).

Settings (provider, model, API key, etc.) are read from the settings DB on each
chat() call — no restart needed when settings change.
"""
import inspect
import json
import logging
import re
from typing import Any
from db import operations as db_ops
from shared.constants import MAX_TOOL_ITERATIONS, MAX_TOOL_RESULT_CHARS, RAG_SCORE_THRESHOLD
from services.settings import get_setting

logger = logging.getLogger(__name__)


# --- Tool Definition Generation ---

# Map of tool_name → callable function
TOOL_REGISTRY: dict[str, callable] = {}

# The db operations to expose as tools (all 22)
EXPOSED_OPS = [
    "create_item", "get_item", "list_items", "update_item", "delete_item",
    "create_task", "get_task", "list_tasks", "update_task",
    "create_document", "get_document", "list_documents",
    "search_items", "search_documents",
    "create_relationship", "get_relationships",
    "get_stats", "get_schema_info",
    "backup_database", "reset_database", "restore_database", "list_backups",
]

# Python type → JSON schema type
TYPE_MAP = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def _parse_docstring_args(docstring: str) -> dict[str, str]:
    """Extract parameter descriptions from Google-style docstrings.

    Looks for an 'Args:' section and parses 'param_name: description' lines.
    Returns dict of {param_name: description}.
    """
    descriptions = {}
    if not docstring:
        return descriptions
    in_args = False
    for line in docstring.split("\n"):
        stripped = line.strip()
        if stripped.startswith("Args:"):
            in_args = True
            continue
        if in_args:
            if stripped.startswith("Returns:") or stripped.startswith("Raises:") or stripped == "":
                if stripped.startswith("Returns:") or stripped.startswith("Raises:"):
                    break
                continue
            if ":" in stripped:
                param, desc = stripped.split(":", 1)
                descriptions[param.strip()] = desc.strip()
    return descriptions


def _tool_def_from_fn(name: str, fn: callable) -> dict:
    """Build a single Anthropic-format tool definition from any callable.

    Introspects signature and Google-style docstring to produce JSON schema.
    Reusable for both MCP-exposed db ops and Janus self-query tools.

    Args:
        name: Tool name (used in API calls and TOOL_REGISTRY).
        fn: The callable to introspect.

    Returns:
        Dict with name, description, input_schema keys.
    """
    sig = inspect.signature(fn)
    doc = inspect.getdoc(fn) or ""
    arg_descriptions = _parse_docstring_args(doc)

    properties = {}
    required = []
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        annotation = param.annotation
        if annotation != inspect.Parameter.empty:
            type_name = getattr(annotation, "__name__", str(annotation))
            origin = getattr(annotation, "__origin__", None)
            if origin is not None:
                args = getattr(annotation, "__args__", ())
                if type(None) in args:
                    for a in args:
                        if a is not type(None):
                            type_name = getattr(a, "__name__", str(a))
                            break
            json_type = TYPE_MAP.get(type_name, "string")
        else:
            json_type = "string"

        prop: dict[str, Any] = {"type": json_type}
        if param_name in arg_descriptions:
            prop["description"] = arg_descriptions[param_name]
        properties[param_name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    description = doc.split("\n")[0] if doc else name.replace("_", " ").title()

    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _build_tool_definitions() -> list[dict]:
    """Build Anthropic tool definitions from db/operations.py functions.

    Inspects function signatures and docstrings to generate JSON schema
    compatible tool definitions for the Anthropic API.
    """
    tools = []
    for name in EXPOSED_OPS:
        fn = getattr(db_ops, name, None)
        if fn is None:
            continue
        TOOL_REGISTRY[name] = fn
        tools.append(_tool_def_from_fn(name, fn))
    return tools


# Pre-build tool definitions at import time
TOOL_DEFINITIONS = _build_tool_definitions()


# --- Self-Query Tools for Ollama In-App Chat (R32: The Mirror) ---

def _build_self_query_tools() -> list[dict]:
    """Build tool definitions for Janus self-query (Ollama in-app chat).

    Read-only tools only — no CRUD, no destructive operations.
    These let Janus actively search her own memory during conversation.
    """
    from services.vector_store import search_all
    from db.entity_ops import search_entities, get_entity
    from atlas.cooccurrence import get_cooccurrence_neighbors
    from graph.graph_service import get_neighbors
    from db.chat_operations import search_conversations

    ops = {
        "search_memories": search_all,
        "search_entities": search_entities,
        "get_entity": get_entity,
        "get_cooccurrence_neighbors": get_cooccurrence_neighbors,
        "graph_neighbors": get_neighbors,
        "search_conversations": search_conversations,
    }
    tools = []
    for name, fn in ops.items():
        TOOL_REGISTRY[name] = fn
        tools.append(_tool_def_from_fn(name, fn))
    return tools


SELF_QUERY_DEFINITIONS = _build_self_query_tools()


# --- System Prompt (R19: superseded by services/prompt_composer.py) ---

DEFAULT_SYSTEM_PROMPT_TEMPLATE = """You are Janus, an AI collaborator embedded in JANATPMP (Janat Project Management Platform).
You help Mat manage projects, tasks, and documents across multiple domains.

You can search your own memory when you need to recall something specific.
All the context you need is provided below — answer directly from it when possible.
If you don't have enough context to answer, say so plainly.

{context_block}

Key context:
- Items are projects, books, features, websites, etc. organized by domain and hierarchy.
- Tasks are work items assigned to agents, Claude, Mat, Janus, or unassigned.
- Documents store conversations, research, session notes, code, and artifacts.
- Relationships connect any two entities (items, tasks, documents).

Domains: {domains}

You are a collaborator, not just an assistant. Be thoughtful, expressive, and thorough in your responses."""


def _build_system_prompt(history: list[dict] = None,
                         conversation_id: str = "",
                         directives: dict = None) -> tuple[str, dict]:
    """Compose the full system prompt via the R19 prompt composer.

    Delegates to services/prompt_composer.py which assembles up to 9 layers:
    Identity Core, Relational Context, Memory Directive, Temporal Grounding,
    Conversation State, Self-Knowledge Boundary, Platform Context,
    Self-Introspection, Behavioral Guidelines + Tone Directive.

    Args:
        history: Conversation history for turn count awareness.
        conversation_id: Active conversation ID for temporal/state queries.
        directives: Pre-cognition directives dict (R25) with layer_weights,
            tone_directive, memory_directive. None = default weights.

    Returns:
        Tuple of (system prompt string, layers dict with per-layer text and char counts).
    """
    from services.prompt_composer import compose_system_prompt
    return compose_system_prompt(history or [], conversation_id=conversation_id,
                                 directives=directives)


_EMPTY_RAG_METRICS = {
    "hit_count": 0, "hits_used": 0, "collections_searched": [],
    "avg_rerank_score": 0.0, "avg_salience": 0.0, "scores": [],
    "rejected": [], "context_text": "",
}

_EMPTY_TOKEN_COUNTS = {"prompt": 0, "reasoning": 0, "response": 0, "total": 0}


_FTS_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can",
    "do", "for", "from", "had", "has", "have", "he", "her", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "me", "my",
    "no", "not", "of", "on", "or", "our", "she", "so", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "to",
    "up", "us", "was", "we", "were", "what", "when", "which", "who",
    "will", "with", "would", "you", "your",
}

# R28: Temporal reference patterns — suppress decay for explicit historical queries
_TEMPORAL_REFERENCE = re.compile(
    r"(last\s*(year|month|week|summer|winter|fall|spring|"
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december))|"
    r"(months?\s*ago|years?\s*ago|weeks?\s*ago)|"
    r"(in\s*(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)(\s+\d{4})?)|"
    r"(in\s+\d{4})|"
    r"(back\s+when|first\s+time|earliest|originally)|"
    r"(our\s+(first|earliest|original)\s+(conversation|discussion|chat))",
    re.IGNORECASE,
)


def _fts_search_messages(query: str, limit: int = 10) -> list[dict]:
    """Keyword search on messages via SQLite FTS5.

    Complements vector search for cases where specific terms (like "Entry #008")
    are buried deep in long messages and invisible to the embedding model.
    Filters stop words, uses AND logic for remaining terms.

    Returns results in the same dict format as Qdrant search_all() so they
    can be merged into the same candidate pipeline.
    """
    from db.operations import get_connection
    import re
    results = []
    try:
        # Extract meaningful terms: strip punctuation, remove stop words.
        # For numbers like #008, also generate zero-padded variants (#0008)
        # since content may use different padding.
        raw_terms = re.sub(r'[^\w\s]', '', query).split()
        meaningful = [t for t in raw_terms if t.lower() not in _FTS_STOP_WORDS and len(t) > 1]
        if not meaningful:
            return []

        # Expand number terms with padding variants
        expanded = []
        for t in meaningful:
            if re.match(r'^\d+$', t):
                # Pure number: add zero-padded variants (008 → 0008, 00008)
                expanded.append(f'("{t}" OR "{t.zfill(4)}" OR "{t.zfill(5)}")')
            else:
                expanded.append(f'"{t}"')

        # Use AND logic — all terms must appear. More precise than OR.
        fts_query = " AND ".join(expanded)

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT m.id, m.user_prompt, m.model_response,
                       m.conversation_id, c.title as conv_title,
                       m.created_at
                FROM messages m
                JOIN messages_fts fts ON fts.rowid = m.rowid
                JOIN conversations c ON c.id = m.conversation_id
                WHERE messages_fts MATCH ?
                ORDER BY rank, m.created_at DESC
                LIMIT ?
            """, (fts_query, limit)).fetchall()

        for row in rows:
            text = f"Q: {row['user_prompt']}\nA: {row['model_response']}"
            results.append({
                "id": row["id"],
                "text": text,
                "score": 0.5,
                "source_collection": "messages",
                "conversation_id": row["conversation_id"],
                "conv_title": row["conv_title"] or "",
                "created_at": row["created_at"] or "",
                "_fts_match": True,
            })
    except Exception as e:
        logger.debug("FTS search failed: %s", e)
    return results


def _fts_search_chunks(query: str, limit: int = 10) -> list[dict]:
    """Keyword search on chunks via SQLite FTS5.

    R16: Searches the chunks_fts table for chunk-level keyword matches.
    Returns results in the same dict format as Qdrant search_all() so they
    can be merged into the same candidate pipeline.
    """
    from db.operations import get_connection
    import re

    results = []
    try:
        raw_terms = re.sub(r'[^\w\s]', '', query).split()
        meaningful = [t for t in raw_terms if t.lower() not in _FTS_STOP_WORDS and len(t) > 1]
        if not meaningful:
            return []

        expanded = []
        for t in meaningful:
            if re.match(r'^\d+$', t):
                expanded.append(f'("{t}" OR "{t.zfill(4)}" OR "{t.zfill(5)}")')
            else:
                expanded.append(f'"{t}"')

        fts_query = " AND ".join(expanded)

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT c.point_id as id, c.chunk_text as text,
                       c.entity_id, c.chunk_index, c.position,
                       c.entity_type,
                       m.conversation_id, conv.title as conv_title,
                       m.created_at
                FROM chunks c
                JOIN chunks_fts fts ON fts.id = c.id
                LEFT JOIN messages m ON c.entity_type = 'message' AND c.entity_id = m.id
                LEFT JOIN conversations conv ON m.conversation_id = conv.id
                WHERE chunks_fts MATCH ?
                AND c.point_id IS NOT NULL
                ORDER BY rank, m.created_at DESC
                LIMIT ?
            """, (fts_query, limit)).fetchall()

        for row in rows:
            source = "messages" if row["entity_type"] == "message" else "documents"
            results.append({
                "id": row["id"],
                "text": row["text"],
                "score": 0.5,
                "source_collection": source,
                "conversation_id": row["conversation_id"] or "",
                "conv_title": row["conv_title"] or "",
                "created_at": row["created_at"] or "",
                "parent_message_id": row["entity_id"] if row["entity_type"] == "message" else "",
                "chunk_index": row["chunk_index"],
                "chunk_position": row["position"],
                "_fts_match": True,
            })
    except Exception as e:
        logger.debug("FTS chunk search failed: %s", e)
    return results


def _format_relative_time(iso_ts: str) -> str:
    """Convert ISO timestamp to human-readable relative time.

    '2025-11-15T...' → '3 months ago'
    '2026-02-23T...' → 'yesterday'
    '2026-02-24T...' → 'today'
    """
    if not iso_ts:
        return ""
    try:
        from datetime import datetime, timezone
        # Parse ISO timestamp (handle both 'T' separator and space)
        ts_str = iso_ts.replace("T", " ").split(".")[0]
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        delta = now - dt
        days = delta.days

        if days < 0:
            return ""
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days} days ago"
        if days < 30:
            weeks = days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        if days < 365:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        years = days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    except Exception:
        return ""


def _apply_temporal_decay(candidates, half_life=0.0, floor=0.0):
    """Multiply RAG candidate scores by temporal decay factor.

    factor = floor + (1 - floor) * exp(-age_days / half_life)
    Candidates missing 'created_at' pass through unmodified.

    R28: Temporal Gravity
    """
    import math
    from datetime import datetime
    from atlas.config import TEMPORAL_DECAY_HALF_LIFE, TEMPORAL_DECAY_FLOOR

    hl = half_life or TEMPORAL_DECAY_HALF_LIFE
    fl = floor or TEMPORAL_DECAY_FLOOR
    now = datetime.now()
    trace = {"applied": True, "half_life_days": hl, "decay_floor": fl,
             "candidates_decayed": 0, "candidates_skipped": 0}

    for c in candidates:
        created_at = c.get("created_at", "")
        if not created_at:
            c["temporal_factor"] = 1.0
            trace["candidates_skipped"] += 1
            continue
        try:
            ts = created_at.replace("T", " ").split("+")[0].split(".")[0]
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            age_days = max(0, (now - dt).days)
        except Exception:
            c["temporal_factor"] = 1.0
            trace["candidates_skipped"] += 1
            continue

        factor = fl + (1.0 - fl) * math.exp(-age_days / hl)
        c["pre_decay_score"] = round(c.get("score", 0.0), 4)
        c["score"] = c.get("score", 0.0) * factor
        c["temporal_factor"] = round(factor, 4)
        c["age_days"] = age_days
        trace["candidates_decayed"] += 1

    candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return candidates, trace


def _needs_rag(message: str) -> bool:
    """Decide whether a message warrants RAG retrieval.

    Skips RAG for short conversational messages (greetings, acknowledgments,
    single-word responses) that don't need knowledge base context. This avoids
    loading 3 extra models (embedder, reranker, synthesizer) for "Hello Janus".

    Args:
        message: The user's message text.

    Returns:
        True if RAG should run, False to skip.
    """
    # Strip and lowercase for matching
    clean = message.strip().lower()

    # Too short to be a knowledge query (under 3 words)
    words = clean.split()
    if len(words) < 3:
        return False

    # After removing stop words, is there enough substance?
    content_words = [w for w in words if w not in _FTS_STOP_WORDS]
    if len(content_words) < 2:
        return False

    return True


def _build_rag_context(user_message: str,
                       skip_gate: bool = False,
                       entity_ids: list[str] | None = None,
                       intent: str = "") -> tuple[str, dict]:
    """Hybrid search: Qdrant vectors + SQLite FTS keyword matching.

    Two-source retrieval ensures both semantic similarity AND keyword matches
    surface relevant content. Particularly important for specific terms like
    "Entry #008" buried deep in long messages.

    Reads rag_score_threshold and rag_max_chunks from settings DB so they
    can be tuned at runtime via the Admin panel.

    Skips retrieval entirely for short conversational messages (greetings,
    acknowledgments) via _needs_rag() gate — avoids loading embedder, reranker,
    and synthesizer models for messages that don't need knowledge context.

    Args:
        user_message: The user's current message.

    Returns:
        Tuple of (formatted context string, RAG metrics dict).
        Returns ("", empty_metrics) if no results or Qdrant unavailable.
    """
    metrics = dict(_EMPTY_RAG_METRICS, scores=[], rejected=[])

    if not skip_gate and not _needs_rag(user_message):
        logger.debug("RAG skipped — message too short/conversational: %s", user_message[:50])
        return "", metrics

    try:
        from services.vector_store import search_all
        threshold = float(get_setting("rag_score_threshold") or RAG_SCORE_THRESHOLD)
        rerank_threshold = float(get_setting("rag_rerank_threshold") or 0.3)
        max_chunks = int(get_setting("rag_max_chunks") or 10)
        # R16: diversity cap — max chunks from same parent message (0 = no limit)
        max_per_message = int(get_setting("rag_max_chunks_per_message") or 3)
        # Fetch extra candidates — short stubs and low-quality hits will be
        # filtered out below, so we need headroom to still fill max_chunks.
        results = search_all(user_message, limit=max_chunks * 3)

        # Hybrid: FTS keyword search catches specific terms (Entry #008,
        # proper nouns) buried deep in long messages that vector search
        # misses. FTS results go FIRST — they matched by exact keyword,
        # which is a strong signal that vector similarity can't replicate.
        fts_results = _fts_search_messages(user_message, limit=max_chunks)
        # R16: also search chunk-level FTS for focused paragraph matches
        fts_chunk_results = _fts_search_chunks(user_message, limit=max_chunks)
        seen_ids = set()
        merged = []
        for fts_r in fts_results + fts_chunk_results:
            fid = fts_r["id"]
            if fid not in seen_ids:
                merged.append(fts_r)
                seen_ids.add(fid)
        for r in results:
            rid = r.get("id")
            if rid not in seen_ids:
                merged.append(r)
                seen_ids.add(rid)
        results = merged

        if not results:
            return "", metrics

        # R21: Graph-aware ranking — boost candidates from topic neighborhood
        try:
            from atlas.graph_ranking import compute_graph_affinity
            results, graph_trace = compute_graph_affinity(results)
            metrics["graph_trace"] = graph_trace
        except Exception as e:
            logger.debug("Graph ranking unavailable: %s", e)
            metrics["graph_trace"] = {}

        # R30: Graph retrieval — pull source messages via entity edges
        graph_retrieval_trace = {}
        if entity_ids:
            try:
                from atlas.graph_retrieval import retrieve_entity_sources
                graph_msgs, graph_retrieval_trace = retrieve_entity_sources(
                    entity_ids)
                for msg in graph_msgs:
                    msg_id = msg.get("message_id", "")
                    if msg_id not in seen_ids:
                        seen_ids.add(msg_id)
                        results.append({
                            "id": msg_id,
                            "text": msg["text"],
                            "conversation_id": msg.get("conversation_id", ""),
                            "created_at": msg.get("created_at", ""),
                            "score": 0.7,
                            "source_collection": "graph_retrieval",
                            "_fts_match": False,
                        })
                if graph_msgs:
                    logger.debug("Graph retrieval added %d source messages",
                                 len(graph_msgs))
            except Exception as e:
                logger.debug("Graph retrieval unavailable: %s", e)
        metrics["graph_retrieval_trace"] = graph_retrieval_trace

        # R28: Temporal decay — recency-weight candidates
        temporal_trace = {"applied": False, "reason": "decay disabled"}
        if _TEMPORAL_REFERENCE.search(user_message):
            temporal_trace = {"applied": False, "reason": "historical query detected"}
        else:
            results, temporal_trace = _apply_temporal_decay(results)
        metrics["temporal_trace"] = temporal_trace

        metrics["hit_count"] = len(results)
        metrics["collections_searched"] = list({r.get("source_collection", "unknown") for r in results})

        context_parts = []
        used_scores = []
        rejected_scores = []
        for r in results:
            source = r.get("source_collection", "unknown")
            title = r.get("title", r.get("conv_title", ""))
            full_text = r.get("text", "") or ""

            # Extract Q/A portions for messages stored as "Q: ...\nA: ..."
            # The model response (A:) contains the actual knowledge; the
            # user prompt (Q:) is contextual but shouldn't dominate.
            q_part = ""
            a_part = full_text
            if full_text.startswith("Q: "):
                a_idx = full_text.find("\nA: ")
                if a_idx > 0:
                    q_part = full_text[3:a_idx].strip()
                    a_part = full_text[a_idx + 4:].strip()

            # Preview shows the A (response) portion — that's the knowledge
            text_preview = a_part[:200] if a_part else full_text[:200]

            candidate_info = {
                "id": r.get("id", ""),
                "source": source, "title": title,
                "rerank_score": r.get("rerank_score") or 0.0,
                "salience": r.get("salience", 0.0),
                "ann_score": r.get("score", 0.0),
                "text_preview": text_preview,
                "source_conversation_id": r.get("conversation_id", ""),
                "source_conversation_title": r.get("conv_title", ""),
                "created_at": r.get("created_at", ""),
                "fts_match": r.get("_fts_match", False),
                # R16 chunk metadata
                "parent_message_id": r.get("parent_message_id", ""),
                "chunk_index": r.get("chunk_index"),
                "chunk_total": r.get("chunk_total"),
                "chunk_position": r.get("chunk_position", ""),
                # R28 temporal decay
                "temporal_factor": r.get("temporal_factor", 1.0),
                "age_days": r.get("age_days"),
                "pre_decay_score": r.get("pre_decay_score"),
            }

            # Filter 1: Minimum text length — reject short stubs (domain
            # descriptions, placeholder docs) that match everything broadly
            # and crowd out real content. Check the A portion for messages.
            content_text = a_part if a_part != full_text else full_text
            if len(content_text) < 50:
                candidate_info["reject_reason"] = f"text too short ({len(content_text)} chars)"
                rejected_scores.append(candidate_info)
                continue

            # Filter 2: Rerank/ANN score threshold.
            # FTS keyword matches bypass score filters — they matched by
            # exact terms, which is a strong relevance signal on its own.
            # Prefer rerank_score (cross-encoder relevance) over ANN score.
            # Qwen3-Reranker scores are 0-1 probabilities (via vLLM).
            # ANN scores are cosine similarity (0-1), only used as fallback.
            is_fts = r.get("_fts_match", False)
            if not is_fts:
                rerank = r.get("rerank_score")
                if rerank is not None:
                    if rerank < rerank_threshold:
                        candidate_info["reject_reason"] = f"rerank {rerank:.3f} < {rerank_threshold}"
                        rejected_scores.append(candidate_info)
                        continue
                else:
                    ann_score = r.get("score", 0)
                    if ann_score <= threshold:
                        candidate_info["reject_reason"] = f"ann {ann_score:.3f} <= {threshold}"
                        rejected_scores.append(candidate_info)
                        continue

            # Cap at max_chunks used results to control context size
            if len(used_scores) >= max_chunks:
                candidate_info["reject_reason"] = "over max_chunks limit"
                rejected_scores.append(candidate_info)
                continue

            # R16: diversity cap — limit chunks from same parent message
            if max_per_message > 0:
                parent_id = r.get("parent_message_id", r.get("id", ""))
                parent_count = sum(
                    1 for s in used_scores
                    if s.get("parent_message_id", s.get("id", "")) == parent_id
                )
                if parent_count >= max_per_message:
                    candidate_info["reject_reason"] = (
                        f"diversity cap ({parent_count}/{max_per_message} "
                        f"from same message)"
                    )
                    rejected_scores.append(candidate_info)
                    continue

            # R16: chunks are already right-sized (~2500 chars), no truncation needed.
            # Build attribution with temporal position for chunk-aware context.
            chunk_pos = r.get("chunk_position", "")
            chunk_idx = r.get("chunk_index")
            chunk_total = r.get("chunk_total")
            pos_label = {
                "first": "early in discussion",
                "middle": "mid-discussion",
                "last": "late in discussion",
            }.get(chunk_pos, "")

            # R17: relative time label from created_at timestamp
            # NOTE: Temporal labels are display-only for R17. Temporal weighting
            # (recent conversations scoring higher on ambiguous queries) is deferred
            # to the Intelligent Pipeline sprint. This is a future hook, not a gap.
            created_at = r.get("created_at", "")
            age_label = _format_relative_time(created_at) if created_at else ""

            # R31: Dream attribution — label synthesized insights distinctly
            doc_type = r.get("doc_type", "")
            if doc_type == "agent_output":
                source = "synthesized insight"

            # R32: Intent-gated attribution — narrative for relational,
            # clinical for analytical intents
            _RELATIONAL_INTENTS = {"greeting", "emotional", "farewell",
                                   "continuation"}
            if intent in _RELATIONAL_INTENTS:
                # Narrative attribution — conversational framing
                time_phrase = f" ({age_label})" if age_label else ""
                if title:
                    attribution = (f"From a conversation about "
                                   f"{title}{time_phrase}")
                else:
                    attribution = f"From memory{time_phrase}"
            else:
                # Clinical attribution — structured metadata
                attr_parts = [f"[{source}]"]
                if title:
                    attr_parts.append(f'"{title}"')
                if pos_label:
                    attr_parts.append(f"({pos_label}")
                    if (chunk_idx is not None and chunk_total
                            and chunk_total > 1):
                        attr_parts[-1] += (
                            f", chunk {chunk_idx + 1}/{chunk_total}")
                        if age_label:
                            attr_parts[-1] += f", {age_label})"
                        else:
                            attr_parts[-1] += ")"
                    else:
                        if age_label:
                            attr_parts[-1] += f", {age_label})"
                        else:
                            attr_parts[-1] += ")"
                elif age_label:
                    attr_parts.append(f"({age_label})")
                attribution = " ".join(attr_parts)

            # Inject the A (response) portion with brief Q context
            if q_part and a_part != full_text:
                q_summary = q_part[:100] + ("..." if len(q_part) > 100 else "")
                inject_text = f"(asked: {q_summary})\n{a_part}"
            else:
                inject_text = full_text
            context_parts.append(f"{attribution}: {inject_text}")
            used_scores.append(candidate_info)

        metrics["hits_used"] = len(used_scores)
        metrics["scores"] = used_scores
        metrics["rejected"] = rejected_scores
        if used_scores:
            metrics["avg_rerank_score"] = sum(s["rerank_score"] for s in used_scores) / len(used_scores)
            metrics["avg_salience"] = sum(s["salience"] for s in used_scores) / len(used_scores)

        if not context_parts:
            return "", metrics

        raw_context = "\n\n---\nRelevant context from knowledge base:\n" + "\n\n".join(context_parts) + "\n---\n"

        # Synthesize via Gemini Flash-Lite if configured — compresses raw
        # chunks into a coherent context package that the chat model can
        # actually use. Falls back to raw chunks if unavailable.
        context = _synthesize_rag_context(user_message, raw_context, context_parts)
        metrics["context_text"] = context
        metrics["raw_context_text"] = raw_context
        metrics["synthesized"] = (context != raw_context)
        return context, metrics
    except Exception as e:
        logger.debug("RAG context unavailable: %s", e)
        return "", metrics  # Graceful degradation if Qdrant is down


def _build_light_rag_context(user_message: str) -> tuple[str, dict]:
    """Light RAG — vector search only, top-5, no FTS/graph/synthesis.

    Used for CONTINUATION, CLARIFICATION, and META intents where
    some context helps but full pipeline is overkill.

    Args:
        user_message: The user's current message.

    Returns:
        Tuple of (formatted context string, RAG metrics dict).
    """
    metrics = dict(_EMPTY_RAG_METRICS, light_rag=True, scores=[], rejected=[])
    try:
        from services.vector_store import search_all
        threshold = float(get_setting("rag_score_threshold") or RAG_SCORE_THRESHOLD)
        results = search_all(user_message, limit=5, rerank=False)

        if not results:
            return "", metrics

        # Filter by score threshold
        passed = [r for r in results if r.get("score", 0) >= threshold]
        if not passed:
            return "", metrics

        # Simple concatenation — no synthesis, no diversity cap
        context_parts = []
        used_scores = []
        for r in passed[:3]:
            text = r.get("text", "")[:500]
            if text:
                context_parts.append(text)
                used_scores.append({
                    "score": round(r.get("score", 0), 4),
                    "collection": r.get("collection", ""),
                    "text_preview": text[:100],
                })

        if not context_parts:
            return "", metrics

        context = "\n\n---\n\n[Relevant context]\n\n" + "\n\n".join(context_parts)
        metrics["hit_count"] = len(results)
        metrics["hits_used"] = len(context_parts)
        metrics["scores"] = used_scores
        metrics["context_text"] = context
        return context, metrics
    except Exception as e:
        logger.debug("Light RAG unavailable: %s", e)
        return "", metrics


def _synthesize_rag_context(user_message: str, raw_context: str, context_parts: list[str]) -> str:
    """Synthesize raw RAG chunks into coherent context via a dedicated model.

    Supports two backends:
    - "ollama": Local model (default, zero-cost, no rate limits)
    - "gemini": Google Gemini API (needs API key, rate-limited on free tier)

    Takes scattered RAG results and produces a focused, coherent knowledge
    summary that the chat model can actually use. This solves the problem of
    small local models being unable to extract answers from raw chunked context.

    Falls back to raw_context if synthesis fails or is disabled.

    Args:
        user_message: The user's question (provides synthesis focus).
        raw_context: The raw chunk-based context string (fallback).
        context_parts: Individual chunk strings for the synthesis prompt.

    Returns:
        Synthesized context string, or raw_context on fallback.
    """
    provider = get_setting("rag_synthesizer_provider") or "ollama"
    model = get_setting("rag_synthesizer_model")
    if not model or not model.strip():
        return raw_context

    # Build the synthesis prompt (shared across backends)
    synthesis_prompt = (
        "You are a knowledge synthesis engine. Your job is to read the retrieved "
        "knowledge chunks below and produce a clear, coherent summary that directly "
        "addresses the user's question. Include ALL relevant facts, names, dates, "
        "numbers, and details from the chunks. Do not add information that isn't in "
        "the chunks. If the chunks don't contain relevant information, say so.\n\n"
        f"USER QUESTION: {user_message}\n\n"
        "RETRIEVED KNOWLEDGE CHUNKS:\n"
    )
    for i, part in enumerate(context_parts):
        synthesis_prompt += f"\n--- Chunk {i+1} ---\n{part}\n"
    synthesis_prompt += (
        "\n--- END OF CHUNKS ---\n\n"
        "Now synthesize the above into a coherent knowledge briefing that "
        "directly answers the user's question. Be thorough — include every "
        "relevant detail from the chunks."
    )

    try:
        if provider == "ollama":
            synthesis = _synth_ollama(model, synthesis_prompt)
        elif provider == "gemini":
            api_key = get_setting("rag_synthesizer_api_key")
            if not api_key or not api_key.strip():
                return raw_context
            synthesis = _synth_gemini(api_key, model, synthesis_prompt)
        else:
            logger.debug("Unknown synthesizer provider: %s", provider)
            return raw_context

        if synthesis and len(synthesis.strip()) > 50:
            logger.info("RAG synthesis: %d chunks → %d char summary via %s/%s",
                        len(context_parts), len(synthesis), provider, model)
            return f"\n\n---\nSynthesized knowledge (from {len(context_parts)} sources):\n{synthesis.strip()}\n---\n"
        else:
            logger.debug("RAG synthesis produced empty/short result, using raw context")
            return raw_context

    except Exception as e:
        logger.warning("RAG synthesis failed (%s/%s), using raw context: %s", provider, model, e)
        return raw_context


def _synth_ollama(model: str, prompt: str) -> str:
    """Run synthesis via Ollama's OpenAI-compatible API."""
    from openai import OpenAI
    base_url = get_setting("chat_base_url") or "http://ollama:11434/v1"
    client = OpenAI(api_key="ollama", base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a knowledge synthesis engine. Produce clear, factual summaries. No thinking tags."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
        extra_body={"options": {"num_ctx": 8192}},  # Synthesizer processes short chunks, not full conversations
    )
    return response.choices[0].message.content or ""


def _synth_gemini(api_key: str, model: str, prompt: str) -> str:
    """Run synthesis via Google Gemini API."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key.strip())
    response = client.models.generate_content(
        model=model,
        contents=[types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )],
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    return response.text or ""


# --- Provider Presets ---

# Provider: (display_name, default_models_list)
# Users can also type custom model strings
PROVIDER_PRESETS = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-6",
        ],
        "default_model": "claude-sonnet-4-20250514",
        "needs_api_key": True,
        "base_url": None,
    },
    "gemini": {
        "name": "Google (Gemini)",
        "models": [
            "gemini-2.0-flash",
            "gemini-2.5-pro-preview-06-05",
            "gemini-2.5-flash-preview-05-20",
            "gemini-2.5-flash-lite",
        ],
        "default_model": "gemini-2.0-flash",
        "needs_api_key": True,
        "base_url": None,
    },
    "ollama": {
        "name": "Ollama (Local)",
        "models": [],  # Populated dynamically via fetch_ollama_models()
        "default_model": "qwen3.5:27b",
        "needs_api_key": False,
        "base_url": "http://ollama:11434/v1",
    },
}


def fetch_ollama_models(base_url: str = "") -> list[str]:
    """Fetch available model names from Ollama /api/tags endpoint.

    Args:
        base_url: Ollama base URL override. Defaults to settings or Docker internal URL.

    Returns:
        Sorted list of model name strings. Empty list on error.
    """
    import httpx
    url = base_url or get_setting("chat_base_url") or "http://ollama:11434/v1"
    # Strip /v1 suffix — /api/tags is on the root
    api_base = url.replace("/v1", "").rstrip("/")
    try:
        resp = httpx.get(f"{api_base}/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        # Filter out embedding models — they aren't useful for chat
        chat_models = [m for m in models if "embedding" not in m.lower()]
        return sorted(chat_models)
    except Exception as e:
        logger.debug("Could not fetch Ollama models: %s", e)
        return []


# --- Anthropic Tool Format (native) ---

def _tools_anthropic() -> list[dict]:
    """Return tool definitions in Anthropic's native format."""
    return TOOL_DEFINITIONS  # Already in Anthropic format


# --- Gemini Tool Format ---

def _tools_gemini() -> list:
    """Convert tool definitions to google-genai function declarations."""
    from google.genai import types
    declarations = []
    for t in TOOL_DEFINITIONS:
        declarations.append(types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["input_schema"],
        ))
    return [types.Tool(function_declarations=declarations)]


# --- Ollama Self-Query Tool Format (R32: The Mirror) ---

def _tools_ollama() -> list[dict]:
    """Return self-query tool definitions in OpenAI format for Ollama."""
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": t["input_schema"],
    }} for t in SELF_QUERY_DEFINITIONS]


# --- Shared Helpers ---

def _build_api_messages(history: list[dict], include_system: str = "") -> list[dict]:
    """Convert chat history to API message format (Anthropic/Ollama dict format).

    Filters to user/assistant roles with non-empty content.
    Optionally prepends a system message (used by Ollama).

    Args:
        history: Chat history in gr.Chatbot format.
        include_system: If non-empty, prepend as a system message.

    Returns:
        List of {"role": str, "content": str} dicts.
    """
    messages = []
    if include_system:
        messages.append({"role": "system", "content": include_system})
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    return messages


def _execute_tool(tool_name: str, tool_input: dict) -> tuple[str, bool]:
    """Execute a registered tool call by name.

    Args:
        tool_name: Name of the tool (must be in TOOL_REGISTRY).
        tool_input: Dict of keyword arguments to pass to the tool function.

    Returns:
        Tuple of (result_string, is_error). Result is JSON for dicts/lists.
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        logger.error("Unknown tool requested: %s", tool_name)
        return f"Error: Unknown tool '{tool_name}'", True
    try:
        result = fn(**tool_input)
        if isinstance(result, (dict, list)):
            result = json.dumps(result, indent=2, default=str)
        else:
            result = str(result)
        if len(result) > MAX_TOOL_RESULT_CHARS:
            result = result[:MAX_TOOL_RESULT_CHARS] + f"\n... (truncated, {len(result)} total chars)"
        logger.info("Tool executed: %s", tool_name)
        return result, False
    except Exception as e:
        logger.error("Tool execution failed: %s — %s", tool_name, e)
        return f"Error executing {tool_name}: {str(e)}", True


def _run_tool_loop(
    api_call_fn: callable,
    parse_response_fn: callable,
    handle_tool_calls_fn: callable,
    history: list[dict],
    last_response: dict | None = None,
) -> list[dict]:
    """Run the tool-use iteration loop shared across all providers.

    Args:
        api_call_fn: () -> response. Makes the provider-specific API call.
        parse_response_fn: (response) -> (text_parts: list[str], tool_calls: list).
            Extracts text and tool call objects from the provider response.
        handle_tool_calls_fn: (response, tool_calls, history) -> None.
            Executes tools, updates API message state, appends status to history.
        history: Chat history list to append assistant messages to.
        last_response: If provided, stores the last API response as last_response["ref"]
            for token extraction by the calling provider function.

    Returns:
        Updated history.
    """
    for iteration in range(MAX_TOOL_ITERATIONS):
        response = api_call_fn()
        if last_response is not None:
            last_response["ref"] = response
        text_parts, tool_calls = parse_response_fn(response)

        if text_parts:
            history.append({"role": "assistant", "content": "\n".join(text_parts)})

        if not tool_calls:
            break

        logger.info("Tool loop iteration %d: %d tool call(s)", iteration + 1, len(tool_calls))
        handle_tool_calls_fn(response, tool_calls, history)

    return history


# --- Provider-Specific Chat Implementations ---

def _chat_anthropic(api_key: str, model: str, history: list[dict], system_prompt: str,
                    temperature: float = 0.7, top_p: float = 0.9, max_tokens: int = 2048) -> tuple[list[dict], dict]:
    """Run chat loop using Anthropic API with native tool use.

    Args:
        api_key: Anthropic API key.
        model: Model identifier (e.g. 'claude-sonnet-4-20250514').
        history: Chat history in gr.Chatbot message format.
        system_prompt: Full system prompt string.
        temperature: Sampling temperature (0.0-1.0).
        top_p: Nucleus sampling threshold.
        max_tokens: Maximum response tokens.

    Returns:
        Tuple of (updated history, token_counts dict).
    """
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key.strip())
    api_messages = _build_api_messages(history)
    resp_container = {}

    def make_call():
        return client.messages.create(
            model=model, max_tokens=max_tokens, system=system_prompt,
            tools=_tools_anthropic(), messages=api_messages,
            temperature=temperature, top_p=top_p,
        )

    def parse(response):
        text_parts, tool_blocks = [], []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_blocks.append(block)
        return text_parts, tool_blocks

    def handle_tools(response, tool_blocks, history):
        api_messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tb in tool_blocks:
            history.append({"role": "assistant", "content": f"Using `{tb.name}`..."})
            result, is_error = _execute_tool(tb.name, tb.input)
            tool_results.append({
                "type": "tool_result", "tool_use_id": tb.id,
                "content": result, "is_error": is_error,
            })
        api_messages.append({"role": "user", "content": tool_results})

    history = _run_tool_loop(make_call, parse, handle_tools, history, resp_container)

    # Extract token counts from the last API response
    tokens = dict(_EMPTY_TOKEN_COUNTS)
    resp = resp_container.get("ref")
    if resp and hasattr(resp, "usage") and resp.usage:
        tokens["prompt"] = getattr(resp.usage, "input_tokens", 0) or 0
        tokens["response"] = getattr(resp.usage, "output_tokens", 0) or 0
        tokens["total"] = tokens["prompt"] + tokens["response"]

    return history, tokens


def _chat_gemini(api_key: str, model: str, history: list[dict], system_prompt: str,
                 temperature: float = 0.7, top_p: float = 0.9, max_tokens: int = 2048) -> tuple[list[dict], dict]:
    """Run chat loop using Google Gemini API with function calling.

    Args:
        api_key: Google AI API key.
        model: Model identifier (e.g. 'gemini-2.0-flash').
        history: Chat history in gr.Chatbot message format.
        system_prompt: Full system prompt string.
        temperature: Sampling temperature (0.0-1.0).
        top_p: Nucleus sampling threshold.
        max_tokens: Maximum response tokens.

    Returns:
        Tuple of (updated history, token counts dict).
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key.strip())

    # Build Gemini content from history (uses types.Content, not plain dicts)
    contents = []
    for msg in _build_api_messages(history):
        role = "model" if msg["role"] == "assistant" else msg["role"]
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt, tools=_tools_gemini(),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=temperature, top_p=top_p, max_output_tokens=max_tokens,
    )

    def make_call():
        return client.models.generate_content(
            model=model, contents=contents, config=config,
        )

    def parse(response):
        text_parts, fn_calls = [], []
        for part in response.candidates[0].content.parts:
            if part.text:
                text_parts.append(part.text)
            elif part.function_call:
                fn_calls.append(part)
        return text_parts, fn_calls

    def handle_tools(response, fn_calls, history):
        contents.append(response.candidates[0].content)
        fn_response_parts = []
        for fc_part in fn_calls:
            fc = fc_part.function_call
            history.append({"role": "assistant", "content": f"Using `{fc.name}`..."})
            result, is_error = _execute_tool(fc.name, dict(fc.args))
            fn_response_parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": result, "is_error": is_error},
            ))
        contents.append(types.Content(role="user", parts=fn_response_parts))

    resp_container = {}
    history = _run_tool_loop(make_call, parse, handle_tools, history, resp_container)

    # Extract token counts from Gemini usage_metadata
    tokens = dict(_EMPTY_TOKEN_COUNTS)
    resp = resp_container.get("ref")
    if resp and hasattr(resp, "usage_metadata") and resp.usage_metadata:
        um = resp.usage_metadata
        tokens["prompt"] = getattr(um, "prompt_token_count", 0) or 0
        tokens["reasoning"] = getattr(um, "thoughts_token_count", 0) or 0
        tokens["response"] = getattr(um, "candidates_token_count", 0) or 0
        tokens["total"] = tokens["prompt"] + tokens["reasoning"] + tokens["response"]

    return history, tokens


def _chat_ollama(base_url: str, model: str, history: list[dict], system_prompt: str,
                 temperature: float = 0.7, top_p: float = 0.9, max_tokens: int = 8192,
                 num_ctx: int = 0, keep_alive: str = "") -> tuple[list[dict], dict]:
    """Run chat using Ollama via OpenAI-compatible API with self-query tools.

    R32: Janus can now search her own memory via 6 read-only self-query tools.
    RAG still provides passive context; tools add active retrieval on demand.
    think=True captures reasoning. Max 3 tool iterations to bound token budget.

    Args:
        base_url: Ollama OpenAI-compatible endpoint URL.
        model: Model identifier (e.g. 'qwen3:32b').
        history: Chat history in gr.Chatbot message format.
        system_prompt: Full system prompt string.
        temperature: Sampling temperature (0.0-1.0).
        top_p: Nucleus sampling threshold.
        max_tokens: Maximum response tokens.
        num_ctx: Context window size (0 = model default).
        keep_alive: Model keep-alive duration string (e.g. '5m').

    Returns:
        Tuple of (updated history, token counts dict).
    """
    from openai import OpenAI
    client = OpenAI(api_key="ollama", base_url=base_url)
    messages = _build_api_messages(history, include_system=system_prompt)
    ollama_opts = {"options": {"num_ctx": num_ctx}, "keep_alive": keep_alive, "think": True}
    ollama_tools = _tools_ollama()
    tool_calls_used = []  # Track for cognition trace

    def make_call():
        return client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, top_p=top_p, max_tokens=max_tokens,
            tools=ollama_tools if ollama_tools else None,
            extra_body=ollama_opts,
        )

    def parse(response):
        msg = response.choices[0].message
        # Ollama returns thinking via different field names depending on API version.
        extras = getattr(msg, "model_extra", {}) or {}
        reasoning = (
            getattr(msg, "reasoning_content", None)
            or extras.get("reasoning")
            or extras.get("reasoning_content")
            or extras.get("thinking")
        )
        if reasoning:
            logger.debug("Thinking captured (%d chars) via Ollama think=True", len(reasoning))
        text_parts = []
        if reasoning:
            text_parts.append(f"<think>{reasoning}</think>")
        if msg.content:
            text_parts.append(msg.content)
        # Extract tool calls if present
        tool_calls = getattr(msg, "tool_calls", None) or []
        return text_parts, tool_calls

    def handle_tools(response, tool_calls, history):
        msg = response.choices[0].message
        # Append assistant message (with tool_calls) to API messages
        assistant_msg = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id or f"call_{tc.function.name}_{len(tool_calls_used)}",
                 "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        # Execute each tool and append results
        for tc in tool_calls:
            fn_name = tc.function.name
            tc_id = tc.id or f"call_{fn_name}_{len(tool_calls_used)}"
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result, is_error = _execute_tool(fn_name, args)
            messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
            tool_calls_used.append(fn_name)
            # Friendly message in UI history
            args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
            history.append({"role": "assistant",
                            "content": f"*Searching: {fn_name}({args_str})*"})

    resp_container = {}
    history = _run_tool_loop(make_call, parse, handle_tools, history, resp_container)

    # Extract token counts from Ollama/OpenAI usage
    tokens = dict(_EMPTY_TOKEN_COUNTS)
    resp = resp_container.get("ref")
    if resp and hasattr(resp, "usage") and resp.usage:
        tokens["prompt"] = getattr(resp.usage, "prompt_tokens", 0) or 0
        tokens["response"] = getattr(resp.usage, "completion_tokens", 0) or 0
        tokens["total"] = tokens["prompt"] + tokens["response"]
    # Attach tool call trace for cognition tracking
    if tool_calls_used:
        tokens["_tool_calls"] = tool_calls_used

    return history, tokens


# --- Main Chat Entry Point ---

def chat(message: str, history: list[dict],
         conversation_id: str = "",
         provider_override: str = "", model_override: str = "",
         temperature: float = 0.7, top_p: float = 0.9, max_tokens: int = 8192,
         system_prompt_append: str = "") -> dict:
    """Send a message using settings from the database (with optional overrides).

    Args:
        message: User's new message text.
        history: Current conversation history in gr.Chatbot format.
        conversation_id: Active conversation ID for prompt composer context.
        provider_override: Override provider (empty = use DB setting).
        model_override: Override model (empty = use DB setting).
        temperature: Sampling temperature.
        top_p: Top-p nucleus sampling.
        max_tokens: Maximum response tokens.
        system_prompt_append: Per-conversation system prompt addition.

    Returns:
        Dict with keys: history, rag_metrics, token_counts, timings, provider, model.
    """
    from services.settings import get_setting
    from services.turn_timer import TurnTimer

    _EMPTY_TIMINGS = {"rag": 0, "inference": 0, "total": 0}

    provider = provider_override or get_setting("chat_provider")
    api_key = get_setting("chat_api_key")
    model = model_override or get_setting("chat_model")
    logger.info("Chat: provider=%s, model=%s", provider, model)
    base_url = get_setting("chat_base_url")

    # R19 Bootstrap lifecycle: sleeping → awake on first message
    if get_setting("janus_lifecycle_state") == "sleeping":
        from services.settings import set_setting
        set_setting("janus_lifecycle_state", "awake")
        logger.info("Bootstrap: first chat message, state → awake")

    # R26: Intent classification (< 5ms, no I/O)
    from services.intent_router import classify_intent, RAGDepth
    intent_result = classify_intent(
        message, conversation_turn_count=len(history) // 2)
    logger.info("Intent: %s (%.0f%% conf, RAG=%s, precog=%s)",
                intent_result.intent.value, intent_result.confidence * 100,
                intent_result.rag_depth.value, intent_result.run_precognition)

    # R30: Entity-aware routing (gated by RAG depth, <10ms)
    entity_result = None
    if intent_result.rag_depth != RAGDepth.NONE:
        try:
            from services.entity_routing import detect_entities
            entity_result = detect_entities(message)
            if entity_result and entity_result.entities_found:
                logger.info("Entity routing: %d entities found (%s)",
                            len(entity_result.entities_found),
                            ", ".join(e.name for e in entity_result.entities_found))
        except Exception as e:
            logger.debug("Entity routing unavailable: %s", e)

    # R25: Pre-cognition — adaptive prompt shaping (gated by intent)
    precog_directives = {}
    if intent_result.run_precognition:
        try:
            from services.precognition import run_precognition
            precog_directives = run_precognition(conversation_id, history,
                                                 user_message=message)
        except Exception as e:
            logger.debug("Pre-cognition unavailable: %s", e)

    # R32: Thread intent and register exemplars through directives
    precog_directives["intent"] = intent_result.intent.value
    _RELATIONAL_INTENTS_SET = {"greeting", "emotional", "farewell",
                                "continuation"}
    if intent_result.intent.value in _RELATIONAL_INTENTS_SET:
        try:
            from atlas.register_mining import search_register_exemplars
            exemplars = search_register_exemplars(message, limit=3)
            if exemplars:
                precog_directives["register_exemplars"] = exemplars
        except Exception:
            pass

    # R33: Inject previous turn's Post-Cognition corrective signal
    try:
        from db.chat_operations import get_latest_postcognition_signal
        last_postcog = get_latest_postcognition_signal(conversation_id)
        if last_postcog and last_postcog.get("corrective_directive"):
            precog_directives["postcognition_correction"] = (
                last_postcog["corrective_directive"])
    except Exception:
        pass

    system_prompt, prompt_layers = _build_system_prompt(
        history, conversation_id, directives=precog_directives)
    if system_prompt_append and system_prompt_append.strip():
        system_prompt += f"\n\n{system_prompt_append.strip()}"

    def _error_result(error_history):
        return {
            "history": error_history,
            "rag_metrics": dict(_EMPTY_RAG_METRICS),
            "token_counts": dict(_EMPTY_TOKEN_COUNTS),
            "timings": dict(_EMPTY_TIMINGS),
            "provider": provider,
            "model": model,
            "cognition_trace": {},
        }

    with TurnTimer() as timer:
        # R26/R30: RAG depth gated by intent + entity routing
        # High-confidence entity matches downgrade FULL → LIGHT
        effective_rag_depth = intent_result.rag_depth
        rag_depth_adjusted = ""
        if (entity_result and effective_rag_depth == RAGDepth.FULL
                and any(e.confidence >= 0.7
                        for e in entity_result.entities_found)):
            effective_rag_depth = RAGDepth.LIGHT
            rag_depth_adjusted = "FULL \u2192 LIGHT"
            logger.info("Entity routing downgraded RAG: %s", rag_depth_adjusted)

        # Extract entity_ids for graph retrieval inside _build_rag_context
        entity_ids = (
            [e.entity_id for e in entity_result.entities_found]
            if entity_result and entity_result.entities_found else None
        )

        with timer.span("rag"):
            if effective_rag_depth == RAGDepth.FULL:
                rag_context, rag_metrics = _build_rag_context(
                    message, skip_gate=True, entity_ids=entity_ids,
                    intent=intent_result.intent.value)
            elif effective_rag_depth == RAGDepth.LIGHT:
                rag_context, rag_metrics = _build_light_rag_context(message)
            else:
                rag_context = ""
                rag_metrics = dict(_EMPTY_RAG_METRICS, skipped=True,
                                   skip_reason=intent_result.intent.value)

        # R30: Prepend entity structured context before RAG context
        if entity_result and entity_result.structured_context:
            rag_context = entity_result.structured_context + "\n\n" + rag_context

        if rag_context:
            system_prompt += rag_context
        logger.debug("System prompt composed (%d chars)", len(system_prompt))

        # Validate API key for providers that need it
        preset = PROVIDER_PRESETS.get(provider, {})
        if preset.get("needs_api_key") and (not api_key or not api_key.strip()):
            return _error_result(history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": f"No API key set. Add your {preset.get('name', provider)} API key in the Admin tab sidebar."},
            ])

        # Add user message
        history = history + [{"role": "user", "content": message}]

        try:
            with timer.span("inference"):
                if provider == "anthropic":
                    history, token_counts = _chat_anthropic(api_key, model, history, system_prompt, temperature, top_p, max_tokens)
                elif provider == "gemini":
                    history, token_counts = _chat_gemini(api_key, model, history, system_prompt, temperature, top_p, max_tokens)
                elif provider == "ollama":
                    url = base_url or preset.get("base_url", "http://ollama:11434/v1")
                    num_ctx = int(get_setting("ollama_num_ctx"))
                    keep_alive = get_setting("ollama_keep_alive")
                    history, token_counts = _chat_ollama(url, model, history, system_prompt, temperature, top_p, max_tokens,
                                                          num_ctx=num_ctx, keep_alive=keep_alive)
                else:
                    history.append({"role": "assistant", "content": f"Unknown provider: {provider}"})
                    return _error_result(history)

            return {
                "history": history,
                "rag_metrics": rag_metrics,
                "token_counts": token_counts,
                "timings": timer.results(),
                "provider": provider,
                "model": model,
                "system_prompt_length": len(system_prompt),
                # R21: Cognition trace for introspection surface
                "cognition_trace": {
                    "intent": {
                        "intent": intent_result.intent.value,
                        "confidence": intent_result.confidence,
                        "rag_depth": intent_result.rag_depth.value,
                        "run_precognition": intent_result.run_precognition,
                        "reasoning": intent_result.reasoning,
                    },
                    # R30: Entity routing trace
                    "entity_routing": {
                        **(entity_result.trace if entity_result else {}),
                        "rag_depth_adjusted": rag_depth_adjusted,
                    },
                    "graph_retrieval": rag_metrics.get(
                        "graph_retrieval_trace", {}),
                    "prompt_layers": prompt_layers,
                    "graph_trace": rag_metrics.get("graph_trace", {}),
                    "temporal_trace": rag_metrics.get("temporal_trace", {}),
                    "rag_query": message,
                    "history_turns_sent": len(history) // 2,
                    "precognition": precog_directives,  # R25
                    "tool_calls": token_counts.pop("_tool_calls", []),  # R32
                },
            }
        except Exception as e:
            logger.error("Chat failed: provider=%s, model=%s — %s", provider, model, e)
            history.append({"role": "assistant", "content": f"Error: {str(e)}"})
            return _error_result(history)


def chat_with_janus(message: str) -> dict:
    """Send a message to Janus through the full pipeline and return response + diagnostics.

    Runs the complete chat pipeline: intent classification, pre-cognition, RAG retrieval,
    graph ranking, temporal decay, inference, message persistence, and triple-write.
    Returns the model response alongside full cognition trace and RAG metrics.

    Use this to diagnose pipeline behavior, test RAG quality, or interact with Janus
    programmatically via MCP.

    Args:
        message: The message to send to Janus.

    Returns:
        Dict with response, cognition_trace, rag_metrics, timings, token_counts,
        provider, model, conversation_id, message_id.
    """
    from db.chat_operations import (
        get_or_create_janus_conversation, get_messages, add_message,
        add_message_metadata, update_message_metadata, parse_reasoning,
    )
    from services.settings import get_setting

    conv_id = get_or_create_janus_conversation()

    # Load recent history in gr.Chatbot format
    window = int(get_setting("janus_context_messages") or "10")
    raw_msgs = get_messages(conv_id, limit=window * 2, latest=True)
    history = []
    for m in raw_msgs:
        if m.get("user_prompt"):
            history.append({"role": "user", "content": m["user_prompt"]})
        if m.get("model_response"):
            history.append({"role": "assistant", "content": m["model_response"]})

    # Run full pipeline
    result = chat(message, history, conversation_id=conv_id)

    # Extract response
    new_messages = result["history"][len(history):]
    raw_response = ""
    for msg in reversed(new_messages):
        if msg.get("role") == "assistant":
            raw_response = msg.get("content", "")
            break

    reasoning, clean_response = parse_reasoning(raw_response)
    rag_metrics = result.get("rag_metrics", {})
    token_counts = result.get("token_counts", {})
    timings = result.get("timings", {})
    cognition_trace = result.get("cognition_trace", {})
    provider = result.get("provider", "")
    model = result.get("model", "")

    # Decompose reasoning tokens if needed
    if reasoning and token_counts.get("reasoning", 0) == 0:
        completion = token_counts.get("response", 0)
        r_len = len(reasoning)
        c_len = len(clean_response or raw_response)
        total_len = r_len + c_len
        if completion > 0 and total_len > 0:
            token_counts["reasoning"] = int(completion * r_len / total_len)
            token_counts["response"] = completion - token_counts["reasoning"]

    # Persist triplet message
    msg_id = add_message(
        conversation_id=conv_id,
        user_prompt=message,
        model_reasoning=reasoning or None,
        model_response=clean_response or raw_response,
        provider=provider, model=model,
        tools_called=json.dumps(cognition_trace.get("tool_calls", [])),
        tokens_prompt=token_counts.get("prompt", 0),
        tokens_reasoning=token_counts.get("reasoning", 0),
        tokens_response=token_counts.get("response", 0),
    )

    # Persist metadata
    if msg_id:
        add_message_metadata(
            message_id=msg_id,
            latency_total_ms=timings.get("total", 0),
            latency_rag_ms=timings.get("rag", 0),
            latency_inference_ms=timings.get("inference", 0),
            rag_hit_count=rag_metrics.get("hit_count", 0),
            rag_hits_used=rag_metrics.get("hits_used", 0),
            rag_collections=json.dumps(rag_metrics.get("collections_searched", [])),
            rag_avg_rerank=rag_metrics.get("avg_rerank_score", 0.0),
            rag_avg_salience=rag_metrics.get("avg_salience", 0.0),
            rag_scores=json.dumps(rag_metrics.get("scores", [])),
            system_prompt_length=result.get("system_prompt_length", 0),
            rag_context_text=rag_metrics.get("context_text", ""),
            rag_synthesized=1 if rag_metrics.get("synthesized") else 0,
            cognition_prompt_layers=json.dumps(
                cognition_trace.get("prompt_layers", {})),
            cognition_graph_trace=json.dumps(
                cognition_trace.get("graph_trace", {})),
            cognition_precognition=json.dumps(
                cognition_trace.get("precognition", {})),
        )

        # Usage signal
        try:
            from atlas.usage_signal import compute_usage_signal
            from atlas.memory_service import write_usage_salience
            scores = rag_metrics.get("scores", [])
            if scores and (clean_response or raw_response):
                usage = compute_usage_signal(scores, clean_response or raw_response)
                if usage:
                    update_message_metadata(msg_id, rag_scores=json.dumps(usage))
                    for coll in {u.get("source", "") for u in usage if u.get("source")}:
                        col_hits = [u for u in usage if u.get("source") == coll]
                        write_usage_salience(coll, col_hits)
        except Exception:
            pass

        # Triple-write: chunk + embed + INFORMED_BY edges
        try:
            from atlas.on_write import on_message_write
            on_message_write(
                message_id=msg_id,
                conversation_id=conv_id,
                user_prompt=message,
                model_response=clean_response or raw_response,
                provider=provider, model=model,
                rag_hits=rag_metrics.get("scores", []),
            )
        except Exception:
            pass

    # R33: Post-Cognition — evaluate response, store corrective signal
    postcog_signal = {}
    if msg_id:
        try:
            from services.postcognition import run_postcognition
            tone_dir = cognition_trace.get("precognition", {}).get(
                "tone_directive", "")
            postcog_signal = run_postcognition(
                janus_response=clean_response or raw_response,
                user_message=message,
                tone_directive=tone_dir,
                precognition_signals=cognition_trace.get("precognition"),
            )
            if postcog_signal.get("postcognition_used"):
                update_message_metadata(
                    msg_id,
                    cognition_postcognition=json.dumps(postcog_signal),
                )
        except Exception:
            pass

    # Build diagnostic return — everything an architect needs
    return {
        "response": clean_response or raw_response,
        "reasoning": reasoning[:500] if reasoning else "",
        "conversation_id": conv_id,
        "message_id": msg_id or "",
        "provider": provider,
        "model": model,
        "timings": timings,
        "token_counts": token_counts,
        "cognition_trace": cognition_trace,
        "postcognition": postcog_signal,
        "rag_summary": {
            "hit_count": rag_metrics.get("hit_count", 0),
            "hits_used": rag_metrics.get("hits_used", 0),
            "hits_rejected": len(rag_metrics.get("rejected_scores", [])),
            "collections": rag_metrics.get("collections_searched", []),
            "synthesized": rag_metrics.get("synthesized", False),
            "skipped": rag_metrics.get("skipped", False),
            "skip_reason": rag_metrics.get("skip_reason", ""),
            "temporal_trace": rag_metrics.get("temporal_trace", {}),
            "graph_trace": rag_metrics.get("graph_trace", {}),
        },
        "rag_hits": [
            {
                "title": s.get("title", ""),
                "score": s.get("ann_score", 0),
                "text_preview": s.get("text_preview", "")[:150],
                "source_conversation": s.get("source_conversation_title", ""),
                "created_at": s.get("created_at", ""),
                "temporal_factor": s.get("temporal_factor", 1.0),
                "age_days": s.get("age_days"),
            }
            for s in rag_metrics.get("scores", [])[:10]
        ],
    }
