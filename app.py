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
import time
import warnings
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

APP_NAME = "Mortgage Work"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    # In PyInstaller frozen builds, __file__ lives inside Contents/MacOS/,
    # but all bundled data files (frontend/dist, .env, browser/, assets/)
    # reside under Contents/Resources/ — sys._MEIPASS points there.
    BASE_DIR = sys._MEIPASS


# ── Worker fast path ──────────────────────────────────────────────────────
# The frozen exe re-spawns itself to host the agent service (see
# start_services). That child never needs pywebview, PyObjC, or the agents
# stack — but it inherits this module's top-level imports, which cost
# several seconds of LLM-stack loading. Dispatch the worker branch before
# any heavy import and let the child boot lean.

_WORKERS = {
    # Frozen releases never spawn the data viewers (dev/debug surface, not
    # bundled) — the only worker an exe re-invokes is the agent service.
    "agent":    "agent_service.py",
}


def run_worker(name: str) -> None:
    """Run the agent service in-process.

    Called via ``--worker <name>`` when the frozen executable spawns its own
    subprocesses — the exe must be able to run the bundled service script
    even though it is a data file, not a console argument.
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

    # Service scripts have their own argparse in __main__; clear sys.argv
    # so the parent's --worker flag doesn't leak into their parser.
    sys.argv = [script_path]

    log.info("worker %s starting: %s", name, script_path)
    try:
        runpy.run_path(script_path, run_name='__main__')
    except Exception:
        traceback.print_exc()
        log.error("worker %s crashed", name, exc_info=True)
        sys.exit(1)


if "--worker" in sys.argv:
    idx = sys.argv.index("--worker")
    if idx + 1 >= len(sys.argv):
        print("usage: Mortgage Work --worker <name>", file=sys.stderr)
        sys.exit(2)
    sys.path.insert(0, BASE_DIR)
    from log import setup_logging  # noqa: E402
    setup_logging()
    log = logging.getLogger(__name__)
    run_worker(sys.argv[idx + 1])

# ── Windows WebView2 / pythonnet bootstrap ───────────────────────────────
# Must run before ``import webview``: pywebview's WinForms backend imports
# pythonnet at module level.  The PyInstaller runtime hook
# (_pyi_runtime_edge.py) calls the same bootstrap, so dev and frozen builds
# share one loader strategy.  Diagnostics are logged after setup_logging().
from webview_bootstrap import bootstrap_windows_webview  # noqa: E402

_WEBVIEW_BOOTSTRAP = bootstrap_windows_webview(
    BASE_DIR, frozen=getattr(sys, 'frozen', False))


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

# Centralized service config (auth URL + local agent port, all from .env)
sys.path.insert(0, BASE_DIR)
from log import setup_logging  # noqa: E402
setup_logging()
log = logging.getLogger(__name__)
log.info("webview bootstrap: runtime=%s config=%s patched_winforms=%s",
         _WEBVIEW_BOOTSTRAP.get('pythonnet_runtime'),
         _WEBVIEW_BOOTSTRAP.get('runtime_config'),
         _WEBVIEW_BOOTSTRAP.get('patched_winforms'))
from config import SERVICES, app_version  # noqa: E402
# Restore the logged-in identity (session from the auth service, stored in
# the OS keychain — see auth.py) before anything that needs identity imports.
# Nobody logged in yet → everything below degrades gracefully and the UI
# shows the login screen instead of a workspace.
import user  # noqa: E402
import auth  # noqa: E402
import httpx  # noqa: E402
user.fetch_user()
from settings import (SettingsError, check_provider,  # noqa: E402
                      embedding_target, read_embedding_providers,
                      read_kb_config,
                      read_memory_config, read_models,
                      remove_model, remove_provider, reveal_models_file,
                      save_embedding_provider,
                      save_kb_config,
                      save_memory_config, save_memory_llm,
                      save_provider, set_memory_enabled)
from shared_kb import check_shared_kb  # noqa: E402
from workrepo import (SEEKA_DIR, STAGES, RepoError, _emit_boot, add_files,  # noqa: E402
                      copy_path, create_client, create_file, create_folder,
                      delete_client, delete_path, paste_text,
                      duplicate_path, file_history, file_status, flush_sync,
                      forget_reachability, is_offline, local_repo_path, move_path,
                      on_boot_progress, on_sync_state, open_external,
                      queue_external, queue_sync,
                      read_agents_md, read_file, rename_path,
                      restore_version, reveal_path, set_client_stage, start_watch,
                      update_client,
                      upload_files, workspace_snapshot, write_agents_md, write_file,
                      write_pdf, write_session, read_model_pref, write_model_pref)
import docindex  # noqa: E402
import skills_manager  # noqa: E402
import index  # noqa: E402
import connector_service  # noqa: E402
import runtime_services  # noqa: E402
from integration.kg import FalkorStoreClient  # noqa: E402
from integration.rag import QdrantStoreClient  # noqa: E402
from settings import connectors as _conn_settings  # noqa: E402
# NOTE: agents.organizer is imported lazily inside Api.organize_client_folder —
# it pulls in the chak LLM stack (~3s at boot) and only that one menu action
# needs it. Boot must stay cheap.

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

# Local child services we spawn (the agent service). Killed on exit so we
# never leak uvicorn processes when the window closes.
_service_procs = []

# Last snapshot we pushed to the frontend, so identical rescans stay silent
_last_snapshot = None

# Outbound JS messages, drained by a single dispatcher thread (see js()).
_js_queue: "queue.Queue[str]" = queue.Queue()
_js_lock = threading.Lock()
_js_thread = None


def services_payload():
    """URLs the frontend needs — just the local agent WebSocket. The agent
    port comes from config.py so this stays in lockstep with the spawned
    server.

    The data-store viewers (browser/) are a standalone unit: the frontend
    points its iframes at their fixed loopback ports directly and probes
    their health itself, so nothing viewer-related is injected here."""
    return {
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


def open_url(url):
    """Hand an http(s) URL to the OS default browser.

    Used by the embedded data viewers: the iframe is fine for a peek, but a
    real browser window gives the full screen they're actually inspecting in.
    Scheme-checked so a crafted bridge call can't launch arbitrary commands
    (some platforms route exotic schemes to handlers).
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return {"error": f"refusing to open non-http URL: {url!r}"}
    webbrowser.open(url)
    return {"ok": True}


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
    path = Path(BASE_DIR) / "model_prices.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("model price table unavailable: %s", exc)
        return {"schema": "per_1m_tokens_usd", "models": {}, "aliases": {}}


# ── Usage stats ────────────────────────────────────────────────────────────
# Aggregate LLM usage across every conversation jsonl in the work-repo, per
# day × model.  Only the last 30 days are scanned — the UI offers 7/30-day
# views, and history older than that is not worth re-parsing on every open.

USAGE_WINDOW_DAYS = 30


def _usage_day(value):
    """Date string (YYYY-MM-DD) out of an ISO timestamp; None if unparseable."""
    try:
        return datetime.fromisoformat(str(value or "").strip()).date().isoformat()
    except ValueError:
        return None


def _usage_model_uri(meta: dict) -> str:
    """Same resolution as the frontend's modelUri: provider_trace wins, with
    the message/meta-level fields as fallbacks — the two must never disagree
    about which model a call was billed to."""
    pt = meta.get("provider_trace") or {}
    direct = (meta.get("model_uri") or meta.get("model_ref")
              or meta.get("model_name") or meta.get("model"))
    provider = pt.get("resolved_provider") or pt.get("provider") or meta.get("provider")
    model = pt.get("resolved_model") or pt.get("model") or direct
    if provider and model and "/" not in str(model):
        return f"{provider}/{model}"
    return str(model or provider or "unknown")


def _usage_stats():
    try:
        root = local_repo_path()
    except RepoError as exc:
        return {"error": str(exc)}
    conv_dir = root / "conversations"
    cutoff = (datetime.now() - timedelta(days=USAGE_WINDOW_DAYS)).date().isoformat()
    buckets: dict = {}
    conv_count = 0
    if conv_dir.is_dir():
        for path in sorted(conv_dir.glob("*.jsonl")):
            conv_count += 1
            created_day = None
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue            # an unreadable file must not kill the sweep
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "meta":
                    # The conversation's creation date is the fallback bucket
                    # for messages written before timestamps existed.
                    created_day = _usage_day(obj.get("created"))
                    continue
                if obj.get("role") != "assistant":
                    continue
                usage = (obj.get("metadata") or {}).get("usage") or {}
                if not usage:
                    continue
                day = _usage_day(obj.get("timestamp")) or created_day
                if not day or day < cutoff:
                    continue
                key = (day, _usage_model_uri(obj.get("metadata") or {}))
                b = buckets.setdefault(
                    key, {"calls": 0, "prompt": 0, "completion": 0,
                          "cacheW": 0, "cacheR": 0, "total": 0})
                prompt = usage.get("prompt_tokens") or 0
                completion = usage.get("completion_tokens") or 0
                cache_w = usage.get("cache_creation_input_tokens") or 0
                cache_r = usage.get("cache_read_input_tokens") or 0
                b["calls"] += 1
                b["prompt"] += prompt
                b["completion"] += completion
                b["cacheW"] += cache_w
                b["cacheR"] += cache_r
                b["total"] += usage.get("total_tokens") or (
                    prompt + completion + cache_w + cache_r)
    by_day: dict = {}
    for (day, uri), b in buckets.items():
        by_day.setdefault(day, []).append({"uri": uri, **b})
    days = [{"date": day,
             "models": sorted(rows, key=lambda r: r["total"], reverse=True)}
            for day, rows in sorted(by_day.items(), reverse=True)]
    return {"ok": True, "window_days": USAGE_WINDOW_DAYS, "days": days,
            "prices": _model_prices(), "conversations": conv_count,
            "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M")}


def _auth_reply(res: httpx.Response) -> dict:
    """Auth-service reply → bridge payload: the JSON body on success, a
    readable error otherwise. FastAPI errors arrive as {"detail": "..."} and
    that message is user-facing wording, so it passes through verbatim."""
    try:
        data = res.json()
    except ValueError:
        return {"error": f"auth service answered garbage (HTTP {res.status_code})"}
    if res.status_code >= 300:
        detail = data.get("detail") if isinstance(data, dict) else None
        return {"error": detail or f"auth service error (HTTP {res.status_code})"}
    return data


def _refresh_session() -> None:
    """Boot-time session refresh: trade the stored token for a fresh
    /user/me payload and overwrite the saved session with it.

    Why: the session persisted at login is frozen — its ``services`` block
    (RAG/KG endpoints and keys) reflects the server's env on the day the
    user logged in, and sessions saved before the block existed have none
    at all. runtime_services then degrades to the .env fallback and a
    release build ends up hitting http://localhost:8000. /user/me rebuilds
    ``services`` on every call and re-signs the token, so one call here
    fixes stale sessions and delivers server-side key rotation without a
    re-login. Runs synchronously before the window exists so reveal()'s
    index bootstrap already resolves the fresh endpoints.

    Degrades silently — an unreachable auth service (dev box without
    server/) keeps the stored session as-is; a rejected token logs a
    warning and leaves the session alone for the frontend to handle."""
    payload = auth.load_session()
    if not payload or not payload.get("token"):
        return
    try:
        res = httpx.get(f"{SERVICES.auth_service_url}/user/me",
                        headers={"Authorization": f"Bearer {payload['token']}"},
                        timeout=10)
    except httpx.HTTPError as exc:
        log.info("session refresh skipped — auth service unreachable: %s", exc)
        return
    fresh = _auth_reply(res)
    if fresh.get("error"):
        log.warning("session refresh rejected: %s", fresh["error"])
        return
    if not isinstance(fresh.get("user"), dict):
        log.warning("session refresh got an unexpected payload shape")
        return
    auth.save_session(fresh)
    user.apply_session(fresh)
    log.info("session refreshed · %s (%s) · plan %s",
             fresh["user"].get("name"), fresh["user"].get("id"),
             fresh["user"].get("plan"))


# How often the running app re-asks the auth service for the account's
# state. A portal-side plan change lands within this window; the write
# path re-asks anyway (the quota check), so this timer mostly drives the
# READ side — queries and the UI.
PLAN_POLL_SECS = 60


def _plan_poll_once() -> None:
    """One poll round: fresh /user/me, adopt what changed.

    The re-signed token is always worth persisting (the session never ages
    out on a long-running app), so save_session runs every round; the
    in-memory identity and the frontend only hear about it when id or
    plan actually moved — a quiet round stays quiet.

    Crossing INTO a KB-eligible plan re-fires the index bootstrap: the
    free leg never set _boot_owner, so this run does the real work and
    the boot reconciler backfills whatever was never submitted. Crossing
    OUT needs no teardown — every submit path asks the live predicate.
    """
    payload = auth.load_session()
    if not payload or not payload.get("token"):
        return
    try:
        res = httpx.get(f"{SERVICES.auth_service_url}/user/me",
                        headers={"Authorization": f"Bearer {payload['token']}"},
                        timeout=10)
    except httpx.HTTPError:
        return  # offline round — the next tick tries again
    fresh = _auth_reply(res)
    if fresh.get("error") or not isinstance(fresh.get("user"), dict):
        return
    auth.save_session(fresh)
    current = user.fetch_user() if not user.is_logged_in() else user.current_user()
    new_plan = str(fresh["user"].get("plan") or user.DEFAULT_PLAN).lower()
    if current is None:
        return
    if current.id == fresh["user"].get("id") and current.plan == new_plan:
        return  # quiet round: only the token aged
    old_plan = current.plan
    user.apply_session(fresh)
    if old_plan != new_plan:
        log.info("plan changed server-side · %s → %s", old_plan, new_plan)
        js(f"applyPlanUpdate({json.dumps(new_plan)})")
        if user.current_user().can_index_kb():
            threading.Thread(target=_boot_indexing, daemon=True).start()


def _plan_poll_loop() -> None:
    """Forever-loop wrapper — a watcher thread must never die on one bad
    round, so every exception is swallowed at this layer."""
    while True:
        time.sleep(PLAN_POLL_SECS)
        try:
            _plan_poll_once()
        except Exception as exc:  # noqa: BLE001
            log.debug("plan poll error: %s", exc)


# ── Knowledge Base data browser: raw-store clients ──
# The isolation enforcement lives here and ONLY here: the collection/graph is
# pinned to the logged-in user's own ids, and no frontend parameter can change
# it — the kb_* Api methods below don't even accept one.

_KG_STORES = {}  # (uri, graph) -> FalkorStoreClient — cache the zig connection

# Document Index reads the newest units first (latest() window over a
# created_at index) — at six figures of points, paging the whole collection
# in order is off the table.
_KB_WINDOW = 500


def _kb_qdrant():
    """Store client bound to the current user's collection; None = not
    configured (empty url → the pane degrades to a friendly board)."""
    url, key = runtime_services.qdrant_target()
    if not url:
        return None
    return QdrantStoreClient(url, key, user.current_user().rag_dataset_id)


def _kb_falkor():
    """Store client bound to the current user's graph; None = not configured.
    Instances are cached per (uri, graph) — the graph name is the user id, so
    an identity switch gets its own client with its own cached connection."""
    uri = runtime_services.falkordb_target()
    if not uri:
        return None
    graph = user.current_user().kg_graph_name
    key = (uri, graph)
    client = _KG_STORES.get(key)
    if client is None:
        client = FalkorStoreClient(uri, graph)
        _KG_STORES[key] = client
    return client


def _kb_call(what, get_store, action):
    """One store read, errors as data — each side (qdrant/falkordb) may fail
    independently and the frontend degrades only that pane."""
    try:
        store = get_store()
        if store is None:
            return {"error": "not configured"}
        return action(store)
    except user.AuthError:
        return {"error": "not logged in"}
    except Exception as exc:  # noqa: BLE001
        log.warning("api %s failed: %s", what, exc)
        return {"error": str(exc)}


class Api:
    """Methods the frontend calls via window.pywebview.api.* — pywebview runs
    them on a worker thread, so the git clone/pull inside never blocks UI."""

    # ── Login flow (email code → auth service → per-user work repo) ──

    def auth_status(self):
        # The frontend asks on boot: logged in → normal workspace boot,
        # otherwise it paints the in-app login screen.
        return {"loggedIn": user.is_logged_in()}

    def app_version(self):
        # Build stamp for the Settings pane — same source as the first line
        # of runtime.log (pyproject.toml in dev, VERSION/plist when frozen).
        return {"version": app_version()}

    def login_request_code(self, email):
        try:
            res = httpx.post(f"{SERVICES.auth_service_url}/user/request-code",
                             json={"email": email}, timeout=20)
        except httpx.HTTPError as exc:
            return {"error": f"auth service unreachable: {exc}"}
        return _auth_reply(res)

    def login_verify(self, email, code, region):
        # verify doubles as sign-up: on first login the service provisions
        # the user's private work repo — generous timeout for a slow host.
        try:
            res = httpx.post(f"{SERVICES.auth_service_url}/user/verify",
                             json={"email": email, "code": code, "region": region},
                             timeout=300)
        except httpx.HTTPError as exc:
            return {"error": f"auth service unreachable: {exc}"}
        payload = _auth_reply(res)
        if payload.get("error"):
            return payload
        auth.save_session(payload)
        u = user.apply_session(payload)
        log.info("api login ok · %s (%s) · plan %s", u.name, u.id, u.plan)
        js(f"applyPlanUpdate({json.dumps(u.plan)})")
        # Mid-session login: the reveal()-time index bootstrap either bailed
        # (nobody was logged in) or ran for a different user. Re-fire it so
        # this user's dataset/graph get created right away — _boot_owner
        # inside keeps a repeat login for the same user a cheap no-op.
        threading.Thread(target=_boot_indexing, daemon=True).start()
        return {"ok": True, "user": {"id": u.id, "name": u.name,
                                     "email": u.email, "plan": u.plan}}

    def redeem_code(self, code):
        # The payment-free upgrade path: a code minted in the admin viewer
        # moves this account to the code's plan. The reply is a full fresh
        # session payload — same handling as login_verify.
        payload_session = auth.load_session() or {}
        token = payload_session.get("token", "")
        if not token:
            return {"error": "not logged in"}
        try:
            res = httpx.post(f"{SERVICES.auth_service_url}/user/redeem",
                             json={"code": code},
                             headers={"Authorization": f"Bearer {token}"},
                             timeout=20)
        except httpx.HTTPError as exc:
            return {"error": f"auth service unreachable: {exc}"}
        payload = _auth_reply(res)
        if payload.get("error"):
            return payload
        auth.save_session(payload)
        u = user.apply_session(payload)
        log.info("redeem ok · %s (%s) · plan %s", u.name, u.id, u.plan)
        js(f"applyPlanUpdate({json.dumps(u.plan)})")
        # The upgrade may have unlocked the KB — re-fire the bootstrap;
        # _boot_owner keeps it a no-op when everything already ran.
        threading.Thread(target=_boot_indexing, daemon=True).start()
        return {"ok": True, "plan": u.plan}

    def logout(self):
        # The frontend reloads the page afterwards so boot re-runs and lands
        # on the login screen. Child services keep running; they re-resolve
        # identity per request once the next user logs in.
        auth.clear_session()
        user.clear()
        return {"ok": True}

    def workspace_snapshot(self):
        # No identity → no workspace. The frontend turns this flag into the
        # login screen; everything below assumes somebody is logged in.
        if not user.is_logged_in():
            return {"auth": "required"}
        # Errors travel as data, not exceptions: the JS bridge would swallow
        # tracebacks, a payload the frontend can toast is far more useful.
        # Terminal prints keep the evidence around after the toast fades.
        # pull=False: boot scans the local checkout only — sub-second. The
        # frontend calls sync_workspace right after to pull in the background.
        # Tell the overlay up front when the checkout isn't there yet: a first
        # boot may spend minutes in clone (possibly started by a sibling
        # process), and the user must see "downloading" the whole time — not
        # a blank curtain that looks broken.
        try:
            root = local_repo_path()
            if not (root / "clients").is_dir():
                _emit_boot("cloning", user.current_user().work_repo_url)
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
            # snap["offline"] was captured during _pull — BEFORE flush_sync ran
            # the merger + push.  If flush_sync succeeded, _offline is now False
            # but the snapshot still carries the stale True from the pull phase.
            # Refresh it so the frontend doesn't flip to "offline" after a push
            # that the sync engine already reported as "ok".
            snap["offline"] = is_offline()
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

    def read_model_pref(self):
        # Last model pick, synced through the work-repo so it follows the
        # user across machines. Read failures just mean "no preference yet".
        try:
            return {"ok": True, "pref": read_model_pref()}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not read model preference: {exc}"}

    def save_model_pref(self, pref):
        try:
            return write_model_pref(pref)
        except RepoError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not save model preference: {exc}"}

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

    def load_usage_stats(self):
        # Usage page data: per day × model token aggregates over the last 30
        # days of conversations, plus the price table for costing on the
        # frontend (same pricing code path as the conversation inspector).
        try:
            return _usage_stats()
        except Exception as exc:  # noqa: BLE001
            log.exception("usage stats load failed")
            return {"error": str(exc)}

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
            # Same stale-offline fix as sync_workspace: the merger inside
            # flush_sync may have resolved a conflict that _pull couldn't.
            snap["offline"] = is_offline()
            return _remember(snap)
        except RepoError as exc:
            log.warning("api sync_now RepoError: %s", exc)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log.exception("sync failed")
            return {"error": f"sync failed: {exc}"}

    def boot_retry(self):
        # The first-run gate's button: the workspace didn't load, the user
        # pressed retry, this is the one place that is allowed to do the whole
        # slow round (clone/pull + flush) on a click instead of on boot.
        # Also kicks the skills market sync on the side — the demo machine
        # needs both repos for the agent to be useful, and its agent worker
        # may not have reached ensure_skills() if boot failed early.
        def _sync_skills_async():
            try:
                from skills_manager import ensure_skills
                ensure_skills()
            except Exception as exc:  # noqa: BLE001 — skills are additive, not load-bearing
                log.warning("boot_retry skills sync failed: %s", exc)

        threading.Thread(target=_sync_skills_async, daemon=True).start()
        try:
            forget_reachability()
            _emit_boot("retrying")
            snap = workspace_snapshot(pull=True)
            queue_external()
            flush_sync(force_push=True)
            snap["offline"] = is_offline()
            return _remember(snap)
        except RepoError as exc:
            log.warning("api boot_retry RepoError: %s", exc)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log.exception("boot retry failed")
            return {"error": f"boot failed: {exc}"}

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

    def paste_text(self, scope, dirpath, content):
        # Plain-text paste into the tree — see workrepo.paste_text
        return _guard(paste_text, scope, dirpath, content)

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

    def organize_client_folder(self, scope, model_ref=""):
        """Classify and move loose files in a client's root directory into
        the appropriate subdirectories.  *model_ref* is the active model
        from the chat panel (e.g. ``"openai/gpt-4o"``).  Progress is pushed
        to the frontend via ``window.__organizerProgress()`` so the tree
        animates each classification and move."""
        try:
            root = local_repo_path() / "clients" / scope
        except RepoError as exc:
            return {"error": str(exc)}
        if not root.is_dir():
            return {"error": f"not a client directory: clients/{scope}"}

        import json
        from agents.organizer import organize

        def _progress(phase, filename, target):
            if main_window is None:
                return
            ev = json.dumps({"phase": phase, "file": filename, "target": target})
            main_window.evaluate_js(f"window.__organizerProgress({ev})")

        result = organize(root, model_ref=model_ref,
                          on_progress=_progress,
                          queue_sync_fn=queue_sync)
        # Commit any pending changes so the tree snapshot reflects the moves
        queue_external()
        return result

    def reveal_path(self, scope, relpath):
        return _guard(reveal_path, scope, relpath)

    def open_external(self, scope, relpath):
        return _guard(open_external, scope, relpath)

    def open_url(self, url):
        return _guard(open_url, url)

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

    def client_stages(self):
        # Pipeline stages as [key, label] pairs — the Mark Status submenu
        return STAGES

    def set_client_stage(self, slug, stage):
        # Right-click "Mark Status" → client.yaml stage field only
        return _guard(set_client_stage, slug, stage)

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

    def save_memory_llm(self, provider, model=""):
        return _guard(save_memory_llm, provider, model)

    def save_embedding_provider(self, provider, api_key, model=""):
        return _guard(save_embedding_provider, provider, api_key, model)

    def read_embedding_providers(self):
        return _guard(read_embedding_providers)

    def set_memory_enabled(self, enabled):
        return _guard(set_memory_enabled, bool(enabled))

    # ---- Knowledge bases. Personal switch + shared (read-only) mounts,
    # addressed by email — storage names are derived at query time, so this
    # config never touches dataset/graph identifiers. ----

    def read_kb_config(self):
        return _guard(read_kb_config)

    def save_kb_config(self, config):
        return _guard(save_kb_config, config)

    def check_shared_kb(self, kb_id):
        # Existence probe before a mount is accepted — the settings UI refuses
        # an ID whose dataset/graph doesn't exist (or is empty).
        return _guard(check_shared_kb, kb_id)

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

    # ---- Knowledge Base (indexing pipeline). The status-bar chip queries
    # these on boot/open; the panel's failed chips retry one side at a time.
    # Plans without KB rights get the empty picture: index.jsonl still keeps
    # its disk cursor internally, but nothing about it may reach a screen. ----

    @staticmethod
    def _indexing_visible() -> bool:
        try:
            return user.current_user().can_index_kb()
        except user.AuthError:
            return False

    def knowledge_status(self):
        if not self._indexing_visible():
            return {"total": 0, "processing": 0, "failed": 0,
                    "pending": 0, "canceled": 0}
        return _guard(index.knowledge_summary)

    def knowledge_rows(self):
        if not self._indexing_visible():
            return []
        return _guard(index.panel_rows)

    def retry_index(self, doc_id, side):
        # Synchronous answer for the optimistic chip: 'processing' means the
        # re-submission took; a still-'failed' status or an error payload
        # bounces the chip back with a toast.
        result = _guard(index.retry_one, doc_id, side)
        if isinstance(result, dict):
            return result  # error payload from _guard
        return {"ok": True, "status": result}

    def retry_indexing(self):
        # Bulk self-heal — kept for the boot path; the UI retries per side
        # through retry_index now.
        result = _guard(index.retry_failed)
        if isinstance(result, dict):
            return result  # error payload from _guard
        return {"ok": True, "count": result}

    # ---- Knowledge Base data browser (raw stores). Read-only, scoped to the
    # logged-in user by the _kb_* helpers above — none of these signatures
    # takes a collection/graph, so nobody else's data is reachable. Each side
    # degrades independently: an error payload only blanks that pane. ----

    def kb_store_info(self):
        # Both sides in one call: qdrant collection meta + graph counts.
        return {
            "qdrant": _kb_call("kb_store_info", _kb_qdrant, lambda s: s.info()),
            "falkordb": _kb_call("kb_store_info", _kb_falkor, lambda s: s.stats()),
        }

    def kb_points(self, limit=None, offset=None, reset=False):
        # The newest units, newest first, one shot: {points, next}. The grid
        # loads in two phases — a small limit paints the first page fast,
        # then the caller refetches with no limit for the full _KB_WINDOW.
        # offset/reset stay in the signature for the bridge's old shape but
        # are ignored (order_by disables cursor paging).
        def _window(store):
            store.ensure_order_index()
            try:
                n = min(int(limit), _KB_WINDOW) if limit else _KB_WINDOW
            except (TypeError, ValueError):
                n = _KB_WINDOW
            return {"points": store.latest(limit=n), "next": None}
        return _kb_call("kb_points", _kb_qdrant, _window)

    def kb_roots(self):
        return _kb_call("kb_roots", _kb_falkor,
                        lambda s: {"roots": s.roots()})

    def kb_children(self, node_id, label):
        # One lazy-expansion hop; label must be in the matrix spec.
        return _kb_call("kb_children", _kb_falkor,
                        lambda s: {"children": s.children(str(node_id), str(label))})

    def kb_node(self, node_id, label):
        def _fetch(s):
            node = s.node(str(node_id), str(label))
            return {"node": node} if node else {"error": f"node not found: {node_id}"}
        return _kb_call("kb_node", _kb_falkor, _fetch)

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

    def log_frontend(self, level, message):
        """Log from the frontend JS to runtime.log for debugging."""
        try:
            msg = str(message or "")[:500]
            if level == "error":
                log.error("[frontend] %s", msg)
            elif level == "warn":
                log.warning("[frontend] %s", msg)
            else:
                log.info("[frontend] %s", msg)
        except Exception:
            pass

    # ---- Connector configuration. IM platform credentials in settings.yaml,
    # secrets reduced to masked hints before they cross the bridge. ----

    def read_connectors(self):
        return _guard(_conn_settings.read_connectors)

    def save_connector(self, platform, fields):
        result = _guard(_conn_settings.save_connector, platform, fields)
        # Restart gateway so the new config takes effect immediately
        if result and not result.get("error"):
            threading.Thread(target=connector_service.restart, daemon=True).start()
        return result

    def remove_connector(self, platform):
        result = _guard(_conn_settings.remove_connector, platform)
        # Restart gateway so the removal takes effect immediately
        if result and not result.get("error"):
            threading.Thread(target=connector_service.restart, daemon=True).start()
        return result

    # ---- Connector messaging. Gateway status, chat history, send/receive. ----

    def connector_status(self):
        return _guard(connector_service.get_status)

    def connector_history(self, platform, conv_id=None, limit=50):
        return _guard(connector_service.get_history, platform, conv_id, limit)

    def connector_conversations(self, platform):
        return _guard(connector_service.list_conversations, platform)

    def connector_send(self, platform, conv_id, text):
        return _guard(connector_service.send_message, platform, conv_id, text)

    def connector_attachment(self, path):
        """Return attachment bytes as {b64, mime} for frontend blob rendering.

        Same pattern as workrepo.read_file — the frontend does atob → Blob →
        URL.createObjectURL, which is what DocViewer uses for images.
        """
        import base64, mimetypes
        data = connector_service.read_attachment(path)
        if data is None:
            return {"error": "not found"}
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return {"b64": base64.b64encode(data).decode("ascii"), "mime": mime}

    def connector_open_attachment(self, path):
        """Open an attachment file with the system default application.

        WKWebView blocks the <a download> attribute, so file "downloads"
        are routed through here to be opened in the OS-native app.
        """
        data = connector_service.read_attachment(path)
        if data is None:
            return {"error": "not found"}
        import tempfile, os, subprocess, sys, mimetypes
        suffix = os.path.splitext(path)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", tmp_path])
            elif sys.platform == "win32":
                os.startfile(tmp_path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", tmp_path])
            return {"ok": True}
        except Exception as exc:
            log.exception("connector_open_attachment failed")
            return {"error": str(exc)}



def start_services():
    """Spawn the local agent service with the current venv's Python, so its
    clients (chak/fastapi) resolve. A failure here is logged but never fatal
    — the app window must open even when the agent can't start.

    The data-store viewers (browser/) are a standalone unit, not app services:
    they run from their own venv via browser/serve.sh and the app only borrows
    an iframe slot to display them, so nothing here spawns them.

    When frozen (PyInstaller), the executable cannot run an arbitrary Python
    script from the command line — it only knows how to run app.py. Instead
    we re-invoke ourselves with ``--worker <name>`` and app.py dispatches to
    the right service via :func:`run_worker`.
    """
    frozen = getattr(sys, 'frozen', False)
    popen_kwargs: dict = dict(cwd=BASE_DIR, start_new_session=True)
    # The child must not inherit the parent's stdio. Under launch.sh the parent
    # is piped into `tee runtime.log`, so a child that outlives app.py holds
    # the pipe's write end open and the pipeline — and the terminal — never
    # finishes. Its logs do not need stdout anyway: log.setup_logging()
    # gives every process a RotatingFileHandler straight into runtime.log,
    # which is exactly what the in-app Console panel tails.
    popen_kwargs['stdout'] = subprocess.DEVNULL
    popen_kwargs['stderr'] = subprocess.DEVNULL
    if sys.platform == 'win32' and frozen:
        popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        # Capture worker stderr so crashes aren't silently lost.
        _worker_err = open(os.path.join(BASE_DIR, 'worker_errors.log'), 'a',
                           encoding='utf-8', errors='replace')
        popen_kwargs['stderr'] = _worker_err
        popen_kwargs['stdout'] = _worker_err

    try:
        if frozen:
            cmd = [sys.executable, "--worker", "agent"]
        else:
            script = os.path.join(BASE_DIR, "agent_service.py")
            cmd = [sys.executable, script]
        _service_procs.append(subprocess.Popen(cmd, **popen_kwargs))
        # Optimistic on purpose: Popen success only means the fork worked, not
        # that uvicorn will bind. The health watcher below is the proof, and a
        # child that dies at boot now lands in runtime.log instead of leaving
        # the frontend's chat panel offline with no trace.
        log.info("agent spawned → %s", SERVICES.agent_ws_url())
        threading.Thread(target=_watch_agent_health, daemon=True).start()
    except Exception as exc:
        log.error("agent failed to start: %s", exc)
    atexit.register(stop_services)


def _watch_agent_health():
    """Verify the spawned agent actually answers /health, and say so in
    runtime.log. The permanent chat-offline red dot was invisible before:
    the spawn log line looked like "service up" even when the child died
    seconds later (port handover race, boot crash), and chatws logged
    nothing. One watcher, two answers: healthy → log it; exited → log why
    chat will stay offline."""
    proc = _service_procs[-1] if _service_procs else None
    url = f"http://127.0.0.1:{SERVICES.agent_port}/health"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            log.error("agent service exited at boot (code %s) — chat will "
                      "stay offline until the app restarts", proc.returncode)
            return
        try:
            resp = httpx.get(url, timeout=2)
            if resp.status_code == 200:
                log.info("agent service healthy → %s", SERVICES.agent_ws_url())
                return
        except Exception:
            pass
        time.sleep(1)
    log.warning("agent service not healthy after 60s — chat may stay offline")


def stop_services():
    # Each child was started with start_new_session=True, so it leads its own
    # process group. Kill the whole group — uvicorn (agent_service) may have
    # spawned workers of its own, and killing only the leader orphans them.
    # This is the path that matters when the window closes or the process is
    # killed without running atexit: SIGTERM to the group reaches everyone.
    # os.killpg is Unix-only (AttributeError on Windows); fall back to plain
    # terminate() there — launch.ps1's port sweep is the Windows backstop.
    procs = [p for p in _service_procs if p.poll() is None]
    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            p.terminate()
    # uvicorn's graceful shutdown waits out in-flight work before honouring
    # SIGTERM — a clerk or IM pass (up to 600s) can block it for minutes.
    # Closing the window must never strand the terminal that long: a short
    # grace, then the whole group dies unconditionally.
    deadline = time.monotonic() + 3.0
    for p in procs:
        while p.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
    for p in procs:
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                p.kill()
    _service_procs.clear()
    connector_service.stop()


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


def apply_mac_chrome(dark: bool):
    # Transparent title bar painted with the page's --bg: the bar reads as the
    # same black (or white) as the app body with only the traffic lights
    # floating on it — the integrated look Windows gets via immersive dark.
    from AppKit import NSApp, NSAppearance, NSColor
    from PyObjCTools import AppHelper

    def apply():
        NSApp.setAppearance_(NSAppearance.appearanceNamed_(
            "NSAppearanceNameDarkAqua" if dark else "NSAppearanceNameAqua"))
        win = getattr(main_window, "native", None) if main_window else None
        if win is None and NSApp.windows():
            win = NSApp.windows()[0]
        if win is None:
            return
        win.setTitlebarAppearsTransparent_(True)
        win.setTitleVisibility_(1)  # NSWindowTitleHidden — the app draws its own chrome
        color = NSColor.blackColor() if dark else NSColor.whiteColor()
        win.setBackgroundColor_(color)
        # pywebview deliberately paints the title bar view with the system
        # window background color so it never follows the window color (cocoa.py
        # non-frameless branch) — repaint that same view or the bar stays gray.
        try:
            bar = win.contentView().superview().subviews().lastObject()
            if bar is not None:
                bar.setBackgroundColor_(color)
        except Exception:
            log.warning("mac title bar view repaint failed", exc_info=True)

    # webview.start() callbacks run on a worker thread; AppKit UI mutations
    # must happen on the main thread or they are silently ignored.
    AppHelper.callAfter(apply)


def force_dark_chrome_macos():
    from AppKit import NSApp
    from PyObjCTools import AppHelper

    def extras():
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

    apply_mac_chrome(True)
    AppHelper.callAfter(extras)


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
        # Immersive dark mode only recolors the *active* caption — the moment
        # the window loses focus Windows falls back to the system inactive
        # caption color (gray). Pin the caption + text color explicitly: DWM
        # honors DWMWA_CAPTION_COLOR in both focus states — the same "stays
        # dark unfocused" look macOS gets from its transparent title bar.
        # COLORREF is 0x00BBGGRR; Win11-only attribute, fails harmlessly on
        # older builds. Must be the theme's --bg (pure black), not the
        # editor tone — anything lighter reads as a mismatched strip.
        caption = ctypes.c_uint32(0x000000)  # BG, byte-swapped
        caption_text = ctypes.c_uint32(0xCCD2D2)  # TEXT, byte-swapped
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            handle, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            handle, 36, ctypes.byref(caption_text), ctypes.sizeof(caption_text))
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
                # Same trick as force_dark_chrome_windows: keep the caption
                # color stable when the window loses focus. CLR_INVALID
                # (0xFFFFFFFF) resets to the system default for light mode.
                # Dark uses the theme's --bg (pure black) — a lighter tone
                # shows as a visible strip above the page.
                caption = ctypes.c_uint32(0x000000 if dark else 0xFFFFFFFF)
                caption_text = ctypes.c_uint32(0xCCD2D2 if dark else 0xFFFFFFFF)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    handle, 35, ctypes.byref(caption), ctypes.sizeof(caption))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    handle, 36, ctypes.byref(caption_text), ctypes.sizeof(caption_text))
                # Nudge the frame to redraw: DWM only repaints the caption on the
                # next non-client paint, so an idle window would keep the old bar.
                form.Invalidate()

            if form.InvokeRequired:
                form.Invoke(Func[Type](apply))
            else:
                apply()
        elif sys.platform == "darwin":
            # Repaint the transparent bar with the new theme's --bg
            apply_mac_chrome(dark)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001 - cosmetic; never take the app down for it
        return {"ok": False, "error": str(e)}


def _adaptive_window_size():
    """Return (width, height, x, y) to fill the usable screen area.

    On macOS we read ``NSScreen.visibleFrame`` so the window fills the entire
    screen minus the menu bar and dock — the same area that the system's
    title-bar "zoom" produces.  On other platforms we target ~92% of the
    screen and center the window.

    Falls back to (1520, 920) on any error so a screen-detection failure
    never blocks the window from opening.
    """
    import sys

    if sys.platform == "darwin":
        try:
            from AppKit import NSScreen
            full = NSScreen.mainScreen().frame()
            visible = NSScreen.mainScreen().visibleFrame()
            w = int(visible.size.width)
            h = int(visible.size.height)
            # Convert from bottom-left origin to pywebview's top-left convention.
            x = int(visible.origin.x - full.origin.x)
            y = int(full.size.height - visible.origin.y - visible.size.height)
            return w, h, x, y
        except Exception:
            pass

    try:
        import tkinter as tk
        root = tk.Tk()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.destroy()
        w = max(1080, int(screen_w * 0.92))
        h = max(680, int(screen_h * 0.92))
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        return w, h, x, y
    except Exception:
        return 1520, 920, None, None


# Identity whose index pipeline was already bootstrapped in this process.
# login_verify re-fires _boot_indexing on every sign-in; this keeps a repeat
# login for the same user from double-running init.
_boot_owner = None


def _boot_indexing():
    """Bootstrap the indexing pipeline for the logged-in user: load the
    content index, create the RAG dataset / KG graph (idempotent), and
    recover tasks left in-flight by a prior crash.

    Fired from reveal() when the window appears, and re-fired by login_verify
    after a mid-session sign-in. Pre-login there is no work repo, so it bails
    quietly and waits for the login re-fire — previously it crashed on
    AuthError here and never ran again, so users who logged in after boot
    never got their dataset/graph created.
    """
    global _boot_owner
    try:
        who = user.current_user()
    except user.AuthError:
        return  # pre-login — login_verify re-fires this once signed in
    if _boot_owner == who.id:
        return  # already bootstrapped for this identity in this process
    from workrepo import local_repo_path
    try:
        repo = local_repo_path()
    except Exception as exc:  # logout race or repo not provisioned yet
        log.info("index boot skipped: %s", exc)
        return
    # First boot races the work-repo clone (triggered by the frontend's
    # first snapshot call). Indexing needs the checkout to exist before
    # docindex can read/write index.jsonl. Waiting for .git alone is not
    # enough: the clone creates .git first and checks the worktree out
    # LAST, and an index.jsonl written mid-clone makes git refuse to
    # checkout ("untracked file would be overwritten") — killing the
    # clone. Wait for clients/ instead: the one directory every valid
    # work repo must have once the checkout has really landed. Bounded
    # so a dead network can't park this thread — 300s matches the
    # slowest plausible first clone (a full repo over a cold link).
    deadline = time.monotonic() + 300
    while not (repo / "clients").is_dir() and time.monotonic() < deadline:
        time.sleep(1)
        # Identity changed while waiting (logout / account switch): the repo
        # path being polled belongs to the previous user — the new login's
        # re-fire takes over with the right path.
        try:
            if user.current_user().id != who.id:
                return
        except user.AuthError:
            return
    if not (repo / "clients").is_dir():
        log.warning("index boot skipped — work repo not ready after 300s")
        return
    # Load (or rebuild) the content index FIRST — the indexing state lives
    # on its records now, so the pipeline must not touch state before the
    # table is in memory. Already in a daemon thread, so it never blocks
    # the window — normal boots just parse an existing text file; only a
    # missing index triggers a full rebuild.
    try:
        import docindex
        docindex.init(Path(repo))
    except Exception as exc:
        log.error("docindex init failed: %s", exc)
    try:
        index.init(repo)
    except Exception as exc:
        log.error("index init failed: %s", exc)
        return
    if who.can_index_kb():
        threading.Thread(target=index.ensure_dataset, daemon=True).start()
        threading.Thread(target=index.sync_with_server, daemon=True).start()
        _boot_owner = who.id
    else:
        # Plans without KB rights never touch the services — no dataset, no
        # boot sync (its adopt/retry passes would submit). _boot_owner stays
        # unset on purpose: the poll/redeem path re-fires this function the
        # moment the account upgrades, and that run must do the real work.
        log.info("index boot: plan %s — dataset/sync skipped", who.plan)


def main():
    global main_window
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--dev", action="store_true",
                        help="load the Vite dev server (hot reload) instead of frontend/dist")
    parser.add_argument("--worker", type=str, metavar="NAME",
                        help="Run a viewer/agent worker (internal subprocess use)")
    args = parser.parse_args()

    # First line of every runtime.log — the version stamp support needs to
    # match a customer report against a release.
    log.info("Mortgage Work %s starting", app_version())

    # Refresh the stored session against /auth/me before anything identity-
    # dependent runs — stale sessions (saved before the services block
    # existed) would otherwise degrade KB calls to the .env localhost
    # fallback. Worker children share the parent's session and never
    # refresh it themselves. Unreachable auth service → silent no-op.
    if not args.worker:
        _refresh_session()
        # Keep the plan honest mid-run: server-side changes (portal edits,
        # redemptions on other machines) land within one poll window.
        threading.Thread(target=_plan_poll_loop, daemon=True).start()

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

    # Fill the usable screen area: on macOS this reads visibleFrame (excludes
    # menu bar + dock) so the window truly fills the screen; on other platforms
    # it targets 92% centered.
    win_w, win_h, win_x, win_y = _adaptive_window_size()

    main_window = webview.create_window(
        "",
        url,
        width=win_w,
        height=win_h,
        x=win_x,
        y=win_y,
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
        # Developer UI surfaces (Runtime panel, conversation inspector) are
        # only visible in dev mode. Frozen/release builds never expose them.
        app_config = {"mode": "dev" if dev_mode else "prod", "dev": dev_mode}
        # The subscription tier shapes what the Knowledge surfaces show;
        # the poller pushes updates mid-run (window.applyPlanUpdate).
        if user.is_logged_in():
            app_config["plan"] = user.current_user().plan
        main_window.evaluate_js(f"window.__APP_CONFIG__ = {json.dumps(app_config)}")
        main_window.evaluate_js(f"window.__SERVICES__ = {json.dumps(services_payload())}")
        main_window.evaluate_js("window.applyAppConfig && window.applyAppConfig(window.__APP_CONFIG__)")
        main_window.show()
        # Bootstrap the indexing pipeline in the background — module-level
        # _boot_indexing() bails quietly when nobody is logged in yet and is
        # re-fired by login_verify after sign-in. All async — none of this
        # should delay the window or block on network.
        threading.Thread(target=_boot_indexing, daemon=True).start()

        # Start the connector gateway if any connectors are configured.
        # Message pull() is now exclusively owned by the IM agent running in
        # agent_service — this process only manages the gateway lifecycle.
        def _boot_connectors():
            try:
                if connector_service.start():
                    log.info("connector service started")
                else:
                    log.info("connector service: no connectors configured")
            except Exception as exc:
                log.error("connector service start failed: %s", exc)

        threading.Thread(target=_boot_connectors, daemon=True).start()

    main_window.events.loaded += reveal
    # Sync-engine state → status bar. Registered before start() so even the
    # first flush finds a listener; js() no-ops until the window exists.
    on_sync_state(lambda state, detail: js(f"setSyncState({state!r}, {detail!r})"))
    # First-run progress → boot overlay. The clone/pull/restore stages each
    # push one line here, so the curtain narrates what the backend is doing
    # instead of showing a frozen screen or an early error.
    def _push_boot(stage, detail):
        log.info("boot progress → %s %s", stage, detail)
        js(f"setBootState({stage!r}, {detail!r})")

    on_boot_progress(_push_boot)
    # Knowledge state → status-bar chip + Knowledge Base panel. Every push
    # carries the summary AND the full row table, so the two surfaces can
    # never disagree.
    def _on_knowledge(summary, rows):
        # The push is the same surface as the bridge methods — plans without
        # KB rights must see the empty picture here too (and a mid-run
        # downgrade scrubs whatever the last push painted).
        if not Api._indexing_visible():
            summary = {"total": 0, "processing": 0, "failed": 0,
                       "pending": 0, "canceled": 0}
            rows = []
        js(f"setKnowledgeState({json.dumps(summary)})")
        js(f"setKnowledgeRows({json.dumps(rows)})")

    index.on_indexing_state(_on_knowledge)

    # Batch-start announcement → long-lived toast with a progress link. The
    # indexer only fires batches on plans with KB rights (trigger/retry gate
    # on can_index_kb), but a user-visible surface never trusts its caller —
    # re-check visibility before anything reaches a screen.
    def _on_announce(count):
        if not Api._indexing_visible():
            return
        js(f"announceIndexing({int(count)})")

    index.on_batch_announce(_on_announce)
    # A save inside the debounce window would otherwise die with the process —
    # flush on the way out so closing the window never loses the last edit.
    # force_push: shutdown must not defer — there is no "next interval" after exit.
    atexit.register(lambda: flush_sync(force_push=True))
    # Spin up the local agent service before the window so chat is ready by
    # the time the user opens the panel.
    start_services()

    # Ctrl+C must reach Python's handler even while the main thread is inside
    # webview's native run loop (where KeyboardInterrupt stays pending). The
    # default SIGINT disposition reraises on the main thread, which never fires
    # if it's blocked in a C call. Installing an explicit handler that calls
    # stop_services() + sys.exit() guarantees the child processes (including
    # clerk inside agent_service) are reaped on every exit path.
    def _on_signal(signum, frame):
        stop_services()
        connector_service.stop()
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
    # Confirm which WinForms backend actually ran (patched hooks copy vs the
    # stock site-packages module) so a loader regression is visible in logs.
    _backend = sys.modules.get('webview.platforms.winforms')
    if _backend is not None:
        log.info("webview backend loaded from %s",
                 getattr(_backend, '__file__', 'unknown'))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback as _tb
        _tb.print_exc()
        if getattr(sys, 'frozen', False):
            input("\nApp crashed. Press Enter to exit...")
