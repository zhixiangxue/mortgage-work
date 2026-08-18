"""The ``memory:`` section — just pointers, no keys of its own.

``memory.embedding`` points at an entry in the ``embedding:`` section,
``memory.llm`` at one in ``llm:``. The Embedding and Models tabs own the
keys; this tab only picks. At runtime the agent side follows the pointers
via ``embedding_target()`` and ``memory_llm_ref()``.
"""
from __future__ import annotations

import logging

from .embedding import EMBEDDING_CAPABLE, EMBEDDING_MODELS
from .store import SettingsError, clean_models, key_hint, load, save, section

log = logging.getLogger(__name__)


def _memory_block(data: dict) -> dict:
    return section(data, "memory")


def _embedding_section(data: dict) -> dict:
    """The top-level ``embedding:`` section, where embedding keys live."""
    return section(data, "embedding")


def _embedding_candidates(data: dict) -> list[dict]:
    """Every provider that can embed, annotated with whether a key is already
    configured in the top-level ``embedding:`` section.  The Memory tab uses
    this to grey out providers that still need a key."""
    configured = _embedding_section(data)
    out = []
    for provider, default_model in EMBEDDING_CAPABLE.items():
        cfg = configured.get(provider)
        key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
        # Models: from config first, then EMBEDDING_MODELS, then default
        if isinstance(cfg, dict) and cfg.get("models"):
            models = clean_models(cfg["models"])
        else:
            models = EMBEDDING_MODELS.get(provider, [default_model])
        out.append({
            "provider": provider,
            "model": models[0] if models else default_model,
            "models": models,
            "available_models": EMBEDDING_MODELS.get(provider, [default_model]),
            "key_hint": key_hint(key) if key else "",
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
        models = clean_models(entry.get("models"))
        out.append({
            "provider": str(provider),
            "model": models[0] if models else "",
            "models": models,
            "available_models": models,
            "key_hint": key_hint(key) if key else "",
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
        models = clean_models(entry.get("models"))
        model = models[0] if models else ""
    key = str(entry.get("api_key") or "")
    return {
        "provider": provider,
        "model": model,
        "key_hint": key_hint(key) if key else "",
        "has_key": bool(key),
    }


def read_memory_config() -> dict:
    """What the Memory tab needs: the switch, the chosen embedder, the chosen
    extraction model, and the choices for each."""
    data = load()
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
            cfg = _embedding_section(data).get(provider)
            if isinstance(cfg, dict) and cfg.get("models"):
                model = str(cfg["models"][0])
        if not model:
            model = EMBEDDING_CAPABLE.get(provider, "")
        embedding = {
            "provider": provider,
            "model": model,
        }
        # Does the pointer's provider actually have a key configured?
        cfg = _embedding_section(data).get(provider)
        cfg_key = str(cfg.get("api_key") or "") if isinstance(cfg, dict) else ""
        if cfg_key:
            embedding["key_hint"] = key_hint(cfg_key)
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


def memory_llm_ref() -> str | None:
    """The configured extraction model as ``"provider/model"``, or None.

    Follows the ``memory.llm`` pointer, then looks up the key in the top-level
    ``llm:`` section (same split as embedding: the Models tab owns keys, the
    Memory tab only picks)."""
    data = load()
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
        models = clean_models(entry.get("models"))
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

    data = load()
    # Validate: the provider must have a key in the embedding section
    cfg = _embedding_section(data).get(provider)
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
    save(data)
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

    data = load()
    entry = data["llm"].get(provider)
    if not isinstance(entry, dict) or not entry.get("api_key"):
        raise SettingsError(
            f"{provider} has no key — configure it in Settings → Models first")

    # Resolve model: explicit > first in llm config > error
    model = (model or "").strip()
    if not model:
        models = clean_models(entry.get("models"))
        model = models[0] if models else ""
    if not model:
        raise SettingsError(f"{provider} has no model configured")

    block = dict(_memory_block(data))
    block["llm"] = {"provider": provider, "model": model}
    data["memory"] = block
    save(data)
    return read_memory_config()


def set_memory_enabled(enabled: bool) -> dict:
    """Flip the switch. Turning it on without an embedder configured is refused
    rather than accepted-and-ignored, so the state on disk stays truthful."""
    data = load()
    block = dict(_memory_block(data))
    emb = block.get("embedding")
    if enabled and not (isinstance(emb, dict) and emb.get("provider")):
        raise SettingsError("configure an embedding provider first")
    block["enabled"] = bool(enabled)
    data["memory"] = block
    save(data)
    return read_memory_config()
