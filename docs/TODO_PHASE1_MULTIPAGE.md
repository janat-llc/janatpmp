# TODO: Phase 1 — Multi-Page Architecture + Projects Page

**Created:** 2026-02-09
**Author:** Claude (The Weavers)
**Executor:** Claude Code
**Status:** READY FOR EXECUTION

---

## CONTEXT

JANATPMP v1.0 works: instant load, 22 MCP tools, modular tabs. Now we're
upgrading from a single-page tabbed layout to a multi-page architecture with
a consistent three-panel design (left nav, center workspace, right chat placeholder).

### Architecture Reference (Mat's Wireframe)

```
JANATPMP   [Projects]  [Work]  [Knowledge]  [Database]     ← demo.route()
┌──────────┬────────────────────────────────┬──────────┐
│          │  [List] [Kanban] [Query] [Hx]  │          │    ← gr.Tabs() within
│ Item 1   │  ┌──────────────────────────┐  │  Chat    │       center column
│ Item 2   │  │                          │  │  ~~~~    │
│ Item 3   │  │   View content changes   │  │  ~~~~    │
│ Item 4   │  │   per tab selected       │  │          │
│          │  │                          │  │  ~~~~    │
│          │  │                          │  │  ~~~~    │
│          │  └──────────────────────────┘  │  [____]  │
└──────────┴────────────────────────────────┴──────────┘
```

**Hierarchy:** Pages (navbar routes) → Panels (three columns) → Views (tabs within center)

### Visual Reference

See `docs/janatpmp-mockup.png` for the target UI design. This mockup shows:
- **Left panel:** Project cards with status dots, type badges, domain/status filters
- **Center panel:** Editable detail form with child items table, tab bar (Detail/List/Query/History)
- **Right panel:** Chat interface showing MCP workflow between Mat and Claude
- **Navbar:** JANATPMP brand with page links (Projects, Work, Knowledge, Database)
- **Color scheme:** Dark canvas (#000000 base), Mat Cyan (#00FFFF) accents, Slate Teal (#00413f)

The Gradio implementation should match this layout structurally. Exact visual styling
(brand colors, fonts) is Phase 4 — for now focus on correct panel structure and functionality.

### Mobile Considerations

JANATPMP will be accessed from both desktop and mobile (Mat running on PC, accessing
from phone on same WiFi). Gradio's Row/Column layout wraps naturally on narrow screens,
but keep these patterns in mind:

- **Launch config:** Use `server_name="0.0.0.0"` so the app is accessible from other devices
  on the local network. The phone hits `http://<PC-IP>:7860`.
- **Panel stacking:** On mobile, the three columns will stack vertically (left → center → right).
  This is acceptable for Phase 1. In Phase 4, consider `gr.Sidebar()` for the left panel
  (collapsible by design, better mobile UX).
- **Touch targets:** Ensure buttons and clickable elements are large enough for touch.
  Use `size="sm"` sparingly — prefer default button sizes.
- **Chat panel:** On mobile the right panel stacks below center content. Phase 4 may
  move this to a collapsible bottom sheet or separate tab.
- **No `fill_width=True`:** Avoid for now as it removes side padding that helps on desktop.
  Can revisit when implementing responsive CSS in Phase 4.

### Gradio Multipage Pattern (from docs)

```python
# Separate page files, each independently runnable
# pages/projects.py
with gr.Blocks() as demo:
    ...content...
if __name__ == "__main__":
    demo.launch()

# app.py — thin orchestrator
import pages.projects, pages.database
with gr.Blocks() as demo:
    pages.projects.demo.render()        # main page
with demo.route("Database", "/database"):
    pages.database.demo.render()
demo.launch()
```

**Key constraint:** No cross-page event listeners. Each page is self-contained.

---

## FILE STRUCTURE (target)

```
app.py                      ← orchestrator: routes + MCP exposure
pages/
  __init__.py               ← empty
  projects.py               ← NEW: three-panel Projects page
  database.py               ← NEW: migrated from tabs/tab_database.py
tabs/                       ← KEEP for now (reuse tab builders in pages)
  __init__.py
  tab_items.py              ← existing, still used by projects.py
  tab_tasks.py              ← existing, used later by Work page
  tab_documents.py          ← existing, used later by Knowledge page
  tab_database.py           ← existing, imported by pages/database.py
db/
  operations.py             ← UNCHANGED
  schema.sql                ← UNCHANGED
```

---

## TASKS

### Task 1: Create pages/ directory structure

**Create:** `pages/__init__.py`

```python
"""Page modules for JANATPMP multi-page app."""
```

That's it. Empty init.

---

### Task 2: Create pages/projects.py — The Three-Panel Projects Page

This is the core deliverable. A fully working Projects page with:
- **Left panel:** Filterable list of project-scope items, clickable to select
- **Center panel:** Detail view of selected item (with tabs for future views)
- **Right panel:** Chat placeholder (gr.Chatbot + gr.Textbox, not wired)

**Create:** `pages/projects.py`

```python
"""Projects page — Three-panel layout with item browser and detail view."""
import gradio as gr
import pandas as pd
from db.operations import (
    list_items, get_item, create_item, update_item, delete_item,
    list_items as get_children  # same function, filtered by parent_id
)


# --- Data helpers ---

# Entity types that appear in the Projects page (project-scope items)
PROJECT_TYPES = ["project", "epic", "book", "website", "milestone"]

DOMAINS = [
    "", "literature", "janatpmp", "janat", "atlas", "meax",
    "janatavern", "amphitheatre", "nexusweaver", "websites",
    "social", "speaking", "life"
]

ALL_TYPES = [
    "project", "epic", "feature", "component", "milestone",
    "book", "chapter", "section",
    "website", "page", "deployment",
    "social_campaign", "speaking_event", "life_area"
]

STATUSES = [
    "not_started", "planning", "in_progress", "blocked",
    "review", "completed", "shipped", "archived"
]


def _fmt(value: str) -> str:
    """Convert 'not_started' → 'Not Started'."""
    return value.replace("_", " ").title() if value else ""


def _projects_list(domain: str = "", status: str = "") -> pd.DataFrame:
    """Fetch project-scope items for the left panel."""
    items = list_items(domain=domain, status=status, limit=100)
    # Filter to project-scope types only
    items = [i for i in items if i.get("entity_type") in PROJECT_TYPES]
    if not items:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Domain", "Status"])
    return pd.DataFrame([{
        "ID": item["id"][:8],
        "Title": item["title"],
        "Type": _fmt(item["entity_type"]),
        "Domain": _fmt(item["domain"]),
        "Status": _fmt(item["status"]),
    } for item in items])


def _children_df(parent_id: str) -> pd.DataFrame:
    """Fetch child items for a given parent."""
    children = list_items(parent_id=parent_id, limit=100)
    if not children:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Status", "Priority"])
    return pd.DataFrame([{
        "ID": c["id"][:8],
        "Title": c["title"],
        "Type": _fmt(c["entity_type"]),
        "Status": _fmt(c["status"]),
        "Priority": c["priority"],
    } for c in children])


def _find_full_id(short_id: str) -> str:
    """Given an 8-char truncated ID, find the full ID from the database."""
    all_items = list_items(limit=500)
    for item in all_items:
        if item["id"].startswith(short_id):
            return item["id"]
    return ""


# --- Page builder ---

with gr.Blocks() as demo:
    # State: currently selected item's full ID
    selected_id = gr.State("")

    with gr.Row():
        # ===== LEFT PANEL: Item list + filters =====
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("### Projects")

            domain_filter = gr.Dropdown(
                label="Domain", choices=DOMAINS, value=""
            )
            status_filter = gr.Dropdown(
                label="Status", choices=STATUSES, value="", allow_custom_value=True
            )
            refresh_btn = gr.Button("🔄 Refresh", variant="secondary", size="sm")

            project_list = gr.DataFrame(
                value=_projects_list(),
                interactive=False,
                label="Click a row to view details",
            )

            # --- Quick Create (collapsed) ---
            with gr.Accordion("➕ New Project", open=False):
                new_type = gr.Dropdown(label="Type", choices=ALL_TYPES, value="project")
                new_domain = gr.Dropdown(label="Domain", choices=DOMAINS[1:], value="janatpmp")
                new_title = gr.Textbox(label="Title", placeholder="Project title...")
                new_desc = gr.Textbox(label="Description", lines=2, placeholder="Optional...")
                new_status = gr.Dropdown(label="Status", choices=STATUSES, value="not_started")
                new_priority = gr.Slider(label="Priority", minimum=1, maximum=5, step=1, value=3)
                new_parent = gr.Textbox(label="Parent ID", placeholder="Optional...")
                create_btn = gr.Button("Create", variant="primary", size="sm")
                create_msg = gr.Textbox(label="Status", interactive=False, visible=True)

        # ===== CENTER PANEL: Detail view with tabs =====
        with gr.Column(scale=3, min_width=500):
            # Tabs for different views
            with gr.Tabs():
                with gr.Tab("Detail"):
                    detail_header = gr.Markdown("*Select a project from the list to view details.*")

                    # Detail fields (hidden until selection)
                    with gr.Column(visible=False) as detail_section:
                        with gr.Row():
                            detail_title = gr.Textbox(label="Title", interactive=True)
                            detail_status = gr.Dropdown(
                                label="Status", choices=STATUSES, interactive=True
                            )
                        with gr.Row():
                            detail_type = gr.Textbox(label="Type", interactive=False)
                            detail_domain = gr.Textbox(label="Domain", interactive=False)
                            detail_priority = gr.Slider(
                                label="Priority", minimum=1, maximum=5, step=1, interactive=True
                            )
                        detail_desc = gr.Textbox(
                            label="Description", lines=4, interactive=True
                        )
                        detail_id_display = gr.Textbox(label="Full ID", interactive=False)

                        with gr.Row():
                            save_btn = gr.Button("💾 Save Changes", variant="primary")
                            save_msg = gr.Textbox(label="", interactive=False, scale=2)

                        # Child items section
                        gr.Markdown("#### Child Items")
                        children_table = gr.DataFrame(
                            value=pd.DataFrame(
                                columns=["ID", "Title", "Type", "Status", "Priority"]
                            ),
                            interactive=False,
                        )

                with gr.Tab("List View"):
                    # Full items table (all types, not just project-scope)
                    gr.Markdown("### All Items")
                    all_items_table = gr.DataFrame(
                        value=pd.DataFrame(
                            columns=["ID", "Title", "Domain", "Type", "Status", "Priority"]
                        ),
                        interactive=False,
                    )
                    all_refresh_btn = gr.Button("🔄 Refresh All", variant="secondary", size="sm")

        # ===== RIGHT PANEL: Chat placeholder =====
        with gr.Column(scale=1, min_width=250):
            gr.Markdown("### Claude")
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": "I'm connected via MCP. Ask me to create items, update tasks, or check project status."}],
                height=500,
                label="Chat"
            )
            chat_input = gr.Textbox(
                placeholder="Chat coming soon...",
                label="",
                interactive=False,  # Not wired yet
            )

    # ===== EVENT WIRING =====

    # -- Left panel: filters and refresh --
    filter_inputs = [domain_filter, status_filter]
    domain_filter.change(
        _projects_list, inputs=filter_inputs, outputs=project_list,
        api_visibility="private"
    )
    status_filter.change(
        _projects_list, inputs=filter_inputs, outputs=project_list,
        api_visibility="private"
    )
    refresh_btn.click(
        _projects_list, inputs=filter_inputs, outputs=project_list,
        api_visibility="private"
    )

    # -- Left panel: row selection → load detail --
    def on_select_project(evt: gr.SelectData, current_list):
        """When user clicks a row in the project list, load its details."""
        if evt.index is None:
            return gr.skip()

        row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        if row_idx >= len(current_list):
            return gr.skip()

        short_id = str(current_list.iloc[row_idx]["ID"])
        full_id = _find_full_id(short_id)
        if not full_id:
            return gr.skip()

        item = get_item(full_id)
        if not item:
            return gr.skip()

        children = _children_df(full_id)

        return (
            full_id,                                                    # selected_id
            f"## {item['title']}",                                      # detail_header
            gr.Column(visible=True),                                    # detail_section
            item.get("title", ""),                                      # detail_title
            item.get("status", ""),                                     # detail_status
            _fmt(item.get("entity_type", "")),                          # detail_type
            _fmt(item.get("domain", "")),                               # detail_domain
            item.get("priority", 3),                                    # detail_priority
            item.get("description", ""),                                # detail_desc
            full_id,                                                    # detail_id_display
            gr.Textbox(value=""),                                       # save_msg (clear)
            children,                                                   # children_table
        )

    project_list.select(
        on_select_project,
        inputs=[project_list],
        outputs=[
            selected_id,
            detail_header, detail_section,
            detail_title, detail_status, detail_type, detail_domain,
            detail_priority, detail_desc, detail_id_display,
            save_msg, children_table,
        ],
        api_visibility="private",
    )

    # -- Center panel: save changes --
    def on_save(item_id, title, status, priority, description):
        """Save edited fields back to the database."""
        if not item_id:
            return "No item selected"
        update_item(
            item_id=item_id,
            title=title,
            status=status,
            priority=int(priority),
            description=description,
        )
        return f"✅ Saved {item_id[:8]}"

    save_btn.click(
        on_save,
        inputs=[selected_id, detail_title, detail_status, detail_priority, detail_desc],
        outputs=[save_msg],
        api_visibility="private",
    )

    # -- Center panel: List View tab refresh --
    def _all_items_df():
        items = list_items(limit=200)
        if not items:
            return pd.DataFrame(columns=["ID", "Title", "Domain", "Type", "Status", "Priority"])
        return pd.DataFrame([{
            "ID": item["id"][:8],
            "Title": item["title"],
            "Domain": _fmt(item.get("domain", "")),
            "Type": _fmt(item.get("entity_type", "")),
            "Status": _fmt(item.get("status", "")),
            "Priority": item.get("priority", 3),
        } for item in items])

    all_refresh_btn.click(
        _all_items_df, outputs=[all_items_table], api_visibility="private"
    )

    # -- Left panel: create item --
    def on_create(entity_type, domain, title, desc, status, priority, parent_id):
        if not title.strip():
            return "❌ Title is required", gr.skip()
        item_id = create_item(
            entity_type=entity_type, domain=domain,
            title=title.strip(),
            description=desc.strip() if desc else "",
            status=status, priority=int(priority),
            parent_id=parent_id.strip() if parent_id else "",
        )
        return f"✅ Created {item_id[:8]}", _projects_list()

    create_btn.click(
        on_create,
        inputs=[new_type, new_domain, new_title, new_desc, new_status, new_priority, new_parent],
        outputs=[create_msg, project_list],
        api_visibility="private",
    )


if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())
```

**Test independently:** `python pages/projects.py` → should load at localhost:7860 with three-panel layout.

---

### Task 3: Create pages/database.py — Migrate Database Tab

This wraps the existing tab_database builder into a standalone page.

**Create:** `pages/database.py`

```python
"""Database page — Schema viewer, backups, and lifecycle management."""
import gradio as gr
from tabs.tab_database import build_database_tab

with gr.Blocks() as demo:
    gr.Markdown("## Database Management")
    build_database_tab()

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())
```

**Note:** `build_database_tab()` currently wraps its content in `gr.Tab("Database")`.
We need to adjust it so it works both as a standalone page AND inside a tab context.

**Edit:** `tabs/tab_database.py` — If the function wraps everything in `with gr.Tab("Database"):`,
that's fine when used inside `gr.Tabs()` but will create an unnecessary tab wrapper when
used as a standalone page. We have two options:

**Option A (preferred):** Leave tab_database.py as-is. In pages/database.py, just call the builder
directly. Since the page IS the database page, having an inner "Database" tab label is
redundant but not broken. We can refine later.

**Option B:** Extract the inner content into a helper function that doesn't wrap in gr.Tab,
then call the helper from both the tab builder and the page. Only do this if Option A
looks bad visually.

**Decision: Go with Option A first.** If it looks weird, refactor.

---

### Task 4: Rewrite app.py — Multi-Page Orchestrator

**Rewrite:** `app.py` (complete replacement)

```python
"""JANATPMP — Multi-page Gradio application with MCP server."""

import gradio as gr
from db.operations import (
    init_database,
    # MCP-exposed operations
    create_item, get_item, list_items, update_item, delete_item,
    create_task, get_task, list_tasks, update_task,
    create_document, get_document, list_documents,
    search_items, search_documents,
    create_relationship, get_relationships,
    get_stats, get_schema_info,
    backup_database, reset_database, restore_database, list_backups,
)
import pages.projects
import pages.database

# Initialize database BEFORE building UI
init_database()

# Build multi-page application
with gr.Blocks(title="JANATPMP") as demo:
    gr.Navbar(main_page_name="Projects")
    pages.projects.demo.render()

with demo.route("Database", "/database"):
    pages.database.demo.render()

# Expose ALL operations as MCP tools (same as v1.0)
gr.api(create_item)
gr.api(get_item)
gr.api(list_items)
gr.api(update_item)
gr.api(delete_item)
gr.api(create_task)
gr.api(get_task)
gr.api(list_tasks)
gr.api(update_task)
gr.api(create_document)
gr.api(get_document)
gr.api(list_documents)
gr.api(search_items)
gr.api(search_documents)
gr.api(create_relationship)
gr.api(get_relationships)
gr.api(get_stats)
gr.api(get_schema_info)
gr.api(backup_database)
gr.api(reset_database)
gr.api(restore_database)
gr.api(list_backups)

if __name__ == "__main__":
    demo.launch(mcp_server=True, server_name="0.0.0.0", theme=gr.themes.Soft())
```

**IMPORTANT:** `gr.api()` calls may need to be INSIDE the `with gr.Blocks() as demo:` context.
If the app errors on launch with gr.api() outside the Blocks context, move them inside like:

```python
with gr.Blocks(title="JANATPMP") as demo:
    gr.Navbar(main_page_name="Projects")
    pages.projects.demo.render()

    # MCP exposure
    gr.api(create_item)
    ... etc ...
```

Test both placements and use whichever works.

---

### Task 5: Verify MCP tools still work

After launching the new multi-page app:
1. Navigate to `http://localhost:7860/gradio_api/mcp/sse` — confirm MCP endpoint responds
2. Check that all 22 tools are still exposed (not more, not fewer)
3. Test one write: create an item via MCP, then click Refresh in the Projects page
4. Test the API docs page at `http://localhost:7860/gradio_api/docs`

---

### Task 6: Clean up old TODO files

**Move to completed/:**
- `TODO_APP_V1.md`
- `TODO_REBUILD_UI.md`
- `TODO_SPRINT1_BUGFIX.md`
- `TODO_FIX_DB_RELIABILITY.md`
- `TODO_HACKATHON_SPRINT_1.md`
- `TODO_004_Database_Operations.md`

These are all done. Keep completed/ as the archive.

---

## WHAT NOT TO DO

- **DO NOT** delete `tabs/` directory. We still import from it and will use tab builders in future pages.
- **DO NOT** modify `db/operations.py` — it's correct and stable.
- **DO NOT** modify `db/schema.sql` — no schema changes in this phase.
- **DO NOT** add any new pip dependencies.
- **DO NOT** wire the chat interface. Right panel is placeholder only.
- **DO NOT** use `demo.load()` for initial data. Use `value=` on DataFrames (already correct pattern).

---

## ACCEPTANCE CRITERIA

1. `python app.py` launches with navbar showing [Projects] [Database]
2. Projects page shows three-panel layout (list | detail | chat placeholder)
3. Clicking a project in left list loads its details in center panel
4. Editing + Save updates the database and shows confirmation
5. Create form in accordion creates items and refreshes the list
6. Database page works (schema viewer, backups, lifecycle)
7. All 22 MCP tools still exposed and functional
8. `python pages/projects.py` runs independently for testing
9. `python pages/database.py` runs independently for testing
10. No `demo.load()` calls anywhere — instant page loads

---

## FUTURE PHASES (not in scope)

- **Phase 2:** Work page with Kanban board (task status columns)
- **Phase 3:** Knowledge page (document browser + search + viewer)
- **Phase 4:** Visual polish — brand CSS (dark theme, Orbitron/Rajdhani fonts, cyan accents),
  `gr.Sidebar()` for mobile-friendly left panel, chat wiring, `gr.HTML` custom cards,
  responsive breakpoints for mobile
