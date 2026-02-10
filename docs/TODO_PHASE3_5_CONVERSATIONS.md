# Phase 3.5: Claude Export Integration + Knowledge Bug Fixes

## Overview

Integrate the standalone Claude Export Viewer into JANATPMP as a "Conversations"
sub-tab in the Knowledge tab. Uses ATTACH DATABASE to read claude_export.db
alongside the main JANATPMP database — no schema changes to JANATPMP.

Also fixes UX bugs in the New Document form from Phase 3.

## Files Changed

| File | Action |
|------|--------|
| `services/claude_export.py` | **NEW** — Service for claude_export.db operations |
| `services/settings.py` | EDIT — Add default for `claude_export_db_path` |
| `pages/projects.py` | EDIT — Add Conversations sub-tab, fix New Document bugs |

## Files NOT Changed

- `db/schema.sql` — NO schema changes
- `db/operations.py` — NO changes (claude_export has its own service)
- `app.py` — NO changes
- No new dependencies (sqlite3 ATTACH is built-in)

---

## Task 1: Claude Export Service

**File:** `services/claude_export.py` (NEW)

**Purpose:** All read/write operations against the external claude_export.db.

### 1a. Database initialization

Port the schema from `C:\Janat\Claude\Claude_Export\database.py`. The service
must be able to **create** the tables if they don't exist (first-time setup).

```python
"""Claude Export service — manages external conversation database."""

import sqlite3
import json
import os
from pathlib import Path
from services.settings import get_setting

def _get_export_db_path() -> str:
    """Get configured path to claude_export.db."""
    return get_setting("claude_export_db_path") or ""

def _get_connection(db_path: str = None):
    """Get connection to claude_export.db."""
    path = db_path or _get_export_db_path()
    if not path or not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def init_export_db(db_path: str):
    """Initialize claude_export.db schema at the given path. Creates file if needed."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        uuid TEXT PRIMARY KEY,
        full_name TEXT,
        email_address TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        uuid TEXT PRIMARY KEY,
        name TEXT,
        description TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        uuid TEXT PRIMARY KEY,
        name TEXT,
        summary TEXT,
        created_at TEXT,
        updated_at TEXT,
        account_uuid TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        uuid TEXT PRIMARY KEY,
        conversation_uuid TEXT,
        sender TEXT,
        text TEXT,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (conversation_uuid) REFERENCES conversations (uuid)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS content_blocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_uuid TEXT,
        type TEXT,
        text TEXT,
        FOREIGN KEY (message_uuid) REFERENCES messages (uuid)
    )''')
    conn.commit()
    conn.close()
```

### 1b. Ingest functions

Port from `C:\Janat\Claude\Claude_Export\ingest.py`. Accept a **directory path**
as parameter (where the JSON files live), not hardcoded.

```python
def ingest_from_directory(export_dir: str, db_path: str = None) -> str:
    """Ingest users.json, projects.json, conversations.json from export_dir.
    
    Returns status message with counts.
    """
    path = db_path or _get_export_db_path()
    if not path:
        return "Error: No claude_export_db_path configured in Settings."
    
    init_export_db(path)  # Ensure schema exists
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    results = []
    
    # Ingest users
    users_path = os.path.join(export_dir, "users.json")
    if os.path.exists(users_path):
        with open(users_path, 'r', encoding='utf-8') as f:
            users = json.load(f)
        for u in users:
            c.execute('INSERT OR REPLACE INTO users (uuid, full_name, email_address) VALUES (?,?,?)',
                      (u.get('uuid'), u.get('full_name'), u.get('email_address')))
        results.append(f"{len(users)} users")
    
    # Ingest projects
    projects_path = os.path.join(export_dir, "projects.json")
    if os.path.exists(projects_path):
        with open(projects_path, 'r', encoding='utf-8') as f:
            projects = json.load(f)
        for p in projects:
            c.execute('INSERT OR REPLACE INTO projects (uuid, name, description, created_at, updated_at) VALUES (?,?,?,?,?)',
                      (p.get('uuid'), p.get('name'), p.get('description'), p.get('created_at'), p.get('updated_at')))
        results.append(f"{len(projects)} projects")
    
    # Ingest conversations (with messages + content blocks)
    conv_path = os.path.join(export_dir, "conversations.json")
    if os.path.exists(conv_path):
        with open(conv_path, 'r', encoding='utf-8') as f:
            conversations = json.load(f)
        msg_count = 0
        blk_count = 0
        for conv in conversations:
            account = conv.get('account')
            account_uuid = account.get('uuid') if account else None
            c.execute('INSERT OR REPLACE INTO conversations (uuid, name, summary, created_at, updated_at, account_uuid) VALUES (?,?,?,?,?,?)',
                      (conv.get('uuid'), conv.get('name'), conv.get('summary'), conv.get('created_at'), conv.get('updated_at'), account_uuid))
            for msg in conv.get('chat_messages', []):
                msg_uuid = msg.get('uuid')
                text_content = msg.get('text', '')
                c.execute('INSERT OR REPLACE INTO messages (uuid, conversation_uuid, sender, text, created_at, updated_at) VALUES (?,?,?,?,?,?)',
                          (msg_uuid, conv.get('uuid'), msg.get('sender'), text_content, msg.get('created_at'), msg.get('updated_at')))
                msg_count += 1
                for content in msg.get('content', []):
                    ctype = content.get('type')
                    if ctype == 'text':
                        ctext = content.get('text', '')
                    elif ctype == 'tool_use':
                        ctext = f"Tool Use: {content.get('name')} input: {content.get('input')}"
                    elif ctype == 'tool_result':
                        ctext = f"Tool Result: {content.get('content')}"
                    elif ctype == 'thinking':
                        ctext = f"Thinking: {content.get('thinking', '')}"
                    else:
                        ctext = str(content)
                    c.execute('INSERT INTO content_blocks (message_uuid, type, text) VALUES (?,?,?)',
                              (msg_uuid, ctype, ctext))
                    blk_count += 1
        results.append(f"{len(conversations)} conversations, {msg_count} messages, {blk_count} content blocks")
    
    conn.commit()
    conn.close()
    return f"Ingested: {', '.join(results)}" if results else "No JSON files found in directory."
```

### 1c. Query functions

```python
def get_conversations() -> list[dict]:
    """List all conversations ordered by date descending."""
    conn = _get_connection()
    if not conn:
        return []
    rows = conn.execute(
        'SELECT uuid, name, created_at, summary FROM conversations ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_conversation_messages(conv_uuid: str) -> list[dict]:
    """Get all messages for a conversation, with content blocks merged."""
    conn = _get_connection()
    if not conn:
        return []
    messages = conn.execute('''
        SELECT m.*, group_concat(cb.text, CHAR(10)) as full_content
        FROM messages m
        LEFT JOIN content_blocks cb ON m.uuid = cb.message_uuid
        WHERE m.conversation_uuid = ?
        GROUP BY m.uuid
        ORDER BY m.created_at ASC
    ''', (conv_uuid,)).fetchall()
    conn.close()
    
    chat_history = []
    for m in messages:
        text = m['full_content'] if m['full_content'] else m['text']
        if text is None:
            text = ""
        role = "user" if m['sender'] == "human" else "assistant"
        chat_history.append({"role": role, "content": text})
    return chat_history

def get_export_stats() -> dict:
    """Get counts from claude_export.db."""
    conn = _get_connection()
    if not conn:
        return {"conversations": 0, "messages": 0, "human": 0, "ai": 0, "est_tokens": 0}
    conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    human_msgs = conn.execute("SELECT COUNT(*) FROM messages WHERE sender='human'").fetchone()[0]
    ai_msgs = conn.execute("SELECT COUNT(*) FROM messages WHERE sender!='human'").fetchone()[0]
    char_count = conn.execute("SELECT COALESCE(SUM(LENGTH(text)),0) FROM messages").fetchone()[0]
    conn.close()
    return {
        "conversations": conv_count,
        "messages": msg_count,
        "human": human_msgs,
        "ai": ai_msgs,
        "est_tokens": char_count // 4,
    }

def is_configured() -> bool:
    """Check if claude_export_db_path is configured and file exists."""
    path = _get_export_db_path()
    return bool(path) and os.path.exists(path)
```

---

## Task 2: Settings Default

**File:** `services/settings.py`

Add one entry to DEFAULTS dict:

```python
DEFAULTS = {
    # ... existing entries ...
    "claude_export_db_path": ("", False),      # Path to claude_export.db
    "claude_export_json_dir": ("", False),      # Path to directory with JSON exports
}
```

---

## Task 3: Conversations Sub-tab

**File:** `pages/projects.py`

### 3a. Add import

At top of file, add:

```python
from services.claude_export import (
    get_conversations as get_export_conversations,
    get_conversation_messages,
    get_export_stats,
    ingest_from_directory,
    is_configured as is_export_configured,
)
from services.settings import get_setting
```

### 3b. Add Conversations sub-tab

After the Connections sub-tab (currently the 4th sub-tab inside Knowledge), add
a 5th sub-tab:

```python
# --- Conversations sub-tab ---
with gr.Tab("Conversations"):
    conv_configured = is_export_configured()
    
    if not conv_configured:
        gr.Markdown(
            "### ⚠️ Claude Export Not Configured\n\n"
            "Set `claude_export_db_path` and `claude_export_json_dir` "
            "in **Admin → Settings** to enable conversation browsing."
        )
    
    with gr.Row():
        with gr.Column(scale=1):
            # Stats
            conv_stats_md = gr.Markdown("*Loading stats...*")
            
            # Ingest controls
            with gr.Accordion("Import / Refresh", open=False):
                gr.Markdown(
                    "Import conversations from your Claude export JSON files. "
                    "Uses INSERT OR REPLACE — safe to re-run."
                )
                conv_ingest_btn = gr.Button(
                    "Ingest from Export Directory", variant="primary"
                )
                conv_ingest_status = gr.Textbox(
                    show_label=False, interactive=False
                )
            
            # Conversation list
            gr.Markdown("### Conversations")
            conv_list = gr.DataFrame(
                headers=["Name", "Date", "UUID"],
                datatype=["str", "str", "str"],
                interactive=False,
                wrap=True,
            )
        
        with gr.Column(scale=2):
            conv_viewer = gr.Chatbot(
                label="Conversation Viewer",
                height=600,
            )
```

### 3c. Event wiring for Conversations

Add in the `# === KNOWLEDGE EVENT WIRING ===` section:

```python
# --- Conversations sub-tab wiring ---

def _load_conv_stats():
    if not is_export_configured():
        return "*Not configured*"
    stats = get_export_stats()
    return (
        f"**{stats['conversations']:,}** conversations · "
        f"**{stats['messages']:,}** messages · "
        f"~**{stats['est_tokens']:,}** tokens"
    )

def _load_conv_list():
    convs = get_export_conversations()
    return [[c.get("name",""), c.get("created_at","")[:16], c.get("uuid","")] for c in convs]

def _load_selected_conversation(evt: gr.SelectData, df):
    if evt.index:
        row = evt.index[0]
        uuid = df.iloc[row, 2]  # 3rd column is UUID
        return get_conversation_messages(uuid)
    return []

def _run_ingest():
    json_dir = get_setting("claude_export_json_dir")
    if not json_dir:
        return "Error: claude_export_json_dir not set in Settings."
    return ingest_from_directory(json_dir)

# Load stats and list when Knowledge tab is selected
knowledge_tab.select(
    _load_conv_stats, outputs=[conv_stats_md], api_visibility="private"
)
knowledge_tab.select(
    _load_conv_list, outputs=[conv_list], api_visibility="private"
)

# Conversation selection → load into chatbot viewer
conv_list.select(
    _load_selected_conversation, inputs=[conv_list],
    outputs=[conv_viewer], api_visibility="private"
)

# Ingest button
conv_ingest_btn.click(
    _run_ingest, outputs=[conv_ingest_status], api_visibility="private"
).then(
    _load_conv_stats, outputs=[conv_stats_md]
).then(
    _load_conv_list, outputs=[conv_list]
)
```

**IMPORTANT:** The `knowledge_tab.select` at line ~677 currently sets `active_tab`. 
Do NOT replace it — add the conv stats/list loads as ADDITIONAL `.select` listeners 
on `knowledge_tab`, OR chain them with `.then()`.

---

## Task 4: New Document Bug Fixes

**File:** `pages/projects.py`

### Bug 4a: No Cancel button on create form

In the create form section (around line 354), add a Cancel button:

```python
with gr.Row():
    doc_create_btn = gr.Button("Create", variant="primary")
    doc_cancel_btn = gr.Button("Cancel", variant="secondary")
    doc_create_msg = gr.Textbox(
        show_label=False, interactive=False, scale=2
    )
```

### Bug 4b: Cancel button wiring

The Cancel button must be wired INSIDE the `@gr.render` function where `new_doc_btn`
is wired (around line 590), because it needs to update components defined outside render.

Actually — `doc_cancel_btn` is defined outside render (in the Blocks structure), 
so we can wire it outside render too. Add near the other Knowledge event wiring:

```python
doc_cancel_btn.click(
    lambda: (
        "*Select a document from the sidebar, or create a new one.*",
        gr.Column(visible=False),  # hide detail
        gr.Column(visible=False),  # hide create form
        "",  # clear create message
        "",  # clear title field
        "",  # clear content field
    ),
    outputs=[
        doc_header, doc_detail_section, doc_create_section,
        doc_create_msg, new_doc_title, new_doc_content,
    ],
    api_visibility="private",
)
```

### Bug 4c: New Document button clears form fields

The `new_doc_btn.click` handler (around line 590) currently shows the create section
but does NOT clear the form fields. Update it to also clear title, content, and status:

```python
new_doc_btn.click(
    lambda: (
        "## New Document",
        gr.Column(visible=False),   # hide detail
        gr.Column(visible=True),    # show create form
        "",                          # clear title
        "",                          # clear content
        "",                          # clear status message
        "session_notes",             # reset type dropdown
        "manual",                    # reset source dropdown
    ),
    outputs=[
        doc_header, doc_detail_section, doc_create_section,
        new_doc_title, new_doc_content, doc_create_msg,
        new_doc_type, new_doc_source,
    ],
    api_visibility="private",
)
```

### Bug 4d: After creation, navigate to new document

The `_on_doc_create` function already sets `selected_doc_id` to the new doc's ID,
which triggers `_load_doc_detail`. This should work IF the `_load_doc_detail` handler
properly hides the create section and shows the detail section. 

Verify `_load_doc_detail` returns `gr.Column(visible=False)` for `doc_create_section`
(it does — line 852). So this should work already. If it doesn't, ensure the outputs 
list for `selected_doc_id.change` includes `doc_create_section`.

---

## Task 5: Update CLAUDE.md

Add to Features section:
```
- ✅ Knowledge > Conversations — Browse Claude export history via Chatbot viewer
- ✅ Claude Export ingestion from JSON exports (conversations, users, projects)
- ✅ Settings: claude_export_db_path, claude_export_json_dir
```

Mark Phase 3.5 complete in status.

---

## Execution Order

1. Task 2 first (settings defaults — tiny change)
2. Task 1 (claude_export service — standalone, testable independently)
3. Task 3 (Conversations sub-tab — depends on Tasks 1+2)
4. Task 4 (bug fixes — independent of other tasks)
5. Task 5 (CLAUDE.md — last)

## Smoke Test

1. **Settings:** Go to Admin → Settings. Verify `claude_export_db_path` and
   `claude_export_json_dir` appear. Set them:
   - db_path: `C:\Janat\Claude\Claude_Export\claude_export.db`
   - json_dir: `C:\Janat\Claude\Claude_Export`

2. **Conversations tab:** Navigate to Knowledge → Conversations. Verify:
   - Stats line shows conversation/message/token counts
   - Conversation list populates with names and dates
   - Clicking a row loads conversation into Chatbot viewer
   - Human messages on right, assistant on left (standard Chatbot)

3. **Ingest:** Click "Ingest from Export Directory". Verify status shows counts.
   Click again — should re-import cleanly (INSERT OR REPLACE).

4. **New Document bugs:**
   - Click "+ New Document" → verify Title and Content are EMPTY
   - Click "Cancel" → verify form hides, returns to default message
   - Click "+ New Document" → fill in title → click "Create" → verify
     navigates to the new document detail view
   - Verify no stale status messages persist

5. **Tab switching:** Switch between all 5 Knowledge sub-tabs. Verify no
   state bleed between them.

## NOT in scope (Phase 4+)

- File upload mode for New Document
- Folder batch import mode
- Claude Exporter refresh/sync mode in New Document form
- Export to Markdown from within JANATPMP
- Conversation search/filter within Conversations sub-tab
- Full-text search across conversation content
