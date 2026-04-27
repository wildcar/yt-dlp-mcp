"""Runtime configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Where finished video files land. Subdirs per channel slug
    # (e.g. ``Veritasium/the-trillion-dollar-equation.mp4``); Plex picks
    # them up via its standard library scan, no special structure needed.
    output_dir: Path = Field(Path("/mnt/storage/Media/Video/Clip"))

    # Path to a Netscape-format cookies.txt — required for age-gated /
    # member-only / region-locked YouTube videos. yt-dlp's --cookies flag
    # accepts the file directly. The health_check tool warns when the
    # SAPISID cookie has <14 days left.
    cookies_file: Path | None = None

    # Override which yt-dlp binary to invoke. Defaults to whichever is on
    # PATH; deploy normally points this at the venv-pinned version
    # (`/opt/yt-dlp-mcp/.venv/bin/yt-dlp`) so the systemd update timer
    # bumps it independently of the OS package.
    yt_dlp_bin: str = "yt-dlp"

    # SQLite-backed task store: keeps in-flight download state across
    # service restarts so the bot's poller can re-attach to an unfinished
    # download instead of orphaning it.
    state_db_path: Path = Field(Path(".cache/yt_dlp_mcp.sqlite"))

    # Bearer token for the streamable-HTTP transport. Optional in stdio
    # mode (the local socket is the auth boundary).
    mcp_auth_token: str | None = None

    # Default playlist preview cap. ``list_playlist`` returns at most
    # this many entries even when the upstream playlist is bigger; the
    # caller asks for more explicitly.
    playlist_preview_limit: int = 20

    # How many recent finished tasks to keep in the SQLite store before
    # garbage-collecting on startup. Doesn't affect on-disk video files.
    task_history_keep: int = 500


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
