# TODO: Architectural Refactor

**Created:** 2026-02-13
**Branch:** `feature/refactor` (to be created)
**Dependency order:** R1 -> R2 & R3 (parallel) -> R4 -> R5 -> R6 -> R7

---

## Phase R1: Centralized Logging Infrastructure

**Why:** Zero logging in 6/8 core services. Foundation for all subsequent phases.

- [ ] Create `db/migrations/0.4.0_app_logs.sql` -- `app_logs` table with level, module, function, message, metadata JSON columns. Indexes on (level, timestamp) and (module, timestamp)
- [ ] Create `services/log_config.py` (~80 lines)
  - [ ] `SQLiteLogHandler(logging.Handler)` -- writes to `app_logs` table, batch flushes on WARNING+ or every 10 records
  - [ ] `setup_logging(level=logging.INFO)` -- configures root logger with console + SQLite handlers
  - [ ] `get_logs(level, module, limit, since)` -- query function for Admin UI
  - [ ] `cleanup_old_logs(days=30)` -- retention, called on startup
- [ ] `app.py` -- Call `setup_logging()` before `init_database()`, replace `print("Qdrant not available...")` (line 42) with `logger.warning()`
- [ ] `services/chat.py` -- Add `logger = logging.getLogger(__name__)`, log chat start/end (INFO), provider errors (ERROR), RAG fallback (DEBUG)
- [ ] `services/settings.py` -- Add logger, log base64 decode failures (WARNING)
- [ ] `services/claude_export.py` -- Add logger, log ingest counts (INFO), missing files (WARNING)
- [ ] `services/claude_import.py` -- Add logger, log summary (INFO), per-conversation (DEBUG)
- [ ] `services/embedding.py` -- Add logger, log model load event (INFO)
- [ ] `services/vector_store.py` -- Add logger, log collection creation (INFO), connection failure (WARNING)
- [ ] `services/bulk_embed.py` -- Add logger, log embed progress (INFO)
- [ ] `db/operations.py` -- Add logger, log backup/restore failures (WARNING)
- [ ] `tabs/tab_database.py` -- New Accordion "Application Logs" with level filter dropdown, module filter, DataFrame display, refresh button

---

## Phase R2: Shared Constants and Utilities

**Why:** Eliminates duplicate enum lists and formatting functions across 5+ files.

- [ ] Create `shared/__init__.py`
- [ ] Create `shared/constants.py` (~60 lines)
  - [ ] Move DOMAINS, ALL_TYPES, STATUSES, TASK_STATUSES, TASK_TYPES, ASSIGNEES, PRIORITIES, DOC_TYPES, DOC_SOURCES, PROJECT_TYPES from `pages/projects.py`
  - [ ] Add `MAX_TOOL_ITERATIONS = 10` (currently hardcoded 3x in chat.py)
  - [ ] Add `RAG_SCORE_THRESHOLD = 0.3` (currently hardcoded in chat.py)
  - [ ] Add `DEFAULT_CHAT_HISTORY` (currently hardcoded in projects.py)
- [ ] Create `shared/formatting.py` (~30 lines)
  - [ ] `fmt_enum(value)` -- replaces 4 copies of `_fmt()`/`_format_display()` across projects.py and tab files
  - [ ] `entity_list_to_df(entities, columns)` -- generic DataFrame builder replacing 4 nearly identical `_*_df()` functions
- [ ] `pages/projects.py` -- Import from `shared.constants` and `shared.formatting`, remove local copies
- [ ] `services/chat.py` -- Replace `max_iterations = 10` (lines 331, 402, 462) with `MAX_TOOL_ITERATIONS`, replace `> 0.3` with `RAG_SCORE_THRESHOLD`

---

## Phase R3: Settings Architecture

**Why:** No validation on settings, base64 decode silently corrupts, DEFAULTS dict mixes concerns.

- [ ] `services/settings.py` -- Rename `DEFAULTS` to `SETTINGS_REGISTRY` with expanded schema: `(default, is_secret, category, validator_fn)`
  - [ ] Categories: `"chat"`, `"ollama"`, `"export"`, `"ingestion"`, `"system"`, `"rag"`
  - [ ] Add validators: `chat_provider` must be in (anthropic, gemini, ollama), `ollama_num_ctx` must be digit, etc.
  - [ ] New settings: `log_level` (system), `log_retention_days` (system), `rag_score_threshold` (rag), `rag_max_chunks` (rag)
  - [ ] `set_setting()` -- validate before storing, return error string on invalid input
  - [ ] `_decode()` -- log WARNING on base64 failure instead of silent return
  - [ ] New: `get_settings_by_category(category) -> dict`
  - [ ] Backward compatible: `get_setting()`/`set_setting()` signatures unchanged
- [ ] `services/chat.py` -- Use `get_setting("rag_score_threshold")` instead of hardcoded 0.3

---

## Phase R4: Chat Service DRY Refactor

**Why:** 3 provider functions (`_chat_anthropic`, `_chat_gemini`, `_chat_ollama`) share ~200 lines of structurally identical logic.

- [ ] `services/chat.py` -- Extract shared helper: `_build_api_messages(history, format)` -- converts internal history to provider-specific format (currently duplicated 3 ways)
- [ ] `services/chat.py` -- Extract shared helper: `_run_tool_loop(api_call_fn, history, max_iterations)` -- the iteration + tool-call detection + `_execute_tool()` + status message pattern
- [ ] `services/chat.py` -- Replace 3x `max_iterations = 10` with import from `shared.constants`
- [ ] `services/chat.py` -- Add structured logging at key points (provider selection, tool execution, errors)
- [ ] Verify: Chat works with all 3 providers, tool use works, reasoning extraction (`<think>` blocks) still works, Ollama no-tools fallback still works

---

## Phase R5: Docstring Standardization and Error Handling

**Why:** Docstrings range from excellent (db/operations.py) to nonexistent. Error handling has 5 inconsistent patterns.

### Part A: Docstrings (Google-style, matching db/operations.py quality)

- [ ] `services/chat.py` -- All provider functions, `_build_rag_context`, `_build_system_prompt`, `chat()`
- [ ] `services/settings.py` -- All functions including validators
- [ ] `services/claude_export.py` -- All 6 functions
- [ ] `services/claude_import.py` -- All 5 functions
- [ ] `services/vector_store.py` -- Add Returns types
- [ ] `services/bulk_embed.py` -- Standardize format
- [ ] `tabs/tab_database.py` -- Inner `_handle_*` functions
- [ ] `pages/projects.py` -- `_load_*`, `_handle_*` helper functions

### Part B: Custom Exceptions and Error Handling

- [ ] Create `shared/exceptions.py` (~30 lines)
  - [ ] `JANATPMPError(Exception)` -- base
  - [ ] `SettingsError` -- invalid settings or configuration
  - [ ] `ProviderError` -- chat provider communication failure
  - [ ] `IngestionError` -- content ingestion failure
  - [ ] `VectorStoreError` -- Qdrant communication failure
- [ ] Replace `except Exception: return ""` patterns with log + return default
- [ ] Remove 80-char error truncation in `services/ingestion/orchestrator.py` and `services/claude_import.py` -- store full text, truncate only in UI display layer
- [ ] Ollama retry pattern: keep, but log INFO when falling back to no-tools mode
- [ ] Verify: MCP tool descriptions still generate correctly at `/gradio_api/docs`

---

## Phase R6: projects.py Decomposition

**Why:** 1,667-line monolith. Extract ~500 lines into focused modules.

### Extract new tab modules

- [ ] Create `tabs/tab_chat.py` (~150 lines) -- Chat tab wiring functions (`_handle_chat_tab`, `_handle_chat`, related helpers) extracted from projects.py
- [ ] Create `tabs/tab_knowledge.py` (~160 lines) -- Knowledge sub-tab conversation handlers (`_load_conv_stats`, `_load_conv_list`, `_load_selected_conversation`, `_run_ingest`, `_run_import`, `_open_in_chat`, `_delete_knowledge_conv`)
- [ ] Create `shared/data_helpers.py` (~100 lines) -- `_load_projects()`, `_all_items_df()`, `_load_tasks()`, `_all_tasks_df()`, `_load_documents()`, `_all_docs_df()`, `_msgs_to_history()`, `_load_most_recent_chat()`

### Update main UI file

- [ ] `pages/projects.py` -- Import wiring functions from new tab modules, reduce from ~1,667 to ~1,100 lines. `build_page()` remains the orchestrator.

### Archive dead prototype files (never imported in live code)

- [ ] `tabs/tab_items.py` -> `completed/archived_tab_items.py`
- [ ] `tabs/tab_tasks.py` -> `completed/archived_tab_tasks.py`
- [ ] `tabs/tab_documents.py` -> `completed/archived_tab_documents.py`

### Verification

- [ ] All 5 tabs render and function (Projects, Work, Knowledge, Chat, Admin)
- [ ] Chat: send message, conversation creates, persists, loads from sidebar
- [ ] Knowledge > Conversations: select, preview, "Open in Chat" works
- [ ] Sidebar context switching works on all tabs
- [ ] Right sidebar visibility toggles on Chat vs other tabs

---

## Phase R7: Schema Fixes and Cleanup

**Why:** Correctness and forward-compatibility.

- [ ] Create `db/migrations/0.4.1_messages_fts_update.sql` -- Add missing FTS UPDATE trigger on messages table (currently only INSERT/DELETE triggers exist -- edits don't sync to FTS)
- [ ] `db/operations.py` -- Add `cleanup_cdc_outbox(days=90)` function, call on startup after `init_database()`
- [ ] `services/vector_store.py` -- Make Qdrant URL configurable via settings + env var override: `os.environ.get("QDRANT_URL", get_setting("qdrant_url"))`. Add `qdrant_url` to settings registry.
- [ ] `CLAUDE.md` -- Document `shared/` module, logging architecture, settings registry, custom exceptions, updated project structure

---

## Risk Notes

| Phase | Risk | Mitigation |
|-------|------|-----------|
| R1 Logging | LOW | Additive only, no logic changes |
| R2 Constants | LOW | Moving constants, verify dropdowns populate |
| R3 Settings | MEDIUM | Test backward compat: existing DB settings still load |
| R4 Chat DRY | MEDIUM | Test all 3 providers, tool use, reasoning extraction |
| R5 Docs/Errors | LOW | Docstrings + exceptions don't change behavior |
| R6 UI Decomposition | HIGH | Test every tab, sidebar, cross-component interaction |
| R7 Schema | LOW | Additive migration, verify FTS works on existing DB |

## Verification (every phase)

1. `docker compose down && docker compose up -d --build` -- app starts clean
2. All 5 tabs render and function
3. Chat works with Ollama
4. 36 MCP tools accessible at `/gradio_api/docs`
5. Admin > Application Logs shows entries (after R1)
