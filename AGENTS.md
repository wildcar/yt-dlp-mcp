# Agent Instructions — yt-dlp-mcp

Primary entrypoint for any agent (Claude, Codex, DeepSeek, etc.) working **inside
this repo**. Read this first.

## Workspace

Part of the **`movie_handler`** workspace — a set of independent sibling repos
coordinated by a root harness. Cross-repo architecture, end-to-end flows, hosts,
and shared agreements live in `../AGENTS.md` + `../AGENTS/SPEC.md`. **This file is
authoritative inside this repo**; open the root harness only when reasoning about
how this server fits the bot / other MCPs.

`yt-dlp-mcp` is the yt-dlp download worker (priority added after the original five
servers). It deploys on the **media host** (`v.wildcar.ru`, same box as
`rtorrent-mcp`) as a systemd unit on **port 8769** over streamable-HTTP, with a
daily **`yt-dlp-mcp-update.timer`** that bumps the yt-dlp binary.

## Project

MCP server wrapping the `yt-dlp` CLI: probe a video URL, list a playlist, start a
background download, and poll its progress. Covers YouTube + ~1800 other sites. The
Telegram bot's "paste a video URL" flow is the main consumer.

## Document Map

| File | Role |
|------|------|
| `AGENTS.md` | This entrypoint. Repo map, workflow, rules. |
| `CLAUDE.md` | Compatibility pointer to `AGENTS.md`. |
| `AGENTS/SPEC.md` | Repo functional + technical spec: tools, task store, gotchas, structure. |
| `AGENTS/STATE.md` | Current snapshot: goal, now, next, open, deferred. Overwritten each iteration. |
| `AGENTS/HISTORY.md` | Append-only iteration log, newest first. |
| `AGENTS/MEMORY.md` | Durable repo-local facts/agreements. |
| `AGENTS/ENV.md` | Repo-local deploy/env detail (cookies, update timer); points to `../AGENTS/ENV.md` for shared host facts. |
| `README.md` | User-facing tool list, config, deploy. Kept current. |
| `docs/adr/` | Architecture Decision Records (`docs/adr/TEMPLATE.md`). |

## Environment

- OS / shell: Ubuntu 24.04 / `bash`, user `keeper` (passwordless sudo) on the dev box.
- Commit identity: `wildcar <wildcar@mail.ru>`.
- Remote: `github.com/wildcar/yt-dlp-mcp`.
- Deploys to the media host (`v.wildcar.ru`), systemd unit on port 8769.

## Startup Checklist

1. Read `AGENTS.md` (this file).
2. Read `AGENTS/SPEC.md` for the tool surface and internals.
3. Read `AGENTS/STATE.md` for the live snapshot.
4. Read top 3–5 entries in `AGENTS/HISTORY.md`.
5. Read `AGENTS/MEMORY.md` (durable facts — the yt-dlp 2026.03 runtime gotchas).
6. `git status --short` before editing. Open `AGENTS/ENV.md` for host / deploy detail.

## Change Workflow

For every iteration that changes code or behavior:

1. If the tool contract changes — update `AGENTS/SPEC.md` (and `README.md`) first.
2. Make the changes.
3. Overwrite `AGENTS/STATE.md`; if the cross-repo picture shifted, also touch
   `../AGENTS/STATE.md`.
4. Prepend an entry to `AGENTS/HISTORY.md` (≤5 lines, format below). Cross-repo
   changes also get a one-liner in `../AGENTS/HISTORY.md`.
5. Run `ruff` + `mypy` + `pytest`, then commit and push (see Project Rules).

### `AGENTS/HISTORY.md` entry format (≤5 lines, newest first)

```
## YYYY-MM-DD · <short iteration title>
- What: <one line — what changed>
- Why: <one line — reason / task>
- Files: <key paths, comma-separated>
- Next: <one line — what was planned right after>
```

## Memory

`AGENTS/MEMORY.md` is the **single** store of durable repo-local memory. Read it at
session start; append a short bullet when you learn a durable fact and commit it with
the related change. Durable facts/agreements → `MEMORY.md`; current snapshot →
`STATE.md`; iteration log → `HISTORY.md`. Don't record what's already in code or SPEC.

## Language Rules

- Source code, technical docs, code comments: **English**.
- Conversation with the user: **Russian**.
- End-user UI text (bot side): **Russian**.
- Docs already in another language stay in that language — don't silently translate.

## Project Rules

- **`media_id` is the cross-server key**, shape `<source>-<id>`. This server's output
  feeds two media-id shapes: `yt-<video_id>` (YouTube) and `dl-<sha1(url)[:12]>`
  (non-YouTube sources). This repo emits `video_id` + a 16-char hex `task_id`; the
  bot composes the `media_id` at media-watch register time.
- **Structured error returns, not exceptions** across the MCP boundary
  (`ToolError(code, message)` in every response envelope).
- **Pydantic models** for all tool I/O. **Secrets only via env vars** (`.env`,
  `pydantic-settings`), never tool arguments. Ships `.env.example`.
- **Transport:** `stdio` for local dev; HTTP+SSE / streamable-HTTP with Bearer
  `MCP_AUTH_TOKEN` in production (port 8769).
- **Trust the file on disk over yt-dlp's exit code** — see SPEC gotchas.
- **Every commit passes `ruff` + `mypy` + `pytest` locally before push.** Commit +
  push to `main` directly after verification — no feature branch, no asking.
- **`git pull --ff-only` on prod** — never surprise merge commits.

## Stack & Commands

Python ≥ 3.11, `asyncio`, official `mcp` SDK (`FastMCP`), `pydantic` +
`pydantic-settings`, `structlog` (JSON in prod), `sqlite3` task store. Shells out to
the `yt-dlp` CLI (detached subprocess). Deps via `uv`. Full cheat-sheet in
`AGENTS/ENV.md` + `../AGENTS/ENV.md`.

```bash
uv sync --all-groups                          # install / sync deps
uv run yt-dlp-mcp                              # run over stdio
MCP_TRANSPORT=streamable-http uv run yt-dlp-mcp  # 127.0.0.1:8769
uv run pytest && uv run ruff check && uv run mypy src
npx @modelcontextprotocol/inspector uv run yt-dlp-mcp   # manual verify
```

## Code Style

- Match surrounding code: comment density, naming, idiom.
- `ruff` format + lint (line-length 100), `mypy --strict`.
