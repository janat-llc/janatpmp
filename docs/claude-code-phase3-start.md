# Phase 3 — Knowledge Tab, Universal Search, Connections

## Before you start

1. Read `CLAUDE.md` completely — it describes the architecture, conventions, and common mistakes.
2. Read `docs/TODO_PHASE3_KNOWLEDGE_SEARCH.md` — it is the complete spec with all 5 tasks.
3. Read `pages/projects.py` — this is the ONLY file you will modify (plus CLAUDE.md).
4. Understand the existing pattern by studying how the **Projects** and **Work** tabs work:
   - Sidebar cards → `selected_*_id` state → detail loads in center
   - `@gr.render` rebuilds sidebar when state changes
   - "+ New" button toggles create section visible, detail section hidden
   - All event listeners use `api_visibility="private"`
   - Loop variables frozen in callbacks: `def handler(x=x):`

## What you're building

The Knowledge tab — the last stub. It mirrors Projects/Work patterns for documents,
and adds two new sub-tabs: universal FTS5 search and entity relationship viewer.

**Backend is done.** All 6 operations exist in `db/operations.py`:
- `create_document`, `get_document`, `list_documents`, `search_documents`
- `create_relationship`, `get_relationships`
- `search_items`

You are building UI only. No schema changes. No new files. No new dependencies.

## Execution order

1. **Task 1:** Add imports, constants (DOC_TYPES, DOC_SOURCES), state variables
   (`selected_doc_id`, `docs_state`), and helper functions (`_load_documents`, `_all_docs_df`)
2. **Task 2:** Replace Knowledge tab stub with center panel (Documents detail/create,
   List View, Search, Connections sub-tabs)
3. **Task 3:** Replace Knowledge sidebar stub in `render_left()` — update `@gr.render`
   inputs to include `docs_state`, add document cards/filters/+ New Doc
4. **Task 4:** Wire all event listeners (doc detail, doc create, search, connections)
5. **Task 5:** Update CLAUDE.md status and add Knowledge tab documentation

## Critical reminders

- The `@gr.render` decorator MUST have `docs_state` in its inputs list
- The `render_left` function signature MUST accept the new `docs` parameter
- FTS5 queries can throw on special characters — always wrap `search_items()`
  and `search_documents()` in try/except
- All event listeners need `api_visibility="private"`
- Test by running `python app.py` and verifying all 4 sub-tabs work

## Smoke test

```bash
python app.py
# 1. Knowledge tab → 4 sub-tabs visible (Documents, List View, Search, Connections)
# 2. "+ New Document" → create → appears in sidebar
# 3. Click card → detail loads
# 4. Search tab → search "test" → results display
# 5. Connections tab → paste an ID → relationships display
# 6. Switch tabs → sidebar updates correctly
```
