"""Centralized **infrastructure** configuration for Mortgage Work.

Why this exists
---------------
Every infra endpoint the app itself talks to — the auth service, the local
agent service, the RAG/KG services — is defined here, sourced from a single
``.env`` at the project root. Nothing hardcodes a URI or port anywhere else,
so moving from local dev to the cloud deployment is a one-file change
instead of a hunt through scripts.

Scope: endpoints and ports only. **Credentials do not ship in the release** —
RAG/KG and web-fetching keys arrive with the login session (see
``runtime_services.py``); the ``.env`` values below are the dev fallback.
Identity (user_id, user_name, work_repo_url) lives in ``user.py``, not here.

The data-store viewers (browser/) are a standalone unit with their own
pyproject/.env — the app never reads their config and never spawns them,
so nothing viewer-related belongs here.

Usage
-----
    from config import SERVICES
    SERVICES.auth_service_url  # where the desktop app reaches login
    SERVICES.agent_ws_url()    # ws:// endpoint of the local agent service
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
if getattr(sys, 'frozen', False):
    # In PyInstaller frozen builds, all bundled data files live under
    # sys._MEIPASS (the _internal/ directory). BASE_DIR must point there
    # so load_dotenv finds the bundled .env instead of falling back to
    # localhost defaults.
    BASE_DIR = Path(sys._MEIPASS)

# The single source of connection values. Kept out of version control (.env is
# gitignored); .env.example documents the shape.
load_dotenv(BASE_DIR / ".env")

# The locally-spawned agent service only ever serves the desktop app, so bind
# to localhost — never expose it on the network.
LOCALHOST = "127.0.0.1"


def _int_env(name: str, default: int) -> int:
    """int from .env that can never crash the boot: a missing OR malformed
    value (empty, non-numeric) falls back to the default."""
    try:
        return int(str(os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Services:
    """Typed view over the infra ``.env``. App-critical fields (auth URL,
    agent port) keep localhost defaults so the app boots with an empty .env.
    User identity is NOT here — see ``user.py``."""

    # ── Local agent service (chat over WebSocket, spawned by app.py) ──
    agent_port: int

    # ── RAG service (vector dataset/ingest/query on :8000) ──
    # Dev fallback only: releases resolve these from the login session
    # (runtime_services.rag_target / kg_target), never from this .env.
    rag_service_url: str
    rag_api_key: str

    # ── KG service (knowledge graph on :8001) ──
    kg_service_url: str
    kg_api_key: str

    # ── Auth service (login + per-user repo provisioning, server/) ──
    auth_service_url: str

    @classmethod
    def from_env(cls) -> "Services":
        return cls(
            agent_port=_int_env("AGENT_PORT", 19791),
            rag_service_url=os.environ.get("RAG_SERVICE_URL", "http://localhost:8000"),
            rag_api_key=os.environ.get("RAG_API_KEY", ""),
            kg_service_url=os.environ.get("KG_SERVICE_URL", "http://localhost:8001"),
            kg_api_key=os.environ.get("KG_API_KEY", ""),
            auth_service_url=os.environ.get("AUTH_SERVICE_URL", "http://127.0.0.1:8700"),
        )

    def agent_ws_url(self) -> str:
        """WebSocket endpoint of the local agent service (chat)."""
        return f"ws://{LOCALHOST}:{self.agent_port}/ws"

    def clerk_sse_url(self) -> str:
        """SSE endpoint of the local agent service (clerk status)."""
        return f"http://{LOCALHOST}:{self.agent_port}/clerk/stream"


SERVICES = Services.from_env()
