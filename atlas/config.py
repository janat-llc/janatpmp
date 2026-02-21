"""ATLAS configuration constants."""

# --- Service URLs (Docker internal DNS) ---
# Embedding runs through Ollama's OpenAI-compatible API
OLLAMA_EMBED_URL = "http://ollama:11434"
# Reranking runs through dedicated vLLM sidecar
VLLM_RERANK_URL = "http://janatpmp-vllm-rerank:8000"

# --- Model identifiers ---
EMBEDDING_MODEL = "hf.co/Qwen/Qwen3-Embedding-4B-GGUF:Q4_K_M"
RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"

# --- Vector dimensions ---
EMBEDDING_DIM = 2560  # Qwen3-Embedding-4B max (Matryoshka: 128-2560)

# --- Text limits ---
MAX_TEXT_CHARS = 20_000  # Pre-filter before sending to embed API

# --- Salience parameters ---
SALIENCE_BOOST_RATE = 0.05  # How much a rerank score nudges salience per retrieval
SALIENCE_DEFAULT = 0.5      # Starting salience for new entries

# --- Reranking parameters ---
RERANK_CANDIDATES = 20  # ANN top-k before reranking
RERANK_RETURN = 5        # Top-n returned after reranking

# --- Qwen3 asymmetric query instruction ---
QUERY_INSTRUCTION = (
    "Instruct: Given a query, retrieve relevant documents "
    "that answer the query\nQuery: "
)
