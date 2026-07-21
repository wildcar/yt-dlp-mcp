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
- Install: `sudo install -m 0640 -o root -g movie cookies.txt /etc/yt-dlp-mcp/` then
  `systemctl restart yt-dlp-mcp`. Group `movie` so the service user can read it.
- `ProtectSystem=strict` blocks writes — the unit grants
  `ReadWritePaths=-/etc/yt-dlp-mcp`.
- `health_check.cookies_warn_days_left < 14` → re-export from a dedicated bot browser
  profile via the "Get cookies.txt LOCALLY" extension. Auth cookies last ~6–12 months.
- `cookies_warn_days_left` null with a configured file → not readable by `movie` or
  not Netscape format.

## Daily yt-dlp update timer

`yt-dlp-mcp-update.timer` fires ~04:00 daily (30-min jitter); the paired service runs
`pip install -U yt-dlp` in the venv and restarts the MCP. Bumps the **yt-dlp binary
only**, not this service's code. Manual trigger:

```bash
sudo systemctl start yt-dlp-mcp-update.service
journalctl -u yt-dlp-mcp-update.service -n 50 --no-pager
```

## Redeploy (service code)

```bash
sudo -u movie git -C /opt/yt-dlp-mcp pull --ff-only
# only when deps changed (pyproject/lockfile touched):
sudo -u movie bash -c "cd /opt/yt-dlp-mcp && uv sync --no-dev"
sudo systemctl restart yt-dlp-mcp
```

## Troubleshooting

- **`yt-dlp returned non-JSON` / no formats** — usually a YouTube extractor break or
  the JS-runtime/EJS path; run the update timer manually, confirm `node` + github
  egress.
- **Downloads hang at 99%** — ffmpeg muxing; check `journalctl -u yt-dlp-mcp -f`.
- **`health_check.sample_probe_ok=false`** — yt-dlp can't reach YouTube; check egress
  + DNS first.
