"""ATLAS configuration constants.

Service URLs, model identifiers, vector dimensions, salience/rerank parameters,
chunking parameters, and temporal engine defaults.
"""

# --- Service URLs (Docker internal DNS) ---
# Embedding runs through Ollama's OpenAI-compatible API
OLLAMA_EMBED_URL = "http://ollama:11434"
# Reranking via vLLM sidecar (DECOMMISSIONED — Gemma migration, kept for import compat)
VLLM_RERANK_URL = "http://janatpmp-vllm-rerank:8000"  # Unused — rerank defaults to False
# Neo4j graph database
NEO4J_URI = "bolt://janatpmp-neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "janatpmp_graph"
NEO4J_DATABASE = "neo4j"

# --- CDC consumer ---
CDC_POLL_INTERVAL = 5    # Seconds between CDC polling cycles
CDC_BATCH_SIZE = 50      # Max rows per poll

# --- Model identifiers ---
EMBEDDING_MODEL = "qwen3-embedding:0.6b"
RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"  # DECOMMISSIONED — kept for import compat

# --- Vector dimensions ---
EMBEDDING_DIM = 1024  # Qwen3-Embedding-0.6B (1024-dim, Matryoshka support for smaller dims)

# --- Text limits ---
MAX_TEXT_CHARS = 20_000  # Pre-filter before sending to embed API

# --- Chunking parameters ---
CHUNK_MAX_CHARS = 2500       # Target max chunk size (~600 tokens for Qwen3)
CHUNK_MIN_CHARS = 200        # Floor — avoid tiny fragment vectors
CHUNK_OVERLAP_CHARS = 200    # Overlap between consecutive chunks
CHUNK_THRESHOLD = 3000       # Messages/docs under this stay single-vector

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

# --- Temporal Engine defaults (R17) ---
LOCATION_LAT = 46.8290       # Fargo, ND (Mat's house)
LOCATION_LON = -96.8540
LOCATION_NAME = "3351 Washington Street South, Fargo, ND 58104"
LOCATION_TZ = "America/Chicago"

# --- Query instruction (Qwen3-Embedding asymmetric query prefix) ---
QUERY_INSTRUCTION = (
    "Instruct: Given a query, retrieve relevant documents "
    "that answer the query\nQuery: "
)
