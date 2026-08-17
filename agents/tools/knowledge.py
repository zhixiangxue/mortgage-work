"""Shared knowledge-base resolution for the RAG and KG tools.

A query turn fans out over every enabled KB: the user's own (personal,
read-write) plus any shared mounts (other accounts, read-only). Mounts are
configured by email in settings.yaml; the storage name is derived locally
with the same deterministic formula the auth service uses, so no server
round-trip is needed to resolve someone else's dataset/graph.

Read/write separation is structural, not enforced: the indexer only ever
writes the logged-in user's own storage, and these tools only read.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from model_settings import read_kb_config
from user import current_user, user_id_from_email

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class KB:
    """One knowledge base a tool should query."""

    label: str        # display name for result sections ("Personal" / email)
    storage_id: str   # dataset id (RAG) / graph name (KG) — same value
    personal: bool    # per-turn scope filters apply to personal only


def enabled_knowledge_bases() -> list[KB]:
    """The KBs the agent should query, in precedence order: personal first
    (its results lead the output), then each enabled shared mount.

    Degrades to personal-only when the config can't be read — knowledge is
    the product, so a broken settings file must turn everything ON, never
    silently off. Mounting one's own email is skipped while personal is on:
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
    me = (user.email or "").strip().lower()
    for entry in config.get("shared") or []:
        if not entry.get("enabled", True):
            continue
        email = str(entry.get("email") or "").strip().lower()
        if not email:
            continue
        if email == me and config.get("personal", True):
            continue  # same storage as personal — would double every hit
        kbs.append(KB(label=email, storage_id=user_id_from_email(email),
                      personal=False))
    return kbs
