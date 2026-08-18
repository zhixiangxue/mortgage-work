"""Runtime service credentials — delivered with the login session.

Release builds ship zero infrastructure secrets: the auth service embeds a
``services`` block in the session payload (see ``_services_block`` in
``server/main.py``), and this module is the single place that resolves it.
Resolution order:

1. **The stored login session** (OS keychain via ``auth.py``) — what every
   end user gets. Keys rotate server-side without an app release, and the
   server decides per user what is handed out.
2. **``.env`` fallback** — dev only: scripts and machines that talk to the
   bare stack without logging in still work, and a session from an older
   server (no ``services`` block yet) degrades instead of breaking.

Consumers must go through here instead of reading ``SERVICES.rag_*`` or
``os.getenv("FIRECRAWL_API_KEY")`` directly — a release build's .env
carries neither, and that is the point.
"""
from __future__ import annotations

import os

import auth
from config import SERVICES


def _session_services() -> dict:
    """The ``services`` block of the stored session, or {} when nobody is
    logged in (or the session predates the block)."""
    payload = auth.load_session() or {}
    svc = payload.get("services")
    return svc if isinstance(svc, dict) else {}


def _kb_entry(name: str) -> dict:
    kb = _session_services().get("kb")
    entry = kb.get(name) if isinstance(kb, dict) else None
    return entry if isinstance(entry, dict) else {}


def rag_target() -> tuple[str, str]:
    """(url, api_key) of the RAG service — session first, .env fallback."""
    entry = _kb_entry("rag")
    url = str(entry.get("url") or "").strip() or SERVICES.rag_service_url
    key = str(entry.get("api_key") or "").strip() or SERVICES.rag_api_key
    return url, key


def kg_target() -> tuple[str, str]:
    """(url, api_key) of the KG service — session first, .env fallback."""
    entry = _kb_entry("kg")
    url = str(entry.get("url") or "").strip() or SERVICES.kg_service_url
    key = str(entry.get("api_key") or "").strip() or SERVICES.kg_api_key
    return url, key


def web_keys() -> tuple[str, str]:
    """(firecrawl_key, jina_key) for the QA agent's web tool. Empty string
    means "skip that fetch layer"; both empty still leaves the local
    httpx fallback working."""
    web = _session_services().get("web")
    if not isinstance(web, dict):
        web = {}
    firecrawl = str(web.get("firecrawl") or "") or os.environ.get("FIRECRAWL_API_KEY", "")
    jina = str(web.get("jina") or "") or os.environ.get("JINA_API_KEY", "")
    return firecrawl, jina
