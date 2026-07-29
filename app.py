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
import subprocess
import sys

import webview
import webview.menu as wm

# Centralized service config (URIs + local viewer ports, all from .env)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SERVICES  # noqa: E402
from workrepo import RepoError, read_file, workspace_snapshot, write_file  # noqa: E402

# Drop pywebview's default Edit/View menus; we bring our own
webview.settings['SHOW_DEFAULT_MENUS'] = False

APP_NAME = "Mortgage Work"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def set_app_branding():
    # macOS shows CFBundleName in the menu bar AND as the Dock hover label; from
    # the bare interpreter that key is "Python"/"python3". Patch the in-memory
    # bundle info BEFORE the menu bar / Dock registration (too late once the app
    # is running). Patch BOTH dictionaries: the Dock reads the base
    # infoDictionary, so patching only the localized one (as before) fixed the
    # menu bar but left the Dock tooltip as "python3".
    if sys.platform != "darwin":
        return

    from Foundation import NSBundle, NSProcessInfo

    bundle = NSBundle.mainBundle()
    for info in (bundle.localizedInfoDictionary(), bundle.infoDictionary()):
        if info is not None:
            info["CFBundleName"] = APP_NAME
            info["CFBundleDisplayName"] = APP_NAME

    # CFBundleName drives the menu bar, but the Dock hover label follows the
    # process name — which defaults to the executable ("python3") for an
    # un-bundled interpreter. Set it explicitly so the Dock shows the app name.
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


def services_payload():
    """URLs the frontend iframes point at — all three are our local viewer
    servers. Ports/hosts come from config.py so this stays in lockstep with
    the spawned servers."""
    return {
        "falkordb": SERVICES.viewer_url("falkordb"),
        "rqlite": SERVICES.viewer_url("rqlite"),
        "qdrant": SERVICES.viewer_url("qdrant"),
        "redis": SERVICES.viewer_url("redis"),
    }


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
            return snap
        except RepoError as exc:
            print(f"[api] workspace_snapshot RepoError: {exc}")
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — never leave the UI hanging on mocks silently
            import traceback
            traceback.print_exc()
            return {"error": f"workspace scan failed: {exc}"}

    def sync_workspace(self):
        # Background pull + rescan; the frontend rehydrates quietly on success
        try:
            snap = workspace_snapshot(pull=True)
            print("[api] sync_workspace ok")
            return snap
        except RepoError as exc:
            print(f"[api] sync_workspace RepoError: {exc}")
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            import traceback
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
    atexit.register(stop_viewers)


def stop_viewers():
    for p in _viewer_procs:
        if p.poll() is None:
            p.terminate()
    _viewer_procs.clear()


def js(script):
    if main_window:
        main_window.evaluate_js(script)


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
    # Spin up the data-browser servers (falkordb / rqlite) before the window so
    # they're ready by the time a user clicks into the runtime services.
    start_viewers()
    # Menus are parked for now — add menu=MENU back when the app grows into them
    webview.start(force_dark_chrome, main_window, debug=False,
                  http_server=True, icon=windows_icon())


if __name__ == "__main__":
    main()
