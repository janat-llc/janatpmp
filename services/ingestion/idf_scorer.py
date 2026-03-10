"""IDF-based batch stopword detection for entity extraction (R52).

Builds a document-frequency table from a batch of documents,
identifies terms in >50% of docs as corpus noise, and stores
them transiently in settings so entity_extraction.py can
exclude them from Gemini prompts.

Usage:
    from services.ingestion.idf_scorer import (
        build_batch_df_table, get_batch_stopwords, set_stopwords, clear_stopwords
    )
    docs = ingest_directory(directory, exclude_patterns=[...])
    df = build_batch_df_table(docs)
    stopwords = get_batch_stopwords(df, len(docs), threshold=0.5)
    set_stopwords(stopwords)
    # ... run ingestion ...
    clear_stopwords()
"""

import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)

_STOPWORDS_KEY = "batch_extraction_stopwords"

# English function words — always excluded from DF counting
_BASE_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "that", "this", "it", "i", "we", "you",
    "he", "she", "they",
})


def _tokenize(text: str) -> list[str]:
    """Extract lowercase alpha tokens of 3+ chars, excluding base stopwords."""
    return [
        t for t in re.findall(r"[a-z]{3,}", text.lower())
        if t not in _BASE_STOPWORDS
    ]


def build_batch_df_table(documents: list[dict]) -> dict[str, int]:
    """Count how many documents each term appears in.

    Args:
        documents: List of document dicts with 'content' key.

    Returns:
        Dict mapping term -> document count.
    """
    df: Counter = Counter()
    for doc in documents:
        content = doc.get("content", "") or ""
        terms = set(_tokenize(content))  # set: count once per document
        df.update(terms)
    return dict(df)


def get_batch_stopwords(
    df_table: dict[str, int],
    total_docs: int,
    threshold: float = 0.5,
    min_docs: int = 5,
) -> list[str]:
    """Return terms appearing in more than threshold fraction of documents.

    Args:
        df_table: Term -> doc count mapping from build_batch_df_table().
        total_docs: Total number of documents in batch.
        threshold: Fraction threshold (default 0.5 = appears in >50% of docs).
        min_docs: Minimum absolute count to qualify (avoids false positives on tiny batches).

    Returns:
        Sorted list of high-frequency terms to exclude from entity extraction.
    """
    cutoff = max(min_docs, int(total_docs * threshold))
    stopwords = sorted(term for term, count in df_table.items() if count >= cutoff)
    logger.info(
        "IDF: %d terms in >%.0f%% of %d docs → batch stopwords",
        len(stopwords), threshold * 100, total_docs,
    )
    return stopwords


def set_stopwords(stopwords: list[str]) -> None:
    """Persist batch stopwords to settings for entity extraction to read.

    Args:
        stopwords: List of terms to suppress in Gemini extraction prompts.
    """
    from services.settings import set_setting
    value = ",".join(stopwords[:500])  # cap at 500 terms for prompt safety
    set_setting(_STOPWORDS_KEY, value)
    logger.info("IDF: stored %d batch stopwords in settings", len(stopwords))


def clear_stopwords() -> None:
    """Remove batch stopwords from settings (call after extraction pass closes)."""
    from services.settings import set_setting
    set_setting(_STOPWORDS_KEY, "")
    logger.info("IDF: batch stopwords cleared")


def get_active_stopwords() -> list[str]:
    """Read current batch stopwords from settings.

    Returns:
        List of suppressed terms, or empty list if none set.
    """
    from services.settings import get_setting
    value = get_setting(_STOPWORDS_KEY) or ""
    if not value.strip():
        return []
    return [t for t in value.split(",") if t.strip()]
