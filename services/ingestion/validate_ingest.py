"""Ingestion validation — assertion-based checks for batch ingest quality (R52).

Run after each ingestion stage to confirm the Triad received what was expected.
Each check returns PASS or FAIL with a human-readable message. A stage gate
passes only when all checks pass.

Usage:
    from services.ingestion.validate_ingest import validate_stage1_journals
    result = validate_stage1_journals()
    for line in result["checks"] + result["failures"]:
        print(line)
    print("GATE PASSED" if result["passed"] else "GATE FAILED")
"""

import logging
from db.operations import get_connection

logger = logging.getLogger(__name__)


def validate_stage1_journals(expected_count: int = 62) -> dict:
    """Validate Stage 1 Claude Journals ingestion gate.

    Args:
        expected_count: Expected minimum number of journal documents.

    Returns:
        Dict with: passed (bool), checks (list[str]), failures (list[str]).
    """
    checks = []
    failures = []

    with get_connection() as conn:
        # Check 1: Document count
        actual = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE source_type='journal' AND author='claude'"
        ).fetchone()[0]
        if actual >= expected_count:
            checks.append(f"PASS: document count {actual} >= {expected_count}")
        else:
            failures.append(f"FAIL: document count {actual} < expected {expected_count}")

        # Check 2: All have file_created_at (no NULLs)
        null_ts = conn.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE source_type='journal' AND author='claude' AND file_created_at IS NULL"
        ).fetchone()[0]
        if null_ts == 0:
            checks.append("PASS: all journal documents have file_created_at")
        else:
            failures.append(f"FAIL: {null_ts} journal documents missing file_created_at")

        # Check 3: Temporal spread — files should span Oct–Nov 2025
        row = conn.execute(
            "SELECT MIN(file_created_at), MAX(file_created_at) FROM documents "
            "WHERE source_type='journal' AND author='claude'"
        ).fetchone()
        min_ts, max_ts = row[0], row[1]
        if min_ts and "2025-10" in min_ts:
            checks.append(f"PASS: temporal spread min={min_ts[:10]}")
        else:
            failures.append(
                f"FAIL: temporal spread unexpected — min={min_ts!r} (expected 2025-10-xx)"
            )
        if max_ts and ("2025-11" in max_ts or "2025-12" in max_ts):
            checks.append(f"PASS: temporal spread max={max_ts[:10]}")
        else:
            failures.append(
                f"WARN: temporal spread max={max_ts!r} (expected 2025-11-xx or later)"
            )

        # Check 4: FTS index has entries for ingested journals
        fts_count = conn.execute(
            "SELECT COUNT(*) FROM documents_fts "
            "WHERE id IN (SELECT id FROM documents WHERE source_type='journal' AND author='claude')"
        ).fetchone()[0]
        if fts_count >= expected_count:
            checks.append(f"PASS: FTS index has {fts_count} journal entries")
        else:
            failures.append(
                f"FAIL: FTS index has {fts_count} journal entries (expected {expected_count})"
            )

        # Check 5: Embedding completion (90% threshold — embeddings may still be running)
        completed = conn.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE source_type='journal' AND author='claude' AND embedding_status='completed'"
        ).fetchone()[0]
        threshold_90 = int(expected_count * 0.9)
        if completed >= threshold_90:
            checks.append(f"PASS: {completed}/{actual} embeddings completed")
        else:
            failures.append(
                f"WARN: {completed}/{actual} embeddings completed "
                f"(need {threshold_90} — may still be running)"
            )

        # Check 6: Session 01 spot-check
        session01 = conn.execute(
            "SELECT id FROM documents WHERE title LIKE '%Session 01%' AND author='claude'"
        ).fetchone()
        if session01:
            checks.append(f"PASS: Session 01 document present (id={session01[0][:8]}...)")
        else:
            failures.append("FAIL: Session 01 document not found — title mismatch or not ingested")

    return {
        "passed": len(failures) == 0,
        "checks": checks,
        "failures": failures,
    }


def validate_stage2_minutes(expected_count: int = 61) -> dict:
    """Validate Stage 2 BookClub Session Minutes ingestion gate.

    Args:
        expected_count: Expected minimum number of minutes documents.

    Returns:
        Dict with: passed (bool), checks (list[str]), failures (list[str]).
    """
    checks = []
    failures = []

    with get_connection() as conn:
        # Check 1: Document count
        actual = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE source_type='session_minutes'"
        ).fetchone()[0]
        if actual >= expected_count:
            checks.append(f"PASS: document count {actual} >= {expected_count}")
        else:
            failures.append(f"FAIL: document count {actual} < expected {expected_count}")

        # Check 2: All have file_created_at
        null_ts = conn.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE source_type='session_minutes' AND file_created_at IS NULL"
        ).fetchone()[0]
        if null_ts == 0:
            checks.append("PASS: all minutes documents have file_created_at")
        else:
            failures.append(f"FAIL: {null_ts} minutes documents missing file_created_at")

        # Check 3: FTS presence
        fts_count = conn.execute(
            "SELECT COUNT(*) FROM documents_fts "
            "WHERE id IN (SELECT id FROM documents WHERE source_type='session_minutes')"
        ).fetchone()[0]
        if fts_count >= expected_count:
            checks.append(f"PASS: FTS index has {fts_count} minutes entries")
        else:
            failures.append(
                f"FAIL: FTS index has {fts_count} minutes entries (expected {expected_count})"
            )

        # Check 4: Embedding completion
        completed = conn.execute(
            "SELECT COUNT(*) FROM documents "
            "WHERE source_type='session_minutes' AND embedding_status='completed'"
        ).fetchone()[0]
        threshold_90 = int(expected_count * 0.9)
        if completed >= threshold_90:
            checks.append(f"PASS: {completed}/{actual} embeddings completed")
        else:
            failures.append(
                f"WARN: {completed}/{actual} embeddings completed "
                f"(need {threshold_90} — may still be running)"
            )

        # Check 5: Session 1 spot-check
        session01 = conn.execute(
            "SELECT id FROM documents "
            "WHERE title LIKE '%Session 1%' AND source_type='session_minutes'"
        ).fetchone()
        if session01:
            checks.append(f"PASS: Session 1 minutes present (id={session01[0][:8]}...)")
        else:
            failures.append(
                "FAIL: Session 1 minutes not found — title mismatch or not ingested"
            )

    return {
        "passed": len(failures) == 0,
        "checks": checks,
        "failures": failures,
    }
