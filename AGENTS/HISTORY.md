# History — yt-dlp-mcp

Newest first. Each entry ≤5 lines using the format in `AGENTS.md`. Repo-local log;
cross-repo log is `../AGENTS/HISTORY.md`.

---

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
