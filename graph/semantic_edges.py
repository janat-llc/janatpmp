"""Semantic edge generation — vector similarity to graph topology.

Bridges Qdrant vector similarity into Neo4j SIMILAR_TO edges between
Conversation nodes. Transforms isolated conversation chains into a
connected semantic network.

R20: Graph Awakening
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from atlas.config import (
    SEMANTIC_EDGE_SCORE_THRESHOLD,
    SEMANTIC_EDGE_MAX_NEIGHBORS,
    SEMANTIC_EDGE_SEARCH_CANDIDATES,
    SEMANTIC_EDGE_REPR_CHUNKS,
    SEMANTIC_EDGE_REPR_MAX_CHARS,
)

logger = logging.getLogger(__name__)


def _build_representative_text(conversation: dict) -> str:
    """Build representative text for a conversation from title + early messages.

    Args:
        conversation: Conversation dict with at least 'id' and 'title' keys.

    Returns:
        Concatenated representative text, or empty string if no content.
    """
    from db.chat_operations import get_messages

    title = conversation.get("title", "") or ""
    conv_id = conversation.get("id", "")

    parts = [title] if title else []

    try:
        messages = get_messages(conv_id, limit=SEMANTIC_EDGE_REPR_CHUNKS)
        for msg in messages:
            user_prompt = (msg.get("user_prompt") or "")[:SEMANTIC_EDGE_REPR_MAX_CHARS]
            model_response = (msg.get("model_response") or "")[:SEMANTIC_EDGE_REPR_MAX_CHARS]
            text = f"{user_prompt} {model_response}".strip()
            if text:
                parts.append(text)
    except Exception as e:
        logger.debug("Failed to get messages for %s: %s", conv_id[:12], e)

    return " | ".join(parts)


def _find_similar_conversations(
    conv_id: str,
    representative_vector: list[float],
) -> list[dict]:
    """Search Qdrant for chunks similar to the representative vector, group by conversation.

    Args:
        conv_id: Source conversation ID (filtered out of results).
        representative_vector: Pre-computed embedding of representative text.

    Returns:
        List of dicts with keys: conversation_id, mean_score, hit_count.
        Sorted by mean_score descending, capped to MAX_NEIGHBORS. Self-links excluded.
    """
    from services.vector_store import _get_client, COLLECTION_MESSAGES

    client = _get_client()
    results = client.query_points(
        collection_name=COLLECTION_MESSAGES,
        query=representative_vector,
        limit=SEMANTIC_EDGE_SEARCH_CANDIDATES,
        with_payload=True,
    )

    # Group hits by conversation_id, compute mean score
    conv_scores: dict[str, list[float]] = defaultdict(list)
    for hit in results.points:
        hit_conv_id = hit.payload.get("conversation_id", "")
        if hit_conv_id and hit_conv_id != conv_id:
            conv_scores[hit_conv_id].append(hit.score)

    # Compute mean score per conversation, filter, sort
    neighbors = []
    for target_conv_id, scores in conv_scores.items():
        mean_score = sum(scores) / len(scores)
        if mean_score >= SEMANTIC_EDGE_SCORE_THRESHOLD:
            neighbors.append({
                "conversation_id": target_conv_id,
                "mean_score": round(mean_score, 4),
                "hit_count": len(scores),
            })

    neighbors.sort(key=lambda x: x["mean_score"], reverse=True)
    return neighbors[:SEMANTIC_EDGE_MAX_NEIGHBORS]


def weave_conversation_graph(
    score_threshold: float = 0.0,
    max_neighbors: int = 0,
    dry_run: bool = False,
) -> dict:
    """Weave semantic SIMILAR_TO edges between conversations in Neo4j.

    For each conversation, builds a representative embedding from title and
    early messages, searches for similar conversations via Qdrant vector search,
    and writes SIMILAR_TO edges in Neo4j for matches above threshold.

    Transforms the knowledge graph from isolated conversation chains into a
    connected semantic network. Safe to re-run (MERGE-based, idempotent).

    Args:
        score_threshold: Minimum mean similarity to create edge. 0 uses default (0.55).
        max_neighbors: Maximum SIMILAR_TO edges per conversation. 0 uses default (5).
        dry_run: If True, compute similarities but do not write edges to Neo4j.

    Returns:
        Dict with keys: conversations_processed (int), edges_created (int),
            skipped (int), errors (list of str), elapsed_seconds (float).
    """
    from db.chat_operations import list_conversations
    from services.embedding import embed_query
    from graph.graph_service import create_edge

    start_time = time.time()

    # Apply overrides (0 = use config default)
    threshold = score_threshold if score_threshold > 0 else SEMANTIC_EDGE_SCORE_THRESHOLD
    max_n = max_neighbors if max_neighbors > 0 else SEMANTIC_EDGE_MAX_NEIGHBORS

    stats = {
        "conversations_processed": 0,
        "edges_created": 0,
        "skipped": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    # Fetch all conversations from SQLite
    try:
        conversations = list_conversations(limit=2000, active_only=False)
    except Exception as e:
        stats["errors"].append(f"Failed to list conversations: {e}")
        stats["elapsed_seconds"] = round(time.time() - start_time, 2)
        return stats

    logger.info(
        "Weave: starting for %d conversations (threshold=%.2f, max_neighbors=%d, dry_run=%s)",
        len(conversations), threshold, max_n, dry_run,
    )

    for i, conv in enumerate(conversations):
        conv_id = conv.get("id", "")
        if not conv_id:
            stats["skipped"] += 1
            continue

        try:
            # Step 1: Build representative text
            repr_text = _build_representative_text(conv)
            if not repr_text or len(repr_text) < 20:
                stats["skipped"] += 1
                continue

            # Step 2: Embed representative text
            vector = embed_query(repr_text)

            # Step 3: Find similar conversations via Qdrant
            neighbors = _find_similar_conversations(conv_id, vector)

            # Step 4: Apply custom threshold/limit if overridden
            filtered = [n for n in neighbors if n["mean_score"] >= threshold][:max_n]

            # Step 5: Write edges to Neo4j
            now_iso = datetime.now(timezone.utc).isoformat()
            for neighbor in filtered:
                if not dry_run:
                    try:
                        create_edge(
                            "Conversation", conv_id,
                            "Conversation", neighbor["conversation_id"],
                            "SIMILAR_TO",
                            {
                                "score": neighbor["mean_score"],
                                "method": "vector_centroid_v1",
                                "created_at": now_iso,
                            },
                        )
                    except Exception as e:
                        stats["errors"].append(
                            f"Edge write {conv_id[:12]}→{neighbor['conversation_id'][:12]}: {e}"
                        )
                        continue
                stats["edges_created"] += 1

            stats["conversations_processed"] += 1

        except Exception as e:
            stats["errors"].append(f"Conversation {conv_id[:12]}: {e}")
            stats["skipped"] += 1

        # Progress logging every 50 conversations
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            logger.info(
                "Weave progress: %d/%d conversations, %d edges, %.1fs elapsed",
                i + 1, len(conversations), stats["edges_created"], elapsed,
            )

    stats["elapsed_seconds"] = round(time.time() - start_time, 2)

    # Truncate error list for readability
    if len(stats["errors"]) > 20:
        stats["errors"] = stats["errors"][:20] + [
            f"... and {len(stats['errors']) - 20} more errors"
        ]

    logger.info(
        "Weave complete: %d conversations, %d edges, %d skipped, %d errors, %.1fs",
        stats["conversations_processed"], stats["edges_created"],
        stats["skipped"], len(stats["errors"]), stats["elapsed_seconds"],
    )

    return stats


def weave_new_conversations(since: str = "") -> dict:
    """Weave semantic SIMILAR_TO edges for conversations created since a timestamp.

    Incremental version of weave_conversation_graph(). Reads the 'since'
    parameter (ISO timestamp), or falls back to the 'last_graph_weave_at'
    setting. After completion, updates the setting to current time.

    Args:
        since: ISO timestamp. Empty = read from settings.

    Returns:
        Dict with conversations_processed, edges_created, skipped,
        errors, elapsed_seconds.
    """
    from db.operations import get_connection
    from graph.graph_service import create_edge
    from services.embedding import embed_query
    from services.settings import get_setting, set_setting

    start_time = time.time()

    stats = {
        "conversations_processed": 0,
        "edges_created": 0,
        "skipped": 0,
        "errors": [],
    }

    # Determine watermark
    if not since:
        since = get_setting("last_graph_weave_at") or ""
    if not since:
        since = "1970-01-01T00:00:00"

    # Fetch conversations created since watermark
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE created_at > ? ORDER BY created_at",
                (since,),
            ).fetchall()
            conversations = [dict(r) for r in rows]
    except Exception as e:
        stats["errors"].append(f"Failed to query conversations: {e}")
        stats["elapsed_seconds"] = round(time.time() - start_time, 2)
        return stats

    if not conversations:
        stats["elapsed_seconds"] = round(time.time() - start_time, 2)
        set_setting("last_graph_weave_at", datetime.now(timezone.utc).isoformat())
        return stats

    logger.info("Weave incremental: %d new conversations since %s", len(conversations), since[:19])

    for conv in conversations:
        conv_id = conv.get("id", "")
        if not conv_id:
            stats["skipped"] += 1
            continue

        try:
            repr_text = _build_representative_text(conv)
            if not repr_text or len(repr_text) < 20:
                stats["skipped"] += 1
                continue

            vector = embed_query(repr_text)
            neighbors = _find_similar_conversations(conv_id, vector)

            now_iso = datetime.now(timezone.utc).isoformat()
            for neighbor in neighbors:
                try:
                    create_edge(
                        "Conversation", conv_id,
                        "Conversation", neighbor["conversation_id"],
                        "SIMILAR_TO",
                        {
                            "score": neighbor["mean_score"],
                            "method": "vector_centroid_v1",
                            "created_at": now_iso,
                        },
                    )
                    stats["edges_created"] += 1
                except Exception as e:
                    stats["errors"].append(
                        f"Edge {conv_id[:12]}→{neighbor['conversation_id'][:12]}: {e}"
                    )

            stats["conversations_processed"] += 1

        except Exception as e:
            stats["errors"].append(f"Conversation {conv_id[:12]}: {e}")
            stats["skipped"] += 1

    # Update watermark
    set_setting("last_graph_weave_at", datetime.now(timezone.utc).isoformat())

    stats["elapsed_seconds"] = round(time.time() - start_time, 2)

    if stats["edges_created"] > 0:
        logger.info(
            "Weave incremental: %d edges from %d conversations in %.1fs",
            stats["edges_created"], stats["conversations_processed"],
            stats["elapsed_seconds"],
        )

    return stats
