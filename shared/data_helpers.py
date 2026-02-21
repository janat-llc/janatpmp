"""Shared data-loading helpers for JANATPMP UI."""
import pandas as pd
from db.operations import list_items, list_tasks, list_documents
from db.chat_operations import list_conversations, get_messages
from shared.constants import PROJECT_TYPES, DEFAULT_CHAT_HISTORY
from shared.formatting import entity_list_to_df


def _load_projects(domain: str = "", status: str = "") -> list:
    """Fetch project-scope items as list of dicts for card rendering."""
    items = list_items(domain=domain, status=status, limit=100)
    return [i for i in items if i.get("entity_type") in PROJECT_TYPES]


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
    """Load most recent conversation for Chat tab initialization."""
    convs = list_conversations(limit=1)
    if not convs:
        return "", list(DEFAULT_CHAT_HISTORY)
    conv_id = convs[0]["id"]
    msgs = get_messages(conv_id)
    if not msgs:
        return conv_id, list(DEFAULT_CHAT_HISTORY)
    history = _msgs_to_history(msgs)
    return conv_id, history if history else list(DEFAULT_CHAT_HISTORY)


def _load_chat_session() -> dict:
    """Load most recent conversation with full session data for sovereign chat.

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
    convs = list_conversations(limit=1)
    if not convs:
        return empty
    conv_id = convs[0]["id"]
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

    return {
        "conv_id": conv_id,
        "display_history": display_history or list(DEFAULT_CHAT_HISTORY),
        "api_history": api_history or list(DEFAULT_CHAT_HISTORY),
        "token_totals": totals,
        "turn_count": len(msgs),
    }
