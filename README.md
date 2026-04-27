# yt-dlp-mcp

MCP server wrapping the [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
CLI. Exposes five tools so a chat agent / bot can:

- `probe(url)` — pull title, duration, channel, thumbnails, and the
  full format list without downloading.
- `start_download(url, format_selector?)` — kick off a background
  yt-dlp run and return a `task_id`. Default format selector targets a
  browser-playable mp4 (H.264 + AAC) so the result is watchable in
  `<video>` without remux.
- `get_download_status(task_id)` — current state, percentage,
  downloaded / total bytes, and (on completion) `output_path`.
- `list_playlist(url, limit?)` — flat-extract a YouTube playlist; the
  bot turns the result into a plain-text list of links and the user
  copies one back into chat to download.
- `health_check()` — yt-dlp version, cookies file expiry, output-dir
  writability, plus a canary probe of a known-good URL.

Designed to live on the same host as `rtorrent-mcp` (the media host),
because that's where the storage is mounted. The MCP listens on
`127.0.0.1:8769` over streamable-HTTP by default; the bot connects via
the same `MCP_AUTH_TOKEN` it already uses.

## Quick local run

```
uv sync --all-groups
uv run yt-dlp-mcp                          # stdio mode
MCP_TRANSPORT=streamable-http uv run yt-dlp-mcp   # 127.0.0.1:8769
```

Smoke-test the live tool surface via `npx @modelcontextprotocol/inspector`.

## Configuration

All settings come from env vars (see `.env.example`):

| Variable                     | Purpose                                                              |
|------------------------------|----------------------------------------------------------------------|
| `OUTPUT_DIR`                 | Where finished videos land. Default `/mnt/storage/Media/Video/Clip`. |
| `COOKIES_FILE`               | Netscape `cookies.txt` for age-gated / member-only YouTube videos.   |
| `YT_DLP_BIN`                 | Path to yt-dlp binary. Default `yt-dlp` (PATH).                      |
| `STATE_DB_PATH`              | SQLite for in-flight tasks. Default `.cache/yt_dlp_mcp.sqlite`.      |
| `MCP_AUTH_TOKEN`             | Bearer token for streamable-HTTP transport.                          |
| `MCP_HTTP_HOST` / `_PORT`    | Listen address. Default `127.0.0.1:8769`.                            |
| `MCP_TRANSPORT`              | `stdio` (default), `sse`, or `streamable-http`.                      |
| `PLAYLIST_PREVIEW_LIMIT`     | Default cap for `list_playlist`. Default `20`.                       |
| `TASK_HISTORY_KEEP`          | Recent finished tasks kept in SQLite. Default `500`.                 |

## Deploy

End-to-end deploy on the media host (Ubuntu 22.04+) is documented in
[`env.md`](./env.md) — covers OS prerequisites (Python 3.11+, ffmpeg,
Node.js for JS-based extractors, the cookies file), systemd unit
files, and the auto-update timer that pulls a fresh `yt-dlp` once a
day. Read it before the first install.

## Composite media-id

Downloads register on `media-watch-web` under `yt-<video_id>` (or
`dl-<sha1(url)[:12]>` for non-YouTube sources where there's no canonical
short id). The schema is the same as for rutracker downloads — the
prefix prevents collisions between sources. See the workspace-level
`AGENTS-SUMMARY.md` for the full pipeline.
