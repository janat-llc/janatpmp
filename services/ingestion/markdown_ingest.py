"""
Markdown & Text File Ingester

Parses markdown (.md) and plain text (.txt) files into JANATPMP document records.
Extracts title from first heading (markdown) or filename, classifies document type
by content patterns, and computes word count.

Output format:
    {
        "title": str,
        "content": str,
        "doc_type": str,     # chapter, essay, session_notes, research, conversation, etc.
        "source": "markdown" | "text",
        "word_count": int,
    }
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Patterns for doc_type classification
_DOC_TYPE_PATTERNS = [
    (r"(?i)^chapter\b|^chpt\b|^ch\s*\d", "chapter"),
    (r"(?i)conversation|session_\d|^\d{8}", "conversation"),
    (r"(?i)journal|diary|log\b", "journal"),
    (r"(?i)essay|paper|thesis|abstract", "essay"),
    (r"(?i)research|study|analysis|survey", "research"),
    (r"(?i)grimoire|spell|illusion|ritual", "creative"),
    (r"(?i)protocol|mandate|sprint|mission", "project_doc"),
    (r"(?i)readme|changelog|todo|guide", "documentation"),
]


def ingest_markdown(file_path: str | Path) -> dict | None:
    """
    Read a markdown file and return a document record.

    Args:
        file_path: Path to the .md file.

    Returns:
        Document dict, or None if the file is empty/unreadable.
    """
    return _ingest_file(file_path, source="markdown")


def ingest_text(file_path: str | Path) -> dict | None:
    """
    Read a plain text file and return a document record.

    Args:
        file_path: Path to the .txt file.

    Returns:
        Document dict, or None if the file is empty/unreadable.
    """
    return _ingest_file(file_path, source="text")


def ingest_directory(
    directory: str | Path,
    extensions: tuple[str, ...] = (".md", ".txt"),
) -> list[dict]:
    """
    Ingest all markdown and text files in a directory.

    Args:
        directory: Path to directory.
        extensions: File extensions to include.

    Returns:
        List of document dicts (skips empty/invalid files).
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.error(f"Not a directory: {directory}")
        return []

    results = []
    files = sorted(
        f for f in directory.iterdir() if f.suffix.lower() in extensions
    )
    logger.info(f"Processing {len(files)} files from {directory.name}/")

    for file_path in files:
        source = "markdown" if file_path.suffix.lower() == ".md" else "text"
        result = _ingest_file(file_path, source=source)
        if result:
            results.append(result)

    logger.info(f"Ingested {len(results)}/{len(files)} files from {directory.name}/")
    return results


def _ingest_file(file_path: str | Path, source: str) -> dict | None:
    """
    Core ingestion logic for a single file.

    Args:
        file_path: Path to file.
        source: Source label ("markdown" or "text").

    Returns:
        Document dict, or None if empty/unreadable.
    """
    file_path = Path(file_path)

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to read {file_path.name}: {e}")
        return None

    content = content.strip()
    if not content:
        logger.warning(f"{file_path.name}: empty file")
        return None

    title = _extract_title(content, file_path)
    doc_type = _classify_doc_type(title, file_path.name)
    word_count = len(content.split())

    return {
        "title": title,
        "content": content,
        "doc_type": doc_type,
        "source": source,
        "word_count": word_count,
    }


def _extract_title(content: str, file_path: Path) -> str:
    """
    Extract title from first markdown heading, or fall back to filename.

    Args:
        content: File content.
        file_path: Path to file (for fallback).

    Returns:
        Title string.
    """
    # Look for first # heading in the first 5 lines
    for line in content.split("\n")[:5]:
        match = re.match(r"^#{1,3}\s+(.+)", line.strip())
        if match:
            return match.group(1).strip()

    # Fall back to filename without extension
    return file_path.stem.replace("_", " ").replace("-", " ")


def _classify_doc_type(title: str, filename: str) -> str:
    """
    Classify document type based on title and filename patterns.

    Args:
        title: Extracted title.
        filename: Original filename.

    Returns:
        Document type string.
    """
    combined = f"{title} {filename}"
    for pattern, doc_type in _DOC_TYPE_PATTERNS:
        if re.search(pattern, combined):
            return doc_type
    return "general"
