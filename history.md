# history — yt-dlp-mcp

Reverse-chronological log of meaningful changes. Add an entry **before**
the work starts so future agents can see the intent even if a session
is interrupted; expand it with results once the change lands.

---

## 2026-04-27 — Initial scaffold

**Why.** Cross-repo plan (see `AGENTS-TODO.md` → «YouTube URL pasted-link
flow»): users want to drop a YouTube URL in chat and get the same
mid-pipeline preview-and-confirm UX as for a rutracker URL. yt-dlp
covers YouTube + 1800 other sites, so this MCP is the natural home for
the «download by URL» path.

**What.**
- Five MCP tools: `probe(url)`, `start_download(url, format_selector?)`,
  `get_download_status(task_id)`, `list_playlist(url, limit?)`,
  `health_check()`.
- yt-dlp invocation via subprocess (rationale: detached process for
  kills, swap-friendly under the daily update timer).
- Default format selector: `(bv[avc1|h264]+ba[m4a])/b[avc1|h264][mp4]/b[mp4]/b`
  — prefers a single progressive H.264+AAC mp4, then mp4 video + m4a
  audio that ffmpeg copies into mp4 (no transcode), then anything
  yt-dlp can produce. Fully browser-playable mp4 is the steady-state
  output; non-mp4 fallbacks land on disk so the user can still grab
  the file via the watch page's «Скачать».
- Plex-friendly slug naming: `<channel-slug>/<title-slug>.mp4`,
  ASCII-only, length-capped at 80/60 chars, collisions append `-2`,
  `-3`, …. Cyrillic is transliterated by `python-slugify`.
- SQLite-backed task store so service restarts don't strand
  in-flight downloads invisible to the bot poller.
- `health_check` parses the configured Netscape cookies.txt and
  returns `cookies_warn_days_left` for the soonest auth-relevant
  cookie (SAPISID / __Secure-1PSID / LOGIN_INFO). <14 → operator
  rotates.
- `list_playlist` returns a flat preview (id, title, url, duration,
  thumbnail) up to `playlist_preview_limit`. The bot turns it into a
  plain-text list of links and the user copies one back into chat —
  simpler than per-entry inline buttons for long playlists.
- systemd: `yt-dlp-mcp.service` + `yt-dlp-mcp-update.{service,timer}`
  in `deploy/`. Daily timer runs `pip install -U yt-dlp` in the venv
  and restarts the MCP. Node.js is documented as a manual install
  (no auto-update by design).
- Tests: `FakeYtDlpClient` replaces the real client; canned probe /
  playlist / progress payloads exercise every tool. 12/12 pass.
