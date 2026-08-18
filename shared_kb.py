"""Shared knowledge-base validation for Settings → Knowledge.

Before a knowledge-base ID can be mounted as a shared KB, its derived
storage must actually exist — otherwise anyone could "add" a bogus ID and
get silent empty results forever. The probe is read-only on both services
and never creates anything.
"""
from __future__ import annotations

import logging
import re

import httpx

from runtime_services import kg_target, rag_target
from integration import KgClient, RagClient
from settings import SettingsError

log = logging.getLogger(__name__)

# A knowledge-base ID is an xxh64 hexdigest — exactly 16 lowercase hex chars.
_KB_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def check_shared_kb(kb_id: str) -> dict:
    """Probe the dataset/graph behind a knowledge-base ID on both services.

    Returns existence and size for each side, so the settings UI can refuse
    a mount that has nothing to share. Missing storage is a normal answer
    (fields stay false/0); an unreachable service raises SettingsError,
    which the bridge turns into a user-visible error.
    """
    kb_id = (kb_id or "").strip().lower()
    if not _KB_ID_RE.match(kb_id):
        raise SettingsError("not a knowledge base ID")
    result = {
        "id": kb_id,
        "rag_exists": False, "rag_docs": 0,
        "kg_exists": False, "kg_nodes": 0,
    }
    try:
        rag_url, rag_key = rag_target()
        rag = RagClient(rag_url, rag_key, kb_id)
        if rag.dataset_info() is not None:
            result["rag_exists"] = True
            result["rag_docs"] = len(rag.list_documents())
        kg_url, kg_key = kg_target()
        kg = KgClient(kg_url, kg_key, kb_id)
        info = kg.graph_info()
        if info is not None:
            result["kg_exists"] = True
            result["kg_nodes"] = int(info.get("node_count") or 0)
    except (httpx.HTTPError, RuntimeError) as exc:
        # Network failure, not "no knowledge base" — the UI must tell the
        # two apart or a flaky service looks like a missing colleague.
        log.warning("shared kb check failed for %s: %s", kb_id, exc)
        raise SettingsError(f"knowledge service unreachable: {exc}") from exc
    log.info("shared kb check · %s → %s", kb_id, result)
    return result
