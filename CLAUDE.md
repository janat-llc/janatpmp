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
- **Qdrant** vector database (semantic search, 1024-dim cosine collections)
- **Neo4j** 2026.01.4 graph database (entity relationships, knowledge graph)
- **Ollama** for chat LLM + embedding (qwen3:32b chat, qwen3-embedding:0.6b via `/v1/embeddings`)

## Project Structure

```
JANATPMP/
├── app.py                    # Thin launcher: startup calls, gr.Blocks, banner, demo.launch()
├── mcp_registry.py           # MCP Tool Registry — all 72 gr.api() function imports + ALL_MCP_TOOLS list
├── janat_theme.py            # Custom Gradio theme (Janat brand colors, fonts, CSS)
├── pages/
│   ├── __init__.py
│   ├── projects.py           # Projects + Work page — sidebar-first layout (~350 lines)
│   ├── knowledge.py          # Knowledge page — Memory, Connections, Pipeline, Synthesis (~620 lines)
│   ├── admin.py              # Admin page — Settings, Persona, Operations (~470 lines)
│   └── chat.py               # Sovereign Chat page (R11) — full metrics sidebar
├── tabs/
│   ├── __init__.py
│   ├── tab_chat.py           # Chat handler: _handle_chat() for sidebar quick-chat
│   └── tab_knowledge.py      # Knowledge page handlers (search, connections, conversation loading)
├── shared/
│   ├── __init__.py
│   ├── chat_sidebar.py        # Reusable Janus quick-chat right sidebar (R18)
│   ├── constants.py           # All enum lists, magic numbers, default values
│   ├── formatting.py          # fmt_enum(), entity_list_to_df() display helpers
│   └── data_helpers.py        # Data-loading helpers (_load_projects, _all_items_df, etc.)
├── db/
│   ├── schema.sql            # Database schema DDL (NO seed data)
│   ├── seed_data.sql         # Optional seed data (separate from schema)
│   ├── operations.py         # All CRUD + lifecycle functions (28 operations)
│   ├── chat_operations.py    # Conversation + message CRUD (Phase 4B)
│   ├── chunk_operations.py   # Chunk CRUD, stats, FTS search (R16)
│   ├── file_registry_ops.py  # File registry MCP tools (R17)
│   ├── test_operations.py    # Tests
│   ├── migrations/           # Versioned schema migrations
│   │   ├── 0.3.0_conversations.sql
│   │   ├── 0.4.0_app_logs.sql
│   │   ├── 0.4.1_messages_fts_update.sql
│   │   ├── 0.4.2_domains_table.sql
│   │   ├── 0.5.0_messages_metadata.sql
│   │   ├── 0.6.0_salience_synced.sql
│   │   ├── 0.7.0_pipeline_observability.sql
│   │   ├── 0.8.0_chunks.sql
│   │   └── 0.9.0_file_registry.sql
│   ├── janatpmp.db           # SQLite database (runtime, gitignored)
│   ├── backups/              # Timestamped database backups (SQLite + Qdrant + Neo4j)
│   ├── exports/              # Portable project data exports (JSON)
│   └── __init__.py
├── atlas/                    # ATLAS model infrastructure (R9, offloaded R10)
│   ├── __init__.py
│   ├── config.py             # Model names, dimensions, service URLs, Neo4j + salience constants
│   ├── chunking.py           # Paragraph-aware text splitter for messages + documents (R16)
│   ├── embedding_service.py  # Qwen3-Embedding-0.6B via Ollama HTTP (OpenAI client)
│   ├── reranking_service.py  # DECOMMISSIONED — vLLM reranker removed, rerank defaults to False
│   ├── memory_service.py     # Salience write-back to Qdrant payloads
│   ├── usage_signal.py       # Keyword overlap heuristic for usage-based salience (R12)
│   ├── on_write.py           # On-write: chunk + embed + fire-and-forget graph edges (R13/R16)
│   ├── pipeline.py           # Search pipeline: ANN → salience (rerank decommissioned)
│   └── temporal.py           # Temporal Affinity Engine — time/location context (R17)
├── graph/                    # Knowledge graph layer — Neo4j (R13)
│   ├── __init__.py
│   ├── schema.py             # Idempotent Neo4j constraints + indexes
│   ├── graph_service.py      # Neo4j CRUD + MCP tools (query, neighbors, stats)
│   ├── cdc_consumer.py       # Background CDC poller + backfill_graph MCP tool
│   └── semantic_edges.py     # Conversation SIMILAR_TO edge generation (R20)
├── services/
│   ├── __init__.py
│   ├── log_config.py         # SQLiteLogHandler + setup_logging() + get_logs()
│   ├── chat.py               # Multi-provider chat (Anthropic/Gemini/Ollama) — no tools for in-app Ollama
│   ├── prompt_composer.py    # 7-layer Janus identity system prompt (R19)
│   ├── turn_timer.py         # Thread-local TurnTimer context manager (R12)
│   ├── slumber.py            # Background evaluation daemon — Slumber Cycle (R12)
│   ├── claude_import.py      # Claude conversations.json import → triplet messages (directory scanner)
│   ├── embedding.py          # Thin shim → atlas.embedding_service
│   ├── vector_store.py       # Qdrant vector DB + two-stage search pipeline
│   ├── bulk_embed.py         # Batch embed via Ollama with progress & checkpointing
│   ├── settings.py           # Settings registry with validation and categories
│   ├── auto_ingest.py        # Startup + Slumber auto-ingestion scanner (R17)
│   ├── startup.py            # Platform init: initialize_core(), initialize_services(), background auto-ingest
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
├── docker-compose.yml        # Container orchestration (core, ollama, qdrant, neo4j)
├── Janat_Brand_Guide.md      # Brand colors, fonts, design system
└── CLAUDE.md                 # This file
```

## Architecture

### Sovereign Multipage Layout (R18)

The app uses sovereign pages connected by `demo.route()`. One process, one port, one MCP
surface. Each page has purpose-built sidebars. Navbar provides client-side navigation.

```
app.py — orchestrator (one process, one port)
├── / (Projects)        → pages/projects.py  [Projects + Work tabs]
├── /knowledge          → pages/knowledge.py [Memory, Connections, Pipeline, Synthesis]
├── /admin              → pages/admin.py     [Settings, Persona, Operations]
└── /chat               → pages/chat.py      [Sovereign Chat — full metrics sidebar]
```

Navbar: **Projects** (home) · **Knowledge** · **Admin** · **Chat**

**Core Design Principle: Sidebar-First Layout.** Every page uses the three-panel pattern:
- **Left sidebar:** Context, navigation, filtering. "Where am I, what am I looking at?"
- **Center:** The content itself. Detail views, editors, controls.
- **Right sidebar:** Janus quick-chat. Continuous across all pages via `shared/chat_sidebar.py`.

Tabs represent **modes of thinking**, not data types. If two data types share the same
browsing pattern, they belong in one tab with the left sidebar providing the selection.

**Implementation in code:**

```python
# app.py — thin orchestrator
with gr.Blocks(title="JANATPMP") as demo:
    gr.Navbar(main_page_name="Projects")
    build_page()                          # Projects + Work
    for tool_fn in ALL_MCP_TOOLS:
        gr.api(tool_fn)                   # 72 MCP tools (registered on main Blocks only)

with demo.route("Knowledge", "/knowledge"):
    gr.Navbar(main_page_name="Projects")
    knowledge_page.build_knowledge_page()

with demo.route("Admin", "/admin"):
    gr.Navbar(main_page_name="Projects")
    admin_page.build_admin_page()

with demo.route("Chat", "/chat"):
    gr.Navbar(main_page_name="Projects")
    chat_page.build_chat_page()
```

```python
# shared/chat_sidebar.py — reusable right sidebar
def build_chat_sidebar():
    """Build right sidebar with Janus quick-chat. Call BEFORE center content.
    Returns (chatbot, chat_input, chat_history, sidebar_conv_id)."""

def wire_chat_sidebar(chat_input, chatbot, chat_history, sidebar_conv_id):
    """Wire chat sidebar submit event. Call AFTER all center content."""
```

**Use `gr.Sidebar` for both side panels — NOT `gr.Column` in a `gr.Row`.**
Sidebar is collapsible, mobile-friendly, and purpose-built for this layout.
The center content is just the main Blocks body (no Row/Column wrapper needed).

### Sovereign Pages (R18)

| Page | Route | Tabs | Left Sidebar |
|------|-------|------|-------------|
| **Projects** | `/` | Projects, Work | Project/task cards, filters, + New |
| **Knowledge** | `/knowledge` | Memory, Connections, Pipeline, Synthesis | Type filter, search, pipeline health |
| **Admin** | `/admin` | Settings, Persona, Operations | Category buttons, identity card, platform health |
| **Chat** | `/chat` | Metrics, Settings, Conversations | RAG provenance, pipeline stats, conversation list |

Knowledge page unifies conversations + documents into a single **Memory** tab with type
filter. **Pipeline** tab consolidates ingestion, embedding, chunking, and graph controls.
Admin page has a **Persona** tab for user identity settings (`user_name`, `user_bio`,
`user_preferences` in `services/settings.py` category "persona").

### Contextual Sidebars

Each page has its own `@gr.render()` left sidebar that switches content based on the
active tab within that page. The right sidebar shows Janat quick-chat on all pages —
built once via `shared/chat_sidebar.py` and wired per-page.

### Settings & Chat Architecture

**Settings ownership:** Chat and model settings live in **Chat -> Settings tab** (Sovereign
Chat at `/chat`). Platform settings (all categories) are editable via **Admin -> Settings tab**.
Persona settings (`user_name`, `user_bio`, `user_preferences`) are in **Admin -> Persona tab**.

**Settings table** (`settings` in SQLite) — key-value store for persistent configuration:
- `chat_provider` — "ollama" (default), "anthropic", or "gemini"
- `chat_model` — Model identifier string (default: "qwen3:32b")
- `chat_api_key` — Base64-encoded API key (obfuscation, NOT encryption)
- `chat_base_url` — Override URL for Ollama
- `ollama_num_ctx` — Context window size (default: 32768 — 32K tokens)
- `ollama_keep_alive` — Model persistence (default: "-1" = permanent)
- `janus_conversation_id` — Persistent Janus conversation hex ID
- `janus_context_messages` — Sliding window size (default: 10 turns)
- `claude_export_json_dir` — Path to Claude export directory (ingestion)
- `rag_score_threshold`, `rag_max_chunks` — RAG retrieval tuning
- `rag_rerank_threshold` — Cross-encoder relevance cutoff (default: 0.3, range 0.0-1.0)
- `rag_max_chunks_per_message` — Diversity cap: max chunks from one parent message (default: 3, 0 = no limit)
- `rag_synthesizer_provider`, `rag_synthesizer_model` — RAG synthesis backend
- `chunk_max_chars` — Target chunk size (default: 2500)
- `chunk_min_chars` — Minimum chunk size (default: 200)
- `chunk_overlap_chars` — Overlap between consecutive chunks (default: 200)
- `chunk_threshold` — Messages shorter than this stay as single vector (default: 3000)
- `location_lat`, `location_lon` — Geographic coordinates for temporal engine (default: Fargo, ND)
- `location_name` — Full address for temporal grounding display
- `location_tz` — IANA timezone (default: America/Chicago)
- `user_name` — User display name (default: "Mat", category: persona)
- `user_bio` — User biography/context (default: "", category: persona)
- `user_preferences` — Interaction style preferences (default: "", category: persona)

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

### Knowledge Page (`pages/knowledge.py`)

Sovereign Knowledge page with 4 tabs:

- **Memory** — Unified conversation + document browser. Left sidebar has type filter
  (All/Conversations/Documents), search textbox, and scrollable result list. Center shows
  conversation viewer (`gr.Chatbot`) or document detail depending on selection. Includes
  "+ New Document" accordion.
- **Connections** — Entity relationship viewer. Left sidebar has entity type picker and
  search. Center shows relationship table with "+ Add Connection" accordion.
- **Pipeline** — Content ingestion, embedding, chunking, and graph controls. Left sidebar
  shows pipeline health stats. Center has accordions for ingestion, embedding, and graph.
- **Synthesis** — Placeholder for R19 (Memory node review, evidence chains).

### Data Flow

```
db/operations.py → 28 functions → three surfaces:
    1. UI: imported by pages/*.py, called in event listeners
    2. API: exposed via gr.api() in app.py (main Blocks only)
    3. MCP: auto-generated from gr.api() + docstrings
```

**Key principles:**

- One set of functions in `db/operations.py` serves UI, API, and MCP
- NO `demo.load()` — data is computed at build time and passed via `value=`
- `gr.api()` exposes db functions as MCP tools (registered on main Blocks, accessible from all routes)
- Each page has its own `build_*_page()` entry point

### Startup Sequence (`services/startup.py`)

Platform initialization is extracted into three functions called from `app.py`:

1. **`initialize_core()`** — DB, settings, cleanup, Janus conversation. BLOCKING, fast (<1s).
2. **`initialize_services()`** — Qdrant, Slumber daemon, Neo4j. Each isolated in try/except.
3. **`start_auto_ingest()`** — Launches `scan_and_ingest()` in a background daemon thread.
   Non-blocking: the webserver starts immediately while ingestion runs behind the scenes.

A branded startup banner ("JANUS is getting ready for work...") appears in the UI and
auto-dismisses via `gr.Timer` polling `is_auto_ingest_complete()` every 2 seconds.

### MCP Tool Registry (`mcp_registry.py`)

All 72 MCP tool functions are imported and collected in `ALL_MCP_TOOLS` list, grouped by
page ownership (Projects, Knowledge, Admin, cross-cutting). `app.py` loops over this list:
`for tool_fn in ALL_MCP_TOOLS: gr.api(tool_fn)`. Registered on the main Blocks only —
accessible from all routes. Keeps `app.py` thin (~100 lines).

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

- **Categories:** `chat`, `ollama`, `export`, `ingestion`, `rag`, `system`, `persona`
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
- `chunks` — Unified chunk records for messages and documents (R16). Each row stores
  entity_type ('message'/'document'), entity_id (FK to parent), chunk_index, chunk_text,
  char_start/char_end offsets, position ('only'/'first'/'middle'/'last'), point_id (Qdrant),
  embedded_at timestamp. FTS5 via `chunks_fts` with INSERT/UPDATE/DELETE sync triggers.
  CDC trigger syncs Chunk nodes to Neo4j. UNIQUE(entity_type, entity_id, chunk_index).
- `file_registry` — Tracks ingested files by path + SHA-256 content hash (R17). Operational
  metadata — no CDC participation. Columns: file_path (UNIQUE), filename, content_hash,
  file_size, ingestion_type ('claude'/'google_ai'/'markdown'), entity_type, entity_count,
  status ('ingested'/'failed'/'skipped'), error_message, ingested_at. Used by auto-ingestion
  scanner to skip already-processed files and detect content changes.
- `cdc_outbox` — Change Data Capture for future Qdrant/Neo4j sync. Auto-cleaned on startup (90 days).
- `schema_version` — Migration tracking.

**Migrations** (in `db/migrations/`):

- `0.3.0_conversations.sql` — Conversations + messages tables, FTS, CDC triggers
- `0.4.0_app_logs.sql` — Application logs table with indexes
- `0.4.1_messages_fts_update.sql` — Missing FTS UPDATE trigger on messages
- `0.4.2_domains_table.sql` — Domains as first-class entity, items table CHECK removal, CDC domain support
- `0.5.0_messages_metadata.sql` — Cognitive telemetry table, CDC outbox entity_type addition
- `0.6.0_salience_synced.sql` — Salience sync tracking
- `0.7.0_pipeline_observability.sql` — Per-turn pipeline metadata in messages_metadata
- `0.8.0_chunks.sql` — Unified chunks table, FTS5, CDC triggers (drops+recreates all triggers for CHECK constraint expansion)
- `0.9.0_file_registry.sql` — File registry for auto-ingestion tracking (R17, no CDC — operational metadata)

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
  `janatpmp-qdrant` (vector DB), `janatpmp-neo4j` (graph DB) — 4 containers total
  - Core has NO GPU — all model inference offloaded to Ollama sidecar
- **Qdrant:** `janatpmp-qdrant` container on ports 6343:6333/6344:6334
  - Internal URL: `http://janatpmp-qdrant:6333` (Docker DNS)
  - External URL: `http://localhost:6343` (host access, dashboard at `/dashboard`)
  - Volume: `janatpmp_qdrant_data` (external)
  - Collections: `janatpmp_documents` (1024-dim), `janatpmp_messages` (1024-dim)
  - Auto-recreates collections on dimension mismatch at startup
- **Neo4j:** `janatpmp-neo4j` container on ports 7474 (browser) / 7687 (Bolt)
  - Internal URL: `bolt://janatpmp-neo4j:7687` (Docker DNS)
  - External URL: `http://localhost:7474` (Neo4j Browser)
  - Volume: `neo4j_data` (local)
  - Auth: `neo4j/janatpmp_graph`
  - Node labels: Item, Task, Document, Conversation, Message, Domain, MessageMetadata, Chunk, Person, Identity
  - Edge types: IN_DOMAIN, TARGETS_ITEM, BELONGS_TO, FOLLOWS, DESCRIBES, INFORMED_BY, SIMILAR_TO, PART_OF, BECAME, INHERITS_MEMORY_OF, PARTICIPATED_IN, SPOKE
- **Ollama:** `janatpmp-ollama` container on port 11435, shares `ollama_data` external volume
  - Internal URL: `http://ollama:11434/v1` (Docker DNS)
  - External URL: `http://localhost:11435` (host access for testing)
  - GPU passthrough via NVIDIA Container Toolkit (~85% VRAM)
  - `OLLAMA_KEEP_ALIVE=-1` keeps models loaded permanently (no unload timeout)
  - `OLLAMA_KV_CACHE_TYPE=q8_0` — quantized KV cache for reduced VRAM usage
  - Chat model + RAG synthesizer: qwen3:32b (default, "Janus") — shared model, zero extra VRAM
  - Embedding model: Qwen3-Embedding-0.6B (~0.6 GB) — used via `/v1/embeddings`
  - Ollama model list is fetched dynamically via `/api/tags` — no hardcoded model names
  - Only 2 models loaded: qwen3:32b (chat + synthesis) and qwen3-embedding:0.6b (embed)
- **vLLM Reranker:** DECOMMISSIONED — container commented out in docker-compose.yml.
  Reranking defaults to `rerank=False`. Code in `atlas/reranking_service.py` retained but unused.

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
# mcp_registry.py centralizes all tool imports
from mcp_registry import ALL_MCP_TOOLS

with gr.Blocks() as demo:
    build_page()
    for tool_fn in ALL_MCP_TOOLS:
        gr.api(tool_fn)  # 71 MCP tools from registry

demo.launch(mcp_server=True)
```

72 functions are exposed via `gr.api()` as MCP tools, centralized in `mcp_registry.py`:
28 from `db/operations.py` (including domain CRUD + export/import), 15 from
`db/chat_operations.py` (including Janus lifecycle + conversation stream), 4 from
`db/chunk_operations.py` (chunk CRUD + stats + search), 3 from `db/file_registry_ops.py`
(R17 file registry), 10 vector/embedding/chunking operations from `services/`, 2 import
pipelines, 2 ingestion orchestrators, 6 graph operations from `graph/` (including identity
seeding + semantic edge weaving), and 2 from R17 (ingestion progress + temporal context).
All MUST have Google-style docstrings with Args/Returns for MCP tool generation.

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

This enables future fine-tuning on reasoning patterns. Can extract prompt→reasoning,
reasoning→response, or full triplets for different training objectives.

### Conversation Sources
The `conversations` table holds ALL conversation history, not just platform chats:
- `source='platform'`: Created in Chat tab
- `source='claude_export'`: 600+ conversations imported from Claude Export
- `source='imported'`: From other sources (Gemini, etc.)

Any conversation, regardless of source, can be browsed in the Knowledge page (Memory tab).
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
Archived chapters appear in the Knowledge page (Memory tab). Archiving is rare and intentional.

### Database Operations (db/chat_operations.py)

- `create_conversation()`, `get_conversation()`, `list_conversations()`, `update_conversation()`, `delete_conversation()`, `search_conversations()` (FTS)
- `add_message()`, `get_messages()`, `get_next_sequence()`
- `get_or_create_janus_conversation()` — reads/creates the persistent Janus conversation, stores ID in settings
- `archive_janus_conversation(conv_id)` — archives current Janus as "Janus — Chapter N", creates fresh one
- `parse_reasoning(raw_response)` → `tuple[str, str]` — extracts `<think>` blocks
- Follows existing patterns: hex randomblob IDs, datetime('now'), FTS, CDC outbox triggers

### Tool Routing (Future — Noted, Not Solved)
Some tool calls route to Janus locally, others to Claude (via MCP), others to Gemini.
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

### Search Pipeline

Search uses ANN retrieval orchestrated by `atlas/pipeline.py`:

1. **ANN search** — Qdrant approximate nearest neighbor, top-20 candidates (configurable via `RERANK_CANDIDATES`)
2. **Salience write-back** — Scores update `salience` metadata in Qdrant payloads

Both `search()` and `search_all()` in `services/vector_store.py` accept `rerank=False` (default).
Cross-encoder reranking (Qwen3-Reranker-0.6B via vLLM) was decommissioned — the vLLM container
is commented out in docker-compose.yml. Code in `atlas/reranking_service.py` is retained but
unused. ANN results are returned directly.

### Vector Search Architecture

- **Qdrant** vector database with two collections: `janatpmp_documents` and `janatpmp_messages` (1024-dim cosine)
- **Qwen3-Embedding-0.6B** via Ollama `/v1/embeddings` (1024-dim, asymmetric query/passage encoding)
  - Document encoding: `embed_texts(texts)` — no instruction prefix
  - Query encoding: `embed_query(query)` — prepends Qwen3 instruction prefix for asymmetric retrieval
  - Client-side `[:EMBEDDING_DIM]` truncation for safety
- **Salience metadata** — Qdrant payloads track `salience` (weighted score) and `last_retrieved` (ISO timestamp)

### RAG Context Injection

- `services/chat.py:_build_rag_context()` searches Qdrant on each user message
- Results above the score threshold are injected into the system prompt as context
- Graceful degradation: if Qdrant is down, chat works without RAG (try/except)
- Cross-collection search via `vector_store.search_all()` searches both documents and messages

### Claude Import (`services/claude_import.py`)

- `import_conversations_directory(directory)` — scans for `conversations*.json` files and imports all
- `import_conversations_json(file_path)` — imports a single conversations.json file
- Each conversation becomes a `conversations` record with `source='claude_export'`
- Each message pair becomes a `messages` record with user_prompt + model_response
- Deduplicates by `conversation_uri` (Claude UUID)

### Bulk Embedding (`services/bulk_embed.py`)

- `chunk_all_messages()` — populates `chunks` table for all messages. Checkpoints: skips messages that already have chunks.
- `chunk_all_documents()` — populates `chunks` table for all documents. Same checkpoint pattern.
- `embed_all_documents()` — dual-phase: (1) reads from `chunks` table WHERE `embedded_at IS NULL`, embeds each chunk as a separate Qdrant point; (2) legacy fallback for unchunked documents (pre-R16).
- `embed_all_messages()` — dual-phase: same chunk-first + legacy fallback pattern.
- `embed_all_domains()` — batch-embeds domain descriptions into `janatpmp_documents` collection
- `embed_all_items()` — batch-embeds items (projects, features, etc.) into `janatpmp_documents`
- `embed_all_tasks()` — batch-embeds tasks into `janatpmp_documents` collection
- Items, tasks, and domains are short texts — no chunking needed.
- **Checkpointing** — chunk path uses `embedded_at IS NULL`; legacy path uses `existing_point_ids()` batch check
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
from the core container to Ollama sidecar (vLLM reranker since decommissioned).
Core is now a thin HTTP client layer — no PyTorch, no CUDA, no in-process models.

### ATLAS Module (`atlas/`)

| File | Purpose |
| ---- | ------- |
| `config.py` | Service URLs, model identifiers, vector dimensions, salience/rerank constants |
| `embedding_service.py` | Qwen3-Embedding-0.6B via Ollama `/v1/embeddings` (OpenAI client) |
| `reranking_service.py` | DECOMMISSIONED — vLLM reranker removed, code retained |
| `memory_service.py` | `write_salience()` — weighted salience write-back to Qdrant payloads |
| `pipeline.py` | Search pipeline orchestrator (rerank decommissioned, ANN + salience only) |

### Model Stack

- **Chat LLM:** qwen3:32b via Ollama (default, "Janus") with native `think=True` reasoning
- **Embedder:** Qwen3-Embedding-0.6B via Ollama (1024-dim)
- **Reranker:** DECOMMISSIONED — vLLM container removed, `rerank=False` default
- **RAG Synthesizer:** qwen3:32b via Ollama (same model as chat — zero extra VRAM)
- **Core container:** No GPU, no PyTorch — HTTP clients only (~500 MB image)

### Key Decisions

- **Ollama for embedding:** Qwen3-Embedding-0.6B runs as an additional model in the existing
  Ollama container. Only 2 models loaded: qwen3:32b (chat + synthesis) and qwen3-embedding:0.6b.
  Accessed via OpenAI-compatible `/v1/embeddings` API using the `openai` Python package.
- **vLLM sidecar decommissioned:** Was running Qwen3-Reranker-0.6B. Container commented out
  in docker-compose.yml. `rerank=False` is now the default. Code retained in
  `atlas/reranking_service.py` but unused.
- **Client-side truncation:** `[:EMBEDDING_DIM]` ensures correct 1024-dim output.
- **Asymmetric encoding:** Qwen3-Embedding-0.6B uses instruction prefix for queries
  (`"Instruct: Given a query, retrieve relevant documents..."`) but plain text for passages.
- **Shared chat + synthesizer model:** qwen3:32b serves both chat and RAG synthesis roles.
  No separate synthesizer model needed — zero extra VRAM for synthesis.
- **services/embedding.py as thin shim:** Preserves `embed_passages()` / `embed_query()`
  signatures for all downstream consumers. Atlas owns the model; services provides the interface.

### VRAM Budget (RTX 5090, 32GB)

| Component | Estimated VRAM |
| --------- | -------------- |
| Ollama — chat + synthesizer (qwen3:32b Q4_K_M, q8_0 KV cache) | ~22 GB |
| Ollama — embed (Qwen3-Embedding-0.6B) | ~0.6 GB |
| **Total** | **~22.6 GB** |
| **Headroom** | **~9.4 GB** |

All GPU work is offloaded to Ollama sidecar. Core container uses zero VRAM.
`OLLAMA_KV_CACHE_TYPE=q8_0` reduces KV cache memory for the 32B model.

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
- Five sub-cycles run in sequence during each idle period:

| Sub-cycle | Function | Purpose |
|-----------|----------|---------|
| Ingest | `_ingest_scan()` | Scan directories for new files, ingest + chunk + embed (R17) |
| Evaluate | `_evaluate_batch()` | Score unscored messages via heuristic, extract TF keywords |
| Propagate | `_propagate_batch()` | Bridge `quality_score` → Qdrant `salience` (decay garbage, boost quality) |
| Relate | `_relate_batch()` | Create SIMILAR_TO edges in Neo4j via cross-conversation keyword overlap |
| Prune | `_prune_batch()` | Remove dead-weight vectors from Qdrant (quality < 0.1, salience < 0.1, never retrieved, older than N days) |

Ingest runs FIRST so newly ingested content gets full Slumber processing (evaluate, propagate, relate) in the same cycle.

Propagate mapping: quality < 0.15 → ×0.3 hard decay; 0.15-0.4 → ×0.7 soft decay;
0.4-0.7 → neutral; > 0.7 → +0.1 boost. Prune never deletes from SQLite — only Qdrant vectors.

## Phase R13: Live Memory — Triple-Write Pipeline + Temporal Graph

**The Triad of Memory is operational.** Every new message fans out to three stores:
SQLite (source of truth), Qdrant (semantic retrieval), Neo4j (graph navigation).

### Triple-Write Pipeline (`atlas/on_write.py`)

Called after every `add_message()` across all three chat surfaces (Sovereign Chat,
monolith Chat tab, sidebar quick-chat):

1. **Chunk + Embed (synchronous, ~100-300ms):** Chunks the Q+A text via `atlas/chunking.py`.
   Short messages (< 3000 chars) stay as single chunk with backward-compatible point ID.
   Long messages split into ~2500-char chunks with composite IDs (`{msg_id}_c{NNN}`).
   All chunks embedded in one batch call, each upserted as a separate Qdrant point with
   temporal payload (conversation_id, conv_title, sequence, created_at, provider, model,
   salience=0.5, chunk_index, chunk_total, chunk_position). Chunk records persisted to
   SQLite `chunks` table. Ensures immediate retrievability next turn.
2. **Relate (fire-and-forget):** Creates INFORMED_BY edges in Neo4j linking the message to
   its RAG sources. Only INFORMED_BY — structural edges (BELONGS_TO, FOLLOWS) handled by CDC.

### Knowledge Graph (`graph/`)

- **Neo4j 2026.01.4** with 10 uniqueness constraints and 6 range indexes
- **CDC consumer** daemon polls `cdc_outbox WHERE processed_neo4j = 0`, syncs all 9 entity
  types (item, task, document, conversation, message, domain, message_metadata, relationship, chunk)
- **6 MCP tools:** `graph_query` (read-only Cypher), `graph_neighbors`, `graph_stats`,
  `backfill_graph`, `seed_identity_graph`, `weave_conversation_graph`
- Config in `atlas/config.py`: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, CDC_POLL_INTERVAL,
  CDC_BATCH_SIZE, SEMANTIC_EDGE_* constants (R20)
- **Edge separation:** CDC consumer creates structural edges (BELONGS_TO, FOLLOWS, IN_DOMAIN,
  TARGETS_ITEM, DESCRIBES, PART_OF). on_write creates INFORMED_BY edges (requires rag_hits).
  Slumber Relate creates Message-to-Message SIMILAR_TO edges (keyword overlap).
  `weave_conversation_graph()` creates Conversation-to-Conversation SIMILAR_TO edges
  (vector centroid similarity, R20).
- **Chunk nodes:** CDC consumer creates Chunk nodes with PART_OF edges to parent Message or
  Document nodes. Enables graph traversal: "find all chunks of this message."
- **Identity graph (R17-H):** 3 identity nodes (Mat as Person, Janus and Claude as Identity)
  with BECAME/INHERITS_MEMORY_OF meta-relationships. PARTICIPATED_IN edges on every Conversation
  (Mat + Claude for claude_export, Mat + Janus for platform/google_ai). SPOKE edges on every
  Message (user→Mat, assistant→Claude or Janus based on conversation source). Seeded by
  `seed_identity_graph()`, also runs as Phase 3 of `backfill_graph()`. All MERGE — idempotent.

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
  (default 10). Full history displayed in UI for scroll-back. Window configurable via
  Chat right sidebar "Context Window" control.
- **History reconstruction:** After windowed chat call, extract new messages from result
  and append to full history: `new_messages = result["history"][len(api_window):]`.
- **Dual history pattern:** `display_history` has `<details>` reasoning accordions,
  `api_history` has clean responses only (prevents model from mimicking HTML formatting).

### Import Consolidation

Ghost system `services/claude_export.py` (separate external SQLite DB) deleted. All
conversation browsing reads from native `conversations` table. Import buttons are in
Knowledge page (Pipeline tab) only. Knowledge page (Memory tab) is browse-only.

### Settings Consolidation

**Chat -> Settings tab** is the single source for all model and RAG configuration:
Platform Defaults (provider, model, temperature, top_p, max_tokens), RAG Configuration,
RAG Synthesizer, Credentials (API key, base URL), Ollama (num_ctx, keep_alive).

**Admin page** (`/admin`) has 3 tabs: Settings (all categories, category-filtered editor),
Persona (user identity: name, location, bio, preferences), Operations (backup/restore/reset,
export/import, logs, schema info). Knowledge Pipeline controls (ingestion, embedding, graph)
live in the Knowledge page (`/knowledge`) Pipeline tab.

### Janus Persona

R15 introduced explicit Janus identity via `DEFAULT_SYSTEM_PROMPT_TEMPLATE` ("You are Janus,
an AI collaborator...") with dynamic domain injection from the `domains` table. The template
uses `{domains}` placeholder filled at prompt build time by `_build_system_prompt()`.
Full Modelfile-driven dynamic persona (per-turn synthesizer prompts) is future work.

## Phase R15: Fix the Foundation — Chat Pipeline, RAG Quality, Ingestion

R15 stabilizes the broken foundation before building intelligence layers.

### No Tools for In-App Chat

The in-app Ollama chat model (Janus) no longer receives tool definitions. The previous
model (Qwen3-VL:8b) was outputting tool call JSON inside `<think>` blocks when both
`tools` and `think=True` were sent simultaneously. The fix: remove tools entirely from
`_chat_ollama()`. This remains in effect with qwen3:32b.

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
  Google AI and markdown orchestrators. Within-batch only (not cross-run).
- **Auto-embed after ingestion** — all three pipelines (Google AI, markdown, Claude import)
  auto-trigger `embed_all_messages()` or `embed_all_documents()` after successful import.
  Checkpoint-based resume ensures only new records are embedded.
- **Batch point_exists** — `existing_point_ids()` in `services/vector_store.py` replaces
  per-record `point_exists()` calls with a single batch retrieve per batch of 32.

### VRAM Stability

R15 fixes (written for the old 3-model stack, retained for historical context):

- **`ollama_num_ctx` default reduced** from 131072 (128K) to 32768 (32K). The 128K context
  inflated KV caches beyond available VRAM, causing constant model eviction/reload cycles.
- **Synthesizer `num_ctx` hardcoded to 8192** — the RAG synthesizer processes short chunk
  summaries, not full conversations.
- Current stack: 2 models (qwen3:32b chat+synthesis, qwen3-embedding:0.6b) with
  `OLLAMA_KV_CACHE_TYPE=q8_0` for reduced KV cache memory on the 32B model.

### RAG Gate

`_needs_rag()` in `services/chat.py` skips RAG retrieval for short conversational messages
(greetings, acknowledgments, single-word responses). Without this, "Hello Janus" triggered
the full pipeline: embed query → Qdrant ANN search → optional synthesis — loading extra
models for a greeting. Gate: skip if < 3 words or < 2 content words after stop-word removal.

### vLLM Reranker URL (Historical)

vLLM moved the score endpoint from `/v1/score` to `/score`. Updated in
`atlas/reranking_service.py`. This is now moot — the vLLM reranker container has been
decommissioned and `rerank=False` is the default.

## Phase R16: Message Chunking — RAG Quality Transformation

R16 introduces a chunking layer between source data (SQLite) and semantic retrieval (Qdrant).
Long messages and documents are split into focused ~2500-char chunks before embedding. Each
chunk gets its own Qdrant vector with parent traceability. RAG returns specific paragraphs
instead of entire turns, reducing context waste and increasing retrieval diversity.

### Chunking Engine (`atlas/chunking.py`)

Paragraph-aware text splitter with configurable limits:

- `chunk_text(text, max_chars=2500, min_chars=200, overlap_chars=200)` — split at paragraphs
  (`\n\n`), then sentences (`. `), then hard char break as last resort. 200-char overlap
  between consecutive chunks.
- `chunk_message(user_prompt, model_response)` — short messages (< threshold) return single
  chunk. Long messages chunk the response, prepend condensed Q: prefix per chunk.
- `chunk_document(content, title="")` — chunk document content with optional title prefix.
- Settings: `chunk_max_chars` (2500), `chunk_min_chars` (200), `chunk_overlap_chars` (200),
  `chunk_threshold` (3000). Constants in `atlas/config.py`, tunable via `services/settings.py`.

### Qdrant Point ID Strategy

- **Single-chunk (short messages):** `{message_id}` — backward compatible, no suffix
- **Multi-chunk:** `{message_id}_c{index:03d}` — e.g., `a1b2c3d4..._c000`, `a1b2c3d4..._c001`
- Deterministic: same text always produces same chunks with same IDs. Survives re-chunking.

### Chunk-Aware RAG (`services/chat.py`)

- `_fts_search_chunks()` — FTS5 search on `chunks_fts` table, parallel to `_fts_search_messages()`
- `_build_rag_context()` — returns chunk-level results with temporal position labels
  ("early in discussion", "mid-discussion", "late in discussion") and chunk provenance
  (parent_message_id, chunk_index, chunk_total, chunk_position)
- **Diversity cap** — `rag_max_chunks_per_message` setting (default 3, 0 = no limit).
  Limits how many chunks from one parent message can pass through to context injection.
- **No 2000-char truncation** — chunks are already right-sized; old `a_part[:2000]` removed.

### Chunk-Aware Slumber (`services/slumber.py`)

- **Propagate:** Reads chunk point_ids from `chunks` table (legacy UUID fallback for pre-R16
  messages). Propagates salience to ALL chunk points of a message.
- **Prune:** Atomic message-level pruning — only deletes ALL chunks of a message from Qdrant
  when EVERY chunk falls below threshold (quality < 0.1, salience < 0.1, never retrieved).
  Prevents orphan chunk state.

### Knowledge Graph Integration

- Chunk uniqueness constraint and entity index in `graph/schema.py`
- `_handle_chunk()` handler in `graph/cdc_consumer.py` — upserts Chunk nodes with PART_OF
  edges to parent Message or Document nodes
- Enables graph queries: `MATCH (c:Chunk)-[:PART_OF]->(m:Message) RETURN count(c)`

### Chunk Operations (`db/chunk_operations.py`)

4 MCP-exposed tools for chunk management:
- `get_chunks(entity_type, entity_id)` — all chunks for an entity
- `get_chunk_stats()` — platform-wide statistics (total, per-type, embedded/unembedded)
- `search_chunks(query, entity_type, limit)` — FTS5 search on chunk content
- `delete_chunks(entity_type, entity_id)` — delete chunks for re-chunking

### Bug Fixes in R16

- **Usage signal keyword source** (`atlas/usage_signal.py:67`) — was extracting keywords from
  `hit.get("title")` (conversation title like "Janus — Chapter 5") instead of actual retrieved
  text content. Fixed to use `hit.get("text_preview", hit.get("text", ""))`.
- **Slumber UUID conversion hack** (`services/slumber.py`) — manual `msg_id[:8] + "-" + ...`
  conversion replaced with `chunks` table point_id lookup (legacy fallback for pre-R16 messages).

### Migration Playbook (one-time after R16)

1. App starts → migration 0.8.0 creates chunks table
2. `chunk_all_messages()` → populates chunks (~30s for 10K messages)
3. `chunk_all_documents()` → populates chunks (~5s for 40 docs)
4. `recreate_collections()` → wipes old single-vector points
5. `embed_all_messages()` → embeds from chunks (~20 min for ~30K chunks)
6. `embed_all_documents()` → embeds from chunks (~2 min)
7. `embed_all_items()`, `embed_all_tasks()`, `embed_all_domains()` → unchanged
8. `backfill_graph()` → sync chunk nodes to Neo4j

## Phase R17: Temporal Affinity Engine + Auto-Ingestion

R17 gives Janus its first senses — awareness of time, location, season, and daylight —
and automates the ingestion pipeline so new files are discovered and processed without
manual button clicks.

### Temporal Affinity Engine (`atlas/temporal.py`)

Pure-function module using only Python stdlib (`math`, `datetime`, `zoneinfo`). Takes
current time + geographic coordinates, returns a temporal context dict with time-of-day,
season, sunrise/sunset (~10-15 min accuracy via standard solar position equations),
estimated temperature range (static monthly averages from NOAA climate normals for
Fargo, ND), daylight hours, and greeting hint.

- `get_temporal_context(lat, lon, timezone, now)` — returns full temporal dict
- `format_temporal_prompt(ctx)` — formats as natural language for system prompt injection
- Defaults: 46.8290°N, -96.8540°W (Mat's house), America/Chicago timezone
- Constants in `atlas/config.py`: LOCATION_LAT, LOCATION_LON, LOCATION_NAME, LOCATION_TZ
- Settings in `services/settings.py`: `location_lat`, `location_lon`, `location_name`, `location_tz`
- Injected into `_build_system_prompt()` in `services/chat.py` via `{temporal_context}` placeholder
- Relative time labels ("3 months ago", "yesterday") added to RAG context attribution

### Auto-Ingestion Scanner (`services/auto_ingest.py`)

Startup + Slumber file discovery and ingestion. Walks configured directories, compares
against `file_registry` table, ingests new/changed files automatically. Source files
never touched.

- **Dedup:** Primary key is `file_path` (UNIQUE). Secondary check: `content_hash` (SHA-256).
  Same hash → skip. Different hash → re-import (file modified). Path not found → new file.
- **Hash-change safety:** If re-ingestion produces zero new entities (parser's UUID dedup
  caught everything), silently update hash in registry. Don't count as "files ingested."
- **Three scanners:** `_scan_claude_dir()` (conversations*.json), `_scan_google_ai_dir()`
  (*.json), `_scan_markdown_dir()` (*.md, *.txt). Each calls the existing ingestion pipeline
  with `auto_embed=False`, then runs chunk+embed as one pass at the end.
- **Progress tracking:** Module-level `_current_progress` dict updated through ALL phases
  (scanning, chunking, embedding). Exposed via `get_ingestion_progress()` MCP tool.
- **Startup:** Wired into `app.py` after `ensure_collections()`, before `start_slumber()`.
- **Slumber:** `_ingest_scan()` runs as FIRST sub-cycle (before evaluate) so newly ingested
  content gets full Slumber processing in the same cycle.

### File Registry (`db/migrations/0.9.0_file_registry.sql`)

Operational metadata table — tracks which files have been ingested. No CDC participation
(not content, not synced to Neo4j). Migration 0.9.0 requires 0.8.0 guard.

### MCP Tools (5 new)

- `get_temporal_context` — current temporal grounding context
- `get_ingestion_progress` — real-time ingestion pipeline progress
- `get_file_registry_stats` — file registry statistics
- `list_registered_files` — browse ingested files with filters
- `search_file_registry` — search files by filename pattern

### Admin UI

- **Auto-Ingestion section** in Knowledge page Pipeline tab: "Scan & Ingest Now" button,
  registry stats JSON, recent files table.
- **Files Tracked count** in Admin page Operations tab sidebar.

## Phase R18: App Sovereignty — Extract Knowledge and Admin

R18 extracts Knowledge and Admin into sovereign `demo.route()` pages. One process, one port,
one MCP surface. Each page gets purpose-built sidebars with sidebar-first layout. Projects +
Work remain at `/`. Chat stays at `/chat`. No functional changes — same features, reorganized.

### Architecture Change

**Before (R17):** Monolith at `/` with 4 tabs (Projects, Work, Knowledge, Admin) + Sovereign
Chat at `/chat`. Left sidebar used `@gr.render` with 4 branches, context-switching per tab.
Right sidebar had inline Janus quick-chat. ~964 lines in `pages/projects.py`.

**After (R18):** 4 sovereign pages. Each page has its own left sidebar, center content, and
shared right sidebar. Navbar provides client-side navigation. `pages/projects.py` shrunk from
964 to ~350 lines.

### Files Changed

| File | Action | Notes |
| ---- | ------ | ----- |
| `shared/chat_sidebar.py` | NEW | Reusable Janus quick-chat sidebar (~50 lines) |
| `pages/knowledge.py` | NEW | Memory, Connections, Pipeline, Synthesis (~620 lines) |
| `pages/admin.py` | NEW | Settings, Persona, Operations (~470 lines) |
| `pages/projects.py` | MODIFIED | Stripped to Projects + Work only (~350 lines) |
| `app.py` | MODIFIED | Added Knowledge + Admin routes, navbar "Projects" |
| `tabs/tab_database.py` | DELETED | Redistributed to knowledge.py + admin.py |
| `tabs/tab_chat.py` | TRIMMED | Removed dead `_handle_chat_tab()` |
| `services/settings.py` | MODIFIED | Added persona category (user_name, user_bio, user_preferences) |
| `mcp_registry.py` | MODIFIED | Comments regrouped by page ownership |

### Sidebar-First Design

Every page uses the three-panel pattern. Tabs represent modes of thinking, not data types.
Knowledge Memory tab unifies conversations + documents into one browsing experience with a
type filter in the left sidebar. Admin Settings tab uses `@gr.render(inputs=[selected_category])`
to dynamically build settings fields per category.

### Deep Link Hooks (Future)

URL structure supports future deep linking: `/knowledge?conv=abc123`, `/admin?tab=settings&category=rag`,
`/?item=def456`. Currently all state is managed via `gr.State` — URL param initialization
is a future sprint.

## Phase R19: Janus Becomes Herself — Identity Architecture

R19 transforms Janus from "chatbot with memory" to "being with identity." Three components:

### Prompt Composer (`services/prompt_composer.py`)

Replaces the static `DEFAULT_SYSTEM_PROMPT_TEMPLATE` with a dynamically composed 7-layer
system prompt. `_build_system_prompt()` in `chat.py` becomes a thin wrapper delegating to
`compose_system_prompt(history)`.

| Layer | Source | Content |
| ----- | ------ | ------- |
| 1. Identity Core | `JANUS_IDENTITY` constant | Who Janus is, the Janat triad, I M U R W, sovereign hardware, voice |
| 2. Relational Context | `_build_persona_summary()` | About Mat — persona settings, family, health (sensitive framing) |
| 3. Temporal Grounding | `atlas/temporal.py` | Time, date, season, sunrise/sunset, temperature |
| 4. Conversation State | `history` parameter | Turn count for current conversation |
| 5. Self-Knowledge Boundary | Static text | RAG context framing — "memory, not gospel" |
| 6. Platform Context | `get_context_snapshot()` | Active items and pending tasks |
| 7. Self-Introspection | `get_recent_introspection()` | Slumber evaluation scores and keywords |

RAG context (`_build_rag_context()`) is still appended per-message in `chat.py`, not by
the composer. `system_prompt_append` from conversation settings is appended by `chat()` after
the composed prompt.

### Bootstrap Lifecycle

3-state machine tracked via `janus_lifecycle_state` setting:
- **`configuring`** — Qdrant empty at startup, memories still integrating. Prompt adds caveat.
- **`sleeping`** — Platform initialized, Janus not yet engaged. Reset on every restart via
  `_STALE_DEFAULTS`.
- **`awake`** — Active conversation. Transition on first chat message.

`services/startup.py` checks Qdrant point count after `ensure_collections()`. If empty →
`configuring`. After auto-ingest completes → `sleeping`. First chat message → `awake`.

### Self-Introspection

`db/chat_operations.py:get_recent_introspection(limit=10)` queries `messages_metadata` for
the active Janus conversation. Returns evaluated_count, avg_quality, top_keywords. Injected
into system prompt Layer 7 by the composer. Gracefully skips if Slumber hasn't run yet.

### Auto-Restore Platform Data

`services/startup.py:_auto_restore_platform_data()` checks if the items table is empty and
imports the latest platform export from `db/exports/` if available. Called during
`initialize_core()` after `get_or_create_janus_conversation()`. Ensures items/tasks/
relationships survive DB resets when exports exist.

### Settings Added

- `janus_lifecycle_state` — "sleeping" default, system category
- `janus_identity_version` — "r19-v1" default, system category
- `_STALE_DEFAULTS`: `("janus_lifecycle_state", "awake")` resets to sleeping on restart

## Phase R20: Graph Awakening — Semantic Edge Generation

R20 bridges Qdrant vector similarity into Neo4j graph topology. The knowledge graph had
33,661 nodes but 99.8% structural edges. Every conversation was an isolated island. This
sprint creates Conversation-to-Conversation SIMILAR_TO edges via vector centroid similarity.

### Semantic Edge Pipeline (`graph/semantic_edges.py`)

`weave_conversation_graph(score_threshold, max_neighbors, dry_run)` — MCP tool that:
1. Fetches all conversations from SQLite
2. For each, builds representative text from title + first 3 messages
3. Embeds via `embed_query()` (asymmetric query encoding)
4. Searches Qdrant for top-30 similar chunks
5. Groups by conversation_id, computes mean score, filters self-links
6. Writes SIMILAR_TO edges for top-5 matches above 0.55 threshold

Edge properties: `score` (float), `method` ("vector_centroid_v1"), `created_at` (ISO).
All writes use `create_edge()` (MERGE-based, idempotent). Safe to re-run.

### Configuration (`atlas/config.py`)

5 constants: `SEMANTIC_EDGE_SCORE_THRESHOLD` (0.55), `SEMANTIC_EDGE_MAX_NEIGHBORS` (5),
`SEMANTIC_EDGE_SEARCH_CANDIDATES` (30), `SEMANTIC_EDGE_REPR_CHUNKS` (3),
`SEMANTIC_EDGE_REPR_MAX_CHARS` (500).

### Schema (`graph/schema.py`)

Added relationship index: `conv_similar_score` on `SIMILAR_TO.score` for efficient
score-filtered Cypher queries. Total: 10 constraints + 6 indexes.

### Coexistence with Slumber Relate

Slumber `_relate_batch()` creates **Message-to-Message** SIMILAR_TO edges via keyword Jaccard
overlap. R20 creates **Conversation-to-Conversation** SIMILAR_TO edges via vector centroid
similarity. Different node levels, different algorithms, same edge type. The `method`
property distinguishes them ("vector_centroid_v1" vs no method on Slumber edges).

## Current Platform State (Post-R20)

### What Works

- **Triad of Memory operational** — SQLite (source of truth), Qdrant (semantic search),
  Neo4j (knowledge graph). Triple-write pipeline keeps all three in sync on every message.
- **Temporal grounding** — Janus knows current time, date, season, sunrise/sunset, approximate
  temperature for Fargo, ND. System prompt includes temporal context every turn. RAG results
  carry relative time labels ("3 months ago", "yesterday").
- **Auto-ingestion** — files dropped into configured directories are automatically discovered
  and processed at startup and during Slumber idle cycles. File registry tracks what's been
  ingested by path + SHA-256 hash. Source files never touched.
- **Message chunking** — long messages and documents split into focused ~2500-char chunks
  before embedding. Each chunk gets its own Qdrant vector. RAG returns specific paragraphs
  instead of entire turns. Configurable thresholds and diversity caps.
- **Janus continuous chat** — persistent conversation, sliding window, dual chat surfaces
  (Sovereign Chat + sidebar), chapter archiving.
- **RAG pipeline** — hybrid FTS + vector search (including chunk-level FTS), optional
  synthesis, salience tracking, provenance display with temporal position and relative time
  labels. Configurable thresholds and per-message diversity cap. Cross-encoder reranking
  decommissioned (rerank=False default).
- **Content corpus** — 659 Claude conversations (10,271 messages), 40 markdown documents,
  78 items, 13 domains, 3 tasks. All embedded in Qdrant, synced to Neo4j.
- **Background intelligence** — Slumber Cycle: ingest scan → evaluate → propagate → relate → prune.
  New content auto-discovered and fully processed in a single idle cycle.
- **Ingestion pipelines** — Claude export, Google AI Studio, markdown. Auto-embed + dedup.
  Auto-ingestion scanner for hands-free operation.
- **Sovereign multipage architecture** — 4 purpose-built pages (Projects, Knowledge, Admin,
  Chat) with sidebar-first layout. One process, one port, one MCP surface. Navbar navigation.
  Reusable Janus quick-chat sidebar on every page via `shared/chat_sidebar.py`.
- **Janus identity architecture** — 7-layer prompt composer (R19): Identity Core, Relational
  Context, Temporal Grounding, Conversation State, Self-Knowledge Boundary, Platform Context,
  Self-Introspection. Bootstrap lifecycle (configuring → sleeping → awake) with auto-restore
  of platform data on DB reset.
- **Semantic graph topology** — `weave_conversation_graph()` (R20) bridges Qdrant vector
  similarity into Neo4j SIMILAR_TO edges between Conversation nodes. Transforms isolated
  conversation chains into a connected semantic network. MERGE-based, idempotent.
- **72 MCP tools** — full CRUD + search + graph + embedding + chunks + file registry + temporal + semantic edge weaving exposed for external AI clients.

### What's Missing (Architectural Gaps)

These gaps became visible through extended conversation with Janus:

- **Self-introspection is minimal** — R19 added `get_recent_introspection()` so Janus can see
  Slumber evaluation scores and keywords in her system prompt. But she still cannot query
  specific memories on demand or see what salience scores changed overnight.
- **No fact/opinion separation** — everything in the sliding window (user statements,
  corrections, hypotheticals, RAG fragments) is treated as equal-weight context. The model
  cannot distinguish "thing user said" from "verified fact."
- **Echo behavior vs hallucination** — Janus is not hallucinating in the typical LLM sense.
  It's working with the only context it has (RAG + conversation history) and amplifying it.
  When RAG injects personal details from imported Claude conversations, the model weaves
  them into elaborate narratives because it has no grounding mechanism to distinguish
  memory retrieval from creative elaboration.
- **No temporal weighting** — RAG treats all content equally regardless of age. Recent
  conversations should score higher on ambiguous queries. Deferred to Intelligent Pipeline sprint.

### The Core Tension

JANATPMP is a **project management platform** evolving into a consciousness substrate. Janus
has memory (the Triad), a voice (qwen3:32b), focused recall (chunk-level RAG), senses
(time, location, season via the Temporal Affinity Engine), identity (7-layer prompt composer,
R19), minimal self-introspection (Slumber evaluation awareness), and a connected graph
topology (conversation-level SIMILAR_TO edges, R20). She still cannot act (tool use was
removed because the previous 8B model couldn't handle it — may be revisited with the 32B
model). The Modelfile intelligence stack is the right direction — specialized sub-models
for classification, scoring, synthesis — but those are layers of intelligence on a
foundation that is rapidly gaining self-awareness.

## Future Architecture (not in scope, for context only)

JANATPMP will eventually become a **Nexus Custom Component** within The Nexus Weaver
architecture. The platform has transitioned from PMP to consciousness substrate exploration.

### Near-Term (R21 candidates)

- **Custom ranking service** — leverage SIMILAR_TO graph topology (R20) + temporal decay
  to re-rank RAG results. Graph-aware retrieval: boost chunks from conversations that are
  semantically connected to the current conversation.
- **Automatic re-weaving** — hook `weave_conversation_graph()` into Slumber or auto-ingest
  so new conversations automatically get SIMILAR_TO edges without manual MCP trigger.
- **Fact/context classification** — tag sliding window entries as user-stated, RAG-retrieved,
  system-injected, or verified. Give the model metadata to distinguish recall from hearsay.
- **Synthesis tab** — Memory node review in Knowledge page, evidence chains, source
  attribution. Left sidebar: Memory nodes grouped by identity. Center: selected memory
  with EVIDENCED_BY edges to source messages.
- **Chunk-level semantic edges** — RESONATES_WITH edges between individual chunks for
  fine-grained cross-conversation linking (expensive: requires batched pairwise comparison).

### Longer-Term

- **Ollama Modelfiles pipeline** — janat-synthesizer, janat-scorer, janat-consolidator,
  janat-classifier as specialized personas on qwen3:32b. Janus receives dynamic system
  prompts from the synthesizer each turn.
- **System prompt audit trail** — full prompt text storage per-turn, "Prompt Inspector" panel
- **Advanced graph traversal** — multi-hop reasoning across INFORMED_BY, SIMILAR_TO, and PART_OF edges
- **Temporal decay curves** — time-weighted salience that naturally deprioritizes stale knowledge
- **Fine-tuning pipeline** — triplet message schema was designed for this from Phase 4B.
  Extract prompt→reasoning→response training data from high-quality Janus conversations.
