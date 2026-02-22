"""Chat service — Multi-provider AI with tool use against JANATPMP database.

Supported providers:
- anthropic: Claude models (Opus 4, Sonnet 4, Haiku) — native tool use
- gemini: Google Gemini models (Flash, Pro) — function calling via google-genai
- ollama: Local models via OpenAI-compatible API (Nemotron, etc.) — tool use if model supports it

Settings (provider, model, API key, etc.) are read from the settings DB on each
chat() call — no restart needed when settings change.
"""
import inspect
import json
import logging
from typing import Any
from db import operations as db_ops
from shared.constants import MAX_TOOL_ITERATIONS, RAG_SCORE_THRESHOLD
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

        sig = inspect.signature(fn)
        doc = inspect.getdoc(fn) or ""
        arg_descriptions = _parse_docstring_args(doc)

        # Build properties from function signature
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            # Determine JSON schema type from annotation
            annotation = param.annotation
            if annotation != inspect.Parameter.empty:
                type_name = getattr(annotation, "__name__", str(annotation))
                # Handle Optional types
                origin = getattr(annotation, "__origin__", None)
                if origin is not None:
                    args = getattr(annotation, "__args__", ())
                    if type(None) in args:
                        # Optional[X] — use the non-None type
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

            # Required if no default value
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        # First line of docstring as tool description
        description = doc.split("\n")[0] if doc else name.replace("_", " ").title()

        tool_def = {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }
        tools.append(tool_def)

    return tools


# Pre-build tool definitions at import time
TOOL_DEFINITIONS = _build_tool_definitions()

# --- System Prompt ---

DEFAULT_SYSTEM_PROMPT = """You are an AI assistant embedded in JANATPMP (Janat Project Management Platform).
You help Mat manage projects, tasks, and documents across multiple domains.

Key context:
- Items are projects, books, features, websites, etc. organized by domain and hierarchy.
- Tasks are work items assigned to agents, Claude, Mat, Janus, or unassigned.
- Documents store conversations, research, session notes, code, and artifacts.
- Relationships connect any two entities (items, tasks, documents).

Domains: literature, janatpmp, janat, atlas, nexusweaver, websites, social, speaking, life

You are a collaborator, not just an assistant. Be thoughtful, expressive, and thorough in your responses."""

DEFAULT_SYSTEM_PROMPT_TOOLS = """
You have access to 22 database tools. Use them freely when asked to create, update, search,
or manage items, tasks, and documents. Always confirm what you did after using a tool.
When listing or searching, present results concisely. When creating, confirm the ID and key fields."""


def _build_system_prompt(has_tools: bool = True) -> str:
    """Compose the full system prompt from default + custom + auto-context.

    Layers: DEFAULT_SYSTEM_PROMPT + tool instructions (if model supports tools)
    + user custom prompt (from settings) + live project context snapshot.

    Args:
        has_tools: Whether the model supports tool calling. If False,
            tool-related instructions are omitted to avoid confusing the model.

    Returns:
        Complete system prompt string for injection into API call.
    """
    from services.settings import get_setting
    from db.operations import get_context_snapshot

    base = DEFAULT_SYSTEM_PROMPT
    if has_tools:
        base += DEFAULT_SYSTEM_PROMPT_TOOLS

    custom = get_setting("chat_system_prompt")
    if custom and custom.strip():
        base += f"\n\nAdditional Instructions:\n{custom.strip()}"

    context = get_context_snapshot()
    if context:
        base += f"\n\nCurrent Project State:\n{context}"

    return base


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
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit)).fetchall()

        for row in rows:
            text = f"Q: {row['user_prompt']}\nA: {row['model_response']}"
            results.append({
                "id": row["id"],
                "text": text,
                "score": 0.0,
                "source_collection": "messages",
                "conversation_id": row["conversation_id"],
                "conv_title": row["conv_title"] or "",
                "created_at": row["created_at"] or "",
                "_fts_match": True,
            })
    except Exception as e:
        logger.debug("FTS search failed: %s", e)
    return results


def _build_rag_context(user_message: str) -> tuple[str, dict]:
    """Hybrid search: Qdrant vectors + SQLite FTS keyword matching.

    Two-source retrieval ensures both semantic similarity AND keyword matches
    surface relevant content. Particularly important for specific terms like
    "Entry #008" buried deep in long messages.

    Reads rag_score_threshold and rag_max_chunks from settings DB so they
    can be tuned at runtime via the Admin panel.

    Args:
        user_message: The user's current message.

    Returns:
        Tuple of (formatted context string, RAG metrics dict).
        Returns ("", empty_metrics) if no results or Qdrant unavailable.
    """
    metrics = dict(_EMPTY_RAG_METRICS, scores=[], rejected=[])
    try:
        from services.vector_store import search_all
        threshold = float(get_setting("rag_score_threshold") or RAG_SCORE_THRESHOLD)
        max_chunks = int(get_setting("rag_max_chunks") or 10)
        # Fetch extra candidates — short stubs and low-quality hits will be
        # filtered out below, so we need headroom to still fill max_chunks.
        results = search_all(user_message, limit=max_chunks * 3)

        # Hybrid: FTS keyword search catches specific terms (Entry #008,
        # proper nouns) buried deep in long messages that vector search
        # misses. FTS results go FIRST — they matched by exact keyword,
        # which is a strong signal that vector similarity can't replicate.
        fts_results = _fts_search_messages(user_message, limit=max_chunks)
        seen_ids = set()
        merged = []
        for fts_r in fts_results:
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
                    if rerank < 0.3:
                        candidate_info["reject_reason"] = f"rerank {rerank:.3f} < 0.3"
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

            # Inject the A (response) portion with brief Q context,
            # not the raw "Q: ... A: ..." which wastes context on the question
            if q_part and a_part != full_text:
                q_summary = q_part[:100] + ("..." if len(q_part) > 100 else "")
                inject_text = f"(asked: {q_summary})\n{a_part[:2000]}"
            else:
                inject_text = full_text[:2000]
            context_parts.append(f"[{source}] {title}: {inject_text}")
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
        extra_body={"options": {"num_ctx": int(get_setting("ollama_num_ctx"))}},
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
        "default_model": "nemotron-3-nano:latest",
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


# --- OpenAI / Ollama Tool Format ---

def _tools_openai() -> list[dict]:
    """Convert tool definitions to OpenAI function-calling format.
    Used by Ollama (OpenAI-compatible API)."""
    tools = []
    for t in TOOL_DEFINITIONS:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })
    return tools


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


_ollama_no_tools_models: set[str] = set()


def _chat_ollama(base_url: str, model: str, history: list[dict], system_prompt: str,
                 temperature: float = 0.7, top_p: float = 0.9, max_tokens: int = 8192,
                 num_ctx: int = 0, keep_alive: str = "") -> tuple[list[dict], dict]:
    """Run chat loop using Ollama via OpenAI-compatible API.

    Tool use depends on model capability — gracefully falls back to no tools
    if the model doesn't support function calling. Models that reject tools
    are cached for the process lifetime to avoid repeated failed attempts.

    Args:
        base_url: Ollama OpenAI-compatible endpoint URL.
        model: Model identifier (e.g. 'nemotron-3-nano:latest').
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
    tools = _tools_openai()
    use_tools = bool(tools) and model not in _ollama_no_tools_models
    ollama_opts = {"options": {"num_ctx": num_ctx}, "keep_alive": keep_alive, "think": True}

    def make_call():
        nonlocal use_tools
        if use_tools:
            try:
                return client.chat.completions.create(
                    model=model, messages=messages,
                    tools=tools,
                    temperature=temperature, top_p=top_p, max_tokens=max_tokens,
                    extra_body=ollama_opts,
                )
            except Exception as e:
                logger.info("Ollama model %s does not support tools, disabling: %s", model, e)
                _ollama_no_tools_models.add(model)
                use_tools = False
        return client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, top_p=top_p, max_tokens=max_tokens,
            extra_body=ollama_opts,
        )

    def parse(response):
        msg = response.choices[0].message
        # Ollama returns thinking via different field names depending on API version.
        # Check: reasoning_content (OpenAI convention), thinking (Ollama native),
        # and model_extra (Pydantic catch-all for unknown fields).
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
        return text_parts, msg.tool_calls or []

    def handle_tools(response, tool_calls, history):
        messages.append(response.choices[0].message.model_dump())
        for tc in tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            history.append({"role": "assistant", "content": f"Using `{fn_name}`..."})
            result, is_error = _execute_tool(fn_name, fn_args)
            messages.append({
                "role": "tool", "tool_call_id": tc.id, "content": result,
            })

    resp_container = {}
    history = _run_tool_loop(make_call, parse, handle_tools, history, resp_container)

    # Extract token counts from Ollama/OpenAI usage
    tokens = dict(_EMPTY_TOKEN_COUNTS)
    resp = resp_container.get("ref")
    if resp and hasattr(resp, "usage") and resp.usage:
        tokens["prompt"] = getattr(resp.usage, "prompt_tokens", 0) or 0
        tokens["response"] = getattr(resp.usage, "completion_tokens", 0) or 0
        tokens["total"] = tokens["prompt"] + tokens["response"]

    return history, tokens


# --- Main Chat Entry Point ---

def chat(message: str, history: list[dict],
         provider_override: str = "", model_override: str = "",
         temperature: float = 0.7, top_p: float = 0.9, max_tokens: int = 8192,
         system_prompt_append: str = "") -> dict:
    """Send a message using settings from the database (with optional overrides).

    Args:
        message: User's new message text.
        history: Current conversation history in gr.Chatbot format.
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
    # Ollama models that don't support tools get a cleaner system prompt
    has_tools = provider != "ollama" or model not in _ollama_no_tools_models
    system_prompt = _build_system_prompt(has_tools=has_tools)
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
        }

    with TurnTimer() as timer:
        # RAG context injection (gracefully degrades if Qdrant unavailable)
        with timer.span("rag"):
            rag_context, rag_metrics = _build_rag_context(message)
        if rag_context:
            system_prompt += rag_context

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
            }
        except Exception as e:
            logger.error("Chat failed: provider=%s, model=%s — %s", provider, model, e)
            history.append({"role": "assistant", "content": f"Error: {str(e)}"})
            return _error_result(history)
