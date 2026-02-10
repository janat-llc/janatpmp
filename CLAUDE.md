# CLAUDE.md - Project Guidelines for AI Assistants

## Project Overview

**JANATPMP (Janat Project Management Platform)** is a Gradio-based project management
platform designed for solo architects and engineers working with AI partners. It provides
persistent project state that AI assistants can read and write via MCP (Model Context Protocol).

**Status:** Phase 2.5 — settings persistence, system prompt editor, auto-context injection
**Origin:** Anthropic "Built with Opus 4.6" Claude Code competition (Feb 2026)
**Goal:** Strategic command center for consciousness architecture work across multiple domains.

## Tech Stack

- **Python** 3.14+
- **Gradio** 6.5.1 with MCP support (`gradio[mcp]==6.5.1`)
- **SQLite3** for persistence (WAL mode, FTS5 full-text search)
- **Pandas** for data display

## Project Structure

```
JANATPMP/
├── app.py                    # Thin orchestrator: init_database(), build_page(), gr.api(), launch
├── pages/
│   ├── __init__.py
│   └── projects.py           # ALL UI lives here: build_page() function
├── tabs/
│   ├── __init__.py
│   └── tab_database.py       # Database/Admin tab builder (imported by projects.py)
├── db/
│   ├── schema.sql            # Database schema DDL (NO seed data)
│   ├── seed_data.sql         # Optional seed data (separate from schema)
│   ├── operations.py         # All CRUD + lifecycle functions (22 operations)
│   ├── test_operations.py    # Tests
│   ├── janatpmp.db           # SQLite database (runtime, gitignored)
│   ├── backups/              # Timestamped database backups
│   └── __init__.py
├── services/
│   ├── __init__.py
│   ├── chat.py               # Multi-provider chat with tool use (Anthropic/Gemini/Ollama)
│   └── settings.py           # Settings service: get/set with base64 for secrets
├── docs/
│   └── janatpmp-mockup.png   # Visual reference for Projects page layout
├── completed/                # Archived TODO files
├── screenshots/              # UI screenshots for reference
├── requirements.txt          # Python dependencies (pinned)
├── pyproject.toml            # Project metadata
├── Dockerfile                # Container image (Python 3.14-slim)
├── docker-compose.yml        # Container orchestration (port 7860, volume mount)
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
┌──────────────────────────────────────────────────────────────┐
│  [Projects]  [Work]  [Knowledge]  [Admin]    ← gr.Tabs()    │
├──────────┬──────────────────────────────┬────────────────────┤
│  LEFT    │     CENTER CONTENT           │  RIGHT             │
│  SIDEBAR │                              │  SIDEBAR           │
│          │  Content changes per tab     │                    │
│  Project │  selected. Each top-level    │  Claude Chat       │
│  cards   │  tab can have sub-tabs       │  (MCP placeholder) │
│  Filters │  (Detail/List View, etc.)    │                    │
│  +New    │                              │                    │
└──────────┴──────────────────────────────┴────────────────────┘
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
        build_database_tab()  # "Database" tab from tabs/tab_database.py
```

**Use `gr.Sidebar` for both side panels — NOT `gr.Column` in a `gr.Row`.**
Sidebar is collapsible, mobile-friendly, and purpose-built for this layout.
The center content is just the main Blocks body (no Row/Column wrapper needed).

### Four Tabs (current state)

| Tab | Left Sidebar | Center | Status |
|-----|-------------|--------|--------|
| **Projects** | Project cards, filters, + New | Detail editor, List View | ✅ Working |
| **Work** | Task cards, filters, + New Task | Task detail, List View | ✅ Working |
| **Knowledge** | Placeholder | Placeholder | Stub only |
| **Admin** | Quick Settings (provider/model/key) | System Prompt editor, Stats, Backup/Restore | ✅ Working |

### Contextual Left Sidebar

The left sidebar uses `@gr.render(inputs=[active_tab, projects_state, tasks_state])`
to dynamically switch content based on the active tab. The right sidebar (Claude chat)
stays constant regardless of active tab.

### Settings & Chat Architecture

**Settings table** (`settings` in SQLite) — key-value store for persistent configuration:
- `chat_provider` — "anthropic", "gemini", or "ollama"
- `chat_model` — Model identifier string
- `chat_api_key` — Base64-encoded API key (obfuscation, NOT encryption)
- `chat_base_url` — Override URL for Ollama
- `chat_system_prompt` — Custom system prompt (empty = use default)

**Settings flow:**
- `services/settings.py` provides `get_setting()` / `set_setting()` with auto base64 for secrets
- Admin sidebar quick-settings save on change (no save button needed)
- Chat reads settings from DB on each message — no restart needed
- `init_database()` calls `init_settings()` to seed defaults on first run

**Chat auto-context injection:**
- `db/operations.py:get_context_snapshot()` builds a summary of active items + pending tasks
- `services/chat.py:_build_system_prompt()` composes: default prompt + custom prompt + auto-context
- Fresh context is injected per message, so the AI always knows current project state

### Data Flow

```
db/operations.py → 22 functions → three surfaces:
    1. UI: imported by pages/projects.py, called in event listeners
    2. API: exposed via gr.api() in app.py
    3. MCP: auto-generated from gr.api() + docstrings
```

**Key principles:**

- One set of functions in `db/operations.py` serves UI, API, and MCP
- NO `demo.load()` — data is computed at build time and passed via `value=`
- `gr.api()` exposes db functions as MCP tools without UI components
- `build_page()` is the single entry point for all UI construction

## Database Schema (db/schema.sql)

**Core Tables:**
- `items` — Projects, features, books, etc. across domains. Supports hierarchy via parent_id.
  Has JSON attributes for domain-specific data. FTS5 full-text search enabled.
- `tasks` — Work queue with agent/human assignment. Supports retry logic, dependencies,
  acceptance criteria, cost tracking.
- `documents` — Conversations, files, artifacts, research. FTS5 enabled.
- `relationships` — Universal connector between any two entities. Typed relationships
  (blocks, enables, informs, etc.) with hard/soft strength.
- `settings` — Key-value application configuration. Base64 for secrets. Auto-updated timestamps.
- `cdc_outbox` — Change Data Capture for future Qdrant/Neo4j sync.
- `schema_version` — Migration tracking.

**Domain enum values:** literature, janatpmp, janat, atlas, meax, janatavern,
amphitheatre, nexusweaver, websites, social, speaking, life

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

- **Image:** Python 3.14-slim
- **Port:** 7860
- **Volume:** `.:/app` for live code changes without rebuild
- **MCP:** Enabled via `GRADIO_MCP_SERVER=True` environment variable
- **CMD:** `gradio app.py` (uses Gradio's built-in server)

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

All 22 functions in `db/operations.py` are exposed via `gr.api()`. They MUST have
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

## Future Architecture (not in scope, for context only)

JANATPMP will eventually become a **Nexus Custom Component** within The Nexus Weaver
architecture. Future integrations include Qdrant (vector search) and Neo4j (graph database)
forming a "Triad of Memory" (SQL + Vector + Graph). The CDC outbox table in the schema
provides forward-compatibility for this evolution.
