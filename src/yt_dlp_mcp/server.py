"""MCP entrypoint: registers the five tools and starts the transport."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Final

import structlog
from mcp.server.fastmcp import FastMCP

from . import __version__
from .config import Settings, get_settings
from .context import AppContext, build_app_context
from .models import (
    GetDownloadStatusResponse,
    HealthCheckResponse,
    ListPlaylistResponse,
    ProbeResponse,
    StartDownloadResponse,
)
from .tools import (
    get_download_status_impl,
    health_check_impl,
    list_playlist_impl,
    probe_impl,
    start_download_impl,
)

_SUPPORTED_TRANSPORTS: Final[frozenset[str]] = frozenset({"stdio", "sse", "streamable-http"})


def _configure_logging() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def build_server(ctx: AppContext) -> FastMCP:
    mcp = FastMCP(
        name="yt-dlp-mcp",
        host=os.environ.get("MCP_HTTP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MCP_HTTP_PORT", "8769")),
        instructions=(
            "Downloads videos via yt-dlp (YouTube and 1800+ supported sites). "
            "Use probe(url) for metadata, start_download(url) to enqueue a "
            "background download (returns task_id), and get_download_status("
            "task_id) to poll progress. list_playlist(url) gives a flat "
            "preview of the first N entries. health_check() reports yt-dlp "
            "version, cookie freshness, and a canary probe."
        ),
    )

    async def probe(url: str) -> ProbeResponse:
        """Return metadata + format list for ``url`` without downloading."""
        return await probe_impl(ctx, url)

    async def start_download(url: str, format_selector: str | None = None) -> StartDownloadResponse:
        """Enqueue a download. Returns ``task_id`` to poll via get_download_status."""
        return await start_download_impl(ctx, url, format_selector=format_selector)

    async def get_download_status(task_id: str) -> GetDownloadStatusResponse:
        """Return the current state, progress, and (on completion) output_path."""
        return await get_download_status_impl(ctx, task_id)

    async def list_playlist(url: str, limit: int | None = None) -> ListPlaylistResponse:
        """Flat-extract a playlist; preview at most ``limit`` entries (default 20)."""
        return await list_playlist_impl(ctx, url, limit=limit)

    async def health_check() -> HealthCheckResponse:
        """Report yt-dlp version, cookies state, output dir, and a canary probe."""
        return await health_check_impl(ctx)

    mcp.tool()(probe)
    mcp.tool()(start_download)
    mcp.tool()(get_download_status)
    mcp.tool()(list_playlist)
    mcp.tool()(health_check)
    return mcp


async def _run(settings: Settings, transport: str) -> None:
    async with build_app_context(settings) as ctx:
        server = build_server(ctx)
        structlog.get_logger().info("yt_dlp_mcp.starting", version=__version__, transport=transport)
        if transport == "stdio":
            await server.run_stdio_async()
        elif transport == "sse":
            await server.run_sse_async()
        else:
            await server.run_streamable_http_async()


def main() -> None:
    _configure_logging()
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport not in _SUPPORTED_TRANSPORTS:
        raise SystemExit(
            f"Unsupported MCP_TRANSPORT={transport!r}; "
            f"expected one of {sorted(_SUPPORTED_TRANSPORTS)}"
        )
    asyncio.run(_run(get_settings(), transport))


if __name__ == "__main__":
    main()
