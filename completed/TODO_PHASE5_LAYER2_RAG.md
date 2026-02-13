# Phase 5 — Layer 2: RAG Pipeline (Qdrant + Embedding + Retrieval)

## Goal
Add semantic search and RAG (Retrieval-Augmented Generation) to JANATPMP. Documents and conversation messages get embedded and stored in Qdrant. Chat queries are enriched with relevant context before hitting Ollama for inference.

## Branch
```bash
git checkout -b phase5-rag-pipeline
# (branch may already exist from Layer 1 — use it)
```

## Architecture Overview

```
                    JANATPMP owns this entire pipeline
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Document/Message ──► Embed (sentence-transformers) ──► Qdrant   │
│                        nvidia/llama-nemotron-embed-1b-v2          │
│                                                                  │
│  User Query ──► Embed ──► Qdrant Search ──► Top-K chunks         │
│                                              │                   │
│                              Context injection                   │
│                                              │                   │
│                              Ollama /api/chat ──► Response       │
│                              (Nemotron-3-Nano)                   │
└──────────────────────────────────────────────────────────────────┘
```

**Boundary:** Ollama = inference only. JANATPMP = embedding + vector storage + RAG orchestration.

**Embedding model:** `nvidia/llama-nemotron-embed-1b-v2` via sentence-transformers
- 1B params, 2048-dim embeddings, 8192 token context
- Asymmetric encoding: `input_type="passage"` for documents, `input_type="query"` for searches
- Loaded directly in Python (NOT via Ollama)

## Step 1: Docker Infrastructure

### 1a. Add Qdrant to docker-compose.yml

Add the Qdrant service to the existing `docker-compose.yml`. Do NOT remove or modify the existing `core` or `ollama` services.

```yaml
  qdrant:
    image: qdrant/qdrant:latest
    container_name: janatpmp-qdrant
    ports:
      - "6333:6333"   # REST API
      - "6334:6334"   # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped
    networks:
      - janatpmp_network
```

Add to the `core` service:
```yaml
  core:
    volumes:
      - .:/app
      - C:\Janat\Claude\Claude_Export:/data/claude_export:ro
      - huggingface_cache:/root/.cache/huggingface   # Shared model cache
    depends_on:
      - ollama
      - qdrant
```

Add to volumes section:
```yaml
volumes:
  ollama_data:
    external: true
  huggingface_cache:
    external: true
  qdrant_data:
    driver: local
```

**Volume strategy:**
- `huggingface_cache` is `external: true` — shared across containers (JANATPMP, future training forge, etc.). Models download once, available everywhere.
- `qdrant_data` is `driver: local` — Qdrant-specific, no need to share.
- `ollama_data` is `external: true` — already shared with Open WebUI.

**Before first run, create the external volume:**
```bash
docker volume create huggingface_cache
```

This means `nvidia/llama-nemotron-embed-1b-v2` (~2GB) downloads ONCE on first use, then persists across container rebuilds and is mountable by any future container (training forge, fine-tuning pipelines, etc.).

### 1b. Add Python dependencies to requirements.txt

Append to requirements.txt:
```
sentence-transformers
qdrant-client
```

Do NOT remove any existing dependencies. Do NOT pin versions (let pip resolve).

### 1c. Update Dockerfile

The existing Dockerfile is fine as-is. The `pip install -r requirements.txt` step will pick up the new dependencies. No changes needed UNLESS sentence-transformers requires system packages — test first.

**If the build fails** due to missing system packages, add before the pip install line:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*
```

## Step 2: Embedding Service

### New file: `services/embedding.py`

```python
"""Embedding service using NVIDIA Llama-Nemotron-Embed-1B-v2.

Provides document embedding and query embedding with asymmetric encoding.
Model is loaded lazily on first use and cached for the process lifetime.
"""

from sentence_transformers import SentenceTransformer

_model = None

def _get_model() -> SentenceTransformer:
    """Lazy-load the embedding model (first call downloads ~2GB)."""
    global _model
    if _model is None:
        _model = SentenceTransformer(
            "nvidia/llama-nemotron-embed-1b-v2",
            trust_remote_code=True,
        )
    return _model


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed document passages for storage.
    
    Args:
        texts: List of text passages to embed.
    
    Returns:
        List of embedding vectors (2048-dim each).
    """
    model = _get_model()
    embeddings = model.encode(texts, prompt_name="passage")
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a search query for retrieval.
    
    Args:
        query: The search query text.
    
    Returns:
        Single embedding vector (2048-dim).
    """
    model = _get_model()
    embedding = model.encode([query], prompt_name="query")
    return embedding[0].tolist()
```

**Key points:**
- Lazy loading prevents model download on every container restart if embedding isn't used
- `prompt_name="passage"` vs `prompt_name="query"` is CRITICAL — asymmetric encoding
- Returns plain Python lists (not numpy arrays) for JSON serialization compatibility
- Model downloads to `huggingface_cache` volume on first use (~2GB), persists across rebuilds and is shared with other containers

## Step 3: Vector Store Service

### New file: `services/vector_store.py`

```python
"""Qdrant vector store operations for JANATPMP RAG pipeline.

Collections:
- janatpmp_documents: Embedded document chunks
- janatpmp_messages: Embedded conversation messages
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue,
)
from services.embedding import embed_passages, embed_query

QDRANT_URL = "http://qdrant:6333"  # Docker DNS
VECTOR_DIM = 2048
COLLECTION_DOCUMENTS = "janatpmp_documents"
COLLECTION_MESSAGES = "janatpmp_messages"

_client = None

def _get_client() -> QdrantClient:
    """Lazy-load Qdrant client."""
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=30)
    return _client


def ensure_collections():
    """Create collections if they don't exist. Safe to call multiple times."""
    client = _get_client()
    existing = [c.name for c in client.get_collections().collections]
    
    for name in [COLLECTION_DOCUMENTS, COLLECTION_MESSAGES]:
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=VECTOR_DIM,
                    distance=Distance.COSINE,
                ),
            )


def upsert_document(doc_id: str, text: str, metadata: dict):
    """Embed and store a document chunk.
    
    Args:
        doc_id: Unique document ID (from JANATPMP documents table).
        text: The text content to embed.
        metadata: Dict with keys like doc_type, title, source, created_at.
    """
    client = _get_client()
    vectors = embed_passages([text])
    
    client.upsert(
        collection_name=COLLECTION_DOCUMENTS,
        points=[PointStruct(
            id=doc_id,  # Qdrant supports string IDs
            vector=vectors[0],
            payload={"text": text, **metadata},
        )],
    )


def upsert_message(message_id: str, text: str, metadata: dict):
    """Embed and store a conversation message.
    
    Args:
        message_id: Unique message identifier.
        text: Combined user_prompt + model_response text.
        metadata: Dict with conversation_id, sequence, etc.
    """
    client = _get_client()
    vectors = embed_passages([text])
    
    client.upsert(
        collection_name=COLLECTION_MESSAGES,
        points=[PointStruct(
            id=message_id,
            vector=vectors[0],
            payload={"text": text, **metadata},
        )],
    )


def search(query: str, collection: str = COLLECTION_DOCUMENTS, limit: int = 5) -> list[dict]:
    """Semantic search across a collection.
    
    Args:
        query: Natural language search query.
        collection: Which collection to search.
        limit: Max results to return.
    
    Returns:
        List of dicts with keys: id, score, text, and all metadata fields.
    """
    client = _get_client()
    query_vector = embed_query(query)
    
    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=limit,
        with_payload=True,
    )
    
    return [
        {
            "id": str(hit.id),
            "score": hit.score,
            **hit.payload,
        }
        for hit in results.points
    ]


def search_all(query: str, limit: int = 5) -> list[dict]:
    """Search across ALL collections, merged and sorted by score.
    
    Args:
        query: Natural language search query.
        limit: Max results per collection (total may be up to 2x limit).
    
    Returns:
        List of dicts with source_collection field added, sorted by score desc.
    """
    docs = search(query, COLLECTION_DOCUMENTS, limit)
    for d in docs:
        d["source_collection"] = "documents"
    
    msgs = search(query, COLLECTION_MESSAGES, limit)
    for m in msgs:
        m["source_collection"] = "messages"
    
    combined = docs + msgs
    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined[:limit]
```

**Qdrant URL:** Use `http://qdrant:6333` for Docker networking. For local dev outside Docker, fall back to `http://localhost:6333`. Consider making this configurable via settings or environment variable.

## Step 4: RAG Integration with Chat

### Modify: `services/chat.py`

Add a RAG context injection step to the chat flow. The goal is to enrich the user's message with relevant context from Qdrant before sending to the LLM.

**Add a new function:**

```python
def _build_rag_context(user_message: str, max_chunks: int = 3) -> str:
    """Search Qdrant for relevant context and format for injection.
    
    Args:
        user_message: The user's current message.
        max_chunks: Maximum number of context chunks to include.
    
    Returns:
        Formatted context string, or empty string if no results or Qdrant unavailable.
    """
    try:
        from services.vector_store import search_all
        results = search_all(user_message, limit=max_chunks)
        if not results:
            return ""
        
        context_parts = []
        for r in results:
            source = r.get("source_collection", "unknown")
            title = r.get("title", "")
            text = r.get("text", "")[:500]  # Truncate long chunks
            score = r.get("score", 0)
            if score > 0.3:  # Only include reasonably relevant results
                context_parts.append(f"[{source}] {title}: {text}")
        
        if not context_parts:
            return ""
        
        return "\n\n---\nRelevant context from knowledge base:\n" + "\n\n".join(context_parts) + "\n---\n"
    except Exception:
        return ""  # Graceful degradation if Qdrant is down
```

**Modify the existing chat flow** to inject RAG context. Find where the user message is assembled and add:

```python
rag_context = _build_rag_context(user_message)
if rag_context:
    # Append context to system prompt or user message — prefer system prompt
    # to keep the user message clean in the triplet
    enhanced_system_prompt = system_prompt + rag_context
```

**CRITICAL:** Do NOT break existing chat functionality. RAG context injection must be:
- Gracefully degradable (try/except, empty string fallback)
- Optional (if Qdrant is not running, chat still works)
- Non-destructive (don't modify the stored user_prompt in triplets — only enhance what goes to the LLM)

## Step 5: Bulk Embedding of Existing Data

### New file: `services/bulk_embed.py`

```python
"""Bulk embed existing JANATPMP data into Qdrant.

Run once to backfill, then incremental embedding happens via CDC or on-create.
"""

from db.operations import list_documents, get_connection
from services.vector_store import ensure_collections, upsert_document, upsert_message


def embed_all_documents() -> dict:
    """Embed all documents from the documents table.
    
    Returns:
        Dict with keys: embedded, skipped, errors.
    """
    ensure_collections()
    docs = list_documents(limit=10000)
    embedded = 0
    skipped = 0
    errors = []
    
    for doc in docs:
        try:
            content = doc.get("content", "")
            if not content or len(content.strip()) < 10:
                skipped += 1
                continue
            
            upsert_document(
                doc_id=doc["id"],
                text=content,
                metadata={
                    "title": doc.get("title", ""),
                    "doc_type": doc.get("doc_type", ""),
                    "source": doc.get("source", ""),
                    "created_at": doc.get("created_at", ""),
                },
            )
            embedded += 1
        except Exception as e:
            errors.append(f"{doc.get('id', '?')}: {str(e)[:80]}")
    
    return {"embedded": embedded, "skipped": skipped, "errors": errors}


def embed_all_messages() -> dict:
    """Embed all conversation messages.
    
    Returns:
        Dict with keys: embedded, skipped, errors.
    """
    ensure_collections()
    embedded = 0
    skipped = 0
    errors = []
    
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT m.id, m.conversation_id, m.sequence,
                   m.user_prompt, m.model_response,
                   c.title as conv_title
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.user_prompt != '' OR m.model_response != ''
        """)
        rows = cursor.fetchall()
    
    for row in rows:
        try:
            # Combine prompt + response for richer embedding
            text = f"Q: {row['user_prompt']}\nA: {row['model_response']}"
            if len(text.strip()) < 20:
                skipped += 1
                continue
            
            upsert_message(
                message_id=row["id"],
                text=text,
                metadata={
                    "conversation_id": row["conversation_id"],
                    "conv_title": row["conv_title"] or "",
                    "sequence": row["sequence"],
                },
            )
            embedded += 1
        except Exception as e:
            errors.append(f"{row.get('id', '?')}: {str(e)[:80]}")
    
    return {"embedded": embedded, "skipped": skipped, "errors": errors}
```

## Step 6: MCP Tools + Admin UI

### 6a. Expose via gr.api() in app.py

Add to the MCP tool section of app.py:

```python
from services.vector_store import search as vector_search, search_all as vector_search_all
from services.bulk_embed import embed_all_documents, embed_all_messages

gr.api(vector_search)
gr.api(vector_search_all)
gr.api(embed_all_documents)
gr.api(embed_all_messages)
```

### 6b. Admin Tab — Embedding Controls

In the Admin/Database tab, add a simple section:

```python
gr.Markdown("### Vector Store (Qdrant)")
with gr.Row():
    embed_docs_btn = gr.Button("Embed All Documents")
    embed_msgs_btn = gr.Button("Embed All Messages")
embed_status = gr.Textbox(label="Embedding Status", interactive=False)

embed_docs_btn.click(
    embed_all_documents, outputs=[embed_status],
    api_visibility="private"
)
embed_msgs_btn.click(
    embed_all_messages, outputs=[embed_status],
    api_visibility="private"
)
```

This gives Mat a manual trigger for bulk embedding. Incremental (on-create) embedding can come later.

## Step 7: Initialization

### Modify app.py startup

After `init_database()` and `init_settings()`, add Qdrant collection initialization:

```python
# Initialize vector store collections (safe if Qdrant not running)
try:
    from services.vector_store import ensure_collections
    ensure_collections()
except Exception:
    print("⚠️  Qdrant not available — vector search disabled")
```

This ensures collections exist on startup but doesn't crash the app if Qdrant is down.

## Testing Checklist

1. `docker compose up -d --build` — all three containers start (core, ollama, qdrant)
2. Qdrant health check: `curl http://localhost:6333/healthz` → returns OK
3. Collections created: `curl http://localhost:6333/collections` → shows both collections
4. Embedding model loads on first use (may take 30-60s to download)
5. Bulk embed documents → status shows count
6. Bulk embed messages → status shows count  
7. Semantic search via MCP: `vector_search_all("consciousness physics")` → returns relevant hits
8. Chat with RAG: Ask a question about a known document → response includes relevant context
9. Chat WITHOUT Qdrant: Stop Qdrant container, verify chat still works (graceful degradation)
10. Qdrant data persists across container restarts (volume check)

## Do NOT
- Modify the database schema (schema.sql)
- Touch the Chat tab UI layout
- Change how Ollama is configured or connected
- Add reranking (that's Layer 3)
- Add incremental embedding on document creation (that's Layer 3)
- Add chunking/splitting logic for long documents (that's Layer 3)
- Modify existing MCP tool signatures
- Remove any existing functionality

## File Summary

| File | Action |
|------|--------|
| `docker-compose.yml` | MODIFY — add qdrant service + volume |
| `requirements.txt` | MODIFY — add sentence-transformers, qdrant-client |
| `services/embedding.py` | CREATE — model loading + embed functions |
| `services/vector_store.py` | CREATE — Qdrant CRUD + search |
| `services/bulk_embed.py` | CREATE — backfill existing data |
| `services/chat.py` | MODIFY — add RAG context injection |
| `app.py` | MODIFY — add init + MCP tools |
| `tabs/tab_database.py` | MODIFY — add embedding buttons to Admin |

## GTC Contest Narrative

This implementation runs the full NVIDIA Nemotron stack on a single RTX 5090:
- **Nemotron-3-Nano** (via Ollama) — conversational inference
- **Llama-Nemotron-Embed-1B-v2** (via sentence-transformers) — document vectorization
- Both models running locally, zero cloud dependency
- RAG pipeline connects them: embed → store → retrieve → augment → infer
