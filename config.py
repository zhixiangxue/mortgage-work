"""Centralized service configuration for Mortgage Work.

Why this exists
---------------
Every infra endpoint the app talks to — the data stores (rqlite / FalkorDB /
Qdrant), the local viewer servers we embed as iframes, and the remote worker
supervisor — is defined here, sourced from a single ``.env`` at the project
root. Nothing hardcodes a URI or port anywhere else, so moving from local dev
to the cloud deployment is a one-file change instead of a hunt through scripts.

Usage
-----
    from config import SERVICES
    SERVICES.rqlite_uri            # data store the viewer connects to
    SERVICES.rqlite_viewer_port    # local port the viewer HTTP server listens on
    SERVICES.viewer_url("rqlite")  # http://127.0.0.1:<port> for the iframe/src
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# The single source of connection values. Kept out of version control (.env is
# gitignored); .env.example documents the shape.
load_dotenv(BASE_DIR / ".env")

# Loopback for the locally-spawned viewer servers. They only ever serve the
# desktop app, so bind to localhost — never expose the browsers on the network.
VIEWER_HOST = "127.0.0.1"


def _redis_url_from_env() -> str:
    """Assemble a redis:// URL from discrete .env parts.

    A full ``REDIS_URL`` wins when set; otherwise we build one from the
    HOST/PORT/DB/PASSWORD pieces (the shape the deployment configs ship). This
    keeps the .env readable — the operator sets host+port, not a URL — while
    the viewer only ever deals with a single URL.
    """
    explicit = os.environ.get("REDIS_URL")
    if explicit:
        return explicit
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    db = os.environ.get("REDIS_DB", "0")
    password = os.environ.get("REDIS_PASSWORD", "")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/{db}"


@dataclass(frozen=True)
class Services:
    """Typed view over the service ``.env``. All fields have sane local-dev
    defaults so the app still boots with an empty .env (pointing at localhost
    containers)."""

    # ── Data stores the viewers connect to (may be local or cloud) ──
    rqlite_uri: str
    falkordb_uri: str
    qdrant_url: str
    redis_url: str

    # ── Remote worker supervision over supervisord's XML-RPC interface ──
    supervisor_url: str

    # ── Local ports for the viewer HTTP servers app.py spawns ──
    falkordb_viewer_port: int
    rqlite_viewer_port: int
    qdrant_viewer_port: int
    redis_viewer_port: int

    @classmethod
    def from_env(cls) -> "Services":
        return cls(
            rqlite_uri=os.environ.get("RQLITE_URI", "http://localhost:4001"),
            falkordb_uri=os.environ.get("FALKORDB_URI", "falkordb://localhost:6379"),
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            redis_url=_redis_url_from_env(),
            supervisor_url=os.environ.get("SUPERVISOR_URL", "http://localhost:9001/RPC2"),
            falkordb_viewer_port=int(os.environ.get("FALKORDB_VIEWER_PORT", "8787")),
            rqlite_viewer_port=int(os.environ.get("RQLITE_VIEWER_PORT", "9090")),
            qdrant_viewer_port=int(os.environ.get("QDRANT_VIEWER_PORT", "8789")),
            redis_viewer_port=int(os.environ.get("REDIS_VIEWER_PORT", "8790")),
        )

    def viewer_url(self, name: str) -> str:
        """Loopback URL the frontend iframe points at for a given viewer."""
        ports = {
            "falkordb": self.falkordb_viewer_port,
            "rqlite": self.rqlite_viewer_port,
            "qdrant": self.qdrant_viewer_port,
            "redis": self.redis_viewer_port,
        }
        return f"http://{VIEWER_HOST}:{ports[name]}"


SERVICES = Services.from_env()
