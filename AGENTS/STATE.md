# State — yt-dlp-mcp

Repo-local snapshot. Overwrite each iteration. Cross-repo view → `../AGENTS/STATE.md`.

## Goal

MCP server wrapping yt-dlp: probe / list_playlist / start_download /
get_download_status (+ health_check) so the bot can download a pasted video URL
(YouTube + ~1800 sites) and play it back via media-watch-web.

## Now

- Five tools live, verified via MCP Inspector; deployed on the media host
  (`v.wildcar.ru`, systemd port 8769) with the daily `yt-dlp-mcp-update.timer`.
- Wired into the bot's pasted-URL flow + 60 s completion poller.
- Metadata subprocesses are bounded by `PROBE_TIMEOUT_SECONDS=30`; a stalled
  YouTube probe is killed and returned as a structured error instead of hanging
  `probe`, `start_download`, or `health_check` indefinitely.
- `start_download` reuses a successful probe for the same URL for 10 minutes, so
  the preview→confirm flow does not make a second YouTube metadata request.
- Harness migrated to the `agent-template` layout.

## Next

- (when needed) `stop_download` tool — `cancelled` state + `kill()` already exist on
  the worker; no MCP tool exposes it yet.

## Open questions

- —

## Deferred

- —
