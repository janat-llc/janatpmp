# Claude Code — Phase 2.5 Start Command

## Execute these steps in order:

1. Read `docs/TODO_PHASE2_5_SETTINGS_CONTEXT.md` completely
2. Read `CLAUDE.md` for architecture context
3. Create branch: `git checkout -b feature/phase2.5-settings`
4. Execute Task 1: Add settings table to `db/schema.sql`
5. Execute Task 2: Create `services/settings.py`
6. Execute Task 3: Add `get_context_snapshot()` to `db/operations.py` and update `init_database()`
7. Execute Task 4: Update `services/chat.py` — DB-backed settings + dynamic system prompt
8. Execute Task 5: Update `tabs/tab_database.py` — remove model accordion, add system prompt editor
9. Execute Task 6: Update `pages/projects.py` — Admin sidebar quick-settings + simplified chat wiring
10. Execute Task 7: Update `CLAUDE.md`
11. Smoke test: `python app.py` and verify app starts without errors
12. Commit: `git add -A && git commit -m "Phase 2.5: Settings persistence, system prompt editor, auto-context injection"`

## Key constraint reminders:
- No new pip dependencies
- Schema must be idempotent (IF NOT EXISTS)
- Base64 for API key, not encryption
- Chat reads settings from DB, not from Gradio component state
- All UI event listeners must have `api_visibility="private"`
