"""
Ingestion Orchestrator

Bridges content parsers to database insertion. Each function:
  1. Parses files from a directory using the appropriate parser
  2. Deduplicates against existing DB records (title + source)
  3. Inserts new records via db/chat_operations.py or db/operations.py
  4. Returns summary statistics
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Map parser doc_type values → valid schema doc_type values
# Schema allows: conversation, file, artifact, research, agent_output, session_notes, code
_DOC_TYPE_MAP = {
    "chapter": "file",
    "essay": "research",
    "journal": "session_notes",
    "creative": "artifact",
    "project_doc": "file",
    "documentation": "file",
    "conversation": "conversation",
    "research": "research",
}

# Map parser source values → valid schema source values
# Schema allows: claude_exporter, upload, agent, generated, manual
_SOURCE_MAP = {
    "markdown": "upload",
    "text": "upload",
}


def ingest_google_ai_conversations(directory: str) -> dict:
    """Parse Google AI Studio JSON exports and insert as conversations.

    Args:
        directory: Path to directory containing Google AI Studio JSON files.

    Returns:
        Dict with keys: imported, skipped, errors, total_messages, total_files.
    """
    from db.chat_operations import create_conversation, add_message, list_conversations
    from .google_ai_studio import parse_google_ai_studio_directory

    parsed = parse_google_ai_studio_directory(directory)
    total_files = len(list(Path(directory).glob("*.json")))

    # Build dedup set: existing conversation titles with source='imported'
    existing = list_conversations(limit=9999, active_only=False)
    existing_titles = {
        c["title"] for c in existing if c.get("source") == "imported"
    }

    imported = 0
    skipped = 0
    errors: list[str] = []
    total_messages = 0

    for conv in parsed:
        title = conv["title"]
        if title in existing_titles:
            skipped += 1
            continue

        try:
            conv_id = create_conversation(
                provider="gemini",
                model=conv.get("model") or "unknown",
                system_prompt_append=conv.get("system_instruction") or "",
                title=title,
                source="imported",
            )

            for turn in conv["turns"]:
                add_message(
                    conversation_id=conv_id,
                    user_prompt=turn["user_prompt"],
                    model_reasoning=turn.get("model_reasoning") or "",
                    model_response=turn["model_response"],
                    provider="gemini",
                    model=conv.get("model") or "unknown",
                )
                total_messages += 1

            existing_titles.add(title)
            imported += 1

        except Exception as e:
            errors.append(f"{title[:40]}: {str(e)[:80]}")

    logger.info(
        f"Google AI ingestion: {imported} imported, {skipped} skipped, "
        f"{len(errors)} errors, {total_messages} messages"
    )

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_messages": total_messages,
        "total_files": total_files,
    }


def ingest_markdown_documents(directory: str) -> dict:
    """Parse markdown/text files and insert as documents.

    Args:
        directory: Path to directory containing .md and .txt files.

    Returns:
        Dict with keys: imported, skipped, errors, total_files.
    """
    from db.operations import create_document, list_documents
    from .markdown_ingest import ingest_directory

    parsed = ingest_directory(directory)
    total_files = len(parsed)

    # Build dedup set: existing document titles with source='upload'
    existing = list_documents(source="upload", limit=9999)
    existing_titles = {d["title"] for d in existing}

    imported = 0
    skipped = 0
    errors: list[str] = []

    for doc in parsed:
        title = doc["title"]
        if title in existing_titles:
            skipped += 1
            continue

        try:
            doc_type = _DOC_TYPE_MAP.get(doc["doc_type"], "file")
            source = _SOURCE_MAP.get(doc["source"], "upload")
            create_document(
                doc_type=doc_type,
                source=source,
                title=title,
                content=doc["content"],
            )
            existing_titles.add(title)
            imported += 1

        except Exception as e:
            errors.append(f"{title[:40]}: {str(e)[:80]}")

    logger.info(
        f"Markdown ingestion: {imported} imported, {skipped} skipped, "
        f"{len(errors)} errors"
    )

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_files": total_files,
    }


def ingest_quest_documents(directory: str) -> dict:
    """Parse Troubadourian quest files and insert as documents.

    Quest topology is stored as JSON content for future graph import.

    Args:
        directory: Path to directory containing quest JSON files.

    Returns:
        Dict with keys: imported, skipped, errors, total_files.
    """
    from db.operations import create_document, list_documents
    from .quest_parser import parse_quest_directory

    parsed = parse_quest_directory(directory)
    total_files = len(parsed)

    # Build dedup set: existing document titles with source='upload' and doc_type='research'
    existing = list_documents(source="upload", limit=9999)
    existing_titles = {d["title"] for d in existing}

    imported = 0
    skipped = 0
    errors: list[str] = []

    for quest in parsed:
        title = quest["title"]
        if title in existing_titles:
            skipped += 1
            continue

        try:
            content = json.dumps(
                {
                    "anchor": quest["anchor"],
                    "nodes": quest["nodes"],
                    "relationships": quest["relationships"],
                    "content_text": quest["content_text"],
                },
                indent=2,
            )
            create_document(
                doc_type="research",
                source="upload",
                title=title,
                content=content,
            )
            existing_titles.add(title)
            imported += 1

        except Exception as e:
            errors.append(f"{title[:40]}: {str(e)[:80]}")

    logger.info(
        f"Quest ingestion: {imported} imported, {skipped} skipped, "
        f"{len(errors)} errors"
    )

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_files": total_files,
    }
