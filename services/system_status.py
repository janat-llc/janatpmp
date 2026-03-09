"""System status aggregator — single MCP endpoint for full system health.

R48: Consolidates triad health, Slumber status, pipeline info, coverage gaps,
and auto-generated alerts into one JSON response.
"""

import logging
from datetime import datetime, timezone

from db.operations import get_stats, get_connection
from services.slumber import get_slumber_status
from services.settings import get_setting

logger = logging.getLogger(__name__)


def _generate_alerts() -> list[dict]:
    """Generate system health alerts from current state.

    Returns:
        List of dicts with 'level' (error/warning/ok) and 'message'.
    """
    alerts = []

    # Check Slumber sub-cycles
    try:
        slumber = get_slumber_status()
        state = slumber.get("state", "unknown")
        if state == "offline":
            alerts.append({"level": "error", "message": "Slumber daemon is offline"})
        elif slumber.get("error"):
            alerts.append({"level": "error", "message": f"Slumber error: {slumber['error']}"})

        zero_subcycles = []
        subcycle_keys = {
            "total_evaluated": "Evaluate",
            "total_extracted": "Extract",
            "total_cooccurred": "Co-occurrence",
            "total_woven": "Weave",
            "total_dreams": "Dream",
            "total_decayed": "Decay",
        }
        for key, name in subcycle_keys.items():
            if slumber.get(key, 0) == 0:
                zero_subcycles.append(name)
        if zero_subcycles:
            alerts.append({
                "level": "warning",
                "message": f"Slumber sub-cycles producing 0 output: {', '.join(zero_subcycles)}",
            })
    except Exception as e:
        alerts.append({"level": "error", "message": f"Cannot read Slumber status: {e}"})

    # Check Qdrant
    try:
        from services.vector_store import _get_client, COLLECTION_MESSAGES, COLLECTION_DOCUMENTS
        client = _get_client()
        for coll_name in [COLLECTION_MESSAGES, COLLECTION_DOCUMENTS]:
            try:
                info = client.get_collection(coll_name)
                if info.points_count == 0:
                    alerts.append({"level": "warning", "message": f"Qdrant collection '{coll_name}' has 0 points"})
            except Exception:
                alerts.append({"level": "error", "message": f"Qdrant collection '{coll_name}' unreachable"})
    except Exception:
        alerts.append({"level": "error", "message": "Qdrant client unavailable"})

    # Check Neo4j
    try:
        from graph.graph_service import graph_stats
        gs = graph_stats()
        if gs.get("error"):
            alerts.append({"level": "error", "message": f"Neo4j error: {gs['error']}"})
        elif sum(gs.get("nodes", {}).values() or [0]) == 0:
            alerts.append({"level": "warning", "message": "Neo4j graph has 0 nodes"})
    except Exception:
        alerts.append({"level": "error", "message": "Neo4j unreachable"})

    # Check coverage gaps
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages WHERE id NOT IN (SELECT message_id FROM messages_metadata)")
            no_meta = cursor.fetchone()[0]
            if no_meta > 0:
                alerts.append({"level": "warning", "message": f"{no_meta} messages missing metadata"})
    except Exception:
        pass

    if not alerts:
        alerts.append({"level": "ok", "message": "All systems healthy"})

    return alerts


def get_system_status() -> dict:
    """Get comprehensive system health report in one call.

    Returns a single JSON blob covering triad health (SQLite, Qdrant, Neo4j),
    Slumber daemon status, pipeline info, coverage gaps, and auto-generated
    alerts. Designed for Claude to call once for full system awareness.

    Returns:
        Dict with keys: timestamp, triad_health, slumber, pipeline, coverage, alerts.
    """
    result = {"timestamp": datetime.now(timezone.utc).isoformat()}

    # --- Triad: SQLite ---
    try:
        stats = get_stats()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM conversations")
            conversations = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM messages")
            messages = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM entities")
            entities = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunks = cursor.fetchone()[0]

        sqlite_health = {
            "conversations": conversations,
            "messages": messages,
            "entities": entities,
            "documents": stats.get("total_documents", 0),
            "items": stats.get("total_items", 0),
            "tasks": stats.get("total_tasks", 0),
            "chunks": chunks,
        }
    except Exception as e:
        sqlite_health = {"error": str(e)}

    # --- Triad: Qdrant ---
    try:
        from services.vector_store import _get_client, COLLECTION_MESSAGES, COLLECTION_DOCUMENTS
        client = _get_client()
        from atlas.config import EMBEDDING_MODEL, EMBEDDING_DIM
        qdrant_health = {
            "collections": [COLLECTION_MESSAGES, COLLECTION_DOCUMENTS],
            "embedding_model": EMBEDDING_MODEL,
            "dimensions": EMBEDDING_DIM,
        }
        for coll_name in [COLLECTION_MESSAGES, COLLECTION_DOCUMENTS]:
            key = coll_name.replace("janatpmp_", "") + "_points"
            try:
                info = client.get_collection(coll_name)
                qdrant_health[key] = info.points_count
            except Exception:
                qdrant_health[key] = -1
    except Exception as e:
        qdrant_health = {"error": str(e)}

    # --- Triad: Neo4j ---
    try:
        from graph.graph_service import graph_stats
        neo4j_health = graph_stats()
        neo4j_health["connected"] = "error" not in neo4j_health
    except Exception as e:
        neo4j_health = {"connected": False, "error": str(e)}

    result["triad_health"] = {
        "sqlite": sqlite_health,
        "qdrant": qdrant_health,
        "neo4j": neo4j_health,
    }

    # --- Slumber ---
    try:
        slumber = get_slumber_status()
        result["slumber"] = {
            "state": slumber.get("state", "unknown"),
            "last_cycle_at": slumber.get("last_cycle_at", ""),
            "sub_cycles": {
                "evaluate": {"last_count": slumber.get("last_evaluated", 0), "total": slumber.get("total_evaluated", 0)},
                "propagate": {"last_count": slumber.get("last_propagated", 0), "total": slumber.get("total_propagated", 0)},
                "relate": {"last_count": slumber.get("last_related", 0), "total": slumber.get("total_related", 0)},
                "prune": {"last_count": slumber.get("last_pruned", 0), "total": slumber.get("total_pruned", 0)},
                "extract": {"last_count": slumber.get("last_extracted", 0), "total": slumber.get("total_extracted", 0)},
                "dream": {"last_count": slumber.get("last_dreamed", 0), "total": slumber.get("total_dreams", 0)},
                "weave": {"last_count": slumber.get("last_woven", 0), "total": slumber.get("total_woven", 0)},
                "link": {"last_count": slumber.get("last_cooccurred", 0), "total": slumber.get("total_cooccurred", 0)},
                "decay": {"last_count": slumber.get("last_decayed", 0), "total": slumber.get("total_decayed", 0)},
                "mine": {"last_count": slumber.get("last_mined", 0), "total": slumber.get("total_mined", 0)},
                "dedup": {"last_count": slumber.get("last_deduped", 0), "total": slumber.get("total_deduped", 0)},
            },
            "error": slumber.get("error", ""),
        }
    except Exception as e:
        result["slumber"] = {"state": "error", "error": str(e)}

    # --- Pipeline ---
    try:
        result["pipeline"] = {
            "janus_model": get_setting("chat_model") or "qwen3.5:27b",
            "janus_provider": get_setting("chat_provider") or "ollama",
            "postcognition_healthy": bool(get_setting("postcognition_enabled")),
        }
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.created_at FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.source = 'platform'
                ORDER BY m.created_at DESC LIMIT 1
            """)
            row = cursor.fetchone()
            result["pipeline"]["last_janus_message_at"] = row[0] if row else ""
    except Exception as e:
        result["pipeline"] = {"error": str(e)}

    # --- Coverage ---
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages")
            total_msgs = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT message_id) FROM messages_metadata")
            msgs_with_meta = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM documents")
            total_docs = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT entity_id) FROM chunks WHERE entity_type = 'document'")
            docs_chunked = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            total_chunks = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM entities")
            entities_sqlite = cursor.fetchone()[0]

        # Neo4j entity count
        entities_neo4j = 0
        try:
            from graph.graph_service import graph_stats
            gs = graph_stats()
            entities_neo4j = gs.get("nodes", {}).get("Entity", 0)
        except Exception:
            pass

        result["coverage"] = {
            "messages_with_metadata": msgs_with_meta,
            "messages_without_metadata": total_msgs - msgs_with_meta,
            "documents_chunked": docs_chunked,
            "documents_not_chunked": total_docs - docs_chunked,
            "total_chunks": total_chunks,
            "entities_in_sqlite": entities_sqlite,
            "entities_in_neo4j": entities_neo4j,
            "entity_delta": entities_sqlite - entities_neo4j,
        }
    except Exception as e:
        result["coverage"] = {"error": str(e)}

    # --- Alerts ---
    result["alerts"] = _generate_alerts()

    return result
