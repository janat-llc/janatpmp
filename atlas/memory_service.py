"""ATLAS memory service — salience write-back to Qdrant payloads.

This is where ATLAS turns on. When a retrieval event changes the thing
being retrieved, the system has an opinion about its own contents.
A document that consistently scores high against diverse queries is
genuinely information-dense — that's what salience is.
"""

import logging
from datetime import datetime, timezone

from atlas.config import SALIENCE_BOOST_RATE, SALIENCE_DEFAULT

logger = logging.getLogger(__name__)


def write_salience(collection: str, results: list[dict]):
    """Update Qdrant payloads with salience metadata after reranking.

    For each result, reads current salience, applies a weighted boost from
    the rerank score, and writes back. High rerank scores nudge salience
    upward; the signal accumulates over repeated retrievals.

    Args:
        collection: Qdrant collection name.
        results: List of dicts with 'id' and 'rerank_score' keys.
    """
    # Lazy import to avoid circular dependency (vector_store imports embedding)
    from services.vector_store import _get_client

    try:
        client = _get_client()
    except Exception as e:
        logger.warning("Salience write-back skipped — Qdrant unavailable: %s", e)
        return

    now = datetime.now(timezone.utc).isoformat()

    for result in results:
        point_id = result.get("id")
        rerank_score = result.get("rerank_score", 0.0)
        if not point_id:
            continue

        try:
            # Read current salience from existing payload
            retrieved = client.retrieve(collection, [point_id], with_payload=True)
            if retrieved:
                current_salience = retrieved[0].payload.get("salience", SALIENCE_DEFAULT)
            else:
                current_salience = SALIENCE_DEFAULT

            # Weighted update — rerank score nudges salience, doesn't replace it
            new_salience = min(1.0, current_salience + (rerank_score * SALIENCE_BOOST_RATE))

            client.set_payload(
                collection_name=collection,
                payload={
                    "salience": new_salience,
                    "last_retrieved": now,
                },
                points=[point_id],
            )
        except Exception as e:
            logger.debug("Salience write-back failed for %s: %s", point_id, e)
