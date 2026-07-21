"""App context: holds long-lived components shared by every tool."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import structlog

from .clients.ytdlp import DownloadProcess, YtDlpClient
from .config import Settings
from .tasks import TaskStore

log = structlog.get_logger(__name__)

_PROBE_CACHE_TTL_SECONDS = 600.0
_PROBE_CACHE_MAX_ENTRIES = 128


@dataclass
class AppContext:
    settings: Settings
    yt_dlp: YtDlpClient
    tasks: TaskStore
    # Live download handles, keyed by task_id. Reaped on completion by
    # the worker that owns them.
    procs: dict[str, DownloadProcess] = field(default_factory=dict)
    # Strong refs to fire-and-forget worker tasks. Without this set the
    # GC may collect the task mid-run (asyncio only weak-refs them) and
    # the download silently halts.
    background_tasks: set[asyncio.Task[None]] = field(default_factory=set)
    # The bot probes immediately before showing its confirm button. Reusing that
    # payload avoids hitting YouTube twice for one user action.
    recent_probes: dict[str, tuple[float, dict[str, object]]] = field(default_factory=dict)

    def cache_probe(self, url: str, payload: dict[str, object]) -> None:
        now = time.monotonic()
        self._prune_probe_cache(now)
        if len(self.recent_probes) >= _PROBE_CACHE_MAX_ENTRIES:
            oldest = min(self.recent_probes, key=lambda key: self.recent_probes[key][0])
            self.recent_probes.pop(oldest, None)
        self.recent_probes[url] = (now, payload)

    def get_cached_probe(self, url: str) -> dict[str, object] | None:
        now = time.monotonic()
        self._prune_probe_cache(now)
        entry = self.recent_probes.get(url)
        return entry[1] if entry is not None else None

    def _prune_probe_cache(self, now: float) -> None:
        expired = [
            url
            for url, (created_at, _) in self.recent_probes.items()
            if now - created_at > _PROBE_CACHE_TTL_SECONDS
        ]
        for url in expired:
            self.recent_probes.pop(url, None)


@asynccontextmanager
async def build_app_context(settings: Settings) -> AsyncIterator[AppContext]:
    yt_dlp = YtDlpClient(
        yt_dlp_bin=settings.yt_dlp_bin,
        cookies_file=settings.cookies_file,
        js_runtimes=settings.js_runtimes,
        remote_components=settings.remote_components,
        probe_timeout_seconds=settings.probe_timeout_seconds,
    )
    tasks = TaskStore(path=settings.state_db_path)
    # GC old finished tasks on startup — keeps the SQLite from growing
    # forever in long-running deployments.
    removed = tasks.gc_history(settings.task_history_keep)
    if removed:
        log.info("tasks.gc", removed=removed, keep=settings.task_history_keep)
    try:
        yield AppContext(settings=settings, yt_dlp=yt_dlp, tasks=tasks)
    finally:
        tasks.close()
