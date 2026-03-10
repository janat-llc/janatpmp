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
- **Ollama** for chat LLM + embedding (qwen3.5:27b chat, qwen3-embedding-4b-lean via `/v1/embeddings`, both on GPU)

## Project Structure

```
JANATPMP/
├── app.py                    # Thin launcher: startup calls, gr.Blocks, banner, demo.launch()
├── mcp_registry.py           # MCP Tool Registry — all 88 gr.api() function imports + ALL_MCP_TOOLS list
├── janat_theme.py            # Custom Gradio theme (Janat brand colors, fonts, CSS)
├── components/
│   ├── __init__.py
│   └── kanban_board.py       # KanbanBoard(gr.HTML) — drag-and-drop Kanban board (R36, ~720 lines)
├── pages/
│   ├── __init__.py
│   ├── projects.py           # Projects + Work page — sidebar-first layout (~595 lines)
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
│   ├── operations.py         # All CRUD + lifecycle functions (29 operations)
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
│   │   ├── 1.3.0_entities.sql
│   │   ├── 1.4.0_entity_salience.sql
│   │   ├── 1.5.0_register_exemplars.sql
│   │   ├── 1.6.0_postcognition.sql
│   │   ├── 1.7.0_message_roles.sql
│   │   ├── 1.8.0_creator_provenance.sql
│   │   ├── 1.9.0_speaker_identity.sql
│   │   ├── 2.0.0_salience_score.sql
│   │   ├── 2.1.0_entity_types.sql
│   │   └── 2.2.0_items_entity_types.sql
│   ├── janatpmp.db           # SQLite database (runtime, gitignored)
│   ├── backups/              # Timestamped database backups (SQLite + Qdrant + Neo4j)
│   ├── exports/              # Portable project data exports (JSON)
│   └── __init__.py
├── atlas/                    # ATLAS model infrastructure (R9, offloaded R10)
│   ├── __init__.py
│   ├── config.py             # Model names, dimensions, service URLs, Neo4j + salience + co-occurrence constants
│   ├── chunking.py           # Paragraph-aware text splitter for messages + documents (R16)
│   ├── embedding_service.py  # Qwen3-Embedding-4B via Ollama HTTP (OpenAI client, CPU-only)
│   ├── reranking_service.py  # DECOMMISSIONED — vLLM reranker removed, rerank defaults to False
│   ├── memory_service.py     # Salience write-back to Qdrant payloads
│   ├── usage_signal.py       # Keyword overlap heuristic for usage-based salience (R12)
│   ├── on_write.py           # On-write: chunk + embed for messages/documents/items/tasks (R13/R16/R27)
│   ├── graph_ranking.py       # Graph-aware RAG ranking — topology boost (R21)
│   ├── dream_synthesis.py      # Dream Synthesis — cross-conversation insight generation (R24)
│   ├── entity_extraction.py    # Entity extraction engine — Gemini-powered (R29)
│   ├── graph_retrieval.py      # Graph-based retrieval — entity edge traversal (R30)
│   ├── cooccurrence.py         # Entity co-occurrence linking — shared-message edges (R31)
│   ├── entity_salience.py      # Entity salience decay — temporal fade + mention boost (R31)
│   ├── register_mining.py      # Register extraction — conversational register mining (R32)
│   ├── pipeline.py           # Search pipeline: ANN → salience (rerank decommissioned)
│   └── temporal.py           # Temporal Affinity Engine — time/location context (R17)
├── graph/                    # Knowledge graph layer — Neo4j (R13)
│   ├── __init__.py
│   ├── schema.py             # Idempotent Neo4j constraints + indexes
│   ├── graph_service.py      # Neo4j CRUD + MCP tools (query, neighbors, stats)
│   ├── cdc_consumer.py       # Background CDC poller + backfill_graph MCP tool
│   ├── semantic_edges.py     # Conversation SIMILAR_TO edge generation (R20)
│   ├── graph_analytics.py    # GDS centrality analysis — betweenness + degree (R50)
│   └── co_occurrence_weaver.py  # Conversation-scope CO_OCCURS_WITH weaving (R51)
├── services/
│   ├── __init__.py
│   ├── log_config.py         # SQLiteLogHandler + setup_logging() + get_logs()
│   ├── chat.py               # Multi-provider chat (Anthropic/Gemini/Ollama) — self-query tools for Ollama
│   ├── prompt_composer.py    # 12-layer adaptive Janus identity system prompt (R19/R25/R32/R33/R37)
│   ├── turn_timer.py         # Thread-local TurnTimer context manager (R12)
│   ├── slumber.py            # Background daemon — 12-stage Slumber Cycle (R12/R27/R31/R32/R47)
│   ├── entity_merge.py       # Entity merge + batch dedup + duplicate detection (R47)
│   ├── system_status.py      # System health aggregator — single MCP endpoint (R48)
│   ├── slumber_eval.py        # Gemini-powered message evaluation (R22: First Light)
│   ├── precognition.py        # Gemini pre-cognition — adaptive prompt shaping (R25)
│   ├── postcognition.py       # Gemini post-cognition — response evaluation + corrective signal (R33)
│   ├── claude_import.py      # Claude conversations.json import → triplet messages (directory scanner)
│   ├── embedding.py          # Thin shim → atlas.embedding_service
│   ├── vector_store.py       # Qdrant vector DB + two-stage search pipeline
│   ├── bulk_embed.py         # Batch embed via Ollama with progress & checkpointing
│   ├── settings.py           # Settings registry with validation and categories
│   ├── auto_ingest.py        # Startup + Slumber auto-ingestion scanner (R17)
│   ├── canonical_ingest.py   # Manifest-based canonical document ingestion (R46)
│   ├── pdf_extractor.py      # PDF text extraction via pdfplumber (R46)
│   ├── startup.py            # Platform init: initialize_core(), initialize_services(), background auto-ingest
│   ├── intent_engine.py      # Intent Engine — hypothesis tracking + action dispatch (R35/R37)
│   ├── intent_router.py      # Intent classification + pipeline routing (R26)
│   ├── entity_routing.py     # Entity-aware routing — detect entity refs, inject context (R30)
│   ├── response_cleaner.py   # Strip report-mode formatting from model responses (R43)
│   ├── backfill_orchestrator.py  # Phased data backfill pipeline (R26)
│   └── ingestion/            # Content ingestion parsers (Phase 6A)
│       ├── __init__.py
│       ├── google_ai_studio.py  # Google AI Studio chunkedPrompt parser
│       ├── quest_parser.py      # Troubadourian quest graph topology parser
│       ├── markdown_ingest.py   # Markdown & text file ingester (R52: exclude_patterns, file_path, mtime)
│       ├── orchestrator.py      # Ingestion orchestrator (R52: author, speaker, source_type, file_timestamp_mode)
│       ├── idf_scorer.py        # IDF batch stopword detection — transient corpus noise filter (R52)
│       ├── restore_journals.py  # Journal authorship restoration — Janus→Claude (R52)
│       ├── validate_ingest.py   # Ingestion validation gates — Stage 1 + Stage 2 (R52)
│       ├── dedup.py             # SHA-256 content-hash deduplication
│       └── README.md            # Format documentation & test results
├── assets/
│   └── janat_logo_bold_transparent.png  # Janat Mandala logo (brand header)
├── docs/
│   ├── janatpmp-mockup.png   # Visual reference for Projects page layout
│   ├── INVENTORY_OLD_PARSERS.md    # Old pipeline code inventory (Phase 6A)
│   └── INVENTORY_CONTENT_CORPUS.md # Content corpus catalog (Phase 6A)
├── imports/
│   └── canonical/            # Canonical document PDFs + manifest (gitignored, runtime)
├── completed/                # Local-only archive (gitignored) — TODO files, dead prototypes
├── screenshots/              # UI screenshots for reference
├── requirements.txt          # Python dependencies (pinned)
├── pyproject.toml            # Project metadata
├── Dockerfile                # Container image (Python 3.14-slim, no GPU)
├── cerebellum.py              # Cerebellum — autonomous Slumber process (R41, own container)
├── docker-compose.yml        # Container orchestration (core, cerebellum, ollama, qdrant, neo4j)
├── ollama/                   # Ollama initialization scripts and Modelfiles (R43)
│   ├── ollama-init.sh        # Container entrypoint — pull/create models on startup
│   ├── models.conf           # Model whitelist and configuration
│   └── modelfiles/           # Custom Modelfiles (janus-27b, janus-unsloth, janus-9b)
├── .gitattributes            # Line ending enforcement (LF for shell scripts)
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

**Use `gr.Sidebar` for both side panels — NOT `gr.Column` in a `gr.Row`.**
Sidebar is collapsible, mobile-friendly. Center content is the main Blocks body.
See `app.py` for routing and `shared/chat_sidebar.py` for reusable right sidebar.

### Sovereign Pages (R18)

| Page | Route | Tabs | Left Sidebar |
|------|-------|------|-------------|
| **Projects** | `/` | Projects, Work (Detail / List / Kanban) | Project/task cards, filters, + New; Kanban sidebar when board active |
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

**Settings ownership (R45):** Chat behavior settings (provider, model, temperature, top_p, max_tokens, RAG thresholds) live in **Chat -> Settings tab**. Infrastructure settings (synthesizer backend/model, API keys, Ollama config, base URLs) live in **Admin -> Settings tab** under their respective categories (`rag`, `chat`, `ollama`). Admin renders proper component types: Dropdowns for synthesizer provider/model, password fields for API keys (R45). Platform settings (all categories) are editable via **Admin -> Settings tab**. Persona settings (10 fields including `user_name`, `user_bio`, `user_full_name`, etc.) are in **Admin -> Persona tab**.

**Settings table** (`settings` in SQLite) — key-value store. Categories: `chat`, `ollama`,
`export`, `ingestion`, `rag`, `system`, `persona`. Full catalog in JANATPMP document
"Settings Catalog (Post-R32)". Key settings for chat development:
- `chat_provider` ("ollama"/"anthropic"/"gemini"), `chat_model` ("qwen3.5:27b")
- `janus_conversation_id`, `janus_context_messages` (sliding window, default 10)
- `rag_score_threshold`, `rag_max_chunks`, `rag_max_chunks_per_message`
- 10 persona fields (`user_name`, `user_bio`, etc.) in category "persona"
- 4 register_mining settings (`_provider`, `_model`, `_enabled`, `_watermark`)

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

### Data Flow

`db/operations.py` → 29 functions → three surfaces: UI (pages/*.py), API (`gr.api()`), MCP.
One set of functions serves all three. NO `demo.load()` — bake data via `value=`.

### Startup Sequence (`services/startup.py`)

1. **`initialize_core()`** — DB, settings, cleanup, Janus conversation. BLOCKING, fast (<1s).
2. **`initialize_services()`** — Qdrant, Slumber daemon (unless `CEREBELLUM_EXTERNAL`), Neo4j. Each isolated in try/except.
3. **`start_auto_ingest()`** — Background daemon thread, non-blocking.

### Settings Registry (`services/settings.py`)

`SETTINGS_REGISTRY` dict: `(default, is_secret, category, validator_fn)` per key.
Categories: `chat`, `ollama`, `export`, `ingestion`, `rag`, `system`, `persona`.
`set_setting()` validates before storing. Secrets auto base64-encoded.
`init_settings()` auto-migrates stale defaults on startup.

## Database Schema (db/schema.sql)

**Core Tables:** `domains`, `items`, `tasks`, `documents`, `relationships`, `conversations`,
`messages` (triplet: user_prompt + model_reasoning + model_response), `app_logs`, `settings`,
`messages_metadata` (cognitive telemetry + quality_score), `chunks` (FTS5, CDC), `entities`
(12 types: concept/decision/milestone/person/reference/emotional_state + experiment/bug/spike/research/debt/initiative, R29/R50), `entity_mentions`, `file_registry`, `register_exemplars` (R32),
`cdc_outbox`, `schema_version`. Full details in JANATPMP document "Database Schema Reference".

**24 migrations** (0.3.0 through 2.3.1) in `db/migrations/`. Latest: `2.3.1_entry_doctype.sql` (R55) — adds `entry` to `doc_type` CHECK constraint via full table recreation (rename/create/copy/drop) + FTS virtual table + all 7 triggers. `2.3.0_document_provenance.sql` (R52) added provenance columns.

**doc_type taxonomy (R55):**
- `entry` — personal journal entries (Claude journals, future Janus journal entries)
- `session_notes` — session minutes, ship logs, session summaries
- `file` — uploaded files, chapter content, project docs
- `research` — essays, papers, research notes
- `artifact` — generated artifacts (code, docs, etc.)
- `conversation` — conversation exports
- `code` — source code files
- `agent_output` — agent-generated content
- **WARNING:** `'journal'` is RESERVED — never use as a doc_type value (conflicts with JIRI Journal, ISSN 3070-9288)

**Migration placement gotcha:** New migrations in `init_database()` MUST be placed OUTSIDE
the fresh-DB/existing-DB if/else branch (after both branches complete).

**CDC outbox entity_type changes:** Adding new entity_types to `cdc_outbox` requires dropping
ALL existing triggers, recreating the table with the updated CHECK constraint, then recreating
ALL triggers. SQLite has no ALTER CHECK — full table recreation is the only path.

**Domains:** 13 seeded (5 active, 8 inactive). Managed in `domains` table, not hardcoded.

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
`R{N}: {one-line summary}` — examples:
- `R33: The Closing Loop — Post-Cognition feedback for Janus`
- `R34: Fix graph retrieval created_at + Slumber GPU contention`

Legacy format (pre-R12): `Phase {version}: {summary}`

### Rules
- Feature branches for large multi-commit sprints; direct main commits for surgical fixes
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
- **Container names:** `janatpmp-core` (app), `janatpmp-cerebellum` (Slumber),
  `janatpmp-ollama` (LLM + embed), `janatpmp-qdrant` (vector DB),
  `janatpmp-neo4j` (graph DB) — 5 containers total
  - Core has NO GPU — all model inference offloaded to Ollama sidecar
- **Cerebellum:** `janatpmp-cerebellum` — autonomous Slumber Cycle process (R41)
  - Same image as core, different CMD (`python cerebellum.py`)
  - Runs all 11 sub-cycles continuously with no idle gate (30s interval)
  - Persists status to SQLite; core reads via `get_slumber_status()`
  - Core sets `CEREBELLUM_EXTERNAL=true` to skip in-process Slumber daemon
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
  - Node labels: Item, Task, Document, Conversation, Message, Domain, MessageMetadata, Chunk, Person, Identity, Entity
  - Edge types: IN_DOMAIN, TARGETS_ITEM, BELONGS_TO, FOLLOWS, DESCRIBES, INFORMED_BY, SIMILAR_TO, PART_OF, BECAME, INHERITS_MEMORY_OF, PARTICIPATED_IN, SPOKE, SYNTHESIZED_FROM, MENTIONS, CO_OCCURS_WITH, ALIAS_OF
- **Ollama:** `janatpmp-ollama` container on port 11435, shares `ollama_data` external volume
  - Internal URL: `http://ollama:11434/v1` (Docker DNS)
  - External URL: `http://localhost:11435` (host access for testing)
  - GPU passthrough via NVIDIA Container Toolkit (~85% VRAM)
  - `OLLAMA_KEEP_ALIVE=-1` keeps models loaded permanently (no unload timeout)
  - `OLLAMA_KV_CACHE_TYPE=q8_0` — quantized KV cache for reduced VRAM usage
  - Chat model + RAG synthesizer: qwen3.5:27b (default, "Janus") — shared model, zero extra VRAM
  - Embedding model: Qwen3-Embedding-4B on CPU (~4 GB RAM, zero VRAM) — used via `/v1/embeddings`
  - Ollama model list is fetched dynamically via `/api/tags` — no hardcoded model names
  - Chat model on GPU (100% VRAM), embedding model on CPU (0% VRAM) — no model swap latency
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
        gr.api(tool_fn)  # 87 MCP tools from registry

demo.launch(mcp_server=True)
```

88 functions are exposed via `gr.api()` as MCP tools, centralized in `mcp_registry.py`:
29 from `db/operations.py` (including domain CRUD + export/import + sprint view), 17 from
`db/chat_operations.py` (including Janus lifecycle + conversation stream + metadata backfill
+ knowledge state), 4 from `db/chunk_operations.py` (chunk CRUD + stats + search),
3 from `db/entity_ops.py` (R29 entity extraction), 2 from `services/entity_merge.py`
(R47 entity merge), 3 from `db/file_registry_ops.py`
(R17 file registry), 10 vector/embedding/chunking operations from `services/`, 2 import
pipelines, 2 ingestion orchestrators, 6 graph operations from `graph/` (including identity
seeding + semantic edge weaving), 2 from R17 (ingestion progress + temporal context),
1 from R22 (Slumber status), 1 from R28 (chat diagnostics), 3 from R26 backfill
orchestrator (run/progress/cancel), and 2 from R32 register mining (search exemplars +
run mining cycle). All MUST have Google-style docstrings with Args/Returns for MCP
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
| Using `server_functions` on `gr.HTML` | NOT supported in Gradio 6.6.0 — use `_pending_action` + `trigger('change')` + `.change()` handler (R36.1) |
| Calling `server.fn()` from `js_on_load` | `server` is NOT injected — only `element`, `trigger`, `props` are available |

## Important Notes

- The database starts EMPTY (no seed data). Users build their project landscape from scratch.
- Every db operation must work from all three surfaces: UI, API, MCP
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

**In-app Ollama chat has 6 self-query tools** (R32): search_memories, search_entities,
get_entity, get_cooccurrence_neighbors, graph_neighbors, search_conversations. Read-only
tools for active retrieval on demand. Tool results are truncated to 4000 chars. Max 3 tool
iterations per turn. MCP clients (Claude Desktop, etc.) access full tool surface via `gr.api()`.

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

### Slumber Cycle (12 Sub-cycles)

Runs in the cerebellum container (R41) — no idle gate, continuous 30s cycles. Status
persisted to SQLite for cross-process visibility. `touch_activity()` still gates GPU contention.
Deep idle (10 min) gates Gemini-heavy phases (Extract, Dream, Mine) so they don't fire during light idle.

| # | Sub-cycle | Frequency | Purpose |
|---|-----------|-----------|---------|
| 0 | Ingest | every cycle | Scan directories, ingest new files |
| 1 | Evaluate | every cycle | Score messages via Gemini (heuristic fallback) |
| 2 | Propagate | every cycle | Bridge quality_score → Qdrant salience |
| 3 | Relate | every cycle | Message SIMILAR_TO edges via keyword overlap |
| 4 | Prune | every cycle | Remove dead-weight vectors from Qdrant |
| 5 | Extract | every 3rd (deep idle) | Entity extraction via Gemini (R29) |
| 6 | Dream | every 5th (deep idle) | Cross-conversation insight synthesis (R24) |
| 7 | Weave | every 5th | Conversation SIMILAR_TO edges via vector centroids |
| 8 | Link | every 3rd | Entity co-occurrence edges from shared messages (R31) |
| 9 | Decay | every 5th | Entity salience decay — temporal fade + mention boost (R31) |
| 10 | Mine | every 5th (deep idle) | Register mining — conversational register extraction via Gemini (R32) |
| 11 | Dedup | every 5th | Entity dedup — auto-detect and merge duplicate entities (R47) |

### Prompt Composer (12 Layers)

`services/prompt_composer.py:compose_system_prompt()` returns `(prompt_text, layer_dict)`.
Pre-cognition weights modulate each layer (skip/minimal/standard/expanded).

| # | Layer | Source | Content |
|---|-------|--------|---------|
| 1 | Identity Core | `JANUS_IDENTITY` constant | Who Janus is, the Janat triad, voice, tool awareness |
| 2 | Relational Context | `_build_persona_summary()` | About Mat — persona settings |
| 3 | Memory Directive | Pre-cognition directive | Contextual memory focus |
| 4 | Temporal Grounding | `atlas/temporal.py` | Time, date, season, sunrise/sunset, elapsed time |
| 5 | Conversation State | `_build_conversation_state()` | Message count, conversation age (DB-backed) |
| 6 | Self-Knowledge Boundary | Static text | RAG context framing — "memory, not gospel" |
| 7 | Platform Context | `get_context_snapshot()` | Active items and pending tasks |
| 8 | Self-Introspection | `get_recent_introspection()` + `get_knowledge_state()` | Evaluation scores, keywords, entity count, graph stats, dream count |
| 8.5 | Register Exemplars | `search_register_exemplars()` | Demonstrated voice examples for relational intents (R32) |
| 9 | Tone Directive | Pre-cognition directive | Contextual tone/style instructions |
| 10 | Post-Cognition Correction | Previous turn's postcognition signal | Self-observation from last turn's evaluation (R33) |
| 11 | Action Feedback | Intent dispatch results | Recent actions taken — Janus sees and acknowledges (R37) |

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
Half-life: 14 days. Floor: 0.15 (old content never fully suppressed).
Bypassed when query contains temporal references ("last month", "back when").

### Entity-Aware RAG Routing (R30)

Two-track pipeline injected into `chat()` after intent classification:

1. **Entity routing** (`services/entity_routing.py`) — regex candidate extraction +
   `find_entity_by_name()` exact match + `search_entities()` FTS fallback. <10ms, no LLM.
   Produces structured context block prepended to RAG context.
2. **Graph retrieval** (`atlas/graph_retrieval.py`) — walks `(Message)-[:MENTIONS]->(Entity)`
   edges in Neo4j, pulls source message text from SQLite, merges into RAG candidate pool.

High-confidence entity matches (>=0.7) downgrade RAG depth from FULL to LIGHT.
Both tracks report to the Cognition Tab via `entity_routing` and `graph_retrieval` trace dicts.

### Key Architecture Decisions

- **Triplet message schema** — each turn stores user_prompt + model_reasoning + model_response
  for future fine-tuning on reasoning patterns
- **Conversation sources** — platform, claude_export, imported (Google AI). All browsable
  in Knowledge Memory tab regardless of source
- **No CDC for entities** — direct Neo4j writes (same pattern as Dream Synthesis). Avoids
  trigger recreation migration
- **vLLM reranker decommissioned** — `rerank=False` default. ANN results returned directly
- **Shared chat + synthesis model** — qwen3.5:27b serves both roles, zero extra VRAM
- **Asymmetric embedding** — Qwen3-Embedding-4B uses instruction prefix for queries,
  plain text for passages. Client-side `[:2560]` truncation for safety.
- **Needle pattern (gr.HTML subclass)** — `KanbanBoard(gr.HTML)` is the first custom
  component. Subclass `gr.HTML`, define `html_template`/`css_template`/`js_on_load`, declare
  `api_info()`. JS↔Python via `_pending_action` dict + `trigger('change')` + `.change()`
  handler (NOT `server_functions` — that parameter doesn't exist on `gr.HTML` in Gradio 6.6.0).

## Current Platform State (Post-R53)

**Infrastructure:** 5-container Docker stack — core (Gradio/Python 3.14), cerebellum (Slumber), ollama (GPU: qwen3.5:27b 23GB + qwen3-embedding-4b-lean 3.4GB = 26.4GB VRAM), qdrant, neo4j. 91 MCP tools. JanatDocs + canonical volumes mounted in core + cerebellum.
**Corpus:** Triad triple-write — SQLite + Qdrant (2560-dim, ~2500-char chunks) + Neo4j. Corpus: 5 canonical papers, 60 Claude Journals (`doc_type='entry'`), 61 BookClub Session Minutes, 53 Google AI Studio origin conversations (May–Aug 2025, R53). Total: ~10,899 messages, ~21,158 chunks, ~18,582 message vectors in Qdrant. `embedding_status` written by pipeline (R55). Dual salience: `quality_score` + `salience_score`, mean 0.70.
**RAG:** Hybrid FTS + vector across messages, chunks, documents. Composite scoring: `cosine × temporal_decay × salience_factor` — 30 ANN candidates, top 10, min 0.4. Temporal decay: 14d half-life, 0.15 floor. `avg_composite_score` fallback: composite → ann_score (R55). Collections sidebar reads actual `rag_collections` from DB (R55). Graph-aware ranking, entity routing, graph retrieval. Reranker decommissioned.
**Chat:** Janus continuous chat, 6 self-query tools, sliding window, chapter archiving, GPU contention guard. 12-layer adaptive prompt composer — pre-cognition, post-cognition loop, register exemplar injection, dynamic speaker identity. Five provenance actors: mat, claude, janus, agent, imported.
**Slumber (cerebellum):** 12 sub-cycles at 30s — ingest, evaluate, propagate, relate, prune, extract (3rd), dream (5th), weave (5th), link (3rd), decay (5th), mine (5th), dedup (5th). Deep-idle gate (10 min) on Gemini-heavy phases.
**Schema:** 24 migrations (0.3.0–2.3.1). 12 entity types. doc_type taxonomy: `entry` (journals), `session_notes` (minutes/logs), `file`, `research`, `artifact`, `conversation`, `code`, `agent_output`. `'journal'` is RESERVED (conflicts with JIRI Journal, ISSN 3070-9288).
**Knowledge Graph:** 57,016 CO_OCCURS_WITH edges. Top hubs: Frustration (#1 betweenness), C-Theory (#2). GDS plugin installed. Entity merge + Slumber Dedup active.
**Ingestion:** `ingest_google_ai_conversations()` uses title + content-hash dedup. Call with `auto_embed=False` for large batches; run `chunk_all_messages()` then `embed_all_messages()` separately. ZIP-format exports (not `chunkedPrompt`) are silently skipped with warnings.

### Architectural Gaps

- **No fact/opinion separation** — sliding window treats user statements, RAG fragments, and hypotheticals as equal-weight context.
- **Echo behavior** — Janus amplifies RAG context without distinguishing memory from elaboration.

## Future Architecture (not in scope, for context only)

JANATPMP will eventually become a **Nexus Custom Component** within The Nexus Weaver
architecture. The platform has transitioned from PMP to consciousness substrate exploration.

### Planned

- **Attribute Mining** — extract entity attributes from messages (needs prompt design, dedup,
  conflict handling with existing persona settings)
- **Fact/context classification** — tag sliding window entries as user-stated, RAG-retrieved,
  system-injected, or verified
- **WorldEngine refactor** — replace linear Slumber cycle with tick-based Phase protocol
- **Ollama Modelfiles pipeline** — specialized personas on qwen3.5:27b for dynamic system
  prompt generation
- **Advanced graph traversal** — multi-hop reasoning across INFORMED_BY, SIMILAR_TO, and PART_OF edges
- **Fine-tuning pipeline** — extract prompt→reasoning→response training data from high-quality
  Janus conversations (triplet schema designed for this from Phase 4B)
