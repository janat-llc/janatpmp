# TODO: Sprint 1 Bugfix — DB Init + Reset Refresh
# Priority: CRITICAL — blocks all demo work
# Estimated time: 30 minutes
# Context: Fixes from Sprint 1 execution

## CRITICAL: Run `docker-compose down` before editing files.

---

## BUG 1: No database initialization on cold start

### Problem
On first launch with no existing DB, `get_connection()` auto-creates an empty SQLite file
(SQLite behavior), but no tables exist. Every query fails. The Database tab shows 36.6s
timeouts because stats/schema queries error against an empty database.

### Fix

Add an `init_database()` function to `db/operations.py`:

```python
def init_database() -> str:
    """
    Initialize the database if it doesn't exist or has no tables.
    Reads db/schema.sql and executes it. Safe to call multiple times —
    schema.sql uses CREATE TABLE (not CREATE TABLE IF NOT EXISTS),
    so this will error if tables exist. Catches that case gracefully.

    Returns:
        Status message: 'initialized', 'already_initialized', or error
    """
```

Implementation:
- Check if DB_PATH exists AND has tables: `SELECT name FROM sqlite_master WHERE type='table' AND name='items'`
- If no tables: read SCHEMA_PATH, executescript, return "initialized"
- If tables exist: return "already_initialized"
- Wrap in try/except for safety

Then call it at module level at the BOTTOM of operations.py:
```python
# Auto-initialize database on import
init_database()
```

This means when `app.py` imports from `db.operations`, the database is guaranteed to
have the schema before any queries run. Safe for Docker cold start.

---

## BUG 2: handle_reset doesn't refresh Database tab components

### Problem
After reset, the Database tab's schema_display, db_stats_display, and backups_table
remain stale because handle_reset's outputs don't include those components.

### Fix

Update `handle_reset()` in app.py to also return refreshed schema and stats:

```python
def handle_reset():
    """Reset database after backup."""
    result = reset_database()
    backups = list_backups()
    backup_df = _backups_to_df(backups)
    backup_names = [b['name'] for b in backups]
    schema = load_schema_info()
    stats_json = get_stats()
    return (
        result,                      # reset_status_msg
        get_items_dataframe(),       # items_table
        get_tasks_dataframe(),       # tasks_table
        get_docs_dataframe(),        # docs_table
        *load_stats(),               # stat_items, stat_tasks, stat_docs, stat_rels
        stats_json,                  # db_stats_display
        schema,                      # schema_display
        backup_df,                   # backups_table
        gr.update(choices=backup_names)  # restore_dropdown
    )
```

Then update the wiring in app.py to match:
```python
reset_btn.click(
    handle_reset,
    inputs=[],
    outputs=[reset_status_msg, items_table, tasks_table, docs_table,
             *all_stats, db_stats_display, schema_display, backups_table, restore_dropdown]
)
```

Similarly, update `handle_restore()` with the same pattern.

---

## BUG 3 (COSMETIC, LOW PRIORITY): Display formatting

### Problem  
Dropdowns show raw schema values like `social_campaign` instead of "Social Campaign".

### Skip for now
This is pure polish. The values ARE correct — they're schema enum values, not IDs.
Fixing it requires a display-name-to-value mapping layer. Do it in Sprint 2 if time allows.

---

## VERIFICATION

After fixes, run `docker-compose down && docker-compose up --build` and verify:
1. App loads with empty tables on first cold start (no pre-existing DB)
2. Database tab shows stats (all zeros) and schema info on load — no timeouts
3. Create an item → stats update
4. Click Reset Database → all tables clear, stats go to zero, schema reloads
5. Backup appears in backup list after reset (auto-backup)
6. Restore from backup → data returns, stats update, schema visible

---

## DONE CRITERIA

- [ ] init_database() added and called on import
- [ ] handle_reset() refreshes all Database tab components
- [ ] handle_restore() refreshes all Database tab components
- [ ] All 6 verification steps pass
