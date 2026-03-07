"""PDF text extraction via pdfplumber."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text(path: str | Path) -> str:
    """Extract all text from a PDF file.

    Args:
        path: Path to the PDF file.

    Returns:
        Extracted text as a single string, pages separated by newlines.
        Empty string if extraction fails.
    """
    path = Path(path)
    if not path.exists():
        logger.warning("PDF not found: %s", path)
        return ""

    try:
        import pdfplumber

        pages_text = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)

        result = "\n\n".join(pages_text)
        logger.info(
            "PDF extracted: %s — %d pages, %d chars",
            path.name, len(pages_text), len(result),
        )
        return result

    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", path.name, e)
        return ""
