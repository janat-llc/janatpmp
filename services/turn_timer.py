"""Thread-local turn timer for accumulating named timing spans."""

import threading
import time

_local = threading.local()


class TurnTimer:
    """Accumulates named timing spans across a chat turn.

    Usage:
        with TurnTimer() as timer:
            with timer.span("rag"):
                ...  # RAG work
            with timer.span("inference"):
                ...  # Provider call
            timings = timer.results()  # {"rag": 142, "inference": 3201, "total": 3380}
    """

    def __enter__(self):
        self._spans = {}
        self._start = time.monotonic()
        _local.turn_timer = self
        return self

    def __exit__(self, *exc):
        self._total = int((time.monotonic() - self._start) * 1000)
        _local.turn_timer = None

    class _Span:
        def __init__(self, timer, name):
            self.timer = timer
            self.name = name

        def __enter__(self):
            self._start = time.monotonic()
            return self

        def __exit__(self, *exc):
            self.timer._spans[self.name] = int(
                (time.monotonic() - self._start) * 1000
            )

    def span(self, name: str):
        """Create a named timing span."""
        return self._Span(self, name)

    def results(self) -> dict:
        """Return all recorded spans plus total elapsed time in ms."""
        total = getattr(self, "_total", None)
        if total is None:
            total = int((time.monotonic() - self._start) * 1000)
        return {**self._spans, "total": total}


def get_timer() -> TurnTimer | None:
    """Get the current thread's active TurnTimer, or None."""
    return getattr(_local, "turn_timer", None)
