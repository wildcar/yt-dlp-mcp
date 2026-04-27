"""Tool-surface models. Independent of yt-dlp's internal JSON shape."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class ToolError(_Base):
    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable explanation (English).")


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


class Format(_Base):
    """A single yt-dlp format, trimmed to what the bot actually renders."""

    format_id: str
    ext: str | None = None
    vcodec: str | None = None
    acodec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    filesize_bytes: int | None = None
    is_progressive: bool = Field(
        False,
        description=(
            "True when the format carries both video and audio in one stream "
            "(no muxing required at download time). Browser-playable mp4 "
            "progressive formats are the default download target."
        ),
    )


class Thumbnail(_Base):
    url: str
    width: int | None = None
    height: int | None = None


class Probe(_Base):
    video_id: str
    url: str
    title: str
    duration_seconds: int | None = None
    channel: str | None = None
    channel_url: str | None = None
    uploader: str | None = None
    upload_date: str | None = Field(None, description="YYYYMMDD as yt-dlp returns it.")
    description: str | None = None
    thumbnails: list[Thumbnail] = Field(default_factory=list)
    formats: list[Format] = Field(default_factory=list)
    is_live: bool = False
    age_limit: int = 0


class ProbeResponse(_Base):
    probe: Probe | None = None
    error: ToolError | None = None


# ---------------------------------------------------------------------------
# start_download / get_download_status
# ---------------------------------------------------------------------------


TaskState = Literal[
    "queued",  # task row created, worker not started yet
    "running",  # yt-dlp subprocess is live
    "complete",  # file finalised at output_path
    "failed",  # yt-dlp exited non-zero, see `error`
    "cancelled",  # explicitly stopped via stop_download
]


class TaskInfo(_Base):
    task_id: str
    url: str
    video_id: str | None = None
    title: str | None = None
    channel: str | None = None
    state: TaskState
    progress_pct: float = Field(0.0, ge=0.0, le=100.0)
    downloaded_bytes: int = Field(0, ge=0)
    total_bytes: int | None = None
    output_path: str | None = Field(
        None,
        description="Absolute path of the finished file. Populated only on state=complete.",
    )
    eta_seconds: int | None = None
    speed_bps: float | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class StartDownloadResponse(_Base):
    task: TaskInfo | None = None
    error: ToolError | None = None


class GetDownloadStatusResponse(_Base):
    task: TaskInfo | None = None
    error: ToolError | None = None


# ---------------------------------------------------------------------------
# list_playlist
# ---------------------------------------------------------------------------


class PlaylistEntry(_Base):
    video_id: str
    title: str
    url: str
    duration_seconds: int | None = None
    thumbnail_url: str | None = None


class ListPlaylistResponse(_Base):
    playlist_id: str | None = None
    playlist_title: str | None = None
    total_entries: int = 0
    entries: list[PlaylistEntry] = Field(default_factory=list)
    error: ToolError | None = None


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class HealthCheck(_Base):
    yt_dlp_version: str
    yt_dlp_bin: str
    cookies_file: str | None = None
    cookies_expires_at_min: str | None = Field(
        None, description="ISO-8601 timestamp of the first auth-relevant cookie that expires."
    )
    cookies_warn_days_left: int | None = Field(
        None,
        description=(
            "Days until the soonest auth-relevant cookie expires. <14 → warn the operator."
        ),
    )
    output_dir: str
    output_dir_writable: bool
    sample_probe_ok: bool = Field(
        False,
        description="True when a probe of a stable canary YouTube URL returned a video id.",
    )
    sample_probe_detail: str | None = None


class HealthCheckResponse(_Base):
    health: HealthCheck | None = None
    error: ToolError | None = None
