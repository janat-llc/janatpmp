# TODO: Phase 2.5 — Settings Persistence, System Prompt, Auto-Context

**Created:** 2026-02-10
**Author:** Claude (The Weavers)
**Executor:** Claude Code
**Status:** READY FOR EXECUTION
**Branch:** `feature/phase2.5-settings`

---

## CONTEXT

Phase 2 delivered contextual sidebars, Work tab, and Claude chat with tool use. But:

- **Settings are volatile** — Provider, model, API key reset on every app restart.
- **System prompt is hardcoded** — Can't customize without editing services/chat.py.
- **Chat has zero awareness** — Doesn't know what projects or tasks exist until asked.
- **Admin sidebar wastes space** — Just says "Settings in center panel."

Phase 2.5 fixes all four by adding a `settings` table, moving quick-settings into
the Admin sidebar, adding a system prompt editor, and injecting project context
automatically into every chat conversation.

**Read CLAUDE.md first.** It reflects the current architecture accurately.

### What exists today

```
services/chat.py       → Hardcoded SYSTEM_PROMPT, reads provider/model/api_key from
                          Gradio component state (admin_components dict)
tabs/tab_database.py   → Model Settings accordion in center panel (provider, model,
                          API key, base URL). Returns admin_components dict.
pages/projects.py      → Chat wiring reads from admin_components['provider'] etc.
                          Admin left sidebar just shows "Settings in center panel"
db/schema.sql          → No settings table
```

### What Phase 2.5 delivers

1. **`settings` table** — Key-value store in SQLite, loaded on start, persists across restarts
2. **`services/settings.py`** — Get/set settings with base64 obfuscation for API keys
3. **Admin sidebar quick-settings** — Provider/Model/API Key in left sidebar for any-tab access
4. **System prompt editor** — Editable textarea in Admin center panel, saved to settings
5. **Auto-context injection** — Active items + pending tasks injected into system prompt per message
6. **Chat decoupled from component state** — Reads settings from DB, not from Gradio components

---

## FILE STRUCTURE (changes)

```
MODIFIED:
  db/schema.sql            — Add settings table
  db/operations.py         — Add get_setting(), set_setting(), get_context_snapshot()
  services/chat.py         — Read settings from DB, compose dynamic system prompt
  tabs/tab_database.py     — Remove Model Settings accordion, add System Prompt editor
  pages/projects.py        — Admin sidebar quick-settings, simplified chat wiring
  CLAUDE.md                — Update architecture docs

NEW:
  services/settings.py     — Settings service with base64 encoding for secrets
```

---

## TASKS

### Task 1: Settings table in schema.sql

Add to the END of `db/schema.sql` (before schema_version INSERT, or after it — just append):

```sql
-- ============================================================================
-- SETTINGS: Application configuration (key-value store)
-- ============================================================================

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    is_secret INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Auto-update timestamp
CREATE TRIGGER IF NOT EXISTS settings_updated_at AFTER UPDATE ON settings
BEGIN
    UPDATE settings SET updated_at = datetime('now') WHERE key = NEW.key;
END;
```

**IMPORTANT:** Use `CREATE TABLE IF NOT EXISTS` and `CREATE TRIGGER IF NOT EXISTS` so this
is safe to run against an existing database. The `init_database()` function in operations.py
runs schema.sql on every startup — it must be idempotent.

Update the schema_version INSERT to add a new row:
```sql
INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.2.0', 'Add settings table for persistent configuration');
```

### Task 2: Settings service — services/settings.py

Create `services/settings.py`:

```python
"""Settings service — persistent key-value configuration with secret obfuscation."""
import base64
from db.operations import get_connection

# Default settings applied on first run
DEFAULTS = {
    "chat_provider": ("anthropic", False),
    "chat_model": ("claude-sonnet-4-20250514", False),
    "chat_api_key": ("", True),       # is_secret=True → base64 encoded
    "chat_base_url": ("http://localhost:11434/v1", False),
    "chat_system_prompt": ("", False),  # Empty = use default from chat.py
}


def _encode(value: str) -> str:
    """Base64 encode a value for obfuscation (NOT encryption)."""
    if not value:
        return ""
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def _decode(value: str) -> str:
    """Base64 decode an obfuscated value."""
    if not value:
        return ""
    try:
        return base64.b64decode(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return value  # Return as-is if not valid base64


def init_settings():
    """Insert default settings if they don't exist yet. Call on app startup."""
    with get_connection() as conn:
        for key, (default_value, is_secret) in DEFAULTS.items():
            stored = default_value
            if is_secret and stored:
                stored = _encode(stored)
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, is_secret) VALUES (?, ?, ?)",
                (key, stored, int(is_secret))
            )


def get_setting(key: str) -> str:
    """Get a setting value. Decodes secrets automatically."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value, is_secret FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        default = DEFAULTS.get(key)
        return default[0] if default else ""
    value, is_secret = row["value"], row["is_secret"]
    if is_secret:
        return _decode(value)
    return value


def set_setting(key: str, value: str):
    """Set a setting value. Encodes secrets automatically."""
    is_secret = DEFAULTS.get(key, (None, False))[1]
    stored = _encode(value) if is_secret else value
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO settings (key, value, is_secret)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, stored, int(is_secret))
        )


def get_all_settings() -> dict:
    """Get all settings as a dict. Secrets are decoded."""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value, is_secret FROM settings").fetchall()
    result = {}
    for row in rows:
        value = _decode(row["value"]) if row["is_secret"] else row["value"]
        result[row["key"]] = value
    return result
```

### Task 3: Add get_context_snapshot() to db/operations.py

Add this function to `db/operations.py`. It does NOT need to be in EXPOSED_OPS or
exposed via gr.api() — it's internal, used only by chat.py.

```python
def get_context_snapshot() -> str:
    """Build a context string of active items and pending tasks for system prompt injection.

    Returns a formatted string summarizing:
    - Active/in-progress items (title, domain, status)
    - Pending/processing tasks (title, assigned_to, status)

    This is injected into the chat system prompt so the AI has project awareness
    without the user needing to ask "what projects exist?" every conversation.
    """
    with get_connection() as conn:
        # Active items (not completed/archived/shipped)
        items = conn.execute(
            """SELECT title, domain, status, entity_type, priority
               FROM items
               WHERE status NOT IN ('completed', 'shipped', 'archived')
               ORDER BY priority ASC, updated_at DESC
               LIMIT 20""",
        ).fetchall()

        # Pending/active tasks
        tasks = conn.execute(
            """SELECT title, assigned_to, status, priority
               FROM tasks
               WHERE status IN ('pending', 'processing', 'blocked', 'review')
               ORDER BY
                   CASE priority WHEN 'urgent' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                   created_at DESC
               LIMIT 20""",
        ).fetchall()

    lines = []
    if items:
        lines.append(f"Active Items ({len(items)}):")
        for i in items:
            lines.append(f"  - [{i['domain']}] {i['title']} ({i['status']}, P{i['priority']})")
    else:
        lines.append("No active items.")

    if tasks:
        lines.append(f"\nPending Tasks ({len(tasks)}):")
        for t in tasks:
            assigned = t['assigned_to'] if t['assigned_to'] != 'unassigned' else 'unassigned'
            lines.append(f"  - {t['title']} ({t['status']}, {assigned})")
    else:
        lines.append("\nNo pending tasks.")

    return "\n".join(lines)
```

Also update `init_database()` in operations.py — after running schema.sql, call
`init_settings()`:

```python
def init_database():
    """Initialize database: create tables, seed defaults."""
    # ... existing schema.sql execution ...
    from services.settings import init_settings
    init_settings()
```

The import is inside the function to avoid circular imports (settings.py imports
from operations.py).

### Task 4: Update services/chat.py — DB-backed settings + dynamic system prompt

**Changes to chat.py:**

1. Keep the existing `SYSTEM_PROMPT` as `DEFAULT_SYSTEM_PROMPT` (the fallback).

2. Add a new function `_build_system_prompt()` that composes:
   ```
   base prompt (DEFAULT_SYSTEM_PROMPT)
   + custom prompt (from settings, if non-empty)
   + auto-context (from get_context_snapshot())
   ```

3. Change the `chat()` function signature — remove `provider`, `api_key`, `model`,
   `base_url` parameters. Instead, read them from settings DB:
   ```python
   def chat(message: str, history: list[dict]) -> list[dict]:
       """Send a message using settings from the database."""
       from services.settings import get_setting
       provider = get_setting("chat_provider")
       api_key = get_setting("chat_api_key")
       model = get_setting("chat_model")
       base_url = get_setting("chat_base_url")
       system_prompt = _build_system_prompt()
       # ... rest of logic
   ```

4. Pass `system_prompt` into the provider functions instead of using module-level constant:
   - `_chat_anthropic(api_key, model, history, system_prompt)`
   - `_chat_gemini(api_key, model, history, system_prompt)`
   - `_chat_ollama(base_url, model, history, system_prompt)`

5. Rename `SYSTEM_PROMPT` → `DEFAULT_SYSTEM_PROMPT`

**The _build_system_prompt function:**

```python
def _build_system_prompt() -> str:
    """Compose the full system prompt from default + custom + auto-context."""
    from services.settings import get_setting
    from db.operations import get_context_snapshot

    base = DEFAULT_SYSTEM_PROMPT

    custom = get_setting("chat_system_prompt")
    if custom and custom.strip():
        base += f"\n\nAdditional Instructions:\n{custom.strip()}"

    context = get_context_snapshot()
    if context:
        base += f"\n\nCurrent Project State:\n{context}"

    return base
```

### Task 5: Update tabs/tab_database.py — Remove model accordion, add system prompt

**Remove** the entire "Model Settings" accordion (provider, model, API key, base URL).
These move to the Admin sidebar (Task 6).

**Add** a "System Prompt" section in the center panel:

```python
with gr.Accordion("System Prompt", open=False):
    gr.Markdown("Customize the AI assistant's behavior. Leave empty for default.")
    system_prompt_editor = gr.Textbox(
        label="Custom System Prompt",
        lines=6,
        placeholder="e.g., You manage JANATPMP for The Janat Initiative. Focus on actionable responses.",
        value=_load_system_prompt(),  # Read from settings DB
        interactive=True,
    )
    with gr.Row():
        save_prompt_btn = gr.Button("Save Prompt", variant="primary")
        prompt_status = gr.Textbox(show_label=False, interactive=False, scale=2)

    def _save_prompt(prompt_text):
        from services.settings import set_setting
        set_setting("chat_system_prompt", prompt_text)
        return "System prompt saved."

    save_prompt_btn.click(
        _save_prompt,
        inputs=[system_prompt_editor],
        outputs=[prompt_status],
        api_visibility="private",
    )
```

Helper at top of file:
```python
def _load_system_prompt() -> str:
    from services.settings import get_setting
    return get_setting("chat_system_prompt")
```

**Update the return dict.** Remove `'provider'`, `'model'`, `'api_key'`, `'base_url'`
from the returned admin_components dict. Chat no longer reads from those components.
Just return:

```python
return {
    'tab': admin_tab,
    'stats': stats_display,
    'schema': schema_display,
    'backups_table': backups_table,
    'restore_dropdown': restore_dropdown,
}
```

### Task 6: Update pages/projects.py — Admin sidebar + simplified chat wiring

**6a. Admin sidebar quick-settings**

In the `render_left()` function, replace the Admin branch:

```python
elif tab == "Admin":
    gr.Markdown("### Admin")
    gr.Markdown("*Settings in center panel*")
```

With:

```python
elif tab == "Admin":
    gr.Markdown("### Quick Settings")
    from services.settings import get_setting, set_setting
    from services.chat import PROVIDER_PRESETS

    current_provider = get_setting("chat_provider")
    current_model = get_setting("chat_model")
    current_key = get_setting("chat_api_key")
    current_url = get_setting("chat_base_url")

    preset = PROVIDER_PRESETS.get(current_provider, {})

    sidebar_provider = gr.Dropdown(
        choices=["anthropic", "gemini", "ollama"],
        value=current_provider,
        label="Provider",
        key="admin-provider",
        interactive=True,
    )
    sidebar_model = gr.Dropdown(
        choices=preset.get("models", []),
        value=current_model,
        label="Model",
        key="admin-model",
        allow_custom_value=True,
        interactive=True,
    )
    sidebar_api_key = gr.Textbox(
        value=current_key,
        label="API Key",
        type="password",
        placeholder="sk-ant-... or AIza...",
        key="admin-api-key",
        interactive=True,
        visible=preset.get("needs_api_key", True),
    )
    sidebar_base_url = gr.Textbox(
        value=current_url,
        label="Base URL",
        key="admin-base-url",
        interactive=True,
        visible=(current_provider == "ollama"),
    )

    def _save_provider(provider):
        set_setting("chat_provider", provider)
        p = PROVIDER_PRESETS.get(provider, {})
        default_model = p.get("default_model", "")
        set_setting("chat_model", default_model)
        return (
            gr.Dropdown(choices=p.get("models", []), value=default_model),
            gr.Textbox(visible=p.get("needs_api_key", True)),
            gr.Textbox(visible=(provider == "ollama")),
        )

    def _save_model(model):
        set_setting("chat_model", model)

    def _save_api_key(key):
        set_setting("chat_api_key", key)

    def _save_base_url(url):
        set_setting("chat_base_url", url)

    sidebar_provider.change(
        _save_provider,
        inputs=[sidebar_provider],
        outputs=[sidebar_model, sidebar_api_key, sidebar_base_url],
        api_visibility="private",
    )
    sidebar_model.change(_save_model, inputs=[sidebar_model], api_visibility="private")
    sidebar_api_key.change(_save_api_key, inputs=[sidebar_api_key], api_visibility="private")
    sidebar_base_url.change(_save_base_url, inputs=[sidebar_base_url], api_visibility="private")
```

**6b. Simplify chat wiring**

The chat handler no longer needs provider/model/api_key/base_url as inputs. Change:

```python
# OLD
def _handle_chat(message, history, provider, model, api_key, base_url):
    if not message.strip():
        return history, history, ""
    from services.chat import chat
    updated = chat(provider, api_key, model, message, history, base_url)
    return updated, updated, ""

chat_input.submit(
    _handle_chat,
    inputs=[
        chat_input, chat_history,
        admin_components['provider'],
        admin_components['model'],
        admin_components['api_key'],
        admin_components['base_url'],
    ],
    outputs=[chatbot, chat_history, chat_input],
    api_visibility="private",
)
```

To:

```python
# NEW
def _handle_chat(message, history):
    if not message.strip():
        return history, history, ""
    from services.chat import chat
    updated = chat(message, history)
    return updated, updated, ""

chat_input.submit(
    _handle_chat,
    inputs=[chat_input, chat_history],
    outputs=[chatbot, chat_history, chat_input],
    api_visibility="private",
)
```

### Task 7: Update CLAUDE.md

Add a "Settings" section documenting:
- Settings table (key-value, base64 for secrets)
- Setting keys: `chat_provider`, `chat_model`, `chat_api_key`, `chat_base_url`, `chat_system_prompt`
- Auto-context: active items + pending tasks injected per message
- Admin sidebar shows quick-settings, center panel has system prompt + DB tools
- Chat reads from settings DB, not component state

Update the Admin tab description in the architecture table:

```
| **Admin** | Quick Settings (provider/model/key) | System Prompt editor, Stats, Backup/Restore | ✅ Working |
```

---

## EXECUTION ORDER

1. Task 1 (schema) → Task 2 (settings service) → Task 3 (context snapshot)
2. Task 4 (chat.py) — depends on Task 2 + 3
3. Task 5 (tab_database.py) — depends on Task 2
4. Task 6 (projects.py) — depends on Task 2 + 4 + 5
5. Task 7 (CLAUDE.md) — last

**After all tasks: smoke test**
```bash
python app.py
# 1. Open http://localhost:7860
# 2. Go to Admin tab → verify quick-settings in left sidebar
# 3. Set API key → verify it persists after restarting app (Ctrl+C → python app.py)
# 4. Open chat → verify auto-context appears in responses (ask "what's the current state?")
# 5. Edit system prompt in Admin → clear chat → verify new behavior
# 6. Switch tabs → verify quick-settings only show on Admin tab
```

---

## WHAT THIS DOES NOT CHANGE

- **db/schema.sql core tables** — Items, Tasks, Documents, Relationships untouched
- **db/operations.py existing functions** — All 22 operations unchanged
- **MCP/API surface** — No new gr.api() calls (settings are internal only)
- **Chat history** — Still session-only (Phase 3 / Knowledge)
- **Qdrant/Neo4j** — Not in scope (Triad of Memory is post-launch)
- **Kanban view** — Separate ticket

---

## CONSTRAINTS

- Do NOT add new pip dependencies
- Do NOT modify existing db/operations.py functions (only ADD get_context_snapshot)
- Do NOT expose settings via gr.api() or MCP (internal config only)
- Use `CREATE TABLE IF NOT EXISTS` — schema must be idempotent against existing DBs
- Base64 for API key obfuscation, NOT real encryption
- Settings changes take effect on next chat message (no restart needed)
