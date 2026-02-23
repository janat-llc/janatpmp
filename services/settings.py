"""Settings service — persistent key-value configuration with secret obfuscation.

Settings are stored in SQLite with base64 encoding for secrets (obfuscation,
not encryption). The SETTINGS_REGISTRY defines all known settings with their
defaults, categories, secret flags, and optional validators.
"""
import base64
import logging
from db.operations import get_connection

logger = logging.getLogger(__name__)


# --- Validators ---

def _validate_provider(value: str) -> str | None:
    """Validate chat provider value.

    Args:
        value: Provider string to validate.

    Returns:
        Error message string if invalid, None if valid.
    """
    valid = ("anthropic", "gemini", "ollama")
    if value and value not in valid:
        return f"Invalid provider '{value}'. Must be one of: {', '.join(valid)}"
    return None


def _validate_positive_int(value: str) -> str | None:
    """Validate that value is a positive integer string.

    Args:
        value: String to validate.

    Returns:
        Error message string if invalid, None if valid.
    """
    if value and not value.strip().isdigit():
        return f"Must be a positive integer, got '{value}'"
    return None


def _validate_positive_float(value: str) -> str | None:
    """Validate that value is a non-negative float string.

    Args:
        value: String to validate.

    Returns:
        Error message string if invalid, None if valid.
    """
    if not value:
        return None
    try:
        f = float(value)
        if f < 0:
            return f"Must be non-negative, got '{value}'"
    except ValueError:
        return f"Must be a number, got '{value}'"
    return None


def _validate_float_0_1(value: str) -> str | None:
    """Validate that value is a float between 0.0 and 1.0.

    Args:
        value: String to validate.

    Returns:
        Error message string if invalid, None if valid.
    """
    if not value:
        return None
    try:
        f = float(value)
        if f < 0 or f > 1:
            return f"Must be between 0.0 and 1.0, got '{value}'"
    except ValueError:
        return f"Must be a number, got '{value}'"
    return None


def _validate_log_level(value: str) -> str | None:
    """Validate Python logging level name.

    Args:
        value: Log level string to validate.

    Returns:
        Error message string if invalid, None if valid.
    """
    valid = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    if value and value.upper() not in valid:
        return f"Invalid log level '{value}'. Must be one of: {', '.join(valid)}"
    return None


# --- Settings Registry ---
# Each entry: (default, is_secret, category, validator_fn_or_None)

SETTINGS_REGISTRY = {
    # Chat
    "chat_provider":        ("ollama", False, "chat", _validate_provider),
    "chat_model":           ("qwen3-vl:8b", False, "chat", None),
    "chat_api_key":         ("", True, "chat", None),
    "chat_base_url":        ("http://ollama:11434/v1", False, "chat", None),
    "chat_system_prompt":   ("", False, "chat", None),
    "chat_temperature":     ("0.7", False, "chat", _validate_positive_float),
    "chat_top_p":           ("0.9", False, "chat", _validate_positive_float),
    "chat_max_tokens":      ("8192", False, "chat", _validate_positive_int),

    # Ollama
    "ollama_num_ctx":       ("131072", False, "ollama", _validate_positive_int),
    "ollama_keep_alive":    ("-1", False, "ollama", None),

    # Janus (continuous chat)
    "janus_conversation_id":  ("", False, "chat", None),
    "janus_context_messages": ("10", False, "chat", _validate_positive_int),
    "janus_display_turns":    ("20", False, "chat", _validate_positive_int),

    # Export
    "claude_export_json_dir": ("/app/imports/claude", False, "export", None),

    # Ingestion
    "ingestion_google_ai_dir": ("/app/imports/google_ai", False, "ingestion", None),
    "ingestion_markdown_dir":  ("/app/imports/markdown", False, "ingestion", None),

    # RAG
    "qdrant_url":           ("http://janatpmp-qdrant:6333", False, "rag", None),
    "rag_score_threshold":  ("0.3", False, "rag", _validate_positive_float),
    "rag_rerank_threshold": ("0.3", False, "rag", _validate_float_0_1),
    "rag_max_chunks":       ("10", False, "rag", _validate_positive_int),
    "rag_synthesizer_provider": ("ollama", False, "rag", None),
    "rag_synthesizer_model": ("qwen3:1.7b", False, "rag", None),
    "rag_synthesizer_api_key": ("", True, "rag", None),

    # System
    "log_level":            ("INFO", False, "system", _validate_log_level),
    "log_retention_days":   ("30", False, "system", _validate_positive_int),

    # Slumber Cycle (cognitive telemetry)
    "slumber_idle_threshold":  ("300", False, "system", _validate_positive_int),
    "slumber_batch_size":      ("20",  False, "system", _validate_positive_int),
    "slumber_evaluator":       ("heuristic", False, "system", None),
    "slumber_prune_age_days":  ("7",   False, "system", _validate_positive_int),
}

# Backward-compat alias
DEFAULTS = {k: (v[0], v[1]) for k, v in SETTINGS_REGISTRY.items()}


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
        logger.warning("Failed to base64-decode setting value, returning as-is")
        return value  # Return as-is if not valid base64


def init_settings():
    """Insert default settings if they don't exist yet. Call on app startup.

    Uses INSERT OR IGNORE for new keys. For keys with non-empty defaults,
    also backfills if the stored value is empty (handles new defaults added
    after initial setup). Also migrates stale defaults from previous versions.
    """
    # Stale defaults from pre-R14: update ONLY if stored value matches old default
    # (user never manually changed it). Safe: won't touch user-customized values.
    _STALE_DEFAULTS = [
        ("chat_provider", "anthropic"),
        ("chat_model", "claude-sonnet-4-20250514"),
        ("chat_model", "nemotron-3-nano:latest"),
        ("ollama_num_ctx", "32768"),
        ("claude_export_json_dir", "/data/claude_export"),
        ("janus_context_messages", "50"),
    ]

    with get_connection() as conn:
        # Migrate stale defaults
        for key, old_value in _STALE_DEFAULTS:
            new_reg = SETTINGS_REGISTRY.get(key)
            if not new_reg:
                continue
            new_value = new_reg[0]
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = ? AND value = ?",
                (new_value, key, old_value)
            )

        # Remove defunct settings
        conn.execute("DELETE FROM settings WHERE key = 'ingestion_quest_dir'")
        conn.execute("DELETE FROM settings WHERE key = 'claude_export_db_path'")

        for key, (default_value, is_secret, _cat, _val) in SETTINGS_REGISTRY.items():
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
    """Get a setting value. Decodes secrets automatically.

    Args:
        key: Setting key name.

    Returns:
        The setting value as a string, or the default if not found.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value, is_secret FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        reg = SETTINGS_REGISTRY.get(key)
        return reg[0] if reg else ""
    value, is_secret = row["value"], row["is_secret"]
    if is_secret:
        return _decode(value)
    return value


def set_setting(key: str, value: str) -> str:
    """Set a setting value. Validates and encodes secrets automatically.

    Args:
        key: Setting key name.
        value: New value to store.

    Returns:
        Empty string on success, error message string on validation failure.
    """
    reg = SETTINGS_REGISTRY.get(key)
    if reg:
        _default, is_secret, _cat, validator = reg
        # Validate if a validator is defined
        if validator:
            error = validator(value)
            if error:
                logger.warning("Setting validation failed for '%s': %s", key, error)
                return error
    else:
        is_secret = False

    stored = _encode(value) if is_secret else value
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO settings (key, value, is_secret)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, stored, int(is_secret))
        )
        conn.commit()
    return ""


def get_all_settings() -> dict:
    """Get all settings as a dict. Secrets are decoded."""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value, is_secret FROM settings").fetchall()
    result = {}
    for row in rows:
        value = _decode(row["value"]) if row["is_secret"] else row["value"]
        result[row["key"]] = value
    return result


def get_settings_by_category(category: str) -> dict:
    """Get all settings for a given category.

    Args:
        category: One of 'chat', 'ollama', 'export', 'ingestion', 'rag', 'system'.

    Returns:
        Dict of {key: value} for settings in that category.
    """
    keys = [k for k, v in SETTINGS_REGISTRY.items() if v[2] == category]
    result = {}
    for key in keys:
        result[key] = get_setting(key)
    return result
