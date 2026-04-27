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

    # JS runtime yt-dlp should use for the YouTube player-response
    # decode and PO Token solver. yt-dlp 2026.03+ defaults to deno (not
    # node) and refuses to fall back silently — without this, every
    # YouTube probe hits «No supported JavaScript runtime». Set to a
    # comma-separated list when multiple runtimes are installed; pass
    # `node:/usr/bin/node` to pin a specific binary.
    js_runtimes: str = "node"

    # The n-challenge solver (which decrypts streaming URLs) is no
    # longer bundled with yt-dlp 2026.03+ — it lives in a separate
    # `ejs` package fetched from GitHub on demand. Without this flag
    # YouTube returns «No video formats found». yt-dlp caches the
    # download in its user cache dir, so this is a one-time network
    # cost per refresh. Set empty to disable the auto-fetch (e.g. if
    # the host has no outbound github.com access — then deploy the
    # solver manually and point yt-dlp at it via its own config).
    remote_components: str = "ejs:github"

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
