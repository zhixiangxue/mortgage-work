"""PyInstaller runtime hook — thin forwarder to webview_bootstrap.

Runs before the main script so the frozen exe configures pythonnet and the
patched WinForms backend before anything imports ``webview``.  The dev entry
point (app.py) calls the same bootstrap, so dev and frozen builds share one
loader strategy; the rationale lives in webview_bootstrap.py.
"""
import os
import sys

if sys.platform == 'win32':
    try:
        from webview_bootstrap import bootstrap_windows_webview
        bootstrap_windows_webview(sys._MEIPASS, frozen=True)
    except Exception:
        # Minimal fallback if the bundled bootstrap module is unreachable:
        # the same env configuration plus the same patched-backend finder,
        # kept in lockstep with webview_bootstrap.py.
        os.environ.setdefault('PYTHONNET_RUNTIME', 'coreclr')
        _cfg = os.path.join(sys._MEIPASS, 'pythonnet.runtimeconfig.json')
        if os.path.isfile(_cfg):
            os.environ.setdefault('PYTHONNET_CORECLR_RUNTIME_CONFIG', _cfg)
        try:
            import clr
            clr.AddReference('Microsoft.Win32.SystemEvents')
        except Exception:
            pass
        _patched = os.path.join(sys._MEIPASS, 'webview', 'platforms', 'winforms.py')
        if os.path.isfile(_patched):
            from importlib.abc import Loader, MetaPathFinder
            from importlib.machinery import ModuleSpec

            class _WinformsPatcher(MetaPathFinder, Loader):
                def find_spec(self, fullname, path, target=None):
                    if fullname != 'webview.platforms.winforms':
                        return None
                    return ModuleSpec(fullname, self, origin=_patched)

                def create_module(self, spec):
                    return None  # use default module creation

                def exec_module(self, module):
                    module.__file__ = _patched
                    with open(_patched, 'r', encoding='utf-8') as f:
                        source = f.read()
                    exec(compile(source, _patched, 'exec'), module.__dict__)

            sys.meta_path.insert(0, _WinformsPatcher())
