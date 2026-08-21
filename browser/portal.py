"""Entry page for the standalone data viewers.

Why this exists
---------------
Five viewers on five loopback ports means remembering (or digging for)
``127.0.0.1:19787``…``19791`` every time. This tiny service serves one page
that lists every viewer with its live status and a one-click link, so the
operator opens http://127.0.0.1:19786 once and goes from there.

Status
------
``/api/status`` TCP-probes each viewer port (a bare connect — no HTTP, so it
never touches the backing stores) and reports up/down per viewer; the page
polls it, so a viewer started later appears green on its own.

Usage
-----
    ./serve.sh                              # starts the portal alongside viewers
    uv run python portal.py [--port 19786]

Then open http://localhost:19786 in a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.responses import FileResponse

# This unit's own config and logging (browser/config.py also loads
# browser/.env) — the viewers keep zero imports from the parent repo.
from config import SERVICES, VIEWER_HOST
from log import setup_logging

log = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_HTML_FILE = _SCRIPT_DIR / "portal.html"

# How long a status probe may take before the viewer counts as down.
PROBE_TIMEOUT = 1.0

# One row per viewer, in display order. Mirrors serve.sh's spawn table.
# The fifth column is the backing store the viewer connects to — what an
# operator actually cares about ("which qdrant?"), unlike the viewer's own
# loopback port, which the Open link already encodes.
VIEWERS = (
    ("falkordb", "FalkorDB", "knowledge graph (Redis protocol)", SERVICES.falkordb_viewer_port, SERVICES.falkordb_uri),
    ("rqlite", "rqlite", "SQLite over Raft, incl. NL → SQL", SERVICES.rqlite_viewer_port, SERVICES.rqlite_uri),
    ("qdrant", "Qdrant", "vector store + semantic search", SERVICES.qdrant_viewer_port, SERVICES.qdrant_url),
    ("redis", "Redis", "keyspace + task queues", SERVICES.redis_viewer_port, SERVICES.redis_url),
    ("admin", "Admin", "users, plans & redemption codes (auth proxy)", SERVICES.admin_viewer_port, SERVICES.auth_service_url),
)


def _redact(url: str) -> str:
    """A URL safe to print on the portal page: any embedded password is
    dropped so .env credentials never reach the browser."""
    parts = urlsplit(url)
    if parts.username or parts.password:
        host = parts.hostname or ""
        if parts.port:
            host += f":{parts.port}"
        parts = parts._replace(netloc=host)
    return urlunsplit(parts)

app = FastAPI(title="Mortgage Browser Portal")


async def _port_up(port: int) -> bool:
    """Whether something accepts connections on the loopback viewer port.

    A connect is enough: the viewer PROCESS being up is what the entry page
    promises — probing any HTTP path would just cost an extra round trip.
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(VIEWER_HOST, port), timeout=PROBE_TIMEOUT
        )
        writer.close()
        await writer.wait_closed()
        return True
    except OSError:
        return False
    except asyncio.TimeoutError:
        return False


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_HTML_FILE)


@app.get("/api/status")
async def status() -> dict:
    """Per-viewer status for the entry page: configured (store present in
    browser/.env) and up (its loopback port accepts connections right now)."""
    up = dict(zip((v[0] for v in VIEWERS),
                  await asyncio.gather(*(_port_up(v[3]) for v in VIEWERS))))
    return {
        "viewers": [
            {
                "name": name,
                "label": label,
                "desc": desc,
                "port": port,
                "url": f"http://{VIEWER_HOST}:{port}",
                "target": _redact(target),
                "configured": SERVICES.configured(name),
                "up": up[name],
            }
            for name, label, desc, port, target in VIEWERS
        ],
        "portal_port": SERVICES.portal_port,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=VIEWER_HOST)
    parser.add_argument("--port", type=int, default=SERVICES.portal_port)
    args = parser.parse_args()

    import uvicorn

    setup_logging()
    log.info("Portal → http://%s:%s", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
