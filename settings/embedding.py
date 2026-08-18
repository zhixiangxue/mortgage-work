"""The ``embedding:`` section — embedding providers and their keys.

Keys live here, in one place; the Memory tab only stores a pointer under
``memory.embedding``. At runtime, ``embedding_target()`` follows the pointer
to find the key.
"""
from __future__ import annotations

import logging

from .store import (SettingsError, clean_models, key_hint, load, save,
                    section)

log = logging.getLogger(__name__)

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


def _embedding_providers(data: dict) -> dict:
    """The top-level ``embedding:`` section — embedding keys live here,
    separate from ``llm:`` (LLM chat keys)."""
    return section(data, "embedding")


def read_embedding_providers() -> dict:
    """Return the configured embedding providers for the Settings → Embedding
    tab.  Each entry includes the key as a masked hint (the real key never
    crosses the bridge)."""
    data = load()
    configured = _embedding_providers(data)
    out = {}
    for provider, default_model in EMBEDDING_CAPABLE.items():
        cfg = configured.get(provider)
        key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
        # Models actually configured, or the full list of available ones
        if isinstance(cfg, dict) and cfg.get("models"):
            models = clean_models(cfg["models"])
        else:
            models = EMBEDDING_MODELS.get(provider, [default_model])
        out[provider] = {
            "provider": provider,
            "model": models[0] if models else default_model,
            "models": models,
            "available_models": EMBEDDING_MODELS.get(provider, [default_model]),
            "key_hint": key_hint(key) if key else "",
            "has_key": bool(key),
        }
    # Also include the active pointer info
    emb = section(data, "memory").get("embedding")
    active = None
    if isinstance(emb, dict) and emb.get("provider"):
        active = str(emb["provider"]).lower()
    return {"providers": out, "active": active}


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
    data = load()
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
    existing_models = clean_models(existing.get("models")) if isinstance(existing, dict) else []
    if model not in existing_models:
        existing_models = [model] + existing_models
    data["embedding"][provider] = {
        "api_key": key,
        "models": existing_models,
    }
    save(data)
    return read_embedding_providers()


def embedding_target() -> tuple[str, str] | None:
    """The configured embedder as ``(chak_uri, api_key)``, or None.

    Reads the pointer from ``memory.embedding``, then looks up the actual key
    in the top-level ``embedding:`` section.  Embedding keys live in one place
    — the Embedding Settings tab — and the Memory tab just picks one."""
    data = load()
    emb = section(data, "memory").get("embedding")
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
