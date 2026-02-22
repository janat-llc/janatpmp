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
}

_EMPTY_TOKEN_COUNTS = {"prompt": 0, "reasoning": 0, "response": 0, "total": 0}


def _build_rag_context(user_message: str) -> tuple[str, dict]:
    """Search Qdrant for relevant context and format for injection.

    Reads rag_score_threshold and rag_max_chunks from settings DB so they
    can be tuned at runtime via the Admin panel.

    Args:
        user_message: The user's current message.

    Returns:
        Tuple of (formatted context string, RAG metrics dict).
        Returns ("", empty_metrics) if no results or Qdrant unavailable.
    """
    metrics = dict(_EMPTY_RAG_METRICS, scores=[])
    try:
        from services.vector_store import search_all
        threshold = float(get_setting("rag_score_threshold") or RAG_SCORE_THRESHOLD)
        max_chunks = int(get_setting("rag_max_chunks") or 3)
        results = search_all(user_message, limit=max_chunks)
        if not results:
            return "", metrics

        metrics["hit_count"] = len(results)
        metrics["collections_searched"] = list({r.get("source_collection", "unknown") for r in results})

        context_parts = []
        used_scores = []
        for r in results:
            # Prefer rerank_score (cross-encoder relevance) over ANN score.
            # Qwen3-Reranker scores are 0-1 probabilities (via vLLM).
            # ANN scores are cosine similarity (0-1), only used as fallback.
            rerank = r.get("rerank_score")
            if rerank is not None:
                if rerank < 0.3:
                    continue  # Reranker says low relevance (0-1 scale)
            else:
                if r.get("score", 0) <= threshold:
                    continue  # ANN fallback — below threshold
            source = r.get("source_collection", "unknown")
            title = r.get("title", r.get("conv_title", ""))
            text = r.get("text", "")[:500]
            context_parts.append(f"[{source}] {title}: {text}")
            used_scores.append({
                "source": source, "title": title,
                "rerank_score": rerank or 0.0,
                "salience": r.get("salience", 0.0),
                "ann_score": r.get("score", 0.0),
            })

        metrics["hits_used"] = len(used_scores)
        metrics["scores"] = used_scores
        if used_scores:
            metrics["avg_rerank_score"] = sum(s["rerank_score"] for s in used_scores) / len(used_scores)
            metrics["avg_salience"] = sum(s["salience"] for s in used_scores) / len(used_scores)

        if not context_parts:
            return "", metrics

        context = "\n\n---\nRelevant context from knowledge base:\n" + "\n\n".join(context_parts) + "\n---\n"
        return context, metrics
    except Exception as e:
        logger.debug("RAG context unavailable: %s", e)
        return "", metrics  # Graceful degradation if Qdrant is down


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
        contents.append(types.Content(role=role, parts=[types.Part.from_text(msg["content"])]))

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
