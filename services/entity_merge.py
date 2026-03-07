"""Entity merge infrastructure — graph write tool + duplicate detection (R47).

Provides merge_entities() MCP tool for consolidating duplicate entity nodes
in Neo4j, batch_merge_from_map() for processing dedup maps, and
detect_duplicates() for Slumber auto-dedup cycle.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── False-positive exclusions (never auto-merge these pairs) ──────────────
MERGE_EXCLUSIONS = {
    frozenset({"U", "Us"}),
    frozenset({"Canva", "Canvas"}),
    frozenset({"The Weaver", "The Weavers"}),
    frozenset({"Janu", "Janus"}),
    frozenset({"W", "The W"}),
    frozenset({"We", "The We"}),
}

# ── Abbreviation → full-name pairs (create ALIAS_OF edges, don't merge) ──
ALIAS_PAIRS = [
    ("C-Theory", "Consciousness Capacity Theory"),
    ("S-Theory", "Sentience Theory"),
    ("PoE", "Principle of Existing"),
    ("PoB", "Principle of Being"),
    ("PoDB", "Principle of Dyadic Being"),
    ("TNW", "Nexus Weaver"),
    ("DB-Theory", "Dyadic Being Theory"),
    ("JIRI", "Janat Initiative Research Institute"),
    ("IIT", "Integrated Information Theory"),
    ("PoSB", "Principle of Symbiotic Being"),
    ("MEAX", "Metaphoric Emergence Augmented eXperience"),
    ("JanatPMP", "Janat Project Management Platform"),
    ("UPE", "Universal Pattern Emergence"),
    ("GTC", "GPU Technology Conference"),
]


def _is_excluded(name_a: str, name_b: str) -> bool:
    """Check if a name pair is in the exclusion set."""
    return frozenset({name_a, name_b}) in MERGE_EXCLUSIONS


# ─────────────────────────────────────────────────────────────────────────
# merge_entities — MCP tool
# ─────────────────────────────────────────────────────────────────────────

def merge_entities(
    canonical_id: str,
    duplicate_ids: str,
    actor: str = "agent",
    dry_run: bool = True,
) -> str:
    """Merge duplicate entities into a canonical entity in Neo4j and SQLite.

    Relocates all graph edges from each duplicate to the canonical entity,
    reassigns SQLite mentions, consolidates metadata, then deletes duplicates.
    Use dry_run=True to preview what would change without writing.

    Args:
        canonical_id: The entity ID to keep (32-char hex).
        duplicate_ids: Comma-separated entity IDs to merge into canonical.
        actor: Provenance actor (agent, claude, mat).
        dry_run: If True, report what would change without writing.

    Returns:
        JSON summary with merged count, skipped, errors, and edge details.
    """
    from db.entity_ops import get_entity, update_entity
    from db.operations import get_connection
    from graph.graph_service import (
        _get_driver, create_edge, delete_node, merge_cooccurrence_edge,
    )
    from atlas.config import NEO4J_DATABASE

    dup_id_list = [d.strip() for d in duplicate_ids.split(",") if d.strip()]
    result = {"merged": 0, "skipped": 0, "errors": [], "edges_relocated": 0,
              "dry_run": dry_run, "details": []}

    # Validate canonical exists
    canonical = get_entity(canonical_id)
    if not canonical or isinstance(canonical, str):
        result["errors"].append(f"Canonical entity {canonical_id} not found")
        return json.dumps(result)

    for dup_id in dup_id_list:
        try:
            dup = get_entity(dup_id)
            if not dup or isinstance(dup, str):
                result["skipped"] += 1
                result["details"].append(f"Skip {dup_id}: not found")
                continue

            # ── Collect all Neo4j edges on the duplicate ──
            edges = []
            try:
                driver = _get_driver()
                with driver.session(database=NEO4J_DATABASE) as session:
                    records = session.run(
                        "MATCH (dup:Entity {id: $dup_id})-[r]-(other) "
                        "RETURN type(r) AS rel_type, other.id AS other_id, "
                        "labels(other)[0] AS other_label, "
                        "startNode(r).id = $dup_id AS is_outgoing, "
                        "properties(r) AS props",
                        dup_id=dup_id,
                    )
                    edges = [dict(rec) for rec in records]
            except Exception as e:
                logger.warning("Neo4j edge query failed for %s: %s", dup_id[:12], e)

            edge_count = 0
            if not dry_run:
                # ── Relocate each edge to canonical ──
                for edge in edges:
                    other_id = edge["other_id"]
                    if other_id == canonical_id:
                        continue  # Skip self-loops

                    rel_type = edge["rel_type"]
                    other_label = edge["other_label"] or "Entity"
                    is_outgoing = edge["is_outgoing"]
                    props = dict(edge["props"]) if edge["props"] else {}

                    try:
                        if rel_type == "CO_OCCURS_WITH":
                            weight = props.get("weight", 1)
                            merge_cooccurrence_edge(
                                canonical_id, other_id, weight)
                        elif is_outgoing:
                            create_edge("Entity", canonical_id,
                                        other_label, other_id,
                                        rel_type, props)
                        else:
                            create_edge(other_label, other_id,
                                        "Entity", canonical_id,
                                        rel_type, props)
                        edge_count += 1
                    except Exception as e:
                        logger.warning("Edge relocate failed %s->%s: %s",
                                       rel_type, other_id[:12], e)

                # ── Reassign SQLite mentions (conflict-safe) ──
                with get_connection() as conn:
                    # Delete dup mentions where canonical already has one
                    conn.execute(
                        "DELETE FROM entity_mentions "
                        "WHERE entity_id = ? AND message_id IN ("
                        "  SELECT message_id FROM entity_mentions "
                        "  WHERE entity_id = ?)",
                        (dup_id, canonical_id),
                    )
                    # Reassign remaining
                    conn.execute(
                        "UPDATE entity_mentions SET entity_id = ? "
                        "WHERE entity_id = ?",
                        (canonical_id, dup_id),
                    )

                # ── Consolidate metadata ──
                dup_mentions = dup.get("mention_count", 0) or 0
                canon_mentions = canonical.get("mention_count", 0) or 0
                new_count = canon_mentions + dup_mentions

                # Take earlier first_seen_at, later last_seen_at
                dup_first = dup.get("first_seen_at") or ""
                canon_first = canonical.get("first_seen_at") or ""
                first = min(filter(None, [dup_first, canon_first]),
                            default="")

                dup_last = dup.get("last_seen_at") or ""
                canon_last = canonical.get("last_seen_at") or ""
                last = max(filter(None, [dup_last, canon_last]),
                           default="")

                # Merge description if canonical's is empty
                desc = canonical.get("description") or ""
                if not desc.strip():
                    desc = dup.get("description") or ""

                update_entity(
                    canonical_id,
                    description=desc,
                    mention_count=new_count,
                    last_seen_at=last,
                )
                # Update first_seen_at directly (update_entity doesn't have it)
                if first:
                    with get_connection() as conn:
                        conn.execute(
                            "UPDATE entities SET first_seen_at = ? "
                            "WHERE id = ? AND (first_seen_at IS NULL "
                            "OR first_seen_at > ?)",
                            (first, canonical_id, first),
                        )

                # ── Delete duplicate ──
                with get_connection() as conn:
                    conn.execute("DELETE FROM entities WHERE id = ?",
                                 (dup_id,))
                try:
                    delete_node("Entity", dup_id)
                except Exception as e:
                    logger.warning("Neo4j delete failed for %s: %s",
                                   dup_id[:12], e)

            result["merged"] += 1
            result["edges_relocated"] += edge_count if not dry_run else len(edges)
            result["details"].append(
                f"{'Would merge' if dry_run else 'Merged'} "
                f"{dup.get('name', dup_id[:12])} → "
                f"{canonical.get('name', canonical_id[:12])} "
                f"({len(edges)} edges)"
            )

            # Refresh canonical for next iteration
            if not dry_run:
                canonical = get_entity(canonical_id)

        except Exception as e:
            result["errors"].append(f"Error merging {dup_id}: {e}")
            logger.warning("merge_entities error for %s: %s", dup_id[:12], e)

    return json.dumps(result)


# ─────────────────────────────────────────────────────────────────────────
# batch_merge_from_map — MCP tool
# ─────────────────────────────────────────────────────────────────────────

def batch_merge_from_map(
    map_path: str = "docs/entity-dedup-map-v1.json",
    dry_run: bool = True,
) -> str:
    """Process an entity dedup map and execute merges in bulk.

    Reads merge_clusters from the JSON map, skips false-positive exclusions,
    executes merge_entities for each cluster, then creates ALIAS_OF edges
    for known abbreviation pairs.

    Args:
        map_path: Path to the entity-dedup-map JSON file.
        dry_run: If True, report what would change without writing.

    Returns:
        JSON summary with merge counts, exclusions, alias edges created.
    """
    from db.entity_ops import find_entity_by_name, create_entity
    from graph.graph_service import create_edge

    path = Path(map_path)
    if not path.exists():
        return json.dumps({"error": f"Map not found: {map_path}"})

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return json.dumps({"error": f"Failed to read map: {e}"})

    clusters = data.get("merge_clusters", [])
    stats = {"total_clusters": len(clusters), "merged": 0, "skipped": 0,
             "excluded": 0, "errors": 0, "alias_edges": 0, "dry_run": dry_run}

    # ── Process merge clusters ──
    for cluster in clusters:
        canonical_name = cluster.get("canonical", "")
        canonical_id = cluster.get("canonical_id", "")
        duplicates = cluster.get("duplicates", [])

        # Check exclusions
        dup_names = [d["name"] for d in duplicates]
        excluded = False
        for dn in dup_names:
            if _is_excluded(canonical_name, dn):
                excluded = True
                break
        if excluded:
            stats["excluded"] += 1
            continue

        dup_ids = ",".join(d["id"] for d in duplicates)
        try:
            result_str = merge_entities(
                canonical_id, dup_ids, actor="agent", dry_run=dry_run)
            result = json.loads(result_str)
            stats["merged"] += result.get("merged", 0)
            stats["skipped"] += result.get("skipped", 0)
            if result.get("errors"):
                stats["errors"] += len(result["errors"])
        except Exception as e:
            stats["errors"] += 1
            logger.warning("Batch merge error for %s: %s", canonical_name, e)

    # ── Process ALIAS_OF pairs ──
    for alias_name, full_name in ALIAS_PAIRS:
        try:
            if dry_run:
                stats["alias_edges"] += 1
                continue

            # Find or create both entities
            alias_ent = find_entity_by_name("concept", alias_name)
            full_ent = find_entity_by_name("concept", full_name)

            if not alias_ent:
                # Try other entity types
                for etype in ("reference", "decision", "milestone",
                              "person", "emotional_state"):
                    alias_ent = find_entity_by_name(etype, alias_name)
                    if alias_ent:
                        break

            if not full_ent:
                # Create the full-name entity
                full_id = create_entity(
                    entity_type="concept", name=full_name,
                    description=f"Full name for {alias_name}",
                )
                full_ent = {"id": full_id}

            if alias_ent and full_ent:
                alias_id = alias_ent["id"]
                full_id = full_ent["id"]
                create_edge("Entity", alias_id,
                            "Entity", full_id, "ALIAS_OF")
                stats["alias_edges"] += 1
            else:
                logger.warning("ALIAS_OF skipped: %s → %s (alias not found)",
                               alias_name, full_name)

        except Exception as e:
            logger.warning("ALIAS_OF error %s → %s: %s",
                           alias_name, full_name, e)

    return json.dumps(stats)


# ─────────────────────────────────────────────────────────────────────────
# detect_duplicates — for Slumber auto-dedup cycle
# ─────────────────────────────────────────────────────────────────────────

def detect_duplicates() -> list[dict]:
    """Detect duplicate entities using pattern matching on names.

    Checks three patterns within same entity_type:
    1. Article prefix: "The X" vs "X"
    2. Plural/singular: "X" vs "Xs"
    3. Case variation: same lowercase name, different casing

    Returns:
        List of cluster dicts with canonical_id, canonical, duplicates, entity_type.
    """
    from db.operations import get_connection

    clusters = []
    seen_pairs = set()

    with get_connection() as conn:
        # Pattern 1: Article prefix — "The X" matches "X"
        rows = conn.execute(
            "SELECT a.id AS canon_id, a.name AS canon_name, "
            "       b.id AS dup_id, b.name AS dup_name, "
            "       a.entity_type, a.mention_count AS canon_mc, "
            "       b.mention_count AS dup_mc "
            "FROM entities a "
            "JOIN entities b ON b.name = 'The ' || a.name "
            "  AND a.entity_type = b.entity_type "
            "WHERE a.name NOT LIKE 'The %'"
        ).fetchall()

        for row in rows:
            pair = frozenset({row[0], row[2]})
            if pair in seen_pairs:
                continue
            if _is_excluded(row[1], row[3]):
                continue
            seen_pairs.add(pair)
            # Canonical = more mentions or shorter name
            if (row[5] or 0) >= (row[6] or 0):
                clusters.append({
                    "canonical_id": row[0], "canonical": row[1],
                    "duplicates": [{"id": row[2], "name": row[3],
                                    "pattern": "article_prefix"}],
                    "entity_type": row[4],
                })
            else:
                clusters.append({
                    "canonical_id": row[2], "canonical": row[3],
                    "duplicates": [{"id": row[0], "name": row[1],
                                    "pattern": "article_prefix"}],
                    "entity_type": row[4],
                })

        # Pattern 2: Plural/singular — "X" matches "Xs"
        rows = conn.execute(
            "SELECT a.id AS canon_id, a.name AS canon_name, "
            "       b.id AS dup_id, b.name AS dup_name, "
            "       a.entity_type, a.mention_count AS canon_mc, "
            "       b.mention_count AS dup_mc "
            "FROM entities a "
            "JOIN entities b ON a.name || 's' = b.name "
            "  AND a.entity_type = b.entity_type "
            "WHERE LENGTH(a.name) >= 3"
        ).fetchall()

        for row in rows:
            pair = frozenset({row[0], row[2]})
            if pair in seen_pairs:
                continue
            if _is_excluded(row[1], row[3]):
                continue
            seen_pairs.add(pair)
            if (row[5] or 0) >= (row[6] or 0):
                clusters.append({
                    "canonical_id": row[0], "canonical": row[1],
                    "duplicates": [{"id": row[2], "name": row[3],
                                    "pattern": "plural_singular"}],
                    "entity_type": row[4],
                })
            else:
                clusters.append({
                    "canonical_id": row[2], "canonical": row[3],
                    "duplicates": [{"id": row[0], "name": row[1],
                                    "pattern": "plural_singular"}],
                    "entity_type": row[4],
                })

        # Pattern 3: Case variation
        rows = conn.execute(
            "SELECT a.id, a.name, b.id, b.name, a.entity_type, "
            "       a.mention_count, b.mention_count "
            "FROM entities a "
            "JOIN entities b ON LOWER(TRIM(a.name)) = LOWER(TRIM(b.name)) "
            "  AND a.id < b.id AND a.entity_type = b.entity_type"
        ).fetchall()

        for row in rows:
            pair = frozenset({row[0], row[2]})
            if pair in seen_pairs:
                continue
            if _is_excluded(row[1], row[3]):
                continue
            seen_pairs.add(pair)
            if (row[5] or 0) >= (row[6] or 0):
                clusters.append({
                    "canonical_id": row[0], "canonical": row[1],
                    "duplicates": [{"id": row[2], "name": row[3],
                                    "pattern": "case_variation"}],
                    "entity_type": row[4],
                })
            else:
                clusters.append({
                    "canonical_id": row[2], "canonical": row[3],
                    "duplicates": [{"id": row[0], "name": row[1],
                                    "pattern": "case_variation"}],
                    "entity_type": row[4],
                })

    logger.info("Entity dedup: detected %d duplicate clusters", len(clusters))
    return clusters
