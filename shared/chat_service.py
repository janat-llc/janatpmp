"""Shared chat state — cross-page conversation tracking and config convenience.

This module provides the thin state layer that replaces gr.State bridges
between pages in the multipage architecture. Backend logic stays in
services/chat.py and db/chat_operations.py — this module only manages
the active conversation pointer and config convenience accessors.
"""

from services.settings import get_setting

# Module-level active conversation ID — shared across pages in the same process.
# Replaces the gr.State("active_conversation_id") that previously bridged tabs.
_active_conversation_id: str = ""


def get_active_conversation_id() -> str:
    """Return the currently active conversation ID (empty string if none)."""
    return _active_conversation_id


def set_active_conversation_id(conv_id: str) -> None:
    """Set the active conversation ID (called after creating or switching conversations)."""
    global _active_conversation_id
    _active_conversation_id = conv_id


def get_chat_config() -> dict:
    """Return current chat configuration from the settings DB.

    Returns:
        Dict with keys: provider, model, temperature, top_p, max_tokens,
        system_prompt, base_url.
    """
    return {
        "provider": get_setting("chat_provider"),
        "model": get_setting("chat_model"),
        "temperature": float(get_setting("chat_temperature") or 0.7),
        "top_p": float(get_setting("chat_top_p") or 0.9),
        "max_tokens": int(get_setting("chat_max_tokens") or 8192),
        "system_prompt": get_setting("chat_system_prompt"),
        "base_url": get_setting("chat_base_url"),
    }
