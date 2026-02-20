"""ATLAS reranking service using NVIDIA Llama-Nemotron-Rerank-VL-1B-v2.

Cross-encoder reranker that scores query-document relevance. Designed as a
matched pair with the Nemotron VL embedder — benchmarked together as a pipeline.
"""

import logging

import torch
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoProcessor

from atlas.config import RERANKER_MODEL, GPU_MEMORY_FRACTION, MAX_SEQ_LENGTH
from atlas.embedding_service import _force_eager_attention

logger = logging.getLogger(__name__)

_reranker = None
_reranker_load_error = None


class NemotronReranker:
    """GPU-accelerated reranking service using Nemotron VL cross-encoder."""

    def __init__(self):
        self.model_name = RERANKER_MODEL
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning("CUDA not available — reranker running on CPU (slow)")
        elif not torch.cuda.memory_reserved(0):
            # First CUDA user in this process — set hard VRAM cap
            torch.cuda.set_per_process_memory_fraction(GPU_MEMORY_FRACTION)

        logger.info("Loading reranker model: %s on %s", self.model_name, self.device)

        # Same flash_attention_2 hardcoding fix as embedding_service.py
        config = AutoConfig.from_pretrained(self.model_name, trust_remote_code=True)
        if hasattr(config, "llm_config"):
            _force_eager_attention(config.llm_config)
        if hasattr(config, "vision_config"):
            _force_eager_attention(config.vision_config)

        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            config=config,
            dtype=torch.bfloat16,
            trust_remote_code=True,
            device_map="auto",
        ).eval()

        self.processor = AutoProcessor.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            rerank_max_length=MAX_SEQ_LENGTH,
        )
        logger.info("Reranker model loaded: %s", self.model_name)

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """Rerank candidates by cross-encoder relevance score.

        Args:
            query: The search query.
            candidates: List of dicts, each must have 'text' key with content.
                Other keys (id, score, metadata) are preserved.

        Returns:
            Candidates reordered by rerank_score (descending), with
            'rerank_score' field added to each dict.
        """
        if not candidates:
            return candidates

        # Build examples for cross-encoder (doc_image="" for text-only reranking)
        examples = [
            {"question": query, "doc_text": c.get("text", ""), "doc_image": ""}
            for c in candidates
        ]

        with torch.inference_mode():
            batch_dict = self.processor.process_queries_documents_crossencoder(examples)
            # Move to model device
            batch_dict = {k: v.to(self.model.device) if hasattr(v, "to") else v
                          for k, v in batch_dict.items()}
            outputs = self.model(**batch_dict, return_dict=True)
            logits = outputs.logits.squeeze(-1)
            scores = logits.float().tolist()

        # Handle single-item case (squeeze may return scalar)
        if isinstance(scores, float):
            scores = [scores]

        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = score

        return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)

    def unload(self):
        """Move model to CPU and free GPU VRAM."""
        if hasattr(self, "model") and self.model is not None:
            self.model.to("cpu")
            del self.model
            self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("Reranker unloaded from GPU")


def get_reranker() -> NemotronReranker:
    """Get or create the reranker instance.

    Loads on demand — the reranker is NOT kept resident. After each use,
    call release_reranker() to free ~3.4 GB of VRAM back for Ollama.
    Caches load errors to prevent retry spam.
    """
    global _reranker, _reranker_load_error
    if _reranker_load_error is not None:
        raise _reranker_load_error
    if _reranker is None or _reranker.model is None:
        try:
            _reranker = NemotronReranker()
        except Exception as e:
            _reranker_load_error = e
            logger.error("Reranker failed to load (cached — restart to retry): %s", e)
            raise
    return _reranker


def release_reranker():
    """Unload reranker from GPU after use. Recovers ~3.4 GB VRAM."""
    global _reranker
    if _reranker is not None:
        _reranker.unload()
        _reranker = None
