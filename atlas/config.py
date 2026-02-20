"""ATLAS configuration constants."""

# --- Model identifiers ---
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"
RERANKER_MODEL = "nvidia/llama-nemotron-rerank-vl-1b-v2"

# --- Vector dimensions ---
EMBEDDING_DIM = 2048

# --- Salience parameters ---
SALIENCE_BOOST_RATE = 0.05  # How much a rerank score nudges salience per retrieval
SALIENCE_DEFAULT = 0.5      # Starting salience for new entries

# --- Reranking parameters ---
RERANK_CANDIDATES = 20  # ANN top-k before reranking
RERANK_RETURN = 5        # Top-n returned after reranking
