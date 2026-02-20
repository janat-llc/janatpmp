# JANATPMP — Janat Project Management Platform

![Python 3.14](https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white)
![Gradio 6.5.1](https://img.shields.io/badge/Gradio-6.5.1-orange?logo=gradio&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20%2B%20FTS5-003B57?logo=sqlite&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-46%20Tools-blueviolet)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

A **strategic command center** for solo architects and engineers working with AI partners. JANATPMP gives your AI assistants persistent memory — project state, task queues, documents, conversation history, and semantic search — all readable and writable via [MCP (Model Context Protocol)](https://modelcontextprotocol.io/). Conversations become durable, searchable knowledge. Context survives session boundaries.

Built by and for [The Janat Initiative](https://janatinitiative.org), powering consciousness architecture research across multiple domains.

---

## Architecture

### System Overview

```mermaid
graph TB
    subgraph Docker Compose
        Core[JANATPMP Core<br/>Gradio 6.5.1 + ATLAS<br/>GPU · Port 7860]
        Ollama[Ollama<br/>Nemotron-3-Nano<br/>GPU · Port 11435]
        Qdrant[Qdrant<br/>Vector Search<br/>Port 6343]
    end

    SQLite[(SQLite<br/>WAL + FTS5)]
    Core --> SQLite
    Core --> Ollama
    Core --> Qdrant
    Core -. ATLAS .-> Core

    Claude[Claude Desktop<br/>via MCP] --> Core
    Browser[Web Browser<br/>Desktop / Mobile] --> Core
```

### Data Flow

```mermaid
graph TB
    MCP[MCP Tools<br/>46 operations] --> DB[db/operations.py]
    UI[Gradio UI] --> DB
    API[REST API] --> DB
    DB --> SQLite[(SQLite)]
    DB --> Qdrant[(Qdrant)]
```

One set of functions in `db/operations.py` serves all three surfaces — UI event listeners, REST API, and MCP tool generation — a single source of truth for every operation.

---

## Features

- **46 MCP tools** for AI assistant integration (items, tasks, documents, domains, conversations, relationships, vectors, settings, backups)
- **Multi-provider chat** with triplet message persistence (Anthropic, Gemini, Ollama/local models)
- **ATLAS two-stage search** — ANN retrieval + cross-encoder reranking with salience write-back
- **RAG pipeline** — Qdrant vector search with GPU-accelerated NVIDIA Llama-Nemotron-Embed-VL-1B-v2 embeddings (2048-dim, multimodal)
- **Content ingestion** — parsers for Google AI Studio, quest files, markdown, and text with SHA-256 deduplication
- **Dynamic domain management** — domains are first-class database entities, creatable via MCP without code changes
- **Project / Task / Document management** with typed relationships and hierarchy
- **Claude conversation import** — ingest Claude export JSON into a searchable triplet schema
- **Full-text search** via SQLite FTS5 across items, documents, and conversation messages
- **Single-page responsive UI** with dual collapsible sidebars (mobile-friendly via `gr.Sidebar`)
- **Auto-context injection** — every chat message receives a live snapshot of active projects and pending tasks
- **Change Data Capture** outbox for future graph database sync

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | Gradio 6.5.1 (Blocks, MCP server mode) |
| Language | Python 3.14 |
| Database | SQLite (WAL mode, FTS5 full-text search) |
| Vector DB | Qdrant — semantic search over documents and messages |
| Embeddings | NVIDIA Llama-Nemotron-Embed-VL-1B-v2 (2048-dim, multimodal, GPU) |
| Reranking | NVIDIA Llama-Nemotron-Rerank-VL-1B-v2 (cross-encoder, GPU) |
| ML Runtime | PyTorch 2.10+ (CUDA 12.8) + Transformers 4.47+ |
| Inference | Ollama — Nemotron-3-Nano (default), DeepSeek-R1, Qwen3, Phi-4 |
| Container | Docker Compose (Python 3.14-slim + NVIDIA GPU passthrough for core + Ollama) |
| Data Display | Pandas DataFrames |

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (for GPU-accelerated inference)

### Run

```bash
git clone <repo-url> && cd JANATPMP
docker-compose up --build
```

Once running:

| Surface | URL |
|---------|-----|
| Web UI | http://localhost:7860 |
| MCP endpoint | http://localhost:7860/gradio_api/mcp/sse |
| API docs | http://localhost:7860/gradio_api/docs |
| Qdrant dashboard | http://localhost:6343/dashboard |

The UI is accessible from any device on the same LAN (mobile, tablet, etc.).

### Local Development (no Docker)

```bash
pip install -r requirements.txt
python app.py
```

---

## Project Structure

```
JANATPMP/
├── app.py                     # Orchestrator: init, build_page(), gr.api(), launch
├── janat_theme.py             # Custom Gradio theme (Janat brand colors + CSS)
├── assets/
│   └── janat_logo_bold_transparent.png  # Janat Mandala logo
├── pages/
│   └── projects.py            # UI layout + event wiring
├── tabs/
│   ├── tab_database.py        # Admin tab builder
│   ├── tab_chat.py            # Chat handler functions
│   └── tab_knowledge.py       # Knowledge tab handlers
├── shared/
│   ├── constants.py           # Enum lists, magic numbers, defaults
│   ├── formatting.py          # Display helpers (fmt_enum, entity_list_to_df)
│   ├── data_helpers.py        # Data-loading helpers
│   └── exceptions.py          # Custom exception hierarchy
├── db/
│   ├── schema.sql             # Database DDL
│   ├── operations.py          # 26 CRUD + lifecycle functions
│   ├── chat_operations.py     # Conversation + message CRUD
│   ├── migrations/            # Versioned schema migrations
│   └── backups/               # Timestamped database backups
├── atlas/
│   ├── config.py              # Model identifiers, dimensions, salience constants
│   ├── embedding_service.py   # NemotronEmbedder (VL, GPU, bfloat16, eager attn)
│   ├── reranking_service.py   # NemotronReranker (cross-encoder, GPU)
│   ├── memory_service.py      # Salience write-back to Qdrant
│   └── pipeline.py            # Two-stage search orchestrator
├── services/
│   ├── log_config.py          # SQLite log handler + setup_logging()
│   ├── chat.py                # Multi-provider chat with tool use
│   ├── settings.py            # Settings registry with validation
│   ├── claude_export.py       # Claude Export ingestion service
│   ├── claude_import.py       # Claude JSON → triplet messages
│   ├── embedding.py           # Thin shim → atlas/embedding_service.py
│   ├── vector_store.py        # Qdrant ops + two-stage search pipeline
│   ├── bulk_embed.py          # GPU batch embed with checkpointing
│   └── ingestion/             # Content ingestion parsers
├── Dockerfile                 # Python 3.14-slim + PyTorch CUDA 12.8
├── docker-compose.yml         # Multi-container orchestration
├── Janat_Brand_Guide.md       # Design system (colors, fonts)
└── CLAUDE.md                  # Development guidelines for AI assistants
```

---

## MCP Integration

JANATPMP exposes **46 tools** via [Gradio's MCP server mode](https://www.gradio.app/guides/building-mcp-server-with-gradio). Any MCP-compatible client (Claude Desktop, Claude Code, Cursor, etc.) can connect to:

```
http://localhost:7860/gradio_api/mcp/sse
```

Full API documentation is available at `/gradio_api/docs` while the server is running.

### Tool Categories

| Category | Tools | Examples |
|----------|-------|---------|
| Items | `create_item`, `get_item`, `list_items`, `update_item`, `delete_item`, `search_items` | Projects, features, books — any hierarchical entity |
| Tasks | `create_task`, `get_task`, `list_tasks`, `update_task` | Work queue with assignment, priority, status |
| Documents | `create_document`, `get_document`, `list_documents`, `search_documents` | Session notes, research, artifacts, code |
| Domains | `get_domains`, `get_domain`, `create_domain`, `update_domain` | Organizational categories — database-managed, no code deploys needed |
| Relationships | `create_relationship`, `get_relationships` | Typed connections (blocks, enables, informs, etc.) |
| Conversations | `create_conversation`, `list_conversations`, `search_conversations`, `add_message`, `get_messages`, ... | Chat history with triplet schema |
| Vectors | `vector_search`, `vector_search_all`, `embed_all_documents`, `embed_all_messages`, `embed_all_domains`, `recreate_collections` | ATLAS two-stage search, GPU bulk embedding, collection management |
| System | `get_stats`, `get_schema_info`, `backup_database`, `restore_database`, `list_backups`, `reset_database` | Database administration |
| Import | `import_conversations_json` | Claude conversation JSON import |

All tools are auto-generated from Python docstrings — no separate API definition layer.

---

## UI Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  JANATPMP                                      Powered by [Janat]       │
├──────────────────────────────────────────────────────────────────────────┤
│  [Projects]  [Work]  [Knowledge]  [Chat]  [Admin]    ← Top-level tabs  │
├───────────┬──────────────────────────────────┬────────────────────────────┤
│  LEFT     │     CENTER CONTENT               │  RIGHT                    │
│  SIDEBAR  │                                  │  SIDEBAR                  │
│           │                                  │                           │
│  Context  │  Content changes per tab.        │  Janat Chat (continuous)  │
│  cards    │  Each tab can have sub-tabs      │  OR Chat Settings         │
│  Filters  │  (Detail / List views, etc.)     │  (when Chat tab active)   │
│  + New    │                                  │                           │
└───────────┴──────────────────────────────────┴────────────────────────────┘
```

Both sidebars collapse independently on mobile, leaving center content full-width.

---

## Screenshots

| View | Screenshot |
|------|-----------|
| Projects tab | ![Projects](screenshots/projects.png) |
| Chat tab | ![Chat](screenshots/chat.png) |
| Admin tab | ![Admin](screenshots/admin.png) |

---

## Database Schema

Nine core tables with FTS5 full-text search and a CDC outbox for future sync:

- **domains** — First-class organizational entity. 13 seeded domains (5 active, 8 inactive). Managed via MCP — no code deploys needed to add new domains.
- **items** — Projects, features, books, chapters. Hierarchical via `parent_id`. Domain validated against `domains` table.
- **tasks** — Work queue with agent/human assignment, retry logic, cost tracking, acceptance criteria.
- **documents** — Session notes, research, artifacts, conversation imports. FTS5 enabled.
- **relationships** — Universal typed connector between any two entities (items, tasks, documents, conversations).
- **conversations** — Chat sessions from any source (platform, Claude export, imported). Per-session model/provider config.
- **messages** — Triplet schema: `user_prompt` + `model_reasoning` + `model_response`. Designed for fine-tuning data extraction.
- **settings** — Key-value config with base64 obfuscation for secrets.
- **cdc_outbox** — Change Data Capture for future graph database synchronization.

---

## Development

See [`CLAUDE.md`](CLAUDE.md) for comprehensive development guidelines, including Gradio patterns, state management, and common pitfalls.

### Branch Naming

```
feature/{name}
```

### Workflow

1. Branch from `main`
2. Develop and test: `docker compose down && docker compose up -d --build`
3. Merge to main, delete feature branch

### Rules

- Never commit directly to `main`
- All `db/operations.py` functions must have full docstrings (Gradio uses them for MCP tool descriptions)
- All UI event listeners must include `api_visibility="private"`

---

## Future

JANATPMP will evolve into a **Nexus Custom Component** within The Nexus Weaver architecture. Planned integrations:

- **Neo4j** — Graph database for entity relationship traversal

Together with the existing SQLite and Qdrant, this forms the **Triad of Memory** (SQL + Vector + Graph). The CDC outbox table already provides forward-compatibility for this evolution.

---

## Credits

Built by **Mat Gallagher** — [Janat, LLC](https://janat.org) / [The Janat Initiative](https://janatinitiative.org)

| | |
|---|---|
| UI Framework | [Gradio](https://gradio.app) 6.5.1 |
| Local Inference | [Ollama](https://ollama.ai) + NVIDIA Nemotron |
| Vector Search | [Qdrant](https://qdrant.tech) |
| Embeddings | [NVIDIA Llama-Nemotron-Embed-VL-1B-v2](https://huggingface.co/nvidia/llama-nemotron-embed-vl-1b-v2) |
| Reranking | [NVIDIA Llama-Nemotron-Rerank-VL-1B-v2](https://huggingface.co/nvidia/llama-nemotron-rerank-vl-1b-v2) |
| Persistence | [SQLite](https://sqlite.org) |
