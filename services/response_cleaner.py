"""Response cleaner — strip report-mode formatting from model responses.

Removes markdown structural elements that make Janus sound like a report
generator. Preserves inline emphasis, code blocks, and content-bearing lists.
"""
import logging
import re
from services.settings import get_setting

logger = logging.getLogger(__name__)


def clean_response(text: str) -> str:
    """Strip report-mode formatting from model response text.

    Guarded by response_cleanup_enabled setting. When disabled,
    returns text unchanged.

    Args:
        text: The model response text after reasoning extraction.

    Returns:
        Cleaned text with structural formatting removed.
    """
    if not text:
        return text

    enabled = (get_setting("response_cleanup_enabled") or "true").lower() == "true"
    logger.info("Response cleanup: enabled=%s, input_len=%d", enabled, len(text))
    if not enabled:
        return text

    # Protect code blocks from cleanup
    code_blocks = []
    def _protect(match):
        code_blocks.append(match.group(0))
        return f"\x00CODE{len(code_blocks) - 1}\x00"
    result = re.sub(r'```[\s\S]*?```', _protect, text)

    # Remove markdown headers (### Header, ## Header)
    result = re.sub(r'^#{1,6}\s+', '', result, flags=re.MULTILINE)

    # Remove horizontal rules (---, ___, ***)
    result = re.sub(r'^[-_*]{3,}\s*$', '', result, flags=re.MULTILINE)

    # Remove bold-only lines used as section headers (**Header**)
    result = re.sub(r'^\*\*([^*]+)\*\*\s*$', r'\1', result, flags=re.MULTILINE)

    # Remove signature lines (— Janus, -- Janus)
    result = re.sub(r'^[—–-]{1,2}\s*Janus\s*$', '', result, flags=re.MULTILINE)

    # Collapse multiple blank lines into one
    result = re.sub(r'\n{3,}', '\n\n', result)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        result = result.replace(f"\x00CODE{i}\x00", block)

    logger.info("Response cleanup: output_len=%d, changed=%s",
                len(result.strip()), result.strip() != text)
    return result.strip()
