"""Shared formatting utilities for JANATPMP."""

import pandas as pd


def fmt_enum(value: str) -> str:
    """Convert snake_case enum to Title Case for display.

    Examples:
        'not_started' -> 'Not Started'
        'agent_story' -> 'Agent Story'
    """
    return value.replace("_", " ").title() if value else ""


def entity_list_to_df(
    entities: list[dict],
    columns: list[tuple[str, str]],
    empty_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Build a display DataFrame from a list of entity dicts.

    Args:
        entities: List of entity dicts from db operations.
        columns: List of (display_name, key_or_callable) tuples.
            If key_or_callable is a string, it's used as a dict key.
            Use special prefixes:
                'id:' — truncates to 8 chars (e.g. 'id:id')
                'fmt:' — applies fmt_enum (e.g. 'fmt:status')
                'date:' — truncates to 16 chars (e.g. 'date:created_at')
            Plain string — raw dict lookup (e.g. 'title')
        empty_columns: Column names for the empty DataFrame fallback.
            If None, derived from columns tuples.

    Returns:
        pd.DataFrame with display-ready data.
    """
    col_names = empty_columns or [c[0] for c in columns]
    if not entities:
        return pd.DataFrame(columns=col_names)

    rows = []
    for entity in entities:
        row = {}
        for display_name, spec in columns:
            if spec.startswith("id:"):
                key = spec[3:]
                row[display_name] = entity.get(key, "")[:8]
            elif spec.startswith("fmt:"):
                key = spec[4:]
                row[display_name] = fmt_enum(entity.get(key, ""))
            elif spec.startswith("date:"):
                key = spec[5:]
                val = entity.get(key, "") or ""
                row[display_name] = val[:16]
            else:
                row[display_name] = entity.get(spec, "")
        rows.append(row)

    return pd.DataFrame(rows)
