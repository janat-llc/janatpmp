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


def _validate_float(value: str) -> str | None:
    """Validate that value is any float (including negative).

    Args:
        value: String to validate.

    Returns:
        Error message string if invalid, None if valid.
    """
    if not value:
        return None
    try:
        float(value)
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
    "chat_model":           ("qwen3.5:27b", False, "chat", None),
    "chat_api_key":         ("", True, "chat", None),
    "chat_base_url":        ("http://ollama:11434/v1", False, "chat", None),
    "chat_system_prompt":   ("", False, "chat", None),
    "chat_temperature":     ("0.7", False, "chat", _validate_positive_float),
    "chat_top_p":           ("0.9", False, "chat", _validate_positive_float),
    "chat_max_tokens":      ("8192", False, "chat", _validate_positive_int),
    "response_cleanup_enabled": ("true", False, "chat", None),

    # Ollama
    "ollama_num_ctx":       ("32768", False, "ollama", _validate_positive_int),
    "ollama_keep_alive":    ("-1", False, "ollama", None),

    # Janus (continuous chat)
    "janus_conversation_id":  ("", False, "chat", None),
    "janus_monologue_id":     ("", False, "chat", None),
    "janus_context_messages": ("10", False, "chat", _validate_positive_int),
    "janus_display_turns":    ("20", False, "chat", _validate_positive_int),

    # Export
    "claude_export_json_dir": ("/app/imports/claude", False, "export", None),

    # Ingestion
    "ingestion_google_ai_dir": ("/app/imports/google_ai", False, "ingestion", None),
    "ingestion_markdown_dir":  ("/app/imports/markdown", False, "ingestion", None),
    "auto_import_threshold_hours": ("24", False, "ingestion", _validate_positive_int),

    # RAG
    "qdrant_url":           ("http://janatpmp-qdrant:6333", False, "rag", None),
    "rag_score_threshold":  ("0.3", False, "rag", _validate_positive_float),
    "rag_rerank_threshold": ("0.3", False, "rag", _validate_float_0_1),
    "rag_max_chunks":       ("10", False, "rag", _validate_positive_int),
    "rag_synthesizer_provider": ("ollama", False, "rag", None),
    "rag_synthesizer_model": ("qwen3.5:27b", False, "rag", None),
    "rag_synthesizer_api_key": ("", True, "rag", None),

    # Chunking (R16)
    "chunk_max_chars":            ("2500", False, "rag", _validate_positive_int),
    "chunk_min_chars":            ("200",  False, "rag", _validate_positive_int),
    "chunk_overlap_chars":        ("200",  False, "rag", _validate_positive_int),
    "chunk_threshold":            ("3000", False, "rag", _validate_positive_int),
    "rag_max_chunks_per_message": ("3",    False, "rag", _validate_positive_int),

    # System — Location (R17 Temporal Affinity Engine)
    "location_lat":         ("46.8290", False, "system", _validate_float),
    "location_lon":         ("-96.8540", False, "system", _validate_float),
    "location_name":        ("3351 Washington Street South, Fargo, ND 58104", False, "system", None),
    "location_tz":          ("America/Chicago", False, "system", None),

    # System
    "log_level":            ("INFO", False, "system", _validate_log_level),
    "log_retention_days":   ("30", False, "system", _validate_positive_int),

    # Slumber Cycle (cognitive telemetry)
    "slumber_idle_threshold":  ("300", False, "system", _validate_positive_int),
    "slumber_batch_size":      ("20",  False, "system", _validate_positive_int),
    "slumber_evaluator":       ("heuristic", False, "system", None),
    "slumber_prune_age_days":  ("7",   False, "system", _validate_positive_int),

    # Slumber Evaluation (R22: First Light)
    "slumber_eval_provider":   ("gemini", False, "system", None),
    "slumber_eval_model":      ("gemini-2.5-flash-lite", False, "system", None),
    "slumber_eval_enabled":    ("true", False, "system", None),

    # Dream Synthesis (R24)
    "slumber_dream_enabled":      ("true", False, "system", None),
    "slumber_dream_min_quality":  ("0.7",  False, "system", _validate_float_0_1),

    # Graph Weave (R27)
    "last_graph_weave_at":        ("", False, "system", None),

    # Pre-Cognition (R25)
    "precognition_enabled":    ("true", False, "system", None),
    "precognition_timeout_ms": ("3000", False, "system", _validate_positive_int),

    # Post-Cognition (R33)
    "postcognition_enabled":   ("true", False, "system", None),

    # Janus Identity (R19)
    "janus_lifecycle_state":   ("sleeping", False, "system", None),
    "janus_identity_version":  ("r19-v1", False, "system", None),

    # Co-occurrence Linking (R31)
    "cooccurrence_watermark":  ("0", False, "system", None),
    # Conversation-scope CO_OCCURS_WITH weaving (R51)
    "conv_cooccurrence_watermark": ("0", False, "system", None),

    # Batch Ingestion IDF normalization (R52)
    # Transient comma-separated batch stopwords — set before ingestion, cleared after
    "batch_extraction_stopwords": ("", False, "ingestion", None),

    # Register Mining (R32: The Mirror)
    "register_mining_provider":  ("gemini", False, "system", None),
    "register_mining_model":     ("gemini-2.5-flash-lite", False, "system", None),
    "register_mining_enabled":   ("true", False, "system", None),
    "register_mining_watermark": ("0", False, "system", None),

    # Intent Engine (R35)
    "intent_engine_enabled":            ("true",  False, "system", None),
    "intent_retrospective_interval":    ("5",     False, "system", _validate_positive_int),
    "intent_hypothesis_window":         ("10",    False, "system", _validate_positive_int),
    "intent_hypothesis_ema_weight":     ("0.3",   False, "system", _validate_float_0_1),
    "intent_action_threshold_create":   ("0.8",   False, "system", _validate_float_0_1),
    "intent_action_threshold_update":   ("0.7",   False, "system", _validate_float_0_1),
    "intent_action_threshold_query":    ("0.5",   False, "system", _validate_float_0_1),
    "intent_action_dispatch_enabled":   ("true",  False, "system", None),
    "intent_dispatch_auto_threshold":   ("0.75",  False, "system", _validate_float_0_1),
    "intent_dispatch_confirm_threshold": ("0.5",  False, "system", _validate_float_0_1),

    # Persona (R18 structured schema)
    "user_full_name":       ("", False, "persona", None),
    "user_preferred_name":  ("Mat", False, "persona", None),
    "user_birthdate":       ("", False, "persona", None),
    "user_family":          ("[]", False, "persona", None),
    "user_employer":        ("", False, "persona", None),
    "user_title":           ("", False, "persona", None),
    "user_health_notes":    ("", False, "persona", None),
    "user_interests":       ("", False, "persona", None),
    "user_values":          ("", False, "persona", None),
    "user_bio":             ("", False, "persona", None),
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
        ("chat_model", "qwen3-vl:8b"),
        ("chat_model", "gemma3:27b-it-qat"),
        ("rag_synthesizer_model", "qwen3:1.7b"),
        ("rag_synthesizer_model", "gemma3:1b"),
        ("ollama_num_ctx", "131072"),  # R15: 128K caused VRAM thrashing, 32K is plenty
        ("claude_export_json_dir", "/data/claude_export"),
        ("janus_context_messages", "50"),
        ("janus_lifecycle_state", "awake"),  # R19: reset to sleeping on every restart
        ("slumber_evaluator", "heuristic"),  # R22: superseded by slumber_eval_* settings
        ("slumber_eval_model", "gemini-2.0-flash-lite"),  # R22: deprecated, use 2.5
        ("precognition_timeout_ms", "500"),  # R25: 500ms too aggressive for Gemini cold start
        ("chat_model", "qwen3:32b"),  # Qwen 3.5 replaces Qwen 3 (smaller, faster, better tools)
        ("rag_synthesizer_model", "qwen3:32b"),
        ("intent_action_dispatch_enabled", "false"),  # R37: enable dispatch on existing installs
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

        # Migrate user_name → user_preferred_name (R18 persona schema)
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'user_name'"
        ).fetchone()
        if row and row[0]:
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, is_secret) "
                "VALUES ('user_preferred_name', ?, 0)",
                (row[0],)
            )

        # Remove defunct settings
        conn.execute("DELETE FROM settings WHERE key = 'ingestion_quest_dir'")
        conn.execute("DELETE FROM settings WHERE key = 'claude_export_db_path'")
        conn.execute("DELETE FROM settings WHERE key = 'user_name'")
        conn.execute("DELETE FROM settings WHERE key = 'user_preferences'")

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
