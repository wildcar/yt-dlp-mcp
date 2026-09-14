# Environment — yt-dlp-mcp

Repo-local deploy / env detail. **Shared host facts** (the dev box, the media host,
credential layout, the prod cheat-sheet) live in `../AGENTS/ENV.md` — read that for
the cross-repo picture; this file holds only what's specific to this server.

## Where it lives

Media host `homesrv` (public name `v.wildcar.ru`; same box as `rtorrent-mcp`). Listens on `127.0.0.1:8769`
(or `0.0.0.0:8769` behind the firewall) over streamable-HTTP. The bot hits
`http://wildcar.ru:8769/mcp` with the shared `MCP_AUTH_TOKEN`. Service user `movie`,
`/opt/yt-dlp-mcp`. Output dir `/mnt/storage/Media/Video/Clip/` (Plex picks it up via
its library scan; subdirs per channel slug).

## OS prerequisites (beyond the shared base)

```bash
sudo apt install -y ffmpeg nodejs
```

- **ffmpeg** — mandatory; yt-dlp muxes video+audio into mp4.
- **nodejs** — required: yt-dlp 2026.03+ uses it for the JS runtime / PO-token path
  (`--js-runtimes node`). Distro repo is fine (Ubuntu 22.04 → Node 18+, 24.04 → 20+).
  Not auto-updated by the timer; bump manually during host maintenance.
- **Remote EJS solver** — fetched from github.com on first run
  (`--remote-components ejs:github`); the host needs outbound github.com access once.

## Plex delete rights on `Clip/`

Plex deletes a file by unlinking it from its directory, so it needs **write on the
directories**, not on the files (this is why the world-writable rtorrent dirs "just
work"). One-time host setup (Plex runs natively as user `plex`):

```bash
sudo usermod -aG movie plex
sudo chgrp -R movie /mnt/storage/Media/Video/Clip
sudo find /mnt/storage/Media/Video/Clip -type d -exec chmod 2775 {} +
sudo find /mnt/storage/Media/Video/Clip -type f -exec chmod 0664 {} +
sudo systemctl restart plexmediaserver   # group membership applies on restart
```

The unit sets `UMask=0002` so new per-channel dirs come out 2775 (setgid on `Clip/`
keeps group `movie`) and files 0664 — without it every new channel dir is 0755 and
Plex loses delete rights there again.

## Env file (`/etc/yt-dlp-mcp/yt-dlp-mcp.env`)

```
MCP_TRANSPORT=streamable-http
MCP_HTTP_HOST=0.0.0.0
MCP_HTTP_PORT=8769
MCP_AUTH_TOKEN=<shared-bot-token>
OUTPUT_DIR=/mnt/storage/Media/Video/Clip
COOKIES_FILE=/etc/yt-dlp-mcp/cookies.txt
YT_DLP_BIN=/opt/yt-dlp-mcp/.venv/bin/yt-dlp
STATE_DB_PATH=/opt/yt-dlp-mcp/.cache/yt_dlp_mcp.sqlite
PLAYLIST_PREVIEW_LIMIT=20
TASK_HISTORY_KEEP=500
```

`YT_DLP_BIN` points at the venv copy so the daily timer can bump it independently of
any OS package. Full first-install sequence (useradd, clone, `uv sync --no-dev`,
systemd unit install) is in `README.md` / git history.

## Cookies (`/etc/yt-dlp-mcp/cookies.txt`)

- Netscape format; required for age-gated / member-only / region-locked videos.
- Install: `sudo install -m 0660 -o root -g movie cookies.txt /etc/yt-dlp-mcp/` then
  `systemctl restart yt-dlp-mcp`. Group `movie` so the service user can read **and
  write** it — yt-dlp rewrites the jar on exit with the cookies YouTube rotated
  during the run. A `0640` file (the pre-2026-09-14 instruction) makes every run end
  in `PermissionError … cookies.txt`, the rotated values are lost, and the exported
  login session is soon rejected with «Sign in to confirm you're not a bot».
  `health_check.cookies_file_writable` must be `true`.
- `ProtectSystem=strict` blocks writes — the unit grants
  `ReadWritePaths=-/etc/yt-dlp-mcp`.
- Export per the yt-dlp wiki («Exporting YouTube cookies»): a **private/incognito
  window**, log in, open `https://www.youtube.com/robots.txt`, export with "Get
  cookies.txt LOCALLY", then **close that window** so the browser never rotates the
  session behind yt-dlp's back.
- `health_check.cookies_warn_days_left < 14` → re-export from a dedicated bot browser
  profile via the "Get cookies.txt LOCALLY" extension. Auth cookies last ~6–12 months.
- `cookies_warn_days_left` null with a configured file → not readable by `movie` or
  not Netscape format.

## Daily yt-dlp update timer

`yt-dlp-mcp-update.timer` fires ~04:00 daily (30-min jitter); the paired service runs
`uv pip install --python .venv/bin/python -U yt-dlp` and restarts the MCP. Bumps the
**yt-dlp binary only**, not this service's code. The venv comes from `uv sync` and has
**no pip module** — the original `python -m pip install -U` unit failed every night
with "No module named pip", so prod sat on yt-dlp 2026.03.17 from install until
2026-09-14 (fixed in `deploy/yt-dlp-mcp-update.service`; reinstall the unit file).
`uv sync --no-dev` resets yt-dlp to the version in `uv.lock`, so bump the lock
(`uv lock --upgrade-package yt-dlp`) with releases, or run the update service right
after a sync. Manual trigger:

```bash
sudo systemctl start yt-dlp-mcp-update.service
journalctl -u yt-dlp-mcp-update.service -n 50 --no-pager
```

## Redeploy (service code)

```bash
sudo -u movie git -C /opt/yt-dlp-mcp pull --ff-only
# only when deps changed (pyproject/lockfile touched):
sudo -u movie env PATH=/home/movie/.local/bin:/usr/local/bin:/usr/bin:/bin \
  bash -c "cd /opt/yt-dlp-mcp && uv sync --no-dev"
sudo systemctl restart yt-dlp-mcp
```

`movie` on `homesrv` is a **nologin** account: `sudo -iu movie …` answers "This account
is currently not available" — always use `sudo -u movie … bash -c`, and pass `PATH`
explicitly because sudo's `secure_path` does not include the user's `~/.local/bin`.

## Troubleshooting

- **`yt-dlp returned non-JSON` / no formats** — usually a YouTube extractor break or
  the JS-runtime/EJS path; run the update timer manually, confirm `node` + github
  egress.
- **Downloads hang at 99%** — ffmpeg muxing; check `journalctl -u yt-dlp-mcp -f`.
- **`health_check.sample_probe_ok=false`** — yt-dlp can't reach YouTube; check egress
  + DNS first. If `sample_probe_detail` says «Sign in to confirm you're not a bot», see
  the next bullet.
- **«Sign in to confirm you're not a bot»** (bot surfaces it as `ydl.youtube_blocked`)
  — YouTube's bot check on a server IP; the cookies are the only thing that lifts it.
  Check, in order: (1) `health_check.yt_dlp_version` is current (`pip index versions
  yt-dlp` / PyPI) — run the update service; (2) `cookies_file_writable=true` — else
  `chmod 0660 /etc/yt-dlp-mcp/cookies.txt`; (3) re-export cookies as described above.
  Popular videos (e.g. `dQw4w9WgXcQ`) often pass even with dead cookies, so a single
  successful probe proves nothing — use the canary (`sample_probe_ok`).
