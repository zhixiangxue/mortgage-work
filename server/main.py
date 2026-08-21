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
5. **Plans & redeem codes** — every user carries a ``plan`` (free/pro) in
   the session payload; redeem codes are the payment-free upgrade path.
6. **App updates** — ``GET /app/latest`` tells desktop builds which release
   is current and where its installer lives (assets point at GitHub Release
   files; this service stores metadata only, never binaries).
7. **Admin surface** — ``/admin/*`` manages users, codes and releases behind
   a separate ``ADMIN_TOKEN`` credential, deliberately unrelated to the app's
   session scheme.

Run::

    uv run python server/main.py            # 127.0.0.1:9898, console mailer,
                                            # PROVISIONER=local unless set

Endpoints::

    POST /user/request-code  {email}                 → {ok, isNew}
    POST /user/verify        {email, code, region?}  → session payload
    GET  /user/me            (Bearer token)          → session payload
    GET  /user/quota         (Bearer token)          → {ok, plan, allowed}
    POST /user/redeem        (Bearer token) {code}   → session payload
    GET  /app/latest         ?platform=…             → latest release + asset
    GET  /admin/users        (X-Admin-Token)         → user list
    POST /admin/users/{id}/plan (X-Admin-Token)      → set a user's plan
    GET  /admin/codes        (X-Admin-Token)         → redeem code list
    POST /admin/codes        (X-Admin-Token)         → mint redeem codes
    GET  /admin/releases     (X-Admin-Token)         → release list
    POST /admin/releases     (X-Admin-Token)         → publish a release
    DELETE /admin/releases/{id} (X-Admin-Token)      → retire a release

The legacy ``/auth/*`` paths stay mounted as aliases so already-released
desktop builds keep working.
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
from fastapi import Depends, FastAPI, Header, HTTPException, Request
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

# Subscription tiers. Deliberately a plain set + string column: adding a
# tier is one entry here plus whatever limits the quota check grows.
PLANS = {"free", "pro"}
DEFAULT_PLAN = "free"

# Redeem codes — the payment-free upgrade path (Stripe arrives later through
# the same plan-change funnel). Uppercase alphabet without the ambiguous
# 0/O/1/I so a code read off a screen can be typed back unambiguously.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 12

# Installer flavors the desktop knows how to apply. One asset per platform
# per release; the URL points at a GitHub Release attachment — this DB keeps
# metadata, never binaries.
RELEASE_PLATFORMS = {"windows-x64", "macos-arm64", "macos-x64"}


def _version_key(version: str) -> tuple:
    """Ordering key for dotted versions: numeric parts compare numerically
    (1.10.0 > 1.9.0); a non-numeric tail (e.g. "-beta") sorts before the
    plain release of the same numbers. Never raises — an odd string just
    ranks below everything numeric."""
    parts = version.strip().lstrip("v").split(".")
    key: list = []
    for p in parts:
        num = re.match(r"^\d+", p)
        if num:
            key.append((1, int(num.group()), p[len(num.group()):].lstrip("-")))
        else:
            key.append((0, 0, p))
    return tuple(key)


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
    plan       TEXT NOT NULL DEFAULT 'free',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS codes (
    email      TEXT PRIMARY KEY,
    code       TEXT NOT NULL,
    expires_at REAL NOT NULL,
    sent_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS redeem_codes (
    code       TEXT PRIMARY KEY,
    plan       TEXT NOT NULL,
    created_at REAL NOT NULL,
    used_by    TEXT NOT NULL DEFAULT '',
    used_at    REAL
);
CREATE TABLE IF NOT EXISTS app_releases (
    id         TEXT PRIMARY KEY,
    version    TEXT UNIQUE NOT NULL,
    notes      TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS app_assets (
    id         TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES app_releases(id) ON DELETE CASCADE,
    platform   TEXT NOT NULL,
    url        TEXT NOT NULL,
    sha256     TEXT NOT NULL DEFAULT '',
    size       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(release_id, platform)
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent schema drift fixes for DBs created by older builds.

    SQLite has no versioned-migration machinery; a column-list diff before
    an ALTER is the whole trick. New installs already carry everything via
    _SCHEMA, so this only ever touches upgraded data dirs.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if cols and "plan" not in cols:
        conn.execute(f"ALTER TABLE users ADD COLUMN plan TEXT NOT NULL "
                     f"DEFAULT '{DEFAULT_PLAN}'")
        conn.commit()
        log.info("migrated users table — added plan column (default %s)",
                 DEFAULT_PLAN)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
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
                 "email": row["email"], "region": row["region"],
                 "plan": row["plan"]},
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

# Credential for the /admin/* surface. Deliberately a DIFFERENT scheme from
# the app's session JWT: an attacker who forges or steals a user session
# must not reach user management. The token lives only in server/.env and
# the operator's browser/ viewer — the desktop app never sees it. Empty
# means "local dev, skip the check", the codebase-wide convention.
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()

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


# The user domain lives under /user/*; the /auth/* paths stay mounted as
# aliases so already-released desktop builds keep working. Two decorators
# register the same handler under both names (FastAPI routes take one path).
@app.post("/auth/request-code")
@app.post("/user/request-code")
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
@app.post("/user/verify")
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


def _bearer_claims(authorization: str) -> dict:
    """Validate the session JWT from an Authorization header; 401 otherwise."""
    token = authorization.removeprefix("Bearer ").strip()
    claims = _verify(token) if token else None
    if not claims:
        raise HTTPException(401, "not logged in")
    return claims


def _user_row_or_401(conn: sqlite3.Connection, claims: dict) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (claims["sub"],)).fetchone()
    if not row:
        raise HTTPException(401, "unknown user")
    return row


@app.get("/auth/me")
@app.get("/user/me")
def me(authorization: str = Header("")):
    claims = _bearer_claims(authorization)
    conn = db()
    try:
        row = _user_row_or_401(conn, claims)
        # Fresh token on every call so an active app never ages out.
        return _session_payload(conn, row)
    finally:
        conn.close()


def _quota_verdict(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Whether this user may submit more knowledge-base documents right now.

    TODO(plans): the metering dimension is not defined yet — it may settle
    on tokens ingested, files indexed, or something else entirely. When it
    does, measure it here against the plan's limit. Until then every plan
    passes, and the client already calls this before every submit batch so
    the hook is warm.
    """
    return True


@app.get("/user/quota")
def quota(authorization: str = Header("")):
    """Pre-submit gate the client checks before every indexing batch.

    Carries the caller's CURRENT plan so a desktop whose cached session is
    stale (a mid-run downgrade) snaps back to truth at exactly the moment
    it tries to write.
    """
    claims = _bearer_claims(authorization)
    conn = db()
    try:
        row = _user_row_or_401(conn, claims)
        return {"ok": True, "plan": row["plan"],
                "allowed": _quota_verdict(conn, row)}
    finally:
        conn.close()


class RedeemIn(BaseModel):
    code: str


@app.post("/user/redeem")
def redeem(body: RedeemIn, authorization: str = Header("")):
    """Redeem an unused code: it moves the caller to the code's plan.

    The claim is one atomic UPDATE guarded by used_at IS NULL, so a code
    raced from two machines is consumed exactly once.
    """
    claims = _bearer_claims(authorization)
    code = body.code.strip().upper()
    if not code:
        raise HTTPException(400, "enter a code")
    conn = db()
    try:
        row = _user_row_or_401(conn, claims)
        entry = conn.execute(
            "SELECT * FROM redeem_codes WHERE code = ?", (code,)).fetchone()
        if entry is None:
            raise HTTPException(404, "unknown code")
        if entry["used_at"] is not None:
            raise HTTPException(400, "this code has already been used")
        if entry["plan"] not in PLANS:
            raise HTTPException(500, "code carries an unknown plan")
        claimed = conn.execute(
            "UPDATE redeem_codes SET used_by = ?, used_at = ? "
            "WHERE code = ? AND used_at IS NULL",
            (row["id"], time.time(), code)).rowcount
        if not claimed:
            raise HTTPException(400, "this code has already been used")
        conn.execute("UPDATE users SET plan = ? WHERE id = ?",
                     (entry["plan"], row["id"]))
        conn.commit()
        log.info("redeem · %s (%s) → plan %s via code %s",
                 row["id"], row["email"], entry["plan"], code)
        fresh = conn.execute(
            "SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return _session_payload(conn, fresh)
    finally:
        conn.close()


# ── App updates ──
#
# The desktop polls this to discover new builds. Deliberately public (no
# auth): it carries no user data, and an update channel must keep working
# even from a logged-out or broken session.


@app.get("/app/latest")
def app_latest(platform: str = ""):
    """Highest published release, with the caller's asset if one matches.

    ``release`` is null until the first release is published — the client
    treats that as "nothing new", never an error.
    """
    conn = db()
    try:
        rows = conn.execute(
            "SELECT id, version, notes, created_at FROM app_releases").fetchall()
        if not rows:
            return {"ok": True, "release": None}
        latest = max(rows, key=lambda r: _version_key(r["version"]))
        assets = conn.execute(
            "SELECT platform, url, sha256, size FROM app_assets "
            "WHERE release_id = ?", (latest["id"],)).fetchall()
        asset_list = [dict(a) for a in assets]
        release = {"version": latest["version"], "notes": latest["notes"],
                   "published_at": latest["created_at"], "assets": asset_list}
        if platform:
            release["asset"] = next(
                (a for a in asset_list if a["platform"] == platform), None)
        return {"ok": True, "release": release}
    finally:
        conn.close()


# ── Admin surface ──
#
# Operator-only user and redeem-code management. Auth is the ADMIN_TOKEN
# header — a separate credential scheme from the app's session JWT on
# purpose (see the ADMIN_TOKEN comment up top).

def _require_admin(x_admin_token: str = Header("")) -> None:
    if ADMIN_TOKEN and not hmac.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(403, "admin token missing or wrong")


@app.get("/admin/users")
def admin_users(_: None = Depends(_require_admin)):
    conn = db()
    try:
        rows = conn.execute(
            "SELECT id, email, name, region, plan, created_at "
            "FROM users ORDER BY created_at").fetchall()
        return {"ok": True, "users": [dict(r) for r in rows]}
    finally:
        conn.close()


class PlanIn(BaseModel):
    plan: str


@app.post("/admin/users/{user_id}/plan")
def admin_set_plan(user_id: str, body: PlanIn,
                   _: None = Depends(_require_admin)):
    plan = body.plan.strip().lower()
    if plan not in PLANS:
        raise HTTPException(400, f"unknown plan: {body.plan!r}")
    conn = db()
    try:
        row = conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "unknown user")
        conn.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
        conn.commit()
        log.info("admin · %s (%s) → plan %s", user_id, row["email"], plan)
        return {"ok": True, "id": user_id, "plan": plan}
    finally:
        conn.close()


@app.get("/admin/codes")
def admin_list_codes(_: None = Depends(_require_admin)):
    conn = db()
    try:
        # LEFT JOIN so a code redeemed by a since-deleted user still lists —
        # the page falls back to the raw user id when the email is gone.
        rows = conn.execute(
            "SELECT r.code, r.plan, r.created_at, r.used_by, r.used_at, "
            "u.email AS used_by_email FROM redeem_codes r "
            "LEFT JOIN users u ON u.id = r.used_by "
            "ORDER BY r.created_at DESC").fetchall()
        return {"ok": True, "codes": [dict(r) for r in rows]}
    finally:
        conn.close()


class MintCodesIn(BaseModel):
    plan: str = "pro"
    count: int = 1


@app.post("/admin/codes")
def admin_mint_codes(body: MintCodesIn, _: None = Depends(_require_admin)):
    plan = body.plan.strip().lower()
    if plan not in PLANS:
        raise HTTPException(400, f"unknown plan: {body.plan!r}")
    if not 1 <= body.count <= 100:
        raise HTTPException(400, "count must be between 1 and 100")
    conn = db()
    try:
        minted: list[str] = []
        now = time.time()
        while len(minted) < body.count:
            # secrets.choice is drawn per character — the full alphabet stays
            # in play, so codes keep their 32^12 (~2^60) space.
            code = "".join(secrets.choice(_CODE_ALPHABET)
                           for _ in range(_CODE_LENGTH))
            try:
                conn.execute(
                    "INSERT INTO redeem_codes (code, plan, created_at) "
                    "VALUES (?, ?, ?)", (code, plan, now))
            except sqlite3.IntegrityError:
                continue  # astronomically unlikely collision — draw again
            minted.append(code)
        conn.commit()
        log.info("admin · minted %d %s code(s)", len(minted), plan)
        return {"ok": True, "codes": minted}
    finally:
        conn.close()


# Release management — the operator publishes a build here after CI attaches
# the installers to the GitHub Release. Republishing a version replaces it
# (handy for a broken asset); DELETE retires one entirely.

class ReleaseAssetIn(BaseModel):
    platform: str
    url: str
    sha256: str = ""
    size: int = 0


class ReleaseIn(BaseModel):
    version: str
    notes: str = ""
    assets: list[ReleaseAssetIn] = []


@app.get("/admin/releases")
def admin_list_releases(_: None = Depends(_require_admin)):
    conn = db()
    try:
        rows = conn.execute(
            "SELECT id, version, notes, created_at FROM app_releases "
            "ORDER BY created_at DESC").fetchall()
        releases = []
        for r in rows:
            assets = conn.execute(
                "SELECT id, platform, url, sha256, size FROM app_assets "
                "WHERE release_id = ?", (r["id"],)).fetchall()
            entry = dict(r)
            entry["assets"] = [dict(a) for a in assets]
            releases.append(entry)
        return {"ok": True, "releases": releases}
    finally:
        conn.close()


@app.post("/admin/releases")
def admin_publish_release(body: ReleaseIn, _: None = Depends(_require_admin)):
    version = body.version.strip().lstrip("v")
    if not re.match(r"^\d+(\.\d+)*([-.][0-9A-Za-z.]+)?$", version):
        raise HTTPException(400, "version must look like 1.2.3")
    if not body.assets:
        raise HTTPException(400, "a release needs at least one asset")
    unknown = {a.platform for a in body.assets} - RELEASE_PLATFORMS
    if unknown:
        raise HTTPException(400, f"unknown platform(s): {sorted(unknown)}")
    for a in body.assets:
        if not a.url.startswith(("http://", "https://")):
            raise HTTPException(400, f"asset url must be http(s): {a.url}")
    conn = db()
    try:
        # Republish = replace: the old entry (same version) and its assets go
        # first so a fixed asset never leaves two rows claiming one version.
        old = conn.execute(
            "SELECT id FROM app_releases WHERE version = ?",
            (version,)).fetchone()
        if old:
            conn.execute("DELETE FROM app_assets WHERE release_id = ?",
                         (old["id"],))
            conn.execute("DELETE FROM app_releases WHERE id = ?",
                         (old["id"],))
        rid = secrets.token_hex(8)
        conn.execute(
            "INSERT INTO app_releases (id, version, notes, created_at) "
            "VALUES (?, ?, ?, ?)",
            (rid, version, body.notes.strip(), time.time()))
        for a in body.assets:
            conn.execute(
                "INSERT INTO app_assets (id, release_id, platform, url, "
                "sha256, size) VALUES (?, ?, ?, ?, ?, ?)",
                (secrets.token_hex(8), rid, a.platform, a.url.strip(),
                 a.sha256.strip().lower(), max(0, a.size)))
        conn.commit()
        log.info("admin · published release %s (%d asset(s))",
                 version, len(body.assets))
        return {"ok": True, "id": rid, "version": version}
    finally:
        conn.close()


@app.delete("/admin/releases/{release_id}")
def admin_delete_release(release_id: str, _: None = Depends(_require_admin)):
    conn = db()
    try:
        # Manual delete: PRAGMA foreign_keys stays off by default here, so
        # take the assets down explicitly before the release row.
        conn.execute("DELETE FROM app_assets WHERE release_id = ?",
                     (release_id,))
        gone = conn.execute(
            "DELETE FROM app_releases WHERE id = ?", (release_id,)).rowcount
        conn.commit()
        if not gone:
            raise HTTPException(404, "unknown release")
        log.info("admin · retired release %s", release_id)
        return {"ok": True, "id": release_id}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("AUTH_HOST", "127.0.0.1"),
        port=int(os.environ.get("AUTH_PORT", "9898")),
    )
