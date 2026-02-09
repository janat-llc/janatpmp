# TODO: app.py v1.0 — Correct Gradio Blocks Architecture

**Author:** Claude (The Weavers)  
**Date:** 2026-02-08  
**Priority:** CRITICAL — app currently hangs 30+ seconds on page load  
**Estimated Effort:** Small — mostly deletion and minor edits  

## Root Cause

The app hangs because the old app.py used 7 `demo.load()` calls to populate UI
components after page load. Each was a separate async callback hitting the database,
causing race conditions and 30+ second spinners.

v0.5 (current app.py) attempted to fix this by inlining ALL database logic into a
single 300-line file, duplicating everything already in `db/operations.py` and `tabs/`.

## The Fix

The `tabs/` directory already contains well-structured modular tab builders that import
from `db/operations.py`. They just need one small change: populate DataFrames with
`value=` at build time instead of leaving them empty for `demo.load()` to fill.

Then app.py becomes a thin orchestrator: init DB, build tabs, wire MCP, launch.

## Architecture

```
db/operations.py      ← All CRUD + lifecycle (KEEP AS-IS, already correct)
db/schema.sql         ← DDL (KEEP AS-IS)
tabs/tab_items.py     ← Items tab builder (MINOR EDIT)
tabs/tab_tasks.py     ← Tasks tab builder (MINOR EDIT)
tabs/tab_documents.py ← Documents tab builder (MINOR EDIT)
tabs/tab_database.py  ← Database tab builder (MINOR EDIT)
tabs/__init__.py      ← Re-exports (KEEP AS-IS)
app.py                ← Thin orchestrator (REWRITE — much smaller)
```

Files to DELETE:
- `api.py` — Gradio exposes functions natively via gr.api(), no wrapper needed
- `database.py` — Deprecated, everything is in db/operations.py

---

## Task 1: Fix tab builders — add `value=` to DataFrames

Each tab builder creates DataFrames with `headers=` but no `value=`, so they render
empty. Fix: call the query function at build time.

### tabs/tab_items.py

Change the DataFrame creation from:
```python
items_table = gr.DataFrame(
    headers=["ID", "Title", "Domain", "Type", "Status", "Priority"],
    interactive=False
)
```
To:
```python
items_table = gr.DataFrame(
    value=_items_to_df(),
    interactive=False
)
```

The `_items_to_df()` function already exists in the file and returns a properly
formatted DataFrame with those exact column headers. No other changes needed.

### tabs/tab_tasks.py

Same pattern. Change:
```python
tasks_table = gr.DataFrame(
    headers=["ID", "Title", "Type", "Assigned", "Status", "Priority"],
    interactive=False
)
```
To:
```python
tasks_table = gr.DataFrame(
    value=_tasks_to_df(),
    interactive=False
)
```

### tabs/tab_documents.py

Same pattern. Change:
```python
docs_table = gr.DataFrame(
    headers=["ID", "Title", "Type", "Source", "Created"],
    interactive=False
)
```
To:
```python
docs_table = gr.DataFrame(
    value=_docs_to_df(),
    interactive=False
)
```

### tabs/tab_database.py

This tab has 4 components that need initial values:

```python
stats_display = gr.JSON(label="Stats")
```
→
```python
stats_display = gr.JSON(value=_load_stats(), label="Stats")
```

```python
schema_display = gr.Code(label="Schema", language="json", interactive=False)
```
→
```python
schema_display = gr.Code(value=_load_schema(), label="Schema", language="json", interactive=False)
```

```python
backups_table = gr.DataFrame(
    headers=["Name", "Size (KB)", "Created"],
    interactive=False, label="Available Backups"
)
```
→
```python
backups_table = gr.DataFrame(
    value=_backups_to_df(),
    interactive=False, label="Available Backups"
)
```

```python
restore_dropdown = gr.Dropdown(
    label="Select Backup", choices=[], allow_custom_value=True
)
```
→
```python
restore_dropdown = gr.Dropdown(
    label="Select Backup", choices=_backup_names(), allow_custom_value=True
)
```

---

## Task 2: Rewrite app.py as thin orchestrator

Replace the current 300-line app.py with this structure. The file should be
approximately 60-80 lines.

```python
"""JANATPMP v1.0 — Gradio Blocks application."""

import gradio as gr
from db.operations import (
    init_database,
    # MCP-only operations (no UI component, exposed via gr.api)
    get_item, update_item, delete_item,
    get_task, update_task,
    get_document,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats, get_schema_info,
)
from tabs import build_items_tab, build_tasks_tab, build_documents_tab, build_database_tab

# Initialize database BEFORE building UI
init_database()

# Build the application
with gr.Blocks(title="JANATPMP", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# JANATPMP")

    with gr.Tabs():
        items_table = build_items_tab()
        tasks_table = build_tasks_tab()
        docs_table = build_documents_tab()
        db_components = build_database_tab()

    # Expose operations as MCP tools (no UI needed)
    gr.api(get_item)
    gr.api(update_item)
    gr.api(delete_item)
    gr.api(get_task)
    gr.api(update_task)
    gr.api(get_document)
    gr.api(search_items)
    gr.api(search_documents)
    gr.api(create_relationship)
    gr.api(get_relationships)
    gr.api(get_stats)
    gr.api(get_schema_info)

if __name__ == "__main__":
    demo.launch(mcp_server=True)
```

Key points:
- NO `demo.load()` anywhere
- Tabs build themselves with data already baked in via `value=`
- `gr.api()` exposes db/operations.py functions as API/MCP tools directly
- Total file is ~50 lines

---

## Task 3: Delete deprecated files

- Delete `api.py` (gr.api() replaces it)
- Delete `database.py` (db/operations.py is the canonical source)

---

## Task 4: Update CLAUDE.md

Update the following sections in CLAUDE.md:

1. **Project Structure**: Remove api.py and database.py entries
2. **Architecture diagram**: Simplify to show tabs/ → db/operations.py → SQLite
3. **Status**: Change to `v1.0`
4. Remove references to `demo.load()` pattern in the guidelines section (the correct
   pattern is now `value=` at build time)

---

## Task 5: Test

After all changes, run the app and verify:

```bash
cd C:\Janat\JANATPMP
python app.py
```

Expected behavior:
1. App starts and prints DB ready message
2. Browser opens to http://localhost:7860
3. Page loads INSTANTLY (no spinners, no 30-second wait)
4. Items tab shows empty table (or existing data if DB has records)
5. Create an item → table updates immediately
6. Filter items → table updates with filtered results
7. Switch to Tasks tab → data is already loaded
8. Switch to Database tab → stats and schema are already displayed
9. Reset Database → all tabs reflect empty state
10. Backup/Restore → works without page refresh

MCP verification:
- Navigate to http://localhost:7860/gradio_api/mcp/sse
- Verify tools are listed (get_item, update_item, search_items, etc.)

---

## What This Does NOT Change

- `db/operations.py` — No changes. Already correct.
- `db/schema.sql` — No changes.
- `tabs/__init__.py` — No changes.
- Docker configuration — No changes.
- `requirements.txt` — No changes.

## What This Achieves

1. **Instant page load** — Data computed at build time, no async callbacks
2. **Modular architecture** — Each tab is its own module, easy to extend
3. **MCP exposure** — All 12 operations available as MCP tools
4. **No code duplication** — Single source of truth in db/operations.py
5. **~50 line app.py** — Thin orchestrator, easy to understand
