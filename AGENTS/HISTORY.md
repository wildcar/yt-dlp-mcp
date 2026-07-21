# History — yt-dlp-mcp

Newest first. Each entry ≤5 lines using the format in `AGENTS.md`. Repo-local log;
cross-repo log is `../AGENTS/HISTORY.md`.

---

## 2026-07-21 · Reuse preview metadata on download confirmation
- What: Added a bounded 10-minute/128-entry probe cache; `start_download` reuses the preview payload instead of probing YouTube again.
- Why: The reported URL produced a preview, but the duplicate probe after «Скачать» stalled before a task could be created.
- Files: `AGENTS/SPEC.md`, `AGENTS/STATE.md`, `context.py`, `tools.py`, tests.
- Next: Redeploy `yt-dlp-mcp`; the existing subprocess timeout remains the fallback for uncached/stale URLs.

## 2026-07-21 · Bound stalled yt-dlp metadata extraction
- What: Added a configurable 30-second timeout that kills and reaps hung probe/playlist subprocesses, including the probe inside `start_download`.
- Why: Production accepted a Telegram download callback but then waited forever for yt-dlp metadata, leaving the user without a result.
- Files: `config.py`, `context.py`, `clients/ytdlp.py`, `.env.example`, `README.md`, harness docs, tests.
- Next: Redeploy `yt-dlp-mcp`, then inspect the structured timeout/upstream error if refreshed cookies still cannot extract the video.

## 2026-06-23 · Migrate harness to agent-template layout
- What: Restructured repo docs to the `wildcar/agent-template` harness (`AGENTS.md`, `CLAUDE.md` pointer, `AGENTS/{SPEC,STATE,HISTORY,MEMORY,ENV}.md`, `docs/adr/`).
- Why: Adopt the standard harness so per-repo work keeps the right context.
- Files: `AGENTS.md`, `CLAUDE.md`, `AGENTS/*`, `docs/adr/TEMPLATE.md`; folded `history.md` + `env.md` in.
- Next: Keep README authoritative for the user-facing tool list/config.

## 2026-06-23 · README: document redeploy commands
- What: Added an "Update an existing install" subsection (pull --ff-only + restart, uv sync caveat for dep changes).
- Why: Redeploy steps lived only in operator memory; a fix is live only after they run.
- Files: `README.md`.
- Next: Distinguish service-code updates from the yt-dlp-binary update timer (done inline).

## 2026-06-23 · probe(): reject non-dict yt-dlp JSON (null-payload crash)
- What: `probe()`/`list_playlist()` now require a dict payload; bare `null`/list/scalar raises `YtDlpError` → handled error envelope, no `'NoneType'.get` leak.
- Why: A transient YouTube extraction miss emitted bare JSON `null`, crashing `start_download` and the re-paste preview.
- Files: `src/yt_dlp_mcp/clients/ytdlp.py`, tests.
- Next: —

## 2026-04-27 · Initial scaffold
- What: Five MCP tools (probe, start_download, get_download_status, list_playlist, health_check); detached-subprocess yt-dlp wrapper; browser-mp4 default selector; SQLite task store; Unicode-safe slug naming; systemd unit + daily update timer.
- Why: Cross-repo "paste a YouTube URL" flow — same preview-and-confirm UX as a rutracker URL; yt-dlp covers YouTube + 1800 sites.
- Files: `src/yt_dlp_mcp/*`, `deploy/*`, `tests/*`.
- Next: Wire the bot's youtube_url handler + completion poller to this server.
