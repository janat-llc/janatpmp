"""
Chat operations for JANATPMP.
CRUD functions for Conversations and Messages (triplet schema).
Each function has proper docstrings for MCP tool generation.
"""

import re
import json
from db.operations import get_connection


# =============================================================================
# REASONING PARSER
# =============================================================================

def parse_reasoning(raw_response: str) -> tuple[str, str]:
    """Extract reasoning from model response.

    Handles multiple formats:
    - <think>...</think> blocks (deepseek-r1)
    - Content before a lone </think> tag (Nemotron — Ollama template injects
      the opening <think>, so model output starts with thinking and only has </think>)
    - <reasoning>...</reasoning> blocks

    Args:
        raw_response: The raw model response text

    Returns:
        Tuple of (reasoning, clean_response) where reasoning is the
        extracted chain-of-thought and clean_response is the visible reply
    """
    if not raw_response:
        return "", ""

    reasoning_parts = []

    # Extract <think>...</think> blocks (paired tags)
    think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    for match in think_pattern.finditer(raw_response):
        reasoning_parts.append(match.group(1).strip())
    clean = think_pattern.sub("", raw_response)

    # Handle missing opening <think>: content before a lone </think> is reasoning
    # (Nemotron via Ollama — template injects <think>, model only outputs </think>)
    if "</think>" in clean and "<think>" not in clean:
        parts = clean.split("</think>", 1)
        if parts[0].strip():
            reasoning_parts.append(parts[0].strip())
        clean = parts[1] if len(parts) > 1 else ""

    # Extract <reasoning>...</reasoning> blocks
    reasoning_pattern = re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL)
    for match in reasoning_pattern.finditer(clean):
        reasoning_parts.append(match.group(1).strip())
    clean = reasoning_pattern.sub("", clean)

    reasoning = "\n\n".join(reasoning_parts)
    return reasoning, clean.strip()


# =============================================================================
# CONVERSATION CRUD
# =============================================================================

def create_conversation(
    provider: str = "ollama",
    model: str = "hf.co/unsloth/Nemotron-3-Nano-30B-A3B-GGUF:IQ4_XS",
    system_prompt_append: str = "",
    temperature: float = 0.7,
    top_p: float = 0.9,
    max_tokens: int = 8192,
    title: str = "New Chat",
    source: str = "platform",
) -> str:
    """Create a new conversation.

    Args:
        provider: AI provider (anthropic, gemini, ollama)
        model: Model identifier
        system_prompt_append: Per-session system prompt addition
        temperature: Sampling temperature (0.0-2.0)
        top_p: Top-p nucleus sampling (0.0-1.0)
        max_tokens: Maximum response tokens
        title: Conversation title
        source: Source (platform, claude_export, imported)

    Returns:
        The ID of the created conversation
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations
                (provider, model, system_prompt_append, temperature, top_p, max_tokens, title, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (provider, model, system_prompt_append, temperature, top_p, max_tokens, title, source))
        conn.commit()
        cursor.execute("SELECT id FROM conversations WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_conversation(conversation_id: str) -> dict:
    """Get a single conversation by ID.

    Args:
        conversation_id: The unique conversation ID

    Returns:
        Dict with conversation data or empty dict if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_conversation_by_uri(conversation_uri: str) -> dict:
    """Get a conversation by its external URI (e.g. Claude Export UUID).

    Args:
        conversation_uri: The external conversation URI to look up

    Returns:
        Dict with conversation data or empty dict if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE conversation_uri = ?", (conversation_uri,))
        row = cursor.fetchone()
        return dict(row) if row else {}


def list_conversations(limit: int = 50, active_only: bool = True, title_filter: str = "", source: str = "", oldest_first: bool = False) -> list:
    """List conversations ordered by activity (newest first by default).

    Args:
        limit: Maximum number of conversations to return
        active_only: If true, only return active (non-archived) conversations
        title_filter: Filter by title substring (case-insensitive). Empty = no filter.
        source: Filter by source (platform, claude_export, imported). Empty = no filter.
        oldest_first: If true, sort oldest first instead of newest first.

    Returns:
        List of conversation dicts
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM conversations"
        conditions = []
        params = []
        if active_only:
            conditions.append("is_active = 1")
        if title_filter:
            conditions.append("title LIKE ?")
            params.append(f"%{title_filter}%")
        if source:
            conditions.append("source = ?")
            params.append(source)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        order = "ASC" if oldest_first else "DESC"
        query += f" ORDER BY updated_at {order} LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_conversation(
    conversation_id: str,
    title: str = "",
    system_prompt_append: str = "",
    is_active: int = -1,
    temperature: float = -1.0,
    top_p: float = -1.0,
    max_tokens: int = -1,
) -> str:
    """Update a conversation.

    Args:
        conversation_id: The conversation ID to update
        title: New title (empty = no change)
        system_prompt_append: New system prompt append (empty = no change)
        is_active: Set active status (0 or 1, -1 = no change)
        temperature: New temperature (-1 = no change)
        top_p: New top_p (-1 = no change)
        max_tokens: New max_tokens (-1 = no change)

    Returns:
        Success message or error
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if title:
            updates.append("title = ?")
            params.append(title)
        if system_prompt_append:
            updates.append("system_prompt_append = ?")
            params.append(system_prompt_append)
        if is_active >= 0:
            updates.append("is_active = ?")
            params.append(is_active)
        if temperature >= 0:
            updates.append("temperature = ?")
            params.append(temperature)
        if top_p >= 0:
            updates.append("top_p = ?")
            params.append(top_p)
        if max_tokens >= 0:
            updates.append("max_tokens = ?")
            params.append(max_tokens)

        if not updates:
            return "No updates provided"

        params.append(conversation_id)
        query = f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return f"Updated conversation {conversation_id}" if cursor.rowcount > 0 else f"Conversation {conversation_id} not found"


def delete_conversation(conversation_id: str) -> str:
    """Delete a conversation and all its messages.

    Args:
        conversation_id: The conversation ID to delete

    Returns:
        Success message or error
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        return f"Deleted conversation {conversation_id}" if cursor.rowcount > 0 else f"Conversation {conversation_id} not found"


def search_conversations(query: str, limit: int = 50) -> list:
    """Full-text search across conversation messages.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        List of matching conversations with snippet context
    """
    # Wrap in double quotes so FTS5 treats special chars (. * - etc.) as literals
    safe_query = '"' + query.replace('"', '""') + '"'
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT c.*
            FROM conversations c
            JOIN messages m ON c.id = m.conversation_id
            JOIN messages_fts ON m.id = messages_fts.id
            WHERE messages_fts MATCH ?
            ORDER BY c.updated_at DESC
            LIMIT ?
        """, (safe_query, limit))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# MESSAGE CRUD
# =============================================================================

def get_next_sequence(conversation_id: str) -> int:
    """Get the next sequence number for a conversation.

    Args:
        conversation_id: The conversation ID

    Returns:
        Next sequence number (1-based)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        )
        return cursor.fetchone()[0]


def add_message(
    conversation_id: str,
    user_prompt: str,
    model_reasoning: str = None,
    model_response: str = "",
    provider: str = "",
    model: str = "",
    tokens_prompt: int = 0,
    tokens_reasoning: int = 0,
    tokens_response: int = 0,
    tools_called: str = "[]",
) -> str:
    """Add a message (triplet) to a conversation.

    Args:
        conversation_id: The conversation this message belongs to
        user_prompt: The user's prompt text
        model_reasoning: Chain-of-thought / thinking tokens
        model_response: The visible model reply
        provider: Provider that generated this response
        model: Model that generated this response
        tokens_prompt: Token count for the prompt
        tokens_reasoning: Token count for reasoning
        tokens_response: Token count for response
        tools_called: JSON array of tool names used this turn

    Returns:
        The ID of the created message
    """
    seq = get_next_sequence(conversation_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages
                (conversation_id, sequence, user_prompt, model_reasoning, model_response,
                 provider, model, tokens_prompt, tokens_reasoning, tokens_response, tools_called)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            conversation_id, seq, user_prompt, model_reasoning, model_response,
            provider, model, tokens_prompt, tokens_reasoning, tokens_response, tools_called,
        ))
        conn.commit()
        cursor.execute("SELECT id FROM messages WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_messages(conversation_id: str, limit: int = 100) -> list:
    """Get messages for a conversation ordered by sequence.

    Args:
        conversation_id: The conversation ID
        limit: Maximum messages to return

    Returns:
        List of message dicts ordered by sequence
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY sequence ASC
            LIMIT ?
        """, (conversation_id, limit))
        return [dict(row) for row in cursor.fetchall()]
