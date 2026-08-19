"""Local rqlite table viewer with natural-language SQL execution.

Why this exists
---------------
rqlite has no comfortable built-in browser; inspecting tables through curl and
raw JSON (or ``scripts/rqlite.py`` on the CLI) is painful. This tool serves a
small web UI that lists the tables of one rqlite database, shows their schema
and paginated rows, and carries over the CLI script's flow of
"natural language -> SQL -> confirm -> execute" into the browser.

Safety
------
Table browsing endpoints only interpolate table names that were first read back
from ``sqlite_master`` (whitelist), so a crafted name can't inject SQL. The
free-form ``/api/execute`` endpoint is deliberate — it is the whole point of
the tool — but the UI gates every non-read statement behind an explicit
confirm dialog that shows the exact SQL, mirroring the CLI script.

Connection
----------
The rqlite URI is passed via ``--uri`` and defaults to ``RQLITE_URI`` from
this unit's own ``browser/.env``. Same shape as everywhere else::

    http://host:4001/kg_service   ->  base http://host:4001, db "kg_service"
    http://host:4001              ->  base only, rqlite default database

Usage
-----
    ./serve.sh                              # every configured viewer at once
    uv run python rqlite_viewer.py          # this one alone (reads browser/.env)
    uv run python rqlite_viewer.py --uri http://localhost:4001/kg_service

Then open http://localhost:19788 in a browser.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# This unit's own config and logging (browser/config.py also loads
# browser/.env); the NL→SQL model comes from LLM_URI/LLM_API_KEY there.
from config import SERVICES
from log import setup_logging

log = logging.getLogger(__name__)

# ── Project paths ──

_SCRIPT_DIR = Path(__file__).resolve().parent
_HTML_FILE = _SCRIPT_DIR / "rqlite.html"

# Base rqlite URL, optional database name, and optional basic-auth credentials;
# configured from ``--uri`` in ``main``. Module defaults keep ad-hoc imports
# working.
BASE_URL = "http://localhost:4001"
DB_NAME: str | None = None
AUTH: tuple[str, str] | None = None

# Hard cap on a single rqlite round trip so a pathological query surfaces as
# an error instead of hanging the UI (same rationale as the graph viewer).
QUERY_TIMEOUT = 30.0

# Statements whose first keyword marks them as reads → routed to /db/query.
_READ_COMMANDS = {"SELECT", "PRAGMA", "EXPLAIN"}


def _parse_uri(uri: str) -> tuple[str, str | None, tuple[str, str] | None]:
    """Split an rqlite URI into (base_url, db_name, auth) — same rules as the
    CLI, plus userinfo: ``http://user:pw@host:4001/db`` enables basic auth
    (the deployment script protects rqlite with a shared password)."""
    parsed = urlparse(uri)
    base = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 4001}"
    db = parsed.path.strip("/") or None
    auth = (parsed.username or "", parsed.password or "") if parsed.password else None
    return (base, db, auth)


def _sql_command(sql: str) -> str:
    """Return the leading SQL keyword (SELECT, INSERT, DROP, ...)."""
    parts = sql.strip().split(None, 1)
    return parts[0].upper() if parts else ""


def _is_read(sql: str) -> bool:
    return _sql_command(sql) in _READ_COMMANDS


# One shared async client; rqlite is plain HTTP so pooling is all we need.
_client = httpx.AsyncClient(timeout=QUERY_TIMEOUT)


async def _rq(sql: str) -> dict[str, Any]:
    """Run one statement against rqlite and return its single result object.

    Reads go to GET /db/query, everything else to POST /db/execute. rqlite
    wraps results in ``{"results": [...]}``; we unwrap the first entry and
    raise on transport errors so callers only handle one failure path.
    """
    params: dict[str, str] = {}
    if DB_NAME:
        params["db"] = DB_NAME
    if _is_read(sql):
        params["q"] = sql
        resp = await _client.get(f"{BASE_URL}/db/query", params=params, auth=AUTH)
    else:
        resp = await _client.post(
            f"{BASE_URL}/db/execute", params=params, json=[sql], auth=AUTH
        )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or [{}]
    return results[0]


def _rows(result: dict[str, Any]) -> list[list[Any]]:
    """rqlite omits ``values`` for empty result sets; normalize to a list."""
    return result.get("values") or []


def _err(message: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=code)


async def _table_names() -> list[str]:
    """List user tables; also serves as the whitelist for name interpolation."""
    res = await _rq(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    if "error" in res:
        raise RuntimeError(res["error"])
    return [row[0] for row in _rows(res)]


# ── Natural language → SQL (mirrors scripts/rqlite.py, plus live schema) ──

SYSTEM_PROMPT = """You are a SQL translator for rqlite (distributed SQLite).
Convert the user's natural language request into a single valid SQLite SQL statement.
Rules:
- rqlite handles CREATE TABLE IF NOT EXISTS, DROP TABLE IF EXISTS, INSERT, SELECT, UPDATE, DELETE, PRAGMA.
- For "show tables": SELECT name FROM sqlite_master WHERE type='table' ORDER BY name
- For "describe <table>" or "show columns of <table>": PRAGMA table_info(<table>)
- Output ONLY the raw SQL statement. No markdown, no backticks, no explanation.
- One statement per request.
{schema}"""

# The model comes from this unit's own browser/.env (LLM_URI/LLM_API_KEY) —
# the viewers are standalone, so they never read the desktop app's settings.


async def _schema_context() -> str:
    """Describe the live schema so the model writes SQL against real columns.

    Unlike the CLI (which translates blind), the server can afford one round
    trip per table; failures degrade to an empty context rather than blocking
    translation.
    """
    try:
        names = await _table_names()
    except Exception:  # noqa: BLE001 — schema context is best-effort
        return ""
    lines: list[str] = []
    for name in names:
        try:
            res = await _rq(f"PRAGMA table_info({name})")
            cols = ", ".join(f"{row[1]} {row[2]}".strip() for row in _rows(res))
            lines.append(f"- {name}({cols})")
        except Exception:  # noqa: BLE001
            lines.append(f"- {name}")
    if not lines:
        return ""
    return "Current database schema:\n" + "\n".join(lines)


async def _translate(nl: str, schema: str, table: str | None) -> str:
    """Natural language → SQL via chak (imported lazily: browsing must keep
    working even when no model is configured). Uses ``asend`` since chak
    refuses the sync ``send`` inside a running event loop."""
    import chak

    uri = SERVICES.llm_uri.strip()
    if not uri:
        raise RuntimeError("no LLM configured — set LLM_URI/LLM_API_KEY in browser/.env")
    context = schema
    # Requests like "show the latest 10 rows" rarely name a table; anchor the
    # model on whatever the user is currently browsing instead of letting it
    # guess one from the schema.
    if table:
        context += (
            f"\nThe user is currently browsing table '{table}'. "
            f"When the request does not explicitly name a table, it refers to this one."
        )
    prompt = SYSTEM_PROMPT.format(schema=context)
    conv = chak.Conversation(uri, api_key=SERVICES.llm_api_key, system_prompt=prompt)
    resp = await conv.asend(nl)
    return resp.content.strip()


# ── FastAPI app ──

app = FastAPI(title="rqlite Viewer", docs_url=None, redoc_url=None)


@app.get("/")
async def index() -> FileResponse:
    # charset explicit — without it some browsers fall back to the OS
    # codepage (GBK on zh-CN Windows) and UTF-8 text renders as mojibake.
    return FileResponse(_HTML_FILE, media_type="text/html; charset=utf-8")


@app.get("/api/config")
async def api_config() -> JSONResponse:
    """Expose the active connection so the UI header can render it. ``model``
    is the LLM_URI NL→SQL will use (empty when none configured)."""
    return JSONResponse(
        {
            "base": BASE_URL,
            "db": DB_NAME,
            "model": SERVICES.llm_uri.strip(),
        }
    )


@app.get("/api/tables")
async def api_tables() -> JSONResponse:
    """List tables with row counts for the left column."""
    try:
        names = await _table_names()
    except Exception as exc:  # noqa: BLE001 — surface any connection error to UI
        return _err(f"query failed: {exc}", code=502)
    tables = []
    for name in names:
        try:
            res = await _rq(f"SELECT COUNT(*) FROM {name}")
            rows = _rows(res)
            count = rows[0][0] if rows else 0
        except Exception:  # noqa: BLE001 — a broken table shouldn't hide the list
            count = None
        tables.append({"name": name, "count": count})
    return JSONResponse({"tables": tables})


@app.get("/api/table")
async def api_table(name: str, limit: int = 50, offset: int = 0) -> JSONResponse:
    """Return one table's column defs plus a page of rows.

    ``name`` is validated against sqlite_master before interpolation, and
    limit/offset are ints by FastAPI coercion, so no user text reaches SQL.
    """
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    try:
        names = await _table_names()
        if name not in names:
            return _err(f"unknown table '{name}'", code=404)
        info = await _rq(f"PRAGMA table_info({name})")
        total_res = await _rq(f"SELECT COUNT(*) FROM {name}")
        page = await _rq(f"SELECT * FROM {name} LIMIT {limit} OFFSET {offset}")
    except Exception as exc:  # noqa: BLE001
        return _err(f"query failed: {exc}", code=502)
    for res in (info, total_res, page):
        if "error" in res:
            return _err(res["error"], code=502)
    total_rows = _rows(total_res)
    columns = [
        {"name": row[1], "type": row[2], "pk": bool(row[5])} for row in _rows(info)
    ]
    return JSONResponse(
        {
            "name": name,
            "columns": columns,
            "total": total_rows[0][0] if total_rows else 0,
            "limit": limit,
            "offset": offset,
            "result": {"columns": page.get("columns") or [], "values": _rows(page)},
        }
    )


class TranslateBody(BaseModel):
    prompt: str
    # Table the user is currently browsing (optional); used only as a
    # disambiguation hint for the model.
    table: str | None = None


@app.post("/api/translate")
async def api_translate(body: TranslateBody) -> JSONResponse:
    """Natural language → SQL. Returns the SQL only; execution is a separate,
    user-confirmed step so the model can never run anything by itself."""
    nl = body.prompt.strip()
    if not nl:
        return _err("empty prompt")
    schema = await _schema_context()
    try:
        sql = await _translate(nl, schema, body.table)
    except Exception as exc:  # noqa: BLE001 — model/key failures go to the UI
        return _err(f"translation failed: {exc}", code=502)
    if not sql:
        return _err("model returned empty SQL", code=502)
    return JSONResponse({"sql": sql, "write": not _is_read(sql)})


class ExecuteBody(BaseModel):
    sql: str


@app.post("/api/execute")
async def api_execute(body: ExecuteBody) -> JSONResponse:
    """Run one statement and relay rqlite's result untouched.

    The UI is responsible for confirming writes before calling this; the
    server only classifies the statement so reads hit /db/query.
    """
    sql = body.sql.strip().rstrip(";")
    if not sql:
        return _err("empty SQL")
    try:
        res = await _rq(sql)
    except Exception as exc:  # noqa: BLE001
        return _err(f"query failed: {exc}", code=502)
    if "error" in res:
        # SQL-level errors (bad syntax, missing table) are the user's to fix —
        # report them as a normal payload, not a transport failure.
        return JSONResponse({"error_sql": res["error"], "write": not _is_read(sql)})
    payload: dict[str, Any] = {"write": not _is_read(sql)}
    if "columns" in res:
        payload["result"] = {"columns": res["columns"], "values": _rows(res)}
    else:
        payload["summary"] = {
            k: res[k] for k in ("last_insert_id", "rows_affected") if k in res
        }
    return JSONResponse(payload)


def main() -> None:
    global BASE_URL, DB_NAME, AUTH
    default_uri = SERVICES.rqlite_uri
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri",
        default=default_uri,
        help="rqlite URI (http://[user:pw@]host:4001[/db]); default from RQLITE_URI in browser/.env",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=SERVICES.rqlite_viewer_port)
    args = parser.parse_args()

    if not args.uri:
        # serve.sh never spawns a viewer without a configured store; a manual
        # run with an empty browser/.env should say why it has nothing to show.
        parser.error("no rqlite URI configured — set RQLITE_URI in browser/.env")
    if not args.uri.startswith(("http://", "https://")):
        parser.error("only rqlite http(s) URIs are supported")
    BASE_URL, DB_NAME, AUTH = _parse_uri(args.uri)

    import uvicorn

    setup_logging()
    log.info("rqlite Viewer → http://%s:%s", args.host, args.port)
    secured = " (basic auth)" if AUTH else ""
    log.info("Connected to: %s%s%s", BASE_URL, secured, f" (db: {DB_NAME})" if DB_NAME else "")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
