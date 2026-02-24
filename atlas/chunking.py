"""ATLAS chunking engine — split long texts into focused semantic chunks.

Paragraph-based chunking with character limits. Uses natural text boundaries
(paragraph, sentence) before falling back to hard character splits.

Short texts (under threshold) return a single chunk — backward compatible.
"""

import re
import logging

from atlas.config import (
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    CHUNK_OVERLAP_CHARS,
    CHUNK_THRESHOLD,
)

logger = logging.getLogger(__name__)


def needs_chunking(text: str, threshold: int = CHUNK_THRESHOLD) -> bool:
    """Check if text is long enough to benefit from chunking.

    Args:
        text: Source text to evaluate.
        threshold: Character count above which chunking is applied.

    Returns:
        True if text exceeds threshold.
    """
    return len(text) > threshold


def chunk_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
    min_chars: int = CHUNK_MIN_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[dict]:
    """Split text into focused chunks with overlap.

    Split strategy (in order of preference):
    1. Paragraph boundaries (\\n\\n)
    2. Sentence boundaries (. followed by space/newline)
    3. Hard character split (last resort)

    Args:
        text: Source text to chunk.
        max_chars: Target maximum chunk size in characters.
        min_chars: Minimum chunk size — fragments smaller than this are
            merged with the previous chunk.
        overlap_chars: Character overlap between consecutive chunks.

    Returns:
        List of dicts: {index, text, char_start, char_end, position}.
        position is 'only' (no chunking needed), 'first', 'middle', or 'last'.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_chars:
        return [{"index": 0, "text": text, "char_start": 0,
                 "char_end": len(text), "position": "only"}]

    # --- Split into segments at natural boundaries ---
    segments = _split_paragraphs(text, max_chars)

    # --- Merge small trailing segments ---
    merged = []
    for seg in segments:
        if merged and len(seg) < min_chars:
            merged[-1] += "\n\n" + seg
        else:
            merged.append(seg)
    segments = merged

    # --- Re-split any segments still over max_chars ---
    final_segments = []
    for seg in segments:
        if len(seg) <= max_chars:
            final_segments.append(seg)
        else:
            final_segments.extend(_split_sentences(seg, max_chars, min_chars))
    segments = final_segments

    # --- Apply overlap ---
    chunks = _apply_overlap(text, segments, overlap_chars)

    # --- Assign positions ---
    total = len(chunks)
    if total == 1:
        chunks[0]["position"] = "only"
    else:
        for i, chunk in enumerate(chunks):
            if i == 0:
                chunk["position"] = "first"
            elif i == total - 1:
                chunk["position"] = "last"
            else:
                chunk["position"] = "middle"

    return chunks


def chunk_message(
    user_prompt: str,
    model_response: str,
    max_chars: int = CHUNK_MAX_CHARS,
    min_chars: int = CHUNK_MIN_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
    threshold: int = CHUNK_THRESHOLD,
) -> list[dict]:
    """Chunk a message's combined Q+A text.

    Short messages (under threshold) return a single chunk with the full
    Q+A text and position='only'. Long messages chunk the response portion,
    prepending a condensed question as context to each chunk.

    Args:
        user_prompt: The user's message text.
        model_response: The model's response text.
        max_chars: Target maximum chunk size.
        min_chars: Minimum chunk size.
        overlap_chars: Overlap between consecutive chunks.
        threshold: Total text length below which no chunking occurs.

    Returns:
        List of chunk dicts: {index, text, char_start, char_end, position}.
    """
    combined = f"Q: {user_prompt}\nA: {model_response}"

    if not needs_chunking(combined, threshold):
        return [{"index": 0, "text": combined, "char_start": 0,
                 "char_end": len(combined), "position": "only"}]

    # For long messages, chunk the response portion and prepend question context
    q_context = ""
    if user_prompt:
        q_summary = user_prompt[:150].strip()
        if len(user_prompt) > 150:
            q_summary += "..."
        q_context = f"Q: {q_summary}\nA: "

    # Reserve space for the question prefix in each chunk
    effective_max = max_chars - len(q_context) if q_context else max_chars
    effective_max = max(effective_max, min_chars * 2)  # Safety floor

    response_chunks = chunk_text(
        model_response,
        max_chars=effective_max,
        min_chars=min_chars,
        overlap_chars=overlap_chars,
    )

    # Prepend question context and adjust char offsets
    q_prefix_len = len("Q: ") + len(user_prompt) + len("\nA: ")
    result = []
    for chunk in response_chunks:
        result.append({
            "index": chunk["index"],
            "text": q_context + chunk["text"] if q_context else chunk["text"],
            "char_start": q_prefix_len + chunk["char_start"],
            "char_end": q_prefix_len + chunk["char_end"],
            "position": chunk["position"],
        })

    return result


def chunk_document(
    content: str,
    title: str = "",
    max_chars: int = CHUNK_MAX_CHARS,
    min_chars: int = CHUNK_MIN_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
    threshold: int = CHUNK_THRESHOLD,
) -> list[dict]:
    """Chunk a document's content text.

    Short documents return a single chunk. Long documents are split at
    paragraph/sentence boundaries. Title is prepended to each chunk for
    embedding context.

    Args:
        content: Document content text.
        title: Document title (prepended to each chunk for context).
        max_chars: Target maximum chunk size.
        min_chars: Minimum chunk size.
        overlap_chars: Overlap between consecutive chunks.
        threshold: Content length below which no chunking occurs.

    Returns:
        List of chunk dicts: {index, text, char_start, char_end, position}.
    """
    if not content or not content.strip():
        return []

    if not needs_chunking(content, threshold):
        text = f"{title}\n{content}" if title else content
        return [{"index": 0, "text": text, "char_start": 0,
                 "char_end": len(content), "position": "only"}]

    # Reserve space for title prefix
    title_prefix = f"{title}\n" if title else ""
    effective_max = max_chars - len(title_prefix) if title_prefix else max_chars
    effective_max = max(effective_max, min_chars * 2)

    content_chunks = chunk_text(
        content,
        max_chars=effective_max,
        min_chars=min_chars,
        overlap_chars=overlap_chars,
    )

    result = []
    for chunk in content_chunks:
        result.append({
            "index": chunk["index"],
            "text": title_prefix + chunk["text"] if title_prefix else chunk["text"],
            "char_start": chunk["char_start"],
            "char_end": chunk["char_end"],
            "position": chunk["position"],
        })

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_paragraphs(text: str, max_chars: int) -> list[str]:
    """Split text at paragraph boundaries (\n\n), accumulating until max_chars."""
    paragraphs = re.split(r"\n\n+", text)
    segments = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        candidate = current + ("\n\n" + para if current else para)
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                segments.append(current)
            current = para

    if current:
        segments.append(current)

    return segments


def _split_sentences(text: str, max_chars: int, min_chars: int) -> list[str]:
    """Split text at sentence boundaries when paragraph splitting isn't enough."""
    # Match sentence endings: period/question/exclamation followed by space or newline
    sentences = re.split(r"(?<=[.!?])\s+", text)
    segments = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        candidate = current + (" " + sent if current else sent)
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                segments.append(current)
            # If a single sentence exceeds max_chars, hard-split it
            if len(sent) > max_chars:
                segments.extend(_hard_split(sent, max_chars))
                current = ""
            else:
                current = sent

    if current:
        if segments and len(current) < min_chars:
            segments[-1] += " " + current
        else:
            segments.append(current)

    return segments


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last-resort: split at max_chars boundary (word-aligned when possible)."""
    segments = []
    remaining = text

    while len(remaining) > max_chars:
        # Try to break at a word boundary
        split_at = remaining.rfind(" ", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars  # No good word boundary, hard cut
        segments.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        segments.append(remaining)

    return segments


def _apply_overlap(
    original_text: str,
    segments: list[str],
    overlap_chars: int,
) -> list[dict]:
    """Build chunk dicts with overlap and char offsets.

    For each segment after the first, prepend up to overlap_chars from the
    end of the previous segment's source text.
    """
    if not segments:
        return []

    chunks = []
    # Track position in original text for char_start/char_end
    search_start = 0

    for i, seg in enumerate(segments):
        # Find this segment's position in the original text
        char_start = original_text.find(seg[:50], search_start)
        if char_start < 0:
            char_start = search_start  # Fallback
        char_end = char_start + len(seg)
        search_start = max(char_start + 1, search_start)

        if i > 0 and overlap_chars > 0:
            # Grab overlap from end of previous segment
            prev_text = segments[i - 1]
            overlap_text = prev_text[-overlap_chars:] if len(prev_text) > overlap_chars else prev_text
            # Find a clean word boundary for the overlap start
            space_idx = overlap_text.find(" ")
            if space_idx > 0:
                overlap_text = overlap_text[space_idx + 1:]
            if overlap_text:
                seg = overlap_text + " " + seg

        chunks.append({
            "index": i,
            "text": seg,
            "char_start": char_start,
            "char_end": char_end,
            "position": "",  # Assigned by caller
        })

    return chunks
