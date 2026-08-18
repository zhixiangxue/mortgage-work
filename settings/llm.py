"""The ``llm:`` section — chat providers, their keys, and connectivity checks.

Also the runtime resolution path every caller uses to turn a
``"provider/model"`` ref into a chak URI plus API key (``resolve_ref``),
and the "first configured provider" fallback (``llm_target``) that
background jobs like clerk and IM fall back to.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

from .store import (SETTINGS_DIR, SETTINGS_FILE, SettingsError, clean_models,
                    key_hint, load, save, section)

log = logging.getLogger(__name__)


# ── Read ────────────────────────────────────────────────────────────────────

def llm_entry(provider: str) -> dict | None:
    """The raw entry for one provider (base_url/api_key/models), or None."""
    entry = section(load(), "llm").get(provider)
    return entry if isinstance(entry, dict) else None


def llm_target() -> str | None:
    """First configured provider/model as ``"provider/model"``, or None.

    The shared fallback for callers without a model picker of their own —
    a background job that demanded its own setting would just sit idle
    until somebody noticed it was configured wrong. A broken settings file
    reads as "nothing configured", never as a crash.
    """
    try:
        providers = section(load(), "llm")
    except Exception:  # noqa: BLE001 — broken settings read as empty
        return None
    for provider, entry in providers.items():
        if not isinstance(entry, dict) or not entry.get("api_key"):
            continue
        models = clean_models(entry.get("models"))
        if models:
            return f"{provider}/{models[0]}"
    return None


def resolve_ref(ref: str) -> tuple[str, str]:
    """"provider/model" → ``(chak_uri, api_key)``.

    The one place a ref turns into what chak needs; the URI form matches
    ``check_provider()`` exactly, so a picked model always resolves the way
    Check proved it does.
    """
    if not ref or "/" not in ref:
        raise SettingsError("no model selected — configure one in Settings")
    provider, model = ref.split("/", 1)
    entry = llm_entry(provider)
    if entry is None or not entry.get("api_key"):
        raise SettingsError(f"provider not configured: {provider}")
    base_url = str(entry.get("base_url") or "").strip()
    uri = f"{provider}@{base_url or '~'}:{model}"
    return uri, str(entry["api_key"])


def read_models() -> dict:
    """Everything the settings UI needs, with keys reduced to a hint."""
    data = load()
    providers = []
    for provider, entry in data["llm"].items():
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("api_key") or "")
        providers.append({
            "provider": str(provider),
            "base_url": str(entry.get("base_url") or ""),
            "models": clean_models(entry.get("models")),
            "key_hint": key_hint(key),
            "has_key": bool(key),
            # Last Check result, if one was ever run — a past-tense record the
            # UI stamps with a time, never presented as the live state.
            "last_check": _read_check(entry.get("last_check")),
        })
    return {"path": str(SETTINGS_FILE), "providers": providers}


def _read_check(lc) -> dict | None:
    if not isinstance(lc, dict) or not lc.get("at"):
        return None
    return {
        "ok": bool(lc.get("ok")),
        "at": int(lc.get("at") or 0),
        "note": str(lc.get("note") or ""),
    }


# ── Write ───────────────────────────────────────────────────────────────────

def save_provider(provider: str, base_url: str = "", api_key: str = "",
                  models=None) -> dict:
    """Create or update one provider, then hand back the fresh view.

    An empty ``api_key`` on an existing provider means "leave the key alone" —
    that's what makes Edit usable without re-typing a secret the UI can't show.
    """
    provider = (provider or "").strip().lower()
    if not provider:
        raise SettingsError("pick a provider")
    models = clean_models(models)
    if not models:
        raise SettingsError("pick at least one model")

    data = load()
    existing = data["llm"].get(provider)
    existing = existing if isinstance(existing, dict) else {}
    key = (api_key or "").strip() or str(existing.get("api_key") or "")
    if not key:
        raise SettingsError(f"{provider} needs an API key "
                            f"(local Ollama/vLLM accept any placeholder)")

    entry = {"api_key": key, "models": models}
    base_url = (base_url or "").strip().rstrip("/")
    if base_url:
        # Order matters for a hand-edited file: url above key above models
        entry = {"base_url": base_url, **entry}
    data["llm"][provider] = entry
    save(data)
    return read_models()


def remove_provider(provider: str) -> dict:
    data = load()
    if provider not in data["llm"]:
        raise SettingsError(f"provider not configured: {provider}")
    del data["llm"][provider]
    save(data)
    return read_models()


def remove_model(provider: str, model: str) -> dict:
    """Drop one model. The provider stays even when its last model goes — it
    still holds a working key, and re-adding a model shouldn't mean re-typing it."""
    data = load()
    entry = data["llm"].get(provider)
    if not isinstance(entry, dict):
        raise SettingsError(f"provider not configured: {provider}")
    models = clean_models(entry.get("models"))
    if model not in models:
        raise SettingsError(f"{provider} has no model {model}")
    entry["models"] = [m for m in models if m != model]
    save(data)
    return read_models()


# ── Connectivity check (the only outbound call in this package) ──────────────

# error_type values chak reports; mapped to something a loan officer can act on
REASONS = {
    "auth_error": "API key rejected",
    "connection_error": "can't reach the endpoint",
    "timeout": "timed out",
    "not_found": "model not available on this endpoint",
    "bad_request": "endpoint refused the request",
    "server_error": "provider is down",
}


def _write_check(provider: str, result: dict) -> int:
    """Save a Check outcome next to its provider, stamped with the time, so the
    settings tab can say "connected · 2h ago" instead of a blank "unchecked"
    every visit. The verbose ``detail`` is left out — it's console noise, not a
    fact worth persisting. Failing to record a check never fails the check."""
    at = int(time.time())
    record = {
        "ok": bool(result.get("ok")),
        "at": at,
        "model": result.get("model", ""),
        "note": result.get("note") or result.get("reason") or "",
    }
    try:
        data = load()
        entry = data["llm"].get(provider)
        if isinstance(entry, dict):
            entry["last_check"] = record
            save(data)
    except (SettingsError, OSError):
        pass
    return at


def check_provider(provider: str, model: str = "") -> dict:
    """Send one tiny message through chak and report what happened.

    A real round trip is the only honest check: it proves the endpoint resolves,
    the key is accepted, and the model exists. Anything cheaper (a socket
    connect, a /models GET) can pass while chat still fails.

    The outcome is written back to settings.yaml (see _write_check) so it survives
    reopening the tab — returned with the same ``at`` timestamp it was stored under.
    """
    entry = llm_entry(provider)
    if entry is None:
        raise SettingsError(f"provider not configured: {provider}")
    models = clean_models(entry.get("models"))
    model = (model or "").strip() or (models[0] if models else "")
    if not model:
        raise SettingsError(f"{provider} has no model to check")
    key = str(entry.get("api_key") or "")
    if not key:
        raise SettingsError(f"{provider} has no API key")

    base_url = str(entry.get("base_url") or "").strip()
    # chak's full URI form: provider@base_url:model, "~" = provider default
    uri = f"{provider}@{base_url or '~'}:{model}"

    # Imported here, not at module load: the settings page must still open when
    # chakpy is missing, and app startup shouldn't pay for the LLM stack.
    import chak

    try:
        conv = chak.Conversation(uri, api_key=key)
        conv.send("ping", timeout=20)
    except chak.ProviderError as exc:
        reason = exc.error_type or "unknown"
        # Rate limited means the endpoint answered and the key passed — that is
        # exactly what Check asks about, so it counts as reachable.
        if reason == "rate_limit":
            result = {"ok": True, "model": model, "note": "rate limited — key works"}
        else:
            log.warning("models check %s failed: %s · %s", uri, reason, exc)
            result = {"ok": False, "model": model,
                      "reason": REASONS.get(reason, reason), "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 — a bad URI/config must not crash the bridge
        log.warning("models check %s failed: %s", uri, exc)
        result = {"ok": False, "model": model, "reason": "check failed",
                  "detail": str(exc)}
    else:
        result = {"ok": True, "model": model}

    result["at"] = _write_check(provider, result)
    return result


# ── Open in the user's own editor ───────────────────────────────────────────

def reveal_models_file() -> dict:
    """"…or edit it in any editor" — make that one click. Creates the file first
    so the editor opens something instead of complaining."""
    if not SETTINGS_FILE.exists():
        save(load())
    path = str(SETTINGS_FILE)
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif os.name == "nt":
        subprocess.run(["explorer", f"/select,{path}"], check=False)
    else:
        subprocess.run(["xdg-open", str(SETTINGS_DIR)], check=False)
    return {"ok": True, "path": path}
