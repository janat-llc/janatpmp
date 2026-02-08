# CLAUDE.md - Project Guidelines for AI Assistants

## Project Overview

**JANATPMP (Janat Project Management Platform)** is a Gradio-based project management
platform designed for solo architects and engineers working with AI partners. It provides
persistent project state that AI assistants can read and write via MCP (Model Context Protocol).

**Status:** v0.2 (Hackathon Sprint — Feb 10-16, 2026)
**Hackathon:** Anthropic "Built with Opus 4.6" Claude Code competition
**Demo Story:** Cold start — user installs with empty database, AI partner helps build
project landscape from nothing.

## Tech Stack

- **Python** 3.14+
- **Gradio** 6.5.1 with MCP support (`gradio[mcp]==6.5.1`)
- **SQLite3** for persistence (WAL mode, FTS5 full-text search)
- **Pandas** for data display

## Current Sprint: TODO_HACKATHON_SPRINT_1.md

Read this file first. It contains the complete specification for the current work.

## Project Structure

```
JANATPMP/
├── app.py                    # Main Gradio application (UI + event handlers)
├── api.py                    # API layer - re-exports all operations for MCP
├── database.py               # Legacy file (deprecated, operations moved to db/)
├── requirements.txt          # Python dependencies (pinned)
├── pyproject.toml            # Project metadata
├── Dockerfile                # Container image (Python 3.14-slim)
├── docker-compose.yml        # Container orchestration (port 7860, volume mount)
├── CLAUDE.md                 # This file
├── TODO_HACKATHON_SPRINT_1.md # Current sprint specification
├── db/
│   ├── schema.sql            # Database schema DDL (NO seed data)
│   ├── seed_data.sql         # Optional seed data (separate from schema)
│   ├── operations.py         # All CRUD + lifecycle functions (19+ operations)
│   ├── test_operations.py    # Tests
│   ├── janatpmp.db           # SQLite database (runtime, gitignored)
│   ├── backups/              # Timestamped database backups
│   └── __init__.py
├── features/
│   └── inventory/            # Directory scanning feature (future)
└── completed/                # Archived TODO files
```

## Architecture

```
Gradio UI (app.py)
    ↓ event handlers call
DB Operations (db/operations.py)
    ↓ read/write
SQLite (db/janatpmp.db)

Simultaneously:
    Gradio API  → same functions → same database
    MCP Server  → same functions → same database
```

**Key principle:** One set of functions serves UI, API, and MCP. Every function in
`db/operations.py` with proper docstrings becomes an MCP tool automatically when
wired to a Gradio component.

## Database Schema (db/schema.sql)

**Core Tables:**
- `items` — Projects, features, books, etc. across domains. Supports hierarchy via parent_id.
  Has JSON attributes for domain-specific data. FTS5 full-text search enabled.
- `tasks` — Work queue with agent/human assignment. Supports retry logic, dependencies,
  acceptance criteria, cost tracking.
- `documents` — Conversations, files, artifacts, research. FTS5 enabled.
- `relationships` — Universal connector between any two entities. Typed relationships
  (blocks, enables, informs, etc.) with hard/soft strength.
- `cdc_outbox` — Change Data Capture for future Qdrant/Neo4j sync.
- `schema_version` — Migration tracking.

**Domain enum values:** literature, janatpmp, janat, atlas, meax, janatavern,
amphitheatre, nexusweaver, websites, social, speaking, life

## Commands

```bash
# Local development
pip install -r requirements.txt
python app.py
# App at http://localhost:7860, MCP at http://localhost:7860/gradio_api/mcp/sse

# Docker (preferred)
docker-compose build
docker-compose up              # foreground
docker-compose up -d           # detached
docker-compose down
docker-compose logs -f
```

## Conventions

- All functions in db/operations.py MUST have full docstrings with Args and Returns
  (Gradio uses these for MCP tool descriptions)
- Use `pathlib.Path` for all path handling
- ISO format for timestamps
- Empty string = "no filter" / "no change" in function parameters
- Functions return strings for status messages, dicts for single entities, lists for collections
- Context managers for database connections (`get_connection()`)
- Test each change by running the app — no separate test runner yet

## Docker

- **Image:** Python 3.14-slim
- **Port:** 7860
- **Volume:** `.:/app` for live code changes without rebuild
- **MCP:** Enabled via `GRADIO_MCP_SERVER=True` environment variable
- **CMD:** `gradio app.py` (uses Gradio's built-in server)

## Important Notes

- This is a HACKATHON project — favor completion over perfection
- The database starts EMPTY (no seed data). This is intentional for the demo.
- Every operation must work from all three surfaces: UI, API, MCP
- Do NOT add features not specified in the current TODO file
- When in doubt, ask — don't guess
