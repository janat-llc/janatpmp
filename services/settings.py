"""Settings service — persistent key-value configuration with secret obfuscation."""
import base64
from db.operations import get_connection

# Default settings applied on first run
DEFAULTS = {
    "chat_provider": ("anthropic", False),
    "chat_model": ("claude-sonnet-4-20250514", False),
    "chat_api_key": ("", True),       # is_secret=True → base64 encoded
    "chat_base_url": ("http://ollama:11434/v1", False),
    "chat_system_prompt": ("", False),  # Empty = use default from chat.py
    "claude_export_db_path": ("/data/claude_export/claude_export.db", False),
    "claude_export_json_dir": ("/data/claude_export", False),
    "ingestion_google_ai_dir": ("/app/imports/raw_data/google_ai", False),
    "ingestion_markdown_dir": ("/app/imports/raw_data/markdown", False),
    "ingestion_quest_dir": ("", False),
    "ollama_num_ctx": ("32768", False),
    "ollama_keep_alive": ("5m", False),
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
    """Insert default settings if they don't exist yet. Call on app startup.

    Uses INSERT OR IGNORE for new keys. For keys with non-empty defaults,
    also backfills if the stored value is empty (handles new defaults added
    after initial setup).
    """
    with get_connection() as conn:
        for key, (default_value, is_secret) in DEFAULTS.items():
            stored = default_value
            if is_secret and stored:
                stored = _encode(stored)
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, is_secret) VALUES (?, ?, ?)",
                (key, stored, int(is_secret))
            )
            # Backfill: if default is non-empty but stored value is empty, update it
            if default_value:
                conn.execute(
                    "UPDATE settings SET value = ? WHERE key = ? AND (value IS NULL OR value = '')",
                    (stored, key)
                )
        conn.commit()


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
        conn.commit()


def get_all_settings() -> dict:
    """Get all settings as a dict. Secrets are decoded."""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value, is_secret FROM settings").fetchall()
    result = {}
    for row in rows:
        value = _decode(row["value"]) if row["is_secret"] else row["value"]
        result[row["key"]] = value
    return result
