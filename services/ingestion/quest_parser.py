"""
Troubadourian Quest Parser

Parses quest JSON files from the Troubadourian Amphitheatre system.
Quest files contain memory triplets with graph topology structures
designed for the Salience Engine.

Expected input format (Neo4j graph topology):
    {
        "anchor": {
            "parent_node_label": str,
            "parent_node_name": str,
            "parent_node_id": str
        },
        "topology_plan": {
            "nodes_to_create": [
                {
                    "label": str,
                    "properties": { "name": str, "content": str, ... }
                }
            ],
            "relationships_to_create": [
                {
                    "start_node": str,
                    "end_node": str,
                    "type": str,
                    "properties": { ... }
                }
            ]
        }
    }

Output format:
    {
        "title": str,
        "source": "quest",
        "anchor": dict,
        "nodes": list[dict],
        "relationships": list[dict],
        "node_count": int,
        "relationship_count": int,
        "content_text": str,       # flattened text for search indexing
    }

Note: Quest files preserve Neo4j graph structures — memory triplets with
salience scores from the Troubadourian Amphitheatre. The scores were
computed against an older constitution (values are dated) but the
structure itself is valuable as training data templates for Salience Engine v2.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def parse_quest_file(file_path: str | Path) -> dict | None:
    """
    Parse a single Troubadourian quest JSON file.

    Args:
        file_path: Path to the quest JSON file.

    Returns:
        Parsed quest dict, or None if the file is invalid.
    """
    file_path = Path(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read {file_path.name}: {e}")
        return None

    if not isinstance(data, dict):
        logger.warning(f"{file_path.name}: expected dict, got {type(data).__name__}")
        return None

    # Extract anchor
    anchor = data.get("anchor", {})
    if not anchor:
        logger.warning(f"{file_path.name}: missing 'anchor' key")
        return None

    # Extract topology
    topology = data.get("topology_plan", {})
    nodes = topology.get("nodes_to_create", [])
    relationships = topology.get("relationships_to_create", [])

    if not nodes and not relationships:
        logger.warning(f"{file_path.name}: empty topology (no nodes or relationships)")
        return None

    # Build title from anchor or filename
    title = (
        anchor.get("parent_node_name")
        or anchor.get("parent_node_label")
        or file_path.stem
    )

    # Flatten text content for search indexing
    content_parts = []
    for node in nodes:
        props = node.get("properties", {})
        name = props.get("name", "")
        content = props.get("content", "")
        if name:
            content_parts.append(name)
        if content:
            content_parts.append(content)

    content_text = "\n".join(content_parts)

    return {
        "title": title,
        "source": "quest",
        "anchor": anchor,
        "nodes": nodes,
        "relationships": relationships,
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "content_text": content_text,
    }


def parse_quest_directory(directory: str | Path) -> list[dict]:
    """
    Parse all quest JSON files in a directory.

    Args:
        directory: Path to directory containing quest JSON files.

    Returns:
        List of parsed quest dicts (skips invalid files).
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.error(f"Not a directory: {directory}")
        return []

    results = []
    json_files = sorted(directory.glob("*.json"))
    logger.info(f"Processing {len(json_files)} quest files from {directory.name}/")

    for json_file in json_files:
        result = parse_quest_file(json_file)
        if result:
            results.append(result)

    logger.info(
        f"Parsed {len(results)}/{len(json_files)} quest files from {directory.name}/"
    )
    return results


def validate_quest_file(file_path: str | Path) -> bool:
    """
    Check whether a file is a valid Troubadourian quest JSON.

    Args:
        file_path: Path to JSON file.

    Returns:
        True if the file has anchor + topology_plan structure.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        return "anchor" in data and "topology_plan" in data
    except Exception:
        return False
