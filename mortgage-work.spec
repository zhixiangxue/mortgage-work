# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Mortgage Work.

Standard onedir build — the same structure pyi-makespec generates.
No noarchive tricks, no removed PYZ.  This is what millions of
PyInstaller users run every day.
"""
import os as _os
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs

# ── Editable-install path fix ────────────────────────────────────────────
# chak and seeka are installed via pip -e in local dev. Their __path_hook__
# finders confuse PyInstaller's module collection. Add their real source
# directories to pathex so PyInstaller finds them as regular packages.
# On CI (uv sync --no-editable) these packages live in site-packages and
# don't need this — the isdir guard skips the wrong __file__ path.
_editable_parents = []
for __pkg_name in ('chak', 'seeka'):
    try:
        __pkg = __import__(__pkg_name)
        __pkg_dir = _os.path.dirname(__pkg.__file__)
        __pkg_parent = _os.path.dirname(__pkg_dir)
        # Only add if the parent actually contains the package directory
        # (editable install), not a site-packages noise path.
        if _os.path.isdir(_os.path.join(__pkg_parent, __pkg_name)):
            _editable_parents.append(__pkg_parent)
    except Exception:
        pass

block_cipher = None

# ── Data files ───────────────────────────────────────────────────────────

_datas = [
    ('frontend/dist', 'frontend/dist'),
    ('assets/icon.png', 'assets'),
    ('assets/icon.ico', 'assets'),
    ('assets/icon.icns', 'assets'),
    ('assets/icon.svg', 'assets'),
    ('browser/falkordb.html', 'browser'),
    ('browser/rqlite.html', 'browser'),
    ('browser/qdrant.html', 'browser'),
    ('browser/redis.html', 'browser'),
    ('browser/conv_viewer.html', 'browser'),
    ('browser/model_prices.json', 'browser'),
    ('browser/falkordb_viewer.py', 'browser'),
    ('browser/rqlite_viewer.py', 'browser'),
    ('browser/qdrant_viewer.py', 'browser'),
    ('browser/redis_viewer.py', 'browser'),
    ('agent_service.py', '.'),
    ('pythonnet.runtimeconfig.json', '.'),
    # Patched winforms.py for .NET 8 OpenFolderDialog compatibility.
    # Loaded at runtime via sys.meta_path before FrozenImporter.
    ('hooks/webview/platforms/winforms.py', 'webview/platforms'),
    # Infrastructure config (remote service URLs, API keys).
    # Included only when building locally with a real .env present.
    # On CI without DOTENV_CONTENTS secret the app falls back to
    # localhost defaults; users drop their own .env into _internal/.
    # .env.example is always shipped as documentation.
    ('.env.example', '.'),
]

# Conditionally bundle the real .env when building locally.
# On CI without the DOTENV_CONTENTS secret, skip it — the app
# falls back to localhost defaults and the user provides their
# own .env post-download.
if _os.path.isfile('.env'):
    _datas.append(('.env', '.'))

# ── Hidden imports ───────────────────────────────────────────────────────

_hiddenimports = [
    'webview',
    'webview.platforms.edgechromium',
    'webview.platforms.winforms',
    'webview.platforms.cocoa',
    'webview.platforms.gtk',
    'webview.js.api',
    'webview.menu',
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'chak',
    'chakpy',
    'zig',
    'fylepy',
    'seeka',
    'pydantic',
    'pydantic.deprecated.decorator',
    'pydantic.v1',
    'PIL',
    'PIL.Image',
    'yaml',
    'dotenv',
    'pypdfium2',
    'pypdfium2._pypdfium',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'rich',
    'rich.table',
    'rich.console',
    'rich.logging',
    'watchdog',
    'watchdog.observers',
    'xxhash',
    'openai',
    'redis',
    'redis.asyncio',
    'markdown_it',
    'httpx',
    'fastapi',
    'fastapi.responses',
    'starlette',
    'websockets',
    # ── Project modules only imported by agent_service.py (runpy) ──
    'agents',
    'agents.clerk',
    'agents.mem',
    'docindex',
]

if sys.platform == 'win32':
    _hiddenimports += [
        'clr',
        'System',
        'System.Windows.Forms',
        'System.Drawing',
    ]
elif sys.platform == 'darwin':
    _hiddenimports += [
        'Foundation',
        'AppKit',
        'WebKit',
        'PyObjCTools',
        'pyobjc_core',
    ]

# ── Excludes ─────────────────────────────────────────────────────────────

_excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
    'scipy',
    'pandas',
    'IPython',
    'jupyter',
    'notebook',
    'pytest',
    'setuptools',
    'pip',
]

# ═══════════════════════════════════════════════════════════════════════════
# Standard PyInstaller pipeline — exactly what pyi-makespec produces
# ═══════════════════════════════════════════════════════════════════════════

a = Analysis(
    ['app.py'],
    pathex=['.'] + _editable_parents,
    binaries=collect_dynamic_libs('pythonnet') if sys.platform == 'win32' else [],
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['_pyi_runtime_edge.py'],
    excludes=_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Mortgage Work',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.icns' if sys.platform == 'darwin' else 'assets/icon.ico'][0],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='Mortgage Work',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Mortgage Work.app',
        icon='assets/icon.icns',
        bundle_identifier='com.mortgagework.app',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSHighResolutionCapable': True,
            'CFBundleName': 'Mortgage Work',
            'CFBundleDisplayName': 'Mortgage Work',
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '0.1.0',
            'NSRequiresAquaSystemAppearance': False,
        },
    )
