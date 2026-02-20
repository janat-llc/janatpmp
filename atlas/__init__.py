"""ATLAS — Adaptive Topological Lattice for Associative Synthesis.

JANATPMP stores and retrieves. ATLAS remembers.

This package provides the model infrastructure for ATLAS:
- Embedding service (Nemotron VL embedder, GPU, bfloat16)
- Reranking service (Nemotron VL reranker, GPU, bfloat16)
- Memory service (salience write-back to Qdrant)
- Pipeline orchestrator (embed → search → rerank → salience)
"""
