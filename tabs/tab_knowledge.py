"""Knowledge tab handlers — conversations, search, connections."""
import logging
import gradio as gr
import pandas as pd
from db.operations import (
    get_stats, search_items, search_documents,
    get_relationships, create_relationship,
)

logger = logging.getLogger(__name__)
from db.chat_operations import (
    get_messages, list_conversations, delete_conversation,
)
from services.settings import get_setting
from services.claude_export import ingest_from_directory
from services.claude_import import import_conversations_json
from shared.constants import DEFAULT_CHAT_HISTORY
from shared.formatting import fmt_enum
from shared.data_helpers import _msgs_to_history


# --- Conversation handlers ---

def _load_conv_stats():
    """Load conversation and message counts for display."""
    stats = get_stats()
    convs = stats.get("conversations", 0)
    msgs = stats.get("messages", 0)
    return (
        f"**{convs:,}** conversations · "
        f"**{msgs:,}** messages"
    )


def _load_conv_list():
    """Load conversation list as rows for DataFrame display."""
    convs = list_conversations(limit=500, active_only=False)
    return [[
        c.get("title", ""),
        fmt_enum(c.get("source", "")),
        c.get("message_count", 0),
        (c.get("updated_at") or "")[:16],
        c["id"],
    ] for c in convs]


def _load_selected_conversation(evt: gr.SelectData, df):
    """Load a conversation's messages when selected in the list."""
    if evt.index:
        row = evt.index[0]
        conv_id = df.iloc[row, 4]  # ID column
        msgs = get_messages(conv_id)
        history = _msgs_to_history(msgs)
        return history, conv_id
    return [], ""


def _run_ingest():
    """Ingest conversations from Claude export directory."""
    json_dir = get_setting("claude_export_json_dir")
    if not json_dir:
        return "Error: claude_export_json_dir not set in Settings."
    return ingest_from_directory(json_dir)


def _open_in_chat(conv_id):
    """Open a Knowledge conversation in the Chat tab."""
    if not conv_id:
        return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), "No conversation selected."
    msgs = get_messages(conv_id)
    history = _msgs_to_history(msgs) or list(DEFAULT_CHAT_HISTORY)
    convs = list_conversations(limit=30)
    return (
        conv_id,                       # active_conversation_id
        history,                       # chat_tab_chatbot
        history,                       # chat_tab_history
        convs,                         # conversations_state
        "Chat",                        # active_tab
        gr.Tabs(selected="chat"),      # main_tabs
        "",                            # conv_action_status
    )


def _delete_knowledge_conv(conv_id):
    """Delete a conversation from the Knowledge tab."""
    if not conv_id:
        return "No conversation selected.", gr.skip()
    delete_conversation(conv_id)
    convs = list_conversations(limit=30)
    return f"Deleted conversation.", convs


def _run_import(file):
    """Import conversations.json file into JANATPMP triplet schema."""
    if file is None:
        return "No file selected.", gr.skip()
    result = import_conversations_json(file.name)
    errors = result["errors"]
    msg = (
        f"{result['imported']} conversations imported, "
        f"{result['skipped']} skipped, "
        f"{result['total_messages']} messages"
    )
    if errors:
        msg += f"\n{len(errors)} errors: {errors[0]}"
    convs = list_conversations(limit=30)
    return msg, convs


# --- Search handlers ---

def _run_search(query):
    """Run universal FTS5 search across items and documents."""
    if not query or not query.strip():
        empty_items = pd.DataFrame(
            columns=["ID", "Title", "Domain", "Type", "Status"]
        )
        empty_docs = pd.DataFrame(
            columns=["ID", "Title", "Type", "Source", "Created"]
        )
        return empty_items, empty_docs

    q = query.strip()

    # Search items via FTS5
    try:
        items = search_items(q, limit=50)
    except Exception as e:
        logger.warning("Item search failed for '%s': %s", q, e)
        items = []
    if items:
        items_df = pd.DataFrame([{
            "ID": i["id"][:8],
            "Title": i["title"],
            "Domain": fmt_enum(i.get("domain", "")),
            "Type": fmt_enum(i.get("entity_type", "")),
            "Status": fmt_enum(i.get("status", "")),
        } for i in items])
    else:
        items_df = pd.DataFrame(
            columns=["ID", "Title", "Domain", "Type", "Status"]
        )

    # Search documents via FTS5
    try:
        found_docs = search_documents(q, limit=50)
    except Exception as e:
        logger.warning("Document search failed for '%s': %s", q, e)
        found_docs = []
    if found_docs:
        docs_df = pd.DataFrame([{
            "ID": d["id"][:8],
            "Title": d["title"],
            "Type": fmt_enum(d.get("doc_type", "")),
            "Source": fmt_enum(d.get("source", "")),
            "Created": d.get("created_at", "")[:16] if d.get("created_at") else "",
        } for d in found_docs])
    else:
        docs_df = pd.DataFrame(
            columns=["ID", "Title", "Type", "Source", "Created"]
        )

    return items_df, docs_df


# --- Connection handlers ---

def _lookup_connections(entity_type, entity_id):
    """Look up relationships for a given entity."""
    if not entity_id or not entity_id.strip():
        return pd.DataFrame(
            columns=["Relationship", "Direction", "Connected Type", "Connected ID", "Strength"]
        )

    eid = entity_id.strip()
    rels = get_relationships(entity_type=entity_type, entity_id=eid)

    if not rels:
        return pd.DataFrame(
            columns=["Relationship", "Direction", "Connected Type", "Connected ID", "Strength"]
        )

    rows = []
    for r in rels:
        if r["source_id"] == eid:
            rows.append({
                "Relationship": fmt_enum(r["relationship_type"]),
                "Direction": "-> outgoing",
                "Connected Type": r["target_type"],
                "Connected ID": r["target_id"][:8],
                "Strength": r.get("strength", "hard"),
            })
        else:
            rows.append({
                "Relationship": fmt_enum(r["relationship_type"]),
                "Direction": "<- incoming",
                "Connected Type": r["source_type"],
                "Connected ID": r["source_id"][:8],
                "Strength": r.get("strength", "hard"),
            })
    return pd.DataFrame(rows)


def _on_conn_create(source_type, source_id, target_type, target_id, rel_type):
    """Create a new relationship between two entities."""
    if not source_id.strip() or not target_id.strip():
        return "Both entity ID and target ID are required"
    try:
        rel_id = create_relationship(
            source_type=source_type,
            source_id=source_id.strip(),
            target_type=target_type,
            target_id=target_id.strip(),
            relationship_type=rel_type,
        )
        return f"Created connection {rel_id[:8]}"
    except Exception as e:
        return f"Error: {str(e)}"
