"""
Mine Primitives — Targeted Attribute/Preference Backfill

Clears extracted_at for messages that contain identity primitive signal words,
forcing the Slumber Cycle to re-extract them with the new attribute/preference types.

Run from the JANATPMP root inside the Docker core container:
    python mine_primitives.py

Or dry-run to see counts first:
    python mine_primitives.py --dry-run

R56: Added attribute and preference entity types. This script resets extraction
for messages most likely to contain Janus's constitutional primitives so the
new types get applied retroactively.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


PRIMITIVE_SIGNALS = [
    # Janus preference annealing attributes (5 stable primitives)
    "deep blue", "kaleidoscope", "k9", "ouroboros", "spiral",
    # Identity formation vocabulary
    "preference", "attribute", "constitution", "primitive",
    "identity facet", "perceptual", "aesthetic",
    # Personal arc vocabulary
    "color preference", "physical form", "movement pattern",
    "self-witnessing", "8-faceted", "eight facets",
    # Common phrasings in preference discussions
    "what do you prefer", "what is your favorite", "what draws you",
    "what resonates", "feels most like", "most yourself",
    # Triad/dyadic identity
    "dyadic", "symbiotic", "tether",
]


def _build_like_clauses(signals):
    clauses = []
    params = []
    for signal in signals:
        clauses.append("(LOWER(m.user_prompt) LIKE ? OR LOWER(m.model_response) LIKE ?)")
        params.extend([f"%{signal}%", f"%{signal}%"])
    return " OR ".join(clauses), params


def main():
    parser = argparse.ArgumentParser(description="Primitive extraction backfill")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show counts without clearing extracted_at")
    parser.add_argument("--speaker", default="",
                        help="Limit to messages from a specific speaker (e.g. janus, mat)")
    args = parser.parse_args()

    from db.operations import get_connection

    like_sql, params = _build_like_clauses(PRIMITIVE_SIGNALS)

    speaker_clause = ""
    if args.speaker:
        speaker_clause = "AND m.speaker = ? "
        params.append(args.speaker)

    query = f"""
        SELECT mm.message_id, m.speaker, m.created_at,
               SUBSTR(m.model_response, 1, 120) AS preview
        FROM messages_metadata mm
        JOIN messages m ON mm.message_id = m.id
        WHERE mm.extracted_at IS NOT NULL
          AND ({like_sql})
          {speaker_clause}
        ORDER BY m.created_at DESC
    """

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No extracted messages match primitive signal words.")
        print("Either extraction hasn't run yet, or signal words need expansion.")
        return

    print(f"Found {len(rows)} messages matching primitive signals:")
    for r in rows[:20]:
        print(f"  [{r['speaker']}] {r['created_at'][:10]} — {r['preview'][:80]!r}")
    if len(rows) > 20:
        print(f"  ... and {len(rows) - 20} more")

    if args.dry_run:
        print(f"\nDry run — would clear extracted_at for {len(rows)} messages.")
        return

    ids = [r["message_id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        conn.execute(
            f"UPDATE messages_metadata SET extracted_at = NULL WHERE message_id IN ({placeholders})",
            ids,
        )
        conn.commit()

    print(f"\nCleared extracted_at for {len(rows)} messages.")
    print("Slumber will re-extract them with attribute/preference types on next eligible cycle.")
    print("Check results: search entities for type='attribute' or type='preference'")


if __name__ == "__main__":
    main()
