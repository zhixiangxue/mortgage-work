"""The ``knowledge:`` section — which knowledge bases the agents query.

``knowledge:``
  ``personal: true``          — switch for the user's own KB
  ``shared:``                 — other accounts' KBs, mounted read-only
    ``- {id: ..., enabled: true}``

Shared mounts are addressed by the owner's knowledge-base ID (xxh64 of
their email, shown on their own Knowledge settings page) — never by the
email itself, so mounting a colleague's KB takes an ID they chose to
hand over, not an address someone guessed. Legacy `email:` entries keep
working: reads derive the ID, and the next save rewrites the block.
"""
from __future__ import annotations

import logging
import re

from user import user_id_from_email

from .store import SettingsError, load, save, section

log = logging.getLogger(__name__)

# A knowledge-base ID is an xxh64 hexdigest — exactly 16 lowercase hex chars.
_KB_ID_RE = re.compile(r"^[0-9a-f]{16}$")
# A ceiling, not a policy: past this the query fan-out costs more than any
# real team is worth, and it stops a fat-fingered paste from ballooning it.
KB_MAX_SHARED = 20


def read_kb_config() -> dict:
    """Which knowledge bases the agents query. Personal defaults to on; a
    missing/corrupt block degrades to that — knowledge is the product, so
    the failure mode is "everything on", never "everything silently off"."""
    block = section(load(), "knowledge")
    shared = []
    seen: set[str] = set()
    for entry in block.get("shared") or []:
        if not isinstance(entry, dict):
            continue
        kb_id = str(entry.get("id") or "").strip().lower()
        if not kb_id:
            # Legacy entry addressed by email — derive the ID so existing
            # mounts survive; the next save rewrites the block.
            email = str(entry.get("email") or "").strip().lower()
            if not email:
                continue
            kb_id = user_id_from_email(email)
        if kb_id in seen:
            continue
        seen.add(kb_id)
        shared.append({"id": kb_id, "enabled": bool(entry.get("enabled", True))})
    return {"personal": bool(block.get("personal", True)), "shared": shared}


def save_kb_config(config: dict) -> dict:
    """Whole-block write: toggles and add/remove land in one shot, so the
    front end can't race itself across separate save calls."""
    if not isinstance(config, dict):
        raise SettingsError("knowledge config must be an object")
    shared_in = config.get("shared") or []
    if not isinstance(shared_in, list):
        raise SettingsError("`shared` must be a list of knowledge base IDs")
    if len(shared_in) > KB_MAX_SHARED:
        raise SettingsError(f"at most {KB_MAX_SHARED} shared knowledge bases")
    seen: set[str] = set()
    shared = []
    for entry in shared_in:
        entry = entry if isinstance(entry, dict) else {}
        kb_id = str(entry.get("id") or "").strip().lower()
        if not kb_id:
            raise SettingsError("each shared knowledge base needs an id")
        if not _KB_ID_RE.match(kb_id):
            raise SettingsError(f"not a knowledge base ID: {kb_id}")
        if kb_id in seen:
            continue  # dedupe keeps the list honest
        seen.add(kb_id)
        shared.append({"id": kb_id, "enabled": bool(entry.get("enabled", True))})
    data = load()
    data["knowledge"] = {
        "personal": bool(config.get("personal", True)),
        "shared": shared,
    }
    save(data)
    return read_kb_config()
