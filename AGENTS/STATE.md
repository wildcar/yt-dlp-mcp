# State — yt-dlp-mcp

Repo-local snapshot. Overwrite each iteration. Cross-repo view → `../AGENTS/STATE.md`.

## Goal

MCP server wrapping yt-dlp: probe / list_playlist / start_download /
get_download_status (+ health_check) so the bot can download a pasted video URL
(YouTube + ~1800 sites) and play it back via media-watch-web.

## Now

- Five tools live, verified via MCP Inspector; deployed on the media host
  (`homesrv`, public name `v.wildcar.ru`, systemd port 8769) with the daily
  `yt-dlp-mcp-update.timer`.
- Plex delete rights configured on `homesrv` (2026-08-08): plex in group `movie`,
  `Clip/` tree 2775/0664 setgid, unit runs with `UMask=0002`; verified by a
  write-probe as user plex. Setup commands in `AGENTS/ENV.md`.
- Wired into the bot's pasted-URL flow + 60 s completion poller.
- Metadata subprocesses are bounded by `PROBE_TIMEOUT_SECONDS=30`; a stalled
  YouTube probe is killed and returned as a structured error instead of hanging
  `probe`, `start_download`, or `health_check` indefinitely.
- `start_download` reuses a successful probe for the same URL for 10 minutes, so
  the preview→confirm flow does not make a second YouTube metadata request.
- Single-video pages that extractors report as one-entry playlists (1tv.ru) are
  unwrapped in `probe`, so the card gets the real video id, duration and formats;
  channel falls back to a per-host publisher name, then the hostname. Playlists
  with several entries are refused by `start_download` as `unsupported`.
- Harness migrated to the `agent-template` layout.
- 2026-09-14: YouTube probes on `homesrv` fail with «Sign in to confirm you're not a
  bot» (bot shows `ydl.youtube_blocked`). Diagnosed via `health_check`: yt-dlp still
  **2026.03.17** (the update unit ran `python -m pip` in a pip-less uv venv and failed
  nightly since install) and `/etc/yt-dlp-mcp/cookies.txt` is **not writable** by
  `movie` (rotated cookies lost → session dead). Fixed in-repo: update unit uses
  `uv pip`, `uv.lock` bumped to yt-dlp 2026.8.19, `health_check` reports
  `cookies_file_writable`, stderr tracebacks trimmed from error envelopes.
  Applied on `homesrv` the same day: yt-dlp 2026.08.19 live, cookies 0660 and
  re-exported (expire 2027-10-19), `sample_probe_ok=true`, `XgnBN8BLc-o` probes fine.
  `movie` there is a nologin account — see ENV.md for the `sudo -u movie … bash -c` form.

## Next

- (when needed) `stop_download` tool — `cancelled` state + `kill()` already exist on
  the worker; no MCP tool exposes it yet.

## Open questions

- —

## Deferred

- —
