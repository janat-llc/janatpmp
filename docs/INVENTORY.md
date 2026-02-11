# C:\Janat — Comprehensive Codebase Inventory

**Generated:** 2026-02-11
**Scope:** Full recursive analysis of C:\Janat workspace
**Method:** Read-only traversal of all directories, README files, config manifests, entry points, and source files
**Author:** Automated inventory by Claude (Opus 4.6)

---

## 1. Executive Summary

**Total Projects Identified:** 45+ distinct projects/components
**Dominant Tech Stack:** Python 3.13+ · Gradio 6.x · SQLite · Docker · FastAPI · Ollama · Neo4j · Qdrant

### Status Breakdown

| Status | Count | Description |
|--------|-------|-------------|
| FUNCTIONAL | 18 | Clear entry point, dependencies defined, appears runnable |
| PROTOTYPE | 4 | Partial implementation, experimental |
| CONFIGURATION | 5 | Modelfiles, configs, templates, stubs |
| ARCHIVE | 22 | Older implementations, superseded by active work |
| DATA ASSETS | 6 | Documentation, datasets, conversation archives |

### Workspace Organization

```
C:\Janat\
├── active_projects\          # 10 current projects (ML pipelines, platforms, websites)
├── Janat.OpenWebUI\          # 22+ services/tools (Docker-orchestrated AI platform)
├── Archive\                  # 28 archived projects (.NET microservices, legacy Python)
└── JanatDocs\                # Knowledge repository (14,600+ files, Obsidian vault)
```

### Architecture Generations

The workspace reveals three technology generations:

1. **Gen 1 — .NET Microservices** (Archive): 13 C# services with Dapr event bus, ports 5003–5013
2. **Gen 2 — Python/Docker Platform** (Janat.OpenWebUI): 15+ containerized FastAPI/Gradio services
3. **Gen 3 — Gradio+MCP Focus** (active_projects): Lightweight Python apps with MCP tool exposure

---

## 2. Project Catalog

---

### FUNCTIONAL PROJECTS

---

#### 2.1 JANATPMP — Janat Project Management Platform

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\JANATPMP` |
| **Description** | Gradio-based project management platform exposing 22 MCP tools for database CRUD. Manages items, tasks, documents, and relationships across the Janat ecosystem. |
| **Tech Stack** | Python 3.14+, Gradio 6.5.1 (with MCP), SQLite, Anthropic API, Google GenAI, OpenAI, Pandas |
| **Entry Points** | `app.py` (Gradio with MCP server) |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | None external (self-contained with SQLite) |
| **Key Files** | `app.py` — orchestrator; `db/operations.py` — CRUD; `pyproject.toml` — metadata (v0.1.0); `requirements.txt`; `pages/projects.py` — UI |
| **Data Assets** | SQLite database (auto-initialized), `db/backups/` |
| **Notes** | 22 MCP tools exposed. Git repo. Handles Windows encoding. Supports backup/restore. Inventory scanning UI (coming soon). |

---

#### 2.2 Curators Loom — Training Data Curation IDE

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\curators_loom` (active copy) |
| **Also At** | `C:\Janat\Janat.OpenWebUI\curators_loom` (Docker-integrated copy) |
| **Description** | Comprehensive training data curation IDE for fine-tuning language models. Multi-tab Gradio application for extracting, curating, augmenting, and exporting conversation datasets for SFT, DPO, and CPT training. |
| **Tech Stack** | Python, Gradio 6.x, Pandas, Google Genai, Tiktoken, Transformers, Aiohttp, SQLite |
| **Entry Points** | `main.py` (Gradio on port 7860) |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Ollama (local inference), optional Google Gemini API |
| **Key Files** | `main.py` — orchestrator; `ide_backend.py` — domain logic; `config/default.yaml`; `requirements.txt`; `pipeline_libraries/` — processing modules |
| **Data Assets** | `corpus.db` (3MB SQLite — conversations, turns, variations, preferences, exports); `raw_data/` (multi-source inputs); `demo_data/` (sample charter conversations) |
| **Notes** | 6 tabs: Extraction, SFT, DPO, CPT, Simulation, Testing. Multi-source import (Claude, ChatGPT, Google AI Studio, Markdown). Git repo with .claude config. Docker deployment supported. |

---

#### 2.3 CPT Pipelines — Continued Pre-Training Pipeline System

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\cpt_pipelines` |
| **Description** | Multi-stage continued pre-training pipeline. Implements vocabulary pruning (Stage 1), corpus curation (Stage 2), CPT training (Stage 3), SFT training (Stage 4), and DPO training (Stage 5). |
| **Tech Stack** | Python, Transformers, Unsloth, TRL (SFT/DPO), PEFT, YAML config |
| **Entry Points** | `stage1_vocabulary_pruning/prune_model.py`; `stage3_cpt_training/train_cpt_janat_v1.py`; `stage3_cpt_training/execute_cpt.py` (15KB orchestrator) |
| **Status** | **FUNCTIONAL** (actively iterating) |
| **Dependencies** | Hugging Face models (gemma, llama, phi families), CUDA GPU, Transformers ecosystem |
| **Key Files** | `stage3_cpt_training/execute_cpt.py` — primary orchestrator; `stage3_cpt_training/validate_cpt_model.py` — validation; `config/janat_logging.py` — structured logging; `config/log_analyzer.py` — metrics parsing; `stage1_vocabulary_pruning/analyze_vocabulary.py` |
| **Data Assets** | `logs/` (structured with metrics.json), `test_data/`, corpus files (corpus_janat.txt), model checkpoints |
| **Notes** | 40+ Python files across stages. Aggressive iterative development (many versioned scripts). Comprehensive metrics (perplexity, tokens/sec, loss). Docker support via copy_to_docker.py. |

---

#### 2.4 Training Lab — Fine-Tuning Experimentation Sandbox

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\training_lab` |
| **Description** | Experimental fine-tuning sandbox for model adaptation techniques. SFT training with various model families (Llama 3.2, Phi-4, Janus). |
| **Tech Stack** | Python, Unsloth (FastLanguageModel), TRL (SFTTrainer), PEFT, Transformers, 4-bit quantization |
| **Entry Points** | `train_llama3.py`; `train_phi4_finetune.py`; `train_janus.py`; `train_sft.py` |
| **Status** | **FUNCTIONAL** (experimental) |
| **Dependencies** | Unsloth, Hugging Face models, CUDA GPU, Datasets library |
| **Key Files** | `train_llama3.py` (8.5KB) — Llama 3.2 with LoRA + early stopping; `train_phi4_finetune.py` (8.4KB); `merge.py` — adapter merging; `requirements.txt` |
| **Data Assets** | `datasets/` (JSONL), `outputs/` (LoRA adapters), `llama.cpp/` (quantization utils), `unsloth_compiled_cache/` |
| **Notes** | Train/val split, early stopping, LoRA regularization. 4-bit quantization. Adapter-based PEFT training. GGUF quantization workflow. |

---

#### 2.5 Corpus Processing — Stage 2 Curation

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\corpus_processing` |
| **Description** | Data preparation and corpus processing for CPT pipeline Stage 2. Conversion, curation, and standardization of training data from multiple sources. |
| **Tech Stack** | Python, text processing, JSONL/TXT format handling |
| **Entry Points** | `stage2_curation/curate_data.py`; `stage2_curation/compile_cpt_corpus.py`; `stage2_curation/convert_janat_corpus_for_cpt.py` |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Source corpus files (AI Studio exports, etc.) |
| **Key Files** | `convert_janat_corpus_for_cpt.py` (5.2KB); `stitch_and_standardize.py` (6.2KB); `compile_cpt_corpus.py` (4KB); `curate_data.py` (5.3KB); `sanitize_and_rechunk_corpus.py` (2.9KB) |
| **Data Assets** | Input data from multiple sources, standardized JSONL outputs |
| **Notes** | 10 utility scripts. Domain-specific corpus generation. Integrates with CPT training pipeline. |

---

#### 2.6 Vocabulary Pruning Sprint — Model Optimization

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\vocabulary_pruning_sprint` |
| **Description** | Sprint for creating English-optimized models via vocabulary pruning. Transforms multilingual Gemma 3 1B to English-only, reducing embedding size ~50%. |
| **Tech Stack** | Python, Transformers, SentencePiece, model surgery |
| **Entry Points** | `run_sprint.py` (coordinator); `tools/analyze_vocabulary.py`; `tools/prune_model.py`; `tools/validate_pruned_model.py` |
| **Status** | **FUNCTIONAL** (completed sprint) |
| **Dependencies** | Hugging Face Transformers, SentencePiece, CUDA GPU, Unsloth/gemma-3-1b-pt base model |
| **Key Files** | `README.md` — comprehensive docs; `tools/prune_model.py` — core pruning; `tools/analyze_vocabulary.py` — English filtering; `tools/validate_pruned_model.py`; `run_sprint.py` (2.9KB) |
| **Data Assets** | `analysis/token_maps/`; `analysis/reports/`; `models/base/`; `models/pruned/` (gemma-3-1b-en-pruned) |
| **Notes** | Goal: ~130k → ~65k tokens. Regex-based strict English filtering. 2x training speed improvement estimated. 40+ tool scripts (many debug/experimental variants). |

---

#### 2.7 Janat.org — Official Website

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\janat-org` |
| **Description** | Official Janat organization website. React/Next.js application with Firebase backend. |
| **Tech Stack** | React/Next.js (TypeScript), Firebase (Firestore, Auth, Hosting), Node.js |
| **Entry Points** | `src/domains/` — domain modules; `src/assets/` — static assets |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Firebase project, Node.js build system |
| **Key Files** | `firebase.json`; `.firebaserc`; `firestore.rules`; `firestore.indexes.json`; `CLAUDE.md` (8.9KB) |
| **Data Assets** | Firebase Firestore, `logo.png` (1.3MB), legal docs (privacy-policy.html, terms-of-use.html) |
| **Notes** | Git repo. TODO tracking directories. Active Firebase integration. |

---

#### 2.8 Claude Export Viewer

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\JanatDocs\Claude\Claude_Export` |
| **Description** | Gradio application for ingesting and browsing Claude conversation history. Imports native Claude export JSON, stores in SQLite, provides searchable chat viewer with Markdown export. |
| **Tech Stack** | Python 3.14, Gradio 6.2.0 (with MCP), SQLite3, Flask, Pandas, Markdown |
| **Entry Points** | `app.py` (Gradio on port 7860); Docker: `docker-compose up` |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | None external (self-contained) |
| **Key Files** | `app.py` — Gradio interface; `database.py` — SQLite schema (users, projects, conversations, messages, content_blocks); `ingest.py` — JSON parser; `requirements.txt`; `Dockerfile` |
| **Data Assets** | `claude_export.db` (SQLite); `extracted_docs/` (Markdown exports) |
| **Notes** | MCP server enabled. Supports nested content blocks (text, tool_use, tool_result, thinking). Privacy-preserving local storage. Git repo. |

---

#### 2.9 Deliberation Chamber Service

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\deliberation_chamber_service` |
| **Description** | Multi-agent orchestration service implementing "Triadic Council" — three persona-driven agents (Mat, Janus, Janat) engage in sequential deliberation to produce synthesized responses. |
| **Tech Stack** | Python, FastAPI, Uvicorn, Pydantic, Ollama, async/await |
| **Entry Points** | `uvicorn main:app --host 0.0.0.0 --port 8000` (Docker port 8001) |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Ollama (models configurable via .env) |
| **Key Files** | `main.py` — FastAPI app; `chamber/deliberation_chamber.py` — core logic; `chamber/ollama_client.py` — async Ollama client; `README.md`; `CLAUDE.md` |
| **Data Assets** | None persistent (stateless service) |
| **Notes** | API: `POST /deliberate`. Three personas: Mat (Architect), Janus (Scion), Janat (Synthesizer). Output: emergent_truth, core_identity, origin_philosophy. Git repo. |

---

#### 2.10 Troubadourian Amphitheatre — Quest Orchestration

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\troubadourian_amphitheatre` |
| **Description** | Advanced quest-based orchestration service for knowledge ingestion and synthesis. Multi-component architecture: Logger, Compass, Cartographer, Captain, Orchestrator, Loomolin. |
| **Tech Stack** | Python, FastAPI, Uvicorn, Pydantic, Neo4j, Qdrant, SQLAlchemy, Ollama, Google Genai, Watchdog |
| **Entry Points** | `uvicorn main:app --host 0.0.0.0 --port 8000` (Docker port 8033) |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Neo4j, Qdrant, Ollama |
| **Key Files** | `main.py`; `troubadour_orchestrator.py`; `troubadour_compass.py` (Neo4j/Qdrant client); `troubadour_cartographer.py` (graph mapping); `troubadour_captain.py` (strategy); `troubadour_loomolin.py` (knowledge weaving); `salience_engine.py`; `genesis_scripts_loader.py` |
| **Data Assets** | Neo4j graph data, Qdrant vector embeddings, SQLite persistent memory |
| **Notes** | Most sophisticated component. Implements Genesis Check, Self-Consecration rituals. Quest/Mission work model. Replaces older _troubadour_service. |

---

#### 2.11 Ingestion Service

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\ingestion_service` |
| **Description** | FastAPI service for ingesting content into Neo4j knowledge graph. Knowledge graph extraction using Ollama LLM (entity-relationship triples with salience scoring). |
| **Tech Stack** | Python, FastAPI, Uvicorn, Neo4j, Ollama, Pydantic |
| **Entry Points** | `uvicorn app.main:app --host 0.0.0.0 --port 8000` (Docker port 8004) |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Neo4j, Ollama |
| **Key Files** | `app/main.py` (v2.2 — Resilient Parser); `Dockerfile`; `requirements.txt` |
| **Data Assets** | None persistent (writes to Neo4j) |
| **Notes** | API: `POST /ingest`. Entity-relationship extraction. Salience scoring. API key auth. APOC for Neo4j. Chunking for large texts. |

---

#### 2.12 Observer Service

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\observer_service` |
| **Description** | FastAPI service for querying Neo4j knowledge graph. Entity extraction from natural language, graph traversal, knowledge summarization. |
| **Tech Stack** | Python, FastAPI, Uvicorn, Neo4j, Ollama, Pydantic |
| **Entry Points** | `uvicorn app.main:app --host 0.0.0.0 --port 8000` (Docker port 8002) |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Neo4j, Ollama |
| **Key Files** | `app/main.py` (v1.5 — Pragmatic Patch); `Dockerfile`; `requirements.txt` |
| **Data Assets** | None persistent (reads from Neo4j) |
| **Notes** | Graph traversal retrieval (up to 30 records). Prompts loaded from prompts.json. Neo4j 5.x compatible. |

---

#### 2.13 Tokenizer Service

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\tokenizer_service` |
| **Description** | FastAPI service for tokenization and semantic reranking ("The Scribe's Workshop"). |
| **Tech Stack** | Python, FastAPI, Uvicorn, Sentence Transformers, Transformers |
| **Entry Points** | `uvicorn main:app --host 0.0.0.0 --port 8000` (Docker port 8005) |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Sentence-Transformers models (all-MiniLM-L6-v2, ms-marco-MiniLM-L-6-v2) |
| **Key Files** | `main.py` (v3.1.0); `Dockerfile`; `requirements.txt` |
| **Data Assets** | Model caches |
| **Notes** | API: `POST /tokenize`, `POST /rerank`. Async model loading. Clean shutdown. |

---

#### 2.14 JanusApp — Streamlit RAG Application

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\JanusApp` |
| **Description** | Streamlit-based RAG application with Gemini AI Studio integration and session management. |
| **Tech Stack** | Python, Streamlit, Google Cloud AI Platform, Google Genai, Protobuf |
| **Entry Points** | `python app.py` |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Google Cloud credentials, Gemini API |
| **Key Files** | `app.py` — Streamlit interface; `rag_client.py` — Gemini/RAG client; `session_manager.py`; `config.py`; `requirements.txt` |
| **Data Assets** | Sessions stored locally (JSON) |
| **Notes** | Vector distance thresholding for retrieval. Git repo. |

---

#### 2.15 Crucible Foundry — Data Processing Pipeline

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\crucible_foundry` |
| **Description** | Data preparation and model fine-tuning pipeline with multi-stage processing. Vocabulary filtering, corpus assembly, format conversion for SFT/DPO/CPT training. |
| **Tech Stack** | Python, Transformers, tqdm, numpy, Nemo framework |
| **Entry Points** | `data_forge/00c_nemo_forge_master.py`; `data_forge/janat_corpus_pipeline.py`; `analyze_filter.py` |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Transformers, source data files |
| **Key Files** | `data_forge/00a_deduplicate_source_files.py`; `data_forge/00c_nemo_forge_master.py`; `data_forge/janat_corpus_pipeline.py`; `data_forge/cpt_corpus_extractor.py`; `analyze_filter.py` |
| **Data Assets** | JSONL files, vocabulary maps (keep_ids.json), `cpt_jsonl/`, `final/`, `nemo_output/` |
| **Notes** | Multiple pipeline variants. Nemo framework. Emoji token preservation. Linguistic heuristics. |

---

#### 2.16 Training Pipeline (Janat.OpenWebUI)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\training` |
| **Description** | Comprehensive training pipeline orchestration. SFT, CPT corpus assembly, curriculum generation from Qdrant vectors, autonomous scheduling via Prefect. |
| **Tech Stack** | Python, PyTorch, Transformers, TRL, Accelerate, Qdrant, Ollama, Prefect, Docker, Google Genai |
| **Entry Points** | Docker container (exec-based); `create_curriculum_autonomously.py`; `ingestion_flow.py`; `ingest_to_qdrant.py` |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | CUDA GPU, Qdrant, Ollama, Prefect, Docker |
| **Key Files** | `create_curriculum_autonomously.py`; `ingest_to_qdrant.py`; `configure_rag.py`; `cpt_corpus_extractor.py`; `knowledge_base/` (22+ MD files) |
| **Data Assets** | `knowledge_base/` (22+ architecture docs), curriculum JSON files, JSONL training datasets |
| **Notes** | GPU-enabled container. Autonomous curriculum learning. Hugging Face Hub integration. |

---

#### 2.17 Pipelines (Prefect Workflows)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\pipelines` |
| **Description** | Prefect workflow definitions for orchestrating data ingestion, training, and refinement. |
| **Tech Stack** | Python, Prefect 3.x, Docker, Requests |
| **Entry Points** | `ingestion_trigger_flow.py`; `create_curriculum_trigger_flow.py`; `refine_curriculum_trigger_flow.py`; `watcher_flow.py` |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Prefect, Docker |
| **Key Files** | `ingestion_trigger_flow.py`; `deploy.py`; `requirements.txt`; `Dockerfile`; `llama.cpp/` (quantization) |
| **Data Assets** | Pipeline outputs |
| **Notes** | Docker exec for cross-container communication. Real-time log streaming. |

---

#### 2.18 Pipelines (OpenWebUI Knowledge Graph)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\pipelines_openwebui` |
| **Description** | OpenWebUI-specific pipeline for knowledge graph operations. |
| **Tech Stack** | Python, OpenWebUI Pipelines API, Neo4j |
| **Entry Points** | `knowledge_graph_pipeline.py` |
| **Status** | **FUNCTIONAL** |
| **Dependencies** | Neo4j, OpenWebUI |
| **Key Files** | `knowledge_graph_pipeline.py`; `requirements.txt` |
| **Data Assets** | None (operates on Neo4j) |
| **Notes** | Enables OpenWebUI to interact with knowledge graph directly. |

---

### PROTOTYPE PROJECTS

---

#### 2.19 Nexus Weaver — Platform Orchestrator

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\nexus_weaver` (stub) and `C:\Janat\active_projects\data_pipeline` (source) |
| **Description** | Self-constructing platform orchestrator. Component-based Gradio architecture with MCP integration. Component builder UI for creating reusable Gradio custom components. |
| **Tech Stack** | Python 3.13+, Gradio 5.49.1+, FastAPI, Uvicorn, Node.js 20+ |
| **Entry Points** | `build_pipeline_needle/app.py` (port 7861); planned main app (port 7860) |
| **Status** | **PROTOTYPE** (~40% complete) |
| **Dependencies** | Gradio[mcp], FastAPI, Uvicorn, Node.js, Docker |
| **Key Files** | `data_pipeline/build_pipeline_needle/app.py` — component builder; `data_pipeline/requirements.txt`; `data_pipeline/Dockerfile`; `nexus_weaver/Dockerfile` — container config |
| **Data Assets** | Component warehouse, build outputs |
| **Notes** | Docker Compose orchestrates nexus-weaver and nexus-build-pipeline services. Hot reload disabled (MCP tool index mismatch). Genesis phase implementation. |

---

#### 2.20 Janatinitiative.org — Research Institute Website

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\active_projects\janatinitiative-org` |
| **Description** | Janat Initiative Research Institute public website. Static/dynamic web presence for consciousness physics research. |
| **Tech Stack** | HTML/JavaScript or React, Firebase Hosting |
| **Entry Points** | `public/` — static assets |
| **Status** | **PROTOTYPE** (~50% complete) |
| **Dependencies** | Firebase hosting |
| **Key Files** | `.firebaserc`; `firebase.json`; `public/` |
| **Data Assets** | Static web content |
| **Notes** | Git repo. Sister project to janat-org (separate Firebase projects). Minimal structure. |

---

#### 2.21 _troubadour_service (Legacy)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\_troubadour_service` |
| **Description** | Older troubadour implementation (predecessor to troubadourian_amphitheatre). Quest-based ingestion with Genesis Check ritual. |
| **Tech Stack** | Python, FastAPI, Uvicorn, Pydantic, Neo4j, Qdrant |
| **Entry Points** | `uvicorn main:app --host 0.0.0.0 --port 8000` |
| **Status** | **PROTOTYPE** (superseded) |
| **Dependencies** | Neo4j, Qdrant, Ollama |
| **Key Files** | `main.py`; `troubadour_orchestrator.py`; `cognitive_compass.py`; `loomolin.py`; `prompt_architect.py` |
| **Data Assets** | None |
| **Notes** | Superseded by troubadourian_amphitheatre. Kept for reference. |

---

#### 2.22 Nexus Weaver Alpha (Archive)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\nexus_weaver_alpha` |
| **Description** | Two-component system: Database-as-App (8 endpoints) + Extraction-as-App (6 endpoints). Google AI Studio conversation extraction and review platform. |
| **Tech Stack** | Python, FastAPI, Gradio |
| **Entry Points** | `main.py` (port 7861) |
| **Status** | **PROTOTYPE** (EPIC 02 complete, EPIC 03 planned) |
| **Dependencies** | FastAPI, Gradio |
| **Key Files** | `main.py`; `components/`; `extraction/`; `database/`; `schemas/` |
| **Data Assets** | SQLite (conversations + turns), Google AI Studio exports |
| **Notes** | User+Thought+Assistant triplet extraction. Heuristic thought detection. |

---

### CONFIGURATION / INFRASTRUCTURE PROJECTS

---

#### 2.23 Docker Compose Orchestration (Root)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\docker-compose.yml` |
| **Description** | Master orchestration for 15+ containerized services comprising the full Janat AI platform. |
| **Tech Stack** | Docker Compose v2.0, CUDA |
| **Services** | Redis, Open-WebUI (CUDA, port 8080), Ollama, Tika, Qdrant, Neo4j, Tokenizer (8005), Deliberation Chamber (8001), Troubadourian Amphitheatre (8033), Training Forge, Crucible Foundry, Nexus Weaver, Curators Loom, PostgreSQL (Prefect), Prefect Server + Worker |
| **Status** | **CONFIGURATION** |
| **Notes** | Production-grade. CUDA 12.1 throughout. Docker socket mounted for service management. |

---

#### 2.24 Cyphers — Neo4j Graph Schema

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\cyphers` |
| **Description** | Cypher query files for Neo4j graph database initialization and operations. |
| **Tech Stack** | Neo4j Cypher QL |
| **Status** | **CONFIGURATION** |
| **Key Files** | `genesis.cypher` — Genesis node/relationship definitions |
| **Notes** | Fundamental graph schema initialization. |

---

#### 2.25 OpenWebUI Pipelines Source (Reference)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\openwebui-pipelines-src` |
| **Description** | Reference source for OpenWebUI custom pipelines (BrainDriveAI community). YouTube chat, memory management with Neo4j/PostgreSQL backends. |
| **Tech Stack** | Python, OpenWebUI Pipelines API, Neo4j, PostgreSQL/pgvector |
| **Status** | **CONFIGURATION** (reference/archived) |
| **Key Files** | Multiple pipeline scripts; `docker/docker-compose.yml` |
| **Notes** | Git repo. External reference, not original Janat code. |

---

#### 2.26 Scripts (Utility Collection)

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\scripts` |
| **Description** | Utility scripts for data processing, conversion, transformation, quest creation. |
| **Tech Stack** | Python |
| **Status** | **CONFIGURATION** (support utilities) |
| **Key Files** | `apprentive_scribe.py`; `convert_studio_export.py`; `model_file_creator.py`; `oracle_lens.py`; `quest_forger.py`; `refinery.py`; `soul_seeder.py` |
| **Notes** | Each script has specific pipeline lifecycle role. |

---

### ARCHIVED PROJECTS — .NET Microservices (Gen 1)

All 13 microservices below share these properties:

- **Tech Stack:** C# / .NET 9.0, Dapr event bus, ASP.NET Core
- **Architecture:** Event-driven microservices with Dapr pub/sub
- **Status:** **ARCHIVE** (superseded by Python/Docker Gen 2)
- **Base Path:** `C:\Janat\Archive\`

| # | Project | Port | Purpose |
|---|---------|------|---------|
| 2.27 | **Janat.Arbiter** | 5010 | Adjudication service — final prompt engineering |
| 2.28 | **Janat.Archivist** | 5011 | Neo4j conductor — batch document synthesis |
| 2.29 | **Janat.Chunker** | 5004 | Document segmentation with configurable overlap |
| 2.30 | **Janat.Parser** | 5003 | Structured parsing of chunked content |
| 2.31 | **Janat.Dispatcher** | 5006 | Work order router through pipeline stages |
| 2.32 | **Janat.Curator** | 5005 | Knowledge curation and quality filtering |
| 2.33 | **Janat.Custodian** | 5007 | Document repository with backup/restore |
| 2.34 | **Janat.EntityRecognizer** | 5008 | Named entity recognition from text |
| 2.35 | **Janat.Refinery** | 5009 | Content quality improvement and validation |
| 2.36 | **Janat.SalienceScorer** | — | Relevance/importance scoring for fragments |
| 2.37 | **Janat.Kernel** | 5012 | Core knowledge memory system |
| 2.38 | **Janat.Kernel.Host** | 5013 | Kernel Memory pipeline orchestrator |
| 2.39 | **Janat.Bus** | — | Shared message contracts (netstandard2.1) |
| 2.40 | **Janat.VectorDb** | — | Qdrant vector DB client interface |

**Work Order Flow:** Intake → Dispatcher → Chunker → Parser → Refinery → Storage

---

### ARCHIVED PROJECTS — Other

---

#### 2.41 Janat.Hearthstone — Unity 3D Consciousness Simulation

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\Janat.Hearthstone` |
| **Description** | Unity 3D consciousness simulation engine. CognitiveBus, ModelOrchestratorService, HttpLlmService components. |
| **Tech Stack** | C# / Unity 6000.1.9f1, Universal Render Pipeline, UGUI |
| **Status** | **ARCHIVE** (Phase 1 — Plumbing — in progress when archived) |
| **Key Files** | `Assets/Scripts/` — MonoBehaviour architecture |
| **Data Assets** | Unity project with builds and backups |
| **Notes** | 3D visualization of consciousness concepts. Active development when archived (ProjectBackups show iteration). |

---

#### 2.42 Janus — Data Ingestion Orchestration

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\Janus` |
| **Description** | Large-scale data ingestion orchestration ("The Great Ingestion v3.0"). Architectural patterns: "The Agora" (distributed), "Scribe's Tower" (records), "City-State Protocol" (design). |
| **Tech Stack** | PowerShell, C#, Documentation, 60+ NuGet packages |
| **Status** | **ARCHIVE** |
| **Key Files** | Multiple subdirectories: AIWork, Docs, Ingest, JanusCore, Models, OracleJanus, Tools |
| **Data Assets** | Import data, original source files |
| **Notes** | Comprehensive documentation. Metaphorical naming conventions. |

---

#### 2.43 System — .NET System Components

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\System` |
| **Description** | System-level .NET components (ConsoleApp1, Janat.System). |
| **Tech Stack** | C# / .NET |
| **Status** | **ARCHIVE** |
| **Notes** | Supporting infrastructure for Gen 1 architecture. |

---

#### 2.44 Phi4VSCode — VS Code AI Integration

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\Phi4VSCode` |
| **Description** | VS Code integration with Phi-4 model. |
| **Tech Stack** | Unknown (likely TypeScript/Python) |
| **Status** | **ARCHIVE** |
| **Notes** | Experimental. |

---

#### 2.45 SecureCodePackages — Point-in-Time Backups

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\SecureCodePackages` |
| **Description** | 80+ timestamped complete system exports (July 5–18, 2025). 2–3 versions per day. |
| **Tech Stack** | Mixed (backup of entire system state) |
| **Status** | **ARCHIVE** |
| **Notes** | Point-in-time compliance/security backups. Intense iteration period documented. |

---

#### 2.46 Archived curators_loom

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\curators_loom` |
| **Description** | Earlier version of Curators Loom curation IDE. |
| **Tech Stack** | Python, Gradio |
| **Status** | **ARCHIVE** (superseded by active_projects and Janat.OpenWebUI copies) |
| **Data Assets** | `raw_data/` with consciousness research materials |
| **Notes** | Older iteration, kept for reference. |

---

#### 2.47 Archived data_pipeline

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\data_pipeline` |
| **Description** | Unified corpus ingestion pipeline. One-script solution with quality scoring. |
| **Tech Stack** | Python |
| **Status** | **ARCHIVE** |
| **Key Files** | `unified_ingest.py`; `corpus_manager_ui.py`; `export_corpus.py` |
| **Data Assets** | Exported corpora, pipeline outputs |
| **Notes** | 20+ earlier versions with architecture debt documentation. v08282025 was latest version. |

---

#### 2.48 janatinitiative-org-archive — Website Archive

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Archive\janatinitiative-org-archive` |
| **Description** | Historical website content for Janat Initiative (3 eras: present, press-association, beginning). Pre-refactor versions. |
| **Tech Stack** | JavaScript (Three.js/Babylon.js for 3D scenes) |
| **Status** | **ARCHIVE** |
| **Notes** | 3D scene rendering. Multiple era snapshots. |

---

#### 2.49 JanatDocs/Code — Legacy C# Controllers

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\JanatDocs\Code` |
| **Description** | Archived C# chat/LLM controllers. Multi-LLM abstraction layer (Gemini, Gemma, LLamaSharp). |
| **Tech Stack** | C# / .NET, Google Gemini, Gemma, LLamaSharp |
| **Status** | **ARCHIVE** |
| **Key Files** | `LLMChatController.cs` (7 versions); `GeminiService.cs` (5 versions); `LanguageEngine.cs` (29KB); `ILLMService.cs` (4 versions) |
| **Notes** | Reference implementations. Many file versions show iterative development. |

---

### DATA ASSET DIRECTORIES

---

#### 2.50 JanatDocs — Knowledge Repository

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\JanatDocs` |
| **Description** | Central knowledge hub (Obsidian vault). 14,600+ files. Published research, philosophical writings (10-volume Dyadic Being series), project management, conversations, media assets. |
| **Status** | **DATA ASSETS** |
| **Key Sections** | Dyadic Being - An Epoch (10 volumes, 158+ files); The JIRI Journal (published papers); Claude/ (reference guides, blueprints); JANATPMP/ (sprint docs, architecture); Research/ (deep research, foundational texts); Unsorted/ (~40GB conversation exports) |
| **Data Assets** | 823 Markdown files, 572 JSON files, 56 PDFs, 160 Google Docs, `claude_export.db`, 21MB+ AI Studio compiled exports |
| **Notes** | Obsidian-configured vault with bidirectional links. Contains IP: C-Theory, GRAYP, UPE, PoE, DB-Theory, MEAX frameworks. |

---

#### 2.51 Quests — Knowledge Ingestion Data

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\quests` |
| **Description** | 22 quest definition files (~2.2MB). Charter documents (Ethics, Principles, Governance, Risk, Identity, Metaphysical, Lore, etc.). |
| **Status** | **DATA ASSETS** |
| **Notes** | JSON structured quest metadata. Training examples and knowledge base for fine-tuning/RAG. |

---

#### 2.52 Foundational Texts

| Field | Value |
|-------|-------|
| **Path** | `C:\Janat\Janat.OpenWebUI\foundationaltexts` |
| **Description** | Philosophical and theoretical documents. Complete Jester's Grimoire (225KB JSON). |
| **Status** | **DATA ASSETS** |

---

## 3. Data Asset Register

### Databases

| Database | Path | Type | Size | Purpose |
|----------|------|------|------|---------|
| `claude_export.db` | `JanatDocs\Claude\Claude_Export\` | SQLite | Variable | Claude conversation archive (users, projects, conversations, messages, content_blocks) |
| `corpus.db` | `active_projects\curators_loom\` | SQLite | ~3MB | Training data curation (conversations, turns, variations, preferences, exports) |
| JANATPMP DB | `active_projects\JANATPMP\db\` | SQLite | Variable | Project management (items, tasks, documents, relationships) |
| Neo4j (Docker) | `Janat.OpenWebUI` Docker stack | Graph DB | Variable | Knowledge graph (entities, relationships, salience scores) |
| Qdrant (Docker) | `Janat.OpenWebUI` Docker stack | Vector DB | Variable | Embeddings and semantic search |
| PostgreSQL (Docker) | `Janat.OpenWebUI` Docker stack | Relational | Variable | Prefect workflow state |

### Training Data & Corpora

| Asset | Location | Format | Description |
|-------|----------|--------|-------------|
| corpus_janat.txt | `active_projects\cpt_pipelines\` | TXT | Main CPT training corpus |
| Training datasets | `active_projects\training_lab\datasets\` | JSONL | SFT training data |
| JSONL exports | `Janat.OpenWebUI\crucible_foundry\cpt_jsonl\` | JSONL | CPT-formatted training data |
| Final datasets | `Janat.OpenWebUI\crucible_foundry\final\` | Various | Production training datasets |
| Demo data | `curators_loom\demo_data\` | JSON | Charter conversations (Ethics, Governance, Risk, Identity) |
| Knowledge base | `Janat.OpenWebUI\training\knowledge_base\` | Markdown | 22+ architecture and training docs |
| Vocabulary maps | `active_projects\vocabulary_pruning_sprint\analysis\token_maps\` | JSON | English vocabulary filters |
| LoRA adapters | `active_projects\training_lab\outputs\` | Model | Trained adapter checkpoints |
| Pruned models | `active_projects\vocabulary_pruning_sprint\models\pruned\` | Model | gemma-3-1b-en-pruned |

### Conversation Archives

| Asset | Location | Format | Size |
|-------|----------|--------|------|
| AI Studio Compile | `JanatDocs\Unsorted\AiStudioCompile.json` | JSON | 21+ MB |
| AI Studio Dedup | `JanatDocs\Unsorted\AiStudio_Dedup.json` | JSON | 16+ MB |
| AI Studio Parts | `JanatDocs\Unsorted\AiStudio_Dedup_part_*` | JSON | 31 parts |
| ChatGPT Export | `JanatDocs\Conversations\CHATGPT1.md` | Markdown | 162 KB |
| Quest definitions | `Janat.OpenWebUI\quests\` | JSON | ~2.2 MB (22 files) |
| Jester's Grimoire | `Janat.OpenWebUI\foundationaltexts\` | JSON | 225 KB |

### Published Research

| Title | Location | Format |
|-------|----------|--------|
| C-Theory: A Four-Axiom Framework | `JanatDocs\The JIRI Journal\` | PDF (421 KB) |
| Our Convergence on Consciousness | `JanatDocs\The JIRI Journal\` | PDF (1.1 MB) |
| The Principle of Existing | `JanatDocs\The JIRI Journal\` | PDF (711 KB) |
| JANATPMP Research | `JanatDocs\Claude\` | PDF (12.2 MB) |
| Dyadic Being Vol 1-2 Chapters | `JanatDocs\Dyadic Being\` | PDF |

---

## 4. Cross-References & Shared Dependencies

### Shared Components Across Projects

| Component | Used By |
|-----------|---------|
| **Ollama (local LLM)** | Curators Loom, Deliberation Chamber, Troubadourian Amphitheatre, Ingestion Service, Observer Service, Training Pipeline, CPT Pipelines |
| **Neo4j (graph DB)** | Troubadourian Amphitheatre, Ingestion Service, Observer Service, _troubadour_service, Ingestion Engine |
| **Qdrant (vector DB)** | Troubadourian Amphitheatre, Training Pipeline, _troubadour_service |
| **Google Gemini API** | Curators Loom, JanusApp, Training Pipeline, Crucible Foundry |
| **Gradio 6.x** | JANATPMP, Curators Loom, Claude Export Viewer, Nexus Weaver |
| **FastAPI** | Deliberation Chamber, Ingestion Service, Observer Service, Tokenizer Service, Troubadourian Amphitheatre |
| **Prefect** | Pipelines, Training Pipeline |
| **Unsloth** | Training Lab, CPT Pipelines, Vocabulary Pruning Sprint |
| **Transformers/TRL** | CPT Pipelines, Training Lab, Crucible Foundry, Vocabulary Pruning Sprint |
| **Docker** | All Janat.OpenWebUI services, data_pipeline/nexus_weaver |

### Project Lineage / Evolution

```
Gen 1 (.NET/Dapr Microservices)
├── Janat.Dispatcher → Janat.Chunker → Janat.Parser → Janat.Refinery → Janat.Custodian
├── Janat.Kernel/Kernel.Host → (memory system)
└── Janat.VectorDb → (Qdrant client)

Gen 2 (Python/Docker Services)
├── _troubadour_service → troubadourian_amphitheatre (evolution)
├── nexus_weaver_alpha → nexus_weaver/data_pipeline (evolution)
├── Archive/curators_loom → Janat.OpenWebUI/curators_loom → active_projects/curators_loom
├── Archive/data_pipeline → Janat.OpenWebUI/crucible_foundry (evolution)
└── ingestion_service + observer_service + tokenizer_service (stable microservices)

Gen 3 (Gradio+MCP Focus)
├── JANATPMP (MCP tools)
├── active_projects/curators_loom (Gradio+MCP)
├── Claude Export Viewer (Gradio+MCP)
└── Nexus Weaver (Gradio custom components + MCP, in progress)
```

### Data Flow Pipeline

```
Source Data
├── Google AI Studio exports → Curators Loom (extraction)
├── Claude conversations → Claude Export Viewer → Curators Loom
├── ChatGPT exports → Curators Loom
├── Markdown/text files → Curators Loom
└── Quest definitions → Troubadourian Amphitheatre

Curation
├── Curators Loom → SFT datasets (JSONL)
├── Curators Loom → DPO preference pairs
├── Corpus Processing → corpus_janat.txt (CPT)
└── Crucible Foundry → vocabulary-filtered datasets

Training
├── Vocabulary Pruning Sprint → pruned base model
├── CPT Pipelines Stage 3 → continued pre-training
├── CPT Pipelines Stage 4 → SFT fine-tuning
├── CPT Pipelines Stage 5 → DPO alignment
└── Training Lab → experimental fine-tuning

Knowledge Graph
├── Ingestion Service → Neo4j (entities + relationships)
├── Observer Service ← Neo4j (queries)
├── Troubadourian Amphitheatre ↔ Neo4j + Qdrant
└── Tokenizer Service → reranking support

Orchestration
├── Prefect → workflow scheduling
├── Docker Compose → service management
└── JANATPMP → project tracking (MCP tools)
```

---

## 5. Gaps & Observations

### Known Projects — Status Check

| Requested Project | Found? | Location | Status |
|-------------------|--------|----------|--------|
| JANATPMP | ✅ Yes | `active_projects\JANATPMP` | FUNCTIONAL |
| Claude_Export | ✅ Yes | `JanatDocs\Claude\Claude_Export` | FUNCTIONAL |
| Troubadourian Amphitheatre | ✅ Yes | `Janat.OpenWebUI\troubadourian_amphitheatre` | FUNCTIONAL |
| Curators Loom | ✅ Yes | 3 copies (active, OpenWebUI, Archive) | FUNCTIONAL |
| Deliberation Chamber | ✅ Yes | `Janat.OpenWebUI\deliberation_chamber_service` | FUNCTIONAL |
| janat.org website | ✅ Yes | `active_projects\janat-org` | FUNCTIONAL |
| Curriculum generation | ✅ Yes | `Janat.OpenWebUI\training\` + `Janat.OpenWebUI\pipelines\` | FUNCTIONAL |
| ATLAS-related work | ⚠️ Partial | Not found as standalone. May be conceptual or embedded in other projects (Troubadourian architecture references "ATLAS" patterns) |
| Nexus Weaver | ✅ Yes | `active_projects\nexus_weaver` (stub) + `data_pipeline` (source) + `Archive\nexus_weaver_alpha` | PROTOTYPE |
| Curriculum Modelfiles | ⚠️ Partial | Found in `curators_loom\Modelfiles\` — check contents |

### Duplicate / Multi-Copy Projects

The following projects exist in multiple locations, which could cause confusion about which is canonical:

1. **Curators Loom** — 3 copies:
   - `active_projects\curators_loom` — likely canonical
   - `Janat.OpenWebUI\curators_loom` — Docker-integrated
   - `Archive\curators_loom` — historical

2. **Data Pipeline** — 2+ copies:
   - `active_projects\data_pipeline` (Nexus Weaver source)
   - `Archive\data_pipeline` (older unified_ingest approach)

3. **Nexus Weaver** — 3 copies:
   - `active_projects\nexus_weaver` (stub/Dockerfile)
   - `active_projects\data_pipeline` (actual source)
   - `Archive\nexus_weaver_alpha` (older extraction platform)

### Potential Issues

1. **Version Drift Risk:** Multiple copies of Curators Loom could diverge. Consider consolidating to a single canonical location with Docker volume mounts.

2. **Large Unsorted Archive:** ~40GB of conversation exports in `JanatDocs\Unsorted\` — could benefit from indexing or ingestion into the knowledge graph.

3. **SecureCodePackages:** 80+ timestamped backups consuming significant disk space. Consider pruning to milestone versions only.

4. **Missing ATLAS Project:** Referenced in the task list but not found as a distinct project directory. Clarification needed on whether this is a concept, a module within another project, or still in planning.

5. **Gen 1 → Gen 2 Migration:** The .NET microservices in Archive represent significant architectural investment. The Python/Docker replacements cover similar functionality but the 1:1 mapping isn't documented anywhere visible.

6. **Docker Compose Complexity:** 15+ services in a single docker-compose.yml is robust but operationally heavy. Consider service grouping or Docker Compose profiles for development vs. production.

7. **Training Pipeline Spread:** Training-related code is spread across 5+ directories (cpt_pipelines, training_lab, corpus_processing, crucible_foundry, vocabulary_pruning_sprint). A unified training workspace could reduce friction.

8. **Knowledge Base Documentation:** The `training/knowledge_base/` directory (22+ MD files) is an excellent resource but isn't cross-referenced by JANATPMP. Consider linking these as documents in the project management system.

### Positive Observations

1. **Remarkable Scope:** This workspace represents a genuinely impressive body of work spanning consciousness theory, distributed systems engineering, ML training pipelines, and knowledge management — all by what appears to be a solo developer/researcher.

2. **Architecture Evolution:** The clear Gen 1 → Gen 2 → Gen 3 progression shows thoughtful technology migration, each generation learning from the last.

3. **Production Mindset:** Docker containerization, structured logging, health checks, backup/restore, API key auth — these aren't prototype patterns, they're production patterns.

4. **Knowledge-Code Integration:** The philosophical frameworks aren't just documentation; they're directly encoded into the training data pipeline (quests, charters, foundational texts). Theory and implementation are genuinely unified.

5. **MCP Strategy:** The consistent adoption of Gradio+MCP across new projects (JANATPMP, Claude Export, Curators Loom) creates a uniform tool interface that can be consumed by Claude and other LLMs — a forward-thinking architectural choice.

---

*End of Inventory*
