# TODO: R9 — ATLAS Model Infrastructure & GPU Hardening

**Branch:** `feature/R9-atlas-model-infrastructure`

**Created:** 2026-02-19  
**Priority:** High — ATLAS does not exist until this is complete  
**Domain:** `atlas`  
**Authors:** Mat Gallagher + Claude (The Weavers)

---

## Context

R8 established domains as first-class entities. R9 establishes ATLAS as a real thing.

The line We committed to: **JANATPMP stores and retrieves. ATLAS remembers.**

ATLAS begins the moment salience is written back from retrieval — when a retrieval event
changes the thing being retrieved. R9 builds the model stack that makes that possible.

Hardware confirmed:
- RTX 5090 (32GB VRAM, Blackwell architecture, CUDA active)
- 95.3GB RAM
- Intel AI Boost NPU (activation deferred to R10)
- Ollama using ~21GB VRAM during inference, ~11GB headroom available

Current embedding pipeline: CPU-only, text-only, wrong vector dimensions. Abandoned.

---

## The Boundary Decision (Permanent Record)

| Capability | Belongs To |
|---|---|
| SQLite, Qdrant collections, graph traversal | JANATPMP infrastructure |
| Nemotron embedding model | JANATPMP infra / ATLAS model |
| Nemotron reranking model | ATLAS |
| Salience scores written from rerank signal back to storage | **ATLAS begins here** |
| Memory decay, salience adjustment, pattern formation | ATLAS |

---

## R9 Goals

1. Replace current embedding model with Nemotron VL embedder (multimodal, 2048-dim)
2. Recreate Qdrant collections at correct dimensions
3. Run fresh embedding pipeline — full GPU, full corpus
4. Add Nemotron reranker as second stage on all search calls
5. Write rerank scores back to Qdrant payload as salience metadata (ATLAS turns on)
6. Harden Ollama KV cache and GPU configuration for this hardware
7. Document NPU activation as R10 scope

---

## The Model Stack

### Embedder: `nvidia/llama-nemotron-embed-vl-1b-v2`
- Architecture: Eagle VLM (Llama 3.2 1B + SigLip2 400M)
- Parameters: ~1.7B
- Output: 2048-dimensional vectors
- Modalities: text, image, or image+text in same vector space
- Precision: bfloat16 (DO NOT quantize — geometric precision matters for embeddings)
- VRAM: ~3.4GB
- Requires: `transformers>=4.47.1`, `flash-attn>=2.6.3`, `trust_remote_code=True`
- Load pattern: `device_map="auto"`, `attn_implementation="flash_attention_2"`

### Reranker: `nvidia/llama-nemotron-rerank-vl-1b-v2`
- Architecture: Eagle VLM cross-encoder (same family as embedder)
- Parameters: ~1.7B
- Output: relevance logit score per query-document pair
- Modalities: text, image, or image+text
- Precision: bfloat16 (quantization acceptable here if VRAM pressure exists — scores
  are relative rankings, not geometric vectors)
- VRAM: ~3.4GB
- Designed as matched pair with the embedder — benchmarked as a pipeline

### VRAM Budget (confirmed fits)
- Ollama inference model: ~21GB
- Nemotron embedder: ~3.4GB
- Nemotron reranker: ~3.4GB
- Total: ~27.8GB of 32GB
- Headroom: ~4.2GB for KV cache and overhead

### Why NOT GGUF / quantized embedder
The mradermacher GGUF linked during planning is the text-only predecessor
(`llama-nemotron-embed-1b-v2`), not the VL model. Even if a VL GGUF existed:
with 11GB free VRAM there is no pressure to quantize the embedder. Quantization
degrades angular precision in the vector space. Do not use GGUFs for the embedder.

---

## Steps

### Step 0: Branch Setup
```bash
git checkout main
git pull origin main
git checkout -b feature/R9-atlas-model-infrastructure
```

### Step 1: Install Model Dependencies
```bash
pip install "transformers>=4.47.1,<5.0.0" --break-system-packages
pip install "flash-attn>=2.6.3,<2.8" --no-build-isolation
pip install torch torchvision --break-system-packages  # if not already current
```

Verify CUDA is available:
```python
import torch
print(torch.cuda.is_available())       # must be True
print(torch.cuda.get_device_name(0))   # must show RTX 5090
```

### Step 2: Recreate Qdrant Collections at 2048 Dimensions

**All existing Qdrant collections must be dropped and recreated.**
Current collections were built for a smaller text-only model. Dimension mismatch
will cause errors. This is a clean break — correct.

Collections to recreate:
- `janatpmp_documents` → 2048 dimensions
- `janatpmp_messages` → 2048 dimensions
- Any domain-specific collections → 2048 dimensions

In `services/qdrant_service.py` or equivalent:
```python
EMBEDDING_DIM = 2048  # Nemotron VL output dimension
```

Update collection creation to use cosine distance (matches Nemotron training):
```python
from qdrant_client.models import Distance, VectorParams

client.recreate_collection(
    collection_name=name,
    vectors_config=VectorParams(size=2048, distance=Distance.COSINE)
)
```

### Step 3: Build ATLAS Embedding Service

Create `atlas/embedding_service.py`:

```python
import torch
from transformers import AutoModel
from transformers.image_utils import load_image

class NemotronEmbedder:
    def __init__(self):
        self.model_name = "nvidia/llama-nemotron-embed-vl-1b-v2"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = AutoModel.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
            attn_implementation="flash_attention_2",
            device_map="auto"
        ).eval()
        # Text-only embedding (most common case for ATLAS)
        self.model.processor.p_max_length = 8192
        self.model.processor.max_input_tiles = 6
        self.model.processor.use_thumbnail = True

    def embed_texts(self, texts: list[str]) -> torch.Tensor:
        with torch.inference_mode():
            return self.model.encode_documents(texts=texts)

    def embed_query(self, query: str) -> torch.Tensor:
        with torch.inference_mode():
            return self.model.encode_queries([query])

    def embed_images(self, image_paths: list) -> torch.Tensor:
        images = [load_image(p) for p in image_paths]
        with torch.inference_mode():
            return self.model.encode_documents(images=images)

    def embed_multimodal(self, images: list, texts: list[str]) -> torch.Tensor:
        loaded = [load_image(p) for p in images]
        with torch.inference_mode():
            return self.model.encode_documents(images=loaded, texts=texts)
```

Service should be a singleton — load once at startup, reuse across all calls.

### Step 4: Build ATLAS Reranking Service

Create `atlas/reranking_service.py`:

```python
import torch
from transformers import AutoModel

class NemotronReranker:
    def __init__(self):
        self.model_name = "nvidia/llama-nemotron-rerank-vl-1b-v2"
        self.model = AutoModel.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
            device_map="auto"
        ).eval()

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """
        candidates: list of dicts with 'id', 'content', 'score' (ANN score)
        returns: candidates reordered by rerank score, with rerank_score added
        """
        texts = [c['content'] for c in candidates]
        with torch.inference_mode():
            scores = self.model.compute_score(query, texts)

        for candidate, score in zip(candidates, scores):
            candidate['rerank_score'] = float(score)

        return sorted(candidates, key=lambda x: x['rerank_score'], reverse=True)
```

### Step 5: Salience Write-Back (ATLAS Turns On)

After every rerank call, write scores back to Qdrant payload.
This is the moment JANATPMP infrastructure becomes ATLAS.

In `atlas/memory_service.py` or integrated into reranking service:

```python
def write_salience_back(self, collection: str, results: list[dict]):
    """
    After reranking, update Qdrant payloads with the rerank signal.
    High rerank scores → salience boost.
    Called after every search that goes through the reranker.
    """
    for result in results:
        point_id = result['id']
        rerank_score = result.get('rerank_score', 0.0)

        # Read current salience, apply boost, write back
        current = qdrant_client.retrieve(collection, [point_id])[0]
        current_salience = current.payload.get('salience', 0.5)

        # Weighted update — rerank score nudges salience, doesn't replace it
        new_salience = min(1.0, current_salience + (rerank_score * SALIENCE_BOOST_RATE))

        qdrant_client.set_payload(
            collection_name=collection,
            payload={'salience': new_salience, 'last_retrieved': datetime.utcnow().isoformat()},
            points=[point_id]
        )
```

`SALIENCE_BOOST_RATE` = start at 0.05. Tune after observing behavior.

### Step 6: Update Search Pipeline

All search calls in `services/` that hit Qdrant need to become two-stage:

```
1. ANN search (embedder) → top-k candidates (k=20 or configurable)
2. Reranker → reordered results → top-n returned (n=5 default)
3. Salience write-back → Qdrant payloads updated
```

Update `janatpmp:search` and `janatpmp:search_all` MCP tools to use new pipeline.
The MCP interface does not change — only the internals.

### Step 7: Fresh Embedding Pipeline

Run `embed_all_documents`, `embed_all_messages` with new embedder.
This time: GPU, bfloat16, flash-attention-2, 2048-dim.

Add progress visibility — at minimum a tqdm progress bar writing to stdout.
Estimated time with 5090: 8-20 minutes for full corpus.

Add checkpoint support (from ATLAS epic features already created):
- Record last successfully embedded ID
- On restart, skip already-embedded points
- Check point ID existence in Qdrant before re-embedding

### Step 8: Ollama KV Cache & GPU Hardening

Current state: GPU spikes to 95% during inference, crashes to 2% between turns.
KV cache is evicting. Context re-encodes from scratch each turn.

In Ollama configuration (typically `~/.ollama/config` or via modelfile):

```
# For primary chat model
num_ctx 32768        # full context window the model supports
num_keep 4096        # tokens to keep in KV cache between requests
num_gpu 999          # offload all layers to GPU (5090 has room)
```

Also ensure Ollama is running with CUDA and not falling back:
```bash
ollama run <model> --verbose
# Should show: GPU layers: N/N (all layers on GPU)
```

For Docker deployment — ensure Ollama container has GPU access:
```yaml
# docker-compose.yml
ollama:
  runtime: nvidia
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - CUDA_VISIBLE_DEVICES=0
```

Goal: model stays warm between requests. Context window persists.
Model switching without borking = models unload gracefully, KV cache managed per-model.

### Step 9: Create `atlas/` Directory Structure

R9 begins the physical separation of ATLAS from JANATPMP application code:

```
atlas/
  __init__.py
  embedding_service.py     ← Nemotron embedder (Step 3)
  reranking_service.py     ← Nemotron reranker (Step 4)
  memory_service.py        ← salience write-back, decay (Step 5)
  pipeline.py              ← orchestrates embed → rerank → write-back
  config.py                ← EMBEDDING_DIM=2048, SALIENCE_BOOST_RATE, etc.
```

This is the beginning of the Knots architecture. `atlas/` is the shared substrate
that future Knots (Admin, Chat, Projects, Knowledge) will all import from.

### Step 10: Validate & Test

- [ ] Embed 10 test documents, confirm 2048-dim vectors in Qdrant
- [ ] Run a search query, confirm reranker returns reordered results
- [ ] Check Qdrant payload — confirm `salience` and `last_retrieved` fields exist
- [ ] Run `janatpmp:search` MCP tool — confirm it works through new pipeline
- [ ] Check GPU utilization during embed run — should hold high, not spike/crash
- [ ] Check Ollama model stays warm between turns — context should persist

---

## Deferred to R10

- **Intel AI Boost NPU activation** — OpenVINO conversion of reranker for
  background NPU inference. Architectural vision: NPU as dedicated always-on
  embedding intake processor, GPU free for generation and reranking.
  Not needed now. 32GB VRAM has room. Build the right thing first.

- **Embed on Write** — automatic embedding on every MCP write operation.
  Infrastructure from ATLAS epic already defined. Depends on R9 pipeline being stable.

- **Memory Decay** — salience decreasing over time without retrieval reinforcement.
  Requires salience write-back (R9 Step 5) to be running and stable first.

- **Knots architecture** — splitting app.py into Admin/Chat/Projects/Knowledge Knots.
  `atlas/` directory created in R9 is the foundation. Full Knots separation is R10+.

---

## Architectural Notes (Permanent)

**Why not GGUF for the embedder:**
GGUF quantization degrades angular precision in the vector space. 2048-dimensional
embeddings derive their value from precise geometric relationships between vectors.
With 11GB VRAM headroom on a 5090, there is no pressure to accept quality loss.
Run bfloat16. The reranker is a more acceptable quantization target if pressure
ever arises — relative rankings tolerate noise better than geometric coordinates.

**Why the reranker score is a salience signal, not a sort key:**
A document that consistently scores high against diverse queries is genuinely
information-dense and contextually relevant. That's what salience is. Writing
this signal back transforms retrieval from a read operation into a write operation —
the system has an opinion about its own contents. This is the line between
information system and memory.

**NPU architectural vision (R10):**
Intel AI Boost as the dedicated embedding intake processor.
GPU handles generation + reranking.
Two accelerators, zero contention, true parallel operation.
The NPU becomes ATLAS's always-on sensory intake — everything that arrives
gets embedded immediately, continuously, without competing with inference.

---

## Definition of Done

- [ ] Qdrant collections recreated at 2048 dimensions
- [ ] Nemotron embedder running on GPU (bfloat16, flash-attention-2)
- [ ] Full corpus re-embedded successfully (documents + messages)
- [ ] Nemotron reranker integrated as second stage on all search calls
- [ ] Salience scores writing back to Qdrant payload after every rerank
- [ ] `atlas/` directory exists with embedding, reranking, memory services
- [ ] Ollama KV cache configured and persisting between turns
- [ ] MCP search tools working through new pipeline
- [ ] R9 branch merged to main
