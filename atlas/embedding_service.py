"""ATLAS embedding service using NVIDIA Llama-Nemotron-Embed-VL-1B-v2.

Multimodal embedder (text + image) running on GPU with bfloat16 precision.
Singleton pattern — model loads lazily on first use, cached for process lifetime.
"""

import logging

import torch
from transformers import AutoConfig, AutoModel

from atlas.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_embedder = None
_embedder_load_error = None


def _force_eager_attention(config):
    """Lock a config's attention implementation to 'eager'.

    The Nemotron VL model's custom code hardcodes flash_attention_2 on the
    llm_config. In transformers 4.47+, PretrainedConfig._attn_implementation
    is a property backed by _attn_implementation_internal. We override the
    property on a subclass to always return 'eager' and silently ignore writes.
    """
    cls = type(config)

    # Don't re-patch an already-patched instance
    if getattr(cls, "_attn_locked_eager", False):
        return

    # Set the internal backing attribute directly (belt)
    config._attn_implementation_internal = "eager"

    # Override the property to lock reads to 'eager' and ignore all writes (suspenders)
    patched_cls = type(
        cls.__name__ + "Eager", (cls,),
        {
            "_attn_locked_eager": True,
            "_attn_implementation": property(
                lambda self: "eager",
                lambda self, v: None,  # silently ignore writes
            ),
        },
    )
    config.__class__ = patched_cls
    config._attn_implementation_autoset = False


class NemotronEmbedder:
    """GPU-accelerated embedding service using Nemotron VL embedder."""

    def __init__(self):
        self.model_name = EMBEDDING_MODEL
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning("CUDA not available — embedder running on CPU (slow)")

        logger.info("Loading embedding model: %s on %s", self.model_name, self.device)

        # The model's custom code (modeling_llama_nemotron_vl.py:291) hardcodes:
        #   config.llm_config._attn_implementation = "flash_attention_2"
        # right before constructing the inner LLM. This overrides any config
        # patching we do. Workaround: make _attn_implementation a property that
        # locks to "eager" and ignores writes of "flash_attention_2".
        config = AutoConfig.from_pretrained(self.model_name, trust_remote_code=True)
        # Only patch sub-configs — patching the top-level config triggers a
        # config_class registration mismatch in AutoModel.from_pretrained().
        # The model code only hardcodes flash_attention_2 on llm_config anyway.
        if hasattr(config, "llm_config"):
            _force_eager_attention(config.llm_config)
        if hasattr(config, "vision_config"):
            _force_eager_attention(config.vision_config)

        self.model = AutoModel.from_pretrained(
            self.model_name,
            config=config,
            dtype=torch.bfloat16,
            trust_remote_code=True,
            device_map="auto",
        ).eval()

        # Configure processor for text embedding
        self.model.processor.p_max_length = 8192
        self.model.processor.max_input_tiles = 6
        self.model.processor.use_thumbnail = True
        logger.info("Embedding model loaded: %s", self.model_name)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed document passages for storage (asymmetric document encoding).

        Args:
            texts: List of text passages to embed.

        Returns:
            List of embedding vectors (2048-dim each).
        """
        with torch.inference_mode():
            embeddings = self.model.encode_documents(texts=texts)
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query for retrieval (asymmetric query encoding).

        Args:
            query: The search query text.

        Returns:
            Single embedding vector (2048-dim).
        """
        with torch.inference_mode():
            embeddings = self.model.encode_queries([query])
        return embeddings[0].tolist()


def get_embedder() -> NemotronEmbedder:
    """Get or create the singleton embedder instance.

    Caches load errors to prevent retry spam — if model fails to load,
    subsequent calls raise immediately instead of re-attempting.
    Restart the process to retry after fixing the environment.
    """
    global _embedder, _embedder_load_error
    if _embedder_load_error is not None:
        raise _embedder_load_error
    if _embedder is None:
        try:
            _embedder = NemotronEmbedder()
        except Exception as e:
            _embedder_load_error = e
            logger.error("Embedder failed to load (cached — restart to retry): %s", e)
            raise
    return _embedder
