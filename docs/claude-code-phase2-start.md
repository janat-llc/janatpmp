# Phase 2 — Claude Code Start Command

Paste this into Claude Code to kick off implementation:

---

Read `docs/TODO_PHASE2_CONTEXTUAL_CHAT.md` — that is your complete specification. Read `CLAUDE.md` for current architecture context. Execute all 7 tasks in order.

Before writing any code, read these existing files to understand the patterns:
- `pages/projects.py` (current UI — you're rewriting this)
- `tabs/tab_database.py` (you're modifying this)
- `db/operations.py` (the 22 functions chat.py will expose as tools — read the signatures and docstrings)
- `tabs/tab_tasks.py` (reference pattern for Work tab)

Create a new branch `feature/phase2-contextual-chat` before making changes.

Start with Task 1 (requirements.txt) and Task 2 (services/chat.py) since the chat module has no UI dependencies and can be validated independently. Then Task 3 + Task 7 (Admin tab changes), then Task 4 (the big projects.py rewrite), then Tasks 5-6.

After implementation, run `python app.py` and verify it launches without errors.
