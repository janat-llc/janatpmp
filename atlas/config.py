"""ATLAS configuration constants."""

# --- Model identifiers ---
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"
RERANKER_MODEL = "nvidia/llama-nemotron-rerank-vl-1b-v2"

# --- Vector dimensions ---
EMBEDDING_DIM = 2048

# --- VRAM budget (RTX 5090, 32 GB shared with Ollama) ---
# Ollama is capped at 70% (~22.4 GB) via OLLAMA_GPU_MEMORY_FRACTION.
# That covers 18.2 GB model weights + ~4 GB KV cache for 16K in / 8K out.
# PyTorch (embedder + reranker) gets 25% (~8 GB). 5% headroom for system.
# Peak overlap is minimal: bulk embed runs when not chatting, search queries are tiny.
GPU_MEMORY_FRACTION = 0.25
# Max sequence length in tokens. Tokenizer truncates beyond this.
# 2048 tokens × batch 4 × 24 layers × 16 heads = ~3 GB attention (eager).
# Total peak with model weights (~3.4 GB): ~7.5 GB — well within 12.8 GB cap.
MAX_SEQ_LENGTH = 2048
# Conservative char limit for pre-tokenizer filtering. ~3 chars/token average
# ensures we rarely hit the tokenizer truncation (which is the hard stop).
MAX_TEXT_CHARS = 6_000

# --- Salience parameters ---
SALIENCE_BOOST_RATE = 0.05  # How much a rerank score nudges salience per retrieval
SALIENCE_DEFAULT = 0.5      # Starting salience for new entries

# --- Reranking parameters ---
RERANK_CANDIDATES = 20  # ANN top-k before reranking
RERANK_RETURN = 5        # Top-n returned after reranking
