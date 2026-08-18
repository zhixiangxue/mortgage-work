"""The only module that reads and writes settings.yaml.

Everything else in this package works against the dict this module hands
out and hands its mutations back here to persist. Reading and writing is
plain filesystem work — the only place in the whole package that touches
the network is ``llm.check_provider()``, which the user asks for by
clicking Check.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

SETTINGS_DIR = Path.home() / "MortgageWork" / "settings"
SETTINGS_FILE = SETTINGS_DIR / "settings.yaml"
_LEGACY_FILE = SETTINGS_DIR / "models.yaml"

HEADER = """\
# Mortgage Work settings.
#
# This file holds your API keys and connector credentials.
# It stays on this machine: it is NOT inside the work repo, so it is never
# committed, pushed, or sent anywhere. Edit it here or in the app's Settings
# tab — they read and write the same file.
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
#   connectors:                  # IM platform bot credentials
#     slack:
#       bot_token: xoxb-...
#       app_token: xapp-...
#     feishu:
#       app_id: cli_...
#       app_secret: ...
#     dingtalk:
#       client_id: ...
#       client_secret: ...
#       robot_code: ...
#
# Provider names are chak provider ids: openai, anthropic, google, deepseek,
# bailian, zhipu, moonshot, minimax, mistral, xai, siliconflow, volcengine,
# baidu, tencent, iflytek, azure, ollama, vllm.
"""


class SettingsError(Exception):
    """Bad input or an unreadable settings file — reported to the user as text."""


def load() -> dict:
    """The file as a dict. Missing file is not an error (nothing configured yet);
    unparsable content is — silently starting from scratch would overwrite a
    file the user was in the middle of editing by hand.

    Migration: if settings.yaml doesn't exist but models.yaml does, rename it
    in place so existing users keep their keys without manual intervention."""
    # One-time migration: models.yaml → settings.yaml
    if not SETTINGS_FILE.exists() and _LEGACY_FILE.exists():
        try:
            _LEGACY_FILE.rename(SETTINGS_FILE)
            log.info("migrated %s → %s", _LEGACY_FILE.name, SETTINGS_FILE.name)
        except OSError as exc:
            log.warning("migration failed (%s), continuing with legacy file", exc)
            # Fall back to reading the legacy file in place
            return _load_file(_LEGACY_FILE)
    if not SETTINGS_FILE.exists():
        return {"llm": {}, "embedding": {}}
    return _load_file(SETTINGS_FILE)


def _load_file(path: Path) -> dict:
    """Load and normalise a settings YAML file."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SettingsError(f"{path.name} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SettingsError(f"{path.name} must be a mapping with `llm:` and `embedding:` keys")
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
    # Ensure connectors section exists
    if not isinstance(data.get("connectors"), dict):
        data.setdefault("connectors", {})
    return data


def save(data: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        HEADER + "\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    # Owner-only, best effort. A no-op on Windows (ACLs ignore the mode), which
    # is why it isn't the security story — keeping the file off the network is.
    try:
        SETTINGS_FILE.chmod(0o600)
    except OSError:
        pass


def section(data: dict, name: str) -> dict:
    """One top-level section as a dict; missing or malformed reads as empty.

    The shared replacement for the per-domain ``_xxx_block()`` helpers — and
    what keeps sibling modules from importing each other just to peek at a
    neighbouring section."""
    block = data.get(name)
    return block if isinstance(block, dict) else {}


def key_hint(key: str) -> str:
    """What the UI shows instead of the key. The key itself never crosses the
    bridge — the webview can't leak what it was never handed."""
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:5]}…{key[-4:]}"


def clean_models(models) -> list[str]:
    """Normalise a models field: accept str or list, dedupe, drop blanks."""
    if isinstance(models, str):
        models = [models]
    out = []
    for m in models or []:
        m = str(m).strip()
        if m and m not in out:
            out.append(m)
    return out
