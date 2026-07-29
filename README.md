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

## Sync (save → commit → push)

An explicit save (Ctrl/Cmd+S) writes to disk and hands the file to the sync
engine in `workrepo.py`. A 3s debounce folds a burst of saves into **one commit
per scope**, then pushes. The status bar mirrors the real state — `SYNCING…`,
`SYNCED`, or `OFFLINE · N TO PUSH` — and clicking it forces a flush.

Push failures are non-fatal: commits pile up locally and ride out with the next
save, the next boot (`sync_workspace`), or a click on the indicator. Nothing is
lost when the network is down.

Commit messages are **deterministic templates, never LLM-generated** — the
backup path must stay fast, offline-capable, and predictable:

```
save(sarah-chen): PROFILE.md

scope: clients/sarah-chen
save: PROFILE.md
source: human-edit
```

The subject verb is the action that produced the change — `save`, `add`,
`rename`, `move`, `delete`, `create` (new client), `restore`, or `update` when
one debounce window mixed several. One file is named in the subject; more become
`N files`, itemized per verb in the body:

```
update(sarah-chen): 2 files

scope: clients/sarah-chen
delete: income/1099.txt
save: PROFILE.md
source: human-edit
```

Renames and moves record both ends (`old → new`), so the ledger reads correctly
even where git's rename detection wouldn't fire.

The history is meant to be machine-readable context for agents later: the diff
carries the *what*, the trailer carries the *who/where*. `source:` says where the
change came from — `human-edit` for work done in the app, `filesystem` for
anything that reached the checkout on its own (a file dropped in from Explorer,
another program saving over a document), and `agent:<task-id>` once agents can
write. A window that mixed both lists both (`source: filesystem, human-edit`). If
human-readable summaries are ever wanted, attach them as `git notes` after the
fact — no history rewrite, no change to this path.

### Tree colors

The file tree paints plain `git status` (`workrepo.git_status`), IDE-style:
untracked → green name + `U`, tracked-and-changed → amber name + `M`, and a
folder inherits its loudest child so a collapsed branch still shows it.
Deletions are dropped — there is no row left to paint.

Colors are refreshed from `file_status()` (one git call, no rescan) on every
sync-state change and on view switches, which is also what *clears* them once
the sync engine commits. Consequence worth knowing: because saves auto-commit
within 3s, a clean tree is the normal state — colors mostly show files that
arrived from outside the app (dropped into the folder, written by an agent) or
the brief window between a save and its commit.

## File operations (disk is the truth)

Everything the tree can do — new file/folder, rename, move (drag & drop or
cut/paste), copy/paste, duplicate, delete, add files, Reveal, Copy Path — is a
real filesystem write in `workrepo.py`, followed by a `queue_sync` so the change
lands in the ledger like any save. The frontend **never patches its tree** from
an operation's result: it re-reads `workspace_snapshot()` and re-renders. That's
the invariant that keeps the UI from ever showing a file the checkout doesn't
have. A full rescan of a real book of business costs ~50ms, which is why every
operation can afford to round-trip instead of guessing.

The same rule covers writes we don't originate: a `watchdog` observer on the
checkout (0.5s debounce, `.git` ignored) pushes a fresh snapshot when files are
copied in from Explorer/Finder, pulled from the remote, or written by an agent.
Snapshot merging preserves what's local to the session — expanded folders, the
selected row, the focused client — so a live update never moves the ground under
a click.

**And it backs them up.** A settled change also runs `queue_external()`, which
reads `git status` and queues what it finds into the same debounce every in-app
write uses (`??` → `add`, modified → `save`, missing → `delete`, tagged
`source: filesystem`). A backup that only covered changes made through our own UI
would quietly lose the most common way documents actually arrive — dragged into
the folder in Explorer. The same pass runs on boot, so work done while the app was
closed gets committed too. Entries the app already queued are left alone: it knows
a rename is a rename, where `git status` only sees a delete and an add. Files at
the repo root belong to no client and are never committed by us.

Shared house rules for every operation:

- paths are re-resolved and pinned inside their scope (`_resolve_scoped`) and
  typed names are validated — nothing that crossed the JS bridge is trusted;
- **nothing is ever overwritten**: a collision gets an IDE-style `-2`, `-3`…
  suffix (`report.pdf` → `report-2.pdf`);
- disk first, then `queue_sync`, then rescan. A new *empty* folder queues
  nothing — git tracks files, not directories, so it rides along with its
  first file;
- `client.yaml` is machine-managed: invisible in the tree and rejected as a
  rename/create target.

### Deleting, and the one confirmation left

Deleting a file or folder happens without a prompt, the way an IDE explorer does:
the ledger already has what it committed, so the folder's History brings it back.
The toast says exactly that. The one case it can't cover is a file created and
deleted inside the same 3s window — it never reached a commit.

A **client** is different. Right-clicking a row in the client list gives Open,
Copy Path, Reveal and *Delete Client* (`delete_client`, which validates the slug
itself since it's the one delete that isn't a path inside a scope). It removes the
whole folder and commits `delete(<slug>): client folder`, so the previous commit
still holds every document — but the row is gone from the list, and with it any
place to right-click for History. Because the app can't offer the way back, this
one asks first, in an in-app dialog (`ConfirmModal.vue`) rather than a
`window.confirm()` wearing browser chrome. New Client… stays on the blank area of
the list, where a row isn't the target.

### The tree clipboard

`Ctrl/Cmd+C`, `Ctrl/Cmd+X` and `Ctrl/Cmd+V` (plus Cut/Copy/Paste on the context
menu) work on the selected row; a cut row renders dimmed until it's pasted. Both
land on operations that already exist: **cut/paste is the same `move_path` a drag
& drop makes**, copy/paste is `copy_path`. Pasting into the source's own folder
defers to `duplicate_path`, so there's one naming rule (`-copy`) rather than two.

Two deliberate limits:

- **same scope only.** Pasting across clients would file a document under the
  wrong person, and a mis-filed document is worse than one extra step, so a
  clipboard entry from another client says so instead of moving anything.
- `Ctrl+V` stays polite about the OS clipboard: files copied in Explorer/Finder
  win the keystroke and land as uploads. The tree's clipboard only takes over
  when the system one holds no files.

The key handler yields to text inputs, the editor, open modals and any live text
selection — copying a sentence out of a document must never copy a file.

Two routes bring documents in, because a webview `File` object (unlike
Electron's) exposes no disk path:

- **Add Files…** opens the native picker and copies by real path — no bridge
  payload at all. It's on the dir/root context menu and the Product Library `＋`.
- **Drag & drop / paste** has only the bytes, so they ride the bridge base64'd,
  capped at 40 MB per file (same ceiling both sides; oversized files are skipped
  with a toast rather than freezing the webview).

### History and Restore

`History…` is `git log` for one path, `--follow` so a renamed file keeps its
past, rendered as *when · who · what · revision* (`YOU` for this officer's own
commits). Restore is **append-only**: the old bytes come back as a new change on
top, never a history rewrite, so the undo is itself a versioned event.

A file restores under its *current* name (the revision may predate a rename, so
the blob is read from the name it had then). A folder restores through
`git checkout <sha> -- <dir>`, which is also the way to bring back a deleted
file — a deleted file has no tree row left to right-click, its folder does.

### New client

The folder **is** the client: `create_client` scaffolds `clients/<slug>/` with
`client.yaml` (structured facts, machine-managed), `PROFILE.md` (the LO-facing
page), and the `income/assets/credit/ai` buckets — each with a `.gitkeep`, or
the structure would exist on one machine only. Nothing is registered anywhere
else, and an existing slug is refused instead of merged into.

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
workrepo.py       the work repo: clone/scan, file operations, sync engine, watcher
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
- **Git output must be decoded as UTF-8 explicitly.** `subprocess(text=True)`
  uses the OS locale, which on a non-English Windows (cp936 here) throws on a
  filename with an accent — or on the `→` in our own rename messages. `_git`
  pins `encoding="utf-8", errors="replace"`.
- **`explorer /select,` exits 1 on success.** Reveal fires and forgets
  (`Popen`); checking its return code would report a failure that didn't happen.
