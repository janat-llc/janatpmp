# CLAUDE CODE TASK: Phase 6A Parser Extraction & Content Inventory

## CONTEXT
JANATPMP is a Gradio-based project management platform at `C:\Janat\JANATPMP`.  
We need to import content from multiple sources (Google AI Studio, Claude exports, markdown docs, quest files).  
Working parser code exists in an older pipeline project. Your job is to find it, inventory it, and port the best versions into JANATPMP.

**Before starting any work:**
1. Create and checkout branch `feature/phase6a-content-ingestion`
2. Update `CLAUDE.md` with Phase 6A context (content ingestion pipeline, new services/ingestion module)
3. Update `README.md` to reflect Phase 5 completion (RAG pipeline) and Phase 6A in-progress

## PHASE 1: INVENTORY (Do this FIRST, report before proceeding)

### 1A. Old Pipeline Code Inventory
Scan `C:\Janat\Janat.OpenWebUI\active_projects\data_pipeline\` and produce a structured inventory.

**What to find:**
- All Python files that handle JSON parsing for Google AI Studio exports
- All Python files that handle Claude export ingestion  
- All Python files that handle deduplication or quality scoring
- Any utility/helper files they depend on

**For each file found, record:**
- Full path
- File size
- First 5 lines (to identify purpose)
- Last modified date
- Key functions/classes defined (grep for `def ` and `class `)

**Also check these subdirectories if they exist:**
- `\archive\pipeline_libraries\`
- `\archive\pipeline_libraries\extraction_processing\`
- `\Claude\` 
- `\nexus_weaver\`

**DO NOT** read entire files. Use `head`, `grep`, and `stat` to inventory efficiently.

**Output:** Write inventory to `C:\Janat\JANATPMP\docs\INVENTORY_OLD_PARSERS.md`

### 1B. Content Corpus Inventory
Scan the content directories and produce file counts and sizes.

**Directories to scan:**
```
C:\Janat\JanatDocs\Unsorted\AIStudioConversations\        → count .json files, total size
C:\Janat\JanatDocs\Unsorted\AIStudioConversations\SuperClean\  → count .json files, total size  
C:\Janat\JanatDocs\Unsorted\AiStudio_Dedup_part_*.json    → count files, total size
C:\Janat\JanatDocs\Unsorted\quests\                       → count .json files, total size
C:\Janat\JanatDocs\Unsorted\ChatGPTConversations\          → count files, total size
C:\Janat\JanatDocs\Unsorted\TheJestersGrimoire.json        → file size
C:\Janat\Claude\Claude_Export\conversations.json            → file size
C:\Janat\Claude\Dyadic Being - An Epoch\                   → count .md files recursively, total size
C:\Janat\JanatDocs\Research\                               → count files recursively, total size
C:\Janat\JanatDocs\The JIRI Journal - Essays Papers Articles\ → count files, total size
```

**For each Google AI Studio JSON, sample ONE file** to confirm the schema structure:
- Does it have `chunkedPrompt.chunks[]` with `text`, `role`, `isThought`?
- Or is it a different format?
- Record the schema pattern.

**For quest files, sample ONE file** to confirm schema:
- What are the top-level keys?
- What does a quest record look like?
- Record the schema pattern.

**Output:** Write inventory to `C:\Janat\JANATPMP\docs\INVENTORY_CONTENT_CORPUS.md`

---

## PHASE 2: EXTRACT (Only after Phase 1 inventory is written and reviewed)

### 2A. Create Ingestion Module Directory
```
C:\Janat\JANATPMP\services\ingestion\
├── __init__.py
├── google_ai_studio.py    ← Parser for Google AI Studio JSON exports
├── quest_parser.py        ← Parser for Troubadourian quest JSON files
├── markdown_ingest.py     ← Parser for .md files (book chapters, docs, essays)
├── dedup.py               ← Deduplication utilities (exact hash first)
└── README.md              ← Documents each parser's expected input format
```

### 2B. Port Google AI Studio Parser
Find the BEST working version of the Google AI Studio parser from the old codebase.

**Known facts about the format:**
- Top-level has `runSettings`, `systemInstruction`, `chunkedPrompt`
- `chunkedPrompt.chunks[]` contains objects with `text`, `role` (user/model), `isThought` (boolean)
- Some files are extensionless JSON, some have .json extension
- Thoughts (`isThought: true`) should be PRESERVED (valuable for training data) but tagged separately
- Token counts may be present per chunk

**The parser should:**
1. Accept a file path or directory path
2. Parse Google AI Studio JSON format
3. Extract conversation turns as triplets: user_prompt, model_reasoning (thoughts), model_response
4. Return a list of dicts compatible with JANATPMP's conversation/message schema:
   ```python
   {
       "title": str,           # from systemInstruction or filename
       "source": "google_ai",
       "turns": [
           {
               "user_prompt": str,
               "model_reasoning": str | None,  # isThought content
               "model_response": str,
           }
       ]
   }
   ```
5. Handle edge cases: missing fields, empty chunks, extensionless files

**Port from old code where possible. Rewrite only what's broken.**

### 2C. Port Deduplication Logic
Find any existing dedup code. At minimum, implement:

```python
def compute_content_hash(text: str) -> str:
    """SHA-256 hash of normalized text (lowercase, stripped whitespace)"""

def find_exact_duplicates(messages: list) -> list[tuple]:
    """Returns pairs of (message_id_a, message_id_b) that are exact matches"""
```

### 2D. Create Markdown Ingester
Simple new code (likely no old version exists):

```python
def ingest_markdown(file_path: str) -> dict:
    """
    Read a markdown file and return:
    {
        "title": str,        # from first # heading or filename
        "content": str,      # full text
        "doc_type": str,     # inferred: chapter, essay, session_notes, etc.
        "source": "markdown",
        "word_count": int,
    }
    """
```

### 2E. Create Quest Parser
Parse Troubadourian quest JSONs. Schema will be determined in Phase 1.

**Known context:** Quest files contain memory triplets from the Troubadourian Amphitheatre system:
- Memory A + Memory B + Justification Node
- Salience scores (scored against an older constitution — values are dated but structure is valuable)
- Oracle reasoning and Council reflections

The parser should preserve the full structure. These are training data templates for Salience Engine v2.

---

## PHASE 3: UPDATE PROJECT DOCS

### 3A. Update CLAUDE.md
Add to CLAUDE.md:
- Phase 6A: Content Ingestion Pipeline
- New `services/ingestion/` module and its purpose
- Reference to inventory docs in `docs/`
- Note that Phase 5 (RAG pipeline) is complete

### 3B. Update README.md
- Mark Phase 5 (RAG/Vector Search) as complete
- Add Phase 6A (Content Ingestion) as in-progress
- Add `services/ingestion/` to the project structure section
- Update any outdated information

---

## CONSTRAINTS

- **DO NOT** modify any existing JANATPMP code (app.py, services/*, db/*)
- **DO NOT** install new packages without documenting them
- **DO NOT** read files larger than 50KB in full — use head/tail/grep
- **DO** write clean, documented Python with type hints
- **DO** include docstrings that describe expected input formats
- **DO** test parsers against sample files and include test output in the README
- Target Python 3.14, no deprecated features
- Commit frequently with descriptive messages

## DELIVERABLES CHECKLIST

- [ ] Branch `feature/phase6a-content-ingestion` created
- [ ] `CLAUDE.md` updated with Phase 6A context
- [ ] `README.md` updated for Phase 5 completion + Phase 6A
- [ ] `docs/INVENTORY_OLD_PARSERS.md` — old pipeline code inventory
- [ ] `docs/INVENTORY_CONTENT_CORPUS.md` — content corpus inventory with file counts, sizes, schema samples
- [ ] `services/ingestion/__init__.py`
- [ ] `services/ingestion/google_ai_studio.py` — tested against at least 1 sample file
- [ ] `services/ingestion/quest_parser.py` — tested against at least 1 sample file
- [ ] `services/ingestion/markdown_ingest.py` — tested against at least 1 sample file
- [ ] `services/ingestion/dedup.py` — with exact-match hash dedup
- [ ] `services/ingestion/README.md` — documents all formats and schemas discovered
- [ ] All changes committed to feature branch with descriptive messages

## IMPORTANT
Phase 1 (inventory) should be COMPLETED and WRITTEN TO DISK before starting Phase 2.
If the old pipeline directory structure is different than expected, document what you find and proceed with best judgment.
Do not burn tokens reading massive files. Inventory first, extract surgically.
