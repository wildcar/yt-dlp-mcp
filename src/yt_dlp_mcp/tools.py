"""MCP tool implementations.

Five tools:

- ``probe(url)`` — metadata + format list, no download
- ``start_download(url, format_selector?)`` — kick off a yt-dlp run, returns task_id
- ``get_download_status(task_id)`` — progress / final state
- ``list_playlist(url, limit?)`` — flat playlist preview
- ``health_check()`` — yt-dlp version, cookies state, output dir, canary probe

Internal helpers (cookie-expiry parsing, slug allocation) stay private.
"""

from __future__ import annotations

import asyncio
import http.cookiejar
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from .clients.ytdlp import (
    DEFAULT_FORMAT_SELECTOR,
    DownloadProcess,
    YtDlpError,
)
from .context import AppContext
from .models import (
    Format,
    GetDownloadStatusResponse,
    HealthCheck,
    HealthCheckResponse,
    ListPlaylistResponse,
    PlaylistEntry,
    Probe,
    ProbeResponse,
    StartDownloadResponse,
    TaskInfo,
    Thumbnail,
    ToolError,
)
from .slug import allocate_output_path

log = structlog.get_logger(__name__)


# Stable canary URL used by health_check. Picked deliberately: short
# (so probe finishes fast), long-lived (Google's "Me at the zoo" — the
# very first YouTube video, online since 2005), CC license so re-checks
# don't tickle copyright systems.
_HEALTH_CHECK_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


async def probe_impl(ctx: AppContext, url: str) -> ProbeResponse:
    if not url or not url.strip():
        return ProbeResponse(
            error=ToolError(code="invalid_argument", message="`url` must not be empty.")
        )
    try:
        raw = await ctx.yt_dlp.probe(url)
    except YtDlpError as exc:
        return ProbeResponse(error=ToolError(code="upstream_error", message=str(exc)))

    return ProbeResponse(probe=_to_probe(raw))


def _to_probe(raw: dict[str, Any]) -> Probe:
    formats: list[Format] = []
    for f in raw.get("formats") or []:
        if not isinstance(f, dict):
            continue
        format_id = str(f.get("format_id") or "")
        if not format_id:
            continue
        vcodec = str(f.get("vcodec") or "") or None
        acodec = str(f.get("acodec") or "") or None
        is_progressive = (
            vcodec is not None and acodec is not None and vcodec != "none" and acodec != "none"
        )
        formats.append(
            Format(
                format_id=format_id,
                ext=f.get("ext"),
                vcodec=vcodec,
                acodec=acodec,
                width=_int_or_none(f.get("width")),
                height=_int_or_none(f.get("height")),
                fps=_float_or_none(f.get("fps")),
                filesize_bytes=_int_or_none(f.get("filesize") or f.get("filesize_approx")),
                is_progressive=is_progressive,
            )
        )

    thumbnails: list[Thumbnail] = []
    for th in raw.get("thumbnails") or []:
        if not isinstance(th, dict):
            continue
        url = th.get("url")
        if not isinstance(url, str):
            continue
        thumbnails.append(
            Thumbnail(
                url=url,
                width=_int_or_none(th.get("width")),
                height=_int_or_none(th.get("height")),
            )
        )

    return Probe(
        video_id=str(raw.get("id") or ""),
        url=str(raw.get("webpage_url") or raw.get("original_url") or ""),
        title=str(raw.get("title") or ""),
        duration_seconds=_int_or_none(raw.get("duration")),
        channel=raw.get("channel") or raw.get("uploader"),
        channel_url=raw.get("channel_url") or raw.get("uploader_url"),
        uploader=raw.get("uploader"),
        upload_date=raw.get("upload_date"),
        description=raw.get("description"),
        thumbnails=thumbnails,
        formats=formats,
        is_live=bool(raw.get("is_live")),
        age_limit=int(raw.get("age_limit") or 0),
    )


# ---------------------------------------------------------------------------
# start_download
# ---------------------------------------------------------------------------


async def start_download_impl(
    ctx: AppContext,
    url: str,
    *,
    format_selector: str | None = None,
) -> StartDownloadResponse:
    if not url or not url.strip():
        return StartDownloadResponse(
            error=ToolError(code="invalid_argument", message="`url` must not be empty.")
        )

    try:
        raw = await ctx.yt_dlp.probe(url)
    except YtDlpError as exc:
        return StartDownloadResponse(error=ToolError(code="probe_failed", message=str(exc)))

    probe = _to_probe(raw)
    if not probe.video_id:
        return StartDownloadResponse(
            error=ToolError(code="invalid_argument", message="probe returned no video id.")
        )
    if probe.is_live:
        return StartDownloadResponse(
            error=ToolError(code="unsupported", message="live streams are not supported.")
        )

    # Re-use a prior on-disk file for the same URL when one exists. yt-dlp
    # with --no-overwrites (its CLI default) will see the file already
    # there and skip the actual download — the post-hooks still fire,
    # the worker still records output_path, and the caller's poller
    # registers the unchanged file with media-watch as usual. Without
    # this lookup, allocate_output_path would invent a fresh
    # `<stem>-2.mp4` sibling and yt-dlp would re-download to that path.
    prior = ctx.tasks.find_complete_by_url(url)
    prior_path = (prior or {}).get("output_path")
    if prior_path and await asyncio.to_thread(_file_with_content, prior_path):
        output_path = Path(prior_path)
    else:
        output_path = allocate_output_path(
            ctx.settings.output_dir,
            channel=probe.channel or "unknown",
            title=probe.title or probe.video_id,
            video_id=probe.video_id,
            extension="mp4",
        )

    task_id = secrets.token_hex(8)
    ctx.tasks.insert(task_id=task_id, url=url)
    ctx.tasks.update(
        task_id,
        video_id=probe.video_id,
        title=probe.title,
        channel=probe.channel,
    )

    selector = format_selector or DEFAULT_FORMAT_SELECTOR
    handle = ctx.yt_dlp.spawn_download(url, output_path=output_path, format_selector=selector)
    ctx.procs[task_id] = handle
    # Fire-and-forget: the worker writes its terminal state into the
    # SQLite task store. We hold a strong ref on AppContext (asyncio
    # only weak-refs tasks; without this the GC may collect a worker
    # mid-run) and drop it on completion via a done-callback.
    bg = asyncio.create_task(_run_download(ctx, task_id, handle))
    ctx.background_tasks.add(bg)
    bg.add_done_callback(ctx.background_tasks.discard)

    snapshot = ctx.tasks.get(task_id)
    if snapshot is None:
        return StartDownloadResponse(
            error=ToolError(code="internal_error", message="task disappeared mid-flight")
        )
    return StartDownloadResponse(task=_row_to_task(snapshot))


async def _run_download(ctx: AppContext, task_id: str, handle: DownloadProcess) -> None:
    try:
        await handle.start()
    except Exception as exc:
        log.warning("ytdlp.spawn_failed", task_id=task_id, error=str(exc))
        ctx.tasks.update(task_id, state="failed", error=str(exc))
        ctx.procs.pop(task_id, None)
        return

    ctx.tasks.update(task_id, state="running")

    try:
        async for line in handle.iter_progress():
            ctx.tasks.update(
                task_id,
                progress_pct=line.progress_pct,
                downloaded_bytes=line.downloaded_bytes,
                total_bytes=line.total_bytes,
                eta_seconds=line.eta_seconds,
                speed_bps=line.speed_bps,
            )
    except Exception as exc:
        log.exception("ytdlp.progress_failed", task_id=task_id, error=str(exc))

    rc = await handle.wait()
    ctx.procs.pop(task_id, None)

    # yt-dlp 2026.03 sometimes exits non-zero from cleanup paths (e.g.
    # save_cookies hits a read-only file) *after* the download already
    # finished. Trust the on-disk file: when the literal -o path we
    # gave yt-dlp exists and is non-empty, we got the bytes regardless
    # of what yt-dlp's exit code says.
    final_path = str(handle.output_path)
    on_disk = bool(final_path) and await asyncio.to_thread(_file_with_content, final_path)

    if rc == 0 or on_disk:
        ctx.tasks.update(
            task_id,
            state="complete",
            progress_pct=100.0,
            output_path=final_path,
        )
        return

    # No file → real failure. Pull stderr for a useful error envelope.
    stderr_bytes = b""
    if handle.proc is not None and handle.proc.stderr is not None:
        try:
            stderr_bytes = await handle.proc.stderr.read()
        except Exception:
            stderr_bytes = b""
    msg = stderr_bytes.decode("utf-8", errors="replace").strip() or f"exit code {rc}"
    ctx.tasks.update(task_id, state="failed", error=msg[:2000])


# ---------------------------------------------------------------------------
# get_download_status
# ---------------------------------------------------------------------------


async def get_download_status_impl(ctx: AppContext, task_id: str) -> GetDownloadStatusResponse:
    if not task_id:
        return GetDownloadStatusResponse(
            error=ToolError(code="invalid_argument", message="`task_id` must not be empty.")
        )
    row = ctx.tasks.get(task_id)
    if row is None:
        return GetDownloadStatusResponse(
            error=ToolError(code="not_found", message=f"no task with id {task_id}")
        )
    return GetDownloadStatusResponse(task=_row_to_task(row))


# ---------------------------------------------------------------------------
# list_playlist
# ---------------------------------------------------------------------------


async def list_playlist_impl(
    ctx: AppContext, url: str, *, limit: int | None = None
) -> ListPlaylistResponse:
    if not url or not url.strip():
        return ListPlaylistResponse(
            error=ToolError(code="invalid_argument", message="`url` must not be empty.")
        )
    actual_limit = (
        limit if isinstance(limit, int) and limit > 0 else ctx.settings.playlist_preview_limit
    )
    try:
        raw = await ctx.yt_dlp.list_playlist(url, limit=actual_limit)
    except YtDlpError as exc:
        return ListPlaylistResponse(error=ToolError(code="upstream_error", message=str(exc)))

    entries: list[PlaylistEntry] = []
    raw_entries = raw.get("entries") or []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "")
        if not video_id:
            continue
        url_val = entry.get("url") or entry.get("webpage_url")
        if not isinstance(url_val, str) or not url_val:
            url_val = f"https://www.youtube.com/watch?v={video_id}"
        thumbs = entry.get("thumbnails") or []
        thumb_url = None
        if isinstance(thumbs, list) and thumbs:
            first = thumbs[0]
            if isinstance(first, dict):
                t = first.get("url")
                if isinstance(t, str):
                    thumb_url = t
        entries.append(
            PlaylistEntry(
                video_id=video_id,
                title=str(entry.get("title") or ""),
                url=url_val,
                duration_seconds=_int_or_none(entry.get("duration")),
                thumbnail_url=thumb_url,
            )
        )

    return ListPlaylistResponse(
        playlist_id=raw.get("id"),
        playlist_title=raw.get("title"),
        total_entries=int(raw.get("playlist_count") or len(entries)),
        entries=entries,
    )


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


async def health_check_impl(ctx: AppContext) -> HealthCheckResponse:
    try:
        version = await ctx.yt_dlp.version()
    except YtDlpError as exc:
        return HealthCheckResponse(error=ToolError(code="ytdlp_missing", message=str(exc)))

    cookies_iso, days_left = _cookies_expiry(ctx.settings.cookies_file)

    output_dir = ctx.settings.output_dir
    output_writable = _path_is_writable(output_dir)

    sample_ok = False
    sample_detail: str | None = None
    try:
        raw = await ctx.yt_dlp.probe(_HEALTH_CHECK_URL)
        sample_ok = bool(raw.get("id"))
    except YtDlpError as exc:
        sample_detail = str(exc)

    return HealthCheckResponse(
        health=HealthCheck(
            yt_dlp_version=version,
            yt_dlp_bin=ctx.settings.yt_dlp_bin,
            cookies_file=str(ctx.settings.cookies_file) if ctx.settings.cookies_file else None,
            cookies_expires_at_min=cookies_iso,
            cookies_warn_days_left=days_left,
            output_dir=str(output_dir),
            output_dir_writable=output_writable,
            sample_probe_ok=sample_ok,
            sample_probe_detail=sample_detail,
        )
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row_to_task(row: dict[str, Any]) -> TaskInfo:
    return TaskInfo(
        task_id=str(row["task_id"]),
        url=str(row["url"]),
        video_id=row.get("video_id"),
        title=row.get("title"),
        channel=row.get("channel"),
        state=row["state"],
        progress_pct=float(row.get("progress_pct") or 0.0),
        downloaded_bytes=int(row.get("downloaded_bytes") or 0),
        total_bytes=row.get("total_bytes"),
        output_path=row.get("output_path"),
        eta_seconds=row.get("eta_seconds"),
        speed_bps=row.get("speed_bps"),
        error=row.get("error"),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _file_with_content(path: str) -> bool:
    try:
        st = Path(path).stat()
    except OSError:
        return False
    return st.st_size > 0


def _int_or_none(v: Any) -> int | None:
    return int(v) if isinstance(v, int | float) else None


def _float_or_none(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) else None


# Cookies whose expiry actually matters for YouTube auth. SAPISID is the
# heaviest signal: when it's gone, every member-only / age-gated probe
# starts failing. LOGIN_INFO is the long-lived backup. Other auth-side
# cookies (HSID, SSID, …) usually share the same expiry as SAPISID.
_AUTH_COOKIE_NAMES = frozenset({"SAPISID", "__Secure-1PSID", "LOGIN_INFO"})


def _cookies_expiry(path: Path | None) -> tuple[str | None, int | None]:
    """Read a Netscape cookies.txt and return ``(iso, days_left)`` for
    the soonest-expiring auth cookie. ``(None, None)`` when no cookies
    file is configured or no auth-side cookie is found."""
    if path is None or not path.is_file():
        return None, None
    jar = http.cookiejar.MozillaCookieJar(str(path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except (OSError, http.cookiejar.LoadError):
        return None, None

    soonest: int | None = None
    for cookie in jar:
        if cookie.name not in _AUTH_COOKIE_NAMES:
            continue
        if cookie.expires is None:
            continue
        if soonest is None or cookie.expires < soonest:
            soonest = cookie.expires
    if soonest is None:
        return None, None
    iso = datetime.fromtimestamp(soonest, tz=UTC).isoformat(timespec="seconds")
    delta = soonest - int(datetime.now(UTC).timestamp())
    return iso, max(0, delta // 86400)


def _path_is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    probe = path / ".__yt_dlp_mcp_write_probe"
    try:
        probe.write_text("")
        probe.unlink(missing_ok=True)
    except OSError:
        return False
    return True


__all__ = [
    "get_download_status_impl",
    "health_check_impl",
    "list_playlist_impl",
    "probe_impl",
    "start_download_impl",
]
