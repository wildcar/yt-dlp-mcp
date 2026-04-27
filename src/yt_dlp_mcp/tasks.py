"""SQLite-backed task store.

Persisting in-flight downloads to disk so a service restart re-attaches
to running yt-dlp subprocesses (or, more pragmatically, exposes their
final state to the bot's poller after a crash). Schema is small:
``tasks`` carries everything the MCP tools return.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class TaskStore:
    """Single-process repository facade. The MCP server owns one instance."""

    path: Path
    _conn: sqlite3.Connection = field(init=False)
    _lock: threading.RLock = field(init=False, default_factory=threading.RLock)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._tx() as cur:
            cur.execute("PRAGMA journal_mode = WAL")
            cur.execute("PRAGMA synchronous = NORMAL")
        self._ensure_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    def _ensure_schema(self) -> None:
        with self._tx() as cur:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id           TEXT PRIMARY KEY,
                    url               TEXT NOT NULL,
                    video_id          TEXT,
                    title             TEXT,
                    channel           TEXT,
                    state             TEXT NOT NULL,
                    progress_pct      REAL NOT NULL DEFAULT 0,
                    downloaded_bytes  INTEGER NOT NULL DEFAULT 0,
                    total_bytes       INTEGER,
                    output_path       TEXT,
                    eta_seconds       INTEGER,
                    speed_bps         REAL,
                    error             TEXT,
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
                CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
                """
            )

    def insert(self, *, task_id: str, url: str) -> None:
        now = _now_iso()
        with self._tx() as cur:
            cur.execute(
                """
                INSERT INTO tasks (task_id, url, state, created_at, updated_at)
                VALUES (?, ?, 'queued', ?, ?)
                """,
                (task_id, url, now, now),
            )

    def update(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now_iso()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._tx() as cur:
            cur.execute(
                f"UPDATE tasks SET {cols} WHERE task_id = ?",
                (*fields.values(), task_id),
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._tx() as cur:
            cur.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def list_active(self) -> list[dict[str, Any]]:
        with self._tx() as cur:
            cur.execute(
                "SELECT * FROM tasks WHERE state IN ('queued', 'running') ORDER BY created_at"
            )
            return [dict(r) for r in cur.fetchall()]

    def gc_history(self, keep: int) -> int:
        """Drop the oldest finished tasks, keeping the most recent ``keep``.

        Active tasks are never touched. Returns the number of rows removed.
        """
        with self._tx() as cur:
            cur.execute(
                """
                DELETE FROM tasks
                 WHERE state IN ('complete', 'failed', 'cancelled')
                   AND task_id NOT IN (
                        SELECT task_id FROM tasks
                         WHERE state IN ('complete', 'failed', 'cancelled')
                         ORDER BY updated_at DESC
                         LIMIT ?
                   )
                """,
                (keep,),
            )
            return cur.rowcount


__all__ = ["TaskStore"]
