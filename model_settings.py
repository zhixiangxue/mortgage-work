"""Model settings: a plain YAML file in the user's own directory.

Why a file, and why *there*
---------------------------
This is the one piece of state that holds API keys, so it never leaves the
machine. It lives at ``~/MortgageWork/settings/models.yaml``:

* outside the git checkout (``~/MortgageWork/<repo>/``) — the sync engine has
  no idea it exists, so a key can't ride a commit to the remote;
* outside every service in config.py — no database, no rqlite row, no request.

Reading and writing it is plain filesystem work. The only time this module
touches the network is ``check_provider()``, which the user asks for by
clicking Check.

Shape of the file — hand-editable on purpose, the settings UI and a text
editor are interchangeable views of the same bytes::

    providers:
      openai:
        base_url: https://api.openai.com/v1   # omit for the provider default
        api_key: sk-...
        models: [gpt-4o, gpt-4o-mini]

Provider keys are chak provider ids (``openai``, ``anthropic``, ``deepseek``,
``ollama``, …), so a configured entry maps straight onto a chak model URI:
``provider@base_url:model``. That's the whole point of the format — no
translation layer between what the user configured and what we call.

A second, sibling block configures the memory agent::

    memory:
      enabled: true
      embedding:
        provider: openai
        model: text-embedding-3-small

It names a provider rather than repeating its key: one secret, one home. Change
the key under ``providers:`` and memory picks it up on the next read.

Run standalone to inspect the current file:

    uv run python model_settings.py
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

SETTINGS_DIR = Path.home() / "MortgageWork" / "settings"
MODELS_FILE = SETTINGS_DIR / "models.yaml"

HEADER = """\
# Mortgage Work — model providers.
#
# This file holds your API keys. It stays on this machine: it is NOT inside the
# work repo, so it is never committed, pushed, or sent anywhere. Edit it here or
# in the app's Settings tab — they read and write the same file.
#
#   providers:
#     openai:
#       base_url: https://api.openai.com/v1   # omit for the provider default
#       api_key: sk-...
#       models: [gpt-4o, gpt-4o-mini]
#
# Provider names are chak provider ids: openai, anthropic, google, deepseek,
# bailian, zhipu, moonshot, minimax, mistral, xai, siliconflow, volcengine,
# baidu, tencent, iflytek, azure, ollama, vllm.
#
# A `memory:` block (same level as `providers:`) points the memory agent at one
# of the providers above for embeddings — see the Memory tab in the app.
"""

# Providers that serve an embeddings endpoint, mapped to the model we default
# to. Chat-only providers (DeepSeek, Anthropic, …) are absent on purpose: memory
# needs vectors, and offering a provider that can't produce them just moves the
# failure to the first recall.
EMBEDDING_CAPABLE = {
    "openai": "text-embedding-3-small",
    "azure": "text-embedding-3-small",
    "bailian": "text-embedding-v3",
}


class SettingsError(Exception):
    """Bad input or an unreadable settings file — reported to the user as text."""


def _load() -> dict:
    """The file as a dict. Missing file is not an error (nothing configured yet);
    unparsable content is — silently starting from scratch would overwrite a
    file the user was in the middle of editing by hand."""
    if not MODELS_FILE.exists():
        return {"providers": {}}
    try:
        data = yaml.safe_load(MODELS_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SettingsError(f"models.yaml is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SettingsError("models.yaml must be a mapping with a `providers:` key")
    provs = data.get("providers") or {}
    if not isinstance(provs, dict):
        raise SettingsError("`providers:` must be a mapping of provider id → settings")
    data["providers"] = provs
    return data


def _save(data: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(
        HEADER + "\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    # Owner-only, best effort. A no-op on Windows (ACLs ignore the mode), which
    # is why it isn't the security story — keeping the file off the network is.
    try:
        MODELS_FILE.chmod(0o600)
    except OSError:
        pass


def _entry(data: dict, provider: str) -> dict:
    entry = data["providers"].get(provider)
    if not isinstance(entry, dict):
        raise SettingsError(f"provider not configured: {provider}")
    return entry


def _key_hint(key: str) -> str:
    """What the UI shows instead of the key. The key itself never crosses the
    bridge — the webview can't leak what it was never handed."""
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:5]}…{key[-4:]}"


def _clean_models(models) -> list[str]:
    if isinstance(models, str):
        models = [models]
    out = []
    for m in models or []:
        m = str(m).strip()
        if m and m not in out:
            out.append(m)
    return out


# ── Read ────────────────────────────────────────────────────────────────────

def read_models() -> dict:
    """Everything the settings UI needs, with keys reduced to a hint."""
    data = _load()
    providers = []
    for provider, entry in data["providers"].items():
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("api_key") or "")
        providers.append({
            "provider": str(provider),
            "base_url": str(entry.get("base_url") or ""),
            "models": _clean_models(entry.get("models")),
            "key_hint": _key_hint(key),
            "has_key": bool(key),
            # Last Check result, if one was ever run — a past-tense record the
            # UI stamps with a time, never presented as the live state.
            "last_check": _read_check(entry.get("last_check")),
        })
    return {"path": str(MODELS_FILE), "providers": providers}


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
    models = _clean_models(models)
    if not models:
        raise SettingsError("pick at least one model")

    data = _load()
    existing = data["providers"].get(provider)
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
    data["providers"][provider] = entry
    _save(data)
    return read_models()


def remove_provider(provider: str) -> dict:
    data = _load()
    _entry(data, provider)
    del data["providers"][provider]
    _save(data)
    return read_models()


def remove_model(provider: str, model: str) -> dict:
    """Drop one model. The provider stays even when its last model goes — it
    still holds a working key, and re-adding a model shouldn't mean re-typing it."""
    data = _load()
    entry = _entry(data, provider)
    models = _clean_models(entry.get("models"))
    if model not in models:
        raise SettingsError(f"{provider} has no model {model}")
    entry["models"] = [m for m in models if m != model]
    _save(data)
    return read_models()


# ── Memory: which provider embeds the conversations ─────────────────────────

def _memory_block(data: dict) -> dict:
    block = data.get("memory")
    return block if isinstance(block, dict) else {}


def _embedding_candidates(data: dict) -> list[dict]:
    """Configured providers that can actually embed. A provider with no key is
    left out — it would fail on the first call, and an option that can't work
    isn't an option."""
    out = []
    for provider, entry in data["providers"].items():
        provider = str(provider).lower()
        if provider not in EMBEDDING_CAPABLE or not isinstance(entry, dict):
            continue
        key = str(entry.get("api_key") or "")
        if not key:
            continue
        out.append({
            "provider": provider,
            "model": EMBEDDING_CAPABLE[provider],
            "key_hint": _key_hint(key),
        })
    return out


def read_memory_config() -> dict:
    """What the Memory tab needs: the switch, the chosen embedder, the choices.

    An empty ``candidates`` list is the honest answer to "why can't I turn this
    on" — no configured provider serves embeddings — and the UI can say so
    instead of letting the user enable something that silently never recalls.
    """
    data = _load()
    block = _memory_block(data)
    candidates = _embedding_candidates(data)
    emb = block.get("embedding")
    embedding = None
    if isinstance(emb, dict) and emb.get("provider"):
        provider = str(emb["provider"]).lower()
        embedding = {
            "provider": provider,
            "model": str(emb.get("model") or "").strip()
                     or EMBEDDING_CAPABLE.get(provider, ""),
        }
    return {
        "enabled": bool(block.get("enabled")),
        "embedding": embedding,
        "candidates": candidates,
        # The chosen provider can go away underneath us (key removed, provider
        # deleted). We keep the pointer — repointing memory at a different
        # embedder would orphan every stored vector — but say it isn't usable.
        "ready": bool(embedding) and any(
            c["provider"] == embedding["provider"] for c in candidates),
    }


def embedding_target() -> tuple[str, str] | None:
    """The configured embedder as ``(chak_uri, api_key)``, or None.

    Both the memory agent and the app open the same seeka store, and they must
    agree on the embedder — a different model means a different vector space,
    where nothing written by one side is findable by the other. So the answer
    comes from here rather than being assembled at each call site.

    The key is read live from ``providers:`` instead of being copied into the
    ``memory:`` block: one secret, one home.
    """
    data = _load()
    emb = _memory_block(data).get("embedding")
    if not isinstance(emb, dict) or not emb.get("provider"):
        return None
    provider = str(emb["provider"]).lower()
    model = str(emb.get("model") or "").strip() or EMBEDDING_CAPABLE.get(provider, "")
    if not model:
        return None
    entry = data["providers"].get(provider)
    key = str(entry.get("api_key") or "") if isinstance(entry, dict) else ""
    if not key:
        return None
    return f"{provider}/{model}", key


def save_memory_config(provider: str, model: str = "",
                       enabled: bool | None = None) -> dict:
    """Point memory at a provider for embeddings.

    Switching embedders is not a free edit: a different model means a different
    vector space, so stored vectors stop being comparable to new queries. The
    caller (the Memory tab) only offers this while the store is empty; here we
    just validate that the provider can do the job.
    """
    provider = (provider or "").strip().lower()
    if not provider:
        raise SettingsError("pick a provider for embeddings")

    data = _load()
    if provider not in EMBEDDING_CAPABLE:
        raise SettingsError(f"{provider} has no embeddings endpoint — "
                            f"pick one of: {', '.join(sorted(EMBEDDING_CAPABLE))}")
    entry = _entry(data, provider)
    if not str(entry.get("api_key") or ""):
        raise SettingsError(f"{provider} has no API key")

    block = dict(_memory_block(data))
    block["embedding"] = {
        "provider": provider,
        "model": (model or "").strip() or EMBEDDING_CAPABLE[provider],
    }
    if enabled is not None:
        block["enabled"] = bool(enabled)
    block.setdefault("enabled", False)
    data["memory"] = {"enabled": block["enabled"], "embedding": block["embedding"]}
    _save(data)
    return read_memory_config()


def set_memory_enabled(enabled: bool) -> dict:
    """Flip the switch. Turning it on without an embedder configured is refused
    rather than accepted-and-ignored, so the state on disk stays truthful."""
    data = _load()
    block = dict(_memory_block(data))
    emb = block.get("embedding")
    if enabled and not (isinstance(emb, dict) and emb.get("provider")):
        raise SettingsError("configure an embedding provider first")
    block["enabled"] = bool(enabled)
    data["memory"] = block
    _save(data)
    return read_memory_config()


# ── Connectivity check (the only outbound call in this module) ──────────────

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
        data = _load()
        entry = data["providers"].get(provider)
        if isinstance(entry, dict):
            entry["last_check"] = record
            _save(data)
    except (SettingsError, OSError):
        pass
    return at


def check_provider(provider: str, model: str = "") -> dict:
    """Send one tiny message through chak and report what happened.

    A real round trip is the only honest check: it proves the endpoint resolves,
    the key is accepted, and the model exists. Anything cheaper (a socket
    connect, a /models GET) can pass while chat still fails.

    The outcome is written back to models.yaml (see _write_check) so it survives
    reopening the tab — returned with the same ``at`` timestamp it was stored under.
    """
    data = _load()
    entry = _entry(data, provider)
    models = _clean_models(entry.get("models"))
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
    if not MODELS_FILE.exists():
        _save(_load())
    path = str(MODELS_FILE)
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif os.name == "nt":
        subprocess.run(["explorer", f"/select,{path}"], check=False)
    else:
        subprocess.run(["xdg-open", str(SETTINGS_DIR)], check=False)
    return {"ok": True, "path": path}


if __name__ == "__main__":
    view = read_models()
    print(f"settings file: {view['path']}"
          f"{'' if MODELS_FILE.exists() else ' (not created yet)'}")
    for p in view["providers"]:
        print(f"  {p['provider']:<12} {p['base_url'] or '(default url)':<40} "
              f"{p['key_hint'] or '(no key)':<14} {', '.join(p['models'])}")
    if not view["providers"]:
        print("  no providers configured")
    mem = read_memory_config()
    emb = mem["embedding"]
    print(f"memory: {'on' if mem['enabled'] else 'off'} · "
          f"{(emb['provider'] + '/' + emb['model']) if emb else 'no embedder'}"
          f"{'' if not emb or mem['ready'] else ' (provider unavailable)'}")
