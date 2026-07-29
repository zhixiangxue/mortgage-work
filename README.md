# Mortgage Work

A loan-officer desktop workbench: a native [pywebview](https://pywebview.flowrl.com/)
shell wrapping a Vue 3 UI, with a client tree on the left, a document viewer in
the center, and an agentic AI panel on the right. It also embeds a set of
read-only data-browser "viewers" (rqlite / FalkorDB / Qdrant / Redis) so an
operator can inspect the backing stores without leaving the app.

## Quick start

```bash
uv sync                        # create .venv + install Python deps from uv.lock
npm install --prefix frontend  # install frontend deps
cp .env.example .env           # then fill in the real service endpoints
./dev.sh                       # one command: Vite + the app, cleaned up together
```

`./dev.sh` starts the Vite dev server in the background, waits until it's
actually serving, then launches the app in the foreground. Closing the window
(or Ctrl+C) tears Vite down too — no orphaned dev servers, no juggling two
terminals.

### Run modes

```bash
uv run python app.py           # prod — loads the built frontend/dist
uv run python app.py --dev     # dev  — loads the Vite server on :5273
```

## Architecture

```
pywebview window (app.py)
├── frontend/  ...... Vue 3 + Vite SPA (the actual UI)
│                     dev: Vite @ :5273   prod: frontend/dist (built)
└── browser/   ...... 4 FastAPI viewer servers, spawned as child processes,
                      embedded in the UI via <iframe>. Read-only by design.
```

`app.py` spawns one child process per viewer on startup and kills them all on
exit (`atexit`). Each viewer talks to its data store and serves a small HTML +
JSON API on a fixed loopback port.

| Viewer   | Default port | Data store it inspects |
|----------|--------------|------------------------|
| falkordb | 8787         | FalkorDB (graph)       |
| rqlite   | 9090         | rqlite (SQLite/Raft)   |
| qdrant   | 8789         | Qdrant (vectors)       |
| redis    | 8790         | Redis                  |

Vite dev server runs on **:5273** (`strictPort`, so that port is always ours).

## Configuration

All service endpoints and viewer ports live in **one** place: `config.py`,
sourced from a single `.env` at the project root. Nothing hardcodes a URI or
port elsewhere — moving from local dev to cloud is a one-file change.

- `.env` is **gitignored** (it holds secrets). `.env.example` documents the shape.
- `config.py` exposes a typed `SERVICES` object with sane localhost defaults, so
  the app still boots with an empty `.env`.
- Use `SERVICES.viewer_url("redis")` etc. for iframe `src`; never rebuild URLs.

## Layout

```
app.py            native shell: window, menus, viewer lifecycle, macOS branding
config.py         single source of truth for service URIs + viewer ports (.env)
dev.sh            one-command dev launcher (Vite + app, with cleanup trap)
index.html        legacy single-file prototype (kept for reference)
assets/           app icons — icon.svg is the source; png/ico/icns/iconset derived
browser/          the 4 FastAPI viewers (*_viewer.py) + their HTML frontends
frontend/         the Vue 3 + Vite application (src/, components/, mocks/)
```

## Conventions

- **Python**: managed with [`uv`](https://docs.astral.sh/uv/). Always use the
  local `.venv` (`uv run …` / `uv sync`), never the system interpreter.
- **Comments**: English, and focused on the *why*, not the *what*.
- **Frontend build**: `base: './'` in `vite.config.js` so built asset paths work
  when served by pywebview's bundled HTTP server (relative, no leading slash).

## Notes for future contributors (hard-won gotchas)

These cost real time to figure out — read before touching the relevant area:

- **macOS Dock icon must be set *after* `webview.start()`.** pywebview's Cocoa
  backend rebuilds `NSApplication` inside `start()`, which wipes any icon set
  before it. The icon is applied from a post-start main-thread callback.
- **The Dock hover label follows the *process name*, not `CFBundleName`.** For a
  bare interpreter it defaults to "python3"; we set it explicitly via
  `NSProcessInfo.setProcessName_`. (`CFBundleName` only drives the menu bar.)
- **Native `<select>` ignores the dark theme in WebKit.** The viewers use
  `appearance: none` + an inline-SVG chevron to get a consistent dark dropdown.
- **Redis viewer is DB-aware.** It caches one client per db index and reads
  `CONFIG GET databases` (falls back to 16) to populate the db switcher.
- **Icons**: edit `assets/icon.svg` (the vector source) and re-derive png/ico/
  icns. When generating the `.ico`, downsample from a large render — don't
  upsample a 16×16, or large sizes come out blurry.
