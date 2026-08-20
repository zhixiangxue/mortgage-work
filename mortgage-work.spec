# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Mortgage Work.

Standard onedir build — the same structure pyi-makespec generates.
No noarchive tricks, no removed PYZ.  This is what millions of
PyInstaller users run every day.
"""
import os as _os
import sys
import tomllib
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

# Version lives in pyproject.toml — the single source of truth. Stamping it
# into Info.plist here keeps Finder's "Get Info" and support diagnostics in
# sync with the release tag without a second place to edit. SPECPATH is the
# spec's directory, injected by PyInstaller.
with open(_os.path.join(SPECPATH, 'pyproject.toml'), 'rb') as _f:  # noqa: F821
    _app_version = tomllib.load(_f)['project']['version']

# Windows has no Info.plist: ship a VERSION file the frozen app reads at
# runtime (config.app_version), so the startup line in runtime.log carries
# a real stamp like the macOS bundle does.
_version_staging = _os.path.join('build', 'version-staging')
_os.makedirs(_version_staging, exist_ok=True)
with open(_os.path.join(_version_staging, 'VERSION'), 'w',
          encoding='utf-8', newline='') as _f:
    _f.write(_app_version + '\n')

# Win32 version resource — stamps the exe's Properties → Details tab,
# Task Manager and Settings → Installed apps. Generated from the same
# pyproject.toml version, no second place to edit.
_version_info = None
if sys.platform == 'win32':
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable,
        VarFileInfo, VarStruct, VSVersionInfo,
    )
    _vparts = (_app_version.split('.') + ['0', '0', '0', '0'])[:4]
    _vnums = tuple(int(''.join(ch for ch in p if ch.isdigit()) or 0)
                   for p in _vparts)
    _version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_vnums, prodvers=_vnums,
            mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1,
            subtype=0x0, date=(0, 0),
        ),
        kids=[
            StringFileInfo([StringTable('040904B0', [
                StringStruct('CompanyName', 'Mortgage Work'),
                StringStruct('FileDescription', 'Mortgage Work'),
                StringStruct('FileVersion', _app_version),
                StringStruct('InternalName', 'MortgageWork'),
                StringStruct('LegalCopyright', 'Mortgage Work'),
                StringStruct('OriginalFilename', 'Mortgage Work.exe'),
                StringStruct('ProductName', 'Mortgage Work'),
                StringStruct('ProductVersion', _app_version),
            ])]),
            VarFileInfo([VarStruct('Translation', [1033, 1200])]),
        ],
    )

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
    # Model pricing table consumed by app.py's Settings → Models panel.
    ('model_prices.json', '.'),
    # NOTE: browser/ (the data viewers) is a standalone dev/debug unit with
    # its own pyproject/.env — nothing from it is bundled, so a release
    # ships neither its code nor its credentials.
    ('agent_service.py', '.'),
    ('pythonnet.runtimeconfig.json', '.'),
    # Patched winforms.py for .NET 8 OpenFolderDialog compatibility.
    # Loaded at runtime via sys.meta_path before FrozenImporter.
    ('hooks/webview/platforms/winforms.py', 'webview/platforms'),
    # Runtime config template (non-secret). Infrastructure credentials do
    # not ship in the release — they arrive with the login session (see
    # _services_block in server/main.py, resolved by runtime_services.py).
    ('.env.example', '.'),
    # Version stamp readable at runtime (config.app_version).
    (_os.path.join(_version_staging, 'VERSION'), '.'),
]

# pymupdf-layout ships ONNX models + yaml configs as package data files
# (pymupdf/layout/resources/onnx/*). PyInstaller only collects .py
# modules by default, so without these the layout engine dies at
# runtime with "No such file or directory: .../layout/resources/...".
_datas += collect_data_files('pymupdf', include_py_files=False)

# Conditionally bundle a runtime-only .env.
#
# The root .env may carry dev overrides a release must not ship, and
# infrastructure credentials no longer live in .env at all — they arrive
# with the login session. So instead of shipping the raw file, copy only
# the whitelisted non-secret keys every release actually needs. On CI the
# MW_ENV secret should contain exactly these keys (AUTH_SERVICE_URL at
# minimum); without it the app falls back to localhost defaults.
_RUNTIME_KEYS = {'AUTH_SERVICE_URL', 'AGENT_PORT'}

if _os.path.isfile('.env'):
    _staging = _os.path.join('build', 'env-staging')
    _os.makedirs(_staging, exist_ok=True)
    with open('.env', 'r', encoding='utf-8') as _f:
        _lines = _f.readlines()
    _out = [_line for _line in _lines
            if any(_line.strip().startswith(_k + '=') for _k in _RUNTIME_KEYS)]
    with open(_os.path.join(_staging, '.env'), 'w',
              encoding='utf-8', newline='') as _f:
        _f.writelines(_out)
    _datas.append((_os.path.join(_staging, '.env'), '.'))

# Bundled MinGit (Windows): scripts/bootstrap_mingit.ps1 fetches vendor/mingit/
# before the build so a fresh box needs zero installs. Absent on macOS and CI
# machines that skipped the bootstrap — those keep the system-git fallback.
if _os.path.isdir(_os.path.join('vendor', 'mingit')):
    _datas.append(('vendor/mingit', 'vendor/mingit'))

# ── Hidden imports ───────────────────────────────────────────────────────

_hiddenimports = [
    'webview',
    'webview.js.api',
    'webview.menu',
    # Windows WebView2/pythonnet bootstrap shared by dev and frozen entry points.
    'webview_bootstrap',
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
    # fyle's PDF reader lazy-imports this inside _require_pdf_libs(),
    # invisible to static analysis — without it every PDF tool call dies
    # with "pymupdf4llm is required".
    'pymupdf4llm',
    'pymupdf4llm.helpers.pymupdf_rag',
    'pymupdf4llm.helpers.document_layout',
    # Same lazy-import story in fyle's DOCX/HTML readers.
    'mammoth',
    'markdownify',
    # chak's Pdf tool lazy-imports markdown inside _md_to_html(); the
    # extension names ("tables"/"fenced_code"/"nl2br") resolve via
    # importlib at runtime — doubly invisible to static analysis.
    'markdown',
    'markdown.extensions.tables',
    'markdown.extensions.fenced_code',
    'markdown.extensions.nl2br',
    # Same lazy-import story for PDF form filling (fill/schema workflow).
    'PyPDFForm',
    # chak's Web tool lazy-imports all three inside fetch_page's fallback
    # chain: firecrawl (Layer 1), readability (Layer 3), and bs4 inside
    # _parse_html. Without these the session-delivered keys buy nothing —
    # every fetch silently degrades a layer.
    'firecrawl',
    'readability',
    'bs4',
    'tabulate',
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
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr',
        'System',
        'System.Windows.Forms',
        'System.Drawing',
    ]
elif sys.platform == 'darwin':
    _hiddenimports += [
        'webview.platforms.cocoa',
        'Foundation',
        'AppKit',
        'WebKit',
        'PyObjCTools',
        'pyobjc_core',
    ]

# ── Excludes ─────────────────────────────────────────────────────────────

# NOTE: numpy must stay OUT of this list. pymupdf4llm (bundled via
# hiddenimports above) does `import numpy` at the top level of
# helpers/utils.py; excluding it makes `import pymupdf4llm` raise
# ImportError, which fyle surfaces as "pymupdf4llm is required".
_excludes = [
    'tkinter',
    'matplotlib',
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
    # Windowed (GUI) build: no console window on launch. In this mode the
    # bootloader leaves sys.stdout/stderr as None — _pyi_runtime_edge.py
    # reattaches real handles when the parent redirected them (worker
    # subprocess) and falls back to devnull. Logs reach runtime.log via
    # log.py's file handler regardless.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_version_info,
    icon=['assets/icon.icns' if sys.platform == 'darwin' else 'assets/icon.ico'][0],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='MortgageWork',
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
            'CFBundleShortVersionString': _app_version,
            'CFBundleVersion': _app_version,
            'NSRequiresAquaSystemAppearance': False,
        },
    )
