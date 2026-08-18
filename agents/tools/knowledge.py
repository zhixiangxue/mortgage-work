"""Shared knowledge-base resolution for the RAG and KG tools.

A query turn fans out over every enabled KB: the user's own (personal,
read-write) plus any shared mounts (other accounts, read-only). Mounts are
configured by knowledge-base ID in settings.yaml — the ID doubles as the
RAG dataset / KG graph name, so no derivation or server round-trip is
needed to resolve someone else's storage.

Read/write separation is structural, not enforced: the indexer only ever
writes the logged-in user's own storage, and these tools only read.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from settings.knowledge import read_kb_config
from user import current_user

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class KB:
    """One knowledge base a tool should query."""

    label: str        # display name for result sections ("Personal" / KB ID)
    storage_id: str   # dataset id (RAG) / graph name (KG) — same value
    personal: bool    # per-turn scope filters apply to personal only


def enabled_knowledge_bases() -> list[KB]:
    """The KBs the agent should query, in precedence order: personal first
    (its results lead the output), then each enabled shared mount.

    Degrades to personal-only when the config can't be read — knowledge is
    the product, so a broken settings file must turn everything ON, never
    silently off. Mounting one's own ID is skipped while personal is on:
    it's the same storage and would double every result."""
    try:
        config = read_kb_config()
    except Exception:  # noqa: BLE001 — degrade, never block a query turn
        log.warning("kb config unreadable — falling back to personal only",
                    exc_info=True)
        config = {"personal": True, "shared": []}
    user = current_user()
    kbs: list[KB] = []
    if config.get("personal", True):
        kbs.append(KB(label="Personal", storage_id=user.rag_dataset_id,
                      personal=True))
    for entry in config.get("shared") or []:
        if not entry.get("enabled", True):
            continue
        kb_id = str(entry.get("id") or "").strip().lower()
        if not kb_id:
            continue
        if kb_id == user.id and config.get("personal", True):
            continue  # same storage as personal — would double every hit
        kbs.append(KB(label=kb_id, storage_id=kb_id, personal=False))
    return kbs
