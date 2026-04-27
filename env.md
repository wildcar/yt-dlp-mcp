# Environment Notes — yt-dlp-mcp

## Where it lives

Same media host as `rtorrent-mcp` (`v.wildcar.ru`). Listens on
`127.0.0.1:8769` over streamable-HTTP. The bot host hits
`http://wildcar.ru:8769/mcp` with the same `MCP_AUTH_TOKEN` it already
uses for the other servers — open that port through the firewall.

The output directory is `/mnt/storage/Media/Video/Clip/`. Plex picks
files up via its «Other Videos» / «Home Videos» library scan; subdirs
per channel slug, file stem from a slugified title.

## OS prerequisites

```bash
sudo apt install -y python3.11 python3.11-venv ffmpeg
# Node.js — yt-dlp's PO Token solver and a handful of JS-based
# extractors run JS via `node`. NodeSource has a current LTS:
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node --version  # sanity check; LTS is fine, no need to keep updating
```

`ffmpeg` is mandatory — yt-dlp uses it to mux video+audio streams into
mp4. `node` is optional but hard-recommended (without it, several
YouTube downloads fall back to lower-quality formats).

## First-time install

```bash
sudo useradd --system --shell /usr/sbin/nologin --create-home --home-dir /opt/yt-dlp-mcp movie || true  # exists from rtorrent-mcp on this host
sudo mkdir -p /opt/yt-dlp-mcp /etc/yt-dlp-mcp
sudo chown movie:movie /opt/yt-dlp-mcp /etc/yt-dlp-mcp

sudo -u movie git clone https://github.com/wildcar/yt-dlp-mcp.git /opt/yt-dlp-mcp
cd /opt/yt-dlp-mcp

# uv handles the venv + lockfile.
sudo -u movie uv sync --no-dev

# Service env file.
sudo install -m 0640 -o root -g movie /dev/null /etc/yt-dlp-mcp/yt-dlp-mcp.env
sudo tee /etc/yt-dlp-mcp/yt-dlp-mcp.env >/dev/null <<'EOF'
MCP_TRANSPORT=streamable-http
MCP_HTTP_HOST=0.0.0.0
MCP_HTTP_PORT=8769
MCP_AUTH_TOKEN=<paste-the-shared-bot-token-here>

OUTPUT_DIR=/mnt/storage/Media/Video/Clip
COOKIES_FILE=/etc/yt-dlp-mcp/cookies.txt
YT_DLP_BIN=/opt/yt-dlp-mcp/.venv/bin/yt-dlp
STATE_DB_PATH=/opt/yt-dlp-mcp/.cache/yt_dlp_mcp.sqlite

PLAYLIST_PREVIEW_LIMIT=20
TASK_HISTORY_KEEP=500
EOF

# systemd units (edit User=/Group= if you don't have a `movie` user).
sudo install -m 0644 deploy/yt-dlp-mcp.service /etc/systemd/system/
sudo install -m 0644 deploy/yt-dlp-mcp-update.service /etc/systemd/system/
sudo install -m 0644 deploy/yt-dlp-mcp-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yt-dlp-mcp.service yt-dlp-mcp-update.timer

# Verify
systemctl status yt-dlp-mcp.service --no-pager
journalctl -u yt-dlp-mcp -n 50 --no-pager
curl -sI http://127.0.0.1:8769/mcp  # should answer (200 with session id, etc.)
```

## Cookies file — exporting and rotating

Required for age-gated, member-only, and region-locked YouTube videos.
The expiry on YouTube's auth cookies is ~6–12 months in practice.

1. Log into YouTube in a browser as the account whose access you want
   the bot to inherit. Use a **separate** profile dedicated to the bot
   so a session cleanup on your main profile doesn't clobber it.
2. Install the «Get cookies.txt LOCALLY» extension (Chrome / Firefox)
   and export `youtube.com`. The result is a Netscape-format file.
3. Drop it on the host:
   ```bash
   sudo install -m 0640 -o root -g movie cookies.txt /etc/yt-dlp-mcp/cookies.txt
   sudo systemctl restart yt-dlp-mcp.service
   ```
4. Verify via the `health_check` MCP tool — the response includes
   `cookies_warn_days_left`. <14 days → it's time to re-export.

`health_check` parses the file every call (cheap, single open) so
expiry warnings show up immediately after a new file lands.

## Daily yt-dlp update

`yt-dlp-mcp-update.timer` fires once a day at ~04:00 with a 30-min
random delay; `yt-dlp-mcp-update.service` runs
`pip install -U yt-dlp` inside the venv and restarts the MCP. yt-dlp
ships ~weekly, sometimes daily during YouTube format wars — keeping
the binary fresh is the single most effective uptime measure.

To trigger a manual update:

```bash
sudo systemctl start yt-dlp-mcp-update.service
journalctl -u yt-dlp-mcp-update.service -n 50 --no-pager
```

Node.js is **not** auto-updated by this timer. Bump it manually with
the OS package manager when you're already doing host maintenance.

## Hooking into media-watch-web

Downloads land in `/mnt/storage/Media/Video/Clip/<channel-slug>/<title-slug>.mp4`,
which is inside the existing `MEDIA_WATCH_MEDIA_ROOTS` whitelist if
you add `/mnt/storage/Media/Video/Clip` to it. The bot poller will
register completed videos under composite media id
`yt-<video_id>` and emit a `/watch/yt-<video_id>` URL into the chat.

If `XSendFilePath` is configured for `/mnt/storage/Media`, downloads
through the watch page already carry a real `Content-Length` (browser
shows ETA). No extra work for the new directory.

## Troubleshooting

- **`yt-dlp returned non-JSON`** in `probe` — almost always a YouTube
  upgrade that broke the extractor. Run the update timer manually
  (`sudo systemctl start yt-dlp-mcp-update.service`).
- **Downloads hang at 99%** — usually ffmpeg muxing. Check
  `journalctl -u yt-dlp-mcp -f` for ffmpeg's stderr; rerun by hand if
  it crashed.
- **`health_check.sample_probe_ok=false`** — yt-dlp can't reach
  YouTube at all. Check egress + DNS first; this is rarely a yt-dlp
  bug.
- **`cookies_warn_days_left` is null with a configured cookies file**
  — the file isn't readable by the `movie` user, or it's not in
  Netscape format. `sudo -u movie cat /etc/yt-dlp-mcp/cookies.txt`
  to confirm.
