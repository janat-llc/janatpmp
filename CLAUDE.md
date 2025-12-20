# CLAUDE.md - Project Guidelines for AI Assistants

## Project Overview

**JANATPMP (Janat Project Management Platform)** is a Gradio-based Python web application for codebase inventory management and analysis. It allows users to scan directories, discover projects, index files, and search through a codebase catalog.

**Status:** Alpha (v0.1)

## Tech Stack

- **Python** 3.14+
- **Gradio** 6.2.0+ with MCP (Model Context Protocol) support
- **SQLite3** for persistence
- **Pandas** for data manipulation

## Project Structure

```
JANATPMP/
├── app.py                    # Main Gradio application entry point
├── api.py                    # API layer - re-exports database and scanner functions
├── database.py               # SQLite database layer (schema, CRUD operations)
├── requirements.txt          # Python dependencies
├── pyproject.toml            # Project metadata and configuration
├── Dockerfile                # Container image definition
├── docker-compose.yml        # Container orchestration config
├── .dockerignore             # Files excluded from Docker build context
├── db/
│   ├── schema.sql            # Database schema definition
│   └── janatpmp.db           # SQLite database file (runtime, gitignored)
└── features/                 # Modular features package
    └── inventory/
        ├── __init__.py
        ├── scanner.py        # Directory scanning logic
        ├── models.py         # Data classes (Project, FileItem, ScanRun)
        └── config.py         # Scan configuration (extensions, skip dirs, markers)
```

## Commands

```bash
# Install dependencies (local development)
pip install -r requirements.txt

# Run the application (local)
python app.py
# App launches at http://localhost:7860

# Initialize database (if needed)
python -m database

# Docker commands
docker-compose build          # Build container image
docker-compose up             # Run container (foreground)
docker-compose up -d          # Run container (detached)
docker-compose down           # Stop container
docker-compose logs           # View container logs
```

## Architecture

**Layered Architecture:**
```
Gradio UI (app.py) → API Layer (api.py) → Business Logic (features/inventory/) → Data Access (database.py) → SQLite
```

**Key Patterns:**
- Context managers for database connections (`get_db_connection()`)
- Data classes for type-safe models
- Event-driven UI with Gradio `.click()` bindings
- Functions return dicts with `error` key instead of raising exceptions (API-friendly)

## Database Schema

Located at `db/janatpmp.db`, defined in `db/schema.sql`:

**Core Tables:**
- `items` - Projects/features across 12 domains (literature, janatpmp, janat, atlas, meax, etc.)
- `tasks` - Work queue for agents and users
- `documents` - Conversations, files, artifacts, research
- `relationships` - Universal connector between entities
- `cdc_outbox` - Change Data Capture for Qdrant/Neo4j sync
- `schema_version` - Migration tracking

**Features:**
- Full-text search via FTS5 on items and documents
- CDC triggers for eventual consistency with vector/graph stores
- JSON attributes for domain-specific data
- 12 seeded domain projects

## Conventions

- Use `pathlib.Path` for all path handling (cross-platform compatibility)
- ISO format for all timestamps (`datetime.isoformat()`)
- File queries default to 500-item limit to prevent UI overload
- Extension filtering is whitelist-based (configured in `features/inventory/config.py`)
- Errors collected in result dicts rather than thrown

## Docker

The application runs in a Docker container with live code reloading:
- **Image:** Python 3.14-slim base
- **Port:** 7860 (Gradio default)
- **Volume mount:** Local directory mounted at `/app` for live code changes without rebuild
- **MCP Server:** Enabled via `GRADIO_MCP_SERVER=True` environment variable

## Development Notes

- No test suite exists yet - testing infrastructure needs to be added
- Database located at `db/janatpmp.db` (configured in `database.py`)
- Project detection features are placeholders (under development)
- Built for AI integration via Gradio's MCP support
