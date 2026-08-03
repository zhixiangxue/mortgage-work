"""Local Qdrant collection viewer.

Why this exists
---------------
Qdrant ships a built-in dashboard, but it lives on the store's own port and
mixes in cluster/telemetry views we don't need. This tool serves a small,
theme-matched web UI that lists the collections of one Qdrant instance, shows
each collection's vector config and payload schema, and pages through points
with their payloads — the same left-list / right-grid shape as the rqlite and
FalkorDB browsers, so all three data stores feel like one tool.

Read-only
---------
Every endpoint here only reads (GET /collections, POST .../points/scroll and
.../points/search). No delete/upsert path is exposed — inspecting vectors
should never mutate them.

Connection
----------
The Qdrant base URL is passed via ``--url`` and defaults to ``QDRANT_URL`` from
the project ``.env``. An optional API key (Qdrant Cloud / secured instances) is
read from ``QDRANT_API_KEY``.

Semantic search
---------------
The ``/api/search`` endpoint embeds the user's text with OpenAI (same model
that produced the stored vectors — ``text-embedding-3-small``, 1536-d, override
via ``EMBED_MODEL``) and runs a nearest-neighbour search. It needs
``OPENAI_API_KEY``; without it, browsing still works and the UI just hides the
search box.

Usage
-----
    uv run python browser/qdrant_viewer.py [--url http://localhost:6333] [--port 8789]

Then open http://localhost:8789 in a browser.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Centralized service config lives one level up (mortgage-work/config.py). Importing
# it also loads mortgage-work/.env, so QDRANT_URL / QDRANT_API_KEY are available.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import SERVICES  # noqa: E402
from user import current_user  # noqa: E402

# ── Project paths ──

_SCRIPT_DIR = Path(__file__).resolve().parent
_HTML_FILE = _SCRIPT_DIR / "qdrant.html"

# Base Qdrant URL and optional API key; configured from ``--url`` in ``main``.
# Module defaults keep ad-hoc imports working.
BASE_URL = "http://localhost:6333"
API_KEY: str | None = None

# The user's own collection (RAG dataset_id = user_id). The viewer still lists
# every collection on the instance, but auto-selects this one on load so the
# operator sees their data immediately.
DEFAULT_COLLECTION = current_user().rag_dataset_id

# Embedding model for semantic search. Must match the model that produced the
# collection's stored vectors, or nearest-neighbour results are meaningless.
# The project's vectors are OpenAI 1536-d; override via EMBED_MODEL if needed.
EMBED_MODEL = "text-embedding-3-small"

# Hard cap on a single Qdrant round trip so a pathological scroll surfaces as
# an error instead of hanging the UI (same rationale as the other viewers).
QUERY_TIMEOUT = 30.0

# One shared async client; Qdrant is plain HTTP/JSON so pooling is all we need.
_client = httpx.AsyncClient(timeout=QUERY_TIMEOUT)


def _headers() -> dict[str, str]:
    """Auth header for secured instances; empty for a local unauthenticated one."""
    return {"api-key": API_KEY} if API_KEY else {}


async def _get(path: str) -> dict[str, Any]:
    """GET a Qdrant endpoint and unwrap its ``{"result": ...}`` envelope."""
    resp = await _client.get(f"{BASE_URL}{path}", headers=_headers())
    resp.raise_for_status()
    return resp.json().get("result", {})


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    resp = await _client.post(f"{BASE_URL}{path}", headers=_headers(), json=body)
    resp.raise_for_status()
    return resp.json().get("result", {})


def _err(message: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=code)


def _clean_ids(values: list[str]) -> list[str]:
    """Normalize pasted doc_ids into bare, de-duplicated strings.

    These are typically copied straight out of source code, so a value can
    arrive wrapped in quotes, list brackets, or trailing whitespace
    (``["abc", 'def']``). Each value is also re-split on commas, so the endpoint
    behaves the same whether the caller pre-split the list or pasted one blob.
    Empty leftovers are dropped rather than becoming ids that match nothing.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for token in str(raw).split(","):
            token = token.strip().strip("[]()").strip().strip("\"'`").strip()
            if token and token not in seen:
                seen.add(token)
                out.append(token)
    return out


def _doc_filter(doc_ids: list[str]) -> dict[str, Any] | None:
    """Qdrant filter restricting results to the given doc_ids.

    ``match.any`` covers both the single- and multi-value cases, so one shape
    serves any list length. Returns None when nothing usable was supplied, so
    callers can omit the filter key entirely.
    """
    ids = _clean_ids(doc_ids)
    if not ids:
        return None
    return {"must": [{"key": "doc_id", "match": {"any": ids}}]}


# ── FastAPI app ──

app = FastAPI(title="Qdrant Viewer", docs_url=None, redoc_url=None)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_HTML_FILE)


@app.get("/api/config")
async def api_config() -> JSONResponse:
    """Expose the active connection so the UI header can render it, plus whether
    semantic search is available (an OpenAI key must be configured to embed).
    ``default_collection`` lets the frontend auto-select the user's own data."""
    return JSONResponse(
        {
            "url": BASE_URL,
            "secured": bool(API_KEY),
            "search": bool(os.environ.get("OPENAI_API_KEY")),
            "embed_model": EMBED_MODEL,
            "default_collection": DEFAULT_COLLECTION,
        }
    )


@app.get("/api/collections")
async def api_collections() -> JSONResponse:
    """List collections with their point counts for the left column.

    The list call is cheap; per-collection counts need one extra round trip
    each, so a collection that fails to describe still shows up (count=None)
    rather than hiding the whole list.
    """
    try:
        result = await _get("/collections")
    except Exception as exc:  # noqa: BLE001 — surface any connection error to UI
        return _err(f"query failed: {exc}", code=502)
    collections = []
    for c in result.get("collections", []):
        name = c.get("name")
        try:
            info = await _get(f"/collections/{name}")
            count = info.get("points_count")
        except Exception:  # noqa: BLE001 — a broken collection shouldn't hide the list
            count = None
        collections.append({"name": name, "count": count})
    collections.sort(key=lambda x: x["name"])
    return JSONResponse({"collections": collections})


def _vector_params(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Qdrant's vector config into rows of (name, size, distance).

    Qdrant has two shapes: a single unnamed vector ``{size, distance}`` or a
    map of named vectors ``{name: {size, distance}}``. Normalize both so the UI
    renders one code path.
    """
    vectors = (config.get("params") or {}).get("vectors") or {}
    if "size" in vectors:  # single unnamed vector
        return [{"name": "(default)", "size": vectors.get("size"), "distance": vectors.get("distance")}]
    return [
        {"name": name, "size": spec.get("size"), "distance": spec.get("distance")}
        for name, spec in vectors.items()
        if isinstance(spec, dict)
    ]


@app.get("/api/collection")
async def api_collection(name: str) -> JSONResponse:
    """Return one collection's vector params and payload schema for the header."""
    try:
        info = await _get(f"/collections/{name}")
    except Exception as exc:  # noqa: BLE001
        return _err(f"query failed: {exc}", code=502)
    config = info.get("config") or {}
    payload_schema = info.get("payload_schema") or {}
    fields = [
        {"name": field, "type": (spec or {}).get("data_type")}
        for field, spec in payload_schema.items()
    ]
    return JSONResponse(
        {
            "name": name,
            "points": info.get("points_count"),
            "status": info.get("status"),
            "vectors": _vector_params(config),
            "payload_fields": sorted(fields, key=lambda x: x["name"]),
        }
    )


class ScrollBody(BaseModel):
    name: str
    limit: int = 25
    # Opaque page cursor from the previous response (Qdrant point id or None).
    offset: Any = None
    with_vector: bool = False
    # Optional doc_id whitelist; empty means "whole collection".
    doc_ids: list[str] = []


@app.post("/api/points")
async def api_points(body: ScrollBody) -> JSONResponse:
    """Page through a collection's points via the scroll API.

    Qdrant cursors are opaque (a point id, not a numeric offset), so paging is
    strictly forward: each response carries ``next`` to fetch the following
    page. The UI keeps a cursor stack to walk back. An optional doc_id filter
    narrows the set that is paged over.
    """
    limit = max(1, min(body.limit, 200))
    payload: dict[str, Any] = {
        "limit": limit,
        "with_payload": True,
        "with_vector": body.with_vector,
    }
    if body.offset is not None:
        payload["offset"] = body.offset
    doc_filter = _doc_filter(body.doc_ids)
    if doc_filter:
        payload["filter"] = doc_filter
    try:
        result = await _post(f"/collections/{body.name}/points/scroll", payload)
    except Exception as exc:  # noqa: BLE001
        return _err(f"query failed: {exc}", code=502)
    return JSONResponse(
        {
            "points": result.get("points", []),
            "next": result.get("next_page_offset"),
            "limit": limit,
            "filtered": bool(doc_filter),
        }
    )


class SearchBody(BaseModel):
    name: str
    query: str
    limit: int = 25
    # Optional doc_id whitelist; empty means "whole collection".
    doc_ids: list[str] = []


async def _embed(text: str) -> list[float]:
    """Embed one query string with OpenAI, matching the stored vector space.

    Imported lazily so browsing keeps working when no OpenAI key is set. The
    AsyncOpenAI client reads OPENAI_API_KEY from the environment itself, and
    honours OPENAI_BASE_URL — set it to an OpenAI-compatible proxy when the
    official endpoint isn't reachable from this region.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    resp = await client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


@app.post("/api/search")
async def api_search(body: SearchBody) -> JSONResponse:
    """Semantic nearest-neighbour search over a collection.

    Embeds the user's text with the same model that produced the stored
    vectors, then asks Qdrant for the closest points. Results carry a
    similarity ``score`` the UI shows alongside the payload.
    """
    query = body.query.strip()
    if not query:
        return _err("empty query")
    if not os.environ.get("OPENAI_API_KEY"):
        return _err("semantic search needs OPENAI_API_KEY", code=503)
    limit = max(1, min(body.limit, 200))
    try:
        vector = await _embed(query)
    except Exception as exc:  # noqa: BLE001 — embedding/key failures go to the UI
        return _err(f"embedding failed: {exc}", code=502)
    payload = {"vector": vector, "limit": limit, "with_payload": True}
    doc_filter = _doc_filter(body.doc_ids)
    if doc_filter:
        # Qdrant applies the filter during traversal, so the top-N comes from
        # the selected docs rather than being post-filtered down to fewer hits.
        payload["filter"] = doc_filter
    try:
        # /points/search returns a bare list of scored points under "result".
        result = await _post(f"/collections/{body.name}/points/search", payload)
    except Exception as exc:  # noqa: BLE001
        return _err(f"query failed: {exc}", code=502)
    points = result if isinstance(result, list) else result.get("points", [])
    return JSONResponse({"points": points, "limit": limit, "filtered": bool(doc_filter)})


def main() -> None:
    global BASE_URL, API_KEY, EMBED_MODEL
    default_url = SERVICES.qdrant_url
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=default_url,
        help=f"Qdrant base URL (http://host:6333); default from config.QDRANT_URL: {default_url}",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=SERVICES.qdrant_viewer_port)
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        parser.error("only http(s) Qdrant URLs are supported")
    BASE_URL = args.url.rstrip("/")
    API_KEY = os.environ.get("QDRANT_API_KEY") or None
    EMBED_MODEL = os.environ.get("EMBED_MODEL", EMBED_MODEL)

    import uvicorn

    print(f"Qdrant Viewer → http://{args.host}:{args.port}")
    print(f"Connected to: {BASE_URL}" + (" (api-key set)" if API_KEY else ""))
    print(
        "Semantic search: enabled" if os.environ.get("OPENAI_API_KEY")
        else "Semantic search: disabled (set OPENAI_API_KEY)"
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
