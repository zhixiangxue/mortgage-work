"""Configuration for the standalone data-viewer unit.

Why this exists
---------------
The viewers are an independent dev/debug unit — like ``server/``, they carry
their own ``pyproject.toml``, ``.env`` and launch scripts, and know nothing
about the desktop app. This module is the single place that reads
``browser/.env``: every data-store connection and every local viewer port
comes from here, nothing hardcodes a URI anywhere else.

The desktop app never reads this file and never spawns these viewers — the
app only borrows an iframe slot to display them (frontend points at the
fixed loopback ports below), so a release build ships none of this.

Usage
-----
    from config import SERVICES
    SERVICES.rqlite_uri        # data store this viewer connects to
    SERVICES.rqlite_viewer_port  # local port the viewer listens on
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# The single source of connection values. Kept out of version control
# (.env is gitignored); .env.example documents the shape. Loading it also
# publishes keys the viewers read straight from the environment —
# OPENAI_API_KEY (qdrant semantic search) among them.
load_dotenv(BASE_DIR / ".env")

# The viewers only ever serve the operator on this box, so bind to loopback —
# never expose the browsers on the network.
VIEWER_HOST = "127.0.0.1"


def _int_env(name: str, default: int) -> int:
    """int from .env that can never crash a viewer at import time: a missing
    OR malformed value (empty, non-numeric) falls back to the default."""
    try:
        return int(str(os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def _redis_url_from_env() -> str:
    """Assemble a redis:// URL from discrete .env parts.

    A full ``REDIS_URL`` wins when set; otherwise we build one from the
    HOST/PORT/DB/PASSWORD pieces (the shape the deployment configs ship).
    This keeps the .env readable — the operator sets host+port, not a URL —
    while the viewer only ever deals with a single URL.

    Returns "" when neither shape is present: "not configured" must stay
    distinguishable from "configured to point at localhost" so serve.sh can
    skip spawning this viewer silently.
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
    """Typed view over ``browser/.env``. Data stores default to "" (not
    configured) — serve.sh skips their viewers and a manual run reports why
    there is nothing to show."""

    # ── Data stores the viewers connect to ("" = not in .env) ──
    rqlite_uri: str
    falkordb_uri: str
    qdrant_url: str
    redis_url: str

    # ── Local ports for the viewer HTTP servers ──
    falkordb_viewer_port: int
    rqlite_viewer_port: int
    qdrant_viewer_port: int
    redis_viewer_port: int
    admin_viewer_port: int
    # Entry page listing the viewers with live status (always started by
    # serve.sh, even when no store is configured).
    portal_port: int

    # ── Admin viewer: auth service it proxies to ("" = viewer skipped) ──
    # The admin page never talks to the auth service directly — this viewer
    # forwards requests with ADMIN_TOKEN attached, so the token never enters
    # a browser and the server's CORS list stays untouched.
    auth_service_url: str
    admin_token: str

    # ── Optional LLM for the rqlite viewer's NL -> SQL feature ──
    # chak URI form: "provider@base_url:model" ("~" = provider default
    # endpoint), plus its API key. Empty uri disables the feature; browsing
    # keeps working either way.
    llm_uri: str
    llm_api_key: str

    @classmethod
    def from_env(cls) -> "Services":
        return cls(
            rqlite_uri=os.environ.get("RQLITE_URI", ""),
            falkordb_uri=os.environ.get("FALKORDB_URI", ""),
            qdrant_url=os.environ.get("QDRANT_URL", ""),
            redis_url=_redis_url_from_env(),
            # One consecutive, out-of-the-way block (19787–19791) so the
            # viewers never collide with common dev ports. The frontend's
            # VIEWER_DEFAULTS mirror these exact ports.
            falkordb_viewer_port=_int_env("FALKORDB_VIEWER_PORT", 19787),
            rqlite_viewer_port=_int_env("RQLITE_VIEWER_PORT", 19788),
            qdrant_viewer_port=_int_env("QDRANT_VIEWER_PORT", 19789),
            redis_viewer_port=_int_env("REDIS_VIEWER_PORT", 19790),
            admin_viewer_port=_int_env("ADMIN_VIEWER_PORT", 19791),
            # Just below the block, so the whole barge stays one range.
            portal_port=_int_env("PORTAL_PORT", 19786),
            auth_service_url=os.environ.get("AUTH_SERVICE_URL", ""),
            admin_token=os.environ.get("ADMIN_TOKEN", ""),
            llm_uri=os.environ.get("LLM_URI", ""),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
        )

    def configured(self, name: str) -> bool:
        """Whether the backing service behind a viewer is present in .env —
        serve.sh starts only configured viewers. For the admin viewer the
        "store" is the auth service itself."""
        stores = {
            "falkordb": self.falkordb_uri,
            "rqlite": self.rqlite_uri,
            "qdrant": self.qdrant_url,
            "redis": self.redis_url,
            "admin": self.auth_service_url,
        }
        return bool(str(stores.get(name, "")).strip())


SERVICES = Services.from_env()
