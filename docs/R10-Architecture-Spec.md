# JANATPMP R10 Architecture Specification
**Date:** February 20, 2026  
**Authors:** Mat Gallagher + Claude (The Weavers)  
**Status:** Planning — Ready for Claude Code Implementation

---

## 1. Overview

R10 represents a fundamental architectural refactor of JANATPMP from a single Gradio Blocks application to a multi-app gr.routes() architecture. Each top-level section becomes an independent Gradio application mounted through a central main.py router.

The driving principle: **design to the standard, not the infrastructure.** Schemas, Cypher queries, and vector collections are the architecture. PostgreSQL vs SQLite, Neo4j vs FalkorDB — those are deployment decisions.

---

## 2. Core Architectural Shift

### From
Single app.py with gr.Blocks(), shared sidebar state, navigation via tabs, sidebar re-renders on every view change.

### To
```
main.py (gr.routes() mount point + session persona)
├── app_projects.py   → JANATPMP project management
├── app_atlas.py      → Knowledge / ATLAS corpus layer
├── app_chat.py       → Continuous chat interface
└── app_admin.py      → Configuration and service backend
```

### Loading Pattern (main.py)
All apps load at startup. All APIs and MCP tools are live immediately. Users only see the route they navigate to.

```python
# main.py
import gradio as gr
from apps.chat import demo as chat_app
from apps.knowledge import demo as knowledge_app
from apps.projects import demo as projects_app
from apps.admin import demo as admin_app

app = gr.mount_gradio_app(gr.routes(), chat_app, path="/chat")
app = gr.mount_gradio_app(app, knowledge_app, path="/knowledge")
app = gr.mount_gradio_app(app, projects_app, path="/projects")
app = gr.mount_gradio_app(app, admin_app, path="/admin")
```

### Why gr.routes() Now
- Each section has genuinely independent concerns
- Sidebars SHOULD be different per app — they serve different purposes
- State lives in the Triad of Memory, not in Gradio
- Losing sidebar state on navigation is irrelevant when data persists in the Triad
- Each app.py can be developed, tested, and reasoned about independently

---

## 3. Inter-App Communication

### Principle
Apps are **isolated by purpose, connected by import**. They are not isolated in the sense of being self-contained silos — they are isolated in the sense that each has a single clear responsibility, but they freely share functionality with each other.

### Pattern
Since all apps run in the same Python process, internal communication is direct import — no HTTP, no network hop, no serialization overhead.

```python
# apps/chat.py
from apps.knowledge import search_corpus, get_context

# Chat uses Knowledge's functions natively
context = get_context(user_message)
```

### Who Owns What
```
app_atlas.py (knowledge)  — the brain
  exposes: search_corpus(), get_context(), retrieve_triad()
  
app_chat.py               — consumes knowledge directly
app_projects.py           — consumes knowledge directly
app_admin.py              — configures all apps
```

### API / MCP Surface
The exposed API and MCP tools are for **external consumers** — agents, Claude Desktop, other tools outside the process. Internal apps use Python imports, not the API.

### Isolation vs. Persistence
- **Isolated** — each app has one purpose, independent sidebar, independent development lifecycle
- **Persistent** — each app's API stays live as long as the process runs, available to internal and external consumers equally

---

## 4. Session Persona (main.py)

main.py is not a UI shell. It is a **session context provider**.

### Characteristics
- Single user, embedded deployment
- Persistent cookies, no expiration
- Session persona always exists and is always current
- No authentication layer needed at this stage

### Persona State
```python
{
  "user": "Mat",
  "location": "Fargo, ND",
  "session_start": timestamp,
  "last_active": timestamp,
  "preferences": {
    "default_temperature": 0.7,
    "default_top_p": 0.9,
    "recency_bias": 0.6,
    "graph_traversal": True
  }
}
```

Persona is readable by all apps, writable by Admin. Each app reads what it needs, writes back what changes.

---

## 5. The Triad of Memory (ATLAS)

Three stores, one schema identity. Cross-referenced via shared IDs.

### Design Principle
- **SQL** — what (facts, timestamps, provenance, structured records)
- **Vector** — like (similarity, semantic neighbors, intuition)
- **Graph** — why (relationships, causality, meaning, traversal)

Graph is the most fundamental. SQL and Vector are indexes on content. Graph is an index on meaning.

### Infrastructure (current)
- SQL: SQLite (embedded in core container)
- Vector: Qdrant (janatpmp-qdrant container)
- Graph: Not yet implemented

### Infrastructure (target — flexible)
Schemas and query patterns are written to standards:
- SQL: ANSI SQL (portable to PostgreSQL)
- Vector: Qdrant collection schema (portable to pgvector)
- Graph: Cypher (portable to Neo4j, FalkorDB, AGE)

Implementation decision deferred until Troubadourian Amphitheatre design is reviewed and graph schema is defined.

---

## 6. App Specifications

### 6.1 app_projects.py — JANATPMP
**Purpose:** Project and task management  
**MCP Surface:** create_item, update_item, list_items, create_task, etc.  
**Sidebar:** Project tree, domain filter, status summary  
**State:** Reads/writes SQL Triad layer  
**Note:** No UI changes in R10 — extraction only

---

### 6.2 app_atlas.py — Knowledge / ATLAS

**Purpose:** Corpus management layer. Ingestion, audit, search, and Triad visualization. This is where data enters ATLAS.

#### Tab Structure (refactored from 5 tabs to 3)

**Corpus** (merge of Documents + List View)
- Grid/list toggle
- Source filter (Claude Export, Generated, Uploaded, Agent Output)
- Type filter (conversation, document, artifact, research)
- Bulk operations: embed, delete, export
- Left sidebar: Corpus Stats Panel (persistent)

**Conversations**
- The claude-export-viewer, purpose-clarified
- Job: ingestion + audit only — NOT conversation resumption
- Columns: Title, Source, Messages, Est. Tokens, Status, Updated
- Status flags: ✓ Has content / ⚠ Empty shell / ✗ Broken
- Bug fix: counter showing 0 conversations / 0 messages despite data
- Remove raw ID column, replace with short readable hash
- Right panel: Conversation Viewer for content inspection
- Left sidebar: Corpus Stats Panel (persistent)

**Connections** (Triad Visualization — stub in R10, evolves post-graph)
- Select any entity → see SQL record + vector neighbors + graph paths
- Read-only in R10
- Full implementation after Neo4j/graph store integration
- Left sidebar: Corpus Stats Panel (persistent)

**Search** — REMOVED AS TAB
- Becomes persistent search bar in the left sidebar
- Searches across both Corpus and Conversations simultaneously
- Results filter the active tab's content in place

#### ATLAS Left Sidebar — Corpus Stats Panel
Persistent across all Knowledge tabs. Replaces the current Documents list when in Conversations view.

```
CORPUS OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━
Conversations    603
Messages      12,847
Est. Tokens     ~6.2M

BY SOURCE
Claude Export    598
Platform           3
Gemini Import      4

HEALTH
✓ With content   591
⚠ Empty shells    12
✗ Broken           0

VECTOR COVERAGE
Embedded         487  (81%)
Pending          116  (19%)

[Search corpus................]
```

Note: All counts above are placeholders. Accurate counts require corpus audit (see R10 TODO).

---

### 6.3 app_chat.py — Continuous Chat

**Core Concept:** There is no chat history to resume. The Triad holds all context. Every message is constructed to contain everything Janus needs. Opening a specific old chat to "continue" it would be pointless and confusing — Janus already knows everything through the Triad.

The chat list sidebar is solving a problem we don't have. It is removed.

#### Three Panel Layout

**Left Panel — Instrument Panel (user only, never injected into context)**

```
RETRIEVAL THIS TURN
  Vectors      7 hits  (0.84 avg)
  Memories     3 hits  (0.91 avg)
  Docs         1 hit   (0.79 avg)
  Graph        2 paths

TEMPORAL AFFINITY
  Last 7 days    ████████  60%
  Last 30 days   ████      28%
  Older          ██        12%

ACTIVE PERSONA
  Mat · Fargo ND
  Session: 4h 12m

SHAPING PARAMETERS
  Recency bias    [●●●○○]
  Depth           [●●●●○]
  Graph traversal [on/off]
```

- Read only display for user
- Completely invisible to Janus — never included in context
- Updates after every turn
- Shows exactly what shaped the last response
- Temporal affinity tracked and displayed
- Recency bias and depth are tunable (writes to persona for next turn)

**Center Panel — The Exchange**
- Current conversation only — clean, minimal
- Janus sees only this plus injected Triad context
- No infinite scroll of historical sessions
- Input bar at bottom

**Right Panel — Session Settings (per-turn)**
- Temperature slider
- Top-p slider
- Max tokens
- Model selector
- Takes effect on NEXT message, not current turn
- Changes persist to session persona

---

### 6.4 app_admin.py — Configuration and Services

**Purpose:** Service backend and configuration layer  
**Controls:** Other app.py instances, shared parameters, service health  
**MCP Surface:** Service management tools  
**Note:** No UI spec changes in R10

---

## 7. What R10 Does NOT Include

- Neo4j or graph store integration (schema design pending Troubadourian Amphitheatre review)
- Graph schema definition (same dependency)
- Accurate token counts (requires corpus audit first)
- Authentication or multi-user support
- Chat history resumption (by design, permanently removed)
- Embedding pipeline changes

---

## 8. Implementation Order

1. Corpus audit — accurate counts before any schema changes
2. Triage broken conversations (data present, viewer fails)
3. Review Troubadourian Amphitheatre report (Cowork)
4. Extract app_projects.py from current app.py
5. Build app_atlas.py with refactored Knowledge tabs
6. Build app_chat.py with three-panel layout
7. Wire app_admin.py
8. Create main.py with gr.routes()
9. Test persona persistence across app navigation
10. Graph schema design session (post-Troubadourian review)
11. Graph store selection and container integration
12. graph_service.py in ATLAS module
13. Connections tab full Triad visualization

---

## 9. Open Questions

- Troubadourian Amphitheatre graph schema (Cowork review in progress)
- Graph infrastructure choice (Neo4j vs FalkorDB vs AGE — deferred)
- Corpus audit results (broken conversation count, actual token totals)
- Accurate corpus statistics for resume and public documentation

---

## 10. Key Decisions Made This Session

- **gr.routes() confirmed** over shared Blocks — independence over coordination
- **Inter-app communication via direct import** — same process, no HTTP overhead, API surface reserved for external consumers
- **app_atlas.py is the brain** — search_corpus(), get_context(), retrieve_triad() consumed by chat and projects directly
- **Chat list removed permanently** — Triad replaces the need for it
- **Instrument panel replaces sidebar** — retrieval transparency for user, invisible to Janus
- **Session settings are per-turn** — right panel writes to persona, takes effect next message
- **Graph is most fundamental Triad layer** — not an add-on, core to meaning
- **Design to standards not infrastructure** — Cypher, ANSI SQL, collection schemas are portable
- **Corpus Stats Panel** replaces irrelevant Documents list in ATLAS sidebar

---

*This document was produced in a planning session between Mat Gallagher and Claude (The Weavers). Claude Code will execute implementation from this spec. Claude does not edit working code — only Claude Code does.*
