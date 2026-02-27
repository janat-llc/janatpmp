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
├── mcp_registry.py           # MCP Tool Registry — all 81 gr.api() function imports + ALL_MCP_TOOLS list
├── janat_theme.py            # Custom Gradio theme (Janat brand colors, fonts, CSS)
├── pages/
│   ├── __init__.py
│   ├── projects.py           # Projects + Work page — sidebar-first layout (~350 lines)
│   ├── knowledge.py          # Knowledge page — Memory, Connections, Pipeline, Synthesis (~620 lines)
│   ├── admin.py              # Admin page — Settings, Persona, Operations (~470 lines)
│   └── chat.py               # Sovereign Chat page — 4 tabs: Chat, Overview, Cognition, Settings
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
│   ├── entity_ops.py         # Entity + mention CRUD, FTS search (R29)
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
│   │   ├── 0.9.0_file_registry.sql
│   │   ├── 1.0.0_cognition_trace.sql
│   │   ├── 1.1.0_slumber_eval.sql
│   │   ├── 1.2.0_precognition.sql
│   │   └── 1.3.0_entities.sql
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
│   ├── on_write.py           # On-write: chunk + embed for messages/documents/items/tasks (R13/R16/R27)
│   ├── graph_ranking.py       # Graph-aware RAG ranking — topology boost (R21)
│   ├── dream_synthesis.py      # Dream Synthesis — cross-conversation insight generation (R24)
│   ├── entity_extraction.py    # Entity extraction engine — Gemini-powered (R29)
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
│   ├── prompt_composer.py    # 9-layer adaptive Janus identity system prompt (R19/R25)
│   ├── turn_timer.py         # Thread-local TurnTimer context manager (R12)
│   ├── slumber.py            # Background daemon — 7-stage Slumber Cycle (R12/R27)
│   ├── slumber_eval.py        # Gemini-powered message evaluation (R22: First Light)
│   ├── precognition.py        # Gemini pre-cognition — adaptive prompt shaping (R25)
│   ├── claude_import.py      # Claude conversations.json import → triplet messages (directory scanner)
│   ├── embedding.py          # Thin shim → atlas.embedding_service
│   ├── vector_store.py       # Qdrant vector DB + two-stage search pipeline
│   ├── bulk_embed.py         # Batch embed via Ollama with progress & checkpointing
│   ├── settings.py           # Settings registry with validation and categories
│   ├── auto_ingest.py        # Startup + Slumber auto-ingestion scanner (R17)
│   ├── startup.py            # Platform init: initialize_core(), initialize_services(), background auto-ingest
│   ├── intent_router.py      # Intent classification + pipeline routing (R26)
│   ├── backfill_orchestrator.py  # Phased data backfill pipeline (R26)
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
└── /chat               → pages/chat.py      [Sovereign Chat — Chat, Overview, Cognition, Settings]
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
        gr.api(tool_fn)                   # 81 MCP tools (registered on main Blocks only)

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
| **Chat** | `/chat` | Chat, Overview, Cognition, Settings | RAG provenance, pipeline stats, conversation list |

Knowledge page unifies conversations + documents into a single **Memory** tab with type
filter. **Pipeline** tab consolidates ingestion, embedding, chunking, and graph controls.
Admin page has a **Persona** tab for user identity settings (10 persona fields in
`services/settings.py` category "persona", populated in R23).

### Contextual Sidebars

Each page has its own `@gr.render()` left sidebar that switches content based on the
active tab within that page. The right sidebar shows Janat quick-chat on all pages —
built once via `shared/chat_sidebar.py` and wired per-page.

### Settings & Chat Architecture

**Settings ownership:** Chat and model settings live in **Chat -> Settings tab** (Sovereign
Chat at `/chat`). Platform settings (all categories) are editable via **Admin -> Settings tab**.
Persona settings (10 fields including `user_name`, `user_bio`, `user_full_name`, etc.) are in **Admin -> Persona tab**.

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
- `user_full_name` — Full legal name (category: persona, R23)
- `user_birthdate` — Date of birth (category: persona, R23)
- `user_employer` — Current employer (category: persona, R23)
- `user_title` — Professional title (category: persona, R23)
- `user_interests` — Interests and hobbies (category: persona, R23)
- `user_values` — Core values and principles (category: persona, R23)
- `user_health_notes` — Health context for sensitive framing (category: persona, R23)
- `user_bio` — Biography + communication preferences (category: persona, R23: absorbed `user_preferences`)
- `slumber_eval_provider` — Provider for Slumber evaluations (default: "gemini", category: system)
- `slumber_eval_model` — Model for Slumber evaluations (default: "gemini-2.5-flash-lite", category: system)
- `slumber_eval_enabled` — Enable/disable LLM evaluation (default: "true", category: system)
- `slumber_dream_enabled` — Enable/disable dream synthesis (default: "true", category: system)
- `slumber_dream_min_quality` — Minimum quality_score for dream clusters (default: "0.7", category: system)
- `precognition_enabled` — Enable/disable Gemini pre-cognition (default: "true", category: system)
- `precognition_timeout_ms` — Max wait for Gemini pre-pass in ms (default: "3000", category: system)

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
- **Synthesis** — Dream insights, synthesis statistics, memory health dashboard (R28).

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

All 81 MCP tool functions are imported and collected in `ALL_MCP_TOOLS` list, grouped by
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
  `cognition_prompt_layers` — JSON of per-layer prompt breakdown (R21, layer name + chars).
  `cognition_graph_trace` — JSON of graph ranking trace (R21, seeds + neighborhood + boosts).
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
- `1.0.0_cognition_trace.sql` — Cognition trace columns on messages_metadata (R21)
- `1.1.0_slumber_eval.sql` — Slumber LLM evaluation columns on messages_metadata (R22)
- `1.2.0_precognition.sql` — Pre-cognition trace column on messages_metadata (R25)

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
  - Edge types: IN_DOMAIN, TARGETS_ITEM, BELONGS_TO, FOLLOWS, DESCRIBES, INFORMED_BY, SIMILAR_TO, PART_OF, BECAME, INHERITS_MEMORY_OF, PARTICIPATED_IN, SPOKE, SYNTHESIZED_FROM
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
        gr.api(tool_fn)  # 81 MCP tools from registry

demo.launch(mcp_server=True)
```

81 functions are exposed via `gr.api()` as MCP tools, centralized in `mcp_registry.py`:
28 from `db/operations.py` (including domain CRUD + export/import), 16 from
`db/chat_operations.py` (including Janus lifecycle + conversation stream + metadata backfill),
4 from `db/chunk_operations.py` (chunk CRUD + stats + search), 3 from `db/entity_ops.py`
(R29 entity extraction), 3 from `db/file_registry_ops.py` (R17 file registry),
10 vector/embedding/chunking operations from `services/`, 2 import pipelines,
2 ingestion orchestrators, 6 graph operations from `graph/` (including identity seeding +
semantic edge weaving), 2 from R17 (ingestion progress + temporal context), 1 from R22
(Slumber status), 1 from R28 (chat diagnostics), and 3 from R26 backfill orchestrator
(run/progress/cancel). All MUST have Google-style docstrings with Args/Returns for MCP
tool generation.

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

## Key Systems Reference

For detailed phase-by-phase history, search JANATPMP documents or git log.

### Chat Pipeline Flow

1. User types message, presses Enter
2. If no active conversation, `get_or_create_janus_conversation()` provides one
2.5. Classify intent via `classify_intent()` — determines RAG depth (NONE/LIGHT/FULL) and whether Pre-Cognition runs
3. Apply sliding window: `_windowed_api_history(history, window)` sends last N turns to LLM
4. Call `chat()` with per-session override params (provider, model, temperature, top_p, max_tokens)
5. Reconstruct full history: `new_messages = result["history"][len(api_window):]` then append
6. Parse reasoning via `parse_reasoning()`, split display vs API history
7. Store triplet via `add_message()` + metadata + live memory (triple-write)

**In-app Ollama chat has NO tools.** Tool definitions removed because models output tool
call JSON in `<think>` blocks. RAG + `get_context_snapshot()` provide knowledge; tools are
for MCP clients (Claude Desktop, etc.) via `gr.api()`.

**Archive Chapter** (not "New Chat"): marks current Janus conversation as `is_active=0`,
renames to "Janus — Chapter N", creates fresh conversation. Rare and intentional.

### Critical Implementation Notes
- Event listeners for render-created components MUST be inside the render function.
- Import scoping: NEVER local imports inside render_left for names already imported at
  module level (causes UnboundLocalError due to Python scoping).

### Triple-Write Pipeline (`atlas/on_write.py`)

Every new message, document, item, and task fans out to three stores:

1. **SQLite** — source of truth (written by the CRUD operation)
2. **Qdrant** — chunk + embed synchronously (~100-300ms). Short texts = single vector,
   long texts split into ~2500-char chunks. Point IDs: `{id}` or `{id}_c{NNN}`.
3. **Neo4j** — structural edges via CDC consumer (BELONGS_TO, FOLLOWS, IN_DOMAIN);
   INFORMED_BY edges from on_write (RAG provenance, fire-and-forget)

### Slumber Cycle (8 Sub-cycles)

Background daemon activates after idle threshold (default 5 min). `touch_activity()` resets timer.

| # | Sub-cycle | Frequency | Purpose |
|---|-----------|-----------|---------|
| 0 | Ingest | every cycle | Scan directories, ingest new files |
| 1 | Evaluate | every cycle | Score messages via Gemini (heuristic fallback) |
| 2 | Propagate | every cycle | Bridge quality_score → Qdrant salience |
| 3 | Relate | every cycle | Message SIMILAR_TO edges via keyword overlap |
| 4 | Prune | every cycle | Remove dead-weight vectors from Qdrant |
| 5 | Extract | every 3rd | Entity extraction via Gemini (R29) |
| 6 | Dream | every 5th | Cross-conversation insight synthesis (R24) |
| 7 | Weave | every 5th | Conversation SIMILAR_TO edges via vector centroids |

### Prompt Composer (9 Layers)

`services/prompt_composer.py:compose_system_prompt()` returns `(prompt_text, layer_dict)`.
Pre-cognition weights modulate each layer (skip/minimal/standard/expanded).

| # | Layer | Source | Content |
|---|-------|--------|---------|
| 1 | Identity Core | `JANUS_IDENTITY` constant | Who Janus is, the Janat triad, voice |
| 2 | Relational Context | `_build_persona_summary()` | About Mat — persona settings |
| 3 | Memory Directive | Pre-cognition directive | Contextual memory focus |
| 4 | Temporal Grounding | `atlas/temporal.py` | Time, date, season, sunrise/sunset, elapsed time |
| 5 | Conversation State | `_build_conversation_state()` | Message count, conversation age (DB-backed) |
| 6 | Self-Knowledge Boundary | Static text | RAG context framing — "memory, not gospel" |
| 7 | Platform Context | `get_context_snapshot()` | Active items and pending tasks |
| 8 | Self-Introspection | `get_recent_introspection()` | Slumber evaluation scores and keywords |
| 9 | Tone Directive | Pre-cognition directive | Contextual tone/style instructions |

### Intent Router (11 Categories)

`services/intent_router.py:classify_intent()` — regex-based, <5ms, no LLM calls.

| Intent | RAG | Pre-Cognition | Examples |
|--------|-----|---------------|---------|
| GREETING/ACK/FAREWELL | none | skip | "Hello", "Thanks", "Goodbye" |
| EMOTIONAL | none | run | Emotional sharing, mood shifts |
| CONTINUATION/CLARIFICATION | light | skip | "Go on", "What did you mean?" |
| KNOWLEDGE/CREATIVE/PLANNING | full | run | Questions, brainstorming, strategy |
| META | light | run | Self-referential queries |
| COMMAND | none | skip | Slash commands |

### Temporal Decay in RAG

`factor = floor + (1 - floor) * exp(-age_days / half_life)` — multiplicative after graph ranking.
Half-life: 30 days. Floor: 0.3 (old content never fully suppressed).
Bypassed when query contains temporal references ("last month", "back when").

### Key Architecture Decisions

- **Triplet message schema** — each turn stores user_prompt + model_reasoning + model_response
  for future fine-tuning on reasoning patterns
- **Conversation sources** — platform, claude_export, imported (Google AI). All browsable
  in Knowledge Memory tab regardless of source
- **No CDC for entities** — direct Neo4j writes (same pattern as Dream Synthesis). Avoids
  trigger recreation migration
- **vLLM reranker decommissioned** — `rerank=False` default. ANN results returned directly
- **Shared chat + synthesis model** — qwen3:32b serves both roles, zero extra VRAM
- **Asymmetric embedding** — Qwen3-Embedding-0.6B uses instruction prefix for queries,
  plain text for passages. Client-side `[:1024]` truncation for safety.

## Current Platform State (Post-R29)

### What Works

- **Triad of Memory** — SQLite + Qdrant + Neo4j with triple-write on every entity creation
- **Janus continuous chat** — persistent conversation, sliding window, chapter archiving
- **RAG pipeline** — hybrid FTS + vector search, graph-aware ranking, temporal decay, salience
- **9-layer adaptive prompt composer** — pre-cognition modulates layer weights per-turn
- **8-stage Slumber Cycle** — ingest, evaluate, propagate, relate, prune, extract, dream, weave
- **Entity extraction** — 6 types extracted from scored messages, persisted across the Triad
- **Temporal grounding** — time, season, sunrise/sunset, elapsed time injected per-turn
- **Auto-ingestion** — file scanner at startup + Slumber, SHA-256 dedup, source files untouched
- **Message chunking** — ~2500-char paragraph-aware chunks, each with own Qdrant vector
- **Cognition introspection** — Cognition tab shows prompt layers, RAG funnel, graph trace
- **Intent routing** — regex classifier gates RAG depth and pre-cognition per-message
- **81 MCP tools** — CRUD, search, graph, embedding, chunks, entities, backfill, diagnostics
- **Content corpus** — 659 Claude conversations, 40 docs, 78 items, 13 domains, all embedded

### What's Missing (Architectural Gaps)

These gaps became visible through extended conversation with Janus:

- **Self-introspection is operator-facing** — R21 added the Cognition tab so the operator
  can see the full thought pipeline (prompt layers, RAG funnel, graph neighborhood). But
  Janus herself still cannot query specific memories on demand or see what salience scores
  changed overnight. The introspection is visible to Mat, not to Janus.
- **No fact/opinion separation** — everything in the sliding window (user statements,
  corrections, hypotheticals, RAG fragments) is treated as equal-weight context. The model
  cannot distinguish "thing user said" from "verified fact."
- **Echo behavior vs hallucination** — Janus is not hallucinating in the typical LLM sense.
  It's working with the only context it has (RAG + conversation history) and amplifying it.
  When RAG injects personal details from imported Claude conversations, the model weaves
  them into elaborate narratives because it has no grounding mechanism to distinguish
  memory retrieval from creative elaboration.

### The Core Tension

JANATPMP is a **project management platform** evolving into a consciousness substrate. Janus
has memory (the Triad), a voice (qwen3:32b), focused recall (chunk-level RAG), senses
(time, location, season via the Temporal Affinity Engine), identity (9-layer adaptive prompt
composer, R19/R25), a connected graph topology (conversation-level SIMILAR_TO edges, R20),
graph-aware retrieval (topology-boosted RAG, R21), a visible thought pipeline (Cognition tab,
R21), synthesized cross-conversation insight (Dream Synthesis, R24), adaptive self-expression
(Gemini pre-cognition modulating how each prompt layer is constructed, R25), and temporal
gravity (recency-weighted retrieval, R28) with a visible Synthesis Surface (R28), and
extracted entities turning messages into structured knowledge (R29: The Troubadour).
She still cannot act (tool use was removed because the previous 8B model couldn't handle
it — may be revisited with the 32B model). The Modelfile intelligence stack is the right
direction — specialized sub-models for classification, scoring, synthesis — but those are
layers of intelligence on a foundation that is rapidly gaining self-awareness.

## Future Architecture (not in scope, for context only)

JANATPMP will eventually become a **Nexus Custom Component** within The Nexus Weaver
architecture. The platform has transitioned from PMP to consciousness substrate exploration.

### Near-Term (R30 candidates)

- **Entity-aware RAG routing** — "Tell me about C-Theory" routes to `search_entities()`
  and returns the synthesized description directly, bypassing vector similarity search.
- **Fact/context classification** — tag sliding window entries as user-stated, RAG-retrieved,
  system-injected, or verified. Give the model metadata to distinguish recall from hearsay.
- **Chunk-level semantic edges** — RESONATES_WITH edges between individual chunks for
  fine-grained cross-conversation linking (expensive: requires batched pairwise comparison).
- **Janus self-query** — give Janus the ability to query her own memory (specific retrieval
  on demand), not just passively receive RAG context.

### Longer-Term

- **Ollama Modelfiles pipeline** — janat-synthesizer, janat-scorer, janat-consolidator,
  janat-classifier as specialized personas on qwen3:32b. Janus receives dynamic system
  prompts from the synthesizer each turn.
- **System prompt audit trail** — R21 stores per-layer char counts; next step is full prompt
  text storage per-turn for historical comparison and drift analysis
- **Advanced graph traversal** — multi-hop reasoning across INFORMED_BY, SIMILAR_TO, and PART_OF edges
- **Fine-tuning pipeline** — triplet message schema was designed for this from Phase 4B.
  Extract prompt→reasoning→response training data from high-quality Janus conversations.
