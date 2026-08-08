# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Mortgage Work.

Standard onedir build — the same structure pyi-makespec generates.
No noarchive tricks, no removed PYZ.  This is what millions of
PyInstaller users run every day.
"""
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs

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
]

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
    'websockets',
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
    pathex=['.'],
    binaries=collect_dynamic_libs('pythonnet') if sys.platform == 'win32' else [],
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
