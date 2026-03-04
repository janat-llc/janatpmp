"""Dream Synthesis — cross-conversation insight generation during Slumber.

Selects high-quality message clusters across conversations and uses
Gemini to synthesize emergent patterns, creating new insight documents
and graph edges that feed back into RAG — making Janus's memory not
just searchable, but generative.

R24: Dream Synthesis
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from atlas.config import (
    DREAM_CLUSTER_MAX_SIZE,
    DREAM_CLUSTER_MIN_SIZE,
    DREAM_MAX_CLUSTERS,
    DREAM_MIN_QUALITY,
    DREAM_SIMILARITY_THRESHOLD,
    DREAM_TEMPERATURE,
    SALIENCE_DEFAULT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Synthesis prompt template
# ---------------------------------------------------------------------------

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a knowledge synthesis engine analyzing messages from a personal \
knowledge management system. These messages come from different conversations \
but were selected because they are semantically related.

Your task: Find emergent patterns, unexpected connections, and synthesized \
insights that only become visible when viewing these messages together. \
Focus on connections the individual conversations couldn't see.

Be specific and substantive. Name the actual concepts, reference the actual \
ideas. Generic observations like "these messages share common themes" are \
worthless. What NEW understanding emerges from seeing them side by side?"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_synthesis_clusters(
    min_quality: float = 0.0,
    max_clusters: int = 0,
    max_cluster_size: int = 0,
) -> list[dict]:
    """Select cross-conversation message clusters for synthesis.

    Finds groups of high-quality messages from different conversations
    that are semantically related — the raw material for dreams.

    Args:
        min_quality: Minimum quality_score threshold. 0 = use config.
        max_clusters: Maximum clusters to return. 0 = use config.
        max_cluster_size: Maximum messages per cluster. 0 = use config.

    Returns:
        List of cluster dicts, each containing:
        - messages: list of message dicts
        - mean_quality: average quality score across cluster
        - diversity_score: measure of cross-conversation spread
    """
    from services.settings import get_setting

    min_quality = min_quality or float(
        get_setting("slumber_dream_min_quality") or DREAM_MIN_QUALITY
    )
    max_clusters = max_clusters or DREAM_MAX_CLUSTERS
    max_cluster_size = max_cluster_size or DREAM_CLUSTER_MAX_SIZE

    # 1. Get high-quality scored messages
    high_quality = _get_scored_messages(min_quality)
    if len(high_quality) < DREAM_CLUSTER_MIN_SIZE:
        logger.info(
            "Dream Synthesis: insufficient scored messages (%d < %d)",
            len(high_quality), DREAM_CLUSTER_MIN_SIZE,
        )
        return []

    # 2. Build cross-conversation clusters via Qdrant similarity
    clusters = _build_clusters(high_quality, max_cluster_size)

    # 3. Rank by quality * diversity, return top-K
    clusters.sort(
        key=lambda c: c["mean_quality"] * c["diversity_score"], reverse=True,
    )
    selected = clusters[:max_clusters]
    logger.info(
        "Dream Synthesis: %d scored messages -> %d clusters -> %d selected",
        len(high_quality), len(clusters), len(selected),
    )
    return selected


def synthesize_cluster(cluster: dict) -> dict:
    """Send a message cluster to Gemini for cross-conversation synthesis.

    Args:
        cluster: Cluster dict from select_synthesis_clusters().

    Returns:
        Synthesis result dict with keys: insight_title, insight_text,
        themes, connections, confidence.  On failure: {"error": str}.
    """
    prompt = _build_synthesis_prompt(cluster)

    try:
        raw = _call_gemini(prompt)
        parsed = _parse_synthesis_response(raw)
        if parsed is None:
            return {"error": "JSON parse failed"}
        return parsed
    except Exception as e:
        logger.warning("Dream Synthesis Gemini call failed: %s", e)
        return {"error": str(e)}


def persist_synthesis(cluster: dict, synthesis: dict) -> dict:
    """Store synthesis results as a document and graph edges.

    Creates:
    1. A new document (doc_type='agent_output', source='dream_synthesis')
    2. Chunks + embeds the document inline for immediate RAG availability
    3. SYNTHESIZED_FROM graph edges from document to source messages

    Args:
        cluster: The source cluster.
        synthesis: The Gemini synthesis result.

    Returns:
        Dict with created entity IDs:
        - document_id: The insight document ID
        - edges_created: Number of graph edges created
    """
    title = synthesis.get("insight_title", "Dream Synthesis Insight")[:200]
    content = synthesis.get("insight_text", "")
    themes = synthesis.get("themes", [])

    if not content:
        return {"document_id": "", "edges_created": 0}

    # 1. Create the document
    from db.operations import create_document
    doc_id = create_document(
        doc_type="agent_output",
        source="dream_synthesis",
        title=title,
        content=content,
        actor="agent",
    )

    # 2. Inline chunk + embed
    _embed_document(doc_id, title, content, themes)

    # 3. Create graph edges (fire-and-forget)
    edges = _create_graph_edges(doc_id, cluster)

    logger.info(
        "Dream persisted: '%s' (doc %s, %d edges)",
        title[:50], doc_id[:8], edges,
    )
    return {"document_id": doc_id, "edges_created": edges}


def run_dream_cycle() -> dict:
    """Execute one complete dream synthesis cycle.

    Called by the Slumber Cycle after prune phase completes.
    Selects clusters, synthesizes each, persists results.

    Returns:
        Summary dict with keys: clusters_found, clusters_synthesized,
        insights_created, edges_created, errors.
    """
    summary = {
        "clusters_found": 0,
        "clusters_synthesized": 0,
        "insights_created": 0,
        "edges_created": 0,
        "errors": [],
    }

    try:
        clusters = select_synthesis_clusters()
        summary["clusters_found"] = len(clusters)

        for cluster in clusters:
            result = synthesize_cluster(cluster)
            if "error" in result:
                summary["errors"].append(result["error"])
                continue

            persisted = persist_synthesis(cluster, result)
            summary["clusters_synthesized"] += 1
            if persisted.get("document_id"):
                summary["insights_created"] += 1
            summary["edges_created"] += persisted.get("edges_created", 0)

    except Exception as e:
        logger.error("Dream Synthesis cycle failed: %s", e)
        summary["errors"].append(str(e))

    return summary


# ---------------------------------------------------------------------------
# Internal helpers — scored message query
# ---------------------------------------------------------------------------

def _get_scored_messages(min_quality: float) -> list[dict]:
    """Query messages_metadata for high-quality scored messages."""
    from db.operations import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT mm.message_id, mm.quality_score, mm.keywords,
                      m.model_response, m.user_prompt, m.conversation_id
               FROM messages_metadata mm
               JOIN messages m ON mm.message_id = m.id
               WHERE mm.quality_score >= ?
                 AND mm.quality_score IS NOT NULL
               ORDER BY mm.quality_score DESC
               LIMIT 200""",
            (min_quality,),
        ).fetchall()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Internal helpers — cluster building
# ---------------------------------------------------------------------------

def _build_clusters(messages: list[dict], max_size: int) -> list[dict]:
    """Build cross-conversation clusters using Qdrant similarity."""
    from services.vector_store import search, COLLECTION_MESSAGES

    clusters = []
    used_messages = set()

    for msg in messages[:50]:
        msg_id = msg["message_id"]
        if msg_id in used_messages:
            continue

        # Build query text from the message content
        query_text = (
            (msg.get("user_prompt") or "")[:300]
            + " "
            + (msg.get("model_response") or "")[:500]
        ).strip()
        if len(query_text) < 20:
            continue

        # Search Qdrant for similar messages
        try:
            similar = search(query_text, COLLECTION_MESSAGES, limit=10)
        except Exception:
            continue

        # Filter to other conversations only, above similarity threshold
        cross_conv = [
            s for s in similar
            if s.get("conversation_id") != msg["conversation_id"]
            and s.get("score", 0) > DREAM_SIMILARITY_THRESHOLD
        ]

        if len(cross_conv) < (DREAM_CLUSTER_MIN_SIZE - 1):
            continue

        # Build cluster: seed + cross-conv neighbors
        cluster_msgs = [msg] + cross_conv[:max_size - 1]
        conv_ids = {m.get("conversation_id") for m in cluster_msgs}

        quality_scores = []
        for m in cluster_msgs:
            qs = m.get("quality_score") or m.get("score", 0.5)
            quality_scores.append(float(qs))

        cluster = {
            "messages": cluster_msgs,
            "mean_quality": sum(quality_scores) / len(quality_scores),
            "diversity_score": len(conv_ids) / len(cluster_msgs),
        }
        clusters.append(cluster)

        # Mark messages as used
        used_messages.add(msg_id)
        for m in cross_conv[:max_size - 1]:
            used_messages.add(m.get("id", m.get("message_id", "")))

    return clusters


# ---------------------------------------------------------------------------
# Internal helpers — Gemini synthesis
# ---------------------------------------------------------------------------

def _build_synthesis_prompt(cluster: dict) -> str:
    """Build the user message for Gemini synthesis."""
    parts = []
    for i, msg in enumerate(cluster["messages"]):
        conv_id = str(msg.get("conversation_id", "unknown"))[:8]
        user_text = (msg.get("user_prompt") or "")[:300]
        model_text = (
            msg.get("model_response") or msg.get("text") or ""
        )[:500]
        parts.append(
            f"--- Message {i + 1} (conversation: {conv_id}...) ---\n"
            f"User: {user_text}\n"
            f"Response: {model_text}"
        )

    joined = "\n\n".join(parts)
    return (
        f"{joined}\n\n"
        "Respond in JSON:\n"
        "{\n"
        '    "insight_title": "Concise title for the emergent pattern (max 80 chars)",\n'
        '    "insight_text": "2-4 paragraphs. What do these messages reveal together '
        'that none reveals alone? Be specific about the conceptual bridge.",\n'
        '    "themes": ["theme1", "theme2", "theme3"],\n'
        "    \"connections\": [\n"
        '        {"from_index": 0, "to_index": 2, '
        '"relationship": "specific description"}\n'
        "    ],\n"
        '    "confidence": 0.0-1.0\n'
        "}\n"
        "Only return valid JSON. No markdown fences."
    )


def _call_gemini(user_message: str) -> str:
    """Call Gemini for synthesis. Pattern from slumber_eval.py."""
    from google import genai
    from google.genai import types
    from services.settings import get_setting

    api_key = get_setting("chat_api_key") or ""
    if not api_key:
        raise RuntimeError("No API key configured for dream synthesis")

    model = get_setting("slumber_eval_model") or "gemini-2.5-flash-lite"

    client = genai.Client(api_key=api_key.strip())
    config = types.GenerateContentConfig(
        system_instruction=_SYNTHESIS_SYSTEM_PROMPT,
        temperature=DREAM_TEMPERATURE,
    )
    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=config,
    )
    return response.text


def _parse_synthesis_response(text: str) -> dict | None:
    """Parse JSON from Gemini synthesis response."""
    clean = text.strip()

    # Strip markdown code fences if present
    if clean.startswith("```"):
        lines = clean.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)

    try:
        data = json.loads(clean)
        title = str(data.get("insight_title", ""))
        content = str(data.get("insight_text", ""))
        if not title or not content:
            return None
        return {
            "insight_title": title[:200],
            "insight_text": content,
            "themes": list(data.get("themes", []))[:10],
            "connections": list(data.get("connections", []))[:20],
            "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.debug("Dream synthesis JSON parse failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Internal helpers — document embedding
# ---------------------------------------------------------------------------

def _generate_doc_point_id(doc_id: str, chunk_index: int, chunk_total: int) -> str:
    """Generate Qdrant point ID for a document chunk.

    Same strategy as atlas/on_write.py:_generate_point_id().
    """
    if chunk_total <= 1:
        return doc_id
    namespace = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    return str(uuid.uuid5(namespace, f"{doc_id}_c{chunk_index:03d}"))


def _embed_document(
    doc_id: str, title: str, content: str, themes: list[str],
) -> None:
    """Chunk and embed a document inline (synchronous)."""
    try:
        from atlas.chunking import chunk_document
        from services.embedding import embed_passages
        from services.vector_store import upsert_point, COLLECTION_DOCUMENTS
        from db.operations import get_connection

        chunks = chunk_document(content, title=title)
        if not chunks:
            return

        chunk_texts = [c["text"] for c in chunks]
        vectors = embed_passages(chunk_texts)
        chunk_total = len(chunks)
        now_iso = datetime.now(timezone.utc).isoformat()

        point_ids = [
            _generate_doc_point_id(doc_id, c["index"], chunk_total)
            for c in chunks
        ]

        # Upsert each chunk to Qdrant
        for chunk, vector, point_id in zip(chunks, vectors, point_ids):
            payload = {
                "text": chunk["text"],
                "entity_type": "document",
                "doc_type": "agent_output",
                "title": title,
                "created_at": now_iso,
                "salience": SALIENCE_DEFAULT,
                "themes": themes,
                "chunk_index": chunk["index"],
                "chunk_total": chunk_total,
                "chunk_position": chunk["position"],
            }
            upsert_point(COLLECTION_DOCUMENTS, point_id, vector, payload)

        # Persist chunk records to SQLite
        with get_connection() as conn:
            for chunk, point_id in zip(chunks, point_ids):
                conn.execute(
                    """INSERT OR IGNORE INTO chunks
                       (entity_type, entity_id, chunk_index, chunk_text,
                        char_start, char_end, position, point_id, embedded_at)
                       VALUES ('document', ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (doc_id, chunk["index"], chunk["text"],
                     chunk["char_start"], chunk["char_end"],
                     chunk["position"], point_id),
                )
            conn.commit()

        logger.debug(
            "Dream embed: doc %s -> %d chunk(s) in Qdrant",
            doc_id[:12], chunk_total,
        )

    except Exception as e:
        logger.warning("Dream embed failed for doc %s: %s", doc_id[:12], e)


# ---------------------------------------------------------------------------
# Internal helpers — graph edges
# ---------------------------------------------------------------------------

def _create_graph_edges(doc_id: str, cluster: dict) -> int:
    """Create SYNTHESIZED_FROM edges from dream document to source messages."""
    edges = 0
    try:
        from graph.graph_service import create_edge
        now_iso = datetime.now(timezone.utc).isoformat()

        for msg in cluster["messages"]:
            msg_id = msg.get("message_id") or msg.get("id")
            if not msg_id:
                continue
            try:
                create_edge(
                    "Document", doc_id,
                    "Message", str(msg_id),
                    "SYNTHESIZED_FROM",
                    {"method": "dream_synthesis_v1", "created_at": now_iso},
                )
                edges += 1
            except Exception as e:
                logger.debug("Dream edge failed: %s -> %s: %s", doc_id[:8], str(msg_id)[:8], e)

    except Exception as e:
        logger.warning("Dream graph edges skipped: %s", e)

    return edges
