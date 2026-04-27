"""Thin async wrapper around the yt-dlp CLI.

We shell out instead of using the Python API for two reasons:
- Each download runs as a detached subprocess, so killing it (e.g. via
  ``stop_download``) doesn't risk taking the MCP process down.
- ``systemctl restart yt-dlp-mcp`` after the daily updater can swap the
  yt-dlp binary without us holding a stale Python module in memory.

The price is parsing JSONL progress on stdout — the format is stable
since yt-dlp 2023.07 and well-documented (`--progress-template`).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# Format selector: prefer a single progressive H.264+AAC mp4 (browser
# plays without remux), then mp4 video + m4a audio that ffmpeg can mux
# stream-copy into mp4, then anything ffmpeg can produce. The trailing
# `/b` is the absolute fallback so yt-dlp doesn't error on weird sources.
DEFAULT_FORMAT_SELECTOR = (
    "(bv[vcodec~='^(avc1|h264)']+ba[ext=m4a])/b[vcodec~='^(avc1|h264)'][ext=mp4]/b[ext=mp4]/b"
)


class YtDlpError(Exception):
    """yt-dlp exited non-zero or returned malformed JSON."""


@dataclass
class ProgressLine:
    """One progress event parsed from yt-dlp's stdout."""

    state: str  # 'downloading' / 'finished' / 'post_processing'
    progress_pct: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    eta_seconds: int | None = None
    speed_bps: float | None = None
    output_path: str | None = None  # set on 'finished'


# `--progress-template` emits one JSONL line per tick. We ask for the
# canonical fields explicitly so the parser doesn't depend on yt-dlp's
# default human-readable output.
_PROGRESS_TEMPLATE = (
    "download:"
    '{"state":"downloading",'
    '"downloaded_bytes":%(progress.downloaded_bytes)d,'
    '"total_bytes":%(progress.total_bytes)d,'
    '"total_bytes_estimate":%(progress.total_bytes_estimate)d,'
    '"eta":%(progress.eta)d,'
    '"speed":%(progress.speed)f,'
    '"filename":%(info.filename)j}'
)
_FINISHED_TEMPLATE = 'post_hooks:{"state":"finished","filename":%(info.filename)j}'


@dataclass
class YtDlpClient:
    yt_dlp_bin: str = "yt-dlp"
    cookies_file: Path | None = None

    async def probe(self, url: str) -> dict[str, Any]:
        """Run ``yt-dlp -J`` (full JSON metadata, no download).

        Returns the raw dict. Raises ``YtDlpError`` on non-zero exit.
        """
        argv = [self.yt_dlp_bin, "-J", "--no-warnings", "--no-playlist"]
        argv.extend(self._cookie_args())
        argv.append(url)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise YtDlpError(_clean_stderr(stderr) or "yt-dlp probe failed")
        try:
            return json.loads(stdout)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise YtDlpError(f"yt-dlp returned non-JSON: {exc}") from exc

    async def list_playlist(self, url: str, *, limit: int) -> dict[str, Any]:
        """Flat-extract a playlist; one JSON line per entry."""
        argv = [
            self.yt_dlp_bin,
            "--flat-playlist",
            "-J",
            "--no-warnings",
            "--playlist-end",
            str(limit),
        ]
        argv.extend(self._cookie_args())
        argv.append(url)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise YtDlpError(_clean_stderr(stderr) or "yt-dlp playlist fetch failed")
        try:
            return json.loads(stdout)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise YtDlpError(f"yt-dlp returned non-JSON: {exc}") from exc

    def spawn_download(
        self,
        url: str,
        *,
        output_path: Path,
        format_selector: str = DEFAULT_FORMAT_SELECTOR,
    ) -> DownloadProcess:
        """Start a yt-dlp download. Returns a handle for progress polling.

        The output path is fully resolved upfront (channel slug + title
        slug already applied), so we hand yt-dlp a literal ``-o`` instead
        of a template. ``--no-mtime`` keeps the on-disk file's mtime as
        the download time, not the upload time, so the bot's poller can
        spot fresh writes deterministically.
        """
        argv = [
            self.yt_dlp_bin,
            "--no-warnings",
            "--no-playlist",
            "--no-mtime",
            "-f",
            format_selector,
            "--merge-output-format",
            "mp4",
            "-o",
            str(output_path),
            "--newline",
            "--progress",
            "--progress-template",
            _PROGRESS_TEMPLATE,
            "--progress-template",
            _FINISHED_TEMPLATE,
        ]
        argv.extend(self._cookie_args())
        argv.append(url)
        return DownloadProcess(argv=argv, output_path=output_path)

    def _cookie_args(self) -> list[str]:
        if self.cookies_file is None:
            return []
        return ["--cookies", str(self.cookies_file)]

    async def version(self) -> str:
        proc = await asyncio.create_subprocess_exec(
            self.yt_dlp_bin,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            raise YtDlpError("yt-dlp --version failed")
        return stdout.decode().strip()


@dataclass
class DownloadProcess:
    """Handle to a running yt-dlp download.

    The MCP `start_download` tool spawns the process via
    :meth:`YtDlpClient.spawn_download` and stores this handle in memory
    so subsequent ``get_download_status`` / ``stop_download`` calls have
    something to query without re-shelling-out.
    """

    argv: list[str]
    output_path: Path
    proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self.proc is not None:
            return
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def iter_progress(self) -> AsyncIterator[ProgressLine]:
        """Yield one ``ProgressLine`` per stdout event until yt-dlp exits.

        Lines that aren't our progress JSON (yt-dlp's own banners,
        merge-stage chatter) are silently ignored.
        """
        assert self.proc is not None and self.proc.stdout is not None
        while True:
            raw = await self.proc.stdout.readline()
            if not raw:
                return
            text = raw.decode("utf-8", errors="replace").strip()
            parsed = _parse_progress_line(text)
            if parsed is not None:
                yield parsed

    async def wait(self) -> int:
        assert self.proc is not None
        rc = await self.proc.wait()
        return rc

    async def kill(self) -> None:
        if self.proc is None or self.proc.returncode is not None:
            return
        self.proc.kill()
        await self.proc.wait()


_PROGRESS_RE = re.compile(r"^(?:download|post_hooks):(\{.*\})$")


def _parse_progress_line(text: str) -> ProgressLine | None:
    m = _PROGRESS_RE.match(text)
    if m is None:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    state = str(data.get("state") or "")
    if state == "finished":
        return ProgressLine(state="finished", output_path=data.get("filename"))
    if state != "downloading":
        return None

    total = data.get("total_bytes")
    if not isinstance(total, int) or total <= 0:
        total_est = data.get("total_bytes_estimate")
        total = total_est if isinstance(total_est, int) and total_est > 0 else None

    downloaded = int(data.get("downloaded_bytes") or 0)
    pct = (downloaded / total * 100.0) if total else 0.0

    return ProgressLine(
        state="downloading",
        progress_pct=round(pct, 1),
        downloaded_bytes=downloaded,
        total_bytes=total,
        eta_seconds=int(data["eta"]) if isinstance(data.get("eta"), int) else None,
        speed_bps=float(data["speed"]) if isinstance(data.get("speed"), int | float) else None,
    )


def _clean_stderr(stderr: bytes) -> str:
    text = stderr.decode("utf-8", errors="replace").strip()
    # yt-dlp prefixes most messages with "ERROR:" — drop it for tidier
    # MCP error envelopes.
    return re.sub(r"^ERROR:\s*", "", text, flags=re.MULTILINE)


__all__ = [
    "DEFAULT_FORMAT_SELECTOR",
    "DownloadProcess",
    "ProgressLine",
    "YtDlpClient",
    "YtDlpError",
]
