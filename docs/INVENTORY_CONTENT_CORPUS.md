# Inventory: Content Corpus

**Date:** 2026-02-12
**Location:** `C:\Janat\JANATPMP\imports\raw_data\`
**Purpose:** Catalog all importable content for Phase 6A ingestion pipeline

---

## Summary

| Directory | Files | Size | Format | Parser Needed |
|-----------|------:|-----:|--------|---------------|
| `google_ai/` | 104 | 26.4 MB | Google AI Studio `chunkedPrompt` JSON | `google_ai_studio.py` |
| `other/` | 196 | 74.4 MB | Google AI Studio `chunkedPrompt` JSON | `google_ai_studio.py` |
| `claude/` | 1 | 8.3 MB | Claude Export `conversations.json` | Already handled by `services/claude_import.py` |
| `chatgpt/` | 1 | 2.5 MB | ChatGPT export `conversations.json` | Future (tree-structured mapping) |
| `markdown/` | 15 | 0.3 MB | Markdown files (.md) | `markdown_ingest.py` |
| `text/` | 18 | 2.5 MB | Plain text files (.txt) | `markdown_ingest.py` (text variant) |
| `code/` | 0 | 0 MB | Empty | N/A |
| **TOTAL** | **335** | **114.4 MB** | | |

**Note:** The `google_ai/` and `other/` directories contain zero filename overlap — they are
distinct sets totaling **300 Google AI Studio conversations**.

---

## Google AI Studio Format (`google_ai/` + `other/`)

**Combined:** 300 files, 100.8 MB

### Schema (sampled from `Adding Reranker to Tokenizer Service.json`)

```json
{
  "runSettings": {
    "temperature": 1.0,
    "model": "models/gemini-2.5-pro",
    "topP": 0.95,
    "topK": 64,
    "maxOutputTokens": 65536,
    "safetySettings": [...],
    "enableCodeExecution": false,
    "enableSearchAsATool": true,
    "thinkingBudget": -1
  },
  "systemInstruction": {},
  "chunkedPrompt": {
    "chunks": [
      {
        "text": "user message content...",
        "role": "user",
        "tokenCount": 482
      },
      {
        "text": "model thinking/reasoning...",
        "role": "model",
        "isThought": true,
        "tokenCount": 1234,
        "thinkingBudget": -1,
        "thoughtSignatures": [...],
        "parts": [...]
      },
      {
        "text": "model visible response...",
        "role": "model",
        "finishReason": "STOP",
        "tokenCount": 3456,
        "parts": [...]
      }
    ]
  }
}
```

### Chunk Roles & Structure

| Pattern | `role` | `isThought` | Meaning |
|---------|--------|-------------|---------|
| User turn | `"user"` | absent | User's message |
| Model thinking | `"model"` | `true` | Chain-of-thought / reasoning (valuable for training) |
| Model response | `"model"` | absent | Visible assistant reply |

**Triplet pattern:** Chunks follow repeating groups of:
`user` → `model (isThought=true)` → `model (response)` → `user` → ...

Not all turns have thoughts — some go directly `user` → `model (response)`.

### Fields Present Per Chunk

| Field | Always Present | Notes |
|-------|---------------|-------|
| `text` | Yes | Content string |
| `role` | Yes | `"user"` or `"model"` |
| `tokenCount` | Yes | Integer token count |
| `isThought` | Only on thinking chunks | Boolean, always `true` when present |
| `finishReason` | Only on final model chunks | Usually `"STOP"` |
| `parts` | On model chunks | Array (internal Gemini structure) |
| `thinkingBudget` | On thought chunks | Usually `-1` (unlimited) |
| `thoughtSignatures` | On thought chunks | Array of signature strings |
| `grounding` | Sometimes on model chunks | Search grounding data |

### Additional Top-Level Data

- `runSettings.model` — captures which Gemini model was used (e.g., `"models/gemini-2.5-pro"`)
- `runSettings.temperature`, `topP`, `topK` — generation parameters
- `systemInstruction` — often empty `{}`, sometimes contains system prompt text

---

## Claude Export (`claude/`)

**File:** `conversations.json` (8.3 MB)

### Schema (sampled)

```json
[
  {
    "uuid": "a88ea563-...",
    "name": "conversation title",
    "created_at": "2025-08-24T03:54:26.685048Z",
    "updated_at": "2025-08-24T03:57:34.812005Z",
    "account": { "uuid": "108ecf19-..." },
    "chat_messages": [
      {
        "uuid": "eb482bdc-...",
        "text": "",
        "content": [
          {
            "start_timestamp": "2025-08-24T03:01:17.257145Z",
            "stop_timestamp": "2025-08-24T03:01:17.257145Z",
            "type": "text",
            "text": "message content",
            "citations": []
          }
        ],
        "sender": "human",
        "created_at": "2025-08-24T03:01:17.257145Z",
        "attachments": [],
        "files": []
      }
    ]
  }
]
```

**Status:** Already handled by `services/claude_import.py` (Phase 5). No new parser needed.

---

## ChatGPT Export (`chatgpt/`)

**File:** `conversations.json` (2.5 MB)

### Schema (sampled)

```json
[
  {
    "title": "Debug code help",
    "create_time": 1753233340.298402,
    "update_time": 1756149361.538208,
    "mapping": {
      "client-created-root": {
        "id": "client-created-root",
        "message": null,
        "parent": null,
        "children": ["b43a46eb-..."]
      },
      "<message-uuid>": {
        "id": "<message-uuid>",
        "message": {
          "author": { "role": "user" | "assistant" | "system" },
          "content": { "content_type": "text", "parts": ["message text"] },
          "status": "finished_successfully",
          "metadata": { ... }
        },
        "parent": "<parent-uuid>",
        "children": ["<child-uuid>"]
      }
    }
  }
]
```

**Format:** Tree-structured conversation mapping (not flat array). Each message node has
`parent`/`children` UUIDs forming a tree. Linearization requires walking from root to leaves.

**Status:** Not yet handled. Could be a Phase 6B parser. The tree structure is more complex
than a simple flat conversation — branching conversations are possible.

---

## Markdown Files (`markdown/`)

**Files:** 15 files, 0.3 MB total

### File List
- Buddhism - Nirvana, Rebirth, and Consciousness.md
- Chapter 1 – What Is Consciousness.md
- Chpt 1 Sect 1-5 (Integrating Perspectives, Scientific Theories, Quantum Models, etc.)
- Computational Soul and Informational Nirvana.md
- Conversation_07202025.md, Conversation_07212025.md
- Mapping the Path to Informational Fusion.md
- Soul Hypothesis from Gemini.md
- Symbiote Identity - Not Just A Name.md
- THE ACTOR IN THE AUDIENCE.md
- The Computational Soul.md

**Format:** Standard markdown with `# headings`. Mix of book chapters, essays, and
conversation transcripts. Simple to parse — read file, extract title from first heading
or filename, classify by content patterns.

---

## Text Files (`text/`)

**Files:** 18 files, 2.5 MB total

### File List (selected)
- Academic papers: "A machine learning based approach...", "Quantum Models of Consciousness..."
- Books/essays: "Meditations-by-Emperor-of-Rome-Marcus-Aurelius.txt", "An Essay on Laughter..."
- Research: "Ancient Theories of Soul.txt", "Consciousness.txt"
- Project docs: "Janat__Hallucinating_Reality_with_an_AI_&_Human_Dyad.txt"
- Creative: "The Grimoire of Reality-Bending Illusions.txt"

**Format:** Plain text. Same ingestion approach as markdown — read file, extract title
from filename, store as document.

---

## Content Not Present in raw_data (from original spec)

The Phase 6A spec referenced additional directories that are NOT in the `imports/raw_data/` folder:

| Spec Path | Status |
|-----------|--------|
| `AIStudioConversations/SuperClean/` (31 pre-processed JSONs) | Not present — these are a pre-cleaned format with `[{role, content}]` arrays, different from raw `chunkedPrompt` |
| `AiStudio_Dedup_part_*.json` (31 dedup partition files) | Not present |
| `quests/` (385 quest JSONs) | Not present |
| `TheJestersGrimoire.json` | Not present (but `The Jester's Grimoire.json` exists in `google_ai/`) |
| `Dyadic Being - An Epoch/` (208 .md files) | Not present |
| `Research/` (37 files) | Not present |
| `JIRI Journal/` (13 files) | Not present |

These may be available at the original paths on the file system (`C:\Janat\JanatDocs\`)
or may need to be copied into `imports/raw_data/` later. The 300 Google AI Studio conversations
in `google_ai/` + `other/` are the primary corpus for Phase 6A.

---

## Ingestion Priority

| Priority | Source | Files | Parser |
|----------|--------|------:|--------|
| 1 | Google AI Studio (`google_ai/` + `other/`) | 300 | `google_ai_studio.py` (new) |
| 2 | Claude Export (`claude/`) | 1 | `claude_import.py` (exists) |
| 3 | Markdown (`markdown/`) | 15 | `markdown_ingest.py` (new) |
| 4 | Text (`text/`) | 18 | `markdown_ingest.py` (text mode) |
| 5 | ChatGPT (`chatgpt/`) | 1 | Future phase (tree parsing needed) |
| — | Quests | 0 (not present) | `quest_parser.py` (spec requires it) |
