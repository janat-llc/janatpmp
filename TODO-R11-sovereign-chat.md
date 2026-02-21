# TODO: Multi-App Architecture — Sprint "Sovereign Chat"

## Context

JANATPMP is being separated from a monolithic tab-based Gradio app into a multi-page
application using Gradio 6's native `demo.route()` API. Each "page" is a self-contained
Gradio Blocks app with its own sidebars, layout, and event listeners.

**Critical Gradio 6 constraint:** Multipage apps do NOT support interactions between pages.
An event listener on one page cannot output to a component on another page. Each page owns
its own components entirely. Shared state flows through the backend, never through components.

### Architecture

```
app.py              — Main Blocks + route mounting + navbar
├── /               — Projects App (Home)   → pages/projects.py
├── /chat           — Chat App              → pages/chat.py
├── /knowledge      — Knowledge App         → pages/knowledge.py
└── /admin          — Admin App             → pages/admin.py

shared/backend.py   — Shared backend services (DB, Qdrant, Ollama, vLLM clients)
shared/chat_service.py — Chat logic consumed by Chat app AND right sidebars on other pages
```

### Sidebar Architecture (per-page, NOT platform-level)

| Page       | Left Sidebar                              | Right Sidebar                    |
|------------|-------------------------------------------|----------------------------------|
| Projects   | Project tree / work item list (contextual)| Compact chat (own components)    |
| Chat       | RAG health, context sources, metadata     | NONE — Chat IS the main panel    |
| Knowledge  | Conv list / doc tree / search filters     | Compact chat (own components)    |
| Admin      | Service status per admin tab              | Compact chat (own components)    |

Non-Chat pages each instantiate their own compact chat sidebar widget that calls the same
`shared/chat_service.py` backend functions. Chat app exposes config (model, temp, system
prompt) via backend state that sidebar widgets read on load.

### Gradio 6 Multipage Pattern (from official docs)

```python
# Each page file (e.g. pages/chat.py):
import gradio as gr

with gr.Blocks() as demo:
    # ... full page layout with sidebars ...
    pass

if __name__ == "__main__":
    demo.launch()  # standalone testing

# Main app.py:
import gradio as gr
from pages import projects, chat, knowledge, admin

with gr.Blocks() as demo:
    projects.demo.render()

with demo.route("Chat", "/chat"):
    chat.demo.render()

with demo.route("Knowledge", "/knowledge"):
    knowledge.demo.render()

with demo.route("Admin", "/admin"):
    admin.demo.render()

if __name__ == "__main__":
    demo.launch()
```

---

## Phase 1: Shared Backend Extraction

Extract the shared backend layer from the current monolithic app.py so all pages can import it.

### Task 1.1: Create `shared/backend.py`

**What:** Central backend module that owns all database and service connections.

**Extract from current app.py:**
- SQLite database connection and helper functions
- Qdrant client initialization
- Ollama client / HTTP helpers
- vLLM client / HTTP helpers
- All CRUD operations (items, tasks, documents, conversations, messages, relationships, domains)
- Embedding and search functions

**Interface pattern:**
```python
# shared/backend.py
import sqlite3
from qdrant_client import QdrantClient

# Singleton connections
_db = None
_qdrant = None

def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = sqlite3.connect("db/janatpmp.db", check_same_thread=False)
        _db.row_factory = sqlite3.Row
    return _db

def get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(host="localhost", port=6333)
    return _qdrant

# All CRUD functions go here — items, tasks, documents, conversations, etc.
# All search functions go here — semantic search, full-text search
# All embedding functions go here
```

**Rules:**
- No Gradio imports in this file. Pure Python backend.
- No UI logic. Returns data, never components.
- All functions that currently live in app.py that touch DB/services move here.
- This file should be importable by any page without circular dependencies.

### Task 1.2: Create `shared/chat_service.py`

**What:** Chat-specific backend logic used by the Chat app AND the compact sidebar chat on other pages.

**Functions needed:**
```python
# shared/chat_service.py

def get_chat_config() -> dict:
    """Return current global chat config (model, temp, system_prompt, max_tokens)."""

def set_chat_config(model: str, temperature: float, system_prompt: str, max_tokens: int):
    """Update global chat config. Called from Chat app, read by sidebars."""

def get_active_conversation_id() -> str | None:
    """Return the currently active conversation ID."""

def send_message(conversation_id: str, user_message: str) -> dict:
    """
    Process a user message through the full pipeline:
    1. Store user message in SQLite with timestamp
    2. Fan out retrieval: SQL search + Vector search + Relationship lookup
    3. Build context from retrieval results
    4. Send to Ollama/active model with system prompt + context
    5. Store assistant response with provenance metadata
    6. Return {response, provenance: {sql_hits, vector_hits, relationships}}
    """

def get_conversation_history(conversation_id: str) -> list[dict]:
    """Return messages for a conversation, each with created_at timestamp."""

def search_rag(query: str) -> dict:
    """
    Fan-out retrieval across the Triad of Memory:
    - SQL: Full-text search on items, documents, conversations
    - Vector: Semantic search via Qdrant (messages + documents collections)
    - Relationships: Connected entities for top results
    Returns {sql_results, vector_results, relationships, total_sources}
    """
```

**Rules:**
- Imports from `shared/backend.py` for DB/service access
- No Gradio imports
- Stateless functions — config stored in DB or module-level state
- Provenance metadata on every retrieval (source collection, timestamp, score)

---

## Phase 2: Chat App — `/chat`

The sovereign conversation authority. First real page to build.

### Task 2.1: Create `pages/chat.py`

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ [Navbar: Projects | Chat (active) | Knowledge | Admin]  │
├──────────────┬──────────────────────────────────────────┤
│              │                                          │
│  LEFT        │           MAIN PANEL                     │
│  SIDEBAR     │                                          │
│              │   ┌──────────────────────────────────┐   │
│  RAG Health  │   │                                  │   │
│  • Embed ct  │   │         gr.Chatbot               │   │
│  • Last embed│   │                                  │   │
│  • Qdrant OK │   │    Messages with provenance      │   │
│  • Ollama OK │   │    badges showing source count   │   │
│              │   │                                  │   │
│  Context     │   │                                  │   │
│  Sources     │   └──────────────────────────────────┘   │
│  (what RAG   │   ┌──────────────────────────────────┐   │
│   found this │   │  [Message input]     [Send]      │   │
│   turn)      │   └──────────────────────────────────┘   │
│              │                                          │
│  ─────────── │   Config Panel (Accordion, collapsed)    │
│  Conv Meta   │   • Model selector                       │
│  • Created   │   • Temperature slider                   │
│  • Messages  │   • System prompt                        │
│  • Tokens    │   • Max tokens                           │
│              │                                          │
├──────────────┴──────────────────────────────────────────┤
│ [Status bar: model name | active conv | msg count]      │
└─────────────────────────────────────────────────────────┘
```

**Components:**
- `gr.Sidebar(position="left")` — RAG health stats, context sources, conversation metadata
- `gr.Chatbot()` — Main conversation display (scale=1, fill_height)
- `gr.Textbox()` + `gr.Button()` — Message input
- `gr.Accordion("Configuration")` — Model config (collapsed by default)
- `gr.Timer(5)` — Update left sidebar RAG health stats periodically

**Behavior:**
- On send: call `chat_service.send_message()` → update chatbot + left sidebar context sources
- Config changes: call `chat_service.set_chat_config()` → persists for sidebar consumers
- On load: restore active conversation or create new
- Every message stores `created_at` timestamp — temporal affinity from day one
- Provenance: after each response, show small text below the message with retrieval stats
  (e.g., "Retrieved from: 3 conversations, 2 documents, 1 relationship")

**Event listeners:**
```python
msg_input.submit(handle_send, [msg_input, chatbot, conv_state], [msg_input, chatbot, context_display])
send_btn.click(handle_send, [msg_input, chatbot, conv_state], [msg_input, chatbot, context_display])
model_dropdown.change(update_config, [model_dropdown, temp_slider, sys_prompt, max_tokens], None)
timer.tick(refresh_rag_health, None, [embed_count, qdrant_status, ollama_status])
demo.load(on_load, None, [chatbot, conv_state, config_components...])
```

**Critical:** Chat app does NOT have a right sidebar. Chat IS the main panel.

### Task 2.2: Provenance Display

Each assistant message in the chatbot should include provenance metadata. Use the Gradio
Chatbot message format to append a small metadata section:

```python
# After getting response from chat_service:
provenance = result["provenance"]
response_text = result["response"]
provenance_line = f"\n\n---\n*Sources: {provenance['vector_hits']} semantic, {provenance['sql_hits']} structured, {provenance['relationships']} connected*"
# Add to chatbot as assistant message
```

---

## Phase 3: Minimal Viable Other Pages

Lift-and-shift current tab content into standalone page files. NOT a rewrite —
just reorganization to prove the multi-page architecture works.

### Task 3.1: Create `pages/projects.py`

**What:** Current Work tab functionality moved to a standalone page.
**Left sidebar:** Project list / domain filter using `gr.Sidebar(position="left")`
**Right sidebar:** Compact chat widget using `gr.Sidebar(position="right")` — calls
`chat_service.send_message()` and `chat_service.get_chat_config()` directly.
**Main panel:** Current Work tab content (items table, task list, CRUD buttons).

### Task 3.2: Create `pages/knowledge.py`

**What:** Current Knowledge tab functionality + conversation browser moved from Chat.
**Left sidebar:** Contextual — shows conversation list or document list based on active tab.
**Right sidebar:** Compact chat widget (same pattern as Projects).
**Main panel:** Current Knowledge tab content + conversation viewer.

### Task 3.3: Create `pages/admin.py`

**What:** Current Admin tab functionality.
**Left sidebar:** Service status indicators.
**Right sidebar:** Compact chat widget.
**Main panel:** Current Admin tab content (ingestion controls, config, stats).

### Task 3.4: Create new `app.py`

**What:** The multipage app orchestrator. Mounts all pages.

```python
import gradio as gr
from pages import projects, chat, knowledge, admin

with gr.Blocks(
    title="JANATPMP",
    fill_height=True,
    # theme=janat_theme  # apply when ready
) as demo:
    gr.Navbar(main_page_name="Projects")
    projects.demo.render()

with demo.route("Chat", "/chat"):
    chat.demo.render()

with demo.route("Knowledge", "/knowledge"):
    knowledge.demo.render()

with demo.route("Admin", "/admin"):
    admin.demo.render()

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        mcp_server=True,
    )
```

---

## Phase 4: Compact Chat Sidebar Widget

### Task 4.1: Create `shared/chat_sidebar.py`

**What:** A reusable function that returns sidebar components for non-Chat pages.
Since components can't cross page boundaries, this is a builder function each page calls.

```python
# shared/chat_sidebar.py
import gradio as gr
from shared import chat_service

def create_chat_sidebar():
    """
    Call this inside a gr.Sidebar(position="right") context.
    Returns components dict for event listener wiring.
    """
    gr.Markdown("### Quick Chat")
    chatbot = gr.Chatbot(height=400, show_label=False)
    msg = gr.Textbox(placeholder="Ask anything...", show_label=False, max_lines=3)
    send = gr.Button("Send", size="sm")

    config = chat_service.get_chat_config()
    gr.Markdown(f"*Model: {config.get('model', 'default')}*",
                elem_classes="chat-sidebar-config")

    return {"chatbot": chatbot, "msg": msg, "send": send}
```

**Each page wires the returned components to its own event listeners** — because
event listeners cannot cross page boundaries. The handler functions call the same
`chat_service.send_message()` backend.

---

## Execution Order

1. **Phase 1** first — extract shared backend. Nothing else works without it.
2. **Phase 2** — Build Chat app as standalone page (testable with `python pages/chat.py`)
3. **Phase 3.4** — Wire up app.py multipage routing with Chat + stub pages
4. **Phase 3.1-3.3** — Lift current tab content into page files
5. **Phase 4** — Add compact chat sidebars to non-Chat pages

### First Slice (Phases 1 + 2 + app.py skeleton)

The absolute minimum to prove the architecture:
- `shared/backend.py` extracted from current app.py
- `shared/chat_service.py` with at minimum `send_message()` and `search_rag()`
- `pages/chat.py` with full layout, left sidebar, chatbot, config panel
- `app.py` mounting Chat at `/chat` with stub pages for the other three
- Stub pages just show a Markdown header so navigation works

This gives us:
✓ Multi-page navigation working
✓ Chat app fully functional and sovereign
✓ Backend cleanly separated
✓ Stubs ready for Phase 3 lift-and-shift
✓ Each page testable standalone

---

## File Inventory (to create)

```
shared/backend.py         — DB + service connections, all CRUD
shared/chat_service.py    — Chat logic, RAG fan-out, config management
shared/chat_sidebar.py    — Reusable compact chat widget builder (Phase 4)
pages/__init__.py          — Package init
pages/projects.py          — Projects page (stub → Phase 3)
pages/chat.py              — Chat page (full build → Phase 2)
pages/knowledge.py         — Knowledge page (stub → Phase 3)
pages/admin.py             — Admin page (stub → Phase 3)
app.py                     — Multipage orchestrator (replaces current app.py)
```

## Important Notes

- **Backup current app.py** before replacing. `cp app.py app_monolith_backup.py`
- **Do NOT delete tabs/ directory yet** — Phase 3 will reference it for lift-and-shift
- **Test each page standalone** before wiring into multipage app
- Current Gradio version must be 6.x — verify with `pip show gradio`
- `gr.Sidebar` is the layout component for sidebars (see Controlling Layout docs)

### API / MCP Architecture

**Critical:** Gradio multipage apps share ONE backend. All pages are part of the same
Blocks instance. API endpoints and MCP tools registered on ANY page remain available
regardless of which page the user is viewing. Navigating pages is client-side routing —
the backend never tears down.

From docs: "All of these pages will share the same backend, including the same queue."

**gr.api() for headless MCP tools:** Gradio provides `gr.api()` for creating pure API
endpoints with no UI components. Use this in app.py for JANATPMP backend operations
(CRUD, search, embedding) that should be available as MCP tools regardless of page:

```python
# In app.py, after page mounting:
gr.api(backend.search_items)         # MCP: search items
gr.api(backend.create_item)          # MCP: create item
gr.api(backend.semantic_search)      # MCP: vector search
gr.api(chat_service.send_message)    # MCP: send chat message
# etc.
```

This cleanly separates UI event listeners (per-page, with api_name for page-specific
endpoints) from backend MCP tools (app-level, always available via gr.api()).
