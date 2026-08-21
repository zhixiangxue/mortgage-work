"""Admin viewer — users, plans, redemption codes and app releases on the
auth service.

Why this exists
---------------
Plan changes and code minting live behind the auth service's ``/admin/*``
endpoints, which demand an ``X-Admin-Token`` header. Handing that token to a
browser page is out of the question, so this viewer acts as a loopback
proxy: the page only ever talks to ``127.0.0.1:19791``, and this process
attaches the token when forwarding. The token never enters a browser and
the server's CORS whitelist stays untouched.

Like every viewer here it is an independent unit — own config via
``browser/.env`` (AUTH_SERVICE_URL + ADMIN_TOKEN), zero imports from the
parent repo. serve.sh starts it only when AUTH_SERVICE_URL is configured.

Usage
-----
    ./serve.sh                          # starts it alongside the other viewers
    uv run python admin.py [--port 19791]

Then open http://localhost:19791 in a browser.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import SERVICES, VIEWER_HOST
from log import setup_logging

log = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_HTML_FILE = _SCRIPT_DIR / "admin.html"

# The auth service answers fast (local SQLite); don't let a hung forward
# pile up behind the page's button clicks.
FORWARD_TIMEOUT = 15.0

app = FastAPI(title="Mortgage Admin Viewer")


async def _forward(method: str, path: str, body: dict | None = None) -> JSONResponse:
    """Proxy one call to the auth service's /admin API with ADMIN_TOKEN
    attached, passing status and JSON body straight back to the page."""
    base = SERVICES.auth_service_url.rstrip("/")
    if not base:
        return JSONResponse({"error": "AUTH_SERVICE_URL is not configured"},
                            status_code=503)
    headers = {"X-Admin-Token": SERVICES.admin_token} if SERVICES.admin_token else {}
    try:
        async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT) as client:
            res = await client.request(method, f"{base}{path}",
                                       json=body, headers=headers)
    except httpx.HTTPError as exc:
        return JSONResponse({"error": f"auth service unreachable: {exc}"},
                            status_code=502)
    try:
        return JSONResponse(res.json(), status_code=res.status_code)
    except ValueError:
        return JSONResponse({"error": res.text[:400]}, status_code=res.status_code)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_HTML_FILE)


@app.get("/api/users")
async def users() -> JSONResponse:
    return await _forward("GET", "/admin/users")


class PlanBody(BaseModel):
    plan: str


@app.post("/api/users/{user_id}/plan")
async def set_plan(user_id: str, body: PlanBody) -> JSONResponse:
    return await _forward("POST", f"/admin/users/{user_id}/plan",
                          {"plan": body.plan})


@app.get("/api/codes")
async def codes() -> JSONResponse:
    return await _forward("GET", "/admin/codes")


class MintBody(BaseModel):
    plan: str = "pro"
    count: int = 1


@app.post("/api/codes")
async def mint(body: MintBody) -> JSONResponse:
    return await _forward("POST", "/admin/codes",
                          {"plan": body.plan, "count": body.count})


# ── App releases — the update channel the desktop app polls ──

class ReleaseAssetBody(BaseModel):
    platform: str
    url: str
    sha256: str = ""
    size: int = 0


class ReleaseBody(BaseModel):
    version: str
    notes: str = ""
    assets: list[ReleaseAssetBody] = []


@app.get("/api/releases")
async def releases() -> JSONResponse:
    return await _forward("GET", "/admin/releases")


@app.post("/api/releases")
async def publish_release(body: ReleaseBody) -> JSONResponse:
    return await _forward("POST", "/admin/releases", body.model_dump())


@app.delete("/api/releases/{release_id}")
async def delete_release(release_id: str) -> JSONResponse:
    return await _forward("DELETE", f"/admin/releases/{release_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=VIEWER_HOST)
    parser.add_argument("--port", type=int, default=SERVICES.admin_viewer_port)
    args = parser.parse_args()

    import uvicorn

    setup_logging()
    if not SERVICES.auth_service_url:
        log.warning("AUTH_SERVICE_URL missing from browser/.env — every call "
                    "will answer 503 until it is set")
    log.info("Admin viewer → http://%s:%s (proxying %s)",
             args.host, args.port, SERVICES.auth_service_url or "<unset>")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
