"""PyInstaller runtime hook — force .NET Core CLR loader on Windows.

In pywebview ≥6 the "winforms" module is the only Windows backend, and it
internally detects EdgeChromium (WebView2) automatically.  The real danger
is pythonnet defaulting to the netfx (.NET Framework) loader, which cannot
resolve symbols from the bundled Python.Runtime.dll when .NET Core / .NET 5+
is the only runtime available (the default on Windows 11).

Setting PYTHONNET_RUNTIME=coreclr forces pythonnet to use the modern
hostfxr-based loader that ships with every supported Windows release.
app.py also sets this before importing webview as belt-and-suspenders.
"""
import os
import sys

if sys.platform == 'win32':
    os.environ['PYTHONNET_RUNTIME'] = 'coreclr'
    # Point pythonnet at a runtimeconfig.json that includes
    # Microsoft.WindowsDesktop.App (WinForms).  By default get_coreclr()
    # generates a config with only Microsoft.NETCore.App, which lacks
    # System.Windows.Forms — and pywebview's winforms backend needs it.
    _cfg = os.path.join(sys._MEIPASS, 'pythonnet.runtimeconfig.json')
    if os.path.isfile(_cfg):
        os.environ['PYTHONNET_CORECLR_RUNTIME_CONFIG'] = _cfg

    # In .NET Core, some assemblies that were part of System.dll in .NET
    # Framework are now separate DLLs.  pywebview's winforms.py imports
    # types from these assemblies but does not explicitly AddReference
    # them (they were auto-loaded in .NET Framework).  We pre-load clr
    # and add the missing references here before winforms.py runs.
    import clr
    clr.AddReference('Microsoft.Win32.SystemEvents')

    # ── pywebview OpenFolderDialog .NET 8 compatibility ────────────────
    # pywebview's winforms.py uses a .NET reflection hack
    # (FileDialogNative+IFileDialog) that crashes under .NET 8 because
    # the internal COM wrapper type was removed.  PyInstaller bundles the
    # original winforms.py into its PYZ archive, which always takes
    # precedence over filesystem imports.  We work around this by
    # inserting a meta_path finder that loads our patched winforms.py
    # from the _internal directory *before* the FrozenImporter runs.
    from importlib.abc import MetaPathFinder, Loader
    from importlib.machinery import ModuleSpec

    _PATCHED_WINFORMS = os.path.join(
        sys._MEIPASS, 'webview', 'platforms', 'winforms.py'
    )

    class _WinformsPatcher(MetaPathFinder, Loader):
        def find_spec(self, fullname, path, target=None):
            if fullname != 'webview.platforms.winforms':
                return None
            if not os.path.isfile(_PATCHED_WINFORMS):
                return None
            return ModuleSpec(fullname, self, origin=_PATCHED_WINFORMS)

        def create_module(self, spec):
            return None  # use default module creation

        def exec_module(self, module):
            with open(_PATCHED_WINFORMS, 'r', encoding='utf-8') as f:
                source = f.read()
            code = compile(source, _PATCHED_WINFORMS, 'exec')
            exec(code, module.__dict__)

    sys.meta_path.insert(0, _WinformsPatcher())
