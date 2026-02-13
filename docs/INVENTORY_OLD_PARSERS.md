# Inventory: Old Pipeline Parser Code

**Date:** 2026-02-12
**Source:** `C:\Janat\Janat.OpenWebUI\curators_loom\`
**Purpose:** Identify reusable parser and utility code for Phase 6A content ingestion

---

## Summary

The old pipeline ("Curator's Consciousness Loom") lives at `C:\Janat\Janat.OpenWebUI\curators_loom\`.
It was built for extracting Google AI Studio conversations into a training data pipeline with
DeepSeek tokenization. The code is well-structured but tightly coupled to the old database schema
and tokenizer infrastructure.

**Recommendation:** Port the Google AI Studio parser logic (triplet extraction state machine)
from `google_ai_studio_parser.py`. Skip the token counting, database operations, and config
system — JANATPMP has its own. The dedup hash logic in `file_utils.py` is clean and portable.

---

## Core Parser Files

### `pipeline_libraries/extraction_processing/google_ai_studio_parser.py`
- **Size:** 12,876 bytes
- **Last Modified:** 2025-09-24
- **Purpose:** Handles extraction of User+Thought+Assistant triplets from Google AI Studio format.
  Core v3_unified extraction logic with DeepSeek token counting.
- **Key Functions/Classes:**
  | Line | Name | Notes |
  |------|------|-------|
  | 21 | `class GoogleAIStudioParser` | Wrapper class (thin) |
  | 43 | `extract_google_ai_studio_turns_v3_unified_with_tokens()` | **Main parser** — state machine that walks `chunkedPrompt.chunks[]`, groups user/thought/model into triplets. Token counting via external counter. |
  | 149 | `finalize_triplet_with_tokens()` | Calculates per-triplet token count |
  | 174 | `extract_google_ai_studio_turns_v3_unified()` | Same parser without token counting |
  | 192 | `_extract_turns_legacy()` | Older extraction path |
  | 267 | `validate_triplet_completeness()` | Stats: counts complete vs incomplete triplets |
  | 297 | `format_triplet_for_training()` | Formats triplet dict for fine-tuning output |
- **Port Value:** HIGH — the triplet extraction state machine is exactly what we need.
  Strip token counting and old DB dependencies. The `isThought` handling is proven.

### `pipeline_libraries/extraction_processing/extraction_pipeline.py`
- **Size:** 14,533 bytes
- **Last Modified:** 2025-09-24
- **Purpose:** Main orchestration logic for conversation extraction workflow with DeepSeek tokenization.
  Handles file processing, database operations, and pipeline coordination.
- **Key Functions/Classes:**
  | Line | Name | Notes |
  |------|------|-------|
  | 35 | `class ExtractionPipeline` | Orchestrator class |
  | 68 | `run_extraction_pipeline_with_tokens()` | Directory walker — iterates JSON files, calls parser, inserts to DB |
  | 160 | `process_single_file_with_tokens()` | Per-file processing: load JSON, extract triplets, check duplicates, insert |
  | 252 | `insert_conversation_with_tokens()` | Direct SQL INSERT (old schema) |
  | 286 | `store_turn_token_counts()` | Writes to `turn_metadata` table |
  | 319 | `run_extraction_pipeline()` | Legacy wrapper |
  | 330 | `validate_extraction_results()` | Post-run validation |
- **Port Value:** LOW — too coupled to old DB schema and token counter. The directory-walking
  pattern is trivial to rewrite. Skip this file.

### `pipeline_libraries/extraction_processing/extraction_utilities.py`
- **Size:** 7,128 bytes
- **Last Modified:** 2025-12-30
- **Purpose:** Helper functions for conversation extraction processing. System prompt loading,
  file metadata processing, and utility functions.
- **Key Functions:**
  | Line | Name | Notes |
  |------|------|-------|
  | 24 | `load_canonical_system_prompt()` | Loads system prompt via PromptManager (old infra) |
  | 45 | `process_file_metadata()` | Extracts filename, size, hash, timestamps |
  | 83 | `calculate_extraction_hash()` | SHA-256 of triplet content for change detection |
  | 112 | `get_extraction_statistics()` | Calculates stats over triplet list |
  | 167 | `validate_file_format()` | Checks for `chunkedPrompt.chunks[]` with `role` key |
  | 207 | `create_backup_metadata()` | Creates metadata dict for backups |
- **Port Value:** MEDIUM — `calculate_extraction_hash()` and `validate_file_format()` are useful.
  The rest is old infrastructure. Cherry-pick the hash logic.

### `pipeline_libraries/extraction_processing/format_validators.py`
- **Size:** 9,749 bytes
- **Last Modified:** 2025-09-19
- **Purpose:** Content validation and format checking for extracted conversation data.
- **Key Functions/Classes:**
  | Line | Name | Notes |
  |------|------|-------|
  | 21 | `class TurnTripletValidator` | Configurable validator with thresholds |
  | 71 | `validate_turn_triplet()` | Checks triplet has required fields, non-empty content |
  | 118 | `validate_conversation_data()` | Validates full conversation dict |
  | 170 | `clean_turn_content_enhanced()` | Strips artifacts, normalizes whitespace |
  | 202 | `validate_content_quality()` | Scores content quality (length, diversity, etc.) |
  | 251 | `detect_content_issues()` | Flags truncation, encoding errors, etc. |
- **Port Value:** LOW — over-engineered for our needs. The content cleaning is useful but
  can be simplified to a 10-line function. Skip the validator class.

---

## Utility Files (in `common/`)

### `common/file_utils.py`
- **Size:** 3,177 bytes | **Modified:** 2025-12-30
- **Functions:** `get_file_timestamps()`, `calculate_file_hash()`, `calculate_content_hash()`
- **Port Value:** HIGH — `calculate_content_hash()` is SHA-256 based dedup, exactly what we need.

### `common/content_utils.py`
- **Size:** 11,587 bytes | **Modified:** 2025-12-30
- **Functions:** `validate_and_truncate_content()`, `calculate_variation_token_limit()`,
  `detect_problematic_content()`, `clean_api_json_string()`, `clean_turn_content()`
- **Port Value:** LOW — mostly for LLM API response cleaning. `clean_turn_content()` may
  be useful but is simple enough to rewrite.

### `common/json_utils.py`
- **Size:** 17,782 bytes | **Modified:** 2025-12-30
- **Functions:** `safe_json_parse()`, `robust_json_cleaner()`, `extract_json_from_markdown()`
- **Port Value:** NONE — handles malformed LLM JSON responses. Our input files are well-formed.

### `common/conversation_service.py`
- **Size:** 19,972 bytes | **Modified:** 2025-12-30
- **Purpose:** `ConversationService` class — full DB CRUD for old schema.
- **Port Value:** NONE — JANATPMP has its own `db/chat_operations.py`.

### `common/database_utils.py`
- **Size:** 8,839 bytes | **Modified:** 2025-12-30
- **Functions:** `check_conversation_exists()`, `insert_conversation()`
- **Port Value:** NONE — old schema.

### `common/token_utils.py`
- **Size:** 13,841 bytes | **Modified:** 2025-09-24
- **Purpose:** DeepSeek tokenizer integration for token counting.
- **Port Value:** NONE — JANATPMP uses sentence-transformers for embedding, not DeepSeek tokenizer.

---

## Other Directories Checked

| Path | Result |
|------|--------|
| `C:\Janat\active_projects\data_pipeline\` | Contains `build_pipeline_needle` and `Gradio-App-Designer` — Gradio custom components, NOT parsers. No extraction code here. |
| `archive\pipeline_libraries\` | Does not exist under curators_loom |
| `Claude\` | Does not exist under curators_loom |
| `nexus_weaver\` | Does not exist under curators_loom |

---

## Porting Plan

| Source | Target | Action |
|--------|--------|--------|
| `google_ai_studio_parser.py` → triplet extraction state machine | `services/ingestion/google_ai_studio.py` | Port & simplify (remove token counting, old imports) |
| `file_utils.py` → `calculate_content_hash()` | `services/ingestion/dedup.py` | Port directly |
| `extraction_utilities.py` → `calculate_extraction_hash()` | `services/ingestion/dedup.py` | Port directly |
| `extraction_utilities.py` → `validate_file_format()` | `services/ingestion/google_ai_studio.py` | Inline as validation helper |
| `format_validators.py` → `clean_turn_content_enhanced()` | `services/ingestion/google_ai_studio.py` | Simplify to basic content cleaner |
| Everything else | — | Skip (old infrastructure) |
