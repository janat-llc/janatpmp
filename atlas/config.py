"""ATLAS configuration constants."""

# --- Service URLs (Docker internal DNS) ---
# Embedding runs through Ollama's OpenAI-compatible API
OLLAMA_EMBED_URL = "http://ollama:11434"
# Reranking runs through dedicated vLLM sidecar
VLLM_RERANK_URL = "http://janatpmp-vllm-rerank:8000"
# Neo4j graph database
NEO4J_URI = "bolt://janatpmp-neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "janatpmp_graph"
NEO4J_DATABASE = "neo4j"

# --- CDC consumer ---
CDC_POLL_INTERVAL = 5    # Seconds between CDC polling cycles
CDC_BATCH_SIZE = 50      # Max rows per poll

# --- Model identifiers ---
EMBEDDING_MODEL = "qwen3-embedding:0.6b-compact"
RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"

# --- Vector dimensions ---
EMBEDDING_DIM = 1024  # Qwen3-Embedding-0.6B (Matryoshka: 128-2048, using 1024)

# --- Text limits ---
MAX_TEXT_CHARS = 20_000  # Pre-filter before sending to embed API

# --- Salience parameters ---
SALIENCE_BOOST_RATE = 0.05   # How much a rerank score nudges salience per retrieval
SALIENCE_DEFAULT = 0.5       # Starting salience for new entries
SALIENCE_USAGE_RATE = 0.03   # Boost per usage signal (softer than retrieval boost)
SALIENCE_DECAY_RATE = 0.01   # Decay for retrieved-but-unused chunks

# --- RAG retrieval ---
RAG_MAX_CHUNKS_DEFAULT = 10  # Default max chunks injected (tunable via settings DB)

# --- Reranking parameters ---
RERANK_CANDIDATES = 20  # ANN top-k before reranking
RERANK_RETURN = 5        # Top-n returned after reranking

# --- Qwen3 asymmetric query instruction ---
QUERY_INSTRUCTION = (
    "Instruct: Given a query, retrieve relevant documents "
    "that answer the query\nQuery: "
)
