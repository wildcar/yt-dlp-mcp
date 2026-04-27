"""App context: holds long-lived components shared by every tool."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import structlog

from .clients.ytdlp import DownloadProcess, YtDlpClient
from .config import Settings
from .tasks import TaskStore

log = structlog.get_logger(__name__)


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


@asynccontextmanager
async def build_app_context(settings: Settings) -> AsyncIterator[AppContext]:
    yt_dlp = YtDlpClient(
        yt_dlp_bin=settings.yt_dlp_bin,
        cookies_file=settings.cookies_file,
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
