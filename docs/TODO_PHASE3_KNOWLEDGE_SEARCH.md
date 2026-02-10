# TODO: Phase 3 — Knowledge Tab, Universal Search, Connections

**Created:** 2026-02-10
**Author:** Claude (The Weavers)
**Executor:** Claude Code
**Status:** READY FOR EXECUTION
**Branch:** `feature/phase3-knowledge`

---

## CONTEXT

Phases 1–2.5 delivered Projects, Work, Admin, and Claude Chat — all functional with
contextual sidebars, settings persistence, and auto-context injection. The Knowledge
tab is the last stub: it says "Document browser coming in Phase 3."

The backend is ALREADY DONE. All 6 document/search/relationship operations exist in
`db/operations.py` and are exposed via MCP:
- `create_document`, `get_document`, `list_documents`, `search_documents`
- `create_relationship`, `get_relationships`
- `search_items` (FTS5 on items)

Phase 3 builds the UI that surfaces these operations — following the exact same
patterns established in Projects and Work tabs.

**Read CLAUDE.md first.** It describes the architecture, conventions, and common mistakes.

### What exists today

```
Knowledge tab center:   gr.Markdown("Document browser coming in Phase 3.")
Knowledge left sidebar:  gr.Markdown("Coming in Phase 3")
documents table:         Full schema with FTS5 (doc_type, source, title, content, etc.)
relationships table:     source/target with typed relationships
db/operations.py:        create_document, get_document, list_documents, search_documents,
                         create_relationship, get_relationships, search_items
```

### What Phase 3 delivers

1. **Knowledge sidebar** — Document cards, filters (type, source), + New Document, search box
2. **Documents sub-tab** — Detail view + List View (mirrors Projects/Work pattern)
3. **Search sub-tab** — Universal FTS5 search across items AND documents in one view
4. **Connections sub-tab** — View relationships for any entity (item, task, or document)
5. **Updated CLAUDE.md** — Knowledge tab marked as ✅ Working

---

## FILE STRUCTURE (changes)

```
MODIFIED:
  pages/projects.py     — Knowledge tab center + sidebar content (bulk of the work)
  CLAUDE.md             — Update Knowledge tab status, document new features

NO NEW FILES. No schema changes. No new dependencies.
```

All changes are in `pages/projects.py` (the single-page builder) and `CLAUDE.md`.
The backend operations already exist — this is purely UI work.

---

## TASKS

### Task 1: Add Knowledge state variables and imports

In `build_page()`, add new state variables alongside the existing ones:

```python
# Add after existing states (active_tab, selected_project_id, etc.)
selected_doc_id = gr.State("")
docs_state = gr.State(_load_documents())
```

Add `list_documents`, `get_document`, `create_document`, `search_items`, `search_documents`,
`create_relationship`, `get_relationships` to the imports at the top of `pages/projects.py`
(some may already be imported — don't duplicate).

Add new constants near the existing ones:

```python
DOC_TYPES = [
    "conversation", "file", "artifact", "research",
    "agent_output", "session_notes", "code"
]

DOC_SOURCES = [
    "claude_exporter", "upload", "agent", "generated", "manual"
]
```

Add new data helpers (after the existing `_all_tasks_df`):

```python
def _load_documents(doc_type: str = "", source: str = "") -> list:
    """Fetch documents as list of dicts for sidebar card rendering."""
    return list_documents(doc_type=doc_type, source=source, limit=100)


def _all_docs_df() -> pd.DataFrame:
    """Fetch all documents for the List View."""
    docs = list_documents(limit=200)
    if not docs:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Source", "Created"])
    return pd.DataFrame([{
        "ID": d["id"][:8],
        "Title": d["title"],
        "Type": _fmt(d.get("doc_type", "")),
        "Source": _fmt(d.get("source", "")),
        "Created": d.get("created_at", "")[:16] if d.get("created_at") else "",
    } for d in docs])
```

### Task 2: Build Knowledge tab center panel

Replace the Knowledge tab stub:

```python
# --- Knowledge tab (REPLACE the existing stub) ---
with gr.Tab("Knowledge") as knowledge_tab:
    with gr.Tabs():
        # --- Documents sub-tab ---
        with gr.Tab("Documents"):
            doc_header = gr.Markdown(
                "*Select a document from the sidebar, or create a new one.*"
            )

            with gr.Column(visible=False) as doc_detail_section:
                doc_id_display = gr.Textbox(
                    label="ID", interactive=False, max_lines=1
                )
                with gr.Row():
                    doc_title = gr.Textbox(
                        label="Title", interactive=True, scale=3
                    )
                    doc_type_display = gr.Textbox(
                        label="Type", interactive=False, scale=1
                    )
                    doc_source_display = gr.Textbox(
                        label="Source", interactive=False, scale=1
                    )

                doc_content = gr.Textbox(
                    label="Content", lines=15, interactive=False,
                    show_copy_button=True,
                )

                with gr.Accordion("Metadata", open=False):
                    with gr.Row():
                        doc_file_path = gr.Textbox(
                            label="File Path", interactive=False
                        )
                        doc_created = gr.Textbox(
                            label="Created", interactive=False
                        )

            # --- Create Document form ---
            with gr.Column(visible=False) as doc_create_section:
                with gr.Row():
                    new_doc_type = gr.Dropdown(
                        label="Type", choices=DOC_TYPES,
                        value="session_notes", scale=1
                    )
                    new_doc_source = gr.Dropdown(
                        label="Source", choices=DOC_SOURCES,
                        value="manual", scale=1
                    )
                new_doc_title = gr.Textbox(
                    label="Title", placeholder="Document title..."
                )
                new_doc_content = gr.Textbox(
                    label="Content", lines=10,
                    placeholder="Document content..."
                )
                with gr.Row():
                    doc_create_btn = gr.Button("Create", variant="primary")
                    doc_create_msg = gr.Textbox(
                        show_label=False, interactive=False, scale=2
                    )

        # --- Documents List View sub-tab ---
        with gr.Tab("List View"):
            gr.Markdown("### All Documents")
            all_docs_table = gr.DataFrame(
                value=_all_docs_df(), interactive=False,
            )
            docs_refresh_btn = gr.Button(
                "Refresh All", variant="secondary", size="sm"
            )

        # --- Search sub-tab ---
        with gr.Tab("Search"):
            gr.Markdown("### Universal Search")
            gr.Markdown("Search across all items and documents using full-text search.")
            with gr.Row():
                search_input = gr.Textbox(
                    label="Search Query",
                    placeholder='e.g. "consciousness" or "gradio deploy"',
                    scale=4,
                )
                search_btn = gr.Button("Search", variant="primary", scale=1)

            search_items_results = gr.DataFrame(
                value=pd.DataFrame(
                    columns=["ID", "Title", "Domain", "Type", "Status"]
                ),
                label="Items",
                interactive=False,
            )
            search_docs_results = gr.DataFrame(
                value=pd.DataFrame(
                    columns=["ID", "Title", "Type", "Source", "Created"]
                ),
                label="Documents",
                interactive=False,
            )

        # --- Connections sub-tab ---
        with gr.Tab("Connections"):
            gr.Markdown("### Entity Connections")
            gr.Markdown("View relationships for any item, task, or document.")
            with gr.Row():
                conn_entity_type = gr.Dropdown(
                    choices=["item", "task", "document"],
                    value="item", label="Entity Type", scale=1
                )
                conn_entity_id = gr.Textbox(
                    label="Entity ID",
                    placeholder="Paste full ID or 8-char prefix...",
                    scale=2,
                )
                conn_lookup_btn = gr.Button("Look Up", variant="primary", scale=1)
            connections_table = gr.DataFrame(
                value=pd.DataFrame(
                    columns=[
                        "Relationship", "Direction",
                        "Connected Type", "Connected ID", "Strength"
                    ]
                ),
                label="Connections",
                interactive=False,
            )
            with gr.Accordion("+ Add Connection", open=False):
                with gr.Row():
                    conn_target_type = gr.Dropdown(
                        choices=["item", "task", "document"],
                        value="item", label="Target Type", scale=1
                    )
                    conn_target_id = gr.Textbox(
                        label="Target ID",
                        placeholder="Target entity ID...",
                        scale=2,
                    )
                conn_rel_type = gr.Dropdown(
                    choices=[
                        "blocks", "enables", "informs", "references",
                        "implements", "documents", "depends_on",
                        "parent_of", "attached_to"
                    ],
                    value="references", label="Relationship Type",
                )
                with gr.Row():
                    conn_create_btn = gr.Button("Create Connection", variant="primary")
                    conn_create_msg = gr.Textbox(
                        show_label=False, interactive=False, scale=2
                    )
```

### Task 3: Build Knowledge left sidebar content

In the `render_left` function, replace the Knowledge branch:

```python
elif tab == "Knowledge":
    gr.Markdown("### Documents")
    with gr.Row():
        doc_type_filter = gr.Dropdown(
            label="Type", choices=[""] + DOC_TYPES, value="",
            key="doc-type-filter", scale=1, min_width=100,
        )
        doc_source_filter = gr.Dropdown(
            label="Source", choices=[""] + DOC_SOURCES, value="",
            key="doc-source-filter", scale=1, min_width=100,
        )
    docs_sidebar_refresh = gr.Button(
        "Refresh", variant="secondary", size="sm", key="docs-refresh"
    )

    if not docs:
        gr.Markdown("*No documents yet.*")
    else:
        for d in docs:
            btn = gr.Button(
                f"{d['title']}\n{_fmt(d.get('doc_type', ''))}  ·  {_fmt(d.get('source', '')).upper()}",
                key=f"doc-{d['id'][:8]}",
                size="sm",
            )
            def on_doc_click(d_id=d["id"]):
                return d_id
            btn.click(
                on_doc_click, outputs=[selected_doc_id],
                api_visibility="private"
            )

    new_doc_btn = gr.Button(
        "+ New Document", variant="primary", key="new-doc-btn"
    )

    # Wiring (inside render)
    def _refresh_docs(dtype, source):
        return _load_documents(dtype, source)
    doc_type_filter.change(
        _refresh_docs,
        inputs=[doc_type_filter, doc_source_filter],
        outputs=[docs_state], api_visibility="private"
    )
    doc_source_filter.change(
        _refresh_docs,
        inputs=[doc_type_filter, doc_source_filter],
        outputs=[docs_state], api_visibility="private"
    )
    docs_sidebar_refresh.click(
        _refresh_docs,
        inputs=[doc_type_filter, doc_source_filter],
        outputs=[docs_state], api_visibility="private"
    )

    new_doc_btn.click(
        lambda: (
            "## New Document",
            gr.Column(visible=False),
            gr.Column(visible=True),
        ),
        outputs=[doc_header, doc_detail_section, doc_create_section],
        api_visibility="private",
    )
```

**IMPORTANT:** The `@gr.render` decorator's `inputs` must be updated to include `docs_state`:

```python
@gr.render(inputs=[active_tab, projects_state, tasks_state, docs_state])
def render_left(tab, projects, tasks, docs):
```

### Task 4: Wire Knowledge event listeners

Add these after the existing WORK EVENT WIRING section (before CHAT WIRING):

```python
# === KNOWLEDGE EVENT WIRING ===

# Document detail loading
def _load_doc_detail(doc_id):
    """Load document detail when selection changes."""
    if not doc_id:
        return gr.skip()
    doc = get_document(doc_id)
    if not doc:
        return gr.skip()
    return (
        f"## {doc['title']}",
        gr.Column(visible=True),
        gr.Column(visible=False),
        doc_id,
        doc.get("title", ""),
        _fmt(doc.get("doc_type", "")),
        _fmt(doc.get("source", "")),
        doc.get("content", "") or "",
        doc.get("file_path", "") or "",
        doc.get("created_at", "")[:16] if doc.get("created_at") else "",
    )

selected_doc_id.change(
    _load_doc_detail,
    inputs=[selected_doc_id],
    outputs=[
        doc_header, doc_detail_section, doc_create_section,
        doc_id_display, doc_title, doc_type_display,
        doc_source_display, doc_content,
        doc_file_path, doc_created,
    ],
    api_visibility="private",
)

# Document creation
def _on_doc_create(doc_type, source, title, content):
    if not title.strip():
        return "Title is required", gr.skip(), gr.skip()
    doc_id = create_document(
        doc_type=doc_type,
        source=source,
        title=title.strip(),
        content=content.strip() if content else "",
    )
    return f"Created {doc_id[:8]}", _load_documents(), doc_id

doc_create_btn.click(
    _on_doc_create,
    inputs=[new_doc_type, new_doc_source, new_doc_title, new_doc_content],
    outputs=[doc_create_msg, docs_state, selected_doc_id],
    api_visibility="private",
)

# Document list refresh
docs_refresh_btn.click(
    _all_docs_df, outputs=[all_docs_table], api_visibility="private"
)

# Universal search
def _run_search(query):
    if not query or not query.strip():
        empty_items = pd.DataFrame(
            columns=["ID", "Title", "Domain", "Type", "Status"]
        )
        empty_docs = pd.DataFrame(
            columns=["ID", "Title", "Type", "Source", "Created"]
        )
        return empty_items, empty_docs

    q = query.strip()

    # Search items via FTS5
    try:
        items = search_items(q, limit=50)
    except Exception:
        items = []
    if items:
        items_df = pd.DataFrame([{
            "ID": i["id"][:8],
            "Title": i["title"],
            "Domain": _fmt(i.get("domain", "")),
            "Type": _fmt(i.get("entity_type", "")),
            "Status": _fmt(i.get("status", "")),
        } for i in items])
    else:
        items_df = pd.DataFrame(
            columns=["ID", "Title", "Domain", "Type", "Status"]
        )

    # Search documents via FTS5
    try:
        docs = search_documents(q, limit=50)
    except Exception:
        docs = []
    if docs:
        docs_df = pd.DataFrame([{
            "ID": d["id"][:8],
            "Title": d["title"],
            "Type": _fmt(d.get("doc_type", "")),
            "Source": _fmt(d.get("source", "")),
            "Created": d.get("created_at", "")[:16] if d.get("created_at") else "",
        } for d in docs])
    else:
        docs_df = pd.DataFrame(
            columns=["ID", "Title", "Type", "Source", "Created"]
        )

    return items_df, docs_df

search_btn.click(
    _run_search,
    inputs=[search_input],
    outputs=[search_items_results, search_docs_results],
    api_visibility="private",
)
search_input.submit(
    _run_search,
    inputs=[search_input],
    outputs=[search_items_results, search_docs_results],
    api_visibility="private",
)

# Connections lookup
def _lookup_connections(entity_type, entity_id):
    if not entity_id or not entity_id.strip():
        return pd.DataFrame(
            columns=["Relationship", "Direction", "Connected Type", "Connected ID", "Strength"]
        )

    eid = entity_id.strip()
    rels = get_relationships(entity_type=entity_type, entity_id=eid)

    if not rels:
        return pd.DataFrame(
            columns=["Relationship", "Direction", "Connected Type", "Connected ID", "Strength"]
        )

    rows = []
    for r in rels:
        if r["source_id"] == eid:
            rows.append({
                "Relationship": _fmt(r["relationship_type"]),
                "Direction": "→ outgoing",
                "Connected Type": r["target_type"],
                "Connected ID": r["target_id"][:8],
                "Strength": r.get("strength", "hard"),
            })
        else:
            rows.append({
                "Relationship": _fmt(r["relationship_type"]),
                "Direction": "← incoming",
                "Connected Type": r["source_type"],
                "Connected ID": r["source_id"][:8],
                "Strength": r.get("strength", "hard"),
            })
    return pd.DataFrame(rows)

conn_lookup_btn.click(
    _lookup_connections,
    inputs=[conn_entity_type, conn_entity_id],
    outputs=[connections_table],
    api_visibility="private",
)

# Create connection
def _on_conn_create(source_type, source_id, target_type, target_id, rel_type):
    if not source_id.strip() or not target_id.strip():
        return "Both entity ID and target ID are required"
    try:
        rel_id = create_relationship(
            source_type=source_type,
            source_id=source_id.strip(),
            target_type=target_type,
            target_id=target_id.strip(),
            relationship_type=rel_type,
        )
        return f"Created connection {rel_id[:8]}"
    except Exception as e:
        return f"Error: {str(e)}"

conn_create_btn.click(
    _on_conn_create,
    inputs=[
        conn_entity_type, conn_entity_id,
        conn_target_type, conn_target_id, conn_rel_type,
    ],
    outputs=[conn_create_msg],
    api_visibility="private",
)
```

### Task 5: Update CLAUDE.md

Update the Knowledge tab row in the architecture table:

```
| **Knowledge** | Document cards, filters, + New Doc | Documents (Detail/List), Search, Connections | ✅ Working |
```

Add to the "Settings & Chat Architecture" section or create a new "Knowledge Tab" section:

```markdown
### Knowledge Tab

The Knowledge tab surfaces documents, search, and entity relationships:

- **Documents** — CRUD for session notes, research, artifacts, conversation imports, code.
  Same sidebar-card + detail pattern as Projects and Work tabs.
- **Search** — Universal FTS5 search across items AND documents simultaneously.
  Uses `search_items()` and `search_documents()` from db/operations.py.
- **Connections** — Relationship viewer. Look up any entity (item/task/document) by ID
  to see incoming and outgoing relationships. Create new connections inline.
  Uses `get_relationships()` and `create_relationship()` from db/operations.py.

All 6 underlying operations (`create_document`, `get_document`, `list_documents`,
`search_documents`, `create_relationship`, `get_relationships`) were built in Phase 1
and exposed via MCP — Phase 3 only adds the UI layer.
```

Update the project status line at top of CLAUDE.md:

```markdown
**Status:** Phase 3 — Knowledge tab, universal search, entity connections
```

---

## EXECUTION ORDER

1. Task 1 (states, imports, helpers) — foundation
2. Task 2 (center panel) — build the tab content
3. Task 3 (sidebar) — contextual sidebar for Knowledge
4. Task 4 (event wiring) — connect everything
5. Task 5 (CLAUDE.md) — documentation

**After all tasks: smoke test**
```bash
python app.py
# 1. Open http://localhost:7860
# 2. Click Knowledge tab → verify Documents, List View, Search, Connections sub-tabs
# 3. Click "+ New Document" in sidebar → create a document → verify it appears in sidebar
# 4. Click a document card → verify detail loads in center panel
# 5. Go to Search tab → search a term → verify results from both items and documents
# 6. Go to Connections tab → paste an item ID → verify relationships display
# 7. Create a connection → verify it appears on lookup
# 8. Switch to Projects tab → switch back to Knowledge → verify sidebar updates correctly
# 9. Check List View → click Refresh All → verify document table populates
```

---

## WHAT THIS DOES NOT CHANGE

- **db/schema.sql** — No schema changes (documents, relationships tables already exist)
- **db/operations.py** — No new functions (all 6 operations already exist and work)
- **services/chat.py** — Untouched
- **services/settings.py** — Untouched
- **tabs/tab_database.py** — Untouched
- **MCP/API surface** — No changes (all tools already exposed)
- **requirements.txt** — No new dependencies
- **Docker** — No changes

---

## CONSTRAINTS

- Do NOT add new pip dependencies
- Do NOT modify db/operations.py or db/schema.sql (everything needed already exists)
- Do NOT create new files — all UI changes go in pages/projects.py
- Follow the EXACT same patterns as Projects and Work tabs:
  - Sidebar cards with `key=f"doc-{d['id'][:8]}"`
  - Detail section with `gr.Column(visible=False)` toggled by selection
  - Create section with `gr.Column(visible=False)` toggled by "+ New" button
  - Event listeners with `api_visibility="private"`
  - Loop variable freezing: `def on_doc_click(d_id=d["id"]):`
  - State as both input and output to trigger re-renders
- FTS5 queries may throw if query contains special characters — wrap in try/except
- The `@gr.render` inputs list MUST include `docs_state` alongside existing states
- Document `content` field can be large — use `show_copy_button=True` on the display textbox

---

## DESIGN NOTES

### Why these four sub-tabs?

| Sub-tab | Purpose | Matches |
|---------|---------|---------|
| Documents | CRUD for the documents table | Projects Detail, Work Detail |
| List View | DataFrame of all documents | Projects List View, Work List View |
| Search | The unique value-add of Knowledge | New — FTS5 across items + docs |
| Connections | Relationship graph (table form) | New — surfaces relationships table |

### Search UX

Search returns two DataFrames: one for items, one for documents. This keeps the result
types visually distinct and avoids type-confusion in a merged table. Both tables use
the same column format as their respective List View tabs for consistency.

FTS5 supports porter stemming and unicode — so "consciousness" matches "conscious",
"programming" matches "program", etc. Queries with special FTS5 operators (AND, OR, NOT,
quotes) work naturally. Wrap in try/except to handle malformed queries gracefully.

### Connections UX

The connections viewer shows a flat table of relationships (not a graph visualization).
Each row shows: relationship type, direction (→ outgoing / ← incoming), connected entity
type, connected entity ID (truncated), and strength. This is sufficient for Phase 3 —
a visual graph can be added in a future phase using the HTML component if needed.

The "Add Connection" accordion keeps the UI clean — most of the time you're looking up
connections, not creating them. Creation requires knowing both entity IDs, which power
users will have from other tabs.
