# CLAUDE.md - Project Guidelines for AI Assistants

## Project Overview

**JANATPMP (Janat Project Management Platform)** is a Gradio-based project management
platform designed for solo architects and engineers working with AI partners. It provides
persistent project state that AI assistants can read and write via MCP (Model Context Protocol).

**Status:** Active development
**Goal:** Strategic command center for consciousness architecture work across multiple domains.

## Tech Stack

- **Python** 3.14+
- **Gradio** 6.6.0 with MCP support (`gradio[mcp]==6.6.0`)
- **SQLite3** for persistence (WAL mode, FTS5 full-text search)
- **Pandas** for data display
- **Qdrant** vector database (semantic search, 2560-dim cosine collections)
- **Neo4j** 2026.01.4 graph database (entity relationships, knowledge graph)
- **Ollama** for chat LLM + embedding (Qwen3-Embedding-4B via `/v1/embeddings`)
- **vLLM** sidecar for cross-encoder reranking (Qwen3-Reranker-0.6B via `/v1/score`)

## Project Structure

```
JANATPMP/
├── app.py                    # Thin orchestrator: init_database(), build_page(), gr.api(), launch
├── janat_theme.py            # Custom Gradio theme (Janat brand colors, fonts, CSS)
├── pages/
│   ├── __init__.py
│   ├── projects.py           # UI layout + event wiring (~1220 lines)
│   └── chat.py               # Sovereign Chat page (R11) — full metrics sidebar
├── tabs/
│   ├── __init__.py
│   ├── tab_database.py       # Admin tab builder: DB lifecycle, ingestion, vector store, logs
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
│   ├── operations.py         # All CRUD + lifecycle functions (28 operations)
│   ├── chat_operations.py    # Conversation + message CRUD (Phase 4B)
│   ├── test_operations.py    # Tests
│   ├── migrations/           # Versioned schema migrations
│   │   ├── 0.3.0_conversations.sql
│   │   ├── 0.4.0_app_logs.sql
│   │   ├── 0.4.1_messages_fts_update.sql
│   │   ├── 0.4.2_domains_table.sql
│   │   ├── 0.5.0_messages_metadata.sql
│   │   ├── 0.6.0_salience_synced.sql
│   │   └── 0.7.0_pipeline_observability.sql
│   ├── janatpmp.db           # SQLite database (runtime, gitignored)
│   ├── backups/              # Timestamped database backups (SQLite + Qdrant + Neo4j)
│   ├── exports/              # Portable project data exports (JSON)
│   └── __init__.py
├── atlas/                    # ATLAS model infrastructure (R9, offloaded R10)
│   ├── __init__.py
│   ├── config.py             # Model names, dimensions, service URLs, Neo4j + salience constants
│   ├── embedding_service.py  # Qwen3-Embedding-4B via Ollama HTTP (OpenAI client)
│   ├── reranking_service.py  # Qwen3-Reranker-0.6B via vLLM HTTP (httpx client)
│   ├── memory_service.py     # Salience write-back to Qdrant payloads
│   ├── usage_signal.py       # Keyword overlap heuristic for usage-based salience (R12)
│   ├── on_write.py           # On-write pipeline: sync embed + fire-and-forget graph edges (R13)
│   └── pipeline.py           # Two-stage search: ANN → rerank → salience
├── graph/                    # Knowledge graph layer — Neo4j (R13)
│   ├── __init__.py
│   ├── schema.py             # Idempotent Neo4j constraints + indexes
│   ├── graph_service.py      # Neo4j CRUD + MCP tools (query, neighbors, stats)
│   └── cdc_consumer.py       # Background CDC poller + backfill_graph MCP tool
├── services/
│   ├── __init__.py
│   ├── log_config.py         # SQLiteLogHandler + setup_logging() + get_logs()
│   ├── chat.py               # Multi-provider chat (Anthropic/Gemini/Ollama) — no tools for in-app Ollama
│   ├── turn_timer.py         # Thread-local TurnTimer context manager (R12)
│   ├── slumber.py            # Background evaluation daemon — Slumber Cycle (R12)
│   ├── claude_import.py      # Claude conversations.json import → triplet messages (directory scanner)
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
├── completed/                # Local-only archive (gitignored) — TODO files, dead prototypes
├── screenshots/              # UI screenshots for reference
├── requirements.txt          # Python dependencies (pinned)
├── pyproject.toml            # Project metadata
├── Dockerfile                # Container image (Python 3.14-slim, no GPU)
├── docker-compose.yml        # Container orchestration (core, ollama, vllm-rerank, qdrant, neo4j)
├── Janat_Brand_Guide.md      # Brand colors, fonts, design system
└── CLAUDE.md                 # This file
```

## Architecture

### Hybrid Multipage Layout (R11)

The app uses a hybrid architecture: monolith at `/` (Projects, Work, Knowledge, Admin)
plus Sovereign Chat at `/chat` via `demo.route()`. The monolith retains dual sidebars:

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

### Four Tabs (current state — Chat tab removed in R11, Sovereign Chat at /chat)

| Tab | Left Sidebar | Center | Status |
|-----|-------------|--------|--------|
| **Projects** | Project cards, filters, + New | Detail editor, List View | ✅ Working |
| **Work** | Task cards, filters, + New Task | Task detail, List View | ✅ Working |
| **Knowledge** | Document cards, filters, + New Doc | Documents (Detail/List), Search, Connections, Conversations | ✅ Working |
| **Admin** | Database Overview (reactive row counts) | Database lifecycle, Content Ingestion, Vector Store, Logs | ✅ Working |

### Contextual Sidebars

The left sidebar uses `@gr.render(inputs=[active_tab, projects_state, tasks_state, ..., admin_refresh])`
to dynamically switch content based on the active tab. The Admin sidebar shows Database
Overview with reactive row counts (auto-refreshes after backup/restore/reset/ingest via
`admin_refresh` state counter). The right sidebar shows Janat quick-chat on all tabs —
a persistent Janus conversation window. Both sidebars use state bridge patterns —
render-created components sync to gr.State via .change listeners for cross-component
data flow.

### Settings & Chat Architecture

**Settings ownership:** All chat and model settings live in **Chat -> Settings tab** (Sovereign
Chat at `/chat`). Admin tab has no settings — it's purely database administration.

**Settings table** (`settings` in SQLite) — key-value store for persistent configuration:
- `chat_provider` — "ollama" (default), "anthropic", or "gemini"
- `chat_model` — Model identifier string (default: "qwen3-vl:8b")
- `chat_api_key` — Base64-encoded API key (obfuscation, NOT encryption)
- `chat_base_url` — Override URL for Ollama
- `ollama_num_ctx` — Context window size (default: 32768 — 32K tokens)
- `ollama_keep_alive` — Model persistence (default: "-1" = permanent)
- `janus_conversation_id` — Persistent Janus conversation hex ID
- `janus_context_messages` — Sliding window size (default: 10 turns)
- `claude_export_json_dir` — Path to Claude export directory (ingestion)
- `rag_score_threshold`, `rag_max_chunks` — RAG retrieval tuning
- `rag_rerank_threshold` — Cross-encoder relevance cutoff (default: 0.3, range 0.0-1.0)
- `rag_synthesizer_provider`, `rag_synthesizer_model` — RAG synthesis backend

**Settings flow:**
- `services/settings.py` provides `get_setting()` / `set_setting()` with auto base64 for secrets
- Chat -> Settings tab controls save on change (no save button needed)
- Chat reads settings from DB on each message — no restart needed
- `init_database()` calls `init_settings()` to seed defaults on first run
- `_STALE_DEFAULTS` in `init_settings()` auto-migrates old defaults on startup

**Dynamic system prompt (no user-editable prompt):**
- `db/operations.py:get_context_snapshot()` builds a summary of active items + pending tasks
- `services/chat.py:_build_system_prompt()` composes: DEFAULT_SYSTEM_PROMPT + tool instructions + live project context
- Fresh context is injected per message. Janus persona emerges from conversation history
  and RAG salience, not from static system prompts.

### Knowledge Tab

The Knowledge tab surfaces documents, search, and entity relationships:

- **Documents** — CRUD for session notes, research, artifacts, conversation imports, code.
  Same sidebar-card + detail pattern as Projects and Work tabs.
- **Search** — Universal FTS5 search across items AND documents simultaneously.
  Uses `search_items()` and `search_documents()` from db/operations.py.
- **Connections** — Relationship viewer. Look up any entity (item/task/document) by ID
  to see incoming and outgoing relationships. Create new connections inline.
- **Conversations** — Browse all conversations from native `conversations` table (platform,
  imported, archived Janus chapters). No external DB — ghost `claude_export.py` system deleted
  in R14. Import buttons are in Admin -> Content Ingestion.
  Uses `get_relationships()` and `create_relationship()` from db/operations.py.

All 6 underlying operations (`create_document`, `get_document`, `list_documents`,
`search_documents`, `create_relationship`, `get_relationships`) were built in Phase 1
and exposed via MCP — Phase 3 only adds the UI layer.

### Data Flow

```
db/operations.py → 28 functions → three surfaces:
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
- `init_settings()` migrates stale defaults (e.g., old model names) on startup — only
  updates values that still match the exact old default, preserving user customizations.

### CDC Outbox Retention

The `cdc_outbox` table captures all database mutations and syncs them to Neo4j via the
CDC consumer daemon thread. `cleanup_cdc_outbox(days=90)` deletes entries where both
`processed_qdrant` and `processed_neo4j` are 1 and older than 90 days.

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
- `messages_metadata` — Cognitive telemetry companion to messages (R12). Per-turn timing
  (total/rag/inference ms), frozen RAG snapshot (hit counts, rerank/salience averages,
  per-hit score objects), keywords, labels, quality_score (0.0-1.0, set by Slumber Cycle).
  FK to messages(id) with CASCADE delete. Unique index on message_id.
- `cdc_outbox` — Change Data Capture for future Qdrant/Neo4j sync. Auto-cleaned on startup (90 days).
- `schema_version` — Migration tracking.

**Migrations** (in `db/migrations/`):

- `0.3.0_conversations.sql` — Conversations + messages tables, FTS, CDC triggers
- `0.4.0_app_logs.sql` — Application logs table with indexes
- `0.4.1_messages_fts_update.sql` — Missing FTS UPDATE trigger on messages
- `0.4.2_domains_table.sql` — Domains as first-class entity, items table CHECK removal, CDC domain support
- `0.5.0_messages_metadata.sql` — Cognitive telemetry table, CDC outbox entity_type addition

**Migration placement gotcha:** New migrations in `init_database()` MUST be placed OUTSIDE
the fresh-DB/existing-DB if/else branch (after both branches complete). Placing inside `else`
means fresh databases never run the migration. The 0.5.0 migration established this pattern.

**CDC outbox entity_type changes:** Adding new entity_types to `cdc_outbox` requires dropping
ALL existing triggers, recreating the table with the updated CHECK constraint, then recreating
ALL triggers. SQLite has no ALTER CHECK — full table recreation is the only path.

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
`feature/phase{version}-{description}` or `feature/r{N}-{description}` — examples:
- `feature/phase4b-chat-experience`
- `feature/phase5-claude-export-ingestion`
- `feature/r12-cognitive-telemetry`

### Starting Work
1. Ensure you're on `main` and it's up to date
2. Create feature branch: `git checkout -b feature/phase{X}-{name}`
3. Do all work on the feature branch

### Completing Work
1. Verify everything runs: `docker compose down && docker compose up -d --build`
2. **Pre-commit hygiene** (MUST happen before the final commit on every sprint):
   - Update `README.md` — tool counts, feature list, project structure, Future section
   - Update `CLAUDE.md` — new architecture, settings, patterns, phase documentation
   - Archive completed TODO files: `mv TODO_RN_*.md imports/markdown/`
3. Commit with descriptive message: `git add -A && git commit -m "Phase {X}: {summary of changes}"`
4. Merge to main: `git checkout main && git merge feature/phase{X}-{name}`
5. Delete feature branch: `git branch -d feature/phase{X}-{name}`

### TODO File Workflow

- TODO files (`TODO*.md`) are **gitignored** — they never enter the public repo
- Create TODO files locally for sprint planning
- On sprint completion, archive to `imports/markdown/` (ingested into platform knowledge)
- Sprint content (goals, decisions, architecture notes) should be captured as JANATPMP
  items/documents so the platform itself is the source of truth

### Commit Message Format
`Phase {version}: {one-line summary}` — examples:
- `Phase 4B: Chat experience redesign — triplet message schema, conversation persistence, AI Studio layout`
- `Phase 3: Knowledge tab — documents UI, universal search, connections viewer`

For smaller fixes within a phase: `Phase {version}: Fix {description}`

### Rules
- Never commit directly to `main` — always use a feature branch
- One phase = one branch = one merge
- If a phase has sub-phases (4A, 4B), each gets its own branch
- TODO files are local-only planning artifacts — never committed to the repo

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
  `janatpmp-vllm-rerank` (reranker), `janatpmp-qdrant` (vector DB), `janatpmp-neo4j` (graph DB)
  - Core has NO GPU — all model inference offloaded to Ollama and vLLM sidecars
- **Qdrant:** `janatpmp-qdrant` container on ports 6343:6333/6344:6334
  - Internal URL: `http://janatpmp-qdrant:6333` (Docker DNS)
  - External URL: `http://localhost:6343` (host access, dashboard at `/dashboard`)
  - Volume: `janatpmp_qdrant_data` (external)
  - Collections: `janatpmp_documents` (2560-dim), `janatpmp_messages` (2560-dim)
  - Auto-recreates collections on dimension mismatch at startup
- **Neo4j:** `janatpmp-neo4j` container on ports 7474 (browser) / 7687 (Bolt)
  - Internal URL: `bolt://janatpmp-neo4j:7687` (Docker DNS)
  - External URL: `http://localhost:7474` (Neo4j Browser)
  - Volume: `neo4j_data` (local)
  - Auth: `neo4j/janatpmp_graph`
  - Node labels: Item, Task, Document, Conversation, Message, Domain, MessageMetadata
  - Edge types: IN_DOMAIN, TARGETS_ITEM, BELONGS_TO, FOLLOWS, DESCRIBES, INFORMED_BY, SIMILAR_TO
- **Ollama:** `janatpmp-ollama` container on port 11435, shares `ollama_data` external volume
  - Internal URL: `http://ollama:11434/v1` (Docker DNS)
  - External URL: `http://localhost:11435` (host access for testing)
  - GPU passthrough via NVIDIA Container Toolkit (~85% VRAM)
  - `OLLAMA_KEEP_ALIVE=-1` keeps models loaded permanently (no unload timeout)
  - Chat model: qwen3-vl:8b (default, Janus), nemotron-3-nano:latest Q4_K_M also available
  - Embedding model: Qwen3-Embedding-4B Q4_K_M GGUF (~2.5 GB) — used via `/v1/embeddings`
  - RAG synthesizer: qwen3:1.7b — lightweight model for knowledge synthesis
  - Ollama model list is fetched dynamically via `/api/tags` — no hardcoded model names
- **vLLM Reranker:** `janatpmp-vllm-rerank` container on port 8002
  - Internal URL: `http://janatpmp-vllm-rerank:8000` (Docker DNS)
  - External URL: `http://localhost:8002` (host access for testing)
  - Runs Qwen3-Reranker-0.6B FP16 (~1.7 GB) with `--runner pooling --convert classify`
  - GPU passthrough via NVIDIA Container Toolkit (~10% VRAM)
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

57 functions are exposed via `gr.api()` as MCP tools: 28 from `db/operations.py`
(including domain CRUD + export/import), 13 from `db/chat_operations.py` (including Janus
lifecycle), 8 vector/embedding operations from `services/`, 2 import pipelines, 2 ingestion
orchestrators, and 4 graph operations from `graph/`. All MUST have Google-style docstrings
with Args/Returns for MCP tool generation.

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

Any conversation, regardless of source, can be browsed in Knowledge tab Conversations.
Claude Export ingestion creates conversations + messages records via
`services/claude_import.py` (native pipeline, integrated with triple-write).

### Chat Flow (Janus Continuous Chat — R14)

1. User types message, presses Enter
2. If no active conversation, `get_or_create_janus_conversation()` provides one
3. Apply sliding window: `_windowed_api_history(history, window)` sends last N turns to LLM
4. Call `chat()` with per-session override params (provider, model, temperature, top_p, max_tokens)
5. Reconstruct full history: `new_messages = result["history"][len(api_window):]` then append
6. Parse reasoning via `parse_reasoning()`, split display vs API history
7. Store triplet via `add_message()` + metadata + live memory (triple-write)

### "Archive Chapter" Semantics

Not "New Chat" — "Archive Chapter" marks the current Janus conversation as
`is_active=0`, renames to "Janus — Chapter N", creates a fresh Janus conversation.
Archived chapters appear in Knowledge tab Conversations. Archiving is rare and intentional.

### Database Operations (db/chat_operations.py)

- `create_conversation()`, `get_conversation()`, `list_conversations()`, `update_conversation()`, `delete_conversation()`, `search_conversations()` (FTS)
- `add_message()`, `get_messages()`, `get_next_sequence()`
- `get_or_create_janus_conversation()` — reads/creates the persistent Janus conversation, stores ID in settings
- `archive_janus_conversation(conv_id)` — archives current Janus as "Janus — Chapter N", creates fresh one
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

- `import_conversations_directory(directory)` — scans for `conversations*.json` files and imports all
- `import_conversations_json(file_path)` — imports a single conversations.json file
- Each conversation becomes a `conversations` record with `source='claude_export'`
- Each message pair becomes a `messages` record with user_prompt + model_response
- Deduplicates by `conversation_uri` (Claude UUID)

### Bulk Embedding (`services/bulk_embed.py`)

- `embed_all_documents()` — batch-embeds documents into Qdrant (batch size 32, via Ollama)
- `embed_all_messages()` — batch-embeds messages with user_prompt + model_response concatenated
- `embed_all_domains()` — batch-embeds domain descriptions into `janatpmp_documents` collection
- `embed_all_items()` — batch-embeds items (projects, features, etc.) into `janatpmp_documents`
- `embed_all_tasks()` — batch-embeds tasks into `janatpmp_documents` collection
- Items and tasks use `entity_type` payload field to distinguish from documents/domains
- **Checkpointing** — skips already-embedded points via `point_exists()` (resume after restart)
- **Progress logging** — logs every 100 items with count/total and elapsed time
- **Returns** `elapsed_seconds` in result dict for performance tracking

## Phase 6A: Content Ingestion Pipeline (Complete)

### Content Ingestion Module (`services/ingestion/`)

Parsers for importing conversations and documents from multiple external sources.

| Parser | Format | Status |
| ------ | ------ | ------ |
| `google_ai_studio.py` | Google AI Studio `chunkedPrompt` JSON | Tested: 99/104 files, 1,304 turns |
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

- **Chat LLM:** qwen3-vl:8b via Ollama (default, "Janus"). nemotron-3-nano:latest also available.
- **Embedder:** Qwen3-Embedding-4B Q4_K_M GGUF via Ollama (2560-dim Matryoshka)
- **Reranker:** Qwen3-Reranker-0.6B FP16 via vLLM (0-1 probability scores)
- **RAG Synthesizer:** qwen3:1.7b via Ollama (lightweight knowledge compression)
- **Core container:** No GPU, no PyTorch — HTTP clients only (~500 MB image)

### Key Decisions

- **Ollama for embedding:** Qwen3-Embedding-4B runs as an additional model in the existing
  Ollama container. Ollama manages loading/unloading dynamically alongside the chat LLM.
  Accessed via OpenAI-compatible `/v1/embeddings` API using the `openai` Python package.
- **vLLM sidecar for reranking:** Dedicated container running `--runner pooling --convert classify`
  with `--hf-overrides` for Qwen3ForSequenceClassification architecture.
  Lightweight (~1.7 GB VRAM at 10% gpu-memory-utilization). Uses httpx for `/v1/score` calls.
- **Matryoshka truncation:** Client-side `[:EMBEDDING_DIM]` ensures correct 2560-dim output
  even if Ollama ignores the `dimensions` parameter.
- **Asymmetric encoding:** Qwen3-Embedding-4B uses instruction prefix for queries
  (`"Instruct: Given a query, retrieve relevant documents..."`) but plain text for passages.
- **services/embedding.py as thin shim:** Preserves `embed_passages()` / `embed_query()`
  signatures for all downstream consumers. Atlas owns the model; services provides the interface.

### VRAM Budget (RTX 5090, 32GB)

| Component | Estimated VRAM |
| --------- | -------------- |
| Ollama — chat (qwen3-vl:8b) | ~6 GB |
| Ollama — embed (Qwen3-Embedding-4B Q4_K_M) | ~2.5 GB |
| Ollama — synthesizer (qwen3:1.7b) | ~1.5 GB |
| vLLM — rerank (Qwen3-Reranker-0.6B FP16) | ~1.7 GB |
| **Total** | **~11.7 GB** |
| **Headroom** | **~20.3 GB** |

All GPU work is offloaded to sidecars. Core container uses zero VRAM.

## Phase R12: Cognitive Telemetry

Not standard O11y — a recording layer for self-observing memory and reasoning.

### Recording Layer

- `messages_metadata` table — per-turn timing, frozen RAG snapshots, keywords, quality scores
- `services/turn_timer.py` — `TurnTimer` context manager with named spans (`rag`, `inference`)
- Wired into `chat()` pipeline: RAG and inference calls wrapped in timer spans
- `add_message_metadata()` / `get_message_metadata()` exposed as MCP tools

### Reasoning Token Decomposition

Ollama lumps `<think>` block tokens into `completion_tokens` without separating them.
Anthropic standard API also lacks a dedicated reasoning token field. Pattern:
proportionally split `completion_tokens` by reasoning vs response text length (same model =
same tokenizer = consistent chars-per-token ratio). Fallback: ~4 chars/token estimate.

### Usage Signal (Salience Layer 2)

- `atlas/usage_signal.py` — keyword overlap heuristic estimates which RAG hits the model used
- `atlas/memory_service.py:write_usage_salience()` — boosts salience for used chunks (>0.3),
  decays for retrieved-but-ignored chunks (<0.1)
- Runs inline after each turn. Graceful degradation if Qdrant down.
- Config: `SALIENCE_USAGE_RATE=0.03`, `SALIENCE_DECAY_RATE=0.01` in `atlas/config.py`

### Slumber Cycle (4 Sub-cycles)

- `services/slumber.py` — daemon thread activates after idle threshold (default 5 min)
- `touch_activity()` called in all chat handlers to reset idle timer
- Settings: `slumber_idle_threshold`, `slumber_batch_size`, `slumber_evaluator`, `slumber_prune_age_days`
- Started at app boot in `app.py` via `start_slumber()`
- Four sub-cycles run in sequence during each idle period:

| Sub-cycle | Function | Purpose |
|-----------|----------|---------|
| Evaluate | `_evaluate_batch()` | Score unscored messages via heuristic, extract TF keywords |
| Propagate | `_propagate_batch()` | Bridge `quality_score` → Qdrant `salience` (decay garbage, boost quality) |
| Relate | `_relate_batch()` | Create SIMILAR_TO edges in Neo4j via cross-conversation keyword overlap |
| Prune | `_prune_batch()` | Remove dead-weight vectors from Qdrant (quality < 0.1, salience < 0.1, never retrieved, older than N days) |

Propagate mapping: quality < 0.15 → ×0.3 hard decay; 0.15-0.4 → ×0.7 soft decay;
0.4-0.7 → neutral; > 0.7 → +0.1 boost. Prune never deletes from SQLite — only Qdrant vectors.

## Phase R13: Live Memory — Triple-Write Pipeline + Temporal Graph

**The Triad of Memory is operational.** Every new message fans out to three stores:
SQLite (source of truth), Qdrant (semantic retrieval), Neo4j (graph navigation).

### Triple-Write Pipeline (`atlas/on_write.py`)

Called after every `add_message()` across all three chat surfaces (Sovereign Chat,
monolith Chat tab, sidebar quick-chat):

1. **Embed (synchronous, ~100-300ms):** Combines user prompt + model response, embeds via
   Ollama, upserts to Qdrant with temporal payload (conversation_id, conv_title, sequence,
   created_at, provider, model, salience=0.5). Ensures immediate retrievability next turn.
2. **Relate (fire-and-forget):** Creates INFORMED_BY edges in Neo4j linking the message to
   its RAG sources. Only INFORMED_BY — structural edges (BELONGS_TO, FOLLOWS) handled by CDC.

### Knowledge Graph (`graph/`)

- **Neo4j 2026.01.4** with 7 uniqueness constraints and 3 range indexes
- **CDC consumer** daemon polls `cdc_outbox WHERE processed_neo4j = 0`, syncs all 8 entity
  types (item, task, document, conversation, message, domain, message_metadata, relationship)
- **4 MCP tools:** `graph_query` (read-only Cypher), `graph_neighbors`, `graph_stats`, `backfill_graph`
- Config in `atlas/config.py`: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, CDC_POLL_INTERVAL, CDC_BATCH_SIZE
- **Edge separation:** CDC consumer creates structural edges (BELONGS_TO, FOLLOWS, IN_DOMAIN,
  TARGETS_ITEM, DESCRIBES). on_write creates INFORMED_BY edges (requires rag_hits).
  Slumber Relate creates SIMILAR_TO edges (keyword overlap).

### RAG Provenance

`_build_rag_context()` enriches `used_scores` with `source_conversation_id`,
`source_conversation_title`, and `created_at` from Qdrant payloads. The Sovereign Chat
left sidebar displays "RAG Provenance" — each hit shows its source conversation title,
date, and relevance scores.

### Portable Project Export/Import (`db/operations.py`)

- `export_platform_data()` — exports domains, items, tasks, relationships to versioned JSON
  in `db/exports/`. Schema version `0.6.0`. Virtual columns excluded for portability.
- `import_platform_data(path)` — imports from export JSON. Topologically sorts items by
  `parent_id` for referential integrity. Uses `INSERT OR IGNORE` for re-imports.
- Designed for surviving platform resets: export → reset → import → re-embed → verify.

### Unified Backup/Restore (`db/operations.py`)

- `backup_database()` — creates timestamped directory in `db/backups/` containing SQLite
  copy, Qdrant collection snapshots, and Neo4j graph export. All stores in one archive.
- `restore_database(backup_name)` — restores SQLite, recreates Qdrant collections from
  snapshots, and re-imports Neo4j graph. Full Triad restoration.
- `reset_database()` — wipes all three stores (SQLite, Qdrant, Neo4j). Auto-creates
  backup first. Re-run ingestion + embedding after reset.

## Phase R14: Janus Continuous Chat + Settings Consolidation

### Janus Continuous Chat

One persistent conversation from platform birth — no "New Chat" semantics. Both Sovereign
Chat (`/chat`) and sidebar quick-chat share the same Janus conversation for maximum context
continuity. Key components:

- `get_or_create_janus_conversation()` — reads `janus_conversation_id` from settings, creates
  if missing, validates existence. Called at app startup and as fallback in all chat handlers.
- `archive_janus_conversation(conv_id)` — chapter break: old becomes "Janus — Chapter N"
  (`is_active=0`), fresh Janus created. Rare and intentional.
- **Sliding window:** `_windowed_api_history(history, window)` sends last N turns to LLM
  (default 50). Full history displayed in UI for scroll-back. Window configurable via
  Chat right sidebar "Context Window" control.
- **History reconstruction:** After windowed chat call, extract new messages from result
  and append to full history: `new_messages = result["history"][len(api_window):]`.
- **Dual history pattern:** `display_history` has `<details>` reasoning accordions,
  `api_history` has clean responses only (prevents model from mimicking HTML formatting).

### Import Consolidation

Ghost system `services/claude_export.py` (separate external SQLite DB) deleted. All
conversation browsing reads from native `conversations` table. Import buttons are in
Admin -> Content Ingestion only. Knowledge tab Conversations is browse-only.

### Settings Consolidation

**Chat -> Settings tab** is the single source for all model and RAG configuration:
Platform Defaults (provider, model, temperature, top_p, max_tokens), RAG Configuration,
RAG Synthesizer, Credentials (API key, base URL), Ollama (num_ctx, keep_alive).

**Admin tab** is purely database administration: Database lifecycle (backup/restore/reset/export),
Content Ingestion, Vector Store (embedding), Application Logs. Left sidebar shows Database
Overview with reactive row counts.

### Janus Persona

R15 introduced explicit Janus identity via `DEFAULT_SYSTEM_PROMPT_TEMPLATE` ("You are Janus,
an AI collaborator...") with dynamic domain injection from the `domains` table. The template
uses `{domains}` placeholder filled at prompt build time by `_build_system_prompt()`.
Full Modelfile-driven dynamic persona (per-turn synthesizer prompts) is future work.

## Phase R15: Fix the Foundation — Chat Pipeline, RAG Quality, Ingestion

R15 stabilizes the broken foundation before building intelligence layers.

### No Tools for In-App Chat

The in-app Ollama chat model (Janus) no longer receives tool definitions. Qwen3-VL:8b
was outputting tool call JSON inside `<think>` blocks when both `tools` and `think=True`
were sent simultaneously. The fix: remove tools entirely from `_chat_ollama()`.

- **RAG provides retrieved knowledge**, `get_context_snapshot()` provides live project state
- Tools are for **MCP clients** (Claude Desktop, etc.) via `gr.api()` in `app.py`
- Saves ~3,500 tokens of context window per turn
- System prompt explicitly tells model "You have NO tools" to prevent hallucinated calls
- Anthropic/Gemini providers keep their tool support for MCP compatibility

### Pipeline Observability (Migration 0.7.0)

Per-turn pipeline metadata stored in `messages_metadata`:

- `system_prompt_length` — composed system prompt size (chars)
- `rag_context_text` — raw RAG context injected into prompt
- `rag_synthesized` — whether RAG synthesis was applied (0/1)

Surfaced in Sovereign Chat left sidebar "Pipeline" section.

### RAG Quality Tuning

- **Configurable rerank threshold** — `rag_rerank_threshold` setting (0.0-1.0, default 0.3)
  replaces hardcoded cutoff. Surfaced as slider in Chat Settings right sidebar.
- **Consistent bulk embed payloads** — `embed_all_messages()` now includes `created_at`,
  `provider`, `model`, `salience`, `entity_type` to match `atlas/on_write.py`.

### Ingestion Hardening

- **Content-hash dedup** — `compute_conversation_hash()` and `compute_content_hash()` from
  `services/ingestion/dedup.py` wired as secondary dedup after title-based checks in
  Google AI and markdown orchestrators.
- **Auto-embed after ingestion** — all three pipelines (Google AI, markdown, Claude import)
  auto-trigger `embed_all_messages()` or `embed_all_documents()` after successful import.
  Checkpoint-based resume ensures only new records are embedded.
- **Batch point_exists** — `existing_point_ids()` in `services/vector_store.py` replaces
  per-record `point_exists()` calls with a single batch retrieve per batch of 32.

## Future Architecture (not in scope, for context only)

JANATPMP will eventually become a **Nexus Custom Component** within The Nexus Weaver
architecture. The **Triad of Memory** (SQLite + Qdrant + Neo4j) is now operational — the
triple-write pipeline keeps all three stores in sync. **Janus continuous chat** is live
(R14) — one persistent conversation stream with sliding window context. Future work:

- **System prompt audit trail** — R15 stores system prompt length + RAG context per-turn;
  future: full prompt text storage, "Prompt Inspector" panel, Slumber Cycle consolidation
- **Ollama Modelfiles pipeline** — janat-synthesizer, janat-scorer, janat-consolidator,
  janat-classifier sharing Qwen3:1.7B base weights. Janus (8B) receives dynamic system
  prompts from the synthesizer each turn.
- **Advanced graph traversal** — multi-hop reasoning across INFORMED_BY and SIMILAR_TO edges
- **Temporal decay curves** — time-weighted salience that naturally deprioritizes stale knowledge
