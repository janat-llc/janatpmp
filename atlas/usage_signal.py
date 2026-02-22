"""ATLAS usage signal — estimate how much the model actually used each RAG hit.

Compares keywords from retrieved chunks against the model's response to produce
a 0.0-1.0 usage score per hit. This drives Salience Layer 2: chunks the model
draws from get boosted, chunks retrieved but ignored get decayed.
"""

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Words too common to be meaningful signals
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "that", "this",
    "these", "those", "it", "its", "i", "me", "my", "we", "our", "you",
    "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "what", "which", "who", "whom", "whose",
})

_MIN_WORD_LEN = 3


def _extract_keywords(text: str, top_n: int = 20) -> set[str]:
    """Extract meaningful keywords from text via TF filtering."""
    words = re.findall(r"[a-z][a-z0-9_]+", text.lower())
    filtered = [w for w in words if len(w) >= _MIN_WORD_LEN and w not in _STOPWORDS]
    counts = Counter(filtered)
    return {w for w, _ in counts.most_common(top_n)}


def compute_usage_signal(rag_scores: list[dict], model_response: str) -> list[dict]:
    """For each RAG hit, estimate how much the model actually used it.

    Heuristic: extract keywords from each chunk's text (stored in title field
    of the score dict), count how many appear in the model response. Normalize
    to 0.0-1.0.

    Args:
        rag_scores: List of per-hit score dicts from RAG metrics. Each has
            source, title, rerank_score, salience, ann_score.
        model_response: The model's clean response text.

    Returns:
        List of {source, title, rerank_score, salience, usage_score} dicts.
        Empty list if no scores or empty response.
    """
    if not rag_scores or not model_response:
        return []

    response_keywords = _extract_keywords(model_response, top_n=50)
    if not response_keywords:
        return []

    results = []
    for hit in rag_scores:
        title = hit.get("title", "")
        source = hit.get("source", "unknown")
        if not title:
            results.append({**hit, "usage_score": 0.0})
            continue

        hit_keywords = _extract_keywords(title, top_n=15)
        if not hit_keywords:
            results.append({**hit, "usage_score": 0.0})
            continue

        overlap = hit_keywords & response_keywords
        usage_score = min(1.0, len(overlap) / max(len(hit_keywords), 1))

        results.append({**hit, "usage_score": round(usage_score, 3)})

    return results
