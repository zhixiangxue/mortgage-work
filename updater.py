"""App updater — release discovery, background download, one-click install.

Why this exists
---------------
Released builds must be able to renew themselves without sending users to a
website. The auth service (``server/``) carries release metadata — version,
notes, and per-platform asset URLs that point at GitHub Release attachments
(this module never touches the binaries' hosting). Flow:

    boot + every 6h → GET /app/latest?platform=… → newer version?
        → TopBar icon → user clicks Download → streamed download + sha256
        → user clicks Install → platform installer runs → app relaunches

Install mechanics
-----------------
Windows: the per-user Inno Setup installer needs no elevation — it is
launched silently and the app exits out from under it.
macOS: the DMG is mounted, the .app bundle is swapped in /Applications via
ditto, the quarantine bit is stripped (an unsigned app would otherwise trip
Gatekeeper again), and the bundle is relaunched with ``open``. A bundle
running OUTSIDE /Applications degrades to "DMG mounted — drag manually".

Dev builds run the check and download so the whole UI stays testable, but
install is refused — there is no bundle to replace.

Usage
-----
    updater.on_state(lambda s: push_to_frontend(s))
    updater.start()          # spawns the poll loop (idempotent)
    updater.check_now()      # manual check (Settings / UpdatePanel)
    updater.download()       # background download with progress
    updater.install()        # apply + signal the app to relaunch
"""
from __future__ import annotations

import hashlib
import logging
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from config import SERVICES, app_version

log = logging.getLogger(__name__)

# First check shortly after boot (the window and network both need a moment),
# then settle into a quiet six-hour cadence. Releases are rare events; a
# tighter loop buys nothing.
FIRST_CHECK_DELAY_SECS = 15
CHECK_INTERVAL_SECS = 6 * 3600

DOWNLOAD_CHUNK = 256 * 1024

# States: idle → available → downloading → ready → installing.
# "error" hangs off any stage and keeps the last release info intact so the
# panel can offer a retry without a fresh check.
STATE = {"idle", "available", "downloading", "ready", "installing", "error"}


def platform_key() -> str:
    """Asset flavor this machine needs — mirrors the server's RELEASE_PLATFORMS."""
    if sys.platform == "win32":
        return "windows-x64"
    if sys.platform == "darwin":
        return "macos-arm64" if platform.machine() == "arm64" else "macos-x64"
    return ""


def _staging_dir() -> Path:
    """Where installers land before install — the OS-conventional app-data
    dir, never the work repo (git must not see them)."""
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        d = base / "MortgageWork" / "updates"
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "Mortgage Work" / "updates"
    else:
        d = Path.home() / ".mortgage-work" / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vtup(v: str) -> tuple:
    """Numeric ordering key for a dotted version. Never raises — 'unknown'
    dev stamps rank below every real release, which is the right call."""
    parts = []
    for seg in re.split(r"[.\-+]", (v or "").strip().lstrip("vV")):
        m = re.match(r"^\d+", seg)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts) or (0,)


def _is_newer(latest: str, current: str) -> bool:
    a, b = _vtup(latest), _vtup(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


# ── State ──

_lock = threading.Lock()
_state = {
    "enabled": True,           # False only on platforms without an asset flavor
    "state": "idle",
    "current": "",             # version this build carries
    "version": None,           # the newer version, once discovered
    "notes": "",
    "size": 0,
    "progress": None,          # 0-100 while downloading
    "error": "",
}
_notify_cbs = []
_cancel = threading.Event()
_started = False
_asset: dict = {}               # the asset row for this platform


def on_state(cb) -> None:
    """Register a push callback — app.py wires this to the frontend."""
    _notify_cbs.append(cb)


def status() -> dict:
    with _lock:
        return dict(_state)


def _set(**kw) -> dict:
    with _lock:
        _state.update(kw)
        snap = dict(_state)
    for cb in list(_notify_cbs):
        try:
            cb(snap)
        except Exception as exc:  # noqa: BLE001 — a push failure must not kill the updater
            log.debug("update state push failed: %s", exc)
    return snap


# ── Check ──

def _check_once() -> None:
    """One discovery round against /app/latest. Quiet on every failure —
    an offline machine simply tries again next tick."""
    plat = platform_key()
    if not plat:
        return
    url = f"{SERVICES.auth_service_url.rstrip('/')}/app/latest?platform={plat}"
    try:
        res = httpx.get(url, timeout=15)
        data = res.json()
    except Exception as exc:  # noqa: BLE001
        log.debug("update check failed: %s", exc)
        return
    release = (data or {}).get("release")
    if not release or not isinstance(release, dict):
        return
    latest = str(release.get("version") or "")
    current = app_version()
    asset = release.get("asset") or {}
    if not latest or not _is_newer(latest, current):
        return
    # A download or an already-downloaded installer owns the floor — the
    # discovery result waits for the next round after they conclude.
    with _lock:
        busy = _state["state"] in ("downloading", "ready", "installing")
        same = _state["version"] == latest
    if busy and same:
        return
    global _asset
    _asset = asset
    _set(state="available", version=latest,
         notes=str(release.get("notes") or ""),
         size=int(asset.get("size") or 0), progress=None, error="")
    log.info("update available · %s → %s", current, latest)


def check_now() -> dict:
    """Manual check — runs synchronously so the panel gets the answer in
    the same bridge round-trip (the endpoint is one SQLite read)."""
    _check_once()
    return status()


def _poll_loop() -> None:
    time.sleep(FIRST_CHECK_DELAY_SECS)
    while True:
        try:
            _check_once()
        except Exception as exc:  # noqa: BLE001
            log.debug("update poll error: %s", exc)
        time.sleep(CHECK_INTERVAL_SECS)


def start() -> None:
    """Spawn the poll loop once. The whole feature degrades to invisible
    when this platform has no asset flavor (exotic dev OSes)."""
    global _started
    if _started:
        return
    _started = True
    with _lock:
        _state["current"] = app_version()
        _state["enabled"] = bool(platform_key())
    if not platform_key():
        return
    threading.Thread(target=_poll_loop, daemon=True, name="updater-poll").start()


# ── Download ──

def download() -> dict:
    """Kick off (or report) the background download. Idempotent: a running
    download just reports its progress; a finished one reports ready."""
    with _lock:
        st = _state["state"]
        if st == "downloading":
            return dict(_state)
        if st == "ready":
            return dict(_state)
        if st not in ("available", "error"):
            return dict(_state)
        url = str(_asset.get("url") or "")
    if not url:
        return _set(state="error", error="release has no download for this platform")
    _cancel.clear()
    _set(state="downloading", progress=0.0, error="")
    threading.Thread(target=_download_worker, args=(url,), daemon=True,
                     name="updater-download").start()
    return status()


def cancel() -> dict:
    """Abort a running download — the worker notices within one chunk and
    restores the available state."""
    if status().get("state") == "downloading":
        _cancel.set()
    return status()


def _installer_path(url: str) -> Path:
    name = Path(urlsplit(url).path).name or "installer"
    return _staging_dir() / name


def _download_worker(url: str) -> None:
    """Stream the installer to disk with sha256 + progress. Every failure
    path lands on state=error with a readable message and keeps the release
    info so the panel can offer Retry."""
    expect_sha = str(_asset.get("sha256") or "").lower()
    dest = _installer_path(url)
    tmp = dest.with_suffix(dest.suffix + ".part")
    hasher = hashlib.sha256()
    total = int(_asset.get("size") or 0)
    got = 0
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=30) as res:
            res.raise_for_status()
            total = total or int(res.headers.get("content-length") or 0)
            last_push = 0.0
            with open(tmp, "wb") as f:
                for chunk in res.iter_bytes(DOWNLOAD_CHUNK):
                    if _cancel.is_set():
                        raise InterruptedError("canceled")
                    f.write(chunk)
                    hasher.update(chunk)
                    got += len(chunk)
                    pct = (got / total * 100) if total else 0.0
                    # Push at most once per percent point — a 200MB file over
                    # a fast line would otherwise hammer the bridge.
                    if pct - last_push >= 1.0 or got == total:
                        last_push = pct
                        _set(progress=round(pct, 1))
        if expect_sha and hasher.hexdigest() != expect_sha:
            tmp.unlink(missing_ok=True)
            _set(state="error", progress=None,
                 error="checksum mismatch — download again")
            log.warning("update download sha256 mismatch (%s)", dest.name)
            return
        tmp.replace(dest)
        _set(state="ready", progress=None)
        log.info("update downloaded · %s (%d bytes)", dest.name, got)
    except InterruptedError:
        tmp.unlink(missing_ok=True)
        _set(state="available", progress=None)
        log.info("update download canceled")
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        _set(state="error", progress=None, error=f"download failed: {exc}")
        log.warning("update download failed: %s", exc)


# ── Install ──

def install() -> dict:
    """Apply the downloaded installer. Returns {"ok": True} when the app
    should shut itself down (the install proceeds without it); anything
    else keeps the app running and shows the message."""
    if not getattr(sys, "frozen", False):
        return {"ok": False, "error": "dev build — run the installer by hand"}
    with _lock:
        if _state["state"] != "ready":
            return {"ok": False, "error": "nothing downloaded yet"}
    dest = _installer_path(str(_asset.get("url") or ""))
    if not dest.is_file():
        _set(state="error", error="installer file is missing — download again")
        return {"ok": False, "error": "installer file is missing — download again"}
    _set(state="installing")
    try:
        if sys.platform == "win32":
            return _install_windows(dest)
        if sys.platform == "darwin":
            return _install_macos(dest)
        return {"ok": False, "error": "unsupported platform"}
    except Exception as exc:  # noqa: BLE001
        log.warning("update install failed: %s", exc)
        _set(state="ready", error=str(exc))
        return {"ok": False, "error": str(exc)}


def _install_windows(installer: Path) -> dict:
    """Launch the per-user Inno Setup installer silently, then hand control
    back to app.py which exits the app. CloseApplications=yes in the .iss
    covers the (tiny) race where setup reaches file copy before we're gone.
    /SP- skips the pre-install confirmation dialog that SURVIVES silent mode."""
    subprocess.Popen([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES",
                      "/NORESTART", "/SP-"])
    log.info("update installer launched · %s", installer.name)
    return {"ok": True}


def _dmg_mount(dmg: Path) -> str:
    """Attach a DMG read-only and return its mount point."""
    out = subprocess.run(
        ["hdiutil", "attach", "-plist", "-nobrowse", "-readonly", str(dmg)],
        capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"couldn't open the disk image: {out.stderr.strip()[:200]}")
    import plistlib
    for ent in plistlib.loads(out.stdout.encode()).get("system-entities", []):
        mp = ent.get("mount-point")
        if mp:
            return mp
    raise RuntimeError("disk image has no mountable volume")


def _dmg_detach(mount: str) -> None:
    subprocess.run(["hdiutil", "detach", mount], capture_output=True, timeout=60)


def _install_macos(dmg: Path) -> dict:
    """Swap the .app bundle inside /Applications. The running process lives
    inside that bundle — renaming/deleting it mid-flight is legal on macOS
    (the binary stays mapped), and the relaunch fires before this process
    exits so the window never visibly dies."""
    bundle = Path(sys.executable).resolve().parent.parent
    if not bundle.name.endswith(".app") or "/Applications" not in bundle.as_posix():
        # Running from Downloads/Desktop — auto-replace would write somewhere
        # the user isn't looking. Degrade: mount the image and let them drag.
        mount = _dmg_mount(dmg)
        subprocess.Popen(["open", mount])
        return {"ok": False,
                "error": "drag the new app onto your current one to update"}
    mount = _dmg_mount(dmg)
    try:
        src = Path(mount) / bundle.name
        if not src.exists():
            candidates = sorted(Path(mount).glob("*.app"))
            if not candidates:
                raise RuntimeError("disk image contains no app")
            src = candidates[0]
        # Move-aside beats delete-first: a failed ditto restores the old
        # bundle with one rename, so the user is never left appless.
        old = bundle.with_name(bundle.name + ".old")
        shutil.rmtree(old, ignore_errors=True)   # leftover from a failed run
        bundle.rename(old)
        try:
            r = subprocess.run(["ditto", str(src), str(bundle)],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[:200] or "copy failed")
        except Exception:
            # Roll back: the old bundle moves home and nothing changed.
            shutil.rmtree(bundle, ignore_errors=True)
            old.rename(bundle)
            raise
        # Strip quarantine: the app is unsigned, and without this the user
        # would fight Gatekeeper's right-click dance all over again.
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(bundle)],
                       capture_output=True, timeout=60)
        shutil.rmtree(old, ignore_errors=True)
        subprocess.Popen(["open", str(bundle)])
        log.info("update applied · %s → %s", bundle.name, _state.get("version"))
        return {"ok": True}
    finally:
        _dmg_detach(mount)
