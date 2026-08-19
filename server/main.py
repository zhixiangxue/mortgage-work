"""Mortgage Work auth service — the thin backend behind per-user work repos.

Responsibilities (and nothing else):

1. **Identity** — email + 6-digit code login (registration is implicit: a new
   email becomes a new user on first successful verify). Users live in a
   local SQLite file; no external auth provider.
2. **Repo provisioning** — on first login, create the user's private work
   repo on the host their region choice maps to (see ``provision.py``).
3. **Credential issuing** — return the session JWT plus a clone-ready
   ``work_repo_url`` — exactly the payload the desktop app's ``user.py``
   consumes.
4. **Service entitlement** — the session also carries the RAG/KG and web
   fetching keys the client needs (see ``_services_block``), so release
   builds ship no infrastructure secrets at all.

Run::

    uv run python server/main.py            # 127.0.0.1:8700, console mailer,
                                            # PROVISIONER=local unless set

Endpoints::

    POST /auth/request-code  {email}                 → {ok, isNew}
    POST /auth/verify        {email, code, region?}  → session payload
    GET  /auth/me            (Bearer token)          → session payload
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
# Plain str (not EmailStr): email-validator would be a dep just for a regex
# the routes already run themselves (EMAIL_RE).
from pydantic import BaseModel
import xxhash

# Allow `uv run python server/main.py` from the repo root without installing.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The server is its own deployment unit, so it carries its own .env —
# mail provider, AUTH_HOST/PORT, provisioning credentials all live in
# server/.env, separate from the desktop app's root .env (which only holds
# the client-side AUTH_SERVICE_URL). Real env vars still win: load_dotenv
# never overrides what the process already has.
load_dotenv(Path(__file__).resolve().parent / ".env")

from mailer import send_code  # noqa: E402
from provision import ProvisioningError, provisioner_for  # noqa: E402

log = logging.getLogger("auth")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s · %(message)s")

# ── Config ──

DATA_DIR = os.environ.get("AUTH_DATA_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "auth.db")

CODE_TTL_SECS = 10 * 60      # a code dies ten minutes after it was sent
CODE_RESEND_GAP_SECS = 30    # "send again" mashes collapse into one mail
SESSION_TTL_SECS = 30 * 24 * 3600  # the app session — refreshed on every verify/me

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REGIONS = {"cn", "intl"}


def _secret() -> str:
    """HMAC key for session tokens. Env wins; otherwise a generated key is
    persisted in the data dir so tokens survive server restarts (a fresh
    random key per boot would log everyone out on every redeploy)."""
    env = os.environ.get("AUTH_SECRET", "")
    if env:
        return env
    path = os.path.join(DATA_DIR, ".secret")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = secrets.token_urlsafe(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        return key


SECRET = _secret()

# ── SQLite ──

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    email      TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    region     TEXT NOT NULL,
    repo_url   TEXT NOT NULL,
    git_token  TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS codes (
    email      TEXT PRIMARY KEY,
    code       TEXT NOT NULL,
    expires_at REAL NOT NULL,
    sent_at    REAL NOT NULL
);
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ── Session tokens — hand-rolled HS256 JWT (no dep for ~25 lines) ──


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload: dict) -> str:
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    sig = hmac.new(SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(sig)}"


def _verify(token: str) -> dict | None:
    """Payload if the signature is ours and the token hasn't expired."""
    try:
        head, body, sig = token.split(".")
        expect = hmac.new(SECRET.encode(), f"{head}.{body}".encode(),
                          hashlib.sha256).digest()
        pad = lambda s: s + "=" * (-len(s) % 4)
        if not hmac.compare_digest(base64.urlsafe_b64decode(pad(sig)), expect):
            return None
        payload = json.loads(base64.urlsafe_b64decode(pad(body)))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ── User helpers ──


def _user_id(email: str) -> str:
    """Deterministic user id: xxh64 of the canonical email, hex-encoded.
    Same email → same id everywhere (repo name, RAG dataset, KG graph), so a
    re-provision or a rebuilt DB never invents a second identity; different
    emails collide with ~2^-64 odds, which we take. Canonical form is
    lower+strip — the routes lowercase already, but the id must not depend
    on the caller's hygiene.

    MUST stay in lockstep with ``user.user_id_from_email`` in the desktop
    app — that copy exists only to migrate legacy shared-KB settings that
    were addressed by email."""
    return xxhash.xxh64(email.strip().lower().encode("utf-8")).hexdigest()


def _name_from_email(email: str) -> str:
    local = email.split("@", 1)[0]
    return re.sub(r"[._\-]+", " ", local).strip().title() or local


def _services_block() -> dict:
    """Infrastructure credentials the client needs but the release build must
    never ship — delivered with every session instead of living in the app's
    .env. Sourced from the server's own env (server/.env); an unset key comes
    through empty and the client degrades that feature (web fetching skips
    the layer, KB tools report no knowledge base)."""
    return {
        "kb": {
            "rag": {"url": os.environ.get("RAG_SERVICE_URL", ""),
                    "api_key": os.environ.get("RAG_API_KEY", "")},
            "kg": {"url": os.environ.get("KG_SERVICE_URL", ""),
                   "api_key": os.environ.get("KG_API_KEY", "")},
            # Raw knowledge stores for the user-facing Knowledge Base
            # browser: the desktop reads its own collection/graph straight
            # from Qdrant/FalkorDB (scoped to user_id on the client side).
            # Empty → the client degrades that pane to "not configured".
            "stores": {
                "qdrant": {"url": os.environ.get("QDRANT_URL", ""),
                           "api_key": os.environ.get("QDRANT_API_KEY", "")},
                "falkordb": {"uri": os.environ.get("FALKORDB_URI", "")},
            },
        },
        "web": {
            "firecrawl": os.environ.get("FIRECRAWL_API_KEY", ""),
            "jina": os.environ.get("JINA_API_KEY", ""),
        },
    }


def _session_payload(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """Everything the app needs in one blob — the shape user.py consumes.
    The ``services`` block is rebuilt on every call, so rotating a key in
    server/.env reaches clients on their next /auth/me without a release."""
    return {
        "token": _sign({"sub": row["id"], "email": row["email"],
                        "exp": time.time() + SESSION_TTL_SECS}),
        "user": {"id": row["id"], "name": row["name"],
                 "email": row["email"], "region": row["region"]},
        "work_repo_url": row["repo_url"],
        "git_token": row["git_token"],
        "services": _services_block(),
    }


# ── API ──

# /docs and /openapi.json describe every route of an auth service — treat
# them as an admin surface. When DOCS_TOKEN is set both need ?token=<value>;
# unset (local dev) they stay open, the same "empty means skip" convention
# as the other keys. Same pattern as kg-service.
DOCS_TOKEN = os.environ.get("DOCS_TOKEN", "").strip()

app = FastAPI(title="Mortgage Work auth", docs_url=None, redoc_url=None)
# The desktop app calls from Python (no CORS needed), but the login flow may
# later grow a hosted web page — allow the local dev origins now, cheap.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def guard_openapi(request: Request, call_next):
    # The swagger page is checked in its own route; this closes the raw
    # schema endpoint the page fetches under the hood.
    if DOCS_TOKEN and request.url.path == "/openapi.json":
        if request.query_params.get("token") != DOCS_TOKEN:
            return HTMLResponse(status_code=403, content="403 Forbidden")
    return await call_next(request)


@app.get("/docs", include_in_schema=False)
def docs(token: str = ""):
    if DOCS_TOKEN and token != DOCS_TOKEN:
        raise HTTPException(403, "Forbidden")
    openapi_url = (f"/openapi.json?token={DOCS_TOKEN}" if DOCS_TOKEN
                   else "/openapi.json")
    return get_swagger_ui_html(openapi_url=openapi_url,
                               title="Mortgage Work auth — docs")


class RequestCodeIn(BaseModel):
    email: str


class VerifyIn(BaseModel):
    email: str
    code: str
    region: str | None = None


@app.get("/")
def health():
    return {"ok": True, "service": "mortgage-work-auth"}


@app.post("/auth/request-code")
def request_code(body: RequestCodeIn):
    email = body.email.lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "that doesn't look like an email address")
    now = time.time()
    conn = db()
    try:
        row = conn.execute("SELECT * FROM codes WHERE email = ?", (email,)).fetchone()
        if row and now - row["sent_at"] < CODE_RESEND_GAP_SECS:
            # Rapid re-click: the first mail is still on its way — pretend
            # success without spamming a second code.
            is_new = not conn.execute(
                "SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            return {"ok": True, "isNew": is_new}
        code = f"{secrets.randbelow(1_000_000):06d}"
        conn.execute(
            "INSERT INTO codes (email, code, expires_at, sent_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET code = excluded.code, "
            "expires_at = excluded.expires_at, sent_at = excluded.sent_at",
            (email, code, now + CODE_TTL_SECS, now))
        conn.commit()
        send_code(email, code)  # raises on misconfigured provider → 500 below
        is_new = not conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        return {"ok": True, "isNew": is_new}
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    finally:
        conn.close()


@app.post("/auth/verify")
def verify(body: VerifyIn):
    email = body.email.lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "that doesn't look like an email address")
    conn = db()
    try:
        row = conn.execute("SELECT * FROM codes WHERE email = ?", (email,)).fetchone()
        if not row or row["expires_at"] < time.time():
            raise HTTPException(400, "code expired — request a new one")
        if not hmac.compare_digest(row["code"], body.code.strip()):
            raise HTTPException(400, "wrong code")
        conn.execute("DELETE FROM codes WHERE email = ?", (email,))
        conn.commit()

        user_row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user_row:
            # Returning user: region was fixed at first login and stays.
            return _session_payload(conn, user_row)

        # New user — region decides where the repo lives, forever.
        region = (body.region or "").lower()
        if region not in REGIONS:
            raise HTTPException(400, "pick a region before finishing sign-up")
        uid = _user_id(email)
        name = _name_from_email(email)
        try:
            repo_url, git_token = provisioner_for(region).provision(uid, email, name)
        except ProvisioningError as exc:
            # The user did nothing wrong — give them the real reason instead
            # of a bare 500 so the app can surface it.
            raise HTTPException(500, f"couldn't set up your workspace: {exc}")
        conn.execute(
            "INSERT INTO users (id, email, name, region, repo_url, git_token, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, email, name, region, repo_url, git_token, time.time()))
        conn.commit()
        log.info("new user %s (%s) — repo: %s", uid, email, repo_url)
        user_row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _session_payload(conn, user_row)
    finally:
        conn.close()


@app.get("/auth/me")
def me(authorization: str = Header("")):
    token = authorization.removeprefix("Bearer ").strip()
    claims = _verify(token) if token else None
    if not claims:
        raise HTTPException(401, "not logged in")
    conn = db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (claims["sub"],)).fetchone()
        if not row:
            raise HTTPException(401, "unknown user")
        # Fresh token on every call so an active app never ages out.
        return _session_payload(conn, row)
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("AUTH_HOST", "127.0.0.1"),
        port=int(os.environ.get("AUTH_PORT", "9898")),
    )
