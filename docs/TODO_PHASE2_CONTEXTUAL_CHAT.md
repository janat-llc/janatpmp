# TODO: Phase 2 — Contextual Sidebar, Work Tab, and Claude Chat

**Created:** 2026-02-09
**Author:** Claude (The Weavers)
**Executor:** Claude Code
**Status:** READY FOR EXECUTION
**Branch:** `feature/phase2-contextual-chat`

---

## CONTEXT

Phase 1 delivered a working single-page app with dual sidebars, Projects tab with
detail editing, and Admin tab with backup/restore. The left sidebar is currently static
(always shows project cards). Phase 2 makes the sidebar contextual, adds the Work tab,
and wires up Claude chat with full tool use in the right sidebar.

**Read CLAUDE.md first.** It reflects the current architecture accurately.

### What exists today

```
app.py → build_page() → dual sidebars + 4 tabs (Projects, Work stub, Knowledge stub, Admin)
Left sidebar: project cards, filters, +New (always visible, not contextual)
Right sidebar: Claude chat placeholder (not wired)
Center: Projects tab has Detail/List View. Work and Knowledge are empty stubs.
```

### What Phase 2 delivers

1. **Contextual left sidebar** — content changes based on active tab
2. **Work tab** — task list in sidebar, task detail/create in center
3. **Claude chat** — Anthropic API with tool use against all 22 db operations
4. **API key management** — entered in Admin tab, stored in session state

---

## FILE STRUCTURE (changes)

```
JANATPMP/
├── app.py                    # ADD: import services.chat (no other changes)
├── pages/
│   └── projects.py           # REWRITE: contextual sidebar + Work tab content + chat wiring
├── services/                 # NEW directory
│   ├── __init__.py           # empty
│   └── chat.py               # NEW: Anthropic API chat with tool use
├── tabs/
│   ├── __init__.py           # UPDATE: re-export tab_tasks
│   ├── tab_database.py       # UPDATE: add API key field
│   ├── tab_tasks.py          # EXISTS: task list/create (reference, may adapt)
│   └── tab_documents.py      # UNCHANGED (Phase 3)
├── requirements.txt          # ADD: anthropic, google-genai, openai
└── CLAUDE.md                 # DO NOT MODIFY (already current)
```

---

## TASKS

### Task 1: Add `anthropic` dependency

**Edit:** `requirements.txt`

```
gradio[mcp]==6.5.1
pandas
anthropic
google-genai
openai
```

- `anthropic` — Claude models (Opus, Sonnet, Haiku)
- `google-genai` — Gemini models (large context work)
- `openai` — OpenAI-compatible API used by Ollama/local models

Run `pip install anthropic google-genai openai` to verify.

---

### Task 2: Create `services/chat.py` — Multi-Provider Chat Backend with Tool Use

This module handles ALL provider communication (Anthropic, Gemini, Ollama). It must:
- Accept provider config, message, conversation history, and run the full tool-use loop
- Auto-generate tool definitions from `db/operations.py` functions
- Translate tool schemas per provider (Anthropic format, Gemini format, OpenAI format)
- Execute tool calls against the real database
- Return the updated conversation history for `gr.Chatbot`

**Create:** `services/__init__.py`

```python
"""Service modules for JANATPMP."""
```

**Create:** `services/chat.py`

```python
"""Chat service — Multi-provider AI with tool use against JANATPMP database.

Supported providers:
- anthropic: Claude models (Opus 4, Sonnet 4, Haiku) — native tool use
- gemini: Google Gemini models (Flash, Pro) — function calling via google-genai
- ollama: Local models via OpenAI-compatible API (Nemotron, etc.) — tool use if model supports it
"""
import inspect
import json
from typing import Any
from db import operations as db_ops


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

SYSTEM_PROMPT = """You are an AI assistant embedded in JANATPMP (Janat Project Management Platform).
You help Mat manage projects, tasks, and documents across multiple domains.

You have access to 22 database tools. Use them freely when asked to create, update, search,
or manage items, tasks, and documents. Always confirm what you did after using a tool.

Key context:
- Items are projects, books, features, websites, etc. organized by domain and hierarchy.
- Tasks are work items assigned to agents, Claude, Mat, Janus, or unassigned.
- Documents store conversations, research, session notes, code, and artifacts.
- Relationships connect any two entities (items, tasks, documents).

Domains: literature, janatpmp, janat, atlas, nexusweaver, websites, social, speaking, life

When listing or searching, present results concisely. When creating, confirm the ID and key fields.
Be direct and helpful. You are a collaborator, not just an assistant."""


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
        "models": [
            "nemotron:latest",
            "llama3.1:latest",
            "qwen2.5:latest",
        ],
        "default_model": "nemotron:latest",
        "needs_api_key": False,
        "base_url": "http://localhost:11434/v1",
    },
}


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


# --- Tool Execution (shared across all providers) ---

def _execute_tool(tool_name: str, tool_input: dict) -> tuple[str, bool]:
    """Execute a tool call and return (result_string, is_error)."""
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return f"Error: Unknown tool '{tool_name}'", True
    try:
        result = fn(**tool_input)
        if isinstance(result, (dict, list)):
            result = json.dumps(result, indent=2, default=str)
        else:
            result = str(result)
        return result, False
    except Exception as e:
        return f"Error executing {tool_name}: {str(e)}", True


# --- Provider-Specific Chat Implementations ---

def _chat_anthropic(api_key: str, model: str, history: list[dict]) -> list[dict]:
    """Run chat loop using Anthropic API with native tool use."""
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key.strip())

    # Build API messages from chat history (filter to user/assistant only)
    api_messages = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            api_messages.append({"role": role, "content": content})

    max_iterations = 10
    for _ in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=_tools_anthropic(),
            messages=api_messages,
        )

        text_parts = []
        tool_blocks = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_blocks.append(block)

        if text_parts:
            history.append({"role": "assistant", "content": "\n".join(text_parts)})

        if not tool_blocks:
            break

        api_messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tb in tool_blocks:
            history.append({"role": "assistant", "content": f"🔧 Using `{tb.name}`..."})
            result, is_error = _execute_tool(tb.name, tb.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tb.id,
                "content": result,
                "is_error": is_error,
            })
        api_messages.append({"role": "user", "content": tool_results})

    return history


def _chat_gemini(api_key: str, model: str, history: list[dict]) -> list[dict]:
    """Run chat loop using Google Gemini API with function calling."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key.strip())

    # Build Gemini content from history
    contents = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user" and content:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(content)]))
        elif role == "assistant" and content:
            contents.append(types.Content(role="model", parts=[types.Part.from_text(content)]))

    tools = _tools_gemini()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    max_iterations = 10
    for _ in range(max_iterations):
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        text_parts = []
        fn_calls = []
        for part in response.candidates[0].content.parts:
            if part.text:
                text_parts.append(part.text)
            elif part.function_call:
                fn_calls.append(part)

        if text_parts:
            history.append({"role": "assistant", "content": "\n".join(text_parts)})

        if not fn_calls:
            break

        # Add model response to contents
        contents.append(response.candidates[0].content)

        # Execute function calls and build response parts
        fn_response_parts = []
        for fc_part in fn_calls:
            fc = fc_part.function_call
            history.append({"role": "assistant", "content": f"🔧 Using `{fc.name}`..."})
            result, is_error = _execute_tool(fc.name, dict(fc.args))
            fn_response_parts.append(types.Part.from_function_response(
                name=fc.name,
                response={"result": result, "is_error": is_error},
            ))
        contents.append(types.Content(role="user", parts=fn_response_parts))

    return history


def _chat_ollama(base_url: str, model: str, history: list[dict]) -> list[dict]:
    """Run chat loop using Ollama via OpenAI-compatible API.
    Tool use depends on model capability — gracefully falls back to no tools."""
    from openai import OpenAI
    client = OpenAI(api_key="ollama", base_url=base_url)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    tools = _tools_openai()

    max_iterations = 10
    for _ in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools if tools else None,
            )
        except Exception:
            # If tool use fails (model doesn't support it), retry without tools
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )

        choice = response.choices[0]
        msg = choice.message

        if msg.content:
            history.append({"role": "assistant", "content": msg.content})

        if not msg.tool_calls:
            break

        # Add assistant message with tool calls
        messages.append(msg.model_dump())

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            history.append({"role": "assistant", "content": f"🔧 Using `{fn_name}`..."})
            result, is_error = _execute_tool(fn_name, fn_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return history


# --- Main Chat Entry Point ---

def chat(
    provider: str,
    api_key: str,
    model: str,
    message: str,
    history: list[dict],
    base_url: str = "",
) -> list[dict]:
    """Send a message and run the full tool-use loop.

    Args:
        provider: One of 'anthropic', 'gemini', 'ollama'.
        api_key: API key (ignored for ollama).
        model: Model identifier string.
        message: User's new message text.
        history: Current conversation history in gr.Chatbot format.
        base_url: Override base URL (used for ollama, default localhost:11434).

    Returns:
        Updated history with new user message and all assistant responses.
    """
    # Validate API key for providers that need it
    preset = PROVIDER_PRESETS.get(provider, {})
    if preset.get("needs_api_key") and (not api_key or not api_key.strip()):
        return history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": f"⚠️ No API key set. Add your {preset.get('name', provider)} API key in the Admin tab."},
        ]

    # Add user message
    history = history + [{"role": "user", "content": message}]

    try:
        if provider == "anthropic":
            return _chat_anthropic(api_key, model, history)
        elif provider == "gemini":
            return _chat_gemini(api_key, model, history)
        elif provider == "ollama":
            url = base_url or preset.get("base_url", "http://localhost:11434/v1")
            return _chat_ollama(url, model, history)
        else:
            history.append({"role": "assistant", "content": f"⚠️ Unknown provider: {provider}"})
            return history
    except Exception as e:
        history.append({"role": "assistant", "content": f"⚠️ Error: {str(e)}"})
        return history
```

**Key design decisions:**
- **Multi-provider:** Anthropic (Claude), Google (Gemini), Ollama (local Nemotron etc.)
- Tool schemas auto-converted per provider: Anthropic native, OpenAI format (Ollama), Gemini function declarations
- Shared `_execute_tool()` function — all providers run the same db operations
- `PROVIDER_PRESETS` dict stores defaults, model lists, and whether API key is required
- Ollama gracefully falls back to no-tools if the model doesn't support function calling
- Tool definitions are auto-generated at import time from `db/operations.py` docstrings
- Shows tool usage with 🔧 emoji in chat so Mat can see what Claude is doing
- Safety limit of 10 tool-use iterations per message to prevent runaway loops
- Provider-specific imports are lazy (inside functions) to avoid import errors if a package isn't installed

---

### Task 3: Add Model Settings to Admin Tab

**Edit:** `tabs/tab_database.py`

Add a full model configuration section at the top of the Admin tab. This includes
provider selection, model selection (dropdown with presets + ability to type custom),
API key (masked), and Ollama base URL override.

**Add to `build_database_tab()` — at the very top of the tab, before the Stats/Schema row:**

```python
def build_database_tab():
    with gr.Tab("Admin"):
        # Model Settings
        with gr.Accordion("Model Settings", open=True):
            gr.Markdown("Configure the AI model for the sidebar chat.")
            with gr.Row():
                provider_dropdown = gr.Dropdown(
                    choices=["anthropic", "gemini", "ollama"],
                    value="anthropic",
                    label="Provider",
                    interactive=True,
                )
                model_dropdown = gr.Dropdown(
                    choices=[
                        "claude-sonnet-4-20250514",
                        "claude-haiku-4-5-20251001",
                        "claude-opus-4-6",
                    ],
                    value="claude-sonnet-4-20250514",
                    label="Model",
                    allow_custom_value=True,  # user can type any model string
                    interactive=True,
                )
            api_key_input = gr.Textbox(
                label="API Key",
                type="password",
                placeholder="sk-ant-... or AIza...",
                interactive=True,
            )
            base_url_input = gr.Textbox(
                label="Base URL (Ollama only)",
                value="http://localhost:11434/v1",
                visible=False,
                interactive=True,
            )

            # Wire provider change to update model choices and visibility
            def _on_provider_change(provider):
                from services.chat import PROVIDER_PRESETS
                preset = PROVIDER_PRESETS.get(provider, {})
                models = preset.get("models", [])
                default = preset.get("default_model", "")
                needs_key = preset.get("needs_api_key", True)
                is_ollama = provider == "ollama"
                return (
                    gr.Dropdown(choices=models, value=default),  # model_dropdown
                    gr.Textbox(visible=needs_key),               # api_key_input
                    gr.Textbox(visible=is_ollama),               # base_url_input
                )

            provider_dropdown.change(
                _on_provider_change,
                inputs=[provider_dropdown],
                outputs=[model_dropdown, api_key_input, base_url_input],
            )

        # ... rest of existing Admin tab content (stats, schema, backup, etc.) ...
```

**Return all model config components** — add to the returned dict:

```python
return {
    'provider': provider_dropdown,   # NEW
    'model': model_dropdown,         # NEW
    'api_key': api_key_input,        # NEW
    'base_url': base_url_input,      # NEW
    'stats': stats_display,
    'schema': schema_display,
    'backups_table': backups_table,
    'restore_dropdown': restore_dropdown,
}
```

These components will be referenced by the chat event wiring in `projects.py`.

---

### Task 4: Rewrite `pages/projects.py` — Contextual Sidebar + Work Tab + Chat Wiring

This is the core rewrite. The structure changes from hardcoded project sidebar to
a `@gr.render` that reacts to which tab is active.

**Key architecture:**

```python
def build_page():
    # === STATES ===
    active_tab = gr.State("Projects")
    selected_project_id = gr.State("")
    selected_task_id = gr.State("")
    projects_state = gr.State(_load_projects())
    tasks_state = gr.State(_load_tasks())
    chat_history = gr.State([{...initial message...}])

    # === LEFT SIDEBAR (contextual) ===
    with gr.Sidebar(position="left"):
        @gr.render(inputs=[active_tab, projects_state, tasks_state])
        def render_left(tab, projects, tasks):
            if tab == "Projects":
                # project cards, domain/status filters, +New Item
            elif tab == "Work":
                # task cards, status/assignee filters, +New Task
            elif tab == "Knowledge":
                gr.Markdown("*Coming in Phase 3*")
            elif tab == "Admin":
                gr.Markdown("*Admin settings in center panel*")

    # === RIGHT SIDEBAR (chat — always visible) ===
    with gr.Sidebar(position="right"):
        chatbot = gr.Chatbot(...)
        chat_input = gr.Textbox(...)

    # === CENTER TABS ===
    with gr.Tabs() as tabs:
        with gr.Tab("Projects") as projects_tab:
            # Detail/List View sub-tabs (same as Phase 1)
        with gr.Tab("Work") as work_tab:
            # Task Detail/List View sub-tabs
        with gr.Tab("Knowledge") as knowledge_tab:
            gr.Markdown("*Coming in Phase 3*")
        admin_components = build_database_tab()  # returns dict with api_key

    # === TAB TRACKING ===
    projects_tab.select(lambda: "Projects", outputs=[active_tab])
    work_tab.select(lambda: "Work", outputs=[active_tab])
    knowledge_tab.select(lambda: "Knowledge", outputs=[active_tab])
    # Admin tab.select is inside build_database_tab — handle via the Tab object

    # === CHAT WIRING ===
    def handle_chat(message, history, provider, model, api_key, base_url):
        from services.chat import chat
        updated = chat(provider, api_key, model, message, history, base_url)
        return updated, updated, ""  # chatbot display, state, clear input

    chat_input.submit(
        handle_chat,
        inputs=[
            chat_input, chat_history,
            admin_components['provider'],
            admin_components['model'],
            admin_components['api_key'],
            admin_components['base_url'],
        ],
        outputs=[chatbot, chat_history, chat_input],
        api_visibility="private",
    )
```

**Full implementation details:**

#### Left Sidebar — Projects Panel

When `active_tab == "Projects"`, render:
- `gr.Markdown("### Projects")`
- Domain filter dropdown + Status filter dropdown (in a `gr.Row`)
- Refresh button
- `@gr.render(inputs=projects_state)` for project cards (same pattern as Phase 1)
- Each card is a `gr.Button` that sets `selected_project_id` on click
- `gr.Button("+ New Item", variant="primary")` that shows the create form in center

**Important:** The project card click handlers set `selected_project_id`, and the
filter/refresh handlers update `projects_state`. Both are States defined outside the
render, so they can be referenced from inside.

#### Left Sidebar — Work Panel

When `active_tab == "Work"`, render:
- `gr.Markdown("### Work Queue")`
- Status filter dropdown + Assignee filter dropdown (in a `gr.Row`)
- Refresh button
- `@gr.render(inputs=tasks_state)` for task cards
- Each card shows: task title, status, assignee, priority
- Each card click sets `selected_task_id`
- `gr.Button("+ New Task", variant="primary")`

#### Center — Work Tab

The Work tab should mirror the Projects tab structure:

```python
with gr.Tab("Work") as work_tab:
    with gr.Tabs():
        with gr.Tab("Detail"):
            work_detail_header = gr.Markdown("*Select a task from the sidebar.*")
            with gr.Column(visible=False) as work_detail_section:
                # Task fields: title, type, status, assigned_to, priority
                # Description, agent_instructions
                # Save button
                # Target item link
            with gr.Column(visible=False) as work_create_section:
                # Create task form: type, title, description, assigned_to,
                # target_item_id, priority, agent_instructions
                # Create button
        with gr.Tab("List View"):
            # All tasks table (same as tab_tasks.py pattern)
```

**Task detail fields:**
- Title (editable)
- Type (read-only display)
- Status dropdown (editable): pending, processing, blocked, review, completed, failed, retry, dlq
- Assigned To dropdown (editable): agent, claude, mat, janus, unassigned
- Priority dropdown (editable): urgent, normal, background
- Description (editable, multiline)
- Agent Instructions (editable, multiline)
- Target Item ID (read-only display, link to parent item)
- Save button + status message

#### Center — Chat Wiring

The right sidebar chatbot and input are wired like this:

1. `chat_input.submit` → calls `handle_chat()` with message, history, and API key
2. `handle_chat()` calls `services.chat.chat()` which runs the full tool-use loop
3. Returns updated history to both `chatbot` (display) and `chat_history` (state)
4. Clears `chat_input` after submit

The chatbot should also have a Clear button to reset chat history.

**Critical detail:** The provider, model, api_key, and base_url components are all
created inside `build_database_tab()`. Their return values give us component references.
We pass these directly as inputs to the chat submit handler. Gradio reads their
current values at event time.

#### Event Wiring Summary

**Tab tracking:**
```python
projects_tab.select(lambda: "Projects", outputs=[active_tab])
work_tab.select(lambda: "Work", outputs=[active_tab])
knowledge_tab.select(lambda: "Knowledge", outputs=[active_tab])
```

**Note on Admin tab:** The Admin tab is built by `build_database_tab()` which creates
its own `gr.Tab("Admin")`. To track its selection, you'll need to either:
- Return the Tab component from `build_database_tab()` and wire `.select` outside, OR
- Accept that we don't track Admin tab selection (sidebar shows last-active content)

**Recommended:** Return the Tab component. Add to the build_database_tab return dict:
```python
return {
    'tab': admin_tab,      # the gr.Tab component itself
    'api_key': api_key_input,
    ...
}
```
Then in projects.py: `admin_components['tab'].select(lambda: "Admin", outputs=[active_tab])`

**Project events** (same as Phase 1, but inside contextual render):
- Filter changes → update `projects_state`
- Card clicks → update `selected_project_id`
- `selected_project_id.change` → load detail in center Projects tab
- Save → update_item
- Create → create_item + refresh projects_state
- +New button → show create form, hide detail

**Work events** (mirror of project events):
- Filter changes → update `tasks_state`
- Card clicks → update `selected_task_id`
- `selected_task_id.change` → load detail in center Work tab
- Save → update_task
- +New Task button → show create form, hide detail
- Create → create_task + refresh tasks_state

**Chat events:**
- `chat_input.submit` → handle_chat → update chatbot + chat_history + clear input
- Clear button → reset chat_history to initial message

---

### Task 5: Data Helpers for Work Tab

Add these helper functions to `pages/projects.py` (alongside existing project helpers):

```python
TASK_STATUSES = [
    "pending", "processing", "blocked", "review",
    "completed", "failed", "retry", "dlq"
]

TASK_TYPES = [
    "agent_story", "user_story", "subtask",
    "research", "review", "documentation"
]

ASSIGNEES = ["unassigned", "agent", "claude", "mat", "janus"]

PRIORITIES = ["urgent", "normal", "background"]


def _load_tasks(status: str = "", assigned_to: str = "") -> list:
    """Fetch tasks as list of dicts for card rendering."""
    return list_tasks(status=status, assigned_to=assigned_to, limit=100)


def _all_tasks_df() -> pd.DataFrame:
    """Fetch all tasks for the List View."""
    tasks = list_tasks(limit=200)
    if not tasks:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Assigned", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": t["id"][:8],
        "Title": t["title"],
        "Type": _fmt(t.get("task_type", "")),
        "Assigned": _fmt(t.get("assigned_to", "")),
        "Status": _fmt(t.get("status", "")),
        "Priority": _fmt(t.get("priority", "")),
    } for t in tasks])
```

---

### Task 6: Update `tabs/__init__.py`

**Edit:** `tabs/__init__.py`

```python
"""Tab modules for JANATPMP Gradio UI."""
from .tab_database import build_database_tab

# Phase 2+ — available but not directly imported by tabs/__init__
# tab_tasks.py patterns are used as reference in pages/projects.py
# tab_documents.py will be used in Phase 3
```

No need to re-export tab_tasks since the Work tab logic lives in projects.py now,
using the same db operations directly. The tab_tasks.py file remains as reference.

---

### Task 7: Update `tabs/tab_database.py` — Return Tab + All Model Config

**Edit:** `tabs/tab_database.py`

Three changes:
1. Capture the `gr.Tab("Admin")` as a variable and return it
2. Add full model settings accordion (provider, model, API key, base URL)
3. Wire provider change to update model choices and field visibility

See Task 3 above for the full implementation. The return dict should be:

```python
return {
    'tab': admin_tab,
    'provider': provider_dropdown,
    'model': model_dropdown,
    'api_key': api_key_input,
    'base_url': base_url_input,
    'stats': stats_display,
    'schema': schema_display,
    'backups_table': backups_table,
    'restore_dropdown': restore_dropdown,
}
```

---

## WHAT NOT TO DO

- **DO NOT** modify `db/operations.py` — it's correct and stable
- **DO NOT** modify `db/schema.sql` — no schema changes in this phase
- **DO NOT** modify `CLAUDE.md` — it's already current
- **DO NOT** wire Knowledge tab content — that's Phase 3
- **DO NOT** persist chat history to database — that's Phase 3
- **DO NOT** persist the API key to database or localStorage — session-only for now
- **DO NOT** use `demo.load()` for initial data
- **DO NOT** add any dependencies beyond `anthropic`, `google-genai`, and `openai`
- **DO NOT** delete `tabs/tab_tasks.py` or `tabs/tab_documents.py` — keep as reference
- **DO NOT** change the MCP tool exposure in `app.py`

---

## ACCEPTANCE CRITERIA

1. Left sidebar content changes when switching between Projects/Work/Knowledge/Admin tabs
2. Projects tab works exactly as before (card selection, detail editing, create, filters)
3. Work tab shows task cards in left sidebar with status/assignee filters
4. Clicking a task card loads its detail in the center Work tab
5. Task detail fields are editable with Save button that calls `update_task`
6. Create Task form works and refreshes the task list
7. Work tab has a List View sub-tab showing all tasks in a table
8. Claude chat in right sidebar accepts messages and returns responses
9. Claude chat can use tools (create items, search, etc.) and results appear in chat
10. Model Settings in Admin tab: provider dropdown, model dropdown (with custom input), API key, base URL
11. Switching provider updates model choices and hides/shows API key and base URL fields
11. Missing/invalid API key shows helpful error in chat, doesn't crash
12. Chat has a Clear button to reset history
13. Tool usage shows 🔧 indicators in chat so user can see what Claude is doing
14. All 22 MCP tools still exposed and functional (no regression)
15. `python app.py` launches cleanly with no errors

---

## TESTING CHECKLIST

After implementation, verify:

- [ ] Switch tabs → left sidebar updates
- [ ] Projects: filter, select, edit, save, create (no regression)
- [ ] Work: filter by status, filter by assignee, select task, edit, save
- [ ] Work: create new task, verify it appears in sidebar
- [ ] Chat: type message without API key → get error message
- [ ] Chat: enter API key in Admin, type message → get response
- [ ] Chat: "list all projects" → Claude uses list_items tool
- [ ] Chat: "create a task called 'Test chat' assigned to claude" → task appears
- [ ] Chat: Clear button resets conversation
- [ ] MCP endpoint still works: http://localhost:7860/gradio_api/mcp/sse
- [ ] Mobile: both sidebars collapse independently

---

## FUTURE PHASES (not in scope, for context only)

- **Phase 3:** Knowledge tab — document browser, chat history saved to documents table,
  FTS5 search across documents. Chat saves will populate this automatically.
- **Phase 4:** Visual polish — brand CSS, custom cards via gr.HTML, dark theme refinement
- **Phase 5:** BrowserState for API key persistence, chat history persistence across refreshes
