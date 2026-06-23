# Memory — yt-dlp-mcp

Durable repo-local facts NOT derivable from code / git / SPEC. Read at session start;
append a bullet when you learn something durable and commit it with the change.
Cross-repo facts live in `../AGENTS/MEMORY.md` — don't duplicate them here.

## yt-dlp 2026.03 runtime gotchas

- **Every yt-dlp call needs `--js-runtimes node` + `--remote-components ejs:github`.**
  2026.03+ defaults to deno-only and ships no bundled n-challenge solver. Without both,
  YouTube extraction fails ("No supported JavaScript runtime" / "No video formats
  found"). Host must have `node` installed and one-time github.com egress for the EJS
  solver (yt-dlp caches it). Configurable via `JS_RUNTIMES` / `REMOTE_COMPONENTS`.
- **Trust the file on disk over yt-dlp's exit code.** 2026.03 sometimes exits
  non-zero from a cleanup path (e.g. `save_cookies` on a read-only file) *after* the
  bytes landed. Completion is decided by `Path(output_path).is_file() && size > 0`,
  not `rc == 0`. Same for probe/list: valid JSON on stdout is authoritative regardless
  of RC. Do not re-add a strict exit-code gate.
- **Bare `null` / non-dict probe payload** = transient extraction miss; the client
  raises `YtDlpError` so it routes through the handled error envelope (don't let `None`
  reach `_to_probe`).
- **`NA` sentinel** leaks unquoted in progress JSON; `_parse_progress_line` rewrites
  `:NA` → `:null` before `json.loads`. Keep that shim.

## Operational facts

- Cookies file (`/etc/yt-dlp-mcp/cookies.txt`) is root-owned, group `movie`, `0660`,
  and `ProtectSystem=strict` would block writes — the unit grants
  `ReadWritePaths=-/etc/yt-dlp-mcp`. `health_check.cookies_warn_days_left < 14` →
  re-export (YouTube auth cookies last ~6–12 months).
- The daily `yt-dlp-mcp-update.timer` bumps the **yt-dlp binary** only (pip -U +
  restart). Service **code** ships manually via `git pull --ff-only` + restart.
- Slug naming keeps **Unicode** (Cyrillic OK on ext4 + Plex) — only filesystem-unsafe
  chars are stripped. (Earlier scaffold notes mentioned ASCII transliteration; the
  code was since relaxed.)
