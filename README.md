# JANATPMP — Janat Project Management Platform

![Python 3.14](https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white)
![Gradio 6.6.0](https://img.shields.io/badge/Gradio-6.6.0-orange?logo=gradio&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20%2B%20FTS5-003B57?logo=sqlite&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-84%20Tools-blueviolet)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-2026.01.4-008CC1?logo=neo4j&logoColor=white)

A **strategic command center** for solo architects and engineers working with AI partners. JANATPMP gives your AI assistants persistent memory — project state, task queues, documents, conversation history, semantic search, and a knowledge graph — all readable and writable via [MCP (Model Context Protocol)](https://modelcontextprotocol.io/). Every message fans out to three stores (SQLite, Qdrant, Neo4j) — the **Triad of Memory**. Conversations become durable, searchable, graph-navigable knowledge. Context survives session boundaries.

Built by and for [The Janat Initiative](https://janatinitiative.org), powering consciousness architecture research across multiple domains.

---

## Architecture

### System Overview

```mermaid
graph TB
    subgraph Docker Compose
        Core[JANATPMP Core<br/>Gradio 6.6.0<br/>No GPU · Port 7860]
        Ollama[Ollama<br/>Chat + Embedding<br/>GPU · Port 11435]
        vLLM[vLLM Reranker<br/>DECOMMISSIONED]
        Qdrant[Qdrant<br/>Vector Search<br/>Port 6343]
        Neo4j[Neo4j<br/>Knowledge Graph<br/>Port 7474]
    end

    SQLite[(SQLite<br/>WAL + FTS5)]
    Core --> SQLite
    Core --> Ollama
    Core --> Qdrant
    Core --> Neo4j

    Claude[Claude Desktop<br/>via MCP] --> Core
    Browser[Web Browser<br/>Desktop / Mobile] --> Core
```

### Data Flow

```mermaid
graph TB
    MCP[MCP Tools<br/>81 operations] --> DB[db/operations.py<br/>db/chat_operations.py]
    UI[Gradio UI] --> DB
    API[REST API] --> DB
    DB --> SQLite[(SQLite)]
    DB -->|on_write| Qdrant[(Qdrant)]
    DB -->|CDC consumer| Neo4j[(Neo4j)]
    DB -->|on_write| Neo4j
```

Every mutation fans out to three stores via the **triple-write pipeline**: SQLite (source of truth), Qdrant (semantic retrieval via `atlas/on_write.py`), Neo4j (graph navigation via `graph/cdc_consumer.py`). One set of functions serves all surfaces — UI, REST API, and MCP.

---

## Features

- **84 MCP tools** for AI assistant integration (items, tasks, documents, domains, conversations, relationships, vectors, graph, telemetry, ingestion, chunks, entities, Janus lifecycle, backups, file registry, temporal context, semantic edges, dream synthesis, backfill orchestration, knowledge state, register mining)
- **Sovereign multipage architecture** — 4 independent pages (Projects, Knowledge, Admin, Chat) with client-side navbar navigation; one process, one port, one MCP surface; each page has purpose-built left sidebar + shared Janus right sidebar
- **Message chunking** — long messages and documents are split into focused ~2500-char chunks before embedding; each chunk gets its own Qdrant vector with parent traceability; RAG returns specific paragraphs instead of entire turns; paragraph-aware splitting with configurable thresholds
- **Triple-write pipeline** — every message, document, item, and task fans out to SQLite, Qdrant, and Neo4j synchronously; immediately retrievable on the next turn; messages and documents are chunked before embedding
- **Knowledge graph** — Neo4j with 10 entity types (including Chunk, Person, Identity), CDC consumer for structural edges, INFORMED_BY provenance tracing, SIMILAR_TO cross-conversation linking (message-level via Slumber keyword overlap + conversation-level via vector centroid similarity R20), PART_OF chunk-to-parent edges, identity graph with BECAME/SPOKE/PARTICIPATED_IN edges
- **Janus continuous chat** — one persistent conversation from platform birth, shared across all page sidebars and Sovereign Chat; sliding window sends last N turns to LLM while RAG handles historical context
- **Sovereign Chat** — dedicated chat page (`/chat`) with real-time metrics sidebar: RAG provenance, latency breakdown, token counts, salience scores
- **Multi-provider chat** with triplet message persistence (Anthropic, Gemini, Ollama/local models); Ollama in-app chat has 6 self-query tools for active memory retrieval (R32)
- **Thinking mode** — chain-of-thought captured separately via Ollama `think=True`, stored as `model_reasoning` in triplet schema for future fine-tuning
- **Reasoning token decomposition** — proportional split of completion tokens into reasoning vs response KPIs, even when providers don't report them separately
- **ATLAS semantic search** — ANN retrieval via Qdrant with salience write-back (cross-encoder reranker decommissioned)
- **Usage-based salience** — keyword overlap heuristic estimates which RAG hits the model actually used, feeding salience boosts/decays back to Qdrant
- **RAG pipeline** — Qwen3-Embedding-0.6B embeddings (1024-dim, Matryoshka) via Ollama, injected into chat context per-message
- **Cognitive telemetry** — per-turn timing, frozen RAG snapshots, and token counts persisted to `messages_metadata` for longitudinal analysis
- **Temporal Affinity Engine** — Janus knows current time, date, season, sunrise/sunset, and approximate temperature; pure-function solar calculations + NOAA climate normals; injected into every system prompt; RAG results carry relative time labels
- **Auto-ingestion** — startup + Slumber scanner walks configured directories, discovers new files by SHA-256 hash, ingests automatically without manual button clicks; file registry tracks processed files; real-time progress tracking through all phases
- **LLM-powered message evaluation** — Gemini Flash Lite scores message quality, extracts keywords, and classifies topics in the Slumber Cycle; heuristic fallback when API is unavailable; configurable via `slumber_evaluator` setting (R22)
- **Slumber Cycle** — 11-stage background daemon (Ingest, Evaluate, Propagate, Relate, Prune, Extract, Dream, Weave, Link, Decay, Mine) discovers new files, evaluates quality, bridges quality to Qdrant salience, creates cross-conversation graph edges, removes dead-weight vectors, extracts entities from scored messages, synthesizes cross-conversation insights, weaves semantic SIMILAR_TO edges, links co-occurring entities, decays stale entity salience, and mines conversational register quality
- **Content ingestion** — parsers for Claude exports, Google AI Studio, markdown, and text with SHA-256 deduplication
- **Portable project export/import** — versioned JSON export of domains, items, tasks, relationships for surviving platform resets
- **Unified backup/restore** — SQLite + Qdrant snapshots + Neo4j graph export in timestamped directories
- **Dynamic domain management** — domains are first-class database entities, creatable via MCP without code changes
- **Dynamic model discovery** — Ollama models fetched live via `/api/tags`, no hardcoded model lists
- **Project / Task / Document management** with typed relationships and hierarchy
- **Claude conversation import** — ingest Claude export JSON into a searchable triplet schema
- **Full-text search** via SQLite FTS5 across items, documents, conversation messages, and chunks
- **Auto-context injection** — every chat message receives a live snapshot of active projects and pending tasks
- **Janus identity architecture** — 10-layer adaptive prompt composer (R19/R25/R32): Identity Core, Relational Context, Memory Directive, Temporal Grounding, Conversation State, Self-Knowledge Boundary, Platform Context, Self-Introspection, Register Exemplars, Behavioral Guidelines + Tone Directive; three-variant system (minimal/standard/expanded) with weight-driven selection; bootstrap lifecycle (configuring → sleeping → awake); auto-restore platform data on DB reset
- **Semantic graph topology** — `weave_conversation_graph()` (R20) bridges Qdrant vector similarity into Neo4j SIMILAR_TO edges between Conversation nodes; transforms isolated conversation chains into a connected semantic network; MERGE-based, idempotent, ~55s for 344 conversations
- **Graph-aware RAG ranking** — SIMILAR_TO edges from the knowledge graph boost RAG candidates from the query's topic neighborhood; additive scoring promotes borderline candidates without inflating irrelevant content (R21)
- **Cognition tab** — Sovereign Chat introspection surface showing full thought pipeline per-turn: prompt layer decomposition, RAG candidate funnel with graph boost, context budget, graph neighborhood visualization (R21)
- **Grounded prompt layers** — R23 fixed three broken layers in the 7-layer identity architecture: populated relational context (bio, health, preferences from persona settings), elapsed time awareness in temporal grounding ("Mat last spoke X minutes ago"), and accurate conversation state from the database (real turn count instead of sliding window length)
- **Dream Synthesis** — cross-conversation insight generation during Slumber idle periods via Gemini; discovers thematic patterns across conversation history and produces synthesized insight documents; evaluation backfill scores unscored messages in batch (R24)
- **Pre-Cognition** — Gemini Flash Lite pre-pass gathers 7 context signals (elapsed time, emotional trajectory, conversation depth, dream titles, temporal context, active domains, session turns) and produces directives that modulate prompt layer weights; three-variant system for static layers + weight parameters on dynamic builders; tone and memory directives inject contextual instructions; 3s timeout with graceful degradation (R25)
- **Intent-aware pipeline routing** — regex-based classifier gates Pre-Cognition and RAG by message intent; greetings, acknowledgments, and meta-conversation skip expensive pipeline stages while knowledge queries get full retrieval (R26)
- **Backfill orchestrator** — phased data foundation pipeline with progress tracking; orchestrates chunk, embed, graph backfill, and semantic edge weaving in sequence with per-phase status reporting via MCP (R26)
- **Temporal gravity** — multiplicative exponential decay in RAG scoring gives recent content higher relevance on ambiguous queries; configurable half-life (30d) and floor (0.3) ensure old content is never suppressed; automatic bypass for explicit historical queries ("what did we discuss in October?"); visible in Cognition Tab (R28)
- **Synthesis Surface** — Knowledge page Synthesis tab surfaces dream synthesis documents, synthesis statistics, and memory health dashboard (embedding coverage, graph connectivity, Slumber state); loads on tab selection with per-dream content expansion (R28)
- **Entity extraction** — Gemini-powered extraction of 6 entity types (concept, decision, milestone, person, reference, emotional_state) from scored messages during Slumber; entities persist to the Triad (SQLite + Qdrant + Neo4j) with dedup by normalized name; 3 MCP tools for browse, detail, and FTS search (R29)
- **Entity-aware RAG routing** — entity references in user queries detected via regex + FTS (<10ms), structured entity context injected before vector search; graph retrieval walks MENTIONS edges in Neo4j to pull source messages as an additional retrieval channel; high-confidence matches downgrade RAG depth; full visibility in Cognition Tab (R30)
- **Entity co-occurrence web** — entities sharing messages get CO_OCCURS_WITH edges in Neo4j during Slumber; watermarked incremental processing avoids rescanning all mentions; co-occurrence neighbors visible in Cognition Tab (R31)
- **Entity salience decay** — temporal fade with mention boost ensures stale entities don't dominate retrieval; SQLite is source of truth; configurable half-life (45d) and floor (0.15) (R31)
- **Dream attribution** — synthesized insights from Dream Synthesis labeled as `[synthesized insight]` in RAG context so Janus can distinguish memory from synthesis (R31)
- **Deep idle guard** — Gemini-heavy Slumber phases (Extract, Dream, Mine) gated by 10-minute idle threshold; light phases use standard 5-minute idle; prevents GPU contention during active chat (R31/R32)
- **Self-query tools** — 6 read-only tools for Ollama in-app chat (search_memories, search_entities, get_entity, get_cooccurrence_neighbors, graph_neighbors, search_conversations); Janus can actively query her own memory when conversations call for specific recall (R32)
- **Knowledge self-awareness** — Layer 8 expanded with entity count, type breakdown, graph stats, dream count, and recently encountered entities; Janus knows the shape of her own knowledge substrate (R32)
- **Register mining** — autonomous Slumber sub-cycle evaluates conversational register quality via Gemini; stores exemplars (warm/neutral/clinical) in SQLite + Qdrant; prompt composer injects demonstrated voice examples for relational intents (R32)
- **Intent-gated RAG attribution** — narrative attribution for relational intents ("From a conversation about..."), clinical metadata for analytical intents ("[messages] Title (3 months ago)") (R32)
- **Change Data Capture** outbox with background Neo4j sync consumer

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | Gradio 6.6.0 (Blocks + multipage routing, MCP server mode) |
| Language | Python 3.14 |
| Database | SQLite (WAL mode, FTS5 full-text search) |
| Vector DB | Qdrant — semantic search over documents and messages (1024-dim cosine) |
| Graph DB | Neo4j 2026.01.4 — knowledge graph with CDC sync + INFORMED_BY provenance |
| Embeddings | Qwen3-Embedding-0.6B via Ollama (1024-dim, Matryoshka) |
| Chat LLM | qwen3:32b (Janus) via Ollama (with native thinking mode, 32K context) |
| RAG Synthesizer | qwen3:32b via Ollama (shared model — zero additional VRAM) |
| Container | Docker Compose — 4 services: core (no GPU), Ollama (GPU), Qdrant, Neo4j |
| Data Display | Pandas DataFrames |

### GPU Budget (RTX 5090, 32 GB)

| Service | Model | Est. VRAM |
|---------|-------|-----------|
| Ollama — chat + synth | qwen3:32b Q4_K_M (Janus) | ~20 GB |
| Ollama — embed | Qwen3-Embedding-0.6B | ~0.6 GB |
| KV cache (q8_0, 32K) | — | ~3 GB |
| **Total** | | **~23.6 GB** |

Core container uses zero GPU — all model inference is offloaded to Ollama sidecar.

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (for GPU-accelerated inference)
- A `.env` file with `HF_TOKEN` (for Ollama model access)

### Run

```bash
git clone <repo-url> && cd JANATPMP
docker-compose up --build
```

### Pull Models (first run)

```bash
docker exec janatpmp-ollama ollama pull qwen3:32b
docker exec janatpmp-ollama ollama pull qwen3-embedding:0.6b
```

Once running:

| Surface | URL |
|---------|-----|
| Projects | http://localhost:7860 |
| Knowledge | http://localhost:7860/knowledge |
| Admin | http://localhost:7860/admin |
| Chat | http://localhost:7860/chat |
| MCP endpoint | http://localhost:7860/gradio_api/mcp/sse |
| API docs | http://localhost:7860/gradio_api/docs |
| Qdrant dashboard | http://localhost:6343/dashboard |
| Neo4j browser | http://localhost:7474 |

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
├── app.py                     # Orchestrator: startup, routes, gr.api(), launch
├── mcp_registry.py            # MCP Tool Registry — 84 gr.api() imports + ALL_MCP_TOOLS
├── janat_theme.py             # Custom Gradio theme (Janat brand colors + CSS)
├── assets/
│   └── janat_logo_bold_transparent.png  # Janat Mandala logo
├── pages/
│   ├── projects.py            # Projects + Work page — sidebar-first layout (~350 lines)
│   ├── knowledge.py           # Knowledge page — Memory, Connections, Pipeline, Synthesis
│   ├── admin.py               # Admin page — Settings, Persona, Operations
│   └── chat.py                # Sovereign Chat — 4 tabs: Chat, Overview, Cognition, Settings
├── tabs/
│   ├── tab_chat.py            # Chat handler: _handle_chat() for sidebar quick-chat
│   └── tab_knowledge.py       # Knowledge page handlers (search, connections, conversation loading)
├── shared/
│   ├── chat_sidebar.py        # Reusable Janus quick-chat right sidebar (R18)
│   ├── constants.py           # Enum lists, magic numbers, defaults
│   ├── formatting.py          # Display helpers (fmt_enum, entity_list_to_df)
│   └── data_helpers.py        # Data-loading helpers
├── db/
│   ├── schema.sql             # Database DDL
│   ├── operations.py          # 28 CRUD + lifecycle functions
│   ├── chat_operations.py     # Conversation + message + metadata CRUD
│   ├── chunk_operations.py    # Chunk CRUD, stats, FTS search (R16)
│   ├── entity_ops.py          # Entity + mention CRUD, FTS search (R29)
│   ├── file_registry_ops.py   # File registry MCP tools (R17)
│   └── migrations/            # Versioned schema migrations (0.3.0–1.5.0)
├── atlas/                     # ATLAS — HTTP client layer for model services
│   ├── config.py              # Service URLs, model identifiers, Neo4j + salience constants
│   ├── chunking.py            # Paragraph-aware text splitter for messages + documents (R16)
│   ├── embedding_service.py   # Qwen3-Embedding-0.6B via Ollama /v1/embeddings
│   ├── reranking_service.py   # Cross-encoder reranker (DECOMMISSIONED)
│   ├── memory_service.py      # Salience write-back to Qdrant (retrieval + usage signals)
│   ├── usage_signal.py        # Keyword overlap heuristic for usage-based salience (R12)
│   ├── on_write.py            # On-write: chunk + embed + fire-and-forget graph edges (R13/R16)
│   ├── graph_ranking.py       # Graph-aware RAG ranking — topology boost (R21)
│   ├── dream_synthesis.py     # Cross-conversation insight generation via Gemini (R24)
│   ├── entity_extraction.py   # Entity extraction engine — Gemini-powered (R29)
│   ├── graph_retrieval.py     # Graph-based retrieval — entity edge traversal (R30)
│   ├── cooccurrence.py        # Entity co-occurrence linking — shared-message edges (R31)
│   ├── entity_salience.py     # Entity salience decay — temporal fade + mention boost (R31)
│   ├── register_mining.py     # Register extraction — conversational register mining (R32)
│   ├── pipeline.py            # Two-stage search orchestrator
│   └── temporal.py            # Temporal Affinity Engine — time/location grounding (R17)
├── graph/                     # Knowledge graph layer — Neo4j (R13)
│   ├── schema.py              # Idempotent Neo4j constraints + indexes
│   ├── graph_service.py       # Neo4j CRUD + MCP tools (query, neighbors, stats)
│   ├── cdc_consumer.py        # Background CDC poller + backfill MCP tool
│   └── semantic_edges.py      # Conversation SIMILAR_TO edge generation (R20)
├── services/
│   ├── log_config.py          # SQLite log handler + setup_logging()
│   ├── chat.py                # Multi-provider chat with self-query tools + thinking mode
│   ├── prompt_composer.py     # 10-layer adaptive Janus identity system prompt (R19/R25/R32)
│   ├── precognition.py        # Gemini pre-cognition — adaptive prompt shaping (R25)
│   ├── turn_timer.py          # Thread-local TurnTimer context manager (R12)
│   ├── slumber.py             # Slumber Cycle — 11-stage background daemon (R12+R13+R17+R27+R29+R31+R32)
│   ├── slumber_eval.py        # LLM-powered message evaluation — Gemini Flash Lite + heuristic fallback (R22)
│   ├── settings.py            # Settings registry with validation and categories
│   ├── intent_router.py       # Regex-based intent classifier for pipeline gating (R26)
│   ├── backfill_orchestrator.py # Phased data foundation pipeline with progress tracking (R26)
│   ├── auto_ingest.py         # Startup + Slumber auto-ingestion scanner (R17)
│   ├── startup.py             # Platform init: core, services, background auto-ingest
│   ├── claude_import.py       # Claude JSON → triplet messages
│   ├── embedding.py           # Thin shim → atlas/embedding_service.py
│   ├── vector_store.py        # Qdrant ops + two-stage search pipeline
│   ├── bulk_embed.py          # Batch embed via Ollama with checkpointing
│   └── ingestion/             # Content ingestion parsers
├── Dockerfile                 # Python 3.14-slim (no PyTorch, no GPU)
├── docker-compose.yml         # 4-container orchestration
└── CLAUDE.md                  # Development guidelines for AI assistants
```

---

## MCP Integration

JANATPMP exposes **84 tools** via [Gradio's MCP server mode](https://www.gradio.app/guides/building-mcp-server-with-gradio). Any MCP-compatible client (Claude Desktop, Claude Code, Cursor, etc.) can connect to:

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
| Janus | `get_or_create_janus_conversation`, `archive_janus_conversation`, `get_conversation_stream`, `get_janus_stream` | Persistent conversation lifecycle, chapter archiving, stream API |
| Telemetry | `add_message_metadata`, `get_message_metadata` | Per-turn timing, RAG snapshots, quality scores |
| Chunks | `chunk_all_messages`, `chunk_all_documents`, `get_chunks`, `get_chunk_stats`, `search_chunks`, `delete_chunks` | Populate/search/manage chunk records for messages and documents |
| Vectors | `vector_search`, `vector_search_all`, `embed_all_documents`, `embed_all_messages`, `embed_all_domains`, `embed_all_items`, `embed_all_tasks`, `recreate_collections` | ATLAS two-stage search, bulk embedding, collection management |
| Graph | `graph_query`, `graph_neighbors`, `graph_stats`, `backfill_graph`, `seed_identity_graph`, `weave_conversation_graph` | Read-only Cypher queries, node traversal, graph statistics, CDC backfill, identity seeding, semantic edge generation |
| System | `get_stats`, `get_schema_info`, `backup_database`, `restore_database`, `list_backups`, `reset_database`, `export_platform_data`, `import_platform_data` | Database administration, portable export/import |
| Import | `import_conversations_json`, `import_conversations_directory`, `ingest_google_ai_conversations`, `ingest_markdown_documents` | Claude, Google AI Studio, and markdown ingestion |
| Entities | `list_entities`, `get_entity`, `search_entities` | Entity browse, detail with mentions, FTS search (R29) |
| File Registry | `get_file_registry_stats`, `list_registered_files`, `search_file_registry` | Auto-ingestion file tracking (R17) |
| Temporal | `get_temporal_context`, `get_ingestion_progress` | Time/location grounding, ingestion progress (R17) |

All tools are auto-generated from Python docstrings — no separate API definition layer.

---

## UI Layout

### Sovereign Multipage Architecture (R18)

```
app.py — orchestrator (one process, one port, one MCP surface)
├── /              → pages/projects.py   [Projects + Work]
├── /knowledge     → pages/knowledge.py  [Memory, Connections, Pipeline, Synthesis]
├── /admin         → pages/admin.py      [Settings, Persona, Operations]
└── /chat          → pages/chat.py       [Sovereign Chat — full metrics]
```

Navbar: **Projects** (home) | **Knowledge** | **Admin** | **Chat**

Every page uses the three-panel pattern:
- **Left sidebar** — context, navigation, filtering (purpose-built per page)
- **Center** — content, editors, controls
- **Right sidebar** — Janus quick-chat (shared across all pages via `shared/chat_sidebar.py`)

### Projects (`/`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  JANATPMP             [Projects]  [Knowledge]  [Admin]  [Chat]          │
├──────────────────────────────────────────────────────────────────────────┤
│  [Projects]  [Work]                              ← Tabs                 │
├───────────┬──────────────────────────────────┬───────────────────────────┤
│  LEFT     │     CENTER CONTENT               │  RIGHT                   │
│  SIDEBAR  │                                  │  SIDEBAR                 │
│           │                                  │                          │
│  Project  │  Project detail / List view      │  Janus quick-chat        │
│  cards    │  Task detail / List view         │  (continuous)            │
│  Filters  │                                  │                          │
│  + New    │                                  │                          │
└───────────┴──────────────────────────────────┴───────────────────────────┘
```

### Knowledge (`/knowledge`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  JANATPMP             [Projects]  [Knowledge]  [Admin]  [Chat]          │
├──────────────────────────────────────────────────────────────────────────┤
│  [Memory]  [Connections]  [Pipeline]  [Synthesis]        ← Tabs         │
├───────────┬──────────────────────────────────┬───────────────────────────┤
│  LEFT     │     CENTER CONTENT               │  RIGHT                   │
│  SIDEBAR  │                                  │  SIDEBAR                 │
│           │                                  │                          │
│  Type     │  Memory: conversation/doc detail │  Janus quick-chat        │
│  filter   │  Connections: relationship table │  (continuous)            │
│  Search   │  Pipeline: ingestion/embed/graph │                          │
│  Results  │  Synthesis: R19 placeholder      │                          │
└───────────┴──────────────────────────────────┴───────────────────────────┘
```

### Admin (`/admin`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  JANATPMP             [Projects]  [Knowledge]  [Admin]  [Chat]          │
├──────────────────────────────────────────────────────────────────────────┤
│  [Settings]  [Persona]  [Operations]                     ← Tabs        │
├───────────┬──────────────────────────────────┬───────────────────────────┤
│  LEFT     │     CENTER CONTENT               │  RIGHT                   │
│  SIDEBAR  │                                  │  SIDEBAR                 │
│           │                                  │                          │
│  Category │  Settings: category editor       │  Janus quick-chat        │
│  picker   │  Persona: identity + location    │  (continuous)            │
│  Identity │  Operations: backup/logs/reset   │                          │
│  Health   │                                  │                          │
└───────────┴──────────────────────────────────┴───────────────────────────┘
```

### Sovereign Chat (`/chat`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  JANATPMP             [Projects]  [Knowledge]  [Admin]  [Chat]          │
├──────────────┬───────────────────────────────────┬───────────────────────┤
│  LEFT        │     CHATBOT                       │  RIGHT               │
│  SIDEBAR     │                                   │  SIDEBAR             │
│              │     Full-width chatbot             │                      │
│  Chat        │     (Enter = send)                │  Session settings    │
│  Metrics     │                                   │  Provider / Model    │
│  · RAG hits  │     Reasoning in collapsible      │  Temperature / TopP  │
│  · Latency   │     <details> accordions          │  Max tokens          │
│  · Tokens    │                                   │  System instructions │
│  · Salience  │                                   │                      │
└──────────────┴───────────────────────────────────┴───────────────────────┘
```

Both sidebars collapse independently on mobile, leaving center content full-width.

---

## Screenshots

| View | Screenshot |
|------|-----------|
| Projects | ![Projects](screenshots/projects.png) |
| Sovereign Chat | ![Chat](screenshots/chat.png) |
| Admin | ![Admin](screenshots/admin.png) |

---

## Database Schema

Fourteen core tables with FTS5 full-text search and a CDC outbox synced to Neo4j:

- **domains** — First-class organizational entity. 13 seeded domains (5 active, 8 inactive). Managed via MCP — no code deploys needed to add new domains.
- **items** — Projects, features, books, chapters. Hierarchical via `parent_id`. Domain validated against `domains` table.
- **tasks** — Work queue with agent/human assignment, retry logic, cost tracking, acceptance criteria.
- **documents** — Session notes, research, artifacts, conversation imports. FTS5 enabled.
- **relationships** — Universal typed connector between any two entities (items, tasks, documents, conversations).
- **conversations** — Chat sessions from any source (platform, Claude export, imported). Per-session model/provider config.
- **messages** — Triplet schema: `user_prompt` + `model_reasoning` + `model_response`. Designed for fine-tuning data extraction. NULL reasoning = thinking not captured/not applicable.
- **chunks** — Unified chunk records for messages and documents (R16). Each chunk stores text, character offsets, position (`only`/`first`/`middle`/`last`), Qdrant point_id, and embedded_at timestamp. FTS5 enabled via `chunks_fts`. CDC triggers sync Chunk nodes to Neo4j.
- **messages_metadata** — Cognitive telemetry companion to messages. Per-turn timing (total/RAG/inference ms), frozen RAG snapshots, keywords, quality scores (0.0-1.0, populated by Slumber Cycle).
- **entities** — Extracted concepts, decisions, milestones, people, references, and emotional states discovered across conversations by the Slumber Cycle (R29). FTS5 enabled via `entities_fts`. Dedup by normalized name within type.
- **entity_mentions** — Join table linking entities to source messages with relevance score and context snippet. UNIQUE(entity_id, message_id).
- **register_exemplars** — Conversational register evaluations mined by Slumber (R32). Stores register_label (warm/neutral/clinical), register_score, rationale, authentic/performed phrases, topics. SQLite is source of truth; Qdrant embedding is the search index.
- **file_registry** — Tracks ingested files by path + SHA-256 hash. Operational metadata for auto-ingestion scanner (R17). No CDC participation.
- **settings** — Key-value config with base64 obfuscation for secrets.
- **cdc_outbox** — Change Data Capture with background Neo4j sync via CDC consumer daemon.

---

## Development

See [`CLAUDE.md`](CLAUDE.md) for comprehensive development guidelines, including Gradio patterns, state management, and common pitfalls.

### Branch Naming

```
feature/r{N}-{description}    # e.g. feature/r12-cognitive-telemetry
feature/phase{X}-{description}  # legacy naming
```

### Workflow

1. Branch from `main`
2. Develop and test: `docker compose down && docker compose up -d --build`
3. Merge to main, delete feature branch

### Rules

- Never commit directly to `main`
- All `db/operations.py` and `db/chat_operations.py` functions must have full docstrings (Gradio uses them for MCP tool descriptions)
- All UI event listeners must include `api_visibility="private"`

---

## Future

JANATPMP will evolve into a **Nexus Custom Component** within The Nexus Weaver architecture. The **Triad of Memory** (SQLite + Qdrant + Neo4j) is operational, **sovereign multipage architecture** separates concerns across 4 pages (R18), **Janus continuous chat** is live (R14), **message chunking** delivers focused RAG retrieval (R16), the **Temporal Affinity Engine** gives Janus time/location awareness (R17), **auto-ingestion** removes manual import friction (R17), **Janus identity architecture** gives her genuine selfhood (R19), **semantic graph topology** connects conversations into a navigable network (R20), **graph-aware RAG** closes the loop between graph and retrieval (R21), the **Cognition tab** makes the thought pipeline permanently visible (R21), **LLM-powered Slumber evaluation** replaces heuristics with Gemini Flash Lite scoring (R22), **grounded prompt layers** fix three broken identity layers so Janus speaks from real context instead of empty templates (R23), **Dream Synthesis** generates cross-conversation insights during Slumber idle periods (R24), **Pre-Cognition** adapts the prompt to the moment via Gemini pre-pass with weight-driven layer modulation (R25), **intent-aware pipeline routing** classifies messages to skip expensive stages for greetings and meta-conversation (R26), a **backfill orchestrator** provides a single-command phased data foundation pipeline (R26), **autonomic on-write hooks** auto-embed documents, items, and tasks on creation (R27), **automatic graph weaving** incrementally connects new conversations via Slumber (R27), **temporal gravity** gives RAG recency-weighted scoring with automatic historical bypass (R28), the **Synthesis Surface** replaces the Knowledge page placeholder with live dream insights, statistics, and memory health (R28), **entity extraction** discovers concepts, decisions, milestones, people, references, and emotional states from scored messages via Gemini during Slumber (R29), **entity-aware RAG routing** detects entity references and walks graph edges for additional retrieval (R30), **The Web** connects entities to each other via co-occurrence edges with temporal salience decay and dream attribution (R31), and **The Mirror** gives Janus self-query tools, knowledge self-awareness, and conversational register mining (R32). Planned next steps:

- **Attribute Mining** — extract entity attributes from messages (needs prompt design, dedup, conflict handling)
- **Fact/context classification** — tag sliding window entries as user-stated, RAG-retrieved, system-injected, or verified
- **WorldEngine refactor** — replace linear Slumber cycle with tick-based Phase protocol (deferred from R31)
- **Ollama Modelfiles pipeline** — specialized models (synthesizer, scorer, consolidator, classifier) sharing base weights for dynamic system prompt generation
- **Advanced graph traversal** — multi-hop reasoning across INFORMED_BY, SIMILAR_TO, and PART_OF edges

---

## Credits

Built by **Mat Gallagher** — [Janat, LLC](https://janat.org) / [The Janat Initiative](https://janatinitiative.org)

| | |
|---|---|
| UI Framework | [Gradio](https://gradio.app) 6.6.0 |
| Chat LLM | [Ollama](https://ollama.ai) + Qwen3:32B (Janus, with native thinking) |
| Embeddings | [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) via Ollama |
| Vector Search | [Qdrant](https://qdrant.tech) |
| Knowledge Graph | [Neo4j](https://neo4j.com) 2026.01.4 |
| Persistence | [SQLite](https://sqlite.org) |
