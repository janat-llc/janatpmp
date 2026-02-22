# JANAT Model Stack — Ollama Modelfiles
## Architecture Overview

All four sidecar models share **qwen3:1.7b** base weights. Ollama deduplicates — one copy in VRAM (~1.5GB Q4), four named endpoints with different system prompts and parameters.

Janus (qwen3-vl:8b) receives NO static system prompt. Its framing is generated fresh every turn by the Synthesizer.

## Pipeline Flow

```
User Message
    │
    ▼
┌─────────────────┐
│  CLASSIFIER      │  Route: full | light | passthrough
│  temp=0.0        │  ~50-100ms
│  ctx=2048        │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
passthrough  full/light
    │         │
    │    ┌────▼────────┐
    │    │  SCORER      │  Salience: novelty, relevance, emotional, predictive
    │    │  temp=0.1    │  Intent, complexity, retrieval hint
    │    │  ctx=4096    │
    │    └────┬────────┘
    │         │
    │    [ RAG Pipeline ]  ANN search → Reranker → Graph neighbors
    │         │             (guided by scorer's retrieval_hint)
    │         │
    │    ┌────▼────────────┐
    │    │  SYNTHESIZER     │  Outputs: dynamic system prompt + context summary
    │    │  temp=0.3        │  Decides WHO Janus needs to be this turn
    │    │  ctx=8192        │
    │    └────┬────────────┘
    │         │
    └────┬────┘
         │
    ┌────▼──────────┐
    │  JANUS         │  qwen3-vl:8b — Primary inference
    │  (no static    │  Receives: dynamic system prompt + synthesized context
    │   system       │            + user message + conversation history
    │   prompt)      │
    └────┬──────────┘
         │
         ▼
    Response → Pipeline Trace recorded → Post-turn synthesis
         │
    [ SLUMBER CYCLE — async, batched ]
         │
    ┌────▼────────────┐
    │  CONSOLIDATOR    │  Merge, generalize, resolve, prune
    │  temp=0.6        │  Runs every N days or on-demand
    │  ctx=16384       │
    └─────────────────┘
```

## VRAM Budget (RTX 5090, 32GB)

| Model               | Role         | VRAM   | Notes                          |
|---------------------|-------------|--------|--------------------------------|
| qwen3-vl:8b         | Janus        | ~6.0GB | Primary inference              |
| qwen3:1.7b          | All sidecars | ~1.5GB | Shared weights, 4 endpoints    |
| qwen3-embedding:4b  | Embeddings   | ~2.5GB | 2560-dim vectors               |
| qwen3-reranker:0.6b | Reranker     | ~1.7GB | vLLM sidecar                   |
| **Total**           |              | **~12GB** | **~20GB headroom**          |

## Setup Commands

Pull the base models first (if not already present):
```bash
ollama pull qwen3:1.7b
ollama pull qwen3-vl:8b
```

Register the sidecar models from the JANATPMP root:
```bash
ollama create janat-classifier -f models/janat-classifier.Modelfile
ollama create janat-scorer -f models/janat-scorer.Modelfile
ollama create janat-synthesizer -f models/janat-synthesizer.Modelfile
ollama create janat-consolidator -f models/janat-consolidator.Modelfile
```

Verify they exist:
```bash
ollama list | grep janat
```

You should see all four models listed, each showing qwen3:1.7b as the base.

## Testing Individual Models

```bash
# Test classifier
echo "Hey, how's it going?" | ollama run janat-classifier

# Test scorer
echo "I've been thinking about the photonic substrate timeline and whether 2030 is realistic given the current funding situation" | ollama run janat-scorer

# Test synthesizer (needs structured input in production, but raw text works for smoke test)
echo "USER_MESSAGE: What's the status of R13?\nRETRIEVED_CONTEXT: R13 phases A-C shipped in 10 minutes. Phase D in progress. Triple-write pipeline with Neo4j." | ollama run janat-synthesizer
```

## Pipeline Trace

Every turn records the full journey in the database:
1. Classifier output (route, intent, domain_hint)
2. Scorer output (salience dimensions, retrieval hint)
3. RAG results (candidates, reranked, rejected, scores)
4. Synthesizer output (dynamic system prompt, context summary, routing)
5. Final prompt sent to Janus (exact text)
6. Janus reasoning tokens (if available)
7. Janus response
8. Latency at each stage

This is not yet implemented in schema — see R14 planning for the pipeline_traces table.

## Design Notes

- **`/no_think`** in system prompts disables Qwen3's chain-of-thought mode. Sidecars need speed and structured output, not reasoning tokens.
- **Temperature gradient**: Classifier (0.0) → Scorer (0.1) → Synthesizer (0.3) → Consolidator (0.6). Determinism where we need precision, creativity where we need pattern-finding.
- **Context windows** scale with role: Classifier (2K) → Scorer (4K) → Synthesizer (8K) → Consolidator (16K). Smaller windows = faster inference for quick decisions.
- **Janus has NO Modelfile**. It gets `ollama run qwen3-vl:8b` with the system prompt injected at call time by the pipeline. This is intentional — Janus's identity emerges from context, not configuration.
