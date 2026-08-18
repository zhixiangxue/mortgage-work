"""Centralized **infrastructure** configuration for Mortgage Work.

Why this exists
---------------
Every infra endpoint the app talks to — the data stores (rqlite / FalkorDB /
Qdrant), the local viewer servers we embed as iframes, the auth service — is
defined here, sourced from a single ``.env`` at the project root. Nothing
hardcodes a URI or port anywhere else, so moving from local dev to the cloud
deployment is a one-file change instead of a hunt through scripts.

Scope: endpoints and ports only. **Credentials do not ship in the release** —
RAG/KG and web-fetching keys arrive with the login session (see
``runtime_services.py``); the ``.env`` values below are the dev fallback.
Identity (user_id, user_name, work_repo_url) lives in ``user.py``, not here.

Usage
-----
    from config import SERVICES
    SERVICES.rqlite_uri            # data store the viewer connects to
    SERVICES.rqlite_viewer_port    # local port the viewer HTTP server listens on
    SERVICES.viewer_url("rqlite")  # http://127.0.0.1:<port> for the iframe/src
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

# Loopback for the locally-spawned viewer servers. They only ever serve the
# desktop app, so bind to localhost — never expose the browsers on the network.
VIEWER_HOST = "127.0.0.1"


def _int_env(name: str, default: int) -> int:
    """int from .env that can never crash the boot: a missing OR malformed
    value (empty, non-numeric) falls back to the default. A typo in the
    dev-only viewer block must never take the app down at import time."""
    try:
        return int(str(os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def _redis_url_from_env() -> str:
    """Assemble a redis:// URL from discrete .env parts.

    A full ``REDIS_URL`` wins when set; otherwise we build one from the
    HOST/PORT/DB/PASSWORD pieces (the shape the deployment configs ship). This
    keeps the .env readable — the operator sets host+port, not a URL — while
    the viewer only ever deals with a single URL.

    Returns "" when neither shape is present: redis is a dev/debug viewer
    backend, and "not configured" must stay distinguishable from "configured
    to point at localhost" so app.py can skip spawning its viewer silently.
    """
    explicit = os.environ.get("REDIS_URL")
    if explicit:
        return explicit
    if not os.environ.get("REDIS_HOST"):
        return ""
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    db = os.environ.get("REDIS_DB", "0")
    password = os.environ.get("REDIS_PASSWORD", "")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/{db}"


@dataclass(frozen=True)
class Services:
    """Typed view over the infra ``.env``. App-critical fields (auth URL,
    agent port) keep localhost defaults so the app boots with an empty .env;
    the dev-only viewer data stores default to "" (not configured) — the app
    must start just as happily when the whole viewer block is absent. User
    identity is NOT here — see ``user.py``."""

    # ── Data stores the viewers connect to ("" = viewer block not in .env) ──
    rqlite_uri: str
    falkordb_uri: str
    qdrant_url: str
    redis_url: str

    # ── Local ports for the viewer HTTP servers app.py spawns ──
    falkordb_viewer_port: int
    rqlite_viewer_port: int
    qdrant_viewer_port: int
    redis_viewer_port: int

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
            rqlite_uri=os.environ.get("RQLITE_URI", ""),
            falkordb_uri=os.environ.get("FALKORDB_URI", ""),
            qdrant_url=os.environ.get("QDRANT_URL", ""),
            redis_url=_redis_url_from_env(),
            # One consecutive, out-of-the-way block (19787–19791) so the
            # locally-spawned viewers/agent never collide with common ports.
            falkordb_viewer_port=_int_env("FALKORDB_VIEWER_PORT", 19787),
            rqlite_viewer_port=_int_env("RQLITE_VIEWER_PORT", 19788),
            qdrant_viewer_port=_int_env("QDRANT_VIEWER_PORT", 19789),
            redis_viewer_port=_int_env("REDIS_VIEWER_PORT", 19790),
            agent_port=_int_env("AGENT_PORT", 19791),
            rag_service_url=os.environ.get("RAG_SERVICE_URL", "http://localhost:8000"),
            rag_api_key=os.environ.get("RAG_API_KEY", ""),
            kg_service_url=os.environ.get("KG_SERVICE_URL", "http://localhost:8001"),
            kg_api_key=os.environ.get("KG_API_KEY", ""),
            auth_service_url=os.environ.get("AUTH_SERVICE_URL", "http://127.0.0.1:8700"),
        )

    def viewer_configured(self, name: str) -> bool:
        """Whether the data store behind a viewer is present in .env.

        The viewers are a dev/debug surface: when their block is absent the
        app must boot unchanged — app.py skips spawning them and the frontend
        plates their iframes instead of probing dead ports."""
        stores = {
            "falkordb": self.falkordb_uri,
            "rqlite": self.rqlite_uri,
            "qdrant": self.qdrant_url,
            "redis": self.redis_url,
        }
        return bool(str(stores.get(name, "")).strip())

    def viewer_url(self, name: str) -> str:
        """Loopback URL the frontend iframe points at for a given viewer."""
        ports = {
            "falkordb": self.falkordb_viewer_port,
            "rqlite": self.rqlite_viewer_port,
            "qdrant": self.qdrant_viewer_port,
            "redis": self.redis_viewer_port,
        }
        return f"http://{VIEWER_HOST}:{ports[name]}"

    def agent_ws_url(self) -> str:
        """WebSocket endpoint of the local agent service (chat)."""
        return f"ws://{VIEWER_HOST}:{self.agent_port}/ws"

    def clerk_sse_url(self) -> str:
        """SSE endpoint of the local agent service (clerk status)."""
        return f"http://{VIEWER_HOST}:{self.agent_port}/clerk/stream"


SERVICES = Services.from_env()
