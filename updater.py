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
launched silently and the app exits out from under it. /VERYSILENT skips
the installer's interactive "launch the app" checkbox (skipifsilent), so
the .iss carries a silent-only [Run] entry that reopens the new build
once setup finishes.
macOS: the DMG is mounted and a tiny detached shell script takes over —
it waits for the app to exit (a running process pins its bundle files,
which is exactly why "drag while open" fails), swaps the .app bundle
(move-aside first, so a failed copy rolls back), strips the quarantine
bit (an unsigned app would otherwise trip Gatekeeper again), relaunches,
and deletes itself.

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
import os
import platform
import re
import shlex
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
    else keeps the app running, restores the ready state with a visible
    error, and logs — an install failure must never be silent."""
    if not getattr(sys, "frozen", False):
        log.warning("update install refused: dev build")
        return {"ok": False, "error": "dev build — run the installer by hand"}
    with _lock:
        if _state["state"] != "ready":
            log.warning("update install refused: state=%s", _state["state"])
            return {"ok": False, "error": "nothing downloaded yet"}
    dest = _installer_path(str(_asset.get("url") or ""))
    if not dest.is_file():
        log.warning("update install refused: installer missing (%s)", dest)
        _set(state="error", error="installer file is missing — download again")
        return {"ok": False, "error": "installer file is missing — download again"}
    _set(state="installing")
    log.info("update install start · %s", dest.name)
    try:
        if sys.platform == "win32":
            return _install_windows(dest)
        if sys.platform == "darwin":
            return _install_macos(dest)
        raise RuntimeError("unsupported platform")
    except Exception as exc:  # noqa: BLE001
        log.warning("update install failed: %s", exc)
        _set(state="ready", error=str(exc))
        return {"ok": False, "error": str(exc)}


def _install_fail(msg: str) -> dict:
    """Non-exception install failure — keep it visible everywhere: the log,
    the panel (state back to ready with the message), and the bridge reply."""
    log.warning("update install: %s", msg)
    snap = _set(state="ready", error=msg)
    return {**snap, "ok": False}


def _install_windows(installer: Path) -> dict:
    """Launch the per-user Inno Setup installer silently, then hand control
    back to app.py which exits the app. CloseApplications=yes in the .iss
    covers the (tiny) race where setup reaches file copy before we're gone.
    /SP- skips the pre-install confirmation dialog that SURVIVES silent mode.

    Relaunch is the installer's own job here: the .iss's postinstall entry
    is skipifsilent (skipped under /VERYSILENT), but a silent-only [Run]
    entry guarded by [Code]'s UpdateRelaunch reopens the new build once
    setup finishes — the Windows twin of the macOS apply script's `open`."""
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


# Apply script, generated at install time. Runs detached, outlives the app,
# deletes itself when done. Every path is pre-quoted at generation time —
# the bundle name contains spaces, so bare interpolation would break.
_APPLY_SH = """#!/bin/sh
# Generated by Mortgage Work's updater — swaps in the downloaded update
# once the app has exited, then deletes itself. Safe to delete if orphaned.
pid={pid}
src={src}
target={target}
mount={mount}
self={self}
while kill -0 "$pid" 2>/dev/null; do sleep 0.3; done
sleep 0.5
old="$target.old"
rm -rf "$old"
if [ -d "$target" ]; then
  mv "$target" "$old" || exit 1
fi
if ! ditto "$src" "$target"; then
  # Roll back: the old bundle moves home and nothing changed.
  rm -rf "$target"
  [ -d "$old" ] && mv "$old" "$target"
  exit 1
fi
# Strip quarantine: the app is unsigned, and without this the user would
# fight Gatekeeper's right-click dance all over again.
xattr -dr com.apple.quarantine "$target" 2>/dev/null
rm -rf "$old"
hdiutil detach "$mount" 2>/dev/null
open "$target"
rm -f "$self"
"""


def _install_macos(dmg: Path) -> dict:
    """Replace the running .app bundle with the one inside the DMG.

    The replacement must outlive this process: a running app pins its bundle
    files, which is exactly why any "swap while open" attempt (Finder drag
    included) fails with "the item is in use". So a detached shell script
    waits for our PID to exit and then performs the swap.

    Target is the bundle's current home — except when that home is a mounted
    disk image (running straight off a DMG), which is read-only; the app
    then lands in /Applications where a Mac user expects to find it."""
    exe = Path(sys.executable).resolve()
    # Frozen layout: <bundle>.app/Contents/MacOS/<exe> — the bundle is two
    # directories UP from the executable (.parent.parent stops at Contents,
    # which is how "can't locate the app bundle" happened once).
    bundle = exe.parents[2] if len(exe.parents) > 2 else exe.parent
    log.info("update install: bundle=%s", bundle)
    if not bundle.name.endswith(".app"):
        return _install_fail(f"can't locate the app bundle ({bundle})")
    mount = _dmg_mount(dmg)
    try:
        src = Path(mount) / bundle.name
        if not src.exists():
            candidates = sorted(Path(mount).glob("*.app"))
            if not candidates:
                _dmg_detach(mount)
                return _install_fail("disk image contains no app")
            src = candidates[0]
        if bundle.as_posix().startswith("/Volumes/"):
            target = Path("/Applications") / bundle.name
        else:
            target = bundle
        script = _staging_dir() / "apply-update.sh"
        script.write_text(_APPLY_SH.format(
            pid=os.getpid(),
            src=shlex.quote(str(src)),
            target=shlex.quote(str(target)),
            mount=shlex.quote(mount),
            self=shlex.quote(str(script)),
        ))
        script.chmod(0o755)
        # Detached (new session) so our own shutdown can't take it down.
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("update hand-off · %s → %s (pid %d hands to apply script)",
                 bundle.name, target, os.getpid())
        return {"ok": True}
    except Exception:
        # Nothing took over — release the mount so we don't leak volumes.
        _dmg_detach(mount)
        raise
