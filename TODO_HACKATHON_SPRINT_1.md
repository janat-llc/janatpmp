# TODO: Hackathon Sprint 1 — Foundation Reset & CRUD UI
# Priority: CRITICAL — Must complete before any feature work
# Estimated time: 2-3 hours of Claude Code execution
# Context: JANATPMP hackathon submission (Feb 10-16, 2026)

## OVERVIEW

Transform JANATPMP from a seeded prototype into a clean, demo-ready platform with:
1. Database lifecycle management (reset, backup, restore)
2. Full CRUD UI for all entity types
3. All operations available on UI, API, and MCP simultaneously

The demo story is "cold start" — user installs this with an empty database, and
Claude helps them build their project landscape from nothing. So NO seed data.

## CONSTRAINTS

- Gradio 6.5.1 (pin exact version)
- Python 3.14
- SQLite only (no external dependencies)
- Every new function in db/operations.py MUST have full docstrings with Args/Returns
  (this is how Gradio generates MCP tool descriptions)
- Do NOT delete any existing working code — extend it
- Do NOT change the database schema structure (tables, columns, constraints)
- Test each change by running the app and verifying it works

---

## TASK 1: Update requirements.txt

Pin gradio version exactly:

```
gradio[mcp]==6.5.1
pandas
```

---

## TASK 2: Separate seed data from schema

### Problem
`db/schema.sql` currently contains both schema DDL AND seed INSERT statements at the
bottom. We need them separated so reset can create a clean empty database.

### Steps
1. In `db/schema.sql`, remove the entire "SEED DATA" section (the INSERT INTO items block
   and its comments). Keep everything else exactly as-is.
2. Create a new file `db/seed_data.sql` containing ONLY those INSERT statements with a
   header comment explaining they're optional demo data.

---

## TASK 3: Add database lifecycle operations to db/operations.py

Add these functions to the END of db/operations.py (before any existing code is modified).
Each function must work correctly and have full docstrings.

### 3a: reset_database()

```python
def reset_database() -> str:
    """
    Reset the database to a clean state. Drops all tables and recreates
    the schema from db/schema.sql. All data will be lost.
    Creates a timestamped backup before resetting.

    Returns:
        Status message with backup filename if created, or confirmation of reset
    """
```

Implementation notes:
- First, call `backup_database()` to save current state (if db exists and has data)
- Close any existing connections
- Delete the existing db file
- Read `db/schema.sql` and execute it via `executescript()`
- Return a message like "Database reset. Backup saved as janatpmp_backup_20260207_223000.db"
- If backup wasn't needed (empty db), return "Database reset to clean state."

### 3b: backup_database()

```python
def backup_database() -> str:
    """
    Create a timestamped backup of the current database.
    Backups are stored in the db/backups/ directory.

    Returns:
        The backup filename, or error message if backup failed
    """
```

Implementation notes:
- Create `db/backups/` directory if it doesn't exist
- Use `shutil.copy2()` to copy `db/janatpmp.db` to `db/backups/janatpmp_backup_YYYYMMDD_HHMMSS.db`
- Use `datetime.now().strftime('%Y%m%d_%H%M%S')` for timestamp
- Return the backup filename on success

### 3c: restore_database()

```python
def restore_database(backup_name: str = "") -> str:
    """
    Restore database from a backup. If no backup_name is specified,
    restores the most recent backup.

    Args:
        backup_name: Name of backup file to restore (optional, defaults to most recent)

    Returns:
        Status message confirming restore, or error if no backups found
    """
```

Implementation notes:
- If `backup_name` is empty, find the most recent file in `db/backups/` sorted by name (since
  they're timestamped, alphabetical sort = chronological sort)
- Copy the backup file over `db/janatpmp.db` using `shutil.copy2()`
- Return "Restored from {backup_name}" or "No backups found"

### 3d: list_backups()

```python
def list_backups() -> list:
    """
    List all available database backups.

    Returns:
        List of dicts with backup name, size in bytes, and created timestamp
    """
```

Implementation notes:
- List files in `db/backups/` matching pattern `janatpmp_backup_*.db`
- Return list of `{"name": filename, "size": size_bytes, "created": mtime_iso}` dicts
- Sort by name descending (newest first)

---

## TASK 4: Update api.py exports

Add the new functions to api.py imports and __all__:

```python
from db.operations import (
    # ... existing imports ...
    # Database Lifecycle
    reset_database, backup_database, restore_database, list_backups
)

__all__ = [
    # ... existing exports ...
    'reset_database', 'backup_database', 'restore_database', 'list_backups'
]
```

---

## TASK 5: Rebuild app.py with full CRUD UI

This is the biggest task. Replace the current app.py with a complete UI that exposes
all operations. Keep the same architectural pattern (event handlers at top, UI definition
below, wiring at bottom).

### Layout Structure

```
┌─────────────────────────────────────────────────────────┐
│  JANATPMP v0.2                              [Stats Row] │
├─────────────────────────────────────────────────────────┤
│  Tabs: [Items] [Tasks] [Documents] [Database]           │
│                                                         │
│  Each tab has:                                          │
│  ┌─────────────────────┐  ┌──────────────────────────┐ │
│  │ Data Table           │  │ Create/Edit Form         │ │
│  │ (with filters)       │  │                          │ │
│  │                      │  │ [Create] [Update]        │ │
│  │                      │  │ [Delete]                 │ │
│  └─────────────────────┘  └──────────────────────────┘ │
│                                                         │
│  [Database] tab has:                                    │
│  - Reset Database button (with confirmation pattern)    │
│  - Backup button                                        │
│  - Restore dropdown (populated from list_backups)       │
│  - Schema info display                                  │
│  - Stats display                                        │
└─────────────────────────────────────────────────────────┘
```

### Items Tab Requirements

**Display:** DataFrame showing all items with columns: Title, Domain, Type, Status, Priority
**Filters:** Domain dropdown, Status dropdown, Filter button (KEEP existing)
**Create Form:** Fields for entity_type (dropdown), domain (dropdown), title (text), 
  description (textarea), status (dropdown), priority (slider 1-5), parent_id (text, optional)
**Actions:** Create button, refresh button
**Detail view is NOT required for MVP** — just list + create + filter

### Tasks Tab Requirements

**Display:** DataFrame showing all tasks: Title, Type, Assigned, Status, Priority
**Create Form:** Fields for task_type (dropdown), title, description, assigned_to (dropdown),
  target_item_id (text, optional), priority (dropdown), agent_instructions (textarea, optional)
**Actions:** Create button, refresh button

### Documents Tab Requirements

**Display:** DataFrame showing docs: Title, Type, Source, Created
**Create Form:** Fields for doc_type (dropdown), source (dropdown), title, content (textarea)
**Actions:** Create button, refresh button

### Database Tab Requirements

**Stats:** Show total counts for items, tasks, documents, relationships
**Backup controls:**
  - "Backup Now" button → calls backup_database(), shows result
  - "Available Backups" DataFrame → populated from list_backups()
  - "Restore" button + dropdown of backup names → calls restore_database()
**Reset control:**
  - "Reset Database" button with RED variant
  - This should call backup_database() first, then reset_database()
  - Show result message
**Schema info:** JSON component showing get_schema_info() output

### UI Wiring Pattern

Every form submission should:
1. Call the operation function
2. Show a status message (gr.Info toast or status textbox)
3. Refresh the relevant DataFrame
4. Refresh stats

Example pattern:
```python
create_btn.click(
    fn=handle_create_item,
    inputs=[entity_type, domain, title, description, status, priority],
    outputs=[status_msg, items_table, stat_items, stat_tasks, stat_docs]
)
```

### MCP Exposure

The current `demo.launch(mcp_server=True)` automatically exposes all `gr.api()` decorated
functions OR all event handler functions as MCP tools. To ensure the DB lifecycle functions
are exposed via MCP:

The functions in db/operations.py are called by the UI event handlers. The UI event handlers
themselves get exposed as MCP tools when they're wired to Gradio components. This is the
existing pattern and it works — the current MCP tools I can see are `get_items_dataframe`,
`load_items`, `load_tasks`, `load_stats`.

For the new DB lifecycle functions, we want them exposed as MCP tools too. The simplest way:
make them the direct `fn=` target of button clicks in the UI. Gradio will auto-expose them.

Alternatively, use `gr.api()` to explicitly expose functions. Check Gradio 6.5.1 docs if
needed, but the button-click pattern should work.

---

## TASK 6: Update CLAUDE.md

Update the CLAUDE.md file to reflect:
- Version 0.2
- Gradio 6.5.1
- New file: db/seed_data.sql
- New directory: db/backups/
- Updated architecture description
- Note about hackathon context
- Remove references to "12 seeded domain projects" — it's a clean-start platform now

---

## TASK 7: Update .gitignore

Ensure these are in .gitignore:
```
db/janatpmp.db
db/backups/
__pycache__/
*.pyc
.tmp.driveupload/
```

---

## TASK 8: Test Verification

After all changes, verify:
1. `docker-compose down && docker-compose up --build` starts cleanly
2. App loads at http://localhost:7860 with empty tables (no seed data)
3. Can create an item via the UI → appears in table
4. Can create a task via the UI → appears in table
5. Can create a document via the UI → appears in table
6. Can backup database → file appears in db/backups/
7. Can reset database → tables empty, schema intact
8. Can restore from backup → data returns
9. Stats update correctly after each operation
10. MCP endpoint at /gradio_api/mcp/sse responds

---

## DONE CRITERIA

- [ ] requirements.txt pinned to gradio[mcp]==6.5.1
- [ ] Seed data separated from schema.sql into seed_data.sql
- [ ] 4 new DB lifecycle functions in operations.py with full docstrings
- [ ] api.py updated with new exports
- [ ] app.py rebuilt with CRUD UI for Items, Tasks, Documents
- [ ] Database tab with backup/restore/reset controls
- [ ] CLAUDE.md updated
- [ ] .gitignore updated
- [ ] All 10 test verifications pass
