"""Tool-level tests with FakeYtDlpClient (no real yt-dlp invocation)."""

from __future__ import annotations

import asyncio

from yt_dlp_mcp.clients.ytdlp import ProgressLine
from yt_dlp_mcp.context import AppContext
from yt_dlp_mcp.tools import (
    get_download_status_impl,
    health_check_impl,
    list_playlist_impl,
    probe_impl,
    start_download_impl,
)

from .conftest import FakeYtDlpClient


async def test_probe_normalises_format_progressivity(app_ctx: AppContext) -> None:
    fake: FakeYtDlpClient = app_ctx.yt_dlp  # type: ignore[assignment]
    fake.probe_payload = {
        "id": "abc",
        "title": "Hello",
        "duration": 90,
        "channel": "Foo",
        "webpage_url": "https://youtu.be/abc",
        "formats": [
            {
                "format_id": "18",
                "ext": "mp4",
                "vcodec": "avc1.42001E",
                "acodec": "mp4a.40.2",
                "width": 640,
                "height": 360,
            },
            {
                "format_id": "137",
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "width": 1920,
                "height": 1080,
            },
        ],
    }
    resp = await probe_impl(app_ctx, "https://youtu.be/abc")
    assert resp.error is None
    assert resp.probe is not None
    assert resp.probe.video_id == "abc"
    progressive = [f for f in resp.probe.formats if f.is_progressive]
    assert [f.format_id for f in progressive] == ["18"]


async def test_probe_rejects_empty_url(app_ctx: AppContext) -> None:
    resp = await probe_impl(app_ctx, "  ")
    assert resp.error is not None
    assert resp.error.code == "invalid_argument"


async def test_start_download_runs_to_completion(app_ctx: AppContext) -> None:
    fake: FakeYtDlpClient = app_ctx.yt_dlp  # type: ignore[assignment]
    fake.probe_payload = {
        "id": "vid42",
        "title": "Hello World",
        "channel": "Veritasium",
        "webpage_url": "https://youtu.be/vid42",
    }
    fake.fake_progress = [
        ProgressLine(
            state="downloading", progress_pct=50.0, downloaded_bytes=500, total_bytes=1000
        ),
    ]

    resp = await start_download_impl(app_ctx, "https://youtu.be/vid42")
    assert resp.error is None
    assert resp.task is not None
    task_id = resp.task.task_id

    # Worker is async; wait for the background task to finish.
    for _ in range(50):
        status = await get_download_status_impl(app_ctx, task_id)
        assert status.task is not None
        if status.task.state in ("complete", "failed"):
            break
        await asyncio.sleep(0.02)
    else:  # pragma: no cover — guard against infinite hang
        raise AssertionError("download did not complete in time")

    assert status.task.state == "complete"
    assert status.task.output_path is not None
    assert status.task.output_path.endswith(".mp4")
    assert "veritasium" in status.task.output_path.lower()


async def test_start_download_rejects_live(app_ctx: AppContext) -> None:
    fake: FakeYtDlpClient = app_ctx.yt_dlp  # type: ignore[assignment]
    fake.probe_payload = {
        "id": "live1",
        "title": "Live now",
        "is_live": True,
    }
    resp = await start_download_impl(app_ctx, "https://youtu.be/live1")
    assert resp.error is not None
    assert resp.error.code == "unsupported"


async def test_get_download_status_not_found(app_ctx: AppContext) -> None:
    resp = await get_download_status_impl(app_ctx, "nope")
    assert resp.error is not None
    assert resp.error.code == "not_found"


async def test_list_playlist_normalises_entries(app_ctx: AppContext) -> None:
    fake: FakeYtDlpClient = app_ctx.yt_dlp  # type: ignore[assignment]
    fake.playlist_payload = {
        "id": "PL1",
        "title": "My picks",
        "playlist_count": 3,
        "entries": [
            {"id": "a1", "title": "First", "duration": 60},
            {
                "id": "a2",
                "title": "Second",
                "duration": 90,
                "thumbnails": [{"url": "https://example/t.jpg"}],
            },
            {"title": "no-id"},  # dropped
        ],
    }
    resp = await list_playlist_impl(app_ctx, "https://youtube.com/playlist?list=PL1")
    assert resp.error is None
    assert resp.total_entries == 3
    assert [e.video_id for e in resp.entries] == ["a1", "a2"]
    assert resp.entries[1].thumbnail_url == "https://example/t.jpg"


async def test_health_check_reports_version_and_writability(app_ctx: AppContext) -> None:
    fake: FakeYtDlpClient = app_ctx.yt_dlp  # type: ignore[assignment]
    fake.probe_payload = {"id": "jNQXAC9IVRw", "title": "Me at the zoo"}
    resp = await health_check_impl(app_ctx)
    assert resp.error is None
    assert resp.health is not None
    assert resp.health.yt_dlp_version == "2025.10.14"
    assert resp.health.output_dir_writable is True
    assert resp.health.sample_probe_ok is True
