# yt-dlp-mcp — repo functional & technical specification

Source of truth for *what this server does* and *how it is built*. Cross-repo
contract lives in `../AGENTS/SPEC.md`; this is the repo-local detail.

## Purpose

MCP server wrapping the [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) CLI. Gives a
chat agent / bot a mid-pipeline "download by URL" path: probe a pasted video URL,
optionally expand a playlist, kick off a background download, and poll progress.
Covers YouTube plus ~1800 other yt-dlp-supported sites. Lives on the media host
(`homesrv`, public name `v.wildcar.ru`) because that's where storage is mounted; the bot reaches it at
`http://wildcar.ru:8769/mcp` with the shared `MCP_AUTH_TOKEN`.

Package: `yt_dlp_mcp` (`src/yt_dlp_mcp/`). Entry point: `yt-dlp-mcp` →
`yt_dlp_mcp.server:main`.

## Stack

- Python ≥ 3.11, `asyncio`. MCP via the official Anthropic `mcp` SDK (`FastMCP`).
- `pydantic` v2 tool models; `pydantic-settings` for config (`.env`).
- `structlog` (JSON to stderr). Task store on stdlib `sqlite3` (WAL).
- Engine: shells out to the `yt-dlp` CLI as a **detached subprocess** (not the
  Python API) so kills don't take the MCP down and the daily updater can swap the
  binary under a running service. Requires `ffmpeg` (mux) and `node` (JS runtime).
- Dev: `ruff` (line 100), `mypy --strict`, `pytest` + `pytest-asyncio`. Deps via `uv`.

## Tools

All tools return an envelope `{ <payload> | error: ToolError(code, message) }` —
structured errors, never raised exceptions across the boundary. Registered in
`server.py`; impls in `tools.py`.

- `probe(url) -> ProbeResponse{ probe: Probe | None, error }`
  — `yt-dlp -J`, no download. `Probe` carries `video_id`, `url`, `title`,
  `duration_seconds`, `channel`, `uploader`, `upload_date`, `description`,
  `thumbnails[]`, `formats[]` (with `is_progressive`), `is_live`, `age_limit`.
  The subprocess is terminated after `PROBE_TIMEOUT_SECONDS` (default 30) and
  returns a structured `upstream_error`, so callers never wait indefinitely.
- `list_playlist(url, limit?) -> ListPlaylistResponse{ playlist_id, playlist_title,
  total_entries, entries[], error }`
  — `--flat-playlist -J --playlist-end <limit>`; `limit` defaults to
  `PLAYLIST_PREVIEW_LIMIT` (20). Bot renders a plain-text link list; the user copies
  one back to download.
- `start_download(url, format_selector?) -> StartDownloadResponse{ task: TaskInfo |
  None, error }`
  — reuses a successful `probe` for the same URL from the preceding 10 minutes,
  otherwise probes first (rejects empty URL / no video id / live streams), allocates
  an output path, spawns yt-dlp in the background, returns a `task_id` (16-char hex,
  `secrets.token_hex(8)`). The short-lived cache avoids a duplicate YouTube metadata
  request between preview and confirmation. Default selector targets browser-playable
  mp4 (H.264+AAC), see below.
- `get_download_status(task_id) -> GetDownloadStatusResponse{ task: TaskInfo | None,
  error }`
  — reads the SQLite row. `TaskInfo.state ∈ {queued, running, complete, failed,
  cancelled}`; `progress_pct`, `downloaded_bytes`, `total_bytes`, `eta_seconds`,
  `speed_bps`, and `output_path` (set only on `complete`).
- `health_check() -> HealthCheckResponse{ health: HealthCheck | None, error }`
  — yt-dlp version + bin path, cookies expiry (`cookies_warn_days_left`, <14 →
  rotate), output-dir writability, and a canary probe of a stable URL
  ("Me at the zoo", `jNQXAC9IVRw`).

### Default format selector

`(bv[avc1|h264]+ba[m4a])/b[avc1|h264][mp4]/b[mp4]/b` — prefers progressive H.264+AAC
mp4 (browser-playable, no remux), then mp4 video + m4a audio that ffmpeg stream-copies
into mp4, then any mp4, then anything. `--merge-output-format mp4`, `--no-mtime` (file
mtime = download time so the bot poller spots fresh writes), `--no-playlist`.

## `tasks.sqlite` lifecycle store

`STATE_DB_PATH` (default `.cache/yt_dlp_mcp.sqlite`). One table `tasks` keyed by
`task_id`, carrying everything `TaskInfo` returns (url, video_id, title, channel,
state, progress, byte counts, output_path, error, timestamps). WAL + `synchronous=
NORMAL`. Persisted so a service restart still exposes terminal state to the bot's
poller instead of orphaning an in-flight download. `gc_history(keep)` trims finished
rows to the most recent `TASK_HISTORY_KEEP` (500) on startup; active rows untouched.

### Idempotent re-paste

`start_download` calls `find_complete_by_url(url)`: if a prior `complete` row's
`output_path` still exists on disk (non-empty), it reuses that exact path instead of
allocating a `-2`/`-3` collision sibling. yt-dlp's `--no-overwrites` (CLI default)
then sees the file and skips the actual download; the worker still records
`output_path` and the bot re-registers the unchanged file. Cheap re-paste, no
re-download.

## media_id shapes it feeds

The cross-server `media_id` is `<source>-<id>`. This server doesn't compose it — it
emits the raw `video_id` (from yt-dlp) and a `task_id`. The **bot** derives the
media-id at media-watch register time:

- `yt-<video_id>` — YouTube downloads (canonical short id).
- `dl-<sha1(url)[:12]>` — non-YouTube sources with no canonical short id.

The `task_id` (16-char lower hex) is what `get_download_status` takes and what the
bot stores in `downloads.info_hash` for yt-dlp rows (overloaded column — BT hashes
are 40-char upper hex).

## Output layout

Files land in `OUTPUT_DIR` (default `/mnt/storage/Media/Video/Clip`), one subdir per
channel slug: `<channel-slug>/<title-slug>.mp4`. Slugs in `slug.py` keep **Unicode**
(Cyrillic, accents — ext4 + Plex handle it); they only strip filesystem-unsafe
characters (`\ / : * ? " < > | #`, control chars), collapse whitespace, and cap at
UTF-8 byte counts (200 name / 150 channel, leaving room for `-2` suffix + `.mp4`).
Empty channel → `Без канала`; empty title → falls back to `video_id`.

## yt-dlp 2026.03 runtime gotchas

These are the load-bearing operational facts — also in `AGENTS/MEMORY.md`.

- **JS runtime + remote EJS solver.** yt-dlp 2026.03+ defaults to deno-only and ships
  no bundled n-challenge solver. Every invocation passes `--js-runtimes node`
  (`JS_RUNTIMES`, default `node`) + `--remote-components ejs:github`
  (`REMOTE_COMPONENTS`, default `ejs:github`). Without these, YouTube extraction logs
  "No supported JavaScript runtime" / "No video formats found". Host needs `node`
  installed and one-time github.com egress to fetch the EJS solver (yt-dlp caches it).
- **Non-zero exit on cleanup.** yt-dlp 2026.03 sometimes exits non-zero from cleanup
  paths (e.g. `save_cookies` on a read-only file) *after* the bytes are on disk. The
  worker trusts `Path(output_path).is_file() && size > 0` over the exit code — both
  for `probe`/`list_playlist` (valid JSON on stdout is authoritative regardless of
  RC) and for download completion.
- **Cookies writability.** systemd `ProtectSystem=strict` blocks writes to
  `/etc/yt-dlp-mcp/cookies.txt`; the unit adds `ReadWritePaths=-/etc/yt-dlp-mcp`.
- **`NA` sentinel.** yt-dlp 2026.03 occasionally leaks an unquoted `NA` token in
  progress JSON; `_parse_progress_line` rewrites `:NA` → `:null` before parsing.

## Project structure

```
src/yt_dlp_mcp/
  server.py        — FastMCP entrypoint, registers the 5 tools, picks transport
  tools.py         — tool impls + helpers (cookie expiry, path alloc)
  models.py        — Pydantic tool I/O models (frozen schemas)
  clients/ytdlp.py — async yt-dlp CLI wrapper: probe / list / spawn_download, progress JSONL
  tasks.py         — TaskStore (sqlite3 lifecycle store)
  slug.py          — Unicode-safe filename / channel slug allocation
  config.py        — Settings (pydantic-settings, .env)
  context.py       — AppContext wiring (client + store + settings + bg tasks)
tests/             — FakeYtDlpClient + canned payloads
deploy/            — yt-dlp-mcp.service, yt-dlp-mcp-update.{service,timer}
```

## Configuration

Env vars (`.env.example`): `OUTPUT_DIR`, `COOKIES_FILE`, `YT_DLP_BIN`,
`JS_RUNTIMES`, `REMOTE_COMPONENTS`, `STATE_DB_PATH`, `MCP_AUTH_TOKEN`,
`MCP_HTTP_HOST`/`_PORT` (default `127.0.0.1:8769`), `MCP_TRANSPORT`
(`stdio` | `sse` | `streamable-http`), `PLAYLIST_PREVIEW_LIMIT` (20),
`TASK_HISTORY_KEEP` (500), `PROBE_TIMEOUT_SECONDS` (30; covers probe and playlist
metadata subprocesses, including the probe inside `start_download`).

## Current state

- ✅ Five tools live and verified via MCP Inspector; deployed on the media host
  (systemd, port 8769) with the daily `yt-dlp-mcp-update.timer`.
- ✅ Wired into the bot's pasted-URL flow + completion poller; media-watch register.
- See `AGENTS/STATE.md` for the live Now / Next snapshot and `AGENTS/ENV.md` +
  `../AGENTS/ENV.md` for deploy and host detail.
