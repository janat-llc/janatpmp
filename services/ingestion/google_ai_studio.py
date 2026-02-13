"""
Google AI Studio Parser

Parses Google AI Studio JSON exports (chunkedPrompt format) into
JANATPMP-compatible conversation/message structures.

Expected input format:
    {
        "runSettings": { "model": "...", "temperature": ..., ... },
        "systemInstruction": { ... },
        "chunkedPrompt": {
            "chunks": [
                { "text": "...", "role": "user", "tokenCount": 123 },
                { "text": "...", "role": "model", "isThought": true, ... },
                { "text": "...", "role": "model", "finishReason": "STOP", ... }
            ]
        }
    }

Chunk roles:
    - role="user": User message
    - role="model" + isThought=true: Chain-of-thought reasoning
    - role="model" (no isThought): Visible assistant response

Output format per conversation:
    {
        "title": str,
        "source": "google_ai",
        "model": str | None,
        "system_instruction": str | None,
        "turns": [
            {
                "user_prompt": str,
                "model_reasoning": str | None,
                "model_response": str,
            }
        ]
    }

Ported from: curators_loom/pipeline_libraries/extraction_processing/google_ai_studio_parser.py
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def parse_google_ai_studio_file(file_path: str | Path) -> dict | None:
    """
    Parse a single Google AI Studio JSON export file.

    Args:
        file_path: Path to the JSON file.

    Returns:
        Parsed conversation dict, or None if the file is invalid/empty.
    """
    file_path = Path(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read {file_path.name}: {e}")
        return None

    # Validate structure
    if not isinstance(data, dict) or "chunkedPrompt" not in data:
        logger.warning(f"{file_path.name}: missing 'chunkedPrompt' key")
        return None

    chunks = data.get("chunkedPrompt", {}).get("chunks", [])
    if not chunks:
        logger.warning(f"{file_path.name}: no chunks found")
        return None

    # Extract metadata
    run_settings = data.get("runSettings", {})
    model = run_settings.get("model")

    system_instruction = None
    si = data.get("systemInstruction", {})
    if isinstance(si, dict) and si.get("parts"):
        parts = si["parts"]
        if isinstance(parts, list):
            system_instruction = " ".join(
                p.get("text", "") for p in parts if isinstance(p, dict)
            ).strip() or None

    # Extract turns
    turns = _extract_turns(chunks)
    if not turns:
        logger.warning(f"{file_path.name}: no valid turns extracted")
        return None

    # Build title from filename (strip extension)
    title = file_path.stem

    return {
        "title": title,
        "source": "google_ai",
        "model": model,
        "system_instruction": system_instruction,
        "turns": turns,
    }


def parse_google_ai_studio_directory(
    directory: str | Path,
) -> list[dict]:
    """
    Parse all Google AI Studio JSON files in a directory.

    Args:
        directory: Path to directory containing JSON files.

    Returns:
        List of parsed conversation dicts (skips invalid files).
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.error(f"Not a directory: {directory}")
        return []

    results = []
    json_files = sorted(directory.glob("*.json"))
    logger.info(f"Processing {len(json_files)} JSON files from {directory.name}/")

    for json_file in json_files:
        result = parse_google_ai_studio_file(json_file)
        if result:
            results.append(result)
        else:
            logger.debug(f"Skipped {json_file.name}")

    logger.info(
        f"Parsed {len(results)}/{len(json_files)} files from {directory.name}/"
    )
    return results


def _extract_turns(chunks: list[dict]) -> list[dict]:
    """
    Walk chunks and group into user/thought/response triplets.

    State machine:
        - When we see role="user", start a new triplet.
        - When we see role="model" + isThought=true, attach as reasoning.
        - When we see role="model" (no isThought), attach as response.
        - When the next user chunk arrives, finalize the current triplet.

    Args:
        chunks: List of chunk dicts from chunkedPrompt.chunks[].

    Returns:
        List of turn dicts with user_prompt, model_reasoning, model_response.
    """
    turns: list[dict] = []
    current: dict | None = None

    for chunk in chunks:
        role = chunk.get("role")
        is_thought = chunk.get("isThought", False)
        content = _extract_content(chunk)

        if not content:
            continue

        if role == "user" and not is_thought:
            # Finalize previous triplet if complete
            if current and current.get("user_prompt") and current.get("model_response"):
                turns.append(_finalize_turn(current))
            # Start new triplet
            current = {
                "user_prompt": content,
                "model_reasoning": None,
                "model_response": None,
            }

        elif role == "model" and is_thought:
            if current:
                # Clean thought content: collapse excessive newlines
                cleaned = re.sub(r"\n{2,}", "\n", content).strip()
                current["model_reasoning"] = cleaned

        elif role == "model":
            if current:
                current["model_response"] = content

    # Finalize last triplet
    if current and current.get("user_prompt") and current.get("model_response"):
        turns.append(_finalize_turn(current))

    return turns


def _extract_content(chunk: dict) -> str:
    """
    Extract text content from a chunk, preferring 'parts' array over 'text' field.

    Args:
        chunk: Single chunk dict.

    Returns:
        Cleaned content string, or empty string if no content.
    """
    content = ""
    if "parts" in chunk:
        content = "".join(
            p["text"] for p in chunk.get("parts", []) if isinstance(p, dict) and "text" in p
        )
    else:
        content = chunk.get("text", "")

    return _clean_content(content)


def _clean_content(text: str) -> str:
    """
    Light content cleaning — normalize whitespace, strip control characters.

    Preserves markdown formatting (code blocks, headers, etc.) since these
    conversations contain technical content where formatting is meaningful.

    Args:
        text: Raw text content.

    Returns:
        Cleaned text.
    """
    if not isinstance(text, str):
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n")

    # Remove control characters (keep tabs and newlines)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    # Collapse runs of 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _finalize_turn(turn: dict) -> dict:
    """
    Finalize a turn dict, ensuring clean output.

    Args:
        turn: Raw turn dict.

    Returns:
        Cleaned turn dict.
    """
    return {
        "user_prompt": turn["user_prompt"],
        "model_reasoning": turn.get("model_reasoning") or None,
        "model_response": turn["model_response"],
    }


def validate_file(file_path: str | Path) -> bool:
    """
    Check whether a file is a valid Google AI Studio export.

    Args:
        file_path: Path to JSON file.

    Returns:
        True if the file has the expected chunkedPrompt structure.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        chunks = data.get("chunkedPrompt", {}).get("chunks", [])
        if not chunks:
            return False
        # Check that at least one chunk has a role
        return any("role" in c for c in chunks[:5])
    except Exception:
        return False
