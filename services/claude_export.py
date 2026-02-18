"""Claude Export service — manages external conversation database."""

import sqlite3
import json
import logging
import os
from pathlib import Path
from services.settings import get_setting

logger = logging.getLogger(__name__)


def _get_export_db_path() -> str:
    """Get configured path to claude_export.db from settings.

    Returns:
        Path string, or empty string if not configured.
    """
    return get_setting("claude_export_db_path") or ""


def _get_connection(db_path: str = None):
    """Get SQLite connection to claude_export.db.

    Args:
        db_path: Override path. Uses settings if None.

    Returns:
        sqlite3.Connection with Row factory, or None if DB not found.
    """
    path = db_path or _get_export_db_path()
    if not path or not os.path.exists(path):
        logger.warning("Claude export DB not found: %s", path)
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_export_db(db_path: str):
    """Initialize claude_export.db schema at the given path.

    Creates the database file and all tables (users, projects, conversations,
    messages, content_blocks) if they don't exist. Safe to call multiple times.

    Args:
        db_path: Absolute path to the database file.
    """
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


def ingest_from_directory(export_dir: str, db_path: str = None) -> str:
    """Ingest users.json, projects.json, conversations.json from export_dir.

    Reads JSON files from the export directory and upserts into claude_export.db.
    Conversations include nested messages and content blocks.

    Args:
        export_dir: Path to directory containing Claude export JSON files.
        db_path: Override DB path. Uses settings if None.

    Returns:
        Status message string with ingested counts.
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
    summary = f"Ingested: {', '.join(results)}" if results else "No JSON files found in directory."
    logger.info("Claude export ingest: %s", summary)
    return summary


def get_conversations() -> list[dict]:
    """List all conversations from claude_export.db ordered by date descending.

    Returns:
        List of dicts with keys: uuid, name, created_at, summary.
        Empty list if DB not configured or unavailable.
    """
    conn = _get_connection()
    if not conn:
        return []
    rows = conn.execute(
        'SELECT uuid, name, created_at, summary FROM conversations ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation_messages(conv_uuid: str) -> list[dict]:
    """Get all messages for a conversation, with content blocks merged.

    Args:
        conv_uuid: UUID of the conversation in claude_export.db.

    Returns:
        List of {"role": "user"|"assistant", "content": str} dicts for Chatbot display.
    """
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
    """Get summary counts from claude_export.db.

    Returns:
        Dict with keys: conversations, messages, human, ai, est_tokens.
        All zeros if DB not available.
    """
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
    """Check if claude_export_db_path is configured and file exists.

    Returns:
        True if path is set in settings and the file exists on disk.
    """
    path = _get_export_db_path()
    return bool(path) and os.path.exists(path)
