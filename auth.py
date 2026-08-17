"""Client-side session store — where the login payload from the auth service
lives on this machine.

The payload (session JWT + identity + work_repo_url with its git credential)
is the only thing standing between a cold boot and a clone, so it must
survive restarts but never ship anywhere. Storage ladder:

1. **OS keychain** (macOS Keychain / Windows Credential Manager via
   ``keyring``) — encrypted at rest, per-OS-user. The right place for the
   git credential.
2. **Plain fallback file** (``~/MortgageWork/session.json``, mode 0600) —
   only when no keychain backend is usable (rare: headless boxes, broken
   Secret Service). Same content, weaker at-rest protection; logged so it's
   never a silent downgrade.

The rest of the app never touches either: ``user.py`` is the single reader.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

SERVICE = "Mortgage Work"
ENTRY = "auth-session"
FALLBACK_PATH = Path.home() / "MortgageWork" / "session.json"


def save_session(payload: dict) -> None:
    """Persist the login payload. Keychain first; file only as a fallback."""
    data = json.dumps(payload)
    try:
        import keyring
        keyring.set_password(SERVICE, ENTRY, data)
        return
    except Exception as exc:  # no backend, locked keychain, etc.
        log.warning("keychain unavailable (%s) — session stored in %s",
                    exc, FALLBACK_PATH)
    FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_PATH.write_text(data, encoding="utf-8")
    try:
        os.chmod(FALLBACK_PATH, 0o600)
    except OSError:
        pass


def load_session() -> dict | None:
    """The stored payload, or None when this machine has never logged in
    (or was logged out)."""
    try:
        import keyring
        data = keyring.get_password(SERVICE, ENTRY)
        if data:
            return json.loads(data)
    except Exception as exc:
        log.warning("keychain read failed (%s) — trying the fallback file", exc)
    try:
        return json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def clear_session() -> None:
    """Forget everything — called on logout."""
    try:
        import keyring
        keyring.delete_password(SERVICE, ENTRY)
    except Exception:
        pass  # never stored there, or backend gone — the file pass below covers it
    try:
        FALLBACK_PATH.unlink()
    except FileNotFoundError:
        pass
