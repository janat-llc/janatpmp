"""Manifest-based canonical document ingestion.

Reads imports/canonical/manifest.json, detects new or changed documents via
SHA-256 content hashing, extracts text (PDF or markdown), creates/updates
JANATPMP documents, and embeds with elevated salience floors for decay immunity.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_PATH = Path("/data/canonical/manifest.json")


def _compute_file_hash(path: Path) -> str:
    """SHA-256 of raw file bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_text(path: Path) -> str:
    """Extract text from PDF or read markdown/text files."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from services.pdf_extractor import extract_text
        return extract_text(path)
    elif suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8")
    else:
        logger.warning("Unsupported canonical file type: %s", suffix)
        return ""


def _process_entry(entry: dict) -> str:
    """Process a single manifest entry.

    Returns:
        'processed' if document was created/updated, 'skipped' otherwise.
    """
    file_path = Path(entry["path"])
    if not file_path.exists():
        logger.warning("Canonical file not found: %s", file_path)
        return "skipped"

    # Change detection via SHA-256 of raw file bytes
    current_hash = _compute_file_hash(file_path)
    if current_hash == entry.get("content_hash"):
        return "skipped"

    # Extract text
    text = _extract_text(file_path)
    if not text:
        return "skipped"

    from db.chunk_operations import delete_chunks
    from db.operations import create_document, get_connection

    title = entry["title"]
    doc_type = entry.get("doc_type", "research")
    source = entry.get("source", "manual")
    salience_floor = entry.get("salience_floor", 0.9)
    doc_id = entry.get("document_id")

    if doc_id:
        # Update existing document — replace content, delete old chunks
        with get_connection() as conn:
            conn.execute(
                "UPDATE documents SET content = ?, updated_at = datetime('now'), "
                "modified_by = 'imported' WHERE id = ?",
                (text, doc_id),
            )
        delete_chunks("document", doc_id)
        logger.info("Canonical update: %s (%s)", title, doc_id[:12])
    else:
        # Create new document
        doc_id = create_document(
            doc_type=doc_type, source=source,
            title=title, content=text, actor="imported",
        )
        entry["document_id"] = doc_id
        logger.info("Canonical create: %s (%s)", title, doc_id[:12])

    # Embed with elevated salience floor (R46 decay immunity)
    from atlas.on_write import on_document_write
    on_document_write(doc_id, title, text, doc_type, source,
                      salience_floor=salience_floor)

    # Update manifest entry with hash and timestamp
    entry["content_hash"] = current_hash
    entry["last_ingested"] = datetime.now(timezone.utc).isoformat()

    return "processed"


def process_manifest() -> dict:
    """Read manifest, ingest new/changed documents, update manifest.

    Returns:
        Summary dict: {processed, skipped, errors}.
    """
    if not MANIFEST_PATH.exists():
        logger.debug("Canonical manifest not found at %s", MANIFEST_PATH)
        return {"processed": 0, "skipped": 0, "errors": 0}

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to read canonical manifest: %s", e)
        return {"processed": 0, "skipped": 0, "errors": 0}

    documents = manifest.get("documents", [])
    processed, skipped, errors = 0, 0, 0

    for entry in documents:
        try:
            result = _process_entry(entry)
            if result == "processed":
                processed += 1
            elif result == "skipped":
                skipped += 1
        except Exception as e:
            logger.warning("Canonical ingest error for %s: %s",
                           entry.get("title", "?"), e)
            errors += 1

    # Write updated manifest back (hashes + timestamps + document_ids)
    if processed > 0:
        try:
            MANIFEST_PATH.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to write updated manifest: %s", e)

    logger.info("Canonical ingest: %d processed, %d skipped, %d errors",
                processed, skipped, errors)
    return {"processed": processed, "skipped": skipped, "errors": errors}
