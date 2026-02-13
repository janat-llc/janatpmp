"""
Content Ingestion Module

Parsers for importing conversations and documents from various sources
into the JANATPMP database and vector store.

Supported formats:
- Google AI Studio JSON exports (chunkedPrompt format)
- Troubadourian quest JSON files
- Markdown files (.md)
- Plain text files (.txt)
- Deduplication utilities

See README.md in this directory for format documentation.
"""

from .google_ai_studio import parse_google_ai_studio_file, parse_google_ai_studio_directory
from .quest_parser import parse_quest_file, parse_quest_directory
from .markdown_ingest import ingest_markdown, ingest_text, ingest_directory
from .dedup import compute_content_hash, find_exact_duplicates
