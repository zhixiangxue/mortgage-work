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
import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import traceback

APP_NAME = "Mortgage Work"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
from config import SERVICES  # noqa: E402
from model_settings import (SettingsError, check_provider,  # noqa: E402
                           read_models, remove_model, remove_provider,
                           reveal_models_file, save_provider)
from workrepo import (RepoError, add_files, copy_path, create_client,  # noqa: E402
                      create_file, create_folder, delete_client, delete_path,
                      duplicate_path, file_history, file_status, flush_sync,
                      forget_reachability, move_path, on_sync_state,
                      queue_external, read_file, rename_path, restore_version,
                      reveal_path, start_watch, upload_files,
                      workspace_snapshot, write_file, write_session)

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
        print(f"[watch] snapshot failed: {exc}")
        return
    # ensure_ascii keeps this a plain ASCII JS literal — no escaping surprises
    payload = json.dumps(snap)
    # Some churn is invisible to the UI (git bookkeeping, a rewrite with
    # identical bytes). Same payload = nothing to repaint; stay quiet.
    if payload == _last_snapshot:
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
        print(f"[api] {fn.__name__}: {exc}")
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return {"error": f"{fn.__name__} failed: {exc}"}


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
            print(f"[api] workspace_snapshot ok · {len(snap['clients'])} clients")
            # The checkout exists now (it may have just been cloned), so this
            # is the earliest point a watcher can attach. Idempotent.
            start_watch(push_snapshot)
            return _remember(snap)
        except RepoError as exc:
            print(f"[api] workspace_snapshot RepoError: {exc}")
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — never leave the UI hanging on mocks silently
            traceback.print_exc()
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
            flush_sync()
            print("[api] sync_workspace "
                  f"{'offline — local copy' if snap.get('offline') else 'ok'}")
            return _remember(snap)
        except RepoError as exc:
            print(f"[api] sync_workspace RepoError: {exc}")
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return {"error": f"sync failed: {exc}"}

    def read_file(self, scope, relpath):
        # Same errors-as-data contract as workspace_snapshot
        try:
            return read_file(scope, relpath)
        except RepoError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not read {relpath}: {exc}"}

    def write_file(self, scope, relpath, content):
        try:
            return write_file(scope, relpath, content)
        except RepoError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not save {relpath}: {exc}"}

    def save_session(self, state):
        # UI session (tabs, focused client, chat) — restored on next launch.
        # Best-effort by design: losing it costs a few clicks, not work.
        try:
            return write_session(state)
        except RepoError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not save session: {exc}"}

    def sync_now(self):
        # Status-bar click: the manual retry for "we booted offline". Does the
        # whole round — re-probe the remote, pull, commit whatever is pending
        # (incl. unpushed commits from an offline stretch), push — because that
        # is what a user means when they press a sync button.
        try:
            forget_reachability()   # a stale "no network" must not answer a click
            snap = workspace_snapshot(pull=True)
            queue_external()
            flush_sync()
            return _remember(snap)
        except RepoError as exc:
            print(f"[api] sync_now RepoError: {exc}")
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return {"error": f"sync failed: {exc}"}

    def file_status(self):
        # Source-control colors for the tree, refreshed without a full rescan.
        # Colors are decoration: on failure return nothing rather than an
        # error the UI would have to explain.
        try:
            return file_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[api] file_status failed: {exc}")
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

    def file_history(self, scope, relpath):
        return _guard(file_history, scope, relpath)

    def restore_version(self, scope, relpath, sha):
        return _guard(restore_version, scope, relpath, sha)

    def create_client(self, data):
        # New Client modal → clients/<slug>/ with client.yaml + PROFILE.md
        return _guard(create_client, data)

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


def start_viewers():
    """Spawn the local data-browser servers with the current venv's Python, so
    the clients (zig/chak/fastapi) resolve. Each reads its own connection from
    config.py; failures are logged, not fatal — the app still runs without them.

    Script names carry a _viewer suffix to avoid shadowing same-name PyPI
    packages (e.g. the pip falkordb package that zig depends on)."""
    browser_dir = os.path.join(BASE_DIR, "browser")
    viewers = [
        ("falkordb", "falkordb_viewer.py"),
        ("rqlite", "rqlite_viewer.py"),
        ("qdrant", "qdrant_viewer.py"),
        ("redis", "redis_viewer.py"),
    ]
    for name, script_name in viewers:
        script = os.path.join(browser_dir, script_name)
        try:
            _viewer_procs.append(subprocess.Popen([sys.executable, script], cwd=BASE_DIR))
            print(f"[viewer] started {name} → {SERVICES.viewer_url(name)}")
        except Exception as exc:  # noqa: BLE001 — a viewer that won't start shouldn't kill the app
            print(f"[viewer] failed to start {name}: {exc}")
    # The chat agent service lives at the repo root (it's an app service, not a
    # data browser) but is spawned and reaped exactly like the viewers.
    try:
        script = os.path.join(BASE_DIR, "agent_service.py")
        _viewer_procs.append(subprocess.Popen([sys.executable, script], cwd=BASE_DIR))
        print(f"[agent] started → {SERVICES.agent_ws_url()}")
    except Exception as exc:  # noqa: BLE001 — chat degrades, the app still runs
        print(f"[agent] failed to start: {exc}")
    atexit.register(stop_viewers)


def stop_viewers():
    for p in _viewer_procs:
        if p.poll() is None:
            p.terminate()
    _viewer_procs.clear()


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
            print(f"[js] dropped ({exc}): {script[:60]}")


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
    args = parser.parse_args()

    set_app_branding()
    # On macOS the Dock icon is applied post-start inside force_dark_chrome_macos:
    # pywebview resets the app icon during start(), so setting it here wouldn't
    # stick. set_dock_icon() is a no-op on other platforms anyway.
    set_taskbar_identity()
    # Dev: point at the Vite dev server (--dev + `npm run dev` in frontend/).
    # Prod: load the built bundle; pywebview's local HTTP server avoids the
    # file:// + ES module CORS restriction under Windows WebView2.
    # LO_DEV=1 still works for muscle memory / CI.
    if args.dev or os.environ.get("LO_DEV"):
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
        main_window.evaluate_js(f"window.__SERVICES__ = {json.dumps(services_payload())}")
        main_window.show()

    main_window.events.loaded += reveal
    # Sync-engine state → status bar. Registered before start() so even the
    # first flush finds a listener; js() no-ops until the window exists.
    on_sync_state(lambda state, detail: js(f"setSyncState({state!r}, {detail!r})"))
    # A save inside the debounce window would otherwise die with the process —
    # flush on the way out so closing the window never loses the last edit.
    atexit.register(flush_sync)
    # Spin up the data-browser servers (falkordb / rqlite) before the window so
    # they're ready by the time a user clicks into the runtime services.
    start_viewers()
    # Menus are parked for now — add menu=MENU back when the app grows into them
    webview.start(force_dark_chrome, main_window, debug=False,
                  http_server=True, icon=windows_icon())


if __name__ == "__main__":
    main()
