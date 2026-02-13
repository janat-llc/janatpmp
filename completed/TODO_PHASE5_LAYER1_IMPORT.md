# Phase 5 — Layer 1: Claude Export Import Pipeline

## Goal
Import `conversations.json` (Claude export format) into JANATPMP's `conversations` + `messages` tables using the triplet schema (user_prompt + model_reasoning + model_response).

## Branch
```bash
git checkout -b phase5-rag-pipeline
```

## Deliverable
New file: `services/claude_import.py`

---

## Data Location and Scale

- **File**: `imports/claude/conversations.json` (159MB)
- **Conversations**: 603
- **Content blocks**: ~58,978 total (17,598 text + 13,799 thinking + 10,281 tool_use + 10,129 tool_result + 7,171 token_budget)
- **Note**: File is large — stream/iterate, don't hold entire parsed structure in memory longer than needed

## conversations.json Format Reference

Each conversation object looks like:
```json
{
  "uuid": "abc-123",
  "name": "Chat about physics",
  "created_at": "2024-08-15T...",
  "updated_at": "2024-12-01T...",
  "account": {"uuid": "user-uuid"},
  "chat_messages": [
    {
      "uuid": "msg-001",
      "sender": "human",
      "text": "What is gravity?",
      "content": [{"type": "text", "text": "What is gravity?"}],
      "created_at": "2024-08-15T..."
    },
    {
      "uuid": "msg-002",
      "sender": "assistant",
      "text": "",
      "content": [
        {"type": "thinking", "thinking": "The user is asking about..."},
        {"type": "text", "text": "Gravity is a fundamental force..."},
        {"type": "tool_use", "name": "web_search", "input": {"query": "..."}}
      ],
      "created_at": "2024-08-15T..."
    }
  ]
}
```

## Triplet Mapping Rules

1. Walk `chat_messages` in order
2. When `sender == "human"`: start a new triplet, set `user_prompt` from the human message text
3. When `sender == "assistant"` (following a human message): complete the triplet:
   - `model_reasoning` = concatenate all `content[]` blocks where `type == "thinking"` (use `block["thinking"]` field, join with `\n`)
   - `model_response` = concatenate all `content[]` blocks where `type == "text"` (use `block["text"]` field, join with `\n`)
   - `tools_called` = JSON array of tool names from `content[]` blocks where `type == "tool_use"` (use `block["name"]`)
   - Skip `type == "token_budget"` blocks entirely
   - Skip `type == "tool_result"` blocks (tool outputs are verbose and not useful for RAG retrieval)
4. If multiple assistant messages follow one human message, concatenate into the SAME triplet
5. If a human message has NO following assistant response, still create a row with empty `model_response`
6. If an assistant message appears with no preceding human message (e.g. system), set `user_prompt = ""` or skip — use judgment
7. `sequence` = 1-indexed position of the triplet within the conversation

## Conversation Mapping

| conversations.json field | JANATPMP conversations column |
|---|---|
| uuid | conversation_uri |
| name | title |
| "claude_export" (literal) | source |
| "anthropic" (literal) | provider |
| "claude" (literal) | model |
| created_at | created_at |
| updated_at | updated_at |
| len(triplets) | message_count |
| 1 | is_active |

## Implementation: `services/claude_import.py`

```python
"""Import Claude conversations.json into JANATPMP conversations + messages tables."""

import json
from pathlib import Path
from db.chat_operations import create_conversation, add_message

def import_conversations_json(file_path: str, skip_existing: bool = True) -> dict:
    """
    Import conversations from a Claude export conversations.json file.
    
    Args:
        file_path: Path to conversations.json
        skip_existing: If True, skip conversations whose UUID already exists 
                       (check conversation_uri). If False, replace.
    
    Returns:
        dict with keys: imported, skipped, errors, total_messages
    """
    # Implementation here
```

### Key Functions to Implement

1. **`import_conversations_json(file_path, skip_existing=True) -> dict`**
   - Main entry point
   - Reads JSON, iterates conversations, calls _import_single_conversation for each
   - Returns summary stats: {imported: int, skipped: int, errors: list, total_messages: int}

2. **`_import_single_conversation(conv_data: dict, skip_existing: bool) -> tuple[bool, int]`**
   - Creates conversation row via `create_conversation()`
   - Check: if `skip_existing` and conversation_uri already exists, return (False, 0)
   - Calls `_build_triplets()` to pair messages
   - Calls `add_message()` for each triplet
   - Returns (was_imported: bool, message_count: int)

3. **`_build_triplets(chat_messages: list[dict]) -> list[dict]`**
   - Core pairing logic per rules above
   - Returns list of dicts: {user_prompt, model_reasoning, model_response, tools_called, provider, model}
   - This is the most important function — get the pairing right

4. **`_extract_content_by_type(content_blocks: list[dict]) -> dict`**
   - Helper to split content[] blocks into {thinking: str, text: str, tools: list[str], tool_results: str}
   - Concatenates multiple blocks of same type with \n
   - **IMPORTANT field names from actual export data:**
     - `type="text"` → content is in `block["text"]`
     - `type="thinking"` → content is in `block["thinking"]` (NOT `block["text"]`!)
     - `type="tool_use"` → tool name is in `block["name"]`, input in `block["input"]`
     - `type="tool_result"` → result is in `block["content"]`
     - `type="token_budget"` → **SKIP entirely** (empty metadata, 7K+ occurrences)

### Important: Check if conversation_uri exists

The `create_conversation()` function in `db/chat_operations.py` may not support checking for existing `conversation_uri`. You may need to:
- Add a `get_conversation_by_uri(uri: str)` function to `db/chat_operations.py`
- OR use a direct SQL query in the import module

Prefer adding to `chat_operations.py` for consistency.

## UI Integration

Add to Knowledge tab → Conversations sub-tab, alongside existing "Ingest from Export Directory" button:

1. Add a `gr.File(label="Upload conversations.json", file_types=[".json"])` component
2. Add a `gr.Button("Import to JANATPMP")` 
3. On click: call `import_conversations_json(file.name)` 
4. Display results: "{imported} conversations imported, {skipped} skipped, {total_messages} messages"
5. After import: refresh the Chat tab's conversation list (update `conversations_state`)

**OR** — simpler approach: Add a setting `claude_export_json_path` and an import button that reads from the configured path. Mat can point it at the imports directory.

Both approaches are fine. The file upload is more user-friendly. The setting is more repeatable. Implement the file upload approach.

## Wiring in projects.py

In the Knowledge tab Conversations sub-tab section (~line 503-546), add:
- The file upload component and import button
- Event listener that calls `import_conversations_json` and refreshes stats

This wiring should be ~20-30 lines in projects.py. The actual logic lives in `services/claude_import.py`.

## Testing

After implementation:
1. Import a small test: create a test JSON with 2-3 conversations
2. Verify conversations appear in Chat tab sidebar
3. Verify clicking a conversation loads the triplet messages correctly
4. Verify re-import with skip_existing=True doesn't duplicate
5. Verify FTS works: search for a word that appears in imported messages
6. Verify CDC outbox has entries for the new conversations/messages

## Opportunistic Review

While working in this area, review `services/claude_export.py` (~180 lines). 
- If the existing `ingest_from_directory` function is no longer needed after this import pipeline replaces it, mark it as deprecated with a comment.
- If `claude_export.py` can be simplified or if functionality overlaps with `claude_import.py`, note it but don't refactor yet.

Also review the Knowledge tab Conversations sub-tab code in `projects.py` (~lines 503-546, wiring ~1245-1296):
- If there are sections of 200+ lines that are self-contained and could be extracted into their own file with a single import, do it.
- Do NOT force extractions that create complex import chains.

## Do NOT
- Touch the Chat tab implementation (it works)
- Modify the database schema (it's already correct)
- Add Qdrant/embedding logic (that's Layer 2)
- Refactor projects.py layout structure
- Change how the existing claude_export.db viewer works (it can coexist)
