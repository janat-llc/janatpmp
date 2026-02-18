"""Centralized logging — SQLite log handler + console handler.

Provides a dual-output logging system: console (StreamHandler) for immediate
visibility and SQLite (SQLiteLogHandler) for persistent, queryable log storage
in the app_logs table. Call setup_logging() once at app startup.
"""

import logging
import sqlite3
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta

# Direct path — avoids importing db.operations (which runs init_database on import)
DB_PATH = Path(__file__).parent.parent / "db" / "janatpmp.db"

_BATCH_SIZE = 10


class SQLiteLogHandler(logging.Handler):
    """Logging handler that writes records to the app_logs SQLite table.

    Batches inserts for performance: flushes every _BATCH_SIZE records or
    immediately on WARNING and above.
    """

    def __init__(self):
        super().__init__()
        self._buffer: list[tuple] = []
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("PRAGMA busy_timeout = 3000")
        return conn

    def emit(self, record: logging.LogRecord):
        try:
            metadata = {}
            if hasattr(record, "log_metadata"):
                metadata = record.log_metadata

            row = (
                datetime.utcnow().isoformat(timespec="seconds"),
                record.levelname,
                record.module,
                record.funcName or "",
                self.format(record),
                json.dumps(metadata) if metadata else "{}",
            )

            with self._lock:
                self._buffer.append(row)
                if record.levelno >= logging.WARNING or len(self._buffer) >= _BATCH_SIZE:
                    self._flush_buffer()
        except Exception:
            self.handleError(record)

    def _flush_buffer(self):
        """Write buffered records to SQLite. Caller must hold self._lock."""
        if not self._buffer:
            return
        rows = list(self._buffer)
        self._buffer.clear()
        try:
            conn = self._get_conn()
            try:
                conn.executemany(
                    "INSERT INTO app_logs (timestamp, level, module, function, message, metadata)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # DB not ready yet (pre-migration) — drop silently
            pass

    def flush(self):
        with self._lock:
            self._flush_buffer()

    def close(self):
        self.flush()
        super().close()


def setup_logging(level: int = logging.INFO):
    """Configure root logger with console + SQLite handlers.

    Call once at app startup, before init_database().
    Safe to call multiple times (idempotent — checks for existing handlers).
    """
    root = logging.getLogger()
    # Avoid double-setup
    if any(isinstance(h, SQLiteLogHandler) for h in root.handlers):
        return

    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s.%(funcName)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # SQLite handler
    db_handler = SQLiteLogHandler()
    db_handler.setLevel(level)
    db_handler.setFormatter(fmt)
    root.addHandler(db_handler)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "urllib3", "gradio", "uvicorn",
                 "uvicorn.access", "watchfiles", "hpack", "markdown_it"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logs(
    level: str = "",
    module: str = "",
    limit: int = 100,
    since: str = "",
) -> list[dict]:
    """Query app_logs for the Admin UI.

    Args:
        level: Filter by log level (e.g. 'ERROR'). Empty = all levels.
        module: Filter by module name substring. Empty = all modules.
        limit: Max rows to return.
        since: ISO timestamp — only return logs after this time.

    Returns:
        List of log dicts ordered newest-first.
    """
    # Flush any pending records so query is up-to-date
    for h in logging.getLogger().handlers:
        if isinstance(h, SQLiteLogHandler):
            h.flush()

    clauses = []
    params: list = []
    if level:
        clauses.append("level = ?")
        params.append(level)
    if module:
        clauses.append("module LIKE ?")
        params.append(f"%{module}%")
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM app_logs{where} ORDER BY id DESC LIMIT ?"
    params.append(limit)

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def cleanup_old_logs(days: int = 30):
    """Delete log entries older than the specified number of days.

    Args:
        days: Retention period. Logs older than this are deleted.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("DELETE FROM app_logs WHERE timestamp < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception:
        pass  # Table may not exist yet on first run
