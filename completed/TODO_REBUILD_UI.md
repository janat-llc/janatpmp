# TODO: JANATPMP UI Rebuild — Clean Gradio Architecture

**Date:** 2026-02-08
**Context:** Sprint 1 produced a working DB layer but a broken UI architecture (demo-pattern monolith with manual refresh wiring). We're deconstructing and rebuilding the UI as a thin client over `db/operations.py`.

**Philosophy:** `db/operations.py` IS the product. The UI is one client. MCP is another. Both call the same functions. The UI should be the thinnest possible Gradio layer.

---

## WHAT TO KEEP (DO NOT MODIFY)

- `db/schema.sql` — Production-ready schema (items, tasks, documents, relationships, CDC outbox, FTS)
- `db/operations.py` — Well-typed CRUD functions with MCP-ready docstrings
- `db/__init__.py`
- `CLAUDE.md` — Contains authoritative Gradio patterns (update file list section after rebuild)
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- `.gitignore`, `requirements.txt`, `pyproject.toml`
- `completed/` directory (historical TODO archive)

## WHAT TO DELETE

- `api.py` — Redundant; Gradio's MCP server replaces this
- `database.py` — Redundant with `db/operations.py`
- `features/inventory/` — Premature; not needed for core PM
- `janatpmp.db` in root — Stale duplicate (DB lives at `db/janatpmp.db`)
- `nul` — Artifact
- `app_output.txt` — Debug artifact
- `__pycache__/` in root — Stale
- `.tmp.drivedownload/`, `.tmp.driveupload/` — Google Drive sync artifacts
- `TODO_004_Database_Operations.md` — Completed work
- `TODO_HACKATHON_SPRINT_1.md` — Completed work  
- `TODO_SPRINT1_BUGFIX.md` — Superseded by this rebuild

## WHAT TO BUILD

### File Structure After Rebuild

```
JANATPMP/
├── app.py                  # Entry point — ~30 lines
├── db/
│   ├── __init__.py
│   ├── schema.sql          # (existing, untouched)
│   ├── operations.py       # (existing, + init_database addition)
│   └── backups/
├── tabs/
│   ├── __init__.py         # Exports all build_*_tab functions
│   ├── tab_items.py        # Items tab UI
│   ├── tab_tasks.py        # Tasks tab UI
│   ├── tab_documents.py    # Documents tab UI
│   └── tab_database.py     # Database lifecycle tab UI
├── CLAUDE.md
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── Janat_Brand_Guide.md
├── completed/
└── screenshots/
```

---

### 1. Add `init_database()` to `db/operations.py`

**WHY:** Cold start with no DB file creates empty SQLite but no tables.

Add this function BEFORE the existing CRUD functions:

```python
def init_database():
    """Initialize database schema if tables don't exist.
    Safe to call multiple times — checks before creating.
    Called at module import time."""
    schema_path = Path(__file__).parent / "schema.sql"
    with get_connection() as conn:
        # Check if schema already exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
        )
        if cursor.fetchone() is not None:
            return  # Already initialized
        
        # Run schema
        schema_sql = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema_sql)

# Initialize on import
init_database()
```

**CONSTRAINT:** Add at module level, AFTER `DB_PATH` and `get_connection()` definitions, BEFORE any CRUD functions. The `init_database()` call happens on import.

---

### 2. Create `tabs/__init__.py`

```python
"""Tab modules for JANATPMP Gradio UI."""
from .tab_items import build_items_tab
from .tab_tasks import build_tasks_tab
from .tab_documents import build_documents_tab
from .tab_database import build_database_tab
```

---

### 3. Create `tabs/tab_items.py`

**Pattern:** Each tab function returns the components needed for `demo.load()`.

```python
"""Items tab — Browse, filter, and create work items."""
import gradio as gr
import pandas as pd
from db.operations import list_items, create_item


def _format_display(value: str) -> str:
    """Convert enum values like 'social_campaign' to 'Social Campaign'."""
    return value.replace("_", " ").title() if value else ""


def _items_to_df(domain="", status="") -> pd.DataFrame:
    """Fetch items and return as display DataFrame."""
    items = list_items(domain=domain, status=status, limit=100)
    if not items:
        return pd.DataFrame(columns=["ID", "Title", "Domain", "Type", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": item['id'][:8] + "…",
        "Title": item['title'],
        "Domain": _format_display(item['domain']),
        "Type": _format_display(item['entity_type']),
        "Status": _format_display(item['status']),
        "Priority": item['priority']
    } for item in items])


def _handle_create(entity_type, domain, title, description, status, priority, parent_id):
    """Create item, return status message + refreshed table."""
    if not title.strip():
        return "⚠️ Title is required", _items_to_df()
    item_id = create_item(
        entity_type=entity_type, domain=domain,
        title=title.strip(),
        description=description.strip() if description else "",
        status=status, priority=int(priority),
        parent_id=parent_id.strip() if parent_id else ""
    )
    return f"✅ Created: {item_id[:8]}…", _items_to_df()


def build_items_tab():
    """Build the Items tab. Returns items_table component for demo.load()."""
    with gr.Tab("Items"):
        with gr.Row():
            # Left: Table with filters
            with gr.Column(scale=2):
                gr.Markdown("### 📦 Items")
                with gr.Row():
                    domain_filter = gr.Dropdown(
                        label="Domain",
                        choices=["", "literature", "janatpmp", "janat", "atlas", "meax",
                                 "janatavern", "amphitheatre", "nexusweaver", "websites",
                                 "social", "speaking", "life"],
                        value=""
                    )
                    status_filter = gr.Dropdown(
                        label="Status",
                        choices=["", "not_started", "planning", "in_progress", "blocked",
                                 "review", "completed", "shipped", "archived"],
                        value=""
                    )
                    filter_btn = gr.Button("Filter", variant="primary", size="sm")

                items_table = gr.DataFrame(
                    headers=["ID", "Title", "Domain", "Type", "Status", "Priority"],
                    interactive=False
                )

            # Right: Create form
            with gr.Column(scale=1):
                gr.Markdown("### ➕ Create Item")
                entity_type = gr.Dropdown(
                    label="Type",
                    choices=["project", "epic", "feature", "component", "milestone",
                             "book", "chapter", "section",
                             "website", "page", "deployment",
                             "social_campaign", "speaking_event", "life_area"],
                    value="project"
                )
                domain = gr.Dropdown(
                    label="Domain",
                    choices=["literature", "janatpmp", "janat", "atlas", "meax",
                             "janatavern", "amphitheatre", "nexusweaver", "websites",
                             "social", "speaking", "life"],
                    value="janatpmp"
                )
                title = gr.Textbox(label="Title", placeholder="Item title…")
                description = gr.Textbox(label="Description", lines=3, placeholder="Optional…")
                status = gr.Dropdown(
                    label="Status",
                    choices=["not_started", "planning", "in_progress", "blocked",
                             "review", "completed", "shipped", "archived"],
                    value="not_started"
                )
                priority = gr.Slider(label="Priority", minimum=1, maximum=5, step=1, value=3)
                parent_id = gr.Textbox(label="Parent ID", placeholder="Optional parent…")
                create_btn = gr.Button("Create Item", variant="primary")
                status_msg = gr.Textbox(label="Status", interactive=False)

        # Wiring — all outputs stay within this tab
        filter_btn.click(_items_to_df, inputs=[domain_filter, status_filter], outputs=[items_table])
        create_btn.click(
            _handle_create,
            inputs=[entity_type, domain, title, description, status, priority, parent_id],
            outputs=[status_msg, items_table]
        )

    return items_table  # For demo.load() initialization
```

---

### 4. Create `tabs/tab_tasks.py`

**Same pattern as tab_items.py but for tasks.**

- `_tasks_to_df(status="", assigned="")` → DataFrame
- `_handle_create_task(...)` → status msg + refreshed table
- `build_tasks_tab()` → returns `tasks_table`
- Filters: Status, Assigned To
- Create form: type, title, description, assigned_to, target_item_id, priority, agent_instructions

---

### 5. Create `tabs/tab_documents.py`

**Same pattern for documents.**

- `_docs_to_df(doc_type="", source="")` → DataFrame
- `_handle_create_doc(...)` → status msg + refreshed table
- `build_documents_tab()` → returns `docs_table`
- Filters: Type, Source
- Create form: type, source, title, content

---

### 6. Create `tabs/tab_database.py`

**Database lifecycle: stats, schema, backup, restore, reset.**

- `_load_schema()` → formatted JSON string
- `_load_stats()` → dict for gr.JSON
- `_backups_to_df()` → DataFrame
- `_handle_backup()` → status + backup table + dropdown update
- `_handle_restore(name)` → status + all refreshed outputs
- `_handle_reset()` → status + all refreshed outputs
- `build_database_tab()` → returns `(stats_display, schema_display, backups_table, restore_dropdown)`

**NOTE on reset/restore:** These operations DO need to refresh the items/tasks/docs tables too. The cleanest way: reset/restore return just their own tab's outputs. The user clicks "Refresh" or re-filters on other tabs. This avoids cross-tab output wiring entirely.

**ALTERNATIVE (if cross-tab refresh is needed):** Pass the other tables into `build_database_tab()` as parameters. But start simple.

---

### 7. Rewrite `app.py` — Clean Entry Point

```python
"""JANATPMP — Janat Project Management Platform
Entry point. Thin Gradio shell over db/operations.py.
"""
import gradio as gr
from db.operations import get_stats
from tabs import build_items_tab, build_tasks_tab, build_documents_tab, build_database_tab


def create_app():
    with gr.Blocks(title="JANATPMP", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🏗️ JANATPMP v0.3")

        with gr.Tabs():
            items_table = build_items_tab()
            tasks_table = build_tasks_tab()
            docs_table = build_documents_tab()
            db_components = build_database_tab()

        # Single demo.load() — populate all tabs on startup
        def load_all():
            from tabs.tab_items import _items_to_df
            from tabs.tab_tasks import _tasks_to_df
            from tabs.tab_documents import _docs_to_df
            from tabs.tab_database import _load_stats, _load_schema, _backups_to_df, _backup_names
            return (
                _items_to_df(),
                _tasks_to_df(),
                _docs_to_df(),
                _load_stats(),
                _load_schema(),
                _backups_to_df(),
                gr.Dropdown(choices=_backup_names())
            )

        demo.load(
            load_all,
            outputs=[
                items_table, tasks_table, docs_table,
                db_components['stats'], db_components['schema'],
                db_components['backups_table'], db_components['restore_dropdown']
            ]
        )

    return demo


if __name__ == "__main__":
    app = create_app()
    app.launch(mcp_server=True)
```

---

## VERIFICATION

After implementation, verify in this order:

1. **Cold start:** Delete `db/janatpmp.db`, run `python app.py`. Should create DB with schema automatically.
2. **Empty state:** All tabs load with empty tables, no errors, no timeouts.
3. **Create item:** Fill form → click Create → table refreshes with new row.
4. **Create task:** Same flow.
5. **Create document:** Same flow.
6. **Filter:** Domain/status filters work on Items tab.
7. **Database tab:** Stats show correct counts, schema displays, backup creates file.
8. **Reset:** Clears data, Database tab refreshes properly.
9. **MCP:** Connect an MCP client. `create_item`, `list_items`, `get_stats` etc. should appear as tools.
10. **Display formatting:** Domain/type/status values show as "Social Campaign" not "social_campaign".

## NOTES FOR AGENT

- **Gradio version:** 6.5.1 — check `gr.Blocks()` API, no breaking changes from 6.0.2 patterns
- **Python version:** 3.14
- **DO NOT** add multiple `demo.load()` calls. ONE ONLY in app.py.
- **DO NOT** wire cross-tab refresh (items_table as output of Database tab buttons). Start simple.
- **DO NOT** create `@gr.render()` reactive patterns yet. Standard Blocks event wiring is correct for CRUD forms. Reactive rendering is for dynamic lists/cards — future sprint.
- **DO** use `_format_display()` helper in every tab for enum→display conversion.
- **DO** use emoji in Markdown headers for visual scanning.
- Keep each tab file under 150 lines.
- The `db/operations.py` functions are the MCP tools. Their docstrings and type hints are what Gradio exposes. Do not wrap them.
