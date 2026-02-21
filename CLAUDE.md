# CLAUDE.md - Project Guidelines for AI Assistants

## Project Overview

**JANATPMP (Janat Project Management Platform)** is a Gradio-based project management
platform designed for solo architects and engineers working with AI partners. It provides
persistent project state that AI assistants can read and write via MCP (Model Context Protocol).

**Status:** Active development
**Goal:** Strategic command center for consciousness architecture work across multiple domains.

## Tech Stack

- **Python** 3.14+
- **Gradio** 6.5.1 with MCP support (`gradio[mcp]==6.5.1`)
- **SQLite3** for persistence (WAL mode, FTS5 full-text search)
- **Pandas** for data display
- **Qdrant** vector database (semantic search, 2560-dim cosine collections)
- **Ollama** for chat LLM + embedding (Qwen3-Embedding-4B via `/v1/embeddings`)
- **vLLM** sidecar for cross-encoder reranking (Qwen3-Reranker-0.6B via `/v1/score`)

## Project Structure

```
JANATPMP/
├── app.py                    # Thin orchestrator: init_database(), build_page(), gr.api(), launch
├── janat_theme.py            # Custom Gradio theme (Janat brand colors, fonts, CSS)
├── pages/
│   ├── __init__.py
│   └── projects.py           # UI layout + event wiring (~1220 lines)
├── tabs/
│   ├── __init__.py
│   ├── tab_database.py       # Database/Admin tab builder (imported by projects.py)
│   ├── tab_chat.py           # Chat handler functions (sidebar + Chat tab)
│   └── tab_knowledge.py      # Knowledge tab handlers (conversations, search, connections)
├── shared/
│   ├── __init__.py
│   ├── constants.py           # All enum lists, magic numbers, default values
│   ├── formatting.py          # fmt_enum(), entity_list_to_df() display helpers
│   └── data_helpers.py        # Data-loading helpers (_load_projects, _all_items_df, etc.)
├── db/
│   ├── schema.sql            # Database schema DDL (NO seed data)
│   ├── seed_data.sql         # Optional seed data (separate from schema)
│   ├── operations.py         # All CRUD + lifecycle functions (26 operations)
│   ├── chat_operations.py    # Conversation + message CRUD (Phase 4B)
│   ├── test_operations.py    # Tests
│   ├── migrations/           # Versioned schema migrations
│   │   ├── 0.3.0_conversations.sql
│   │   ├── 0.4.0_app_logs.sql
│   │   ├── 0.4.1_messages_fts_update.sql
│   │   └── 0.4.2_domains_table.sql
│   ├── janatpmp.db           # SQLite database (runtime, gitignored)
│   ├── backups/              # Timestamped database backups
│   └── __init__.py
├── atlas/                    # ATLAS model infrastructure (R9, offloaded R10)
│   ├── __init__.py
│   ├── config.py             # Model names, dimensions, service URLs, salience constants
│   ├── embedding_service.py  # Qwen3-Embedding-4B via Ollama HTTP (OpenAI client)
│   ├── reranking_service.py  # Qwen3-Reranker-0.6B via vLLM HTTP (httpx client)
│   ├── memory_service.py     # Salience write-back to Qdrant payloads
│   └── pipeline.py           # Two-stage search: ANN → rerank → salience
├── services/
│   ├── __init__.py
│   ├── log_config.py         # SQLiteLogHandler + setup_logging() + get_logs()
│   ├── chat.py               # Multi-provider chat with tool use (Anthropic/Gemini/Ollama)
│   ├── claude_export.py      # Claude Export service: ingest/query external conversation DB
│   ├── claude_import.py      # Claude conversations.json import → triplet messages (Phase 5)
│   ├── embedding.py          # Thin shim → atlas.embedding_service
│   ├── vector_store.py       # Qdrant vector DB + two-stage search pipeline
│   ├── bulk_embed.py         # Batch embed via Ollama with progress & checkpointing
│   ├── settings.py           # Settings registry with validation and categories
│   └── ingestion/            # Content ingestion parsers (Phase 6A)
│       ├── __init__.py
│       ├── google_ai_studio.py  # Google AI Studio chunkedPrompt parser
│       ├── quest_parser.py      # Troubadourian quest graph topology parser
│       ├── markdown_ingest.py   # Markdown & text file ingester
│       ├── dedup.py             # SHA-256 content-hash deduplication
│       └── README.md            # Format documentation & test results
├── assets/
│   └── janat_logo_bold_transparent.png  # Janat Mandala logo (brand header)
├── docs/
│   ├── janatpmp-mockup.png   # Visual reference for Projects page layout
│   ├── INVENTORY_OLD_PARSERS.md    # Old pipeline code inventory (Phase 6A)
│   └── INVENTORY_CONTENT_CORPUS.md # Content corpus catalog (Phase 6A)
├── completed/                # Archived TODO files and dead prototype tabs
├── screenshots/              # UI screenshots for reference
├── requirements.txt          # Python dependencies (pinned)
├── pyproject.toml            # Project metadata
├── Dockerfile                # Container image (Python 3.14-slim, no GPU)
├── docker-compose.yml        # Container orchestration (core, ollama, vllm-rerank, qdrant)
├── Janat_Brand_Guide.md      # Brand colors, fonts, design system
└── CLAUDE.md                 # This file
```

## Architecture

### Single-Page, Tab-Based Layout

The app is a single Gradio Blocks page with top-level tabs and dual collapsible sidebars.
This approach was chosen over multi-page routing (`demo.route()`) because:

- Sidebars persist across all tab switches (no re-render, no context loss)
- Simpler state management (one Blocks context, shared gr.State)
- Mobile-friendly: both sidebars collapse independently via built-in hamburger toggle
- No page reload flicker between views

```
┌──────────────────────────────────────────────────────────────────────┐
│  JANATPMP                                    Powered by [Janat]     │
├──────────────────────────────────────────────────────────────────────┤
│  [Projects] [Work] [Knowledge] [Chat] [Admin]  ← gr.Tabs()         │
├──────────┬───────────────────────────────────┬───────────────────────┤
│  LEFT    │     CENTER CONTENT              │  RIGHT                │
│  SIDEBAR │                                 │  SIDEBAR              │
│          │                                 │                       │
│  Context │  Content changes per tab        │  Janat Chat (default)  │
│  cards   │  selected. Each top-level       │  OR Chat Settings      │
│  Filters │  tab can have sub-tabs          │  (when Chat tab active)│
│  +New    │  (Detail/List View, etc.)       │                       │
└──────────┴───────────────────────────────────┴───────────────────────┘
```

**Implementation in code:**

```python
# app.py
with gr.Blocks(title="JANATPMP") as demo:
    build_page()          # builds everything: sidebars + tabs + wiring
    gr.api(create_item)   # MCP tools exposed here
    ...
demo.launch(mcp_server=True, server_name="0.0.0.0")
```

```python
# pages/projects.py — build_page() function
# Handler functions are extracted to tabs/ and shared/ modules.
# projects.py retains layout construction + event wiring (~1220 lines).
def build_page():
    with gr.Sidebar(position="left"):
        # Project list, filters, create form
    with gr.Sidebar(position="right"):
        # Claude chat placeholder
    # Center content — main Blocks body, no wrapper needed
    with gr.Tabs():
        with gr.Tab("Projects"):
            ...
        with gr.Tab("Work"):
            ...
        with gr.Tab("Knowledge"):
            ...
        with gr.Tab("Chat"):
            ...  # Independent provider/model, full-width chatbot
        build_database_tab()  # "Admin" tab from tabs/tab_database.py
```

**Use `gr.Sidebar` for both side panels — NOT `gr.Column` in a `gr.Row`.**
Sidebar is collapsible, mobile-friendly, and purpose-built for this layout.
The center content is just the main Blocks body (no Row/Column wrapper needed).

### Five Tabs (current state)

| Tab | Left Sidebar | Center | Status |
|-----|-------------|--------|--------|
| **Projects** | Project cards, filters, + New | Detail editor, List View | ✅ Working |
| **Work** | Task cards, filters, + New Task | Task detail, List View | ✅ Working |
| **Knowledge** | Document cards, filters, + New Doc | Documents (Detail/List), Search, Connections, Conversations | ✅ Working |
| **Chat** | Conversation history list, + New Chat | Full-width chatbot (Enter=send), triplet persistence | ✅ Working |
| **Admin** | Quick Settings (provider/model/key) | System Prompt editor, Stats, Backup/Restore | ✅ Working |

### Contextual Sidebars

The left sidebar uses `@gr.render(inputs=[active_tab, projects_state, tasks_state])`
to dynamically switch content based on the active tab. The right sidebar is also
contextual: it shows Janat chat on all tabs EXCEPT Chat, where it transforms
into a Chat Settings panel (provider, model, temperature, top_p, system prompt append,
tool toggles). The sidebar chat is a continuous conversation window — it loads the
most recent conversation on startup and carries context forward. No clear button;
the conversation is persistent by design. Both sidebars use state bridge patterns —
render-created components sync to gr.State via .change listeners for cross-component
data flow.

### Settings & Chat Architecture

**Settings table** (`settings` in SQLite) — key-value store for persistent configuration:
- `chat_provider` — "anthropic", "gemini", or "ollama"
- `chat_model` — Model identifier string
- `chat_api_key` — Base64-encoded API key (obfuscation, NOT encryption)
- `chat_base_url` — Override URL for Ollama
- `chat_system_prompt` — Custom system prompt (empty = use default)
- `claude_export_db_path` — Path to claude_export.db
- `claude_export_json_dir` — Path to JSON export directory

**Settings flow:**
- `services/settings.py` provides `get_setting()` / `set_setting()` with auto base64 for secrets
- Admin sidebar quick-settings save on change (no save button needed)
- Chat reads settings from DB on each message — no restart needed
- `init_database()` calls `init_settings()` to seed defaults on first run

**Chat auto-context injection:**
- `db/operations.py:get_context_snapshot()` builds a summary of active items + pending tasks
- `services/chat.py:_build_system_prompt()` composes: default prompt + custom prompt + auto-context
- Fresh context is injected per message, so the AI always knows current project state

### Knowledge Tab

The Knowledge tab surfaces documents, search, and entity relationships:

- **Documents** — CRUD for session notes, research, artifacts, conversation imports, code.
  Same sidebar-card + detail pattern as Projects and Work tabs.
- **Search** — Universal FTS5 search across items AND documents simultaneously.
  Uses `search_items()` and `search_documents()` from db/operations.py.
- **Connections** — Relationship viewer. Look up any entity (item/task/document) by ID
  to see incoming and outgoing relationships. Create new connections inline.
- **Conversations** — Browse Claude export history via Chatbot viewer. Reads from
  external `claude_export.db` via `services/claude_export.py`. Ingest from JSON exports.

**Claude Export settings:**
- `claude_export_db_path` — Path to claude_export.db file
- `claude_export_json_dir` — Path to directory with JSON exports (users.json, projects.json, conversations.json)
  Uses `get_relationships()` and `create_relationship()` from db/operations.py.

All 6 underlying operations (`create_document`, `get_document`, `list_documents`,
`search_documents`, `create_relationship`, `get_relationships`) were built in Phase 1
and exposed via MCP — Phase 3 only adds the UI layer.

### Data Flow

```
db/operations.py → 26 functions → three surfaces:
    1. UI: imported by pages/projects.py, called in event listeners
    2. API: exposed via gr.api() in app.py
    3. MCP: auto-generated from gr.api() + docstrings
```

**Key principles:**

- One set of functions in `db/operations.py` serves UI, API, and MCP
- NO `demo.load()` — data is computed at build time and passed via `value=`
- `gr.api()` exposes db functions as MCP tools without UI components
- `build_page()` is the single entry point for all UI construction

### Shared Module (`shared/`)

Centralized constants, formatting, and data-loading helpers used across UI and services.

- **`shared/constants.py`** — Enum lists (STATUSES, TASK_TYPES, etc.), magic numbers, defaults. Domains are NOT here — they live in the `domains` database table.
  (`MAX_TOOL_ITERATIONS=10`, `RAG_SCORE_THRESHOLD`), and `DEFAULT_CHAT_HISTORY`.
- **`shared/formatting.py`** — `fmt_enum()` (converts `not_started` → `Not Started`),
  `entity_list_to_df()` (generic DataFrame builder from entity dicts).
- **`shared/data_helpers.py`** — Data-loading functions extracted from projects.py:
  `_load_projects()`, `_children_df()`, `_all_items_df()`, `_load_tasks()`, `_all_tasks_df()`,
  `_load_documents()`, `_all_docs_df()`, `_msgs_to_history()`, `_load_most_recent_chat()`.

### Logging Architecture (`services/log_config.py`)

Centralized logging with SQLite persistence:

- **`SQLiteLogHandler`** — Custom `logging.Handler` that writes to `app_logs` table.
  Batches writes (flushes on WARNING+ or every 10 records) to minimize DB overhead.
- **`setup_logging(level)`** — Configures root logger with console + SQLite handlers.
  Called at app startup in `app.py` before any other imports.
- **`get_logs(level, module, limit, since)`** — Query function used by Admin UI log viewer.
- **`cleanup_old_logs(days=30)`** — Retention policy, called on startup.

All services use `logger = logging.getLogger(__name__)` and log at appropriate levels:
INFO for operations, WARNING for fallbacks, ERROR for failures.

### Settings Registry (`services/settings.py`)

Settings use a `SETTINGS_REGISTRY` dict where each key maps to
`(default, is_secret, category, validator_fn)`:

- **Categories:** `chat`, `ollama`, `export`, `ingestion`, `rag`, `system`
- **Validation:** `set_setting()` validates before storing, returns error string on failure
- **Secrets:** Base64-encoded (obfuscation, not encryption). Auto-encoded/decoded by
  `get_setting()` / `set_setting()`.
- `get_settings_by_category(category)` returns all settings for a given category.

### CDC Outbox Retention

The `cdc_outbox` table captures all database mutations for future sync to Qdrant/Neo4j.
`cleanup_cdc_outbox(days=90)` in `db/operations.py` deletes processed entries older than
90 days. Called on startup after `init_database()`.

## Database Schema (db/schema.sql)

**Core Tables:**
- `domains` — First-class organizational entity. Each domain has name, display_name,
  description, color, is_active. Replaces the old hardcoded DOMAINS list. UI dropdowns
  show only active domains; `create_item()` validates against all domains (active + inactive).
  CDC triggers for Qdrant/Neo4j sync.
- `items` — Projects, features, books, etc. across domains. Supports hierarchy via parent_id.
  Has JSON attributes for domain-specific data. FTS5 full-text search enabled.
  Domain validation is app-level via `get_domain()` (no CHECK constraint in schema).
- `tasks` — Work queue with agent/human assignment. Supports retry logic, dependencies,
  acceptance criteria, cost tracking.
- `documents` — Conversations, files, artifacts, research. FTS5 enabled.
- `relationships` — Universal connector between any two entities. Typed relationships
  (blocks, enables, informs, etc.) with hard/soft strength.
- `conversations` — Chat sessions from any source (platform, claude_export, imported).
  Stores provider/model snapshot, system_prompt_append, temperature, top_p, max_tokens.
  Fields: source (platform/claude_export/imported), conversation_uri (Claude Export linkage),
  is_active (1=visible, 0=archived), message_count.
- `messages` — Triplet message schema for training data pipeline. Each turn stores:
  user_prompt, model_reasoning (chain-of-thought/think blocks), model_response (visible reply).
  Per-turn provider/model snapshot, token counts (prompt/reasoning/response), tools_called JSON.
  Ordered by (conversation_id, sequence). FTS5 on user_prompt + model_response.
- `app_logs` — Application log records (level, module, function, message, metadata JSON).
  Written by `SQLiteLogHandler`, queryable via Admin UI.
- `settings` — Key-value application configuration. Base64 for secrets. Auto-updated timestamps.
- `cdc_outbox` — Change Data Capture for future Qdrant/Neo4j sync. Auto-cleaned on startup (90 days).
- `schema_version` — Migration tracking.

**Migrations** (in `db/migrations/`):

- `0.3.0_conversations.sql` — Conversations + messages tables, FTS, CDC triggers
- `0.4.0_app_logs.sql` — Application logs table with indexes
- `0.4.1_messages_fts_update.sql` — Missing FTS UPDATE trigger on messages
- `0.4.2_domains_table.sql` — Domains as first-class entity, items table CHECK removal, CDC domain support

**Domains** are managed in the `domains` table (not hardcoded). 13 seeded domains:
5 active (janat, janatpmp, literature, websites, becoming) and 8 inactive (atlas, meax,
janatavern, amphitheatre, nexusweaver, social, speaking, life). Domain validation in
`create_item()` checks all domains (active + inactive). UI dropdowns show active only.

## Commands

```bash
# Local development
pip install -r requirements.txt
python app.py
# App at http://localhost:7860
# MCP at http://localhost:7860/gradio_api/mcp/sse
# API docs at http://localhost:7860/gradio_api/docs
# Accessible from other devices on LAN (mobile, etc.)

# Docker
docker-compose build
docker-compose up              # foreground
docker-compose up -d           # detached
docker-compose down
docker-compose logs -f
```

## Git Workflow

### Branch Naming
`feature/phase{version}-{description}` — examples:
- `feature/phase4b-chat-experience`
- `feature/phase5-claude-export-ingestion`

### Starting Work
1. Ensure you're on `main` and it's up to date
2. Create feature branch: `git checkout -b feature/phase{X}-{name}`
3. Do all work on the feature branch

### Completing Work
1. Verify everything runs: `docker compose down && docker compose up -d --build`
2. Commit with descriptive message: `git add -A && git commit -m "Phase {X}: {summary of changes}"`
3. Merge to main: `git checkout main && git merge feature/phase{X}-{name}`
4. Delete feature branch: `git branch -d feature/phase{X}-{name}`
5. Move completed TODO to `completed/` directory

### Commit Message Format
`Phase {version}: {one-line summary}` — examples:
- `Phase 4B: Chat experience redesign — triplet message schema, conversation persistence, AI Studio layout`
- `Phase 3: Knowledge tab — documents UI, universal search, connections viewer`

For smaller fixes within a phase: `Phase {version}: Fix {description}`

### Rules
- Never commit directly to `main` — always use a feature branch
- One phase = one branch = one merge
- If a phase has sub-phases (4A, 4B), each gets its own branch
- Completed TODO files move to `completed/` as part of the merge commit

## Conventions

### Code Conventions
- All functions in db/operations.py MUST have full docstrings with Args and Returns
  (Gradio uses these for MCP tool descriptions)
- Use `pathlib.Path` for all path handling
- ISO format for timestamps
- Empty string = "no filter" / "no change" in function parameters
- Functions return strings for status messages, dicts for single entities, lists for collections
- Context managers for database connections (`get_connection()`)

### UI Conventions
- **`api_visibility="private"`** on ALL UI event listeners (keeps them off the MCP/API surface)
- **`server_name="0.0.0.0"`** in launch calls (enables mobile/LAN access)
- **No `demo.load()` anywhere** — bake initial data via `value=` parameter
- **Display formatting** — enum values like `not_started` display as `Not Started` in UI only,
  never modify database values. Use: `value.replace("_", " ").title()`

### Mobile Considerations
- App is accessed from both desktop and phone (same WiFi network)
- `gr.Sidebar` is collapsible by design — collapses to hamburger toggle on mobile
- Both left and right sidebars collapse independently, leaving center content full-width
- Avoid `size="sm"` on critical touch targets
- This dual-sidebar pattern gives us mobile-friendly layout with zero custom CSS

## Docker

- **Image:** Python 3.14-slim (no GPU dependencies — ~500 MB image)
- **Port:** 7860
- **Volume:** `.:/app` for live code changes without rebuild
- **MCP:** Enabled via `GRADIO_MCP_SERVER=True` environment variable
- **CMD:** `python app.py`
- **Container names:** `janatpmp-core` (app), `janatpmp-ollama` (LLM + embed),
  `janatpmp-vllm-rerank` (reranker), `janatpmp-qdrant` (vector DB)
  - Core has NO GPU — all model inference offloaded to Ollama and vLLM sidecars
- **Qdrant:** `janatpmp-qdrant` container on ports 6343:6333/6344:6334
  - Internal URL: `http://janatpmp-qdrant:6333` (Docker DNS)
  - External URL: `http://localhost:6343` (host access, dashboard at `/dashboard`)
  - Volume: `janatpmp_qdrant_data` (external)
  - Collections: `janatpmp_documents` (2560-dim), `janatpmp_messages` (2560-dim)
- **Ollama:** `janatpmp-ollama` container on port 11435, shares `ollama_data` external volume
  - Internal URL: `http://ollama:11434/v1` (Docker DNS)
  - External URL: `http://localhost:11435` (host access for testing)
  - GPU passthrough via NVIDIA Container Toolkit (~70% VRAM)
  - `OLLAMA_KEEP_ALIVE=30m` keeps model warm between turns (prevents GPU spike/crash)
  - Chat model: Nemotron-3-Nano-30B-A3B IQ4_XS (~18 GB)
  - Embedding model: Qwen3-Embedding-4B Q4_K_M GGUF (~2.5 GB) — used via `/v1/embeddings`
- **vLLM Reranker:** `janatpmp-vllm-rerank` container on port 8002
  - Internal URL: `http://janatpmp-vllm-rerank:8000` (Docker DNS)
  - External URL: `http://localhost:8002` (host access for testing)
  - Runs Qwen3-Reranker-0.6B FP16 (~1.7 GB) with `--task score`
  - GPU passthrough via NVIDIA Container Toolkit (~5% VRAM)
  - Volume: `huggingface_cache` (shared HF model cache)

## Gradio Development Patterns (CRITICAL — READ BEFORE WRITING UI CODE)

This app is built with **Gradio Blocks**, NOT Gradio Interface. These are fundamentally
different paradigms. Do NOT use Interface patterns (demo.load for every component,
static layouts, flat input/output wiring). Use Blocks patterns as described below.

### Architecture: @gr.render() for Dynamic UI

`@gr.render()` creates reactive UI regions that rebuild when their inputs change.
This eliminates manual refresh wiring.

**Pattern — Reactive List Display:**
```python
with gr.Blocks() as demo:
    items_state = gr.State([])
    
    @gr.render(inputs=items_state)
    def render_items(items):
        if not items:
            gr.Markdown("No items yet.")
            return
        for item in items:
            with gr.Row(key=f"item-{item['id']}"):
                gr.Textbox(item['title'], show_label=False, container=False)
                btn = gr.Button("Delete", scale=0, variant="stop")
                def delete(item=item):  # Freeze loop variable!
                    items.remove(item)
                    return items
                btn.click(delete, None, [items_state])
```

**Key rules for @gr.render():**
1. ALL event listeners that use components created inside render MUST be defined inside render
2. Event listeners CAN reference components defined OUTSIDE the render function
3. Loop variables used in event listeners MUST be frozen: `def handler(item=item):`
4. Always use `key=` on components inside render to preserve values across re-renders
5. If layouts (gr.Row, gr.Column) wrap keyed components, key the layouts too
6. State changes that should trigger re-render must set the State as an output
7. By default, render triggers on `.change` of inputs and `demo.load`. Override with `triggers=`
8. Use `preserved_by_key=["value", "label"]` to control what survives re-render

### State Management

**gr.State** — Session-scoped, invisible component that holds any Python value.
- Use for data that drives UI (item lists, filter values, selected records)
- Changes to State trigger `.change` listeners and `@gr.render()` re-runs
- For lists/dicts: change is detected when ANY element changes
- For objects/primitives: change is detected via hash

**Global variables** — Shared across ALL users. Use only for read-only config.

**gr.BrowserState** — Persists in localStorage across page refreshes. Use for preferences.

### Event Listener Patterns

**DO — Use `api_visibility="private"` on all UI listeners:**
```python
btn.click(handler, inputs=[...], outputs=[...], api_visibility="private")
```

**DO — Use State to trigger cascading updates:**
```python
items_state = gr.State([])

def add_item(title, items):
    new_item = create_item(title=title)
    return items + [new_item], ""

create_btn.click(add_item, [title_input, items_state], [items_state, title_input],
                 api_visibility="private")
```

**DO NOT — Wire manual refresh to every button:**
```python
# WRONG: This is demo-pattern thinking
create_btn.click(create_fn, inputs, [status_msg])
create_btn.click(refresh_table, None, [table])  # Manual refresh
```

### Loading Initial Data

**DO — Bake data into components at build time via `value=`:**
```python
items_table = gr.DataFrame(value=_items_to_df(), interactive=False)
```

**DO NOT — Use `demo.load()` to populate components after page load:**
```python
# WRONG: causes async callbacks, race conditions, and 30+ second spinners
demo.load(lambda: get_items_dataframe(), outputs=[items_table])
```

### MCP Integration

Gradio auto-generates MCP tools from functions with proper docstrings:

```python
with gr.Blocks() as demo:
    build_page()
    gr.api(create_item)  # Becomes MCP tool, no UI element
    ...

demo.launch(mcp_server=True)
```

All 26 functions in `db/operations.py` (including 4 domain CRUD) plus 8 chat operations
from `db/chat_operations.py` plus 6 vector/embedding operations from `services/` plus 1
import operation are exposed via `gr.api()` (46 total MCP tools). They MUST have
Google-style docstrings with Args/Returns for MCP tool generation.

### Common Mistakes to Avoid

| Mistake | Fix |
|---------|-----|
| Using `gr.Interface` | Use `gr.Blocks` with explicit layout |
| Using `demo.load()` for initial data | Bake data in with `value=` at build time |
| Manual refresh after every action | Use `@gr.render(inputs=state)` for reactive updates |
| Forgetting `key=` in render loops | Always key components and their parent layouts |
| Not freezing loop variables | Use `def handler(item=item):` pattern |
| Returning `gr.update()` for complex state | Return new State value, let render rebuild |
| Wiring outputs to 10+ components per click | Use State as single output, render reacts |
| Missing `api_visibility="private"` | Add to ALL UI event listeners |
| Using `gr.Column` for side panels | Use `gr.Sidebar(position="left"/"right")` instead |
| Wrapping center+right in `gr.Row` | Center is main body, sidebars are separate |

## Important Notes

- The database starts EMPTY (no seed data). Users build their project landscape from scratch.
- Every db operation must work from all three surfaces: UI, API, MCP
- Do NOT add features not specified in the current TODO file
- Do NOT modify `db/operations.py` or `db/schema.sql` unless the TODO explicitly requires it
- Do NOT add new pip dependencies unless the TODO explicitly requires it
- When in doubt, ask — don't guess

## Phase 4B Architecture Decisions

### Triplet Message Schema (Training Data Pipeline)
Every conversation turn stores three distinct artifacts:
- **user_prompt**: what was asked
- **model_reasoning**: chain-of-thought / thinking tokens (e.g. `<think>` blocks from deepseek-r1)
- **model_response**: the visible reply

This enables fine-tuning Nemotron on its own reasoning patterns. Can extract prompt→reasoning,
reasoning→response, or full triplets for different training objectives.

### Conversation Sources
The `conversations` table holds ALL conversation history, not just platform chats:
- `source='platform'`: Created in Chat tab
- `source='claude_export'`: 600+ conversations imported from Claude Export
- `source='imported'`: From other sources (Gemini, etc.)

Any conversation, regardless of source, can be loaded into Chat UI and discussed with
any provider/model. Claude Export ingestion creates conversations + messages records
alongside the existing documents pipeline in services/claude_export.py.

### System Prompt Layering
Base system prompt lives in Admin settings (platform context, tool descriptions).
Per-conversation append field allows scoping to specific project/persona.
At inference: `base_prompt + "\n\n" + session_append`.

### Chat Flow
1. User types message, presses Enter
2. If no active conversation, auto-create one (title = first 50 chars of first prompt)
3. Call `chat()` with override params (provider, model, temperature, top_p, max_tokens, system_prompt_append) — no temp DB setting changes
4. Parse reasoning from response via `parse_reasoning()` (`<think>` block extraction)
5. Collect tool names from "Using `tool`..." status messages
6. Store triplet via `add_message()` (user_prompt, model_reasoning, model_response, tools_called)
7. Update conversations list in left sidebar

### "New Chat" Semantics
Not "Clear Chat" — "New Chat" verifies current conversation is persisted, creates a new
conversation record, clears the display, sets the new one as active. Never destructive.

### Database Operations (db/chat_operations.py)
- `create_conversation()`, `get_conversation()`, `list_conversations()`, `update_conversation()`, `delete_conversation()`, `search_conversations()` (FTS)
- `add_message()`, `get_messages()`, `get_next_sequence()`
- `parse_reasoning(raw_response)` → `tuple[str, str]` — extracts `<think>` blocks
- Follows existing patterns: hex randomblob IDs, datetime('now'), FTS, CDC outbox triggers

### Tool Routing (Future — Noted, Not Solved)
Some tool calls route to Nemotron locally, others to Claude (via MCP), others to Gemini.
Schema captures routing data (tools_called JSON, per-turn provider/model snapshots).
Tool toggles in right sidebar control availability per-session. Full routing is its own phase.

### Critical Implementation Notes
- Relationships table CHECK constraint must be updated to allow 'conversation' and 'message'
  entity types. SQLite has no ALTER CONSTRAINT — requires table recreation (create new,
  copy data, drop old, rename).
- Event listeners for render-created components MUST be inside the render function.
- Import scoping: NEVER local imports inside render_left for names already imported at
  module level (causes UnboundLocalError due to Python scoping).

## Phase 5: RAG Pipeline (Complete, offloaded in R10)

### Two-Stage Search Pipeline

Search uses a two-stage retrieval pipeline orchestrated by `atlas/pipeline.py`:

1. **ANN search** — Qdrant approximate nearest neighbor, top-20 candidates (configurable via `RERANK_CANDIDATES`)
2. **Cross-encoder reranking** — Qwen3-Reranker-0.6B (via vLLM) rescores candidates by relevance (0-1 probability)
3. **Salience write-back** — Rerank scores update `salience` metadata in Qdrant payloads

Both `search()` and `search_all()` in `services/vector_store.py` accept `rerank=True` (default).
Set `rerank=False` for bulk operations or when the reranker is not needed. Graceful degradation:
if the reranker is unavailable, ANN results are returned with a warning.

### Vector Search Architecture

- **Qdrant** vector database with two collections: `janatpmp_documents` and `janatpmp_messages` (2560-dim cosine)
- **Qwen3-Embedding-4B** via Ollama `/v1/embeddings` (2560-dim Matryoshka, asymmetric query/passage encoding)
  - Document encoding: `embed_texts(texts)` — no instruction prefix
  - Query encoding: `embed_query(query)` — prepends Qwen3 instruction prefix for asymmetric retrieval
  - Client-side `[:EMBEDDING_DIM]` truncation for Matryoshka safety
- **Qwen3-Reranker-0.6B** via vLLM `/v1/score` (cross-encoder, FP16)
  - Scores query-document relevance as 0-1 probabilities
  - Adds `rerank_score` field to results
- **HuggingFace cache** shared via external Docker volume (`huggingface_cache`)
- **Salience metadata** — Qdrant payloads track `salience` (weighted score) and `last_retrieved` (ISO timestamp)

### RAG Context Injection

- `services/chat.py:_build_rag_context()` searches Qdrant on each user message
- Results with rerank_score > 0.3 are injected into the system prompt as context
- Graceful degradation: if Qdrant is down, chat works without RAG (try/except)
- Cross-collection search via `vector_store.search_all()` searches both documents and messages

### Claude Import (`services/claude_import.py`)

- Imports Claude `conversations.json` into triplet message schema
- Each conversation becomes a `conversations` record with `source='imported'`
- Each message pair becomes a `messages` record with user_prompt + model_response
- Deduplicates by `conversation_uri` (Claude UUID)

### Bulk Embedding (`services/bulk_embed.py`)

- `embed_all_documents()` — batch-embeds documents into Qdrant (batch size 32, via Ollama)
- `embed_all_messages()` — batch-embeds messages with user_prompt + model_response concatenated
- `embed_all_domains()` — batch-embeds domain descriptions into `janatpmp_documents` collection
- **Checkpointing** — skips already-embedded points via `point_exists()` (resume after restart)
- **Progress logging** — logs every 100 items with count/total and elapsed time
- **Returns** `elapsed_seconds` in result dict for performance tracking

## Phase 6A: Content Ingestion Pipeline (Complete)

### Content Ingestion Module (`services/ingestion/`)

Parsers for importing conversations and documents from multiple external sources.

| Parser | Format | Status |
| ------ | ------ | ------ |
| `google_ai_studio.py` | Google AI Studio `chunkedPrompt` JSON | Tested: 99/104 files, 1,304 turns |
| `quest_parser.py` | Troubadourian quest graph topology JSON | Tested against synthetic data |
| `markdown_ingest.py` | Markdown (.md) and plain text (.txt) files | Tested: title extraction + doc_type classification |
| `dedup.py` | SHA-256 content-hash deduplication | Tested: exact-match detection working |

### Content Corpus (`imports/`)

- `claude/`: 4 Claude exports (244 MB) — handled by `services/claude_import.py`
- `google_ai/` + `other/`: 300 Google AI Studio conversations (100.8 MB)
- `chatgpt/`: 1 ChatGPT export (2.5 MB) — future parser needed (tree structure)
- `markdown/`: 15 markdown files (0.3 MB)
- `text/`: 18 text files (2.5 MB)

See `docs/INVENTORY_CONTENT_CORPUS.md` for full catalog and schema samples.
See `docs/INVENTORY_OLD_PARSERS.md` for old pipeline code analysis.

## Phase R9/R10: ATLAS Model Infrastructure (Offloaded)

**The line:** JANATPMP stores and retrieves. ATLAS remembers.

R9 established the `atlas/` module as the model layer. R10 offloaded all GPU work
from the core container to dedicated sidecars (Ollama for embedding, vLLM for reranking).
Core is now a thin HTTP client layer — no PyTorch, no CUDA, no in-process models.

### ATLAS Module (`atlas/`)

| File | Purpose |
| ---- | ------- |
| `config.py` | Service URLs, model identifiers, vector dimensions, salience/rerank constants |
| `embedding_service.py` | Qwen3-Embedding-4B via Ollama `/v1/embeddings` (OpenAI client) |
| `reranking_service.py` | Qwen3-Reranker-0.6B via vLLM `/v1/score` (httpx client) |
| `memory_service.py` | `write_salience()` — weighted salience write-back to Qdrant payloads |
| `pipeline.py` | `rerank_and_write_salience()` — orchestrator for two-stage search |

### Model Stack

- **Embedder:** Qwen3-Embedding-4B Q4_K_M GGUF via Ollama (2560-dim Matryoshka)
- **Reranker:** Qwen3-Reranker-0.6B FP16 via vLLM (0-1 probability scores)
- **Chat LLM:** Nemotron-3-Nano-30B-A3B IQ4_XS via Ollama
- **Core container:** No GPU, no PyTorch — HTTP clients only (~500 MB image)

### Key Decisions

- **Ollama for embedding:** Qwen3-Embedding-4B runs as an additional model in the existing
  Ollama container. Ollama manages loading/unloading dynamically alongside the chat LLM.
  Accessed via OpenAI-compatible `/v1/embeddings` API using the `openai` Python package.
- **vLLM sidecar for reranking:** Dedicated container running `--task score` mode.
  Lightweight (~1.7 GB VRAM at 5% gpu-memory-utilization). Uses httpx for `/v1/score` calls.
- **Matryoshka truncation:** Client-side `[:EMBEDDING_DIM]` ensures correct 2560-dim output
  even if Ollama ignores the `dimensions` parameter.
- **Asymmetric encoding:** Qwen3-Embedding-4B uses instruction prefix for queries
  (`"Instruct: Given a query, retrieve relevant documents..."`) but plain text for passages.
- **services/embedding.py as thin shim:** Preserves `embed_passages()` / `embed_query()`
  signatures for all downstream consumers. Atlas owns the model; services provides the interface.

### VRAM Budget (RTX 5090, 32GB)

| Component | Estimated VRAM |
| --------- | -------------- |
| Ollama — chat (Nemotron-3-Nano IQ4_XS) | ~18 GB |
| Ollama — embed (Qwen3-Embedding-4B Q4_K_M) | ~2.5 GB |
| vLLM — rerank (Qwen3-Reranker-0.6B FP16) | ~1.7 GB |
| **Total** | **~22.2 GB** |
| **Headroom** | **~9.8 GB** |

All GPU work is offloaded to sidecars. Core container uses zero VRAM.

## Future Architecture (not in scope, for context only)

JANATPMP will eventually become a **Nexus Custom Component** within The Nexus Weaver
architecture. Future integrations include Neo4j (graph database) joining Qdrant (vector search,
now implemented) and SQLite forming a "Triad of Memory" (SQL + Vector + Graph). The CDC outbox
table in the schema provides forward-compatibility for this evolution.
