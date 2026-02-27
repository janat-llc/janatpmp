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


def add_message_metadata(
    message_id: str,
    latency_total_ms: int = 0,
    latency_rag_ms: int = 0,
    latency_inference_ms: int = 0,
    rag_hit_count: int = 0,
    rag_hits_used: int = 0,
    rag_collections: str = "[]",
    rag_avg_rerank: float = 0.0,
    rag_avg_salience: float = 0.0,
    rag_scores: str = "[]",
    keywords: str = "[]",
    labels: str = "[]",
    quality_score: float = None,
    system_prompt_length: int = 0,
    rag_context_text: str = "",
    rag_synthesized: int = 0,
    cognition_prompt_layers: str = "",
    cognition_graph_trace: str = "",
    eval_rationale: str = "",
    eval_emotional_register: str = "",
    eval_provider: str = "",
    eval_model: str = "",
    cognition_precognition: str = "",
) -> str:
    """Add metadata for a message (timing, RAG snapshot, labels, pipeline observability).

    Args:
        message_id: The message this metadata belongs to
        latency_total_ms: Total wall-clock time in milliseconds
        latency_rag_ms: RAG retrieval time in milliseconds
        latency_inference_ms: Provider inference time in milliseconds
        rag_hit_count: Total ANN candidates returned
        rag_hits_used: Results that passed rerank/threshold
        rag_collections: JSON array of collection names searched
        rag_avg_rerank: Average rerank score of used hits
        rag_avg_salience: Average salience of used hits
        rag_scores: JSON array of per-hit score objects
        keywords: JSON array of extracted keywords
        labels: JSON array of user/system labels
        quality_score: Quality score (0.0-1.0), set by Slumber Cycle
        system_prompt_length: Length of composed system prompt in chars
        rag_context_text: RAG context text injected into system prompt
        rag_synthesized: 1 if RAG context was synthesized, 0 if raw chunks
        cognition_prompt_layers: JSON of prompt layer breakdown (R21)
        cognition_graph_trace: JSON of graph ranking trace (R21)
        eval_rationale: 1-2 sentence evaluation rationale from Slumber (R22)
        eval_emotional_register: Detected emotional tone (R22)
        eval_provider: Provider that performed evaluation (R22)
        eval_model: Model that performed evaluation (R22)
        cognition_precognition: JSON of pre-cognition trace (R25)

    Returns:
        The ID of the created metadata record
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages_metadata
                (message_id, latency_total_ms, latency_rag_ms, latency_inference_ms,
                 rag_hit_count, rag_hits_used, rag_collections,
                 rag_avg_rerank, rag_avg_salience, rag_scores,
                 keywords, labels, quality_score,
                 system_prompt_length, rag_context_text, rag_synthesized,
                 cognition_prompt_layers, cognition_graph_trace,
                 eval_rationale, eval_emotional_register, eval_provider, eval_model,
                 cognition_precognition)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id, latency_total_ms, latency_rag_ms, latency_inference_ms,
            rag_hit_count, rag_hits_used, rag_collections,
            rag_avg_rerank, rag_avg_salience, rag_scores,
            keywords, labels, quality_score,
            system_prompt_length, rag_context_text, rag_synthesized,
            cognition_prompt_layers, cognition_graph_trace,
            eval_rationale, eval_emotional_register, eval_provider, eval_model,
            cognition_precognition,
        ))
        conn.commit()
        cursor.execute("SELECT id FROM messages_metadata WHERE rowid = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return row['id'] if row else ""


def get_message_metadata(message_id: str) -> dict:
    """Get metadata for a message.

    Args:
        message_id: The message ID to look up metadata for

    Returns:
        Dict with metadata fields or empty dict if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM messages_metadata WHERE message_id = ?",
            (message_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else {}


def update_message_metadata(
    message_id: str,
    keywords: str = "",
    labels: str = "",
    quality_score: float = -1.0,
    rag_scores: str = "",
    salience_synced: int = -1,
    eval_rationale: str = "",
    eval_emotional_register: str = "",
    eval_provider: str = "",
    eval_model: str = "",
) -> str:
    """Update metadata fields for a message.

    Args:
        message_id: The message ID whose metadata to update
        keywords: JSON array of keywords (empty = no change)
        labels: JSON array of labels (empty = no change)
        quality_score: Quality score 0.0-1.0 (negative = no change)
        rag_scores: Updated JSON array of per-hit scores (empty = no change)
        salience_synced: Set to 1 after Slumber propagates quality to Qdrant salience (negative = no change)
        eval_rationale: Evaluation rationale text (empty = no change, R22)
        eval_emotional_register: Detected emotional tone (empty = no change, R22)
        eval_provider: Provider that performed evaluation (empty = no change, R22)
        eval_model: Model that performed evaluation (empty = no change, R22)

    Returns:
        Success or error message
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        updates = []
        params = []
        if keywords:
            updates.append("keywords = ?")
            params.append(keywords)
        if labels:
            updates.append("labels = ?")
            params.append(labels)
        if quality_score >= 0:
            updates.append("quality_score = ?")
            params.append(quality_score)
        if rag_scores:
            updates.append("rag_scores = ?")
            params.append(rag_scores)
        if salience_synced >= 0:
            updates.append("salience_synced = ?")
            params.append(salience_synced)
        if eval_rationale:
            updates.append("eval_rationale = ?")
            params.append(eval_rationale)
        if eval_emotional_register:
            updates.append("eval_emotional_register = ?")
            params.append(eval_emotional_register)
        if eval_provider:
            updates.append("eval_provider = ?")
            params.append(eval_provider)
        if eval_model:
            updates.append("eval_model = ?")
            params.append(eval_model)
        if not updates:
            return "No updates provided"
        params.append(message_id)
        query = f"UPDATE messages_metadata SET {', '.join(updates)} WHERE message_id = ?"
        cursor.execute(query, params)
        conn.commit()
        return f"Updated metadata for message {message_id}" if cursor.rowcount > 0 else f"Metadata for message {message_id} not found"


def get_recent_introspection(limit: int = 10) -> dict:
    """Query recent Slumber evaluations for Janus self-awareness.

    Returns summary of recent quality scores and top keywords from the active
    Janus conversation's messages_metadata. Used by the prompt composer to
    give Janus awareness of her own processing.

    Args:
        limit: Number of recent evaluated messages to consider.

    Returns:
        Dict with keys: evaluated_count, avg_quality, top_keywords, recent_scores.
        Returns empty dict if no evaluated messages exist.
    """
    from services.settings import get_setting
    import json
    from collections import Counter

    janus_id = get_setting("janus_conversation_id")
    if not janus_id:
        return {}

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT mm.quality_score, mm.keywords,
                      mm.eval_rationale, mm.eval_emotional_register
               FROM messages_metadata mm
               JOIN messages m ON mm.message_id = m.id
               WHERE m.conversation_id = ?
                 AND mm.quality_score IS NOT NULL
               ORDER BY m.created_at DESC
               LIMIT ?""",
            (janus_id, limit),
        ).fetchall()

    if not rows:
        return {}

    scores = [r["quality_score"] for r in rows]
    keyword_counter = Counter()
    for row in rows:
        try:
            kws = json.loads(row["keywords"] or "[]")
            keyword_counter.update(kws)
        except Exception:
            pass

    recent_rationales = [
        r["eval_rationale"] for r in rows if r["eval_rationale"]
    ]
    emotional_registers = [
        r["eval_emotional_register"] for r in rows if r["eval_emotional_register"]
    ]

    return {
        "evaluated_count": len(scores),
        "avg_quality": round(sum(scores) / len(scores), 2),
        "top_keywords": [kw for kw, _ in keyword_counter.most_common(5)],
        "recent_scores": scores,
        "recent_rationales": recent_rationales[:3],
        "emotional_registers": emotional_registers,
    }


def get_knowledge_state() -> dict:
    """Aggregate Janus's knowledge substrate stats for self-awareness.

    Queries across SQLite (entities, documents) and Neo4j (graph stats).
    Each data source is isolated — failure in one doesn't block others.

    Returns:
        Dict with keys: entity_count, entity_types, recent_entities,
        graph_node_count, graph_edge_types, dream_count, recent_dreams,
        salience_stats. Empty sub-dicts on failure.
    """
    state = {}

    # Entity awareness (SQLite)
    try:
        with get_connection() as conn:
            state["entity_count"] = conn.execute(
                "SELECT COUNT(*) FROM entities").fetchone()[0]
            type_rows = conn.execute(
                "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
            ).fetchall()
            state["entity_types"] = {r[0]: r[1] for r in type_rows}
            recent = conn.execute(
                "SELECT name FROM entities ORDER BY last_seen_at DESC LIMIT 5"
            ).fetchall()
            state["recent_entities"] = [r[0] for r in recent]
            sal = conn.execute(
                "SELECT MIN(salience), MAX(salience), AVG(salience) "
                "FROM entities WHERE salience IS NOT NULL"
            ).fetchone()
            if sal and sal[0] is not None:
                state["salience_stats"] = {
                    "min": round(sal[0], 3), "max": round(sal[1], 3),
                    "avg": round(sal[2], 3),
                }
    except Exception:
        state.setdefault("entity_count", 0)

    # Dream awareness (SQLite documents)
    try:
        with get_connection() as conn:
            state["dream_count"] = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE doc_type='agent_output'"
            ).fetchone()[0]
            recent_dreams = conn.execute(
                "SELECT title FROM documents WHERE doc_type='agent_output' "
                "ORDER BY created_at DESC LIMIT 3"
            ).fetchall()
            state["recent_dreams"] = [r[0] for r in recent_dreams]
    except Exception:
        state.setdefault("dream_count", 0)

    # Graph awareness (Neo4j)
    try:
        from graph.graph_service import graph_stats
        gstats = graph_stats()
        if isinstance(gstats, dict):
            state["graph"] = gstats
    except Exception:
        state["graph"] = {}

    return state


def backfill_message_metadata(batch_size: int = 500) -> str:
    """Create messages_metadata rows for messages that don't have them.

    Many imported messages (Claude Export, Google AI Studio) lack metadata
    rows because they were imported before R12's cognitive telemetry was
    added. This function creates empty rows (quality_score = NULL) so
    the Slumber Cycle's evaluate phase can score them naturally.

    Safe to call multiple times — uses INSERT OR IGNORE.

    Args:
        batch_size: Max rows to create per call (default 500).

    Returns:
        Status message with count of rows created.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO messages_metadata (message_id)
               SELECT id FROM messages
               WHERE id NOT IN (SELECT message_id FROM messages_metadata)
               LIMIT ?""",
            (batch_size,),
        )
        created = cursor.rowcount
        conn.commit()

    total = 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE id NOT IN "
            "(SELECT message_id FROM messages_metadata)"
        ).fetchone()
        total = row["cnt"] if row else 0

    return f"Created {created} metadata rows. {total} messages still remaining."


def get_messages(conversation_id: str, limit: int = 100, latest: bool = False) -> list:
    """Get messages for a conversation ordered by sequence.

    Args:
        conversation_id: The conversation ID
        limit: Maximum messages to return
        latest: If True, return the last N messages instead of the first N

    Returns:
        List of message dicts ordered by sequence (ascending)
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if latest:
            cursor.execute("""
                SELECT * FROM (
                    SELECT * FROM messages
                    WHERE conversation_id = ?
                    ORDER BY sequence DESC
                    LIMIT ?
                ) sub ORDER BY sequence ASC
            """, (conversation_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY sequence ASC
                LIMIT ?
            """, (conversation_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_message(message_id: str) -> dict:
    """Get a single message by ID with full triplet fields.

    Args:
        message_id: The message ID to retrieve.

    Returns:
        Dict with all message fields (id, conversation_id, sequence,
        user_prompt, model_reasoning, model_response, provider, model,
        tokens_prompt, tokens_reasoning, tokens_response, tools_called,
        created_at). Empty dict if not found.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    return dict(row) if row else {}


# =============================================================================
# JANUS — Continuous Chat Lifecycle
# =============================================================================

def get_or_create_janus_conversation() -> str:
    """Get the Janus conversation ID, creating it on first boot.

    Checks the janus_conversation_id setting. If empty or pointing to a
    non-existent conversation, creates a new one with title "Janus" and
    stores the ID in settings.

    Returns:
        The Janus conversation ID (hex string).
    """
    from services.settings import get_setting, set_setting

    janus_id = get_setting("janus_conversation_id")
    if janus_id:
        conv = get_conversation(janus_id)
        if conv:
            return janus_id

    # Create fresh Janus conversation with current defaults
    provider = get_setting("chat_provider") or "ollama"
    model = get_setting("chat_model") or "qwen3:32b"
    janus_id = create_conversation(
        provider=provider,
        model=model,
        title="Janus",
        source="platform",
    )
    set_setting("janus_conversation_id", janus_id)
    return janus_id


def archive_janus_conversation(janus_conv_id: str) -> str:
    """Archive the current Janus conversation and create a fresh one.

    Sets is_active=0 on the current Janus conversation, renames it to
    "Janus — Chapter N", creates a new Janus conversation, and updates
    the janus_conversation_id setting.

    Args:
        janus_conv_id: Current Janus conversation ID to archive.

    Returns:
        The new Janus conversation ID (hex string).
    """
    from services.settings import get_setting, set_setting

    # Count existing archived chapters for numbering
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM conversations WHERE title LIKE 'Janus%' AND is_active = 0"
        )
        chapter_num = cursor.fetchone()[0] + 1

        # Archive the current conversation
        cursor.execute(
            "UPDATE conversations SET title = ?, is_active = 0 WHERE id = ?",
            (f"Janus \u2014 Chapter {chapter_num}", janus_conv_id)
        )
        conn.commit()

    # Create fresh Janus conversation
    provider = get_setting("chat_provider") or "ollama"
    model = get_setting("chat_model") or "qwen3:32b"
    new_id = create_conversation(
        provider=provider,
        model=model,
        title="Janus",
        source="platform",
    )
    set_setting("janus_conversation_id", new_id)
    return new_id


# ---------------------------------------------------------------------------
# Conversation Stream (real-time message access)
# ---------------------------------------------------------------------------

def get_conversation_stream(conversation_id: str, limit: int = 20) -> list:
    """Get the most recent messages from a conversation, newest first.

    Stream-friendly wrapper around get_messages() with defaults tuned for
    reading a live conversation tail: small limit, reverse chronological order.

    Args:
        conversation_id: The conversation ID (hex string)
        limit: Maximum number of messages to return (default 20)

    Returns:
        List of message dicts, newest first
    """
    messages = get_messages(conversation_id, limit=limit, latest=True)
    messages.reverse()
    return messages


def get_janus_stream(limit: int = 20) -> list:
    """Get the most recent messages from the active Janus conversation.

    Convenience shortcut that auto-resolves the active Janus conversation ID
    then returns the latest messages newest-first. Ideal for MCP clients that
    need quick access to what Janus actually said.

    Args:
        limit: Maximum number of messages to return (default 20)

    Returns:
        List of message dicts from Janus, newest first
    """
    janus_id = get_or_create_janus_conversation()
    return get_conversation_stream(janus_id, limit=limit)
