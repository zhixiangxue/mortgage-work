"""Settings: one YAML file on this machine, split by concern across modules.

The file itself lives at ``~/MortgageWork/settings/settings.yaml`` and holds
API keys plus connector credentials. Why a file, and why *there*:

* outside the git checkout (``~/MortgageWork/<repo>/``) — the sync engine has
  no idea it exists, so a key can't ride a commit to the remote;
* outside every service in config.py — no database, no rqlite row, no request.

Package layout — one module per section of the file:

* ``store.py``      — the only place that reads/writes the file
* ``llm.py``        — ``llm:`` chat providers
* ``embedding.py``  — ``embedding:`` providers
* ``memory.py``     — ``memory:`` pointer (which embedder/extraction model)
* ``knowledge.py``  — ``knowledge:`` personal + shared KB mounts
* ``connectors.py`` — ``connectors:`` IM platform bot credentials

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

    memory:                        # Memory — just a pointer
      enabled: true
      embedding:
        provider: openai
        model: text-embedding-3-small

    connectors:                    # IM platform bot credentials
      slack:
        bot_token: xoxb-...
        app_token: xapp-...

Provider keys are chak provider ids (``openai``, ``anthropic``, ``deepseek``,
``ollama``, …), so a configured entry maps straight onto a chak model URI:
``provider@base_url:model``. That's the whole point of the format — no
translation layer between what the user configured and what we call.

Run standalone to inspect the current file:

    uv run python -m settings
"""
from __future__ import annotations

from .store import SETTINGS_DIR, SETTINGS_FILE, SettingsError
from .llm import (check_provider, llm_entry, llm_target, read_models,
                  remove_model, remove_provider, resolve_ref,
                  reveal_models_file, save_provider)
from .embedding import (EMBEDDING_CAPABLE, EMBEDDING_MODELS,
                        embedding_target, read_embedding_providers,
                        save_embedding_provider)
from .memory import (memory_llm_ref, read_memory_config, save_memory_config,
                     save_memory_llm, set_memory_enabled)
from .knowledge import KB_MAX_SHARED, read_kb_config, save_kb_config
from .connectors import (PLATFORM_FIELDS, PLATFORM_META, PLATFORM_ORDER,
                         get_all_connector_configs, get_connector_config,
                         read_connectors, remove_connector, save_connector)

__all__ = [
    "SETTINGS_DIR", "SETTINGS_FILE", "SettingsError",
    # llm
    "check_provider", "llm_entry", "llm_target", "read_models",
    "remove_model", "remove_provider", "resolve_ref", "reveal_models_file",
    "save_provider",
    # embedding
    "EMBEDDING_CAPABLE", "EMBEDDING_MODELS", "embedding_target",
    "read_embedding_providers", "save_embedding_provider",
    # memory
    "memory_llm_ref", "read_memory_config", "save_memory_config",
    "save_memory_llm", "set_memory_enabled",
    # knowledge
    "KB_MAX_SHARED", "read_kb_config", "save_kb_config",
    # connectors
    "PLATFORM_FIELDS", "PLATFORM_META", "PLATFORM_ORDER",
    "get_all_connector_configs", "get_connector_config", "read_connectors",
    "remove_connector", "save_connector",
]
