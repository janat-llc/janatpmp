# TODO: Fix Database Initialization and Load Reliability

**Date:** 2026-02-08  
**Priority:** CRITICAL — App is non-functional on page refresh  
**Context:** Rebuild produced correct structure but DB lifecycle has fatal bugs

---

## ROOT CAUSES

1. **WAL file ghosts**: `reset_database()` deletes `.db` but not `.db-wal` and `.db-shm`. SQLite sees orphaned WAL files → hangs or corrupts.
2. **One-shot init**: `init_database()` runs at import only. After reset, page refresh doesn't re-init. 
3. **Silent failures**: `load_all()` has no try/except. Any exception → 40s spinner timeout with no feedback.
4. **Possible Google Drive locking**: If `C:\Janat\JANATPMP\` is Google Drive-synced, SQLite WAL + Drive sync = constant lock contention.

---

## FIX 1: `db/operations.py` — Fix `reset_database()` to clean WAL files

In `reset_database()`, AFTER the backup and BEFORE recreating, delete ALL database files:

```python
def reset_database() -> str:
    backup_msg = ""

    # Backup if database exists and has data
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        backup_result = backup_database()
        if not backup_result.startswith("Backup failed"):
            backup_msg = f" Backup saved as {backup_result}"

    # Delete existing database AND journal files
    for suffix in ['', '-wal', '-shm', '-journal']:
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()

    # Recreate from schema
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.executescript(schema_sql)
    finally:
        conn.close()

    if backup_msg:
        return f"Database reset.{backup_msg}"
    return "Database reset to clean state."
```

---

## FIX 2: `db/operations.py` — Make `init_database()` safe to call anytime

Change `init_database()` to also handle the WAL ghost scenario, and make it public (not just import-time):

```python
def init_database():
    """Initialize database schema if tables don't exist.
    Safe to call multiple times. Also cleans orphaned WAL files
    if DB was deleted but journals remain."""
    schema_path = Path(__file__).parent / "schema.sql"
    
    # Clean orphaned WAL files if DB doesn't exist
    if not DB_PATH.exists():
        for suffix in ['-wal', '-shm', '-journal']:
            p = Path(str(DB_PATH) + suffix)
            if p.exists():
                p.unlink()
    
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
        )
        if cursor.fetchone() is not None:
            return  # Already initialized
        schema_sql = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema_sql)

# Initialize on import
init_database()
```

---

## FIX 3: `db/operations.py` — Add `busy_timeout` to `get_connection()`

This prevents lock contention from Google Drive sync or concurrent connections:

```python
@contextmanager
def get_connection():
    """Get database connection with proper settings."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
    finally:
        conn.close()
```

The `timeout=10` in `sqlite3.connect()` is Python's lock wait (seconds).
The `PRAGMA busy_timeout = 5000` is SQLite's internal retry (milliseconds).

---

## FIX 4: `app.py` — Add error handling to `load_all()` and call `init_database()` first

```python
def create_app():
    with gr.Blocks(title="JANATPMP") as demo:
        gr.Markdown("# 🏗️ JANATPMP v0.3")

        with gr.Tabs():
            items_table = build_items_tab()
            tasks_table = build_tasks_tab()
            docs_table = build_documents_tab()
            db_components = build_database_tab()

        def load_all():
            """Load all tab data. Called on page load/refresh."""
            from db.operations import init_database
            init_database()  # Ensure DB exists on every page load
            
            try:
                return (
                    _items_to_df(),
                    _tasks_to_df(),
                    _docs_to_df(),
                    _load_stats(),
                    _load_schema(),
                    _backups_to_df(),
                    gr.Dropdown(choices=_backup_names())
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                # Return safe defaults so UI doesn't hang
                import pandas as pd
                empty_items = pd.DataFrame(columns=["ID", "Title", "Domain", "Type", "Status", "Priority"])
                empty_tasks = pd.DataFrame(columns=["ID", "Title", "Type", "Assigned", "Status", "Priority"])
                empty_docs = pd.DataFrame(columns=["ID", "Title", "Type", "Source", "Created"])
                empty_backups = pd.DataFrame(columns=["Name", "Size (KB)", "Created"])
                return (
                    empty_items, empty_tasks, empty_docs,
                    {"error": str(e)}, "{}",
                    empty_backups, gr.Dropdown(choices=[])
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

## FIX 5: Clean up stale root-level DB file

Delete `C:\Janat\JANATPMP\janatpmp.db` (the one in root, NOT db/janatpmp.db).
Also delete `C:\Janat\JANATPMP\nul` and `C:\Janat\JANATPMP\app_output.txt`.

---

## FIX 6 (OPTIONAL BUT RECOMMENDED): Exclude DB from Google Drive sync

If `C:\Janat\JANATPMP\` is synced to Google Drive:
- Either move `db/` to a non-synced location and symlink
- Or add `db/*.db*` to Google Drive's exclusion list
- The `.tmp.driveupload` files in the directory confirm Drive sync is active

SQLite WAL mode + Google Drive sync is a known anti-pattern that causes exactly the timeout behavior you're seeing.

---

## VERIFICATION

After applying fixes:

1. Stop server completely
2. Delete `db/janatpmp.db`, `db/janatpmp.db-wal`, `db/janatpmp.db-shm` (if they exist)
3. Delete root `janatpmp.db`  
4. Start server: `python app.py`
5. Page should load instantly — empty tables, empty stats, no spinners
6. Create an item → appears in table
7. Click Reset Database → stats go to zero, backup appears
8. Refresh page → should load instantly again (no 39.8s timeout)
9. Check terminal for any error output

---

## WHAT "HARDCODED VALUES" MEANS

If Mat sees data in tabs that doesn't come from the DB: `demo.load()` is failing silently and Gradio is showing default component values. The dropdown CHOICES (domain names, status options) ARE intentionally hardcoded — those are the valid filter options from the schema. The DataFrames should be empty on a clean DB.

After these fixes, if `demo.load()` fails, it will:
1. Print the traceback to the terminal (visible to Mat)
2. Return safe empty defaults so the UI renders immediately
3. Show `{"error": "..."}` in the Stats panel so Mat can see what went wrong
