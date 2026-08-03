"""Local read-only Redis keyspace + task-queue browser.

Why this exists
---------------
Redis backs the dramatiq task queues (and assorted caches). ``redis-cli`` is
fine for one-off pokes, but watching queue depth, peeking at what's enqueued,
and inspecting TTLs across a live keyspace is tedious there. This tool serves a
small web UI that SCANs the keyspace by pattern, shows each key's type / TTL /
size (a list's size IS its queue depth), and renders a selected key's value
according to its Redis type.

Safety
------
Strictly read-only. Every endpoint issues only non-mutating commands
(SCAN / TYPE / TTL / LRANGE / HSCAN / SSCAN / ZRANGE / XREVRANGE / GET /
MEMORY USAGE). There is deliberately no command console — nothing here can
FLUSH, DEL, or otherwise change the store, so it's safe to point at prod.

Connection
----------
The redis URL comes from the centralized config (assembled from
REDIS_HOST/PORT/DB/PASSWORD in .env) and can be overridden with ``--url``::

    uv run python browser/redis_viewer.py
    uv run python browser/redis_viewer.py --url redis://:pw@host:6380/0

Usage
-----
    uv run python browser/redis_viewer.py [--url redis://host:6380/0] [--port 8790]

Then open http://localhost:8790 in a browser.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from redis.asyncio import Redis

# Centralized service config lives one level up (mortgage-work/config.py); make it
# importable whether this viewer is run as a script or spawned by app.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import SERVICES  # noqa: E402
from log import setup_logging  # noqa: E402

log = logging.getLogger(__name__)

# ── Project paths ──

_SCRIPT_DIR = Path(__file__).resolve().parent
_HTML_FILE = _SCRIPT_DIR / "redis.html"

# Redis connection URL; configured from ``--url`` in ``main``. Module default
# keeps ad-hoc imports working.
REDIS_URL = SERVICES.redis_url

# Hard cap on a single command round trip so a pathological read surfaces as an
# error instead of hanging the UI (same rationale as the other viewers).
COMMAND_TIMEOUT = 15.0

# One cached client per DB index. redis-py's async client pools connections
# internally and is safe to share; keying by DB index lets the UI switch
# databases on the fly without tearing anything down — each DB keeps its own
# pool rather than issuing a stateful SELECT on a shared connection.
_clients: dict[int, Redis] = {}


def _url_with_db(db: int) -> str:
    """The configured URL with its DB path component swapped to ``db``."""
    return urlunparse(urlparse(REDIS_URL)._replace(path=f"/{db}"))


def _redis(db: int | None = None) -> Redis:
    """Cached async client for one DB index (defaults to the configured DB)."""
    if db is None:
        db = _db_num()
    if db not in _clients:
        _clients[db] = Redis.from_url(
            _url_with_db(db),
            socket_connect_timeout=COMMAND_TIMEOUT,
            socket_timeout=COMMAND_TIMEOUT,
        )
    return _clients[db]


def _dec(value: Any) -> Any:
    """Decode a Redis byte payload to text for JSON transport.

    Queue payloads are often msgpack/pickle/JSON blobs, so we never assume
    clean UTF-8: decode with ``replace`` to keep binary values viewable (bad
    bytes show as U+FFFD) instead of failing the whole request.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _db_num() -> int:
    """The numeric DB index from the configured URL (redis://host:port/<db>)."""
    path = urlparse(REDIS_URL).path.strip("/")
    return int(path) if path.isdigit() else 0


def _display_url(url: str) -> str:
    """Mask the password so the URL is safe to echo to the UI/logs."""
    parsed = urlparse(url)
    if parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        netloc = f"{parsed.username or ''}:***@{host}"
        parsed = parsed._replace(netloc=netloc)
    return urlunparse(parsed)


# Per-type command that reports a key's "size": list length is queue depth,
# string length is bytes, collections report their cardinality.
_SIZE_CMD = {
    "string": "strlen",
    "list": "llen",
    "set": "scard",
    "zset": "zcard",
    "hash": "hlen",
    "stream": "xlen",
}


def _err(message: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=code)


# ── FastAPI app ──

app = FastAPI(title="Redis Viewer", docs_url=None, redoc_url=None)


@app.get("/")
async def index() -> FileResponse:
    # charset explicit — without it some browsers fall back to the OS
    # codepage (GBK on zh-CN Windows) and UTF-8 text renders as mojibake.
    return FileResponse(_HTML_FILE, media_type="text/html; charset=utf-8")


@app.get("/api/config")
async def api_config() -> JSONResponse:
    """Expose the active connection + how many DBs exist so the UI can render a
    database switcher. ``CONFIG GET databases`` may be disabled on locked-down
    deployments, so fall back to redis's default of 16."""
    parsed = urlparse(REDIS_URL)
    databases = 16
    try:
        cfg = await _redis().config_get("databases")
        databases = int(cfg.get("databases", 16))
    except Exception:  # noqa: BLE001 — CONFIG disabled or unreachable; default stands
        databases = 16
    return JSONResponse(
        {
            "url": _display_url(REDIS_URL),
            "db": _db_num(),
            "databases": databases,
            "secured": bool(parsed.password),
        }
    )


@app.get("/api/overview")
async def api_overview(db: int | None = None) -> JSONResponse:
    """Server + keyspace snapshot for the top panel (health at a glance)."""
    r = _redis(db)
    try:
        info = await r.info()
        dbsize = await r.dbsize()
    except Exception as exc:  # noqa: BLE001 — surface any connection error to UI
        return _err(f"redis error: {exc}", code=502)
    # INFO keyspace lines come back as {"db0": {"keys": N, "expires": M, ...}}.
    keyspace = {
        name: {"keys": stats.get("keys", 0), "expires": stats.get("expires", 0)}
        for name, stats in info.items()
        if name.startswith("db") and isinstance(stats, dict)
    }
    return JSONResponse(
        {
            "dbsize": dbsize,
            "server": {
                "redis_version": info.get("redis_version"),
                "uptime_seconds": info.get("uptime_in_seconds"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "maxmemory_human": info.get("maxmemory_human") or "∞",
            },
            "keyspace": keyspace,
        }
    )


@app.get("/api/keys")
async def api_keys(
    pattern: str = "*", cursor: int = 0, count: int = 200, db: int | None = None
) -> JSONResponse:
    """One SCAN batch: keys matching ``pattern`` with type / TTL / size.

    SCAN is cursor-based and non-blocking, so huge keyspaces page cleanly (the
    UI passes the returned cursor back for "load more"). Type/TTL/size are
    gathered with pipelines to keep each batch to a few round trips.
    """
    count = max(10, min(count, 1000))
    r = _redis(db)
    try:
        next_cursor, raw_keys = await r.scan(cursor=cursor, match=pattern, count=count)
        if raw_keys:
            # First pass: TYPE + TTL (neither needs to know the type up front).
            pipe = r.pipeline(transaction=False)
            for k in raw_keys:
                pipe.type(k)
                pipe.ttl(k)
            meta = await pipe.execute()
            types = [_dec(meta[i]) for i in range(0, len(meta), 2)]
            ttls = [meta[i] for i in range(1, len(meta), 2)]
            # Second pass: the per-type size command now that types are known.
            size_pipe = r.pipeline(transaction=False)
            for k, t in zip(raw_keys, types):
                cmd = _SIZE_CMD.get(t)
                getattr(size_pipe, cmd)(k) if cmd else size_pipe.exists(k)
            sizes = await size_pipe.execute()
        else:
            types, ttls, sizes = [], [], []
    except Exception as exc:  # noqa: BLE001
        return _err(f"redis error: {exc}", code=502)

    keys = []
    for k, t, ttl, size in zip(raw_keys, types, ttls, sizes):
        keys.append(
            {
                "name": _dec(k),
                "type": t,
                # -1 = no expiry (persistent), -2 = already gone; both render
                # as "no TTL" in the UI, so normalize to null.
                "ttl": ttl if isinstance(ttl, int) and ttl >= 0 else None,
                "size": size,
            }
        )
    keys.sort(key=lambda x: x["name"].lower())
    return JSONResponse({"keys": keys, "cursor": next_cursor, "pattern": pattern})


async def _memory(r: Redis, name: str) -> int | None:
    """Best-effort MEMORY USAGE; not all deployments allow the command."""
    try:
        return await r.memory_usage(name)
    except Exception:  # noqa: BLE001 — purely informational
        return None


@app.get("/api/key")
async def api_key(
    name: str, limit: int = 100, offset: int = 0, db: int | None = None
) -> JSONResponse:
    """Inspect one key: its type, TTL, size and a type-appropriate value view.

    list / zset support real offset+limit paging (browse deep into a queue);
    hash / set / stream show the first ``limit`` entries with a ``truncated``
    flag, which is plenty for inspection without a heavy full read.
    """
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    r = _redis(db)
    try:
        ktype = _dec(await r.type(name))
        if ktype == "none":
            return _err(f"key not found: {name}", code=404)
        ttl = await r.ttl(name)
        size_cmd = _SIZE_CMD.get(ktype)
        total = await getattr(r, size_cmd)(name) if size_cmd else 0
        view = await _build_view(r, name, ktype, total, limit, offset)
    except Exception as exc:  # noqa: BLE001
        return _err(f"redis error: {exc}", code=502)
    return JSONResponse(
        {
            "name": name,
            "type": ktype,
            "ttl": ttl if isinstance(ttl, int) and ttl >= 0 else None,
            "total": total,
            "memory": await _memory(r, name),
            "view": view,
        }
    )


async def _build_view(
    r: Redis, name: str, ktype: str, total: int, limit: int, offset: int
) -> dict[str, Any]:
    """Render a key's value into a JSON shape the frontend can grid, keyed by
    ``kind`` so the UI picks the right layout."""
    if ktype == "string":
        return {"kind": "string", "value": _dec(await r.get(name))}

    if ktype == "list":
        raw = await r.lrange(name, offset, offset + limit - 1)
        rows = [{"i": offset + i, "value": _dec(v)} for i, v in enumerate(raw)]
        return {"kind": "list", "offset": offset, "limit": limit, "rows": rows}

    if ktype == "zset":
        raw = await r.zrange(name, offset, offset + limit - 1, withscores=True)
        rows = [{"member": _dec(m), "score": s} for m, s in raw]
        return {"kind": "zset", "offset": offset, "limit": limit, "rows": rows}

    if ktype == "hash":
        # HSCAN one batch keeps a huge hash from being pulled whole; the pairs
        # come back flat [f1, v1, f2, v2, ...].
        _cur, flat = await r.hscan(name, cursor=0, count=limit)
        items = list(flat.items())[:limit]
        rows = [{"field": _dec(f), "value": _dec(v)} for f, v in items]
        return {"kind": "hash", "rows": rows, "truncated": len(rows) < total}

    if ktype == "set":
        _cur, members = await r.sscan(name, cursor=0, count=limit)
        rows = [_dec(m) for m in members[:limit]]
        return {"kind": "set", "rows": rows, "truncated": len(rows) < total}

    if ktype == "stream":
        # Newest entries first — that's what matters when watching a live queue.
        entries = await r.xrevrange(name, count=limit)
        rows = [
            {"id": _dec(eid), "fields": {_dec(k): _dec(v) for k, v in fields.items()}}
            for eid, fields in entries
        ]
        return {"kind": "stream", "rows": rows, "truncated": len(rows) < total}

    return {"kind": "unknown", "value": None}


def main() -> None:
    global REDIS_URL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=REDIS_URL,
        help=f"redis URL (redis://[:pw@]host:port/db); default from config: {_display_url(REDIS_URL)}",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=SERVICES.redis_viewer_port)
    args = parser.parse_args()

    REDIS_URL = args.url

    import uvicorn

    setup_logging()
    log.info("Redis Viewer → http://%s:%s", args.host, args.port)
    log.info("Connected to: %s", _display_url(REDIS_URL))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
