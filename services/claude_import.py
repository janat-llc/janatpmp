"""Import Claude conversations.json into JANATPMP conversations + messages tables.

Reads the Claude export format and converts each conversation into the triplet
schema (user_prompt + model_reasoning + model_response) designed for fine-tuning
data extraction.
"""

import json
import logging
from pathlib import Path
from db.operations import get_connection
from db.chat_operations import get_conversation_by_uri

logger = logging.getLogger(__name__)


# =============================================================================
# CONTENT EXTRACTION
# =============================================================================

def _extract_content(content_blocks: list[dict]) -> dict:
    """Split content[] blocks into typed buckets.

    Args:
        content_blocks: List of content block dicts from a chat_message.

    Returns:
        Dict with keys: thinking (str), text (str), tools (list[str]).
    """
    thinking_parts = []
    text_parts = []
    tools = []

    for block in content_blocks:
        btype = block.get("type", "")
        if btype == "thinking":
            val = block.get("thinking", "")
            if val:
                thinking_parts.append(val)
        elif btype == "text":
            val = block.get("text", "")
            if val:
                text_parts.append(val)
        elif btype == "tool_use":
            name = block.get("name", "")
            if name:
                tools.append(name)
        # Skip tool_result and token_budget

    return {
        "thinking": "\n".join(thinking_parts),
        "text": "\n".join(text_parts),
        "tools": tools,
    }


# =============================================================================
# TRIPLET BUILDER
# =============================================================================

def _build_triplets(chat_messages: list[dict]) -> list[dict]:
    """Pair human/assistant messages into triplet rows.

    Rules:
    - human message starts a new triplet (user_prompt)
    - Following assistant message(s) complete it (reasoning + response + tools)
    - Multiple consecutive assistants merge into the same triplet
    - Human with no assistant reply -> empty model_response
    - Leading assistant with no human -> skipped

    Args:
        chat_messages: The chat_messages array from a conversation object.

    Returns:
        List of triplet dicts with keys: user_prompt, model_reasoning,
        model_response, tools_called.
    """
    triplets = []
    current = None

    for msg in chat_messages:
        sender = msg.get("sender", "")
        content_blocks = msg.get("content", [])

        if sender == "human":
            # Flush previous triplet if any
            if current is not None:
                triplets.append(current)

            # Extract human text (use text field first, fall back to content blocks)
            human_text = msg.get("text", "")
            if not human_text and content_blocks:
                extracted = _extract_content(content_blocks)
                human_text = extracted["text"]

            current = {
                "user_prompt": human_text,
                "model_reasoning": "",
                "model_response": "",
                "tools_called": [],
            }

        elif sender == "assistant":
            extracted = _extract_content(content_blocks)

            if current is None:
                # Leading assistant with no human — skip
                continue

            # Append to current triplet (handles consecutive assistants)
            if extracted["thinking"]:
                if current["model_reasoning"]:
                    current["model_reasoning"] += "\n" + extracted["thinking"]
                else:
                    current["model_reasoning"] = extracted["thinking"]

            if extracted["text"]:
                if current["model_response"]:
                    current["model_response"] += "\n" + extracted["text"]
                else:
                    current["model_response"] = extracted["text"]

            current["tools_called"].extend(extracted["tools"])

    # Flush final triplet
    if current is not None:
        triplets.append(current)

    return triplets


# =============================================================================
# SINGLE CONVERSATION IMPORT
# =============================================================================

def _import_single_conversation(
    conv_data: dict,
    skip_existing: bool = True,
) -> tuple[bool, int]:
    """Import one conversation into JANATPMP.

    Args:
        conv_data: A single conversation object from conversations.json.
        skip_existing: Skip if conversation_uri already exists in DB.

    Returns:
        Tuple of (was_imported, message_count).
    """
    uri = conv_data.get("uuid", "")

    # Check for existing
    if skip_existing and uri:
        existing = get_conversation_by_uri(uri)
        if existing:
            return False, 0

    title = conv_data.get("name", "") or "Untitled"
    created_at = conv_data.get("created_at", "")
    updated_at = conv_data.get("updated_at", "")
    chat_messages = conv_data.get("chat_messages", [])

    triplets = _build_triplets(chat_messages)

    # Create conversation row directly (need conversation_uri which
    # create_conversation() doesn't support)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations
                (title, source, provider, model, conversation_uri,
                 is_active, message_count, created_at, updated_at)
            VALUES (?, 'claude_export', 'anthropic', 'claude', ?,
                    1, 0, ?, ?)
        """, (
            title, uri,
            created_at[:19].replace("T", " ") if created_at else None,
            updated_at[:19].replace("T", " ") if updated_at else None,
        ))
        conv_rowid = cursor.lastrowid
        cursor.execute("SELECT id FROM conversations WHERE rowid = ?", (conv_rowid,))
        row = cursor.fetchone()
        conv_id = row["id"] if row else ""

        # Insert triplet messages
        for seq, triplet in enumerate(triplets, start=1):
            tools_json = json.dumps(triplet["tools_called"]) if triplet["tools_called"] else "[]"
            cursor.execute("""
                INSERT INTO messages
                    (conversation_id, sequence, user_prompt, model_reasoning,
                     model_response, provider, model, tools_called)
                VALUES (?, ?, ?, ?, ?, 'anthropic', 'claude', ?)
            """, (
                conv_id, seq,
                triplet["user_prompt"],
                triplet["model_reasoning"],
                triplet["model_response"],
                tools_json,
            ))

        conn.commit()

    return True, len(triplets)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def import_conversations_json(file_path: str, skip_existing: bool = True) -> dict:
    """Import conversations from a Claude export conversations.json file.

    Args:
        file_path: Path to conversations.json
        skip_existing: If True, skip conversations whose UUID already exists
                       (checks conversation_uri). If False, import all.

    Returns:
        Dict with keys: imported, skipped, errors, total_messages
    """
    path = Path(file_path)
    if not path.exists():
        return {"imported": 0, "skipped": 0, "errors": [f"File not found: {file_path}"], "total_messages": 0}

    with open(path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    imported = 0
    skipped = 0
    total_messages = 0
    errors = []

    for conv in conversations:
        try:
            was_imported, msg_count = _import_single_conversation(conv, skip_existing)
            if was_imported:
                imported += 1
                total_messages += msg_count
            else:
                skipped += 1
        except Exception as e:
            name = conv.get("name", conv.get("uuid", "unknown"))
            logger.error("Import failed for '%s': %s", name[:40], e)
            errors.append(f"{name[:40]}: {str(e)}")

    logger.info("Claude import: %d imported, %d skipped, %d errors, %d messages",
                imported, skipped, len(errors), total_messages)
    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_messages": total_messages,
    }
