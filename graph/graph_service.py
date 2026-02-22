"""Neo4j graph service — CRUD operations and MCP-exposed query tools.

All public functions are safe to call when Neo4j is unavailable —
they log warnings and return empty/false results instead of raising.
"""

import json
import logging
from typing import Any

import neo4j

from atlas.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE
from .schema import init_graph_schema

logger = logging.getLogger(__name__)

_driver: neo4j.Driver | None = None


def _get_driver() -> neo4j.Driver:
    """Lazy-init and return the Neo4j Bolt driver."""
    global _driver
    if _driver is None:
        _driver = neo4j.GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
        )
    return _driver


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

def ensure_schema() -> None:
    """Initialize Neo4j schema (constraints + indexes). Safe to repeat."""
    try:
        driver = _get_driver()
        init_graph_schema(driver)
    except Exception as e:
        logger.warning("Neo4j schema init failed (is Neo4j running?): %s", e)


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------

def upsert_node(label: str, id: str, properties: dict | None = None) -> None:
    """MERGE a node by id and SET properties.

    Args:
        label: Neo4j node label (Item, Task, Message, etc.).
        id: Unique identifier (matches SQLite entity id).
        properties: Dict of properties to set on the node.

    Raises:
        Exception: If Neo4j is unreachable (allows CDC consumer to retry).
    """
    props = dict(properties or {})
    props["id"] = id
    driver = _get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run(
            f"MERGE (n:{label} {{id: $id}}) SET n += $props",
            id=id, props=props,
        )


def delete_node(label: str, id: str) -> None:
    """DETACH DELETE a node by id.

    Args:
        label: Neo4j node label.
        id: Entity identifier.

    Raises:
        Exception: If Neo4j is unreachable.
    """
    driver = _get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run(
            f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n",
            id=id,
        )


def create_edge(
    from_label: str, from_id: str,
    to_label: str, to_id: str,
    rel_type: str,
    properties: dict | None = None,
) -> None:
    """MERGE an edge between two nodes (creates nodes if missing).

    Args:
        from_label: Source node label.
        from_id: Source node id.
        to_label: Target node label.
        to_id: Target node id.
        rel_type: Relationship type (BELONGS_TO, FOLLOWS, INFORMED_BY, etc.).
        properties: Optional properties on the relationship.

    Raises:
        Exception: If Neo4j is unreachable.
    """
    props = dict(properties or {})
    driver = _get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        query = (
            f"MERGE (a:{from_label} {{id: $from_id}}) "
            f"MERGE (b:{to_label} {{id: $to_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
        )
        if props:
            query += "SET r += $props"
        session.run(query, from_id=from_id, to_id=to_id, props=props)


def get_neighbors(
    label: str, id: str,
    rel_type: str = "", direction: str = "both",
) -> list[dict]:
    """Get neighbors of a node.

    Args:
        label: Node label.
        id: Node id.
        rel_type: Filter by relationship type (empty = all).
        direction: 'out', 'in', or 'both'.

    Returns:
        List of dicts with keys: id, label, rel_type, properties.
    """
    try:
        driver = _get_driver()
        rel_pattern = f":{rel_type}" if rel_type else ""

        if direction == "out":
            pattern = f"(n:{label} {{id: $id}})-[r{rel_pattern}]->(m)"
        elif direction == "in":
            pattern = f"(n:{label} {{id: $id}})<-[r{rel_pattern}]-(m)"
        else:
            pattern = f"(n:{label} {{id: $id}})-[r{rel_pattern}]-(m)"

        query = (
            f"MATCH {pattern} "
            "RETURN m.id AS id, labels(m) AS labels, type(r) AS rel_type, "
            "properties(m) AS properties LIMIT 100"
        )

        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, id=id)
            return [
                {
                    "id": record["id"],
                    "label": record["labels"][0] if record["labels"] else "",
                    "rel_type": record["rel_type"],
                    "properties": dict(record["properties"]),
                }
                for record in result
            ]
    except Exception as e:
        logger.warning("Neo4j get_neighbors(%s, %s) failed: %s", label, id[:12], e)
        return []


def health_check() -> bool:
    """Verify Neo4j connectivity.

    Returns:
        True if Neo4j is reachable, False otherwise.
    """
    try:
        driver = _get_driver()
        driver.verify_connectivity()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# MCP-exposed tools (full docstrings for Gradio API / MCP generation)
# ---------------------------------------------------------------------------

def graph_query(cypher: str) -> list[dict]:
    """Run a read-only Cypher query against the Neo4j knowledge graph.

    Use this to explore memory relationships, trace influence chains,
    find temporal patterns, or answer questions about the knowledge graph.

    Examples:
        - "MATCH (m:Message)-[:INFORMED_BY]->(src) RETURN m.id, src.id LIMIT 10"
        - "MATCH (m:Message)-[:BELONGS_TO]->(c:Conversation) RETURN c.title, count(m)"
        - "MATCH (m1:Message)-[:SIMILAR_TO]-(m2:Message) RETURN m1.id, m2.id LIMIT 20"

    Args:
        cypher: A Cypher query string. Must be read-only (no CREATE, MERGE, DELETE, SET).

    Returns:
        List of result dicts, one per row. Returns error dict if query fails.
    """
    forbidden = ["CREATE ", "MERGE ", "DELETE ", "SET ", "REMOVE ", "DROP ", "DETACH "]
    upper = cypher.upper().strip()
    for kw in forbidden:
        if kw in upper:
            return [{"error": f"Write operations not allowed. Found: {kw.strip()}"}]

    try:
        driver = _get_driver()
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(cypher)
            rows = []
            for record in result:
                row = {}
                for key in record.keys():
                    val = record[key]
                    if isinstance(val, neo4j.graph.Node):
                        row[key] = {"id": val.get("id"), "labels": list(val.labels), **dict(val)}
                    elif isinstance(val, neo4j.graph.Relationship):
                        row[key] = {"type": val.type, **dict(val)}
                    elif isinstance(val, list):
                        row[key] = [str(v) for v in val]
                    else:
                        row[key] = val
                rows.append(row)
            return rows
    except Exception as e:
        logger.warning("graph_query failed: %s", e)
        return [{"error": str(e)}]


def graph_neighbors(label: str, id: str, rel_type: str = "", direction: str = "both") -> list[dict]:
    """Get neighbors of a node in the knowledge graph.

    Lightweight traversal tool for exploring connections around a specific entity.

    Args:
        label: Node label (Item, Task, Document, Conversation, Message, Domain).
        id: The entity's unique identifier.
        rel_type: Optional relationship type filter (BELONGS_TO, FOLLOWS, INFORMED_BY, etc.). Empty for all.
        direction: Traversal direction: 'out', 'in', or 'both'.

    Returns:
        List of neighbor dicts with keys: id, label, rel_type, properties.
    """
    return get_neighbors(label, id, rel_type, direction)


def graph_stats() -> dict:
    """Get node and edge counts by label and type from the knowledge graph.

    Dashboard-level overview of the graph's contents.

    Returns:
        Dict with 'nodes' (label→count) and 'edges' (type→count) mappings.
    """
    nodes: dict[str, int] = {}
    edges: dict[str, int] = {}

    try:
        driver = _get_driver()
        with driver.session(database=NEO4J_DATABASE) as session:
            # Node counts by label
            result = session.run(
                "MATCH (n) UNWIND labels(n) AS lbl RETURN lbl, count(*) AS cnt"
            )
            for record in result:
                nodes[record["lbl"]] = record["cnt"]

            # Edge counts by type
            result = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS cnt"
            )
            for record in result:
                edges[record["rel"]] = record["cnt"]
    except Exception as e:
        logger.warning("graph_stats failed: %s", e)
        return {"nodes": {}, "edges": {}, "error": str(e)}

    return {"nodes": nodes, "edges": edges}
