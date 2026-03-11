"""Entity salience decay — age-based retrieval weight adjustment.

Entities mentioned recently stay prominent. Entities not mentioned
in months gradually fade (but never disappear). Mirrors how message
temporal decay works, applied to the entity layer.

SQLite `entities.salience` is the source of truth.

R31: The Web
"""

import logging
from datetime import datetime, timezone

from atlas.config import (
    ENTITY_DECAY_BATCH_SIZE,
    ENTITY_DECAY_FLOOR,
    ENTITY_DECAY_HALF_LIFE,
    SALIENCE_DEFAULT,
)

logger = logging.getLogger(__name__)


def run_entity_decay_cycle(batch_size: int = 0) -> dict:
    """Apply temporal decay to entity salience.

    Queries entities ordered by last_seen_at (oldest first), computes
    a decay factor based on staleness, and updates SQLite (source of truth).

    High mention_count provides a small boost that counteracts decay,
    keeping frequently-referenced entities more prominent.

    Args:
        batch_size: Max entities to process. 0 = config default.

    Returns:
        Dict with keys: processed, decayed, boosted, errors.
    """
    batch_size = batch_size or ENTITY_DECAY_BATCH_SIZE

    from db.operations import get_connection

    result = {"processed": 0, "decayed": 0, "boosted": 0, "errors": 0}

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, last_seen_at, mention_count, salience
                FROM entities
                WHERE last_seen_at IS NOT NULL
                ORDER BY last_seen_at ASC
                LIMIT ?
                """,
                (batch_size,),
            ).fetchall()
    except Exception as e:
        logger.debug("Entity decay query failed: %s", e)
        result["errors"] = 1
        return result

    if not rows:
        return result

    # Compute decay for each entity, collect updates
    updates: list[tuple[float, str, str]] = []  # (salience, updated_at, id)

    for row in rows:
        entity_id = row["id"]
        mention_count = row["mention_count"] or 1
        try:
            current_salience = float(row["salience"]) if row["salience"] is not None else SALIENCE_DEFAULT
        except (ValueError, TypeError):
            current_salience = SALIENCE_DEFAULT

        # Parse last_seen_at
        try:
            last_seen_str = row["last_seen_at"]
            if last_seen_str:
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                days_stale = max(0, (now - last_seen).days)
            else:
                days_stale = 0
        except (ValueError, TypeError):
            days_stale = 0

        # Compute decay
        decay_factor = max(
            ENTITY_DECAY_FLOOR,
            ENTITY_DECAY_HALF_LIFE / (ENTITY_DECAY_HALF_LIFE + days_stale),
        )
        mention_boost = min(0.15, mention_count * 0.005)
        new_salience = round(
            min(1.0, (SALIENCE_DEFAULT * decay_factor) + mention_boost), 3
        )

        # Skip if no meaningful change
        if abs(new_salience - current_salience) < 0.001:
            result["processed"] += 1
            continue

        # Track direction
        if new_salience < current_salience:
            result["decayed"] += 1
        else:
            result["boosted"] += 1

        updates.append((new_salience, now_iso, entity_id))
        result["processed"] += 1

    # Batch write to SQLite (source of truth)
    if updates:
        try:
            with get_connection() as conn:
                conn.executemany(
                    "UPDATE entities SET salience = ?, updated_at = ? WHERE id = ?",
                    updates,
                )
                conn.commit()
        except Exception as e:
            logger.debug("Entity decay SQLite batch update failed: %s", e)
            result["errors"] += len(updates)

    if result["decayed"] or result["boosted"]:
        logger.info(
            "Entity salience decay: %d processed (%d decayed, %d boosted, %d errors)",
            result["processed"], result["decayed"], result["boosted"], result["errors"],
        )

    return result
