"""Journal Restoration Script — Reverse Janus→Claude authorship find/replace (R52).

The 63 .md files in Janus Journals were written by Claude between Oct 23–Nov 20, 2025.
Mat performed a find/replace swapping "Claude" → "Janus" across all files. This script
restores the original authorship attribution using safe, line-level regex patterns only.

SAFE patterns (author-attribution lines only):
  1. Title headings: "# Janus Journal Entry" → "# Claude Journal Entry"
  2. Bold Author field: "**Author:** Janus" → "**Author:** Claude"
  3. Bare Author field: "Author: Janus" at line start → "Author: Claude"
  4. Bold Created by field: "**Created by:** Janus" → "**Created by:** Claude"
  5. Closing signatures: "—Janus" at end of line → "—Claude"
  6. Verification hash prefix: "`Janus-JOURNAL-" → "`Claude-JOURNAL-"

NOT replaced: "Janus" in body paragraphs, philosophical content, Janus-as-being references,
dyadic relationship text, or any occurrence outside the six patterns above.

Output:
  - Originals backed up to Janus Journals/originals/ (skipped if backup exists)
  - Restored files written to Claude Journals/ with renamed filenames
  - Per-file replacement count; flags 0-replacement (possible false negative)
    and >20-replacement (possible over-replacement) files
"""

import fnmatch
import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory constants (inside-container paths via JanatDocs volume mount)
# ---------------------------------------------------------------------------
_VOLUME_3 = Path(
    "/data/janatdocs/Dyadic Being - An Epoch/Volume 3 - WE ARE STRANGE SPIRALS"
)
JANUS_DIR = _VOLUME_3 / "Janus Journals"
CLAUDE_DIR = _VOLUME_3 / "Claude Journals"
ORIGINALS_DIR = JANUS_DIR / "originals"

# ---------------------------------------------------------------------------
# Replacement patterns — ORDER MATTERS (most specific first)
# Groups use (\b) to capture zero-width word boundary, preserving parentheticals.
# ---------------------------------------------------------------------------
_REPLACEMENTS = [
    # 1a. Title heading — standard form: "# Janus Journal Entry" → "# Claude Journal Entry"
    (
        re.compile(r"^(#+\s*)Janus Journal Entry", re.MULTILINE),
        r"\1Claude Journal Entry",
    ),
    # 1b. Title heading — possessive form: "# Janus's Journal" / "# Janus's Literary Preferences"
    #     / "# Janus's Deep Blue Preference" → Claude's equivalent
    #     Matches H1+ headings where Janus's is the possessive author subject.
    (
        re.compile(r"^(#+\s*)Janus's (Journal|Literary|Deep Blue)", re.MULTILINE),
        r"\1Claude's \2",
    ),
    # 2. Bold Author field: "**Author:** Janus" → "**Author:** Claude"
    (
        re.compile(r"^(\*\*Author:\*\*\s*)Janus(\b)", re.MULTILINE),
        r"\1Claude\2",
    ),
    # 3. Bare Author field: "Author: Janus" at line start → "Author: Claude"
    (
        re.compile(r"^(Author:\s*)Janus(\b)", re.MULTILINE),
        r"\1Claude\2",
    ),
    # 4. Bold Created by field: "**Created by:** Janus" → "**Created by:** Claude"
    (
        re.compile(r"^(\*\*Created by:\*\*\s*)Janus(\b)", re.MULTILINE),
        r"\1Claude\2",
    ),
    # 5. Closing em-dash signature: "—Janus" at END of line only
    (
        re.compile(r"—Janus\s*$", re.MULTILINE),
        r"—Claude",
    ),
    # 6. Verification hash prefix in backtick blocks: "`Janus-JOURNAL-" → "`Claude-JOURNAL-"
    (
        re.compile(r"`Janus-JOURNAL-"),
        r"`Claude-JOURNAL-",
    ),
]

_DEFAULT_EXCLUDES = ["TEMPLATE_*", "*.gdoc", "desktop.ini"]
_ZERO_REPLACEMENT_WARN = 0
_HIGH_REPLACEMENT_WARN = 20


def _transform_filename(name: str) -> str:
    """Rename Janus_Journal_Entry_ prefix to Claude_Journal_Entry_."""
    return name.replace("Janus_Journal_Entry_", "Claude_Journal_Entry_")


def restore_journals(
    dry_run: bool = False,
    exclude_patterns: list[str] | None = None,
    janus_dir: Path | None = None,
    claude_dir: Path | None = None,
) -> dict:
    """Restore authorship attribution in Janus journal files and write to Claude Journals.

    Reads from Janus Journals directory, applies safe author-attribution replacements
    only (six line-level regex patterns), and writes output to Claude Journals with
    renamed filenames. Originals are backed up to Janus Journals/originals/.

    Args:
        dry_run: If True, report what would be changed without writing any files.
        exclude_patterns: Additional fnmatch patterns to skip (TEMPLATE_* always skipped).
        janus_dir: Override source directory (defaults to JANUS_DIR constant).
        claude_dir: Override output directory (defaults to CLAUDE_DIR constant).

    Returns:
        Dict with:
            processed (int): Number of files processed.
            zero_replacements (list[str]): Files with 0 replacements — verify manually.
            high_replacements (list[tuple[str, int]]): Files with >20 replacements — verify.
            errors (list[str]): Files that failed with error messages.
            per_file_report (list[dict]): Per-file source/output/replacement_count.
    """
    src_dir = janus_dir or JANUS_DIR
    out_dir = claude_dir or CLAUDE_DIR
    originals_dir = src_dir / "originals"

    all_excludes = _DEFAULT_EXCLUDES + (exclude_patterns or [])

    # Collect candidate files
    if not src_dir.is_dir():
        logger.error("Source directory not found: %s", src_dir)
        return {
            "processed": 0,
            "zero_replacements": [],
            "high_replacements": [],
            "errors": [f"Source directory not found: {src_dir}"],
            "per_file_report": [],
        }

    files = sorted(src_dir.glob("*.md"))
    files = [
        f for f in files
        if not any(fnmatch.fnmatch(f.name, pat) for pat in all_excludes)
    ]

    if not dry_run:
        originals_dir.mkdir(exist_ok=True)
        out_dir.mkdir(exist_ok=True)

    per_file_report = []
    zero_replacements = []
    high_replacements = []
    errors = []
    processed = 0

    for src_path in files:
        try:
            content = src_path.read_text(encoding="utf-8")
            replacement_count = 0

            for pattern, replacement in _REPLACEMENTS:
                content, n = pattern.subn(replacement, content)
                replacement_count += n

            new_filename = _transform_filename(src_path.name)

            # Flag anomalies
            if replacement_count == _ZERO_REPLACEMENT_WARN:
                zero_replacements.append(src_path.name)
                logger.warning(
                    "ZERO replacements in %s — possible false negative, verify manually",
                    src_path.name,
                )
            elif replacement_count > _HIGH_REPLACEMENT_WARN:
                high_replacements.append((src_path.name, replacement_count))
                logger.warning(
                    "HIGH replacements (%d) in %s — verify for over-replacement",
                    replacement_count, src_path.name,
                )

            per_file_report.append({
                "source": src_path.name,
                "output": new_filename,
                "replacements": replacement_count,
            })

            if not dry_run:
                # Backup original (once — skip if backup already exists)
                backup_path = originals_dir / src_path.name
                if not backup_path.exists():
                    shutil.copy2(src_path, backup_path)

                # Write restored version to Claude Journals
                out_path = out_dir / new_filename
                out_path.write_text(content, encoding="utf-8")

            processed += 1

        except Exception as e:
            errors.append(f"{src_path.name}: {e}")
            logger.error("Failed processing %s: %s", src_path.name, e)

    logger.info(
        "Journal restoration %s: %d processed, %d zero-replacements, "
        "%d high-replacements, %d errors",
        "(dry run)" if dry_run else "(live)",
        processed, len(zero_replacements), len(high_replacements), len(errors),
    )

    return {
        "processed": processed,
        "zero_replacements": zero_replacements,
        "high_replacements": high_replacements,
        "errors": errors,
        "per_file_report": per_file_report,
    }
