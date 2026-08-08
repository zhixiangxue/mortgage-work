# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Mortgage Work — cross-platform desktop app bundle.

Usage (after frontend is built to frontend/dist/):
    uv run pyinstaller mortgage-work.spec

Output:
    macOS:   dist/Mortgage Work.app
    Windows: dist/Mortgage Work/  (onedir, zip this folder for distribution)
"""
import sys
from pathlib import Path

block_cipher = None

# ── Data files that must ship alongside the frozen executable ───────────
# Each tuple is (source_path_on_disk, destination_dir_in_bundle).
# Paths are relative to the project root (where this .spec lives).

_datas: list[tuple[str, str]] = [
    # Frontend — MUST be built (npm run build) before running PyInstaller
    ('frontend/dist', 'frontend/dist'),
    # App icons (all platforms)
    ('assets/icon.png', 'assets'),
    ('assets/icon.ico', 'assets'),
    ('assets/icon.icns', 'assets'),
    ('assets/icon.svg', 'assets'),
    # Browser viewer HTML pages (served by the viewer FastAPI servers)
    ('browser/falkordb.html', 'browser'),
    ('browser/rqlite.html', 'browser'),
    ('browser/qdrant.html', 'browser'),
    ('browser/redis.html', 'browser'),
    ('browser/conv_viewer.html', 'browser'),
    # Pricing data for the conversation inspector
    ('browser/model_prices.json', 'browser'),
    # Subprocess entry-point scripts — app.py spawns these via Popen,
    # so they need to exist on disk at the expected relative paths.
    ('browser/falkordb_viewer.py', 'browser'),
    ('browser/rqlite_viewer.py', 'browser'),
    ('browser/qdrant_viewer.py', 'browser'),
    ('browser/redis_viewer.py', 'browser'),
    ('agent_service.py', '.'),
]

# ── Hidden imports PyInstaller may fail to discover ─────────────────────
# Many of these come from dynamic imports (e.g. pywebview loads a platform
# module at runtime), namespace packages, or lazy-loaded submodules.

_hiddenimports = [
    # pywebview — picks the platform backend at runtime
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.cocoa',
    'webview.platforms.gtk',
    'webview.js.api',
    'webview.menu',
    # FastAPI / uvicorn — auto-detected protocol/loop modules
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    # chak ecosystem (local packages resolved via [tool.uv.sources])
    'chak',
    'chakpy',
    'zig',
    'fylepy',
    'seeka',
    # Pydantic v2 (Cython-compiled core)
    'pydantic',
    'pydantic.deprecated.decorator',
    'pydantic.v1',
    # Common packages with lazy / conditional imports
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
    'websockets',
    'json',
]

# Platform-specific hidden imports
if sys.platform == 'win32':
    _hiddenimports += [
        'clr',                          # pythonnet loader
        'System',                       # .NET System namespace
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

# ── Exclude heavyweight packages we never import ────────────────────────
# Shrinks the bundle and speeds up the Analysis pass.

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
# Analysis — discovers every import reachable from app.py
# ═══════════════════════════════════════════════════════════════════════════

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ═══════════════════════════════════════════════════════════════════════════
# PYZ — compress pure-Python modules into a single archive
# ═══════════════════════════════════════════════════════════════════════════

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ═══════════════════════════════════════════════════════════════════════════
# EXE — the frozen executable (GUI mode, no terminal window)
# ═══════════════════════════════════════════════════════════════════════════

exe_kwargs = dict(
    pyz=pyz,
    name='Mortgage Work',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,                      # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == 'darwin':
    exe_kwargs['icon'] = 'assets/icon.icns'
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_kwargs)
else:
    exe_kwargs['icon'] = 'assets/icon.ico'
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_kwargs)

# ═══════════════════════════════════════════════════════════════════════════
# COLLECT — gather binaries + data into the distribution directory
# ═══════════════════════════════════════════════════════════════════════════

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Mortgage Work',
)

# ═══════════════════════════════════════════════════════════════════════════
# BUNDLE — macOS .app wrapper (only on Darwin)
# ═══════════════════════════════════════════════════════════════════════════

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
