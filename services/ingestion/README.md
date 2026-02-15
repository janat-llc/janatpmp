# Content Ingestion Module

Parsers for importing conversations and documents from multiple sources
into JANATPMP's database and vector store.

## Parsers

### `google_ai_studio.py` — Google AI Studio JSON Exports

**Input:** JSON files with `chunkedPrompt.chunks[]` structure exported from Google AI Studio.

**Schema:**
```json
{
  "runSettings": { "model": "models/gemini-2.5-pro", ... },
  "systemInstruction": { },
  "chunkedPrompt": {
    "chunks": [
      { "text": "...", "role": "user", "tokenCount": 123 },
      { "text": "...", "role": "model", "isThought": true, ... },
      { "text": "...", "role": "model", "finishReason": "STOP", ... }
    ]
  }
}
```

**Chunk roles:**
- `role="user"` — User message
- `role="model"` + `isThought=true` — Chain-of-thought reasoning (preserved separately)
- `role="model"` (no `isThought`) — Visible assistant response

**Output:**
```python
{
    "title": str,              # from filename
    "source": "google_ai",
    "model": str | None,       # e.g. "models/gemini-2.5-pro"
    "system_instruction": str | None,
    "turns": [
        {
            "user_prompt": str,
            "model_reasoning": str | None,  # thought content
            "model_response": str,
        }
    ]
}
```

**Functions:**
- `parse_google_ai_studio_file(path)` — Parse a single file
- `parse_google_ai_studio_directory(path)` — Parse all `.json` files in a directory
- `validate_file(path)` — Check if a file is valid Google AI Studio format

**Test results (google_ai/ corpus):**
- 99/104 files parsed (5 empty/invalid)
- 1,304 total turns extracted
- 997 turns with model reasoning (76%)
- Average 13.2 turns per conversation

---

### `quest_parser.py` — Troubadourian Quest Files

**Input:** JSON files with Neo4j graph topology structures.

**Schema:**
```json
{
  "anchor": {
    "parent_node_label": "Memory",
    "parent_node_name": "Topic Name",
    "parent_node_id": "mem_001"
  },
  "topology_plan": {
    "nodes_to_create": [
      { "label": "Concept", "properties": { "name": "...", "content": "..." } }
    ],
    "relationships_to_create": [
      { "start_node": "...", "end_node": "...", "type": "INFORMS", "properties": { "salience": 0.85 } }
    ]
  }
}
```

**Output:**
```python
{
    "title": str,              # from anchor.parent_node_name or filename
    "source": "quest",
    "anchor": dict,
    "nodes": list[dict],
    "relationships": list[dict],
    "node_count": int,
    "relationship_count": int,
    "content_text": str,       # flattened for search indexing
}
```

**Functions:**
- `parse_quest_file(path)` — Parse a single quest file
- `parse_quest_directory(path)` — Parse all `.json` files in a directory
- `validate_quest_file(path)` — Check if a file has anchor + topology_plan

**Note:** Quest files contain memory triplets with salience scores from the
Troubadourian Amphitheatre. Scores were computed against an older constitution
(values are dated) but the graph structure is valuable as Salience Engine v2 training templates.

---

### `markdown_ingest.py` — Markdown & Text Files

**Input:** `.md` and `.txt` files.

**Output:**
```python
{
    "title": str,              # from first # heading or filename
    "content": str,            # full text
    "doc_type": str,           # chapter, essay, research, conversation, etc.
    "source": "markdown" | "text",
    "word_count": int,
}
```

**Functions:**
- `ingest_markdown(path)` — Parse a `.md` file
- `ingest_text(path)` — Parse a `.txt` file
- `ingest_directory(path)` — Parse all `.md` and `.txt` files in a directory

**Doc type classification** is pattern-based on title/filename:
chapter, conversation, journal, essay, research, creative, project_doc, documentation, general.

---

### `dedup.py` — Deduplication Utilities

**Functions:**
- `compute_content_hash(text)` — SHA-256 of normalized text (lowercase, collapsed whitespace)
- `compute_file_hash(path)` — SHA-256 of raw file bytes
- `compute_conversation_hash(turns)` — SHA-256 of concatenated user+response content
- `find_exact_duplicates(items, content_key)` — Returns `(id_a, id_b)` pairs of exact matches
- `find_duplicate_conversations(conversations)` — Returns duplicate conversation pairs

---

## Content Corpus

Located at `imports/raw_data/`:

| Directory | Files | Size | Parser |
|-----------|------:|-----:|--------|
| `google_ai/` | 104 | 26.4 MB | `google_ai_studio.py` |
| `other/` | 196 | 74.4 MB | `google_ai_studio.py` |
| `claude/` | 1 | 8.3 MB | `services/claude_import.py` (Phase 5) |
| `chatgpt/` | 1 | 2.5 MB | Future parser |
| `markdown/` | 15 | 0.3 MB | `markdown_ingest.py` |
| `text/` | 18 | 2.5 MB | `markdown_ingest.py` (text mode) |

See `docs/INVENTORY_CONTENT_CORPUS.md` for full details.
