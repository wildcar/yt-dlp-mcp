"""Shared fixtures.

Tests don't actually invoke yt-dlp — a FakeYtDlpClient replaces the real
client, returning canned probe / playlist payloads and a no-op download
process. Keeps the suite hermetic and fast.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest_asyncio

from yt_dlp_mcp.clients.ytdlp import DownloadProcess, ProgressLine, YtDlpClient
from yt_dlp_mcp.config import Settings
from yt_dlp_mcp.context import AppContext
from yt_dlp_mcp.tasks import TaskStore


@dataclass
class FakeDownloadProcess(DownloadProcess):
    progress_events: list[ProgressLine] = field(default_factory=list)
    rc: int = 0
    started: bool = False

    async def start(self) -> None:
        self.started = True

    async def iter_progress(self) -> AsyncIterator[ProgressLine]:
        for ev in self.progress_events:
            yield ev

    async def wait(self) -> int:
        return self.rc

    async def kill(self) -> None:
        return


@dataclass
class FakeYtDlpClient(YtDlpClient):
    probe_payload: dict[str, Any] | None = None
    playlist_payload: dict[str, Any] | None = None
    fake_version: str = "2025.10.14"
    fake_progress: list[ProgressLine] = field(default_factory=list)
    fake_rc: int = 0
    raise_on_probe: Exception | None = None

    async def probe(self, url: str) -> dict[str, Any]:
        if self.raise_on_probe is not None:
            raise self.raise_on_probe
        return self.probe_payload or {}

    async def list_playlist(self, url: str, *, limit: int) -> dict[str, Any]:
        return self.playlist_payload or {}

    async def version(self) -> str:
        return self.fake_version

    def spawn_download(
        self,
        url: str,
        *,
        output_path: Path,
        format_selector: str = "",
    ) -> DownloadProcess:
        # Pretend yt-dlp wrote the output file. The worker resolves the
        # final path from `handle.output_path` (the literal `-o` we
        # passed), so the test only needs the file to exist.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("")
        return FakeDownloadProcess(
            argv=[],
            output_path=output_path,
            progress_events=list(self.fake_progress),
            rc=self.fake_rc,
        )


@pytest_asyncio.fixture
async def settings(tmp_path: Path) -> Settings:
    return Settings(
        output_dir=tmp_path / "out",
        cookies_file=None,
        state_db_path=tmp_path / "tasks.sqlite",
        yt_dlp_bin="yt-dlp",
    )


@pytest_asyncio.fixture
async def app_ctx(settings: Settings) -> AsyncIterator[AppContext]:
    yt_dlp = FakeYtDlpClient(yt_dlp_bin=settings.yt_dlp_bin, cookies_file=settings.cookies_file)
    tasks = TaskStore(path=settings.state_db_path)
    try:
        yield AppContext(settings=settings, yt_dlp=yt_dlp, tasks=tasks)
    finally:
        tasks.close()
