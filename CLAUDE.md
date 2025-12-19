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
├── janatpmp.db               # SQLite database file (runtime)
└── features/                 # Modular features package
    └── inventory/
        ├── __init__.py
        ├── scanner.py        # Directory scanning logic
        ├── models.py         # Data classes (Project, FileItem, ScanRun)
        └── config.py         # Scan configuration (extensions, skip dirs, markers)
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
# App launches at http://localhost:7860

# Initialize database (if needed)
python -m database
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

Three-table normalized design:
- `projects` - Detected project roots (path, type, detection timestamp)
- `files` - Indexed files (path, filename, extension, size, timestamps)
- `scan_runs` - Scan execution history

## Conventions

- Use `pathlib.Path` for all path handling (cross-platform compatibility)
- ISO format for all timestamps (`datetime.isoformat()`)
- File queries default to 500-item limit to prevent UI overload
- Extension filtering is whitelist-based (configured in `features/inventory/config.py`)
- Errors collected in result dicts rather than thrown

## Development Notes

- No test suite exists yet - testing infrastructure needs to be added
- Database path is hardcoded to `janatpmp.db` in project root
- Project detection features are placeholders (under development)
- Built for AI integration via Gradio's MCP support
