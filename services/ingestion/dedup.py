"""
Deduplication Utilities

Content-hash-based deduplication for detecting exact and near-exact duplicates
across imported conversations and documents.

Ported from: curators_loom/common/file_utils.py (calculate_content_hash, calculate_file_hash)
"""

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_content_hash(text: str) -> str:
    """
    SHA-256 hash of normalized text for exact-match deduplication.

    Normalization: lowercase, stripped whitespace, collapsed internal whitespace.
    This catches duplicates that differ only in casing or whitespace formatting.

    Args:
        text: Raw text content.

    Returns:
        Hex SHA-256 hash string.
    """
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_file_hash(file_path: str | Path) -> str:
    """
    SHA-256 hash of a file's raw bytes for file-level dedup.

    Reads in 4KB chunks to handle large files efficiently.

    Args:
        file_path: Path to the file.

    Returns:
        Hex SHA-256 hash string.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(4096):
            h.update(chunk)
    return h.hexdigest()


def compute_conversation_hash(turns: list[dict]) -> str:
    """
    SHA-256 hash of a conversation's turn content for conversation-level dedup.

    Hashes the concatenation of all user_prompt + model_response pairs.
    Ignores model_reasoning (thoughts) since those may vary between exports.

    Args:
        turns: List of turn dicts with 'user_prompt' and 'model_response' keys.

    Returns:
        Hex SHA-256 hash string.
    """
    parts = []
    for turn in turns:
        user = turn.get("user_prompt", "")
        response = turn.get("model_response", "")
        parts.append(f"U:{user}\nA:{response}")

    combined = "\n---\n".join(parts)
    return compute_content_hash(combined)


def find_exact_duplicates(items: list[dict], content_key: str = "content") -> list[tuple]:
    """
    Find pairs of items that are exact content matches.

    Args:
        items: List of dicts, each with an 'id' field and a content field.
        content_key: Key name for the content field to compare.

    Returns:
        List of (id_a, id_b) tuples for exact duplicates.
    """
    hash_map: dict[str, list] = {}

    for item in items:
        content = item.get(content_key, "")
        item_id = item.get("id")
        if not content or not item_id:
            continue

        h = compute_content_hash(content)
        hash_map.setdefault(h, []).append(item_id)

    duplicates = []
    for h, ids in hash_map.items():
        if len(ids) > 1:
            # Generate all pairs
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    duplicates.append((ids[i], ids[j]))

    if duplicates:
        logger.info(f"Found {len(duplicates)} duplicate pairs across {len(items)} items")

    return duplicates


def find_duplicate_conversations(conversations: list[dict]) -> list[tuple]:
    """
    Find pairs of conversations that are exact content matches based on turns.

    Args:
        conversations: List of conversation dicts, each with 'id' and 'turns' fields.

    Returns:
        List of (id_a, id_b) tuples for duplicate conversations.
    """
    hash_map: dict[str, list] = {}

    for conv in conversations:
        conv_id = conv.get("id")
        turns = conv.get("turns", [])
        if not conv_id or not turns:
            continue

        h = compute_conversation_hash(turns)
        hash_map.setdefault(h, []).append(conv_id)

    duplicates = []
    for h, ids in hash_map.items():
        if len(ids) > 1:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    duplicates.append((ids[i], ids[j]))

    if duplicates:
        logger.info(
            f"Found {len(duplicates)} duplicate conversation pairs "
            f"across {len(conversations)} conversations"
        )

    return duplicates
