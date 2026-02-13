# JANATPMP (Janat Project Management Platform)

A Gradio-based project management platform designed for solo architects and engineers
working with AI partners. Provides persistent project state that AI assistants can
read and write via MCP (Model Context Protocol).

**Status:** v1.0 (Hackathon Sprint — Feb 10-16, 2026)
**Origin:** Anthropic "Built with Opus 4.6" Claude Code competition (Feb 2026)

## Features

- **Projects, Work, Knowledge tabs** — CRUD for items, tasks, and documents with FTS5 search
- **Chat tab** — Multi-provider chat (Anthropic/Gemini/Ollama) with triplet message persistence
- **RAG pipeline** — Qdrant vector search with Llama-Nemotron-Embed-1B-v2 embeddings
- **Content ingestion** — Parsers for Google AI Studio, quest files, markdown, and text
- **MCP server** — 36+ tools auto-generated from function docstrings
- **Docker deployment** — Three-container stack (app, Ollama, Qdrant)

## Tech Stack

- Python 3.14+ / Gradio 6.5.1 / SQLite3 (WAL, FTS5) / Qdrant / Pandas

## Setup

```bash
# Local development
pip install -r requirements.txt
python app.py
# App at http://localhost:7860

# Docker (recommended)
docker-compose build
docker-compose up -d
# App at http://localhost:7860
# Qdrant dashboard at http://localhost:6343/dashboard
```

## Phase History

| Phase | Description | Status |
| ----- | ----------- | ------ |
| 1-2 | Multi-page layout, settings persistence | Complete |
| 3 | Knowledge tab — documents, search, connections | Complete |
| 3.5 | Claude Export integration, conversation browser | Complete |
| 4B | Chat experience — triplet messages, conversation persistence | Complete |
| 5 | RAG pipeline — Qdrant vector search, Claude import, embeddings | Complete |
| 6A | Content ingestion — parsers for Google AI Studio, quests, markdown | Complete |

See [CLAUDE.md](CLAUDE.md) for full architecture documentation.
