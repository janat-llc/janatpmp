"""Backfill orchestrator — Run the full data foundation pipeline.

Executes phases in dependency order with progress tracking,
error recovery, and graceful interruption support.

R26: The Waking Mind
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class BackfillPhase(Enum):
    METADATA = "metadata"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    GRAPH = "graph"
    COMPLETE = "complete"


@dataclass
class BackfillProgress:
    """Live progress state for the backfill pipeline."""
    phase: BackfillPhase = BackfillPhase.METADATA
    phase_detail: str = ""
    started_at: float = 0.0

    # Per-phase results
    metadata_result: str = ""
    chunking_results: dict = field(default_factory=dict)
    embedding_results: dict = field(default_factory=dict)
    graph_results: dict = field(default_factory=dict)

    # Error tracking
    errors: list[str] = field(default_factory=list)

    # Control
    cancel_requested: bool = False

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0


# Module-level progress (readable from any thread)
_current_progress: BackfillProgress | None = None
_lock = threading.Lock()


def get_backfill_progress() -> dict:
    """Return current backfill progress as a dict.

    Returns idle status if no backfill is running, otherwise
    current phase, counters, elapsed time, and any errors.

    Returns:
        Dict with status, phase, details, and per-phase results.
    """
    with _lock:
        if _current_progress is None:
            return {"status": "idle"}
        p = _current_progress
        return {
            "status": "running" if p.phase != BackfillPhase.COMPLETE else "complete",
            "phase": p.phase.value,
            "phase_detail": p.phase_detail,
            "elapsed_seconds": round(p.elapsed_seconds, 1),
            "metadata_result": p.metadata_result,
            "chunking_results": p.chunking_results,
            "embedding_results": p.embedding_results,
            "graph_results": p.graph_results,
            "errors": p.errors[-10:],
        }


def cancel_backfill() -> str:
    """Request graceful cancellation of the running backfill.

    The pipeline checks the cancel flag between phases and stops
    after the current operation completes.

    Returns:
        Status message confirming cancellation request or noting no backfill is running.
    """
    global _current_progress
    with _lock:
        if _current_progress and _current_progress.phase != BackfillPhase.COMPLETE:
            _current_progress.cancel_requested = True
            return "Cancellation requested — will stop after current phase."
        return "No backfill running."


def run_backfill(skip_phases: str = "") -> dict:
    """Execute the full backfill pipeline in dependency order.

    Phases run sequentially:
        1. metadata  — backfill_message_metadata()
        2. chunking  — chunk_all_messages() + chunk_all_documents()
        3. embedding — embed_all_messages() + embed_all_documents() + items + tasks
        4. graph     — backfill_graph() + weave_conversation_graph()

    Each phase is checkpoint-safe (re-runnable, skips already-processed entities).
    Cancellation is checked between phases.

    Args:
        skip_phases: Comma-separated phase names to skip (e.g. "graph,embedding").

    Returns:
        Summary dict with per-phase results and total elapsed time.
    """
    global _current_progress

    skip = set(s.strip().lower() for s in skip_phases.split(",") if s.strip())

    with _lock:
        if (_current_progress is not None
                and _current_progress.phase != BackfillPhase.COMPLETE):
            return {"error": "Backfill already running",
                    "phase": _current_progress.phase.value}
        _current_progress = BackfillProgress(started_at=time.time())

    p = _current_progress

    try:
        # --- Phase 1: Metadata backfill ---
        if "metadata" not in skip and not p.cancel_requested:
            p.phase = BackfillPhase.METADATA
            p.phase_detail = "Creating metadata rows for imported messages"
            logger.info("Backfill: Phase 1 — metadata")
            try:
                from db.chat_operations import backfill_message_metadata
                # Large batch to process all at once
                result = backfill_message_metadata(batch_size=100000)
                p.metadata_result = result
                logger.info("Backfill metadata: %s", result)
            except Exception as e:
                p.errors.append(f"metadata: {e}")
                logger.warning("Backfill metadata failed: %s", e)

        # --- Phase 2: Chunking ---
        if "chunking" not in skip and not p.cancel_requested:
            p.phase = BackfillPhase.CHUNKING
            p.phase_detail = "Chunking messages"
            logger.info("Backfill: Phase 2 — chunking")
            chunk_results = {}
            try:
                from services.bulk_embed import chunk_all_messages
                p.phase_detail = "Chunking messages"
                chunk_results["messages"] = chunk_all_messages()
            except Exception as e:
                p.errors.append(f"chunk_messages: {e}")
                logger.warning("Backfill chunk_messages failed: %s", e)

            if not p.cancel_requested:
                try:
                    from services.bulk_embed import chunk_all_documents
                    p.phase_detail = "Chunking documents"
                    chunk_results["documents"] = chunk_all_documents()
                except Exception as e:
                    p.errors.append(f"chunk_documents: {e}")
                    logger.warning("Backfill chunk_documents failed: %s", e)
            p.chunking_results = chunk_results

        # --- Phase 3: Embedding ---
        if "embedding" not in skip and not p.cancel_requested:
            p.phase = BackfillPhase.EMBEDDING
            logger.info("Backfill: Phase 3 — embedding")
            embed_results = {}

            embed_steps = [
                ("messages", "Embedding message chunks",
                 "services.bulk_embed", "embed_all_messages"),
                ("documents", "Embedding document chunks",
                 "services.bulk_embed", "embed_all_documents"),
                ("items", "Embedding items",
                 "services.bulk_embed", "embed_all_items"),
                ("tasks", "Embedding tasks",
                 "services.bulk_embed", "embed_all_tasks"),
            ]
            for name, detail, module, func_name in embed_steps:
                if p.cancel_requested:
                    break
                p.phase_detail = detail
                try:
                    import importlib
                    mod = importlib.import_module(module)
                    fn = getattr(mod, func_name)
                    embed_results[name] = fn()
                except Exception as e:
                    p.errors.append(f"embed_{name}: {e}")
                    logger.warning("Backfill embed_%s failed: %s", name, e)
            p.embedding_results = embed_results

        # --- Phase 4: Graph sync ---
        if "graph" not in skip and not p.cancel_requested:
            p.phase = BackfillPhase.GRAPH
            logger.info("Backfill: Phase 4 — graph")
            graph_results = {}

            p.phase_detail = "Syncing graph (CDC + identity)"
            try:
                from graph.cdc_consumer import backfill_graph
                graph_results["backfill"] = backfill_graph()
            except Exception as e:
                p.errors.append(f"backfill_graph: {e}")
                logger.warning("Backfill graph failed: %s", e)

            if not p.cancel_requested:
                p.phase_detail = "Weaving conversation graph"
                try:
                    from graph.semantic_edges import weave_conversation_graph
                    graph_results["weave"] = weave_conversation_graph()
                except Exception as e:
                    p.errors.append(f"weave_graph: {e}")
                    logger.warning("Backfill weave failed: %s", e)
            p.graph_results = graph_results

        # --- Complete ---
        p.phase = BackfillPhase.COMPLETE
        if p.cancel_requested:
            p.phase_detail = "Cancelled by user"
            logger.info("Backfill cancelled after %.1fs", p.elapsed_seconds)
        else:
            p.phase_detail = "All phases complete"
            logger.info("Backfill complete in %.1fs", p.elapsed_seconds)

        return get_backfill_progress()

    except Exception as e:
        p.errors.append(f"fatal: {e}")
        p.phase = BackfillPhase.COMPLETE
        p.phase_detail = f"Failed: {e}"
        logger.error("Backfill fatal error: %s", e)
        return get_backfill_progress()


def run_backfill_async() -> str:
    """Launch backfill in a background daemon thread.

    Returns immediately with a status message. Use get_backfill_progress()
    to monitor progress.

    Returns:
        Status message confirming the backfill was started.
    """
    with _lock:
        if (_current_progress is not None
                and _current_progress.phase != BackfillPhase.COMPLETE):
            return "Backfill already running."

    thread = threading.Thread(target=run_backfill, daemon=True,
                              name="backfill-orchestrator")
    thread.start()
    return "Backfill started in background. Use get_backfill_progress() to monitor."
