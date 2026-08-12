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

    llm:                           # LLM chat providers
      openai:
        base_url: https://api.openai.com/v1   # omit for the provider default
        api_key: sk-...
        models: [gpt-4o, gpt-4o-mini]

    embedding:                     # Embedding providers (peer of llm)
      openai:
        api_key: sk-...
        models: [text-embedding-3-small]
      bailian:
        api_key: sk-...
        models: [text-embedding-v3]

    memory:                        # Memory — just a pointer
      enabled: true
      embedding:
        provider: openai
        model: text-embedding-3-small

Provider keys are chak provider ids (``openai``, ``anthropic``, ``deepseek``,
``ollama``, …), so a configured entry maps straight onto a chak model URI:
``provider@base_url:model``. That's the whole point of the format — no
translation layer between what the user configured and what we call.

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
#   llm:                         # LLM chat providers
#     openai:
#       base_url: https://api.openai.com/v1   # omit for the provider default
#       api_key: sk-...
#       models: [gpt-4o, gpt-4o-mini]
#
#   embedding:                   # Embedding providers — peer of llm
#     openai:
#       api_key: sk-...
#       models: [text-embedding-3-small]
#     bailian:
#       api_key: sk-...
#       models: [text-embedding-v3]
#
#   memory:                      # Just a pointer — which embedder to use
#     enabled: true
#     embedding:
#       provider: openai
#       model: text-embedding-3-small
#
# Provider names are chak provider ids: openai, anthropic, google, deepseek,
# bailian, zhipu, moonshot, minimax, mistral, xai, siliconflow, volcengine,
# baidu, tencent, iflytek, azure, ollama, vllm.
"""

# Providers that serve an embeddings endpoint, mapped to the model we default
# to. Chat-only providers (DeepSeek, Anthropic, …) are absent on purpose: memory
# needs vectors, and offering a provider that can't produce them just moves the
# failure to the first recall.
EMBEDDING_CAPABLE = {
    "openai": "text-embedding-3-small",
    "bailian": "text-embedding-v3",
}

# Every model the LO can choose from per provider. The first entry is the
# default (same as EMBEDDING_CAPABLE).
EMBEDDING_MODELS = {
    "openai": ["text-embedding-3-small", "text-embedding-3-large",
               "text-embedding-ada-002"],
    "bailian": ["text-embedding-v3", "text-embedding-v4"],
}


class SettingsError(Exception):
    """Bad input or an unreadable settings file — reported to the user as text."""


def _load() -> dict:
    """The file as a dict. Missing file is not an error (nothing configured yet);
    unparsable content is — silently starting from scratch would overwrite a
    file the user was in the middle of editing by hand."""
    if not MODELS_FILE.exists():
        return {"llm": {}, "embedding": {}}
    try:
        data = yaml.safe_load(MODELS_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SettingsError(f"models.yaml is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SettingsError("models.yaml must be a mapping with `llm:` and `embedding:` keys")
    # Normalise llm section (was called providers in older files)
    llm = data.get("llm") or data.get("providers") or {}
    if not isinstance(llm, dict):
        raise SettingsError("`llm:` must be a mapping of provider id → settings")
    data["llm"] = llm
    data.pop("providers", None)  # migrate: old key → llm, don't write both
    # Normalise embedding section
    emb = data.get("embedding") or {}
    if not isinstance(emb, dict):
        raise SettingsError("`embedding:` must be a mapping of provider id → settings")
    data["embedding"] = emb
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
    entry = data["llm"].get(provider)
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
    for provider, entry in data["llm"].items():
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
    _save(data)
    return read_models()


def remove_provider(provider: str) -> dict:
    data = _load()
    _entry(data, provider)
    del data["llm"][provider]
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


# ── Memory: embedding providers (top-level) + memory pointer ────────────────
#
#  models.yaml structure:
#
#    llm:                {provider: {api_key, models, ...}}     — LLM tab
#    embedding:          {provider: {api_key, models, ...}}     — Embedding tab
#    memory:             {enabled, embedding: {provider, model}} — pointer
#
#  The Embedding tab manages the ``embedding:`` section (add/edit keys).
#  The Memory tab just stores a pointer under ``memory.embedding``.
#  At runtime, embedding_target() follows the pointer to find the key.

def _memory_block(data: dict) -> dict:
    block = data.get("memory")
    return block if isinstance(block, dict) else {}


def _embedding_providers(data: dict) -> dict:
    """The top-level ``embedding:`` section — embedding keys live here, separate
    from ``llm:`` (LLM chat keys)."""
    emb = data.get("embedding") or {}
    return emb if isinstance(emb, dict) else {}


def _embedding_candidates(data: dict) -> list[dict]:
    """Every provider that can embed, annotated with whether a key is already
    configured in the top-level ``embedding:`` section.  The Memory tab uses
    this to grey out providers that still need a key."""
    configured = _embedding_providers(data)
    out = []
    for provider, default_model in EMBEDDING_CAPABLE.items():
        cfg = configured.get(provider)
        key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
        # Models: from config first, then EMBEDDING_MODELS, then default
        if isinstance(cfg, dict) and cfg.get("models"):
            models = _clean_models(cfg["models"])
        else:
            models = EMBEDDING_MODELS.get(provider, [default_model])
        out.append({
            "provider": provider,
            "model": models[0] if models else default_model,
            "models": models,
            "available_models": EMBEDDING_MODELS.get(provider, [default_model]),
            "key_hint": _key_hint(key) if key else "",
            "has_key": bool(key),
        })
    return out


def _llm_candidates(data: dict) -> list[dict]:
    """Every LLM provider that has a key configured, for the Memory tab's
    extraction-model picker.  Unlike embedding, any chat provider qualifies —
    dream() just needs something that can talk."""
    out = []
    for provider, entry in data["llm"].items():
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("api_key") or "")
        models = _clean_models(entry.get("models"))
        out.append({
            "provider": str(provider),
            "model": models[0] if models else "",
            "models": models,
            "available_models": models,
            "key_hint": _key_hint(key) if key else "",
            "has_key": bool(key),
        })
    return out


def _memory_llm_view(data: dict) -> dict | None:
    """The ``memory.llm`` pointer as the Memory tab shows it, or None.

    Mirrors how ``read_memory_config`` resolves the embedding pointer: follows
    ``memory.llm.{provider, model}``, then checks the ``llm:`` section for a
    real key so the UI can grey it out if the key was rotated away."""
    block = _memory_block(data)
    ptr = block.get("llm")
    if not isinstance(ptr, dict) or not ptr.get("provider"):
        return None
    provider = str(ptr["provider"]).strip().lower()
    entry = data["llm"].get(provider)
    if not isinstance(entry, dict):
        # Provider removed from llm: section — pointer is stale
        return None
    model = str(ptr.get("model") or "").strip()
    if not model:
        models = _clean_models(entry.get("models"))
        model = models[0] if models else ""
    key = str(entry.get("api_key") or "")
    return {
        "provider": provider,
        "model": model,
        "key_hint": _key_hint(key) if key else "",
        "has_key": bool(key),
    }


def read_memory_config() -> dict:
    """What the Memory tab needs: the switch, the chosen embedder, the chosen
    extraction model, and the choices for each."""
    data = _load()
    block = _memory_block(data)
    candidates = _embedding_candidates(data)
    llm_candidates = _llm_candidates(data)
    llm_info = _memory_llm_view(data)
    emb = block.get("embedding")
    embedding = None
    if isinstance(emb, dict) and emb.get("provider"):
        provider = str(emb["provider"]).lower()
        # Model from the pointer first, then from embedding config, then default
        model = str(emb.get("model") or "").strip()
        if not model:
            cfg = _embedding_providers(data).get(provider)
            if isinstance(cfg, dict) and cfg.get("models"):
                model = str(cfg["models"][0])
        if not model:
            model = EMBEDDING_CAPABLE.get(provider, "")
        embedding = {
            "provider": provider,
            "model": model,
        }
        # Does the pointer's provider actually have a key configured?
        cfg = _embedding_providers(data).get(provider)
        cfg_key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
        if cfg_key:
            embedding["key_hint"] = _key_hint(cfg_key)
            embedding["has_key"] = True
        else:
            embedding["key_hint"] = ""
            embedding["has_key"] = False
    return {
        "enabled": bool(block.get("enabled")),
        "embedding": embedding,
        "candidates": candidates,
        "llm": llm_info,
        "llm_candidates": llm_candidates,
        "ready": bool(embedding) and embedding.get("has_key", False)
                 and llm_info is not None and llm_info.get("has_key", False),
    }


def read_embedding_providers() -> dict:
    """Return the configured embedding providers for the Settings → Embedding
    tab.  Each entry includes the key as a masked hint (the real key never
    crosses the bridge)."""
    data = _load()
    configured = _embedding_providers(data)
    out = {}
    for provider, default_model in EMBEDDING_CAPABLE.items():
        cfg = configured.get(provider)
        key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
        # Models actually configured, or the full list of available ones
        if isinstance(cfg, dict) and cfg.get("models"):
            models = _clean_models(cfg["models"])
        else:
            models = EMBEDDING_MODELS.get(provider, [default_model])
        out[provider] = {
            "provider": provider,
            "model": models[0] if models else default_model,
            "models": models,
            "available_models": EMBEDDING_MODELS.get(provider, [default_model]),
            "key_hint": _key_hint(key) if key else "",
            "has_key": bool(key),
        }
    # Also include the active pointer info
    emb = _memory_block(data).get("embedding")
    active = None
    if isinstance(emb, dict) and emb.get("provider"):
        active = str(emb["provider"]).lower()
    return {"providers": out, "active": active}


def embedding_target() -> tuple[str, str] | None:
    """The configured embedder as ``(chak_uri, api_key)``, or None.

    Reads the pointer from ``memory.embedding``, then looks up the actual key
    in the top-level ``embedding:`` section.  Embedding keys live in one place
    — the Embedding Settings tab — and the Memory tab just picks one."""
    data = _load()
    block = _memory_block(data)
    emb = block.get("embedding")
    if not isinstance(emb, dict) or not emb.get("provider"):
        return None
    provider = str(emb["provider"]).lower()
    # Model: from pointer first, then from embedding config, then default
    model = str(emb.get("model") or "").strip()
    if not model:
        cfg = _embedding_providers(data).get(provider)
        if isinstance(cfg, dict) and cfg.get("models"):
            model = str(cfg["models"][0])
    if not model:
        model = EMBEDDING_CAPABLE.get(provider, "")
    if not model:
        return None
    # Key lives in the top-level embedding section
    cfg = _embedding_providers(data).get(provider)
    key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
    if not key:
        return None
    return f"{provider}/{model}", key


def memory_llm_ref() -> str | None:
    """The configured extraction model as ``"provider/model"``, or None.

    Follows the ``memory.llm`` pointer, then looks up the key in the top-level
    ``llm:`` section (same split as embedding: the Models tab owns keys, the
    Memory tab only picks).  Returns the ref form ``_default_ref()`` expects."""
    data = _load()
    block = _memory_block(data)
    ptr = block.get("llm")
    if not isinstance(ptr, dict) or not ptr.get("provider"):
        return None
    provider = str(ptr["provider"]).strip().lower()
    entry = data["llm"].get(provider)
    if not isinstance(entry, dict) or not entry.get("api_key"):
        return None
    model = str(ptr.get("model") or "").strip()
    if not model:
        models = _clean_models(entry.get("models"))
        model = models[0] if models else ""
    if not model:
        return None
    return f"{provider}/{model}"


def save_memory_config(provider: str, model: str = "",
                       enabled: bool | None = None) -> dict:
    """Point memory at a provider for embeddings.  Stores only the pointer
    (provider + model); the key must already be configured in the top-level
    ``embedding:`` section via the Embedding Settings tab."""
    provider = (provider or "").strip().lower()
    if not provider:
        raise SettingsError("pick a provider for embeddings")
    if provider not in EMBEDDING_CAPABLE:
        raise SettingsError(f"{provider} has no embeddings endpoint — "
                            f"pick one of: {', '.join(sorted(EMBEDDING_CAPABLE))}")

    data = _load()
    # Validate: the provider must have a key in the embedding section
    cfg = _embedding_providers(data).get(provider)
    cfg_key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
    if not cfg_key:
        raise SettingsError(
            f"{provider} has no embedding key — configure it in "
            f"Settings → Embedding first")

    # Resolve model: explicit > first in embedding config > default
    model = (model or "").strip()
    if not model and isinstance(cfg, dict) and cfg.get("models"):
        model = str(cfg["models"][0])
    if not model:
        model = EMBEDDING_CAPABLE[provider]

    block = dict(_memory_block(data))
    block["embedding"] = {"provider": provider, "model": model}
    if enabled is not None:
        block["enabled"] = bool(enabled)
    block.setdefault("enabled", False)
    data["memory"] = block
    _save(data)
    return read_memory_config()


def save_memory_llm(provider: str, model: str = "") -> dict:
    """Point memory's extraction (dream) step at a chat model.

    Stores only the pointer (``memory.llm.{provider, model}``); the API key
    must already live in the top-level ``llm:`` section — configured via the
    Models tab, not here.

    Not a one-way door: swapping the extraction model does not invalidate
    existing embeddings, so this is callable any time memory is on."""
    provider = (provider or "").strip().lower()
    if not provider:
        raise SettingsError("pick a provider for extraction")

    data = _load()
    entry = data["llm"].get(provider)
    if not isinstance(entry, dict) or not entry.get("api_key"):
        raise SettingsError(
            f"{provider} has no key — configure it in Settings → Models first")

    # Resolve model: explicit > first in llm config > error
    model = (model or "").strip()
    if not model:
        models = _clean_models(entry.get("models"))
        model = models[0] if models else ""
    if not model:
        raise SettingsError(f"{provider} has no model configured")

    block = dict(_memory_block(data))
    block["llm"] = {"provider": provider, "model": model}
    data["memory"] = block
    _save(data)
    return read_memory_config()


def save_embedding_provider(provider: str, api_key: str,
                            model: str = "") -> dict:
    """Save or update an embedding provider config in the top-level
    ``embedding:`` section.  Called from Settings → Embedding when the LO
    edits a key inline, or when they change just the model dropdown.
    Does NOT change which provider is active (that's the Memory tab's job)."""
    provider = (provider or "").strip().lower()
    api_key = (api_key or "").strip()
    if not provider:
        raise SettingsError("pick a provider")
    if provider not in EMBEDDING_CAPABLE:
        raise SettingsError(f"{provider} is not an embedding provider")
    data = _load()
    existing = _embedding_providers(data).get(provider)
    # Key: use the provided one, or keep the existing one, or fail
    if api_key:
        key = api_key
    elif isinstance(existing, dict) and existing.get("api_key"):
        key = existing["api_key"]
    else:
        raise SettingsError("API key is required")
    # Model: use provided, or default
    model = (model or "").strip() or EMBEDDING_CAPABLE[provider]
    # Preserve existing models, add new one if novel
    existing_models = _clean_models(existing.get("models")) if isinstance(existing, dict) else []
    if model not in existing_models:
        existing_models = [model] + existing_models
    data["embedding"][provider] = {
        "api_key": key,
        "models": existing_models,
    }
    _save(data)
    return read_embedding_providers()


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
        entry = data["llm"].get(provider)
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
