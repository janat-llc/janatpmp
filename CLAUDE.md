# CLAUDE.md - Project Guidelines for AI Assistants

## Project Overview

**JANATPMP (Janat Project Management Platform)** is a Gradio-based project management
platform designed for solo architects and engineers working with AI partners. It provides
persistent project state that AI assistants can read and write via MCP (Model Context Protocol).

**Status:** v1.0 operational, Phase 1 multi-page upgrade in progress
**Origin:** Anthropic "Built with Opus 4.6" Claude Code competition (Feb 2026)
**Goal:** Strategic command center for consciousness architecture work across multiple domains.

## Tech Stack

- **Python** 3.14+
- **Gradio** 6.5.1 with MCP support (`gradio[mcp]==6.5.1`)
- **SQLite3** for persistence (WAL mode, FTS5 full-text search)
- **Pandas** for data display

## Current Sprint: TODO_PHASE1_MULTIPAGE.md

Read this file first. It contains the complete specification for the current work.
Also see `docs/janatpmp-mockup.png` for the visual target of the Projects page layout.

## Project Structure

```
JANATPMP/
├── app.py                    # Multi-page orchestrator: routes, navbar, MCP exposure
├── pages/                    # Multi-page modules (each independently runnable)
│   ├── __init__.py
│   ├── projects.py           # Three-panel Projects page (Phase 1)
│   └── database.py           # Database management page (Phase 1)
├── tabs/                     # LEGACY tab builders (still imported by pages)
│   ├── __init__.py           # Re-exports build_*_tab functions
│   ├── tab_items.py          # Items tab builder
│   ├── tab_tasks.py          # Tasks tab builder (future: Work page)
│   ├── tab_documents.py      # Documents tab builder (future: Knowledge page)
│   └── tab_database.py       # Database tab builder (imported by pages/database.py)
├── db/
│   ├── schema.sql            # Database schema DDL (NO seed data)
│   ├── seed_data.sql         # Optional seed data (separate from schema)
│   ├── operations.py         # All CRUD + lifecycle functions (22 operations)
│   ├── test_operations.py    # Tests
│   ├── janatpmp.db           # SQLite database (runtime, gitignored)
│   ├── backups/              # Timestamped database backups
│   └── __init__.py
├── docs/
│   └── janatpmp-mockup.png   # Visual reference for Projects page layout
├── requirements.txt          # Python dependencies (pinned)
├── pyproject.toml            # Project metadata
├── Dockerfile                # Container image (Python 3.14-slim)
├── docker-compose.yml        # Container orchestration (port 7860, volume mount)
├── CLAUDE.md                 # This file
└── completed/                # Archived TODO files
```

## Architecture

### Multi-Page Structure (Phase 1+)

```
app.py (orchestrator)
    ├── init_database()
    ├── gr.Blocks() with gr.Navbar()
    │   ├── pages/projects.py  → main page (/)
    │   └── pages/database.py  → demo.route("Database", "/database")
    ├── gr.api() × 22          → MCP tool exposure
    └── demo.launch(mcp_server=True, server_name="0.0.0.0")
```

### Three-Panel Layout Pattern (all content pages)

```
┌──────────────┬──────────────────────────────┬──────────────┐
│  LEFT PANEL  │       CENTER PANEL           │ RIGHT PANEL  │
│  gr.Column   │       gr.Column              │ gr.Column    │
│  scale=1     │       scale=3                │ scale=1      │
│              │  [Tab1] [Tab2] [Tab3] [Tab4] │              │
│  Item list   │  ┌──────────────────────┐    │  Chat        │
│  Filters     │  │  Detail / List /     │    │  placeholder │
│  Create form │  │  Kanban / Query      │    │  (Phase 4)   │
│  (accordion) │  └──────────────────────┘    │              │
└──────────────┴──────────────────────────────┴──────────────┘
```

See `docs/janatpmp-mockup.png` for the visual target.

### Page Architecture Rules

- **Each page is a standalone `gr.Blocks()` app** — independently runnable via `__main__`
- **No cross-page event listeners** — each page is fully self-contained
- **Pages import from `db/operations.py`** for all data access
- **Pages may import from `tabs/`** to reuse existing tab builders
- **`app.py` renders pages** via `demo.route()` and `gr.Navbar`

### Data Flow

```
db/operations.py → 22 functions → three surfaces:
    1. UI: imported by pages/, called in event listeners
    2. API: exposed via gr.api() in app.py
    3. MCP: auto-generated from gr.api() + docstrings
```

**Key principles:**

- One set of functions in `db/operations.py` serves UI, API, and MCP
- NO `demo.load()` — data is computed at build time and passed via `value=`
- `gr.api()` exposes db functions as MCP tools without UI components
- Each page module is self-contained: imports from db/operations, builds its own UI

## Four Pages (planned)

| Page | Route | Status | Description |
|------|-------|--------|-------------|
| Projects | `/` (main) | Phase 1 | Three-panel: project list → detail editor → chat |
| Work | `/work` | Phase 2 | Task engine with Kanban board (columns by status) |
| Knowledge | `/knowledge` | Phase 3 | Document browser with FTS5 search |
| Database | `/database` | Phase 1 | Schema viewer, backups, lifecycle management |

## Database Schema (db/schema.sql)

**Core Tables:**
- `items` — Projects, features, books, etc. across domains. Supports hierarchy via parent_id.
  Has JSON attributes for domain-specific data. FTS5 full-text search enabled.
- `tasks` — Work queue with agent/human assignment. Supports retry logic, dependencies,
  acceptance criteria, cost tracking.
- `documents` — Conversations, files, artifacts, research. FTS5 enabled.
- `relationships` — Universal connector between any two entities. Typed relationships
  (blocks, enables, informs, etc.) with hard/soft strength.
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
# Accessible from other devices on LAN (mobile, etc.)

# Test individual pages
python pages/projects.py     # Projects page standalone
python pages/database.py     # Database page standalone

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
- **Each page independently runnable** — include `if __name__ == "__main__": demo.launch()`
- **No `demo.load()` anywhere** — bake initial data via `value=` parameter
- **Display formatting** — enum values like `not_started` display as `Not Started` in UI only,
  never modify database values. Use: `value.replace("_", " ").title()`

### Mobile Considerations
- App is accessed from both desktop and phone (same WiFi network)
- Gradio's Row/Column layout wraps naturally on narrow screens
- Three panels stack vertically on mobile (left → center → right) — acceptable for now
- Avoid `size="sm"` on critical touch targets
- Phase 4 will upgrade left panel to `gr.Sidebar()` for better mobile UX

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

### Multi-Page Routing

Gradio 6.5.1 supports multi-page apps with URL-based routing:

```python
import pages.projects
import pages.database

with gr.Blocks(title="JANATPMP") as demo:
    gr.Navbar(main_page_name="Projects")
    pages.projects.demo.render()

with demo.route("Database", "/database"):
    pages.database.demo.render()

demo.launch(mcp_server=True, server_name="0.0.0.0")
```

**Key constraints:**
- No cross-page event listeners — each page's Blocks context is isolated
- `gr.api()` calls may need to be inside or outside the `with gr.Blocks()` context —
  test both placements if errors occur
- Each page defines its own `with gr.Blocks() as demo:` and is independently testable

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
    # ... UI components ...
    gr.api(create_item)  # Becomes MCP tool, no UI element

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
| Cross-page event listeners | Not supported — keep each page self-contained |
| Using `demo.load()` for page init | Use `value=` parameter on components instead |

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
