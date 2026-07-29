"""Local read-only graph viewer for the matrix / dpa FalkorDB graphs.

Why this exists
---------------
FalkorDB's built-in browser is awkward for inspecting deep, tree-shaped data.
Both of our graphs are strict hierarchies:

    matrix: Lender  -> Product -> Requirement -> Group -> Condition -> Field
    dpa:    Agency   -> Program -> {Requirement -> Group -> Condition -> Field,
                                    Benefit}

This tool lets you pick a lender/agency, then a product/program, and lazily
expands the eligibility sub-tree one hop at a time (children fetched on demand)
so even products with thousands of nodes open instantly instead of freezing.

Safety
------
Every query is issued through zig's ``execute`` with a fixed set of Cypher
templates built from a per-graph spec; the caller never supplies raw Cypher.
Reads dominate; the only mutations are the two ``DELETE`` endpoints, which
remove a Product/Program (or a Lender/Agency plus everything it offers) by
exact, prefix-guarded node ID — mirroring the ingest pipeline's per-item
cleanup and always preserving the shared ``field:`` nodes.

Connection
----------
The FalkorDB base URI is passed explicitly via ``--uri`` (no env vars). Give
the scheme + optional auth + host + port, WITHOUT a trailing graph name — the
graph (``matrix`` / ``dpa``) is appended per request. Examples::

    # local Docker FalkorDB (default)
    uv run python browser/falkordb_viewer.py

    # production over the SSH tunnel (open it first, keep it running):
    #   ssh -L 6386:localhost:6379 ubuntu@<public-host>
    uv run python browser/falkordb_viewer.py \
        --uri falkordb://:vkgjFHOS8CNt@localhost:6386

Usage
-----
    uv run python browser/falkordb_viewer.py --uri <base-uri> [--port 8787]

Then open http://localhost:8787 in a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from zig import Graph

# Centralized service config lives one level up (mortgage-work/config.py); make it
# importable whether this viewer is run as a script or spawned by app.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import SERVICES  # noqa: E402

# ── Project paths ──

_SCRIPT_DIR = Path(__file__).resolve().parent
_HTML_FILE = _SCRIPT_DIR / "falkordb.html"

# Base FalkorDB URI (scheme://[auth@]host:port, no graph suffix). Defaults to
# the centralized config; ``--uri`` still overrides for ad-hoc use.
BASE_URI = SERVICES.falkordb_uri


def resolve_uri(graph: str) -> str:
    """Append the graph name to the explicitly-configured base URI."""
    return f"{BASE_URI.rstrip('/')}/{graph}"


def _display_uri(base: str) -> str:
    """Mask the password in a URI so it is safe to echo to the UI/logs."""
    parsed = urlparse(base)
    if parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        userinfo = f"{parsed.username or ''}:***@"
        netloc = f"{userinfo}{host}"
        parsed = parsed._replace(netloc=netloc)
    return urlunparse(parsed)


# ── Per-graph structural spec ──
#
# Each spec describes the hierarchy so the query builders and tree assembler
# stay graph-agnostic. ``chain`` is the strictly linear backbone; ``branches``
# are extra direct children of the selected item (e.g. dpa Benefits) that hang
# off the item node rather than the requirement chain.

SPECS: dict[str, dict[str, Any]] = {
    "matrix": {
        "root": {"label": "Lender", "rel": "OFFERS", "name": "name"},
        "item": {"label": "Product", "id": "product_id", "name": "product_name", "subtitle": "program_type"},
        "chain": [
            ("HAS_REQUIREMENT", "Requirement"),
            ("HAS_GROUP", "Group"),
            ("HAS_CONDITION", "Condition"),
            ("ON_FIELD", "Field"),
        ],
        "branches": [],
    },
    "dpa": {
        "root": {"label": "Agency", "rel": "OFFERS", "name": "name"},
        "item": {"label": "Program", "id": "program_id", "name": "program_name", "subtitle": "product_line"},
        "chain": [
            ("HAS_REQUIREMENT", "Requirement"),
            ("HAS_GROUP", "Group"),
            ("HAS_CONDITION", "Condition"),
            ("ON_FIELD", "Field"),
        ],
        "branches": [("HAS_BENEFIT", "Benefit")],
    },
}

# Preferred human-readable property per node label, with fallback to ``id``.
DISPLAY_PROP: dict[str, str] = {
    "Lender": "name",
    "Agency": "name",
    "Product": "product_name",
    "Program": "program_name",
    "Requirement": "title",
    "Group": "label",
    "Condition": "label",
    "Field": "path",
    "Benefit": "title",
}


def _node_props(node: Any) -> dict[str, Any]:
    """Normalize a zig node record into its properties dict.

    zig returns a node as ``{"label": ..., "properties": {...}}``; guard
    against unexpected shapes so a malformed row can't crash the assembler.
    """
    if isinstance(node, dict) and isinstance(node.get("properties"), dict):
        return node["properties"]
    if isinstance(node, dict):
        return node
    return {}


def _make_node(label: str, props: dict[str, Any]) -> dict[str, Any]:
    """Build one tree node payload for the frontend."""
    display = DISPLAY_PROP.get(label, "id")
    name = props.get(display) or props.get("id") or label
    return {
        "id": props.get("id") or f"{label}:{name}",
        "type": label,
        "name": str(name),
        "props": props,
        "children": [],
    }


# ── FastAPI app ──

app = FastAPI(title="KG Graph Viewer", docs_url=None, redoc_url=None)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_HTML_FILE)


@app.get("/api/config")
async def api_config() -> JSONResponse:
    """Expose available graphs + the active connection so the UI can render."""
    return JSONResponse(
        {
            "graphs": list(SPECS.keys()),
            "uri": _display_uri(BASE_URI),
            "labels": {g: {"root": s["root"]["label"], "item": s["item"]["label"]} for g, s in SPECS.items()},
        }
    )


# Hard cap on a single DB round trip. A pathological query then surfaces as an
# error instead of freezing the event loop (and making the process unkillable)
# against a slow tunnel or an oversized result set.
QUERY_TIMEOUT = 30.0

# Deletes DETACH-scan the graph by an (unindexed) ID prefix, so they can run
# longer than a lazy read hop; give them more room while still capping them so
# a mutation can never wedge the event loop against a slow tunnel.
DELETE_TIMEOUT = 120.0

# One cached connection (and a serializing lock) per resolved graph URI.
# Reusing the handle avoids paying the ~2s connection warmup on every request,
# which is very noticeable over the SSH tunnel to prod. The lock keeps
# concurrent requests from interleaving commands on one underlying connection.
_GRAPHS: dict[str, Graph] = {}
_LOCKS: dict[str, asyncio.Lock] = {}


def _graph(graph: str) -> tuple[Graph, asyncio.Lock]:
    uri = resolve_uri(graph)
    if uri not in _GRAPHS:
        _GRAPHS[uri] = Graph(uri)
        _LOCKS[uri] = asyncio.Lock()
    return _GRAPHS[uri], _LOCKS[uri]


async def _run(graph: str, cypher: str, params: dict | None = None):
    """Execute one read query on the cached connection with a hard timeout."""
    g, lock = _graph(graph)
    async with lock:
        return await asyncio.wait_for(
            g.execute(cypher, params=params or {}), timeout=QUERY_TIMEOUT
        )


async def _run_write(graph: str, cypher: str, params: dict | None = None):
    """Execute one mutating query under the same per-URI lock as reads, but with
    the longer :data:`DELETE_TIMEOUT` since a cascade delete scans the whole
    graph by ID prefix."""
    g, lock = _graph(graph)
    async with lock:
        return await asyncio.wait_for(
            g.execute(cypher, params=params or {}), timeout=DELETE_TIMEOUT
        )


def _err(message: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=code)


@app.get("/api/roots")
async def api_roots(graph: str = "matrix") -> JSONResponse:
    """List root organizations (lenders / agencies) with their item counts.

    Uses OPTIONAL MATCH so a root that currently offers nothing still appears
    (with a count of 0), letting the operator spot and prune orphaned roots
    left behind by item deletes rather than hiding them.
    """
    spec = SPECS.get(graph)
    if spec is None:
        return _err(f"unknown graph '{graph}'")
    root, item = spec["root"], spec["item"]
    cypher = (
        f"MATCH (r:{root['label']}) "
        f"OPTIONAL MATCH (r)-[:{root['rel']}]->(i:{item['label']}) "
        f"RETURN r.id AS root_id, r.{root['name']} AS name, count(i) AS count "
        f"ORDER BY toLower(name)"
    )
    try:
        result = await _run(graph, cypher)
    except Exception as exc:  # noqa: BLE001 — surface any connection error to UI
        return _err(f"query failed: {exc}", code=502)
    roots = [
        {"root_id": rec.get("root_id"), "name": rec.get("name") or "(unnamed)", "count": rec.get("count", 0)}
        for rec in result.records
    ]
    return JSONResponse({"roots": roots})


@app.get("/api/items")
async def api_items(root_id: str, graph: str = "matrix") -> JSONResponse:
    """List products / programs offered by one root organization."""
    spec = SPECS.get(graph)
    if spec is None:
        return _err(f"unknown graph '{graph}'")
    root, item = spec["root"], spec["item"]
    cypher = (
        f"MATCH (r:{root['label']} {{id: $root_id}})-[:{root['rel']}]->(i:{item['label']}) "
        f"RETURN i.{item['id']} AS id, i.{item['name']} AS name, i.{item['subtitle']} AS subtitle "
        f"ORDER BY toLower(name)"
    )
    try:
        result = await _run(graph, cypher, {"root_id": root_id})
    except Exception as exc:  # noqa: BLE001
        return _err(f"query failed: {exc}", code=502)
    items = [
        {"id": rec.get("id"), "name": rec.get("name") or "(unnamed)", "subtitle": rec.get("subtitle") or ""}
        for rec in result.records
    ]
    return JSONResponse({"items": items})


def _relations(spec: dict[str, Any]) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str]]:
    """Derive, from a graph spec, the direct-children map and per-label anchor
    id property used for lazy expansion.

    ``children[label]`` lists ``(relationship, child_label)`` reachable in one
    hop; ``id_props[label]`` is the property a node of that label is matched by
    (now backed by a RANGE index on prod, so the anchor is an index seek rather
    than a full label scan over tens of thousands of nodes).
    """
    root, item, chain, branches = spec["root"], spec["item"], spec["chain"], spec["branches"]
    children: dict[str, list[tuple[str, str]]] = {root["label"]: [(root["rel"], item["label"])]}
    id_props: dict[str, str] = {root["label"]: "id", item["label"]: item["id"]}

    item_children: list[tuple[str, str]] = list(chain[:1]) + list(branches)
    children[item["label"]] = item_children
    for idx, (_rel, label) in enumerate(chain):
        id_props.setdefault(label, "id")
        children[label] = [chain[idx + 1]] if idx + 1 < len(chain) else []
    for _rel, label in branches:
        id_props.setdefault(label, "id")
        children.setdefault(label, [])
    return children, id_props


@app.get("/api/children")
async def api_children(id: str, label: str, graph: str = "matrix") -> JSONResponse:  # noqa: A002
    """Return the direct children of one node for on-demand tree expansion.

    Only id + display name are projected (never the full node), keeping each
    hop tiny and fast over the tunnel; heavy props are fetched lazily via
    ``/api/node`` when a node is selected. ``leaf`` tells the UI whether a child
    can be expanded further.
    """
    spec = SPECS.get(graph)
    if spec is None:
        return _err(f"unknown graph '{graph}'")
    children_map, id_props = _relations(spec)
    if label not in children_map:
        return _err(f"unknown label '{label}'")
    id_prop = id_props[label]

    out: list[dict[str, Any]] = []
    for rel, child_label in children_map[label]:
        child_id_prop = id_props.get(child_label, "id")
        name_prop = DISPLAY_PROP.get(child_label, child_id_prop)
        cypher = (
            f"MATCH (p:{label} {{{id_prop}: $id}})-[:{rel}]->(c:{child_label}) "
            f"RETURN c.{child_id_prop} AS id, c.{name_prop} AS name"
        )
        try:
            res = await _run(graph, cypher, {"id": id})
        except Exception as exc:  # noqa: BLE001
            return _err(f"query failed: {exc}", code=502)
        leaf = not children_map.get(child_label)
        for rec in res.records:
            cid = rec.get("id")
            name = rec.get("name")
            out.append(
                {
                    "id": cid,
                    "type": child_label,
                    "name": str(name if name not in (None, "") else cid or child_label),
                    "leaf": leaf,
                }
            )
    out.sort(key=lambda n: n["name"].lower())
    return JSONResponse({"children": out})


@app.get("/api/node")
async def api_node(id: str, label: str, graph: str = "matrix") -> JSONResponse:  # noqa: A002
    """Return the full property bag of a single node for the detail panel."""
    spec = SPECS.get(graph)
    if spec is None:
        return _err(f"unknown graph '{graph}'")
    _children_map, id_props = _relations(spec)
    id_prop = id_props.get(label, "id")
    cypher = f"MATCH (n:{label} {{{id_prop}: $id}}) RETURN n LIMIT 1"
    try:
        res = await _run(graph, cypher, {"id": id})
    except Exception as exc:  # noqa: BLE001
        return _err(f"query failed: {exc}", code=502)
    if not res.records:
        return _err(f"node not found: {id}", code=404)
    return JSONResponse({"node": _make_node(label, _node_props(res.records[0].get("n")))})


# ── Deletes (mirror the ingest pipeline's per-item cleanup) ──
#
# Every descendant of an item carries an ID prefixed with ``{item_id}:``
# (Requirement/Group/Condition, plus dpa Benefit), while shared Field nodes live
# under a separate ``field:`` namespace and are deliberately preserved. Deleting
# a root (Lender/Agency) therefore fans out over the items it OFFERS — whose IDs
# are not root-prefixed — deletes each item sub-tree, then drops the now-childless
# root node itself.

_SUBTREE_COUNT = "MATCH (n) WHERE n.id = $id OR n.id STARTS WITH $prefix RETURN count(n) AS c"
_SUBTREE_DELETE = "MATCH (n) WHERE n.id = $id OR n.id STARTS WITH $prefix DETACH DELETE n"


async def _delete_subtree(graph: str, node_id: str) -> int:
    """Delete one item node plus its ``:``-prefixed descendants; returns the node
    count removed (counted first, since DETACH DELETE reports nothing portable)."""
    params = {"id": node_id, "prefix": f"{node_id}:"}
    res = await _run_write(graph, _SUBTREE_COUNT, params)
    count = int(res.records[0].get("c", 0)) if res.records else 0
    await _run_write(graph, _SUBTREE_DELETE, params)
    return count


@app.delete("/api/item")
async def api_delete_item(id: str, graph: str = "matrix") -> JSONResponse:  # noqa: A002
    """Delete a single Product/Program and its entire eligibility sub-tree.

    The parent Lender/Agency is deliberately left in place even when this was
    its last item — a now-childless root still shows up in the roots listing
    (with a count of 0) so the operator can decide whether to remove it too.
    Guarded by an ID-kind prefix check so a blank or malformed ID can never
    widen into a mass delete. Irreversible — the UI gates it behind a confirm.
    """
    spec = SPECS.get(graph)
    if spec is None:
        return _err(f"unknown graph '{graph}'")
    kind = f"{spec['item']['label'].lower()}:"
    if not id or not id.startswith(kind):
        return _err(f"refusing to delete: id must start with '{kind}'")
    try:
        deleted = await _delete_subtree(graph, id)
    except Exception as exc:  # noqa: BLE001
        return _err(f"delete failed: {exc}", code=502)
    return JSONResponse({"deleted": deleted})


@app.delete("/api/root")
async def api_delete_root(id: str, graph: str = "matrix") -> JSONResponse:  # noqa: A002
    """Delete a Lender/Agency together with every Product/Program it offers.

    Guarded by an ID-kind prefix check. Irreversible — the UI gates it behind a
    confirm that spells out the cascade.
    """
    spec = SPECS.get(graph)
    if spec is None:
        return _err(f"unknown graph '{graph}'")
    root, item = spec["root"], spec["item"]
    kind = f"{root['label'].lower()}:"
    if not id or not id.startswith(kind):
        return _err(f"refusing to delete: id must start with '{kind}'")
    try:
        res = await _run(
            graph,
            f"MATCH (r:{root['label']} {{id: $id}})-[:{root['rel']}]->(i:{item['label']}) "
            f"RETURN i.id AS id",
            {"id": id},
        )
        item_ids = [rec.get("id") for rec in res.records if rec.get("id")]
        deleted = 0
        for item_id in item_ids:
            deleted += await _delete_subtree(graph, item_id)
        await _run_write(graph, f"MATCH (r:{root['label']} {{id: $id}}) DETACH DELETE r", {"id": id})
    except Exception as exc:  # noqa: BLE001
        return _err(f"delete failed: {exc}", code=502)
    return JSONResponse({"deleted": deleted + 1, "items": len(item_ids)})


def main() -> None:
    global BASE_URI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri",
        default=BASE_URI,
        help=(
            "FalkorDB base URI (scheme://[:password@]host:port, no graph "
            "suffix). E.g. falkordb://:vkgjFHOS8CNt@localhost:6386 for prod "
            "over the SSH tunnel. Defaults to the local Docker instance."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=SERVICES.falkordb_viewer_port)
    args = parser.parse_args()

    BASE_URI = args.uri

    import uvicorn

    print(f"KG Graph Viewer → http://{args.host}:{args.port}")
    print(f"Connected to: {_display_uri(BASE_URI)}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
