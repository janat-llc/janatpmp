"""Shared data-loading helpers for JANATPMP UI."""
import pandas as pd
from db.operations import list_items, list_tasks, list_documents, get_connection
from db.chat_operations import (
    list_conversations, get_messages, get_message_metadata,
    get_or_create_janus_conversation,
)
from shared.constants import PROJECT_TYPES, DEFAULT_CHAT_HISTORY
from shared.formatting import entity_list_to_df


def _load_projects(domain: str = "", status: str = "") -> list:
    """Fetch top-level projects for sidebar card rendering."""
    return list_items(domain=domain, status=status, entity_type="project", limit=100)


def _children_df(parent_id: str) -> pd.DataFrame:
    """Fetch child items for a given parent."""
    children = list_items(parent_id=parent_id, limit=100)
    return entity_list_to_df(children, [
        ("ID", "id:id"), ("Title", "title"), ("Type", "fmt:entity_type"),
        ("Status", "fmt:status"), ("Priority", "priority"),
    ])


def _all_items_df() -> pd.DataFrame:
    """Fetch all items for the List View tab."""
    items = list_items(limit=200)
    return entity_list_to_df(items, [
        ("ID", "id:id"), ("Title", "title"), ("Domain", "fmt:domain"),
        ("Type", "fmt:entity_type"), ("Status", "fmt:status"), ("Priority", "priority"),
    ])


def _load_tasks(status: str = "", assigned_to: str = "") -> list:
    """Fetch tasks as list of dicts for card rendering."""
    return list_tasks(status=status, assigned_to=assigned_to, limit=100)


def _all_tasks_df() -> pd.DataFrame:
    """Fetch all tasks for the List View."""
    tasks = list_tasks(limit=200)
    return entity_list_to_df(tasks, [
        ("ID", "id:id"), ("Title", "title"), ("Type", "fmt:task_type"),
        ("Assigned", "fmt:assigned_to"), ("Status", "fmt:status"), ("Priority", "fmt:priority"),
    ])


def _load_documents(doc_type: str = "", source: str = "") -> list:
    """Fetch documents as list of dicts for sidebar card rendering."""
    return list_documents(doc_type=doc_type, source=source, limit=100)


def _all_docs_df() -> pd.DataFrame:
    """Fetch all documents for the List View."""
    docs = list_documents(limit=200)
    return entity_list_to_df(docs, [
        ("ID", "id:id"), ("Title", "title"), ("Type", "fmt:doc_type"),
        ("Source", "fmt:source"), ("Created", "date:created_at"),
    ])


def _msgs_to_history(msgs: list[dict]) -> list[dict]:
    """Convert DB message rows to chat display history with reasoning."""
    history = []
    for m in msgs:
        history.append({"role": "user", "content": m["user_prompt"]})
        resp = m.get("model_response", "")
        reasoning = m.get("model_reasoning", "")
        if resp:
            if reasoning:
                formatted = (
                    f"<details><summary>Thinking</summary>\n\n"
                    f"{reasoning}\n\n</details>\n\n{resp}"
                )
                history.append({"role": "assistant", "content": formatted})
            else:
                history.append({"role": "assistant", "content": resp})
    return history


def _load_most_recent_chat() -> tuple[str, list[dict]]:
    """Load the Janus conversation for sidebar initialization."""
    conv_id = get_or_create_janus_conversation()
    msgs = get_messages(conv_id)
    if not msgs:
        return conv_id, list(DEFAULT_CHAT_HISTORY)
    history = _msgs_to_history(msgs)
    return conv_id, history if history else list(DEFAULT_CHAT_HISTORY)


def _windowed_api_history(api_history: list[dict], window: int) -> list[dict]:
    """Return the last N message pairs from API history for LLM context.

    Each turn is a user + assistant pair (2 entries). The window parameter
    specifies the number of turns, so we keep the last window*2 entries.

    Args:
        api_history: Full API history (list of role/content dicts).
        window: Number of turns to keep.

    Returns:
        Windowed subset of api_history.
    """
    max_entries = window * 2
    if len(api_history) <= max_entries:
        return list(api_history)
    return list(api_history[-max_entries:])


def _load_chat_session() -> dict:
    """Load the Janus conversation with full session data for sovereign chat.

    Returns dict with: conv_id, display_history, api_history, token_totals.
    Display history has reasoning in <details> accordion.
    API history has clean responses only (no HTML — prevents model mimicry).
    Token totals are cumulative across all turns in the conversation.
    """
    empty = {
        "conv_id": "",
        "display_history": list(DEFAULT_CHAT_HISTORY),
        "api_history": list(DEFAULT_CHAT_HISTORY),
        "token_totals": {"prompt": 0, "reasoning": 0, "response": 0, "total": 0},
        "turn_count": 0,
    }
    conv_id = get_or_create_janus_conversation()
    msgs = get_messages(conv_id)
    if not msgs:
        return {**empty, "conv_id": conv_id}

    display_history = []
    api_history = []
    totals = {"prompt": 0, "reasoning": 0, "response": 0, "total": 0}

    for m in msgs:
        user_msg = {"role": "user", "content": m["user_prompt"]}
        display_history.append(user_msg)
        api_history.append(user_msg)

        resp = m.get("model_response", "")
        reasoning = m.get("model_reasoning", "")
        if resp:
            # API history: clean response only
            api_history.append({"role": "assistant", "content": resp})
            # Display history: reasoning in accordion + clean response
            if reasoning:
                formatted = (
                    f"<details><summary>Thinking</summary>\n\n"
                    f"{reasoning}\n\n</details>\n\n{resp}"
                )
                display_history.append({"role": "assistant", "content": formatted})
            else:
                display_history.append({"role": "assistant", "content": resp})

        # Accumulate token counts
        totals["prompt"] += m.get("tokens_prompt", 0) or 0
        totals["reasoning"] += m.get("tokens_reasoning", 0) or 0
        totals["response"] += m.get("tokens_response", 0) or 0
        totals["total"] += (
            (m.get("tokens_prompt", 0) or 0)
            + (m.get("tokens_reasoning", 0) or 0)
            + (m.get("tokens_response", 0) or 0)
        )

    # Load timing from the last message's metadata (for sidebar restore)
    last_timings = {"rag": 0, "inference": 0, "total": 0}
    if msgs:
        last_meta = get_message_metadata(msgs[-1]["id"])
        if last_meta:
            last_timings = {
                "rag": last_meta.get("latency_rag_ms", 0) or 0,
                "inference": last_meta.get("latency_inference_ms", 0) or 0,
                "total": last_meta.get("latency_total_ms", 0) or 0,
            }

    return {
        "conv_id": conv_id,
        "display_history": display_history or list(DEFAULT_CHAT_HISTORY),
        "api_history": api_history or list(DEFAULT_CHAT_HISTORY),
        "token_totals": totals,
        "turn_count": len(msgs),
        "last_timings": last_timings,
    }


def _load_conversation_metrics(conv_id: str) -> list[dict]:
    """Load per-turn metrics for a conversation (JOIN messages + metadata).

    Returns a list of dicts ordered by turn number, each with:
    turn, tokens_prompt, tokens_reasoning, tokens_response,
    latency_total, latency_rag, latency_inference,
    rag_hit_count, rag_hits_used, avg_rerank, avg_salience, quality_score.
    """
    if not conv_id:
        return []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                m.sequence AS turn,
                COALESCE(m.tokens_prompt, 0) AS tokens_prompt,
                COALESCE(m.tokens_reasoning, 0) AS tokens_reasoning,
                COALESCE(m.tokens_response, 0) AS tokens_response,
                COALESCE(mm.latency_total_ms, 0) AS latency_total,
                COALESCE(mm.latency_rag_ms, 0) AS latency_rag,
                COALESCE(mm.latency_inference_ms, 0) AS latency_inference,
                COALESCE(mm.rag_hit_count, 0) AS rag_hit_count,
                COALESCE(mm.rag_hits_used, 0) AS rag_hits_used,
                COALESCE(mm.rag_avg_rerank, 0.0) AS avg_rerank,
                COALESCE(mm.rag_avg_salience, 0.0) AS avg_salience,
                mm.quality_score
            FROM messages m
            LEFT JOIN messages_metadata mm ON mm.message_id = m.id
            WHERE m.conversation_id = ?
            ORDER BY m.sequence
        """, (conv_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
