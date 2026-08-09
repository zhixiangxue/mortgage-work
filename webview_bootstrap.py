"""Windows WebView2 / pythonnet bootstrap — the single source of truth.

Both entry points (dev ``uv run python app.py`` and the PyInstaller runtime
hook ``_pyi_runtime_edge.py``) call :func:`bootstrap_windows_webview` *before*
``import webview``, so dev and frozen builds share one loader strategy:

* ``PYTHONNET_RUNTIME=coreclr`` — pythonnet must use the modern hostfxr
  loader; the netfx loader cannot resolve the WebView2 WinForms assemblies
  on current Windows releases.
* ``PYTHONNET_CORECLR_RUNTIME_CONFIG`` — points pythonnet at a runtimeconfig
  that includes ``Microsoft.WindowsDesktop.App`` (WinForms); the config
  pythonnet generates by default only carries ``Microsoft.NETCore.App``.
* ``Microsoft.Win32.SystemEvents`` — a separate DLL under .NET Core that
  pythonnet's assembly resolver does not always pick up automatically.
* patched ``webview.platforms.winforms`` — the stock pywebview module uses a
  .NET-internal type (``FileDialogNative+IFileDialog``) that .NET 8 removed;
  the project copy in ``hooks/`` falls back to ``FolderBrowserDialog``.

The function is idempotent and a no-op on non-Windows platforms.  Logging is
not configured yet when this runs (it must precede ``import webview``), so
diagnostics are returned as a dict and logged by the caller once
``setup_logging()`` has run.
"""
from __future__ import annotations

import os
import sys

_BOOTSTRAPPED = False
_INFO: dict = {
    "platform": sys.platform,
    "pythonnet_runtime": None,
    "runtime_config": None,
    "patched_winforms": None,
}


def _install_patched_winforms_finder(patched_winforms: str) -> None:
    """Serve ``webview.platforms.winforms`` from the project copy.

    Inserted at ``sys.meta_path[0]`` so it wins over both the regular
    site-packages finder (dev) and PyInstaller's FrozenImporter (frozen).
    """
    from importlib.abc import Loader, MetaPathFinder
    from importlib.machinery import ModuleSpec

    class _PatchedWinformsFinder(MetaPathFinder, Loader):
        def find_spec(self, fullname, path, target=None):
            if fullname == "webview.platforms.winforms":
                return ModuleSpec(fullname, self, origin=patched_winforms)
            return None

        def create_module(self, spec):
            return None  # default module creation

        def exec_module(self, module):
            module.__file__ = patched_winforms
            with open(patched_winforms, "r", encoding="utf-8") as f:
                source = f.read()
            exec(compile(source, patched_winforms, "exec"), module.__dict__)

    sys.meta_path.insert(0, _PatchedWinformsFinder())


def bootstrap_windows_webview(base_dir: str, frozen: bool = False) -> dict:
    """Configure pythonnet/WebView2 on Windows before ``import webview``.

    ``base_dir`` is the project root in dev and ``sys._MEIPASS`` when frozen;
    the patched backend is looked up in both the dev layout
    (``hooks/webview/platforms/winforms.py``) and the frozen layout
    (``webview/platforms/winforms.py``, per the spec's datas mapping).
    Returns the diagnostics dict (also available as module state).
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED or sys.platform != "win32":
        return _INFO
    _BOOTSTRAPPED = True
    _INFO["frozen"] = frozen

    os.environ.setdefault("PYTHONNET_RUNTIME", "coreclr")
    _INFO["pythonnet_runtime"] = os.environ["PYTHONNET_RUNTIME"]

    runtime_config = os.path.join(base_dir, "pythonnet.runtimeconfig.json")
    if os.path.isfile(runtime_config):
        os.environ.setdefault("PYTHONNET_CORECLR_RUNTIME_CONFIG", runtime_config)
    _INFO["runtime_config"] = os.environ.get("PYTHONNET_CORECLR_RUNTIME_CONFIG")

    try:
        import clr  # noqa: E402

        clr.AddReference("Microsoft.Win32.SystemEvents")
    except Exception:
        # Let pywebview surface the real startup exception with its context.
        pass

    for candidate in (
        os.path.join(base_dir, "hooks", "webview", "platforms", "winforms.py"),
        os.path.join(base_dir, "webview", "platforms", "winforms.py"),
    ):
        if os.path.isfile(candidate):
            _install_patched_winforms_finder(candidate)
            _INFO["patched_winforms"] = candidate
            break

    return _INFO
