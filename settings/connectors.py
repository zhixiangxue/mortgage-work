"""The ``connectors:`` section — IM platform bot credentials.

Each top-level key under ``connectors:`` is a platform name (``slack``,
``feishu``, ``dingtalk``, ``wecom``); its value is the credential dict that
linc's adapter ``Config.model_validate(...)`` consumes.

Shape in settings.yaml::

    connectors:
      slack:
        bot_token: xoxb-...
        app_token: xapp-...
      feishu:
        app_id: cli_...
        app_secret: ...
      dingtalk:
        client_id: ...
        client_secret: ...
        robot_code: ...

The real key never crosses the bridge to the webview — ``read_connectors()``
reduces each to a masked hint, same pattern as ``llm.read_models()``.
"""
from __future__ import annotations

import logging
from typing import Any

from .store import SettingsError, key_hint, load, save, section

log = logging.getLogger(__name__)

# ── Platform metadata ────────────────────────────────────────────────────────
#
# Each entry defines what the UI needs to render a config form and what the
# backend validates on save.  ``fields`` mirrors the linc adapter's Config
# pydantic model — field keys must match exactly.

PLATFORM_FIELDS: dict[str, list[dict[str, Any]]] = {
    "slack": [
        {
            "key": "bot_token",
            "label": "Bot Token",
            "placeholder": "xoxb-...",
            "hint": "Bot User OAuth Token from your Slack app settings (OAuth & Permissions).",
            "required": True,
            "secret": True,
        },
        {
            "key": "app_token",
            "label": "App Token",
            "placeholder": "xapp-...",
            "hint": "App-Level Token with connections:write scope (Socket Mode).",
            "required": True,
            "secret": True,
        },
    ],
    "feishu": [
        {
            "key": "app_id",
            "label": "App ID",
            "placeholder": "cli_a1b2c3d4",
            "hint": "Found in Feishu Open Platform → your app → Credentials.",
            "required": True,
            "secret": False,
        },
        {
            "key": "app_secret",
            "label": "App Secret",
            "placeholder": "••••••••••••",
            "hint": "Found next to App ID in the same page.",
            "required": True,
            "secret": True,
        },
    ],
    "dingtalk": [
        {
            "key": "client_id",
            "label": "Client ID",
            "placeholder": "dingers...",
            "hint": "AppKey from DingTalk Open Platform → your app → Credentials & Basic Info.",
            "required": True,
            "secret": False,
        },
        {
            "key": "client_secret",
            "label": "Client Secret",
            "placeholder": "••••••••••••",
            "hint": "AppSecret from the same page.",
            "required": True,
            "secret": True,
        },
        {
            "key": "robot_code",
            "label": "Robot Code",
            "placeholder": "(defaults to Client ID)",
            "hint": "Usually the same as Client ID. Only set this if your bot has a separate robot code.",
            "required": False,
            "secret": False,
        },
    ],
    "wecom": [
        {
            "key": "bot_id",
            "label": "Bot ID",
            "placeholder": "bot-...",
            "hint": "Bot ID from WeCom developer console (企业微信开发者后台).",
            "required": True,
            "secret": False,
        },
        {
            "key": "secret",
            "label": "Bot Secret",
            "placeholder": "••••••••••••",
            "hint": "Bot secret for WebSocket authentication, from the same console page.",
            "required": True,
            "secret": True,
        },
    ],
}

# Display names and descriptions for the UI
PLATFORM_META: dict[str, dict[str, str]] = {
    "slack": {
        "name": "Slack",
        "desc": "Slack workspace bot",
    },
    "feishu": {
        "name": "Feishu Lark",
        "desc": "Feishu / Lark custom bot",
    },
    "dingtalk": {
        "name": "DingTalk",
        "desc": "DingTalk robot",
    },
    "wecom": {
        "name": "WeCom",
        "desc": "WeCom AI bot",
    },
}

# Canonical order for the UI
PLATFORM_ORDER = ["slack", "feishu", "dingtalk", "wecom"]


# ── Read ─────────────────────────────────────────────────────────────────────

def read_connectors() -> dict:
    """Everything the connector UI needs, with secrets reduced to masked hints.

    Returns a list of platform entries, each with:
      - platform: the key (slack/feishu/dingtalk)
      - name, desc: display metadata
      - fields: field definitions (with current values as masked hints)
      - configured: whether this platform has credentials saved
    """
    connectors = section(load(), "connectors")

    platforms = []
    for key in PLATFORM_ORDER:
        meta = PLATFORM_META[key]
        fields_def = PLATFORM_FIELDS[key]
        cfg = connectors.get(key) or {}
        if not isinstance(cfg, dict):
            cfg = {}

        # Build field view with masked values
        field_views = []
        has_any_key = False
        for f in fields_def:
            value = str(cfg.get(f["key"]) or "")
            field_views.append({
                "key": f["key"],
                "label": f["label"],
                "placeholder": f["placeholder"],
                "hint": f["hint"],
                "required": f["required"],
                "secret": f.get("secret", False),
                "value_hint": key_hint(value) if value else "",
                "has_value": bool(value),
            })
            if value:
                has_any_key = True

        platforms.append({
            "platform": key,
            "name": meta["name"],
            "desc": meta["desc"],
            "fields": field_views,
            "configured": has_any_key,
        })

    return {"platforms": platforms}


# ── Write ────────────────────────────────────────────────────────────────────

def save_connector(platform: str, fields: dict[str, str]) -> dict:
    """Save or update one platform's credentials.

    ``fields`` is a dict of ``{field_key: value}`` from the UI.  Empty values
    for existing fields mean "leave the secret alone" — same pattern as
    ``llm.save_provider()`` for model API keys.

    Returns the fresh ``read_connectors()`` view.
    """
    platform = (platform or "").strip().lower()
    if not platform:
        raise SettingsError("pick a platform")
    if platform not in PLATFORM_FIELDS:
        raise SettingsError(f"unknown platform: {platform}")

    fields_def = PLATFORM_FIELDS[platform]
    data = load()
    connectors = section(data, "connectors")
    existing = connectors.get(platform) or {}
    if not isinstance(existing, dict):
        existing = {}

    # Merge: new values override, empty values preserve existing
    merged = {}
    for f in fields_def:
        key = f["key"]
        new_val = (fields.get(key) or "").strip()
        if new_val:
            merged[key] = new_val
        elif key in existing:
            merged[key] = existing[key]
        # If not required and not provided, skip it
        elif f["required"]:
            raise SettingsError(f"{platform} requires {f['key']}")

    # Validate required fields have values (from new or existing)
    for f in fields_def:
        if f["required"] and not merged.get(f["key"]):
            raise SettingsError(f"{platform} requires {f['key']}")

    connectors[platform] = merged
    data["connectors"] = connectors
    save(data)
    return read_connectors()


def remove_connector(platform: str) -> dict:
    """Remove a platform's credentials entirely.

    Returns the fresh ``read_connectors()`` view.
    """
    platform = (platform or "").strip().lower()
    if not platform:
        raise SettingsError("pick a platform")
    if platform not in PLATFORM_FIELDS:
        raise SettingsError(f"unknown platform: {platform}")

    data = load()
    connectors = section(data, "connectors")
    if platform not in connectors:
        raise SettingsError(f"{platform} is not configured")

    del connectors[platform]
    data["connectors"] = connectors
    save(data)
    return read_connectors()


def get_connector_config(platform: str) -> dict[str, str] | None:
    """Return the raw credential dict for a platform, or None if not configured.

    Used by connector_service.py to build the linc config.  The real keys
    cross this boundary but never reach the webview.
    """
    cfg = section(load(), "connectors").get(platform)
    if not isinstance(cfg, dict) or not cfg:
        return None
    return dict(cfg)


def get_all_connector_configs() -> dict[str, dict[str, str]]:
    """Return all configured platform credentials.

    Used by connector_service.py to build the linc gateway config.
    """
    connectors = section(load(), "connectors")
    out = {}
    for platform in PLATFORM_ORDER:
        cfg = connectors.get(platform)
        if isinstance(cfg, dict) and cfg:
            out[platform] = dict(cfg)
    return out
