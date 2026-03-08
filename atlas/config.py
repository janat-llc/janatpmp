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
EMBEDDING_MODEL = "qwen3-embedding-4b-cpu"  # qwen3-embedding:4b on CPU, num_ctx 2048. Zero VRAM — Janus gets full GPU
RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"  # DECOMMISSIONED — kept for import compat

# --- Vector dimensions ---
EMBEDDING_DIM = 2560  # Qwen3-Embedding-4B (2560-dim, upgraded from 0.6B/1024 on 2026-03-08)

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

# --- RAG scoring pipeline (R49: replaces decommissioned reranker) ---
RAG_ANN_CANDIDATES = 30   # ANN candidates fetched per collection before composite scoring
RAG_RETURN_TOP = 10        # Max results after composite scoring (before chat.py filtering)
RAG_MIN_SCORE = 0.4        # Minimum composite score to include in results

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

# --- Semantic Edge Generation (R20: Graph Awakening) ---
SEMANTIC_EDGE_SCORE_THRESHOLD = 0.55  # Min mean similarity for SIMILAR_TO edge
SEMANTIC_EDGE_MAX_NEIGHBORS = 5       # Max edges per conversation
SEMANTIC_EDGE_SEARCH_CANDIDATES = 30  # ANN results before grouping
SEMANTIC_EDGE_REPR_CHUNKS = 3         # Messages used for representative text
SEMANTIC_EDGE_REPR_MAX_CHARS = 500    # Max chars per message in repr text

# --- Graph-Aware RAG Ranking (R21: Strange Loop) ---
GRAPH_BOOST_FACTOR = 0.1         # Score bonus = edge_score * GRAPH_BOOST_FACTOR
GRAPH_TOPIC_CONVERSATIONS = 3    # Top-N source conversations to seed neighborhood
GRAPH_NEIGHBORHOOD_HOPS = 1      # SIMILAR_TO traversal depth (1 = direct neighbors only)

# --- Dream Synthesis (R24) ---
DREAM_MIN_QUALITY = 0.7          # Minimum quality_score for cluster candidates
DREAM_MAX_CLUSTERS = 3           # Max clusters to synthesize per cycle
DREAM_CLUSTER_MIN_SIZE = 3       # Minimum messages to form a valid cluster
DREAM_CLUSTER_MAX_SIZE = 6       # Maximum messages per cluster
DREAM_SIMILARITY_THRESHOLD = 0.6 # Qdrant cosine threshold for cross-conv matches
DREAM_CYCLE_INTERVAL = 5         # Dream every Nth slumber cycle
DREAM_TEMPERATURE = 0.7          # Gemini temperature (creative for synthesis)

# --- Slumber Graph Weave (R27) ---
WEAVE_CYCLE_INTERVAL = 5         # Weave every Nth slumber cycle (same as Dream)

# --- Temporal Decay (R28: Temporal Gravity) ---
TEMPORAL_DECAY_HALF_LIFE = 14    # Days until temporal bonus is halved
TEMPORAL_DECAY_FLOOR = 0.15      # Minimum multiplier (old content never fully suppressed)

# --- Entity Extraction (R29: The Troubadour) ---
EXTRACTION_BATCH_SIZE = 10          # Messages per Slumber cycle
EXTRACTION_MIN_QUALITY = 0.3        # Minimum quality_score to attempt extraction
EXTRACTION_TEMPERATURE = 0.2        # Low temperature for consistent extraction
EXTRACTION_MAX_PER_MESSAGE = 8      # Max entities from a single message
EXTRACTION_CYCLE_INTERVAL = 3       # Extract every Nth slumber cycle

# --- Entity-Aware RAG Routing (R30) ---
ENTITY_CONFIDENCE_THRESHOLD = 0.4    # Minimum confidence to include entity
ENTITY_HIGH_CONFIDENCE = 0.7         # Threshold to downgrade RAG depth
ENTITY_MAX_MATCHES = 3               # Maximum entities per query
ENTITY_CONTEXT_BUDGET = 2000         # Max chars for entity context block
ENTITY_MAX_SNIPPETS = 3              # Max source snippets per entity

# --- Co-Occurrence Linking (R31: The Web) ---
COOCCURRENCE_CYCLE_INTERVAL = 3      # Link every Nth slumber cycle
COOCCURRENCE_BATCH_SIZE = 100        # Max entity pairs per cycle
COOCCURRENCE_MIN_SHARED = 2          # Min shared messages to create edge

# --- Entity Salience Decay (R31: The Web) ---
ENTITY_DECAY_HALF_LIFE = 45          # Days until entity salience halves
ENTITY_DECAY_FLOOR = 0.15            # Entities never fully disappear
ENTITY_DECAY_BATCH_SIZE = 50         # Entities per cycle
ENTITY_DECAY_CYCLE_INTERVAL = 5      # Decay every Nth slumber cycle

# --- Register Mining (R32: The Mirror) ---
REGISTER_MINING_CYCLE_INTERVAL = 5   # Mine every Nth slumber cycle
REGISTER_MINING_BATCH_SIZE = 10      # Messages to check per cycle
REGISTER_MINING_MIN_QUALITY = 0.6    # Min quality_score to evaluate

# --- Entity Dedup (R47: Entity Merge Infrastructure) ---
ENTITY_DEDUP_CYCLE_INTERVAL = 5     # Dedup every Nth slumber cycle
ENTITY_DEDUP_BATCH_SIZE = 50        # Max merges per cycle

# --- Pre-Cognition (R25) ---
PRECOGNITION_TIMEOUT_MS = 3000   # Max wait for Gemini pre-pass (ms)
PRECOGNITION_WEIGHT_MIN = 0.0    # Floor for layer weights
PRECOGNITION_WEIGHT_MAX = 2.0    # Ceiling for layer weights
PRECOGNITION_TEMPERATURE = 0.1   # Low temp — consistent decisions

# --- Data Foundation (R26: The Waking Mind) ---
BACKFILL_EMBEDDING_BATCH_SIZE = 50    # Chunks per embedding batch (reduces Qdrant write pressure)
BACKFILL_BATCH_SLEEP_SECONDS = 0.5    # Pause between batches
