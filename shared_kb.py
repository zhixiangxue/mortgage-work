"""Shared knowledge-base validation for Settings → Knowledge.

Before an email can be mounted as a shared KB, its derived storage must
actually exist — otherwise anyone could "add" a typo'd or never-registered
address and get silent empty results forever. The probe is read-only on
both services and never creates anything.
"""
from __future__ import annotations

import logging

import httpx

from config import SERVICES
from integration import KgClient, RagClient
from model_settings import SettingsError
from user import user_id_from_email

log = logging.getLogger(__name__)


def check_shared_kb(email: str) -> dict:
    """Probe the derived dataset/graph for an email on both services.

    Returns existence and size for each side, so the settings UI can refuse
    a mount that has nothing to share. Missing storage is a normal answer
    (fields stay false/0); an unreachable service raises SettingsError,
    which the bridge turns into a user-visible error.
    """
    uid = user_id_from_email(email)
    result = {
        "email": email,
        "storage_id": uid,
        "rag_exists": False, "rag_docs": 0,
        "kg_exists": False, "kg_nodes": 0,
    }
    try:
        rag = RagClient(SERVICES.rag_service_url, SERVICES.rag_api_key, uid)
        if rag.dataset_info() is not None:
            result["rag_exists"] = True
            result["rag_docs"] = len(rag.list_documents())
        kg = KgClient(SERVICES.kg_service_url, SERVICES.kg_api_key, uid)
        info = kg.graph_info()
        if info is not None:
            result["kg_exists"] = True
            result["kg_nodes"] = int(info.get("node_count") or 0)
    except (httpx.HTTPError, RuntimeError) as exc:
        # Network failure, not "no knowledge base" — the UI must tell the
        # two apart or a flaky service looks like a missing colleague.
        log.warning("shared kb check failed for %s: %s", email, exc)
        raise SettingsError(f"knowledge service unreachable: {exc}") from exc
    log.info("shared kb check · %s → %s", email, result)
    return result
