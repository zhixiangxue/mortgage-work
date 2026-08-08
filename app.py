"""Mortgage Work — UI demo for a loan-officer desktop workbench (pywebview).

IDE-style shell: activity bar (Clients / Product Library), sidebar that
switches between client list and the focused client's folder tree, a
document viewer in the center, and an agentic AI panel on the right.
The UI is a Vue 3 + Vite app in frontend/ (mock data only); this file
provides the native window, menu bar, and macOS branding — same approach
as pywebview-ide.

Usage:
    uv run mortgage-work/app.py          # prod — loads the built frontend/dist
    uv run mortgage-work/app.py --dev    # dev — loads the Vite server (npm run dev)
"""
import argparse
import asyncio
import atexit
import json
import logging
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import warnings
from pathlib import Path

APP_NAME = "Mortgage Work"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Windows WebView2 / pythonnet bootstrap ───────────────────────────────
# pywebview's WinForms backend imports pythonnet lazily during webview.start().
# On current Windows dev machines, the default pythonnet loader may fall back to
# .NET Framework and fail to expose Microsoft.Web.WebView2.WinForms even though
# the DLLs ship inside pywebview.  Force CoreCLR and point it at a runtime config
# that includes Microsoft.WindowsDesktop.App before anything can import clr.
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONNET_RUNTIME', 'coreclr')
    runtime_config = os.path.join(BASE_DIR, 'pythonnet.runtimeconfig.json')
    if os.path.isfile(runtime_config):
        os.environ.setdefault('PYTHONNET_CORECLR_RUNTIME_CONFIG', runtime_config)
    try:
        import clr  # noqa: E402
        # System.Windows.Forms depends on this assembly under .NET Core, but it
        # is not always auto-resolved by pythonnet's assembly loader.
        clr.AddReference('Microsoft.Win32.SystemEvents')
    except Exception:
        # Let pywebview surface the real startup exception with its own context.
        pass

    # Use the project's patched WinForms backend in dev too. The stock pywebview
    # module still contains a .NET 8-incompatible OpenFolderDialog reflection
    # path, so relying on site-packages makes launch fail before any window shows.
    patched_winforms = os.path.join(BASE_DIR, 'hooks', 'webview', 'platforms', 'winforms.py')
    if os.path.isfile(patched_winforms):
        from importlib.abc import Loader, MetaPathFinder  # noqa: E402
        from importlib.machinery import ModuleSpec  # noqa: E402

        class _PatchedWinformsFinder(MetaPathFinder, Loader):
            def find_spec(self, fullname, path, target=None):
                if fullname == 'webview.platforms.winforms':
                    return ModuleSpec(fullname, self, origin=patched_winforms)
                return None

            def create_module(self, spec):
                return None

            def exec_module(self, module):
                module.__file__ = patched_winforms
                with open(patched_winforms, 'r', encoding='utf-8') as f:
                    source = f.read()
                code = compile(source, patched_winforms, 'exec')
                exec(code, module.__dict__)

        sys.meta_path.insert(0, _PatchedWinformsFinder())


def relaunch_as_app_name():
    # macOS builds the Dock hover label (and the Cmd-Tab / Force-Quit name) from
    # the WindowServer's app name, which is pinned to the executable's filename
    # the moment the process first talks to the window server. No runtime API
    # renames it afterwards — CFBundleName only covers the menu bar, and the
    # LaunchServices display name is a different field the Dock ignores. So until
    # this ships as a real .app bundle, re-exec through an alias named after the
    # app and let that filename *be* the app name. The alias has to sit next to
    # the interpreter so venv detection (pyvenv.cfg lookup) keeps working.
    if sys.platform != "darwin":
        return

    exe = sys.executable
    if not exe or os.path.basename(exe) == APP_NAME:
        return
    # A rename that somehow fails to stick must not turn into an exec loop.
    if os.environ.get("MW_APP_NAME_RELAUNCH"):
        return

    alias = os.path.join(os.path.dirname(exe), APP_NAME)
    try:
        if os.path.islink(alias):
            if os.path.realpath(alias) != os.path.realpath(exe):
                os.unlink(alias)        # stale alias from a rebuilt venv
                os.symlink(exe, alias)
        elif os.path.exists(alias):
            return                      # a real file owns that name — hands off
        else:
            os.symlink(exe, alias)
        os.environ["MW_APP_NAME_RELAUNCH"] = "1"
        # orig_argv preserves interpreter flags (notably -u) that sys.argv drops.
        argv = getattr(sys, "orig_argv", None) or [exe, *sys.argv]
        os.execv(alias, [alias, *argv[1:]])
    except OSError:
        # Read-only venv, sandboxing, whatever: the label is cosmetic, carry on.
        os.environ.pop("MW_APP_NAME_RELAUNCH", None)


# Deliberately before the heavy imports: a re-exec throws away everything that
# has been loaded up to this point, so keep that wasted work to a minimum.
relaunch_as_app_name()

import webview  # noqa: E402
import webview.menu as wm  # noqa: E402

# Centralized service config (URIs + local viewer ports, all from .env)
sys.path.insert(0, BASE_DIR)
from log import setup_logging  # noqa: E402
setup_logging()
log = logging.getLogger(__name__)
from config import SERVICES  # noqa: E402
# Resolve the current user (mock auth) before anything that needs identity
# (workrepo, index, viewers) is imported — those call current_user() at import.
import user  # noqa: E402
user.fetch_user()
from model_settings import (SettingsError, check_provider,  # noqa: E402
                           embedding_target, read_embedding_providers,
                           read_memory_config, read_models,
                           remove_model, remove_provider, reveal_models_file,
                           save_embedding_provider,
                           save_memory_config, save_provider, set_memory_enabled)
from workrepo import (SEEKA_DIR, RepoError, add_files, copy_path,  # noqa: E402
                      create_client, create_file, create_folder, delete_client,
                      delete_path,
                      duplicate_path, file_history, file_status, flush_sync,
                      forget_reachability, local_repo_path, move_path, on_sync_state,
                      open_external, queue_external, read_agents_md, read_file, rename_path,
                      restore_version, reveal_path, start_watch, update_client,
                      upload_files, workspace_snapshot, write_agents_md, write_file,
                      write_pdf, write_session)
import docindex  # noqa: E402
import skills_manager  # noqa: E402
import index  # noqa: E402

# Drop pywebview's default Edit/View menus; we bring our own
webview.settings['SHOW_DEFAULT_MENUS'] = False


def set_app_branding():
    # macOS reads CFBundleName for the menu bar title; from a bare interpreter
    # that key is "Python"/"python3". Patch the in-memory bundle info BEFORE the
    # menu bar is built (too late once the app is running), and patch both the
    # localized and the base dictionary since lookups fall back between them.
    # The Dock hover label is a separate mechanism — see relaunch_as_app_name.
    if sys.platform != "darwin":
        return

    from Foundation import NSBundle, NSProcessInfo

    bundle = NSBundle.mainBundle()
    for info in (bundle.localizedInfoDictionary(), bundle.infoDictionary()):
        if info is not None:
            info["CFBundleName"] = APP_NAME
            info["CFBundleDisplayName"] = APP_NAME

    # Cosmetic: makes the app show up as "Mortgage Work" rather than "python3"
    # in Activity Monitor and friends.
    NSProcessInfo.processInfo().setProcessName_(APP_NAME)


def set_dock_icon():
    # Runtime Dock icon so branding shows up during development too;
    # packaging later bakes icon.icns into the .app.
    if sys.platform != "darwin":
        return

    icon_path = os.path.join(BASE_DIR, "assets", "icon.png")
    if not os.path.exists(icon_path):
        # Fall back to the sibling demo's icon so the Dock isn't the rocket
        icon_path = os.path.join(BASE_DIR, "..", "pywebview-ide", "icon.png")
    if not os.path.exists(icon_path):
        return

    from AppKit import NSApplication, NSImage

    image = NSImage.alloc().initWithContentsOfFile_(icon_path)
    if image is not None:
        NSApplication.sharedApplication().setApplicationIconImage_(image)


def windows_icon():
    # WinForms wants a real .ico for the window/taskbar icon; derive it from
    # icon.png so one source file serves both platforms.
    if sys.platform != "win32":
        return None

    ico = os.path.join(BASE_DIR, "assets", "icon.ico")
    png = os.path.join(BASE_DIR, "assets", "icon.png")
    if not os.path.exists(ico) and os.path.exists(png):
        try:
            from PIL import Image

            sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
            Image.open(png).save(ico, sizes=sizes)
        except Exception:
            return None
    return ico if os.path.exists(ico) else None


def set_taskbar_identity():
    # Without an explicit AppUserModelID the taskbar groups the window under
    # the python.exe host and shows the Python icon, ignoring the window icon.
    if sys.platform != "win32":
        return

    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MortgageWork.App")


# Menu callbacks receive no arguments, so keep the window handy at module level
main_window = None

# Data-browser viewer servers we spawn as children (falkordb / rqlite). Killed
# on exit so we never leak uvicorn processes when the window closes.
_viewer_procs = []

# Last snapshot we pushed to the frontend, so identical rescans stay silent
_last_snapshot = None

# Outbound JS messages, drained by a single dispatcher thread (see js()).
_js_queue: "queue.Queue[str]" = queue.Queue()
_js_lock = threading.Lock()
_js_thread = None


def services_payload():
    """URLs the frontend iframes point at — all three are our local viewer
    servers. Ports/hosts come from config.py so this stays in lockstep with
    the spawned servers."""
    return {
        "falkordb": SERVICES.viewer_url("falkordb"),
        "rqlite": SERVICES.viewer_url("rqlite"),
        "qdrant": SERVICES.viewer_url("qdrant"),
        "redis": SERVICES.viewer_url("redis"),
        # Not an iframe: the chat panel opens this WebSocket directly.
        "agent": SERVICES.agent_ws_url(),
    }


def push_snapshot():
    """Disk changed → hand the frontend a fresh snapshot.

    The frontend merges it in place (expanded folders, selection and open tabs
    survive), so this is safe to fire on every settled change: the tree can
    never claim something the checkout doesn't have.
    """
    global _last_snapshot
    try:
        snap = workspace_snapshot(pull=False)
    except Exception as exc:  # noqa: BLE001 — a mid-write rescan can fail; next event retries
        log.warning("watch snapshot failed: %s", exc)
        return
    # ensure_ascii keeps this a plain ASCII JS literal — no escaping surprises
    payload = json.dumps(snap)
    # Same payload = the tree has nothing to repaint. But the change that woke
    # the watcher may be a content-only rewrite of a file that was already
    # modified — invisible to the snapshot, yet stale in an open editor tab.
    # Tell the frontend to re-read its open files either way.
    if payload == _last_snapshot:
        js("refreshOpenDocs()")
        return
    _last_snapshot = payload
    js(f"applySnapshot({payload})")


def _remember(snap):
    """Record what the frontend just fetched for itself, so the watcher event
    trailing an in-app file operation doesn't push the same tree back."""
    global _last_snapshot
    _last_snapshot = json.dumps(snap)
    return snap


def _guard(fn, *args):
    """Run a file operation, errors as data.

    The JS bridge swallows tracebacks, and every one of these is a deliberate
    user action — a toast beats a silent no-op. The terminal keeps the evidence.
    """
    try:
        return fn(*args)
    except (RepoError, SettingsError) as exc:
        log.warning("api %s: %s", fn.__name__, exc)
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("api %s failed", fn.__name__)
        return {"error": f"{fn.__name__} failed: {exc}"}


# ── Memory store: the Memory tab's read side ────────────────────────────────
#
# The agent that fills this store lives in the agent service (agents/mem.py);
# here we only browse, correct and delete. That's why this opens seeka directly
# instead of importing the agent: a viewer is not part of an actor's job, and
# nothing in the UI ever needs to dream.
#
# Two processes hold a handle on the same files — see the concurrent-writer
# TODO at the top of agents/mem.py.

# How many rows the tab shows. A display limit, not a claim about the store:
# past a couple hundred the LO is searching, not scrolling.
MEMO_LIMIT = 200


def _memory_store():
    """Open the store, or None when there's nothing to open.

    No LLM and no extraction skills: nothing here dreams, and a viewer that
    can't think can't quietly spend tokens. No mkdir either — seeka's
    constructor creates the directory, so existence is checked first. Opening
    the tab on a fresh install should report an empty memory, not conjure one.
    """
    embedder = embedding_target()
    if embedder is None:
        return None
    path = local_repo_path() / SEEKA_DIR
    if not path.exists():
        return None
    from seeka import Memory
    uri, key = embedder
    return Memory(str(path), embedding_uri=uri, embedding_api_key=key)


def _memory_call(what, action):
    """Run one memory coroutine, errors as data — the async sibling of _guard.

    ``action`` receives the open store, or None when there is none yet; each
    caller decides what that means for its own shape, because "no store" is the
    normal first-run state rather than a failure.

    A fresh event loop per call: pywebview dispatches bridge methods on worker
    threads, where there is no running loop to join, and these are a handful of
    requests rather than something worth keeping a loop alive for.
    """
    try:
        return asyncio.run(action(_memory_store()))
    except (RepoError, SettingsError) as exc:
        log.warning("api %s: %s", what, exc)
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("api %s failed", what)
        return {"error": f"{what} failed: {exc}"}


def _memo_dict(memo):
    """One memo, flattened for the bridge.

    The embedding stays behind: the tab shows text, and a few hundred floats per
    row is pure transport cost. Read defensively — recall() appends
    graph-derived results that are Memo-shaped rather than actual Memos.
    """
    return {
        "id": str(getattr(memo, "id", "") or ""),
        "content": str(getattr(memo, "content", "") or ""),
        "created": int(getattr(memo, "created", 0) or 0),
        "modified": int(getattr(memo, "modified", 0) or 0),
    }


_CONV_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _read_conv_jsonl(conv_id: str):
    conv_id = str(conv_id or "").strip()
    if not _CONV_ID_RE.match(conv_id):
        raise RepoError(f"bad conversation id: {conv_id!r}")
    path = local_repo_path() / "conversations" / f"{conv_id}.jsonl"
    if not path.exists():
        raise RepoError(f"conversation not found: {conv_id}")
    meta, messages, raw_lines = None, [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw_lines.append(line)
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "meta":
            meta = obj
        else:
            messages.append(obj)
    return {
        "ok": True,
        "conv_id": conv_id,
        "path": str(path),
        "meta": meta or {"id": conv_id, "title": conv_id},
        "messages": messages,
        "raw": "\n".join(raw_lines),
    }


def _model_prices():
    path = Path(BASE_DIR) / "browser" / "model_prices.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("model price table unavailable: %s", exc)
        return {"schema": "per_1m_tokens_usd", "models": {}, "aliases": {}}


class Api:
    """Methods the frontend calls via window.pywebview.api.* — pywebview runs
    them on a worker thread, so the git clone/pull inside never blocks UI."""

    def workspace_snapshot(self):
        # Errors travel as data, not exceptions: the JS bridge would swallow
        # tracebacks, a payload the frontend can toast is far more useful.
        # Terminal prints keep the evidence around after the toast fades.
        # pull=False: boot scans the local checkout only — sub-second. The
        # frontend calls sync_workspace right after to pull in the background.
        try:
            snap = workspace_snapshot(pull=False)
            log.info("api workspace_snapshot ok · %d clients", len(snap['clients']))
            # The checkout exists now (it may have just been cloned), so this
            # is the earliest point a watcher can attach. Idempotent.
            start_watch(push_snapshot)
            return _remember(snap)
        except RepoError as exc:
            log.warning("api workspace_snapshot RepoError: %s", exc)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — never leave the UI hanging on mocks silently
            log.exception("workspace scan failed")
            return {"error": f"workspace scan failed: {exc}"}

    def sync_workspace(self):
        # Background pull + rescan; the frontend rehydrates quietly on success.
        # Bounded by design: workrepo probes the remote first, so an unreachable
        # GitHub costs one short timeout and the app stays on the local copy —
        # boot must never depend on the network being there.
        try:
            snap = workspace_snapshot(pull=True)
            # Settle debts from a previous offline session: any local commits
            # the remote hasn't seen ride out with this boot-time flush, and
            # anything edited on disk while the app was closed gets committed.
            queue_external()
            flush_sync(force_push=True)
            log.info("api sync_workspace %s",
                     'offline — local copy' if snap.get('offline') else 'ok')
            return _remember(snap)
        except RepoError as exc:
            log.warning("api sync_workspace RepoError: %s", exc)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log.exception("sync failed")
            return {"error": f"sync failed: {exc}"}

    def read_file(self, scope, relpath):
        # Same errors-as-data contract as workspace_snapshot
        try:
            return read_file(scope, relpath)
        except RepoError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not read {relpath}: {exc}"}

    def resolve_citation(self, doc_id):
        """Resolve a mai:// citation doc_id to a workspace file identity."""
        try:
            doc_id = str(doc_id or "").strip()
            if not doc_id:
                return {"error": "empty citation document id"}
            if not docindex.all_records():
                docindex.init(local_repo_path())
            records = docindex.lookup(doc_id)
            if not records:
                return {"error": f"citation document not found: {doc_id}"}
            # Prefer the product library path when the same content appears in
            # multiple scopes; guideline citations should open canonical product docs.
            records.sort(key=lambda r: 0 if str(r.get("path") or "").startswith("products/") else 1)
            rel = str(records[0].get("path") or "")
            parts = rel.split("/")
            if len(parts) > 1 and parts[0] in ("products", "conversations"):
                return {"ok": True, "doc_id": doc_id, "scope": parts[0], "path": "/".join(parts[1:])}
            if len(parts) > 2 and parts[0] == "clients":
                return {"ok": True, "doc_id": doc_id, "scope": parts[1], "path": "/".join(parts[2:])}
            return {"error": f"citation path is not openable: {rel}"}
        except Exception as exc:  # noqa: BLE001
            log.exception("citation resolve failed")
            return {"error": f"could not resolve citation: {exc}"}

    def write_file(self, scope, relpath, content):
        try:
            return write_file(scope, relpath, content)
        except RepoError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not save {relpath}: {exc}"}

    def write_pdf(self, scope, relpath, b64):
        # Filled PDF forms from the viewer — bytes come back base64'd
        return _guard(write_pdf, scope, relpath, b64)

    def save_session(self, state):
        # UI session (tabs, focused client, chat) — restored on next launch.
        # Best-effort by design: losing it costs a few clicks, not work.
        try:
            return write_session(state)
        except RepoError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not save session: {exc}"}

    def load_conv_inspector(self, conv_id):
        try:
            data = _read_conv_jsonl(conv_id)
            data["prices"] = _model_prices()
            return data
        except Exception as exc:  # noqa: BLE001
            log.exception("conv inspector load failed")
            return {"error": str(exc)}

    def open_conv_inspector(self, conv_id):
        # Kept for compatibility with older frontend builds. New UI opens the
        # inspector as an in-app editor tab and calls load_conv_inspector().
        return self.load_conv_inspector(conv_id)

    def sync_now(self):
        # Status-bar click: the manual retry for "we booted offline". Does the
        # whole round — re-probe the remote, pull, commit whatever is pending
        # (incl. unpushed commits from an offline stretch), push — because that
        # is what a user means when they press a sync button.
        try:
            forget_reachability()   # a stale "no network" must not answer a click
            snap = workspace_snapshot(pull=True)
            queue_external()
            flush_sync(force_push=True)
            return _remember(snap)
        except RepoError as exc:
            log.warning("api sync_now RepoError: %s", exc)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log.exception("sync failed")
            return {"error": f"sync failed: {exc}"}

    def file_status(self):
        # Source-control colors for the tree, refreshed without a full rescan.
        # Colors are decoration: on failure return nothing rather than an
        # error the UI would have to explain.
        try:
            return file_status()
        except Exception as exc:  # noqa: BLE001
            log.error("api file_status failed: %s", exc)
            return {}

    # ---- File operations. Each one writes to disk and queues a commit; the
    # frontend then rescans, so none of them describes the resulting tree. ----

    def create_file(self, scope, dirpath, name="untitled.md"):
        return _guard(create_file, scope, dirpath, name)

    def create_folder(self, scope, dirpath, name="new-folder"):
        return _guard(create_folder, scope, dirpath, name)

    def rename_path(self, scope, relpath, name):
        return _guard(rename_path, scope, relpath, name)

    def move_path(self, scope, relpath, destdir):
        return _guard(move_path, scope, relpath, destdir)

    def copy_path(self, scope, relpath, destdir):
        return _guard(copy_path, scope, relpath, destdir)

    def delete_path(self, scope, relpath):
        return _guard(delete_path, scope, relpath)

    def duplicate_path(self, scope, relpath):
        return _guard(duplicate_path, scope, relpath)

    def upload_files(self, scope, dirpath, files):
        # Drag & drop / paste — bytes arrive base64'd, see workrepo.upload_files
        return _guard(upload_files, scope, dirpath, files)

    def add_files_dialog(self, scope, dirpath):
        # The native route: the OS hands back real paths, so nothing has to
        # cross the bridge as base64. Runs on the bridge's worker thread, which
        # is exactly where a modal dialog belongs.
        try:
            picked = main_window.create_file_dialog(webview.FileDialog.OPEN,
                                                    allow_multiple=True)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"file dialog failed: {exc}"}
        if not picked:
            return {"ok": True, "count": 0, "names": []}     # cancelled
        return _guard(add_files, scope, dirpath, list(picked))

    def reveal_path(self, scope, relpath):
        return _guard(reveal_path, scope, relpath)

    def open_external(self, scope, relpath):
        return _guard(open_external, scope, relpath)

    def tail_runtime_log(self, lines=300):
        """Return the last N lines of runtime.log for the in-app console."""
        try:
            log_file = os.path.join(BASE_DIR, "runtime.log")
            if not os.path.isfile(log_file):
                return {"lines": []}
            # Read last N lines without loading the whole file into memory
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                # Simple ring-buffer approach for up to ~2 MB files
                buf = []
                for line in f:
                    buf.append(line.rstrip("\n\r"))
                    if len(buf) > int(lines):
                        buf.pop(0)
                return {"lines": buf}
        except Exception as exc:
            return {"error": str(exc)}

    def file_history(self, scope, relpath):
        return _guard(file_history, scope, relpath)

    def restore_version(self, scope, relpath, sha):
        return _guard(restore_version, scope, relpath, sha)

    def create_client(self, data):
        # New Client modal → clients/<slug>/ with client.yaml only
        return _guard(create_client, data)

    def update_client(self, slug, data):
        # Edit Client modal → rewrite the form-owned facts in client.yaml
        return _guard(update_client, slug, data)

    def delete_client(self, slug):
        return _guard(delete_client, slug)

    def set_native_theme(self, dark):
        # The page repaints itself from CSS tokens; only the OS chrome needs us
        return set_native_theme(bool(dark))

    # ---- Model settings. A YAML file in the user's home directory, read and
    # written here so the API keys inside it never cross into the webview. ----

    def read_models(self):
        return _guard(read_models)

    def save_provider(self, provider, base_url="", api_key="", models=None):
        return _guard(save_provider, provider, base_url, api_key, models)

    def remove_provider(self, provider):
        return _guard(remove_provider, provider)

    def remove_model(self, provider, model):
        return _guard(remove_model, provider, model)

    def check_provider(self, provider, model=""):
        # One real round trip through chak — runs on the bridge's worker thread,
        # so a slow endpoint never freezes the UI.
        return _guard(check_provider, provider, model)

    def reveal_models_file(self):
        return _guard(reveal_models_file)

    # ---- Memory. What the agent has learned from conversations, and the LO's
    # controls over it. Extraction is an LLM guess, so it has to be
    # correctable — a wrong memo left in place keeps misinforming clerk. ----

    def read_memory_config(self):
        return _guard(read_memory_config)

    def save_memory_config(self, provider, model=""):
        return _guard(save_memory_config, provider, model)

    def save_embedding_provider(self, provider, api_key, model=""):
        return _guard(save_embedding_provider, provider, api_key, model)

    def read_embedding_providers(self):
        return _guard(read_embedding_providers)

    def set_memory_enabled(self, enabled):
        return _guard(set_memory_enabled, bool(enabled))

    def list_memos(self):
        async def action(store):
            if store is None:
                return {"memos": []}
            rows = await store.memos(limit=MEMO_LIMIT)
            return {"memos": [_memo_dict(m) for m in rows]}
        return _memory_call("list_memos", action)

    def search_memos(self, query=""):
        query = (query or "").strip()
        if not query:
            return self.list_memos()

        async def action(store):
            if store is None:
                return {"memos": []}
            # recall() warns when notes are still waiting on dream(). Not
            # actionable here: this process has no model to dream with, and the
            # agent's tick will get to them.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                hits = await store.recall(query, n=MEMO_LIMIT)
            return {"memos": [_memo_dict(m) for m in hits]}
        return _memory_call("search_memos", action)

    def update_memo(self, memo_id, content):
        content = (content or "").strip()
        if not content:
            return {"error": "a memory can't be empty — delete it instead"}

        async def action(store):
            if store is None:
                return {"error": "no memories to edit yet"}
            try:
                # seeka re-embeds, so a corrected memo also becomes findable by
                # what it now says rather than what it used to.
                await store.update(memo_id, content)
            except KeyError:
                # The agent consolidated it away mid-edit.
                return {"error": "that memory is gone — refresh the list"}
            return {"ok": True}
        return _memory_call("update_memo", action)

    def delete_memo(self, memo_id):
        async def action(store):
            if store is None:
                return {"error": "no memories to delete yet"}
            await store.delete(memo_id)
            return {"ok": True}
        return _memory_call("delete_memo", action)

    def forget_memories(self):
        async def action(store):
            if store is None:
                return {"ok": True}  # nothing stored — already in the end state
            # Memos, pending notes and graph in one shot. Also what unlocks the
            # embedder choice: no vectors left to strand in an abandoned space.
            await store.forget()
            return {"ok": True}
        return _memory_call("forget_memories", action)

    # ---- Workspace instructions (AGENTS.md). The LO's personal rules and
    # preferences, injected into the chat agent's system prompt. Stored at
    # the repo root so it syncs across machines. ----

    def read_agents_md(self):
        return _guard(read_agents_md)

    def write_agents_md(self, content):
        return _guard(write_agents_md, content)

    # ---- Indexing pipeline. The frontend queries status on boot and
    # triggers manual retry from the status bar's reload icon. ----

    def indexing_status(self):
        return index.summary()

    def retry_indexing(self):
        threading.Thread(target=index.retry_failed, daemon=True).start()
        return {"ok": True}

    # ---- Skills (market repo). The UI calls these to browse, install, and
    # toggle the skills that appear in the Tools panel and Tool Market. ----

    def list_skills(self):
        return _guard(skills_manager.skill_inventory)

    def refresh_skills(self):
        # Pull the market repo then return fresh inventory — the Tool Market
        # calls this on open so newly-published skills show up without a restart.
        # Bounded on the git side (15s timeout on ls-remote, 90s on pull); an
        # unreachable remote just returns the existing local inventory.
        try:
            status = skills_manager.sync_market()
            log.info("api refresh_skills: %s", status)
        except Exception as exc:  # noqa: BLE001
            log.exception("refresh_skills failed")
        return _guard(skills_manager.skill_inventory)

    def install_skill(self, skill_id):
        result = skills_manager.install_skill(skill_id)
        log.info("🧩 skill install · %s · %s", skill_id, result)
        return _guard(skills_manager.skill_inventory)

    def uninstall_skill(self, skill_id):
        result = skills_manager.uninstall_skill(skill_id)
        log.info("🧩 skill uninstall · %s · %s", skill_id, result)
        return _guard(skills_manager.skill_inventory)

    def toggle_skill(self, skill_id, enabled):
        result = skills_manager.set_enabled(skill_id, bool(enabled))
        log.info("api toggle_skill %s: %s", skill_id, result)
        return _guard(skills_manager.skill_inventory)


def start_viewers():
    """Spawn the local data-browser servers with the current venv's Python, so
    the clients (zig/chak/fastapi) resolve. Each reads its own connection from
    config.py; failures are logged, not fatal — the app still runs without them.

    Script names carry a _viewer suffix to avoid shadowing same-name PyPI
    packages (e.g. the pip falkordb package that zig depends on).

    When frozen (PyInstaller), the executable cannot run an arbitrary Python
    script from the command line — it only knows how to run app.py.  Instead we
    re-invoke ourselves with ``--worker <name>`` and app.py dispatches to the
    right viewer via :func:`run_worker`.
    """
    frozen = getattr(sys, 'frozen', False)
    popen_kwargs: dict = dict(cwd=BASE_DIR, start_new_session=True)
    if sys.platform == 'win32' and frozen:
        popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        # Capture worker stderr so crashes aren't silently lost.
        _worker_err = open(os.path.join(BASE_DIR, 'worker_errors.log'), 'a',
                           encoding='utf-8', errors='replace')
        popen_kwargs['stderr'] = _worker_err
        popen_kwargs['stdout'] = _worker_err

    viewers = [
        ("falkordb", "falkordb_viewer.py"),
        ("rqlite", "rqlite_viewer.py"),
        ("qdrant", "qdrant_viewer.py"),
        ("redis", "redis_viewer.py"),
    ]
    for name, script_name in viewers:
        try:
            if frozen:
                cmd = [sys.executable, "--worker", name]
            else:
                script = os.path.join(BASE_DIR, "browser", script_name)
                cmd = [sys.executable, script]
            _viewer_procs.append(subprocess.Popen(cmd, **popen_kwargs))
            log.info("viewer started %s → %s", name, SERVICES.viewer_url(name))
        except Exception as exc:
            log.error("viewer failed to start %s: %s", name, exc)
    # The chat agent service lives at the repo root (it's an app service, not a
    # data browser) but is spawned and reaped exactly like the viewers.
    try:
        if frozen:
            cmd = [sys.executable, "--worker", "agent"]
        else:
            script = os.path.join(BASE_DIR, "agent_service.py")
            cmd = [sys.executable, script]
        _viewer_procs.append(subprocess.Popen(cmd, **popen_kwargs))
        log.info("agent started → %s", SERVICES.agent_ws_url())
    except Exception as exc:
        log.error("agent failed to start: %s", exc)
    atexit.register(stop_viewers)


def stop_viewers():
    # Each child was started with start_new_session=True, so it leads its own
    # process group. Kill the whole group — uvicorn (agent_service) may have
    # spawned workers of its own, and killing only the leader orphans them.
    # This is the path that matters when the window closes or the process is
    # killed without running atexit: SIGTERM to the group reaches everyone.
    for p in _viewer_procs:
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                p.terminate()
    _viewer_procs.clear()


_WORKERS = {
    "falkordb": "browser/falkordb_viewer.py",
    "rqlite":   "browser/rqlite_viewer.py",
    "qdrant":   "browser/qdrant_viewer.py",
    "redis":    "browser/redis_viewer.py",
    "agent":    "agent_service.py",
}


def run_worker(name: str) -> None:
    """Run a viewer or agent service in-process.

    Called via ``--worker <name>`` when the frozen executable spawns its own
    subprocesses — the exe must be able to run the viewer scripts even though
    they are data files, not console arguments.
    """
    import runpy
    import traceback

    if name not in _WORKERS:
        print(f"Unknown worker: {name}", file=sys.stderr)
        sys.exit(1)

    if getattr(sys, 'frozen', False):
        script_path = os.path.join(sys._MEIPASS, _WORKERS[name])
    else:
        script_path = os.path.join(BASE_DIR, _WORKERS[name])

    # Viewer scripts have their own argparse in __main__; clear sys.argv
    # so the parent's --worker flag doesn't leak into their parser.
    sys.argv = [script_path]

    log.info("worker %s starting: %s", name, script_path)
    try:
        runpy.run_path(script_path, run_name='__main__')
    except Exception:
        traceback.print_exc()
        log.error("worker %s crashed", name, exc_info=True)
        sys.exit(1)


def js(script):
    """Send JS to the window without ever blocking the caller.

    `evaluate_js` waits on the webview's reply with no timeout of its own, so
    calling it straight from a sync/watch worker can park that worker — and the
    work it was in the middle of — indefinitely. Everything goes through one
    dispatcher thread instead: order is preserved, and no background job can be
    held hostage by the UI layer.
    """
    global _js_thread
    if main_window is None:
        return
    _js_queue.put(script)
    with _js_lock:
        if _js_thread is None or not _js_thread.is_alive():
            _js_thread = threading.Thread(target=_js_pump, daemon=True)
            _js_thread.start()


def _js_pump():
    while True:
        script = _js_queue.get()
        try:
            main_window.evaluate_js(script)
        except Exception as exc:  # noqa: BLE001 — a UI message is never worth a crash
            log.warning("js dropped (%s): %s", exc, script[:60])


def toast(msg):
    js(f"showToast({msg!r})")


# ---- File menu ----

def new_client():
    toast("New Client — creates ~/MortgageWork/clients/<name>/ from template (demo)")


def open_clients_folder():
    result = main_window.create_file_dialog(webview.FileDialog.FOLDER)
    if result:
        toast(f"Workspace folder: {result[0]} (demo)")


def reveal_in_finder():
    toast("Reveal current client folder in Finder (demo)")


# ---- Go menu ----

def go_clients():
    js("goHome(); switchView('clients')")


def go_products():
    js("switchView('products')")


# ---- View menu ----

def toggle_sidebar():
    js('togglePanel("sidebar")')


def toggle_chat():
    js('togglePanel("chat")')


def focus_chat():
    js("focusChat()")


# ---- AI menu ----

def use_model(model):
    def handler():
        js(f"setModel({model!r})")
        toast(f"Model switched: {model}")

    return handler


def run_missing_docs():
    toast("AI checking missing documents for current client… (demo)")


def run_income_analysis():
    toast("AI running income analysis… (demo)")


def export_mismo():
    toast("Exporting MISMO 3.4 for LOS import… (demo)")


MENU = [
    wm.Menu(
        "File",
        [
            wm.MenuAction("New Client…", new_client),
            wm.MenuAction("Open Workspace Folder…", open_clients_folder),
            wm.MenuSeparator(),
            wm.MenuAction("Reveal in Finder", reveal_in_finder),
        ],
    ),
    wm.Menu(
        "Go",
        [
            wm.MenuAction("Clients", go_clients),
            wm.MenuAction("Product Library", go_products),
        ],
    ),
    wm.Menu(
        "View",
        [
            wm.MenuAction("Toggle Sidebar", toggle_sidebar),
            wm.MenuAction("Toggle AI Panel", toggle_chat),
            wm.MenuSeparator(),
            wm.MenuAction("Focus Chat Input", focus_chat),
        ],
    ),
    wm.Menu(
        "AI",
        [
            wm.Menu(
                "Model",
                [
                    wm.MenuAction("gpt-4o", use_model("gpt-4o")),
                    wm.MenuAction("gpt-4o-mini", use_model("gpt-4o-mini")),
                    wm.MenuAction("claude-sonnet", use_model("claude-sonnet")),
                ],
            ),
            wm.MenuSeparator(),
            wm.MenuAction("Check Missing Documents", run_missing_docs),
            wm.MenuAction("Run Income Analysis", run_income_analysis),
            wm.MenuAction("Export MISMO 3.4…", export_mismo),
        ],
    ),
]


def force_dark_chrome(window):
    # Native chrome (title bar, menu) follows the page's dark theme on both
    # platforms — macOS via DarkAqua, Windows via DWM + a dark MenuStrip.
    if sys.platform == "darwin":
        force_dark_chrome_macos()
    elif sys.platform == "win32":
        force_dark_chrome_windows()


def force_dark_chrome_macos():
    from AppKit import NSApp, NSAppearance
    from PyObjCTools import AppHelper

    def apply():
        NSApp.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
        # Re-assert the Dock icon here rather than before start(): pywebview
        # builds its own NSApplication during start() and clobbers any icon set
        # beforehand. Applying it in this post-start, main-thread callback makes
        # it actually stick.
        set_dock_icon()
        # Fallback rename of the app menu title, in case the bundle-info patch
        # was applied too late on some macOS versions
        main_menu = NSApp.mainMenu()
        if main_menu and main_menu.numberOfItems() > 0:
            main_menu.itemAtIndex_(0).submenu().setTitle_(APP_NAME)

    # webview.start() callbacks run on a worker thread; AppKit UI mutations
    # must happen on the main thread or they are silently ignored.
    AppHelper.callAfter(apply)


def force_dark_chrome_windows():
    # Windows paints the title bar and the WinForms MenuStrip white and
    # pywebview exposes no theming hooks, so restyle both by hand.
    import ctypes

    from System import Func, Type
    from System.Drawing import Color
    from System.Windows.Forms import (
        MenuStrip,
        ProfessionalColorTable,
        ToolStripProfessionalRenderer,
    )

    # The start() callback runs concurrently with window construction, so
    # window.native may not be assigned yet. before_show fires once the
    # WinForms Form exists (handle included) — wait for that, then restyle.
    main_window.events.before_show.wait(10)
    form = main_window.native
    if form is None:
        return

    # Same palette as the page: --bg for the bar, raised tone for dropdowns
    BG = Color.FromArgb(0x12, 0x12, 0x11)
    RAISE = Color.FromArgb(0x1B, 0x1B, 0x19)
    HOVER = Color.FromArgb(0x2A, 0x2A, 0x27)
    BORDER = Color.FromArgb(0x2E, 0x2E, 0x2B)
    TEXT = Color.FromArgb(0xD2, 0xD2, 0xCC)

    class DarkTable(ProfessionalColorTable):
        __namespace__ = "MortgageWork"

        @property
        def MenuStripGradientBegin(self): return BG
        @property
        def MenuStripGradientEnd(self): return BG
        @property
        def MenuItemSelected(self): return HOVER
        @property
        def MenuItemSelectedGradientBegin(self): return HOVER
        @property
        def MenuItemSelectedGradientEnd(self): return HOVER
        @property
        def MenuItemPressedGradientBegin(self): return RAISE
        @property
        def MenuItemPressedGradientEnd(self): return RAISE
        @property
        def MenuItemBorder(self): return HOVER
        @property
        def MenuBorder(self): return BORDER
        @property
        def ToolStripDropDownBackground(self): return RAISE
        @property
        def ImageMarginGradientBegin(self): return RAISE
        @property
        def ImageMarginGradientMiddle(self): return RAISE
        @property
        def ImageMarginGradientEnd(self): return RAISE
        @property
        def SeparatorDark(self): return BORDER
        @property
        def SeparatorLight(self): return BORDER

    def paint_items(items):
        # Renderer only covers backgrounds; item text color is per-item
        for it in items:
            it.ForeColor = TEXT
            if hasattr(it, "DropDownItems") and it.DropDownItems.Count:
                paint_items(it.DropDownItems)

    def apply():
        # Dark title bar: DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older Win10)
        handle = form.Handle.ToInt64()
        on = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    handle, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        # Cleaner caption: WTNCA_NODRAWICON tells the theme engine to skip
        # drawing the caption icon. Unlike the WM_SETICON-null hack this only
        # affects painting — taskbar and Alt-Tab keep the window icon.
        class WTA_OPTIONS(ctypes.Structure):
            _fields_ = [("dwFlags", ctypes.c_uint32), ("dwMask", ctypes.c_uint32)]

        WTNCA_NODRAWICON = 0x2
        opts = WTA_OPTIONS(WTNCA_NODRAWICON, WTNCA_NODRAWICON)
        ctypes.windll.uxtheme.SetWindowThemeAttribute(
            handle, 1, ctypes.byref(opts), ctypes.sizeof(opts))  # 1 = WTA_NONCLIENT
        for ctrl in form.Controls:
            if isinstance(ctrl, MenuStrip):
                ctrl.BackColor = BG
                ctrl.ForeColor = TEXT
                ctrl.Renderer = ToolStripProfessionalRenderer(DarkTable())
                paint_items(ctrl.Items)

    # Same thread rule as pywebview itself: WinForms mutations go through Invoke
    if form.InvokeRequired:
        form.Invoke(Func[Type](apply))
    else:
        apply()


def set_native_theme(dark: bool) -> dict:
    """Repaint the OS title bar to match the page theme.

    Called from the frontend whenever the theme flips (and once at boot). This is
    best effort by design: the caption is drawn by the OS, and a Windows build
    without the immersive-dark-mode attribute or a locked-down macOS appearance
    just keeps the frame it had. A dark bar over a light page is cosmetic, so a
    failure here reports itself and changes nothing else.
    """
    try:
        if sys.platform == "win32":
            import ctypes

            from System import Func, Type

            form = main_window.native if main_window else None
            if form is None:
                return {"ok": False, "error": "no native window"}

            def apply():
                handle = form.Handle.ToInt64()
                on = ctypes.c_int(1 if dark else 0)
                for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, 19 on older Win10
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                            handle, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                        break
                # Nudge the frame to redraw: DWM only repaints the caption on the
                # next non-client paint, so an idle window would keep the old bar.
                form.Invalidate()

            if form.InvokeRequired:
                form.Invoke(Func[Type](apply))
            else:
                apply()
        elif sys.platform == "darwin":
            from AppKit import NSApp, NSAppearance
            from PyObjCTools import AppHelper

            name = "NSAppearanceNameDarkAqua" if dark else "NSAppearanceNameAqua"
            AppHelper.callAfter(
                lambda: NSApp.setAppearance_(NSAppearance.appearanceNamed_(name)))
        return {"ok": True}
    except Exception as e:  # noqa: BLE001 - cosmetic; never take the app down for it
        return {"ok": False, "error": str(e)}


def main():
    global main_window
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--dev", action="store_true",
                        help="load the Vite dev server (hot reload) instead of frontend/dist")
    parser.add_argument("--worker", type=str, metavar="NAME",
                        help="Run a viewer/agent worker (internal subprocess use)")
    args = parser.parse_args()

    # ── Worker mode: the frozen exe spawned itself to run a viewer ──────
    if args.worker:
        run_worker(args.worker)
        return

    set_app_branding()
    # On macOS the Dock icon is applied post-start inside force_dark_chrome_macos:
    # pywebview resets the app icon during start(), so setting it here wouldn't
    # stick. set_dock_icon() is a no-op on other platforms anyway.
    set_taskbar_identity()
    # Dev: point at the Vite dev server (--dev + `npm run dev` in frontend/).
    # Prod: load the built bundle; pywebview's local HTTP server avoids the
    # file:// + ES module CORS restriction under Windows WebView2.
    # LO_DEV=1 still works for muscle memory / CI.
    dev_mode = bool(args.dev or os.environ.get("LO_DEV"))
    if dev_mode:
        url = "http://localhost:5273"
    else:
        url = os.path.join(BASE_DIR, "frontend", "dist", "index.html")
    main_window = webview.create_window(
        "",
        url,
        width=1520,
        height=920,
        min_size=(1080, 680),
        # The bridge the frontend uses to pull real workspace data
        js_api=Api(),
        # pywebview otherwise injects `user-select: none` on <body>, which
        # kills text selection in documents (the PDF text layer included).
        # UI chrome opts out with its own user-select: none per component.
        text_select=True,
        # Match the page's dark theme so there's no white flash on startup
        background_color="#000000",
        # Stay hidden until the DOM is ready — the user never sees the blank
        # window; it appears with the boot animation already playing.
        hidden=True,
    )

    def reveal(window=None):
        # Tell the frontend where the viewer iframes should point (sourced from
        # config.py/.env; keeps Python config and JS iframes in lockstep).
        # In frozen builds we always show the developer UI surfaces (Runtime
        # panel, conversation inspector) even though the URL is the built
        # frontend bundle — the user still wants visibility into service health.
        frozen = getattr(sys, 'frozen', False)
        app_config = {"mode": "dev" if dev_mode else "prod", "dev": dev_mode or frozen}
        main_window.evaluate_js(f"window.__APP_CONFIG__ = {json.dumps(app_config)}")
        main_window.evaluate_js(f"window.__SERVICES__ = {json.dumps(services_payload())}")
        main_window.evaluate_js("window.applyAppConfig && window.applyAppConfig(window.__APP_CONFIG__)")
        main_window.show()
        # Bootstrap the indexing pipeline: init SQLite, create RAG dataset
        # (idempotent), and recover any tasks left in-flight by a prior crash.
        # All async — none of this should delay the window or block on network.
        def _boot_indexing():
            from workrepo import local_repo_path
            repo = local_repo_path()
            try:
                index.init(repo)
            except Exception as exc:
                log.error("index init_db failed: %s", exc)
                return
            # Load (or rebuild) the content index. Already in a daemon thread,
            # so it never blocks the window — normal boots just parse an existing
            # text file; only a missing index triggers a full rebuild.
            try:
                import docindex
                docindex.init(Path(repo))
            except Exception as exc:
                log.error("docindex init failed: %s", exc)
            threading.Thread(target=index.ensure_dataset, daemon=True).start()
            threading.Thread(target=index.recover_stale, daemon=True).start()

        threading.Thread(target=_boot_indexing, daemon=True).start()

    main_window.events.loaded += reveal
    # Sync-engine state → status bar. Registered before start() so even the
    # first flush finds a listener; js() no-ops until the window exists.
    on_sync_state(lambda state, detail: js(f"setSyncState({state!r}, {detail!r})"))
    # Indexing state → status bar + tree markers. The callback receives
    # (state, detail, indexing_paths, failed_paths). paintIndexing toggles
    # per-node markers: a spinner for indexing, a bang for failed.
    def _on_indexing(state, detail, indexing, failed):
        js(f"setIndexingState({state!r}, {detail!r})")
        js(f"paintIndexing({json.dumps(indexing)}, {json.dumps(failed)})")

    index.on_indexing_state(_on_indexing)
    # A save inside the debounce window would otherwise die with the process —
    # flush on the way out so closing the window never loses the last edit.
    # force_push: shutdown must not defer — there is no "next interval" after exit.
    atexit.register(lambda: flush_sync(force_push=True))
    # Spin up the data-browser servers (falkordb / rqlite) before the window so
    # they're ready by the time a user clicks into the runtime services.
    start_viewers()

    # Ctrl+C must reach Python's handler even while the main thread is inside
    # webview's native run loop (where KeyboardInterrupt stays pending). The
    # default SIGINT disposition reraises on the main thread, which never fires
    # if it's blocked in a C call. Installing an explicit handler that calls
    # stop_viewers() + sys.exit() guarantees the child processes (including
    # clerk inside agent_service) are reaped on every exit path.
    def _on_signal(signum, frame):
        stop_viewers()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    # Menus are parked for now — add menu=MENU back when the app grows into them
    log.info("starting webview window...")
    try:
        webview.start(force_dark_chrome, main_window, debug=False,
                      http_server=True, icon=windows_icon())
    except Exception:
        log.exception("webview.start() crashed")
        raise
    log.info("webview.start() returned")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback as _tb
        _tb.print_exc()
        if getattr(sys, 'frozen', False):
            input("\nApp crashed. Press Enter to exit...")
