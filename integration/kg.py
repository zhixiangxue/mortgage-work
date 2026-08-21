"""KG service client — pure HTTP wrapper, no business logic.

Wraps the knowledge-graph API (default :8001). Like RAG, document ingest is
two-step: ``upload_bundle`` hosts a zip archive and returns a downloadable
URL, then ``ingest`` submits that URL as an async task. The caller
(index/indexer.py) packs individual product files into single-file zips with
a manifest before handing bytes here.

All task operations (status / cancel / retry) live under ``/{graph}`` — the
graph-less legacy routes are deprecated on the service side and deliberately
not used here.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import httpx

log = logging.getLogger(__name__)


class KgClient:
    """Thin HTTP client for the KG service."""

    def __init__(self, base_url: str, api_key: str, graph: str):
        self._base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key} if api_key else {}
        self._graph = graph

    def _raise(self, resp: httpx.Response, what: str) -> None:
        """raise_for_status with the response body in the log.

        ``httpx.HTTPStatusError`` alone carries no body text, so a 500 from
        the service was previously undiagnosable without server logs. The
        body (truncated) is where the real reason lives — missing deps,
        worker crashes, validation errors.
        """
        if resp.is_error:
            body = resp.text[:400].replace("\n", " ")
            log.error("KG %s → HTTP %s · %s", what, resp.status_code, body)
        resp.raise_for_status()

    def _envelope(self, resp: httpx.Response, what: str) -> dict:
        """Unwrap the KG envelope, turning in-band errors into HTTP-shaped ones.

        This service answers HTTP 200 even when the resource is gone — the
        verdict lives in ``{"success": false, "code": ...}`` (see
        graph_info). Callers (the indexer's poller and retry paths) branch
        on ``httpx.HTTPStatusError`` with a 404 check, so an envelope 404 is
        re-raised as exactly that; without the translation a vanished task
        blew up as a TypeError the poller mistook for a network blip and
        retried forever.
        """
        self._raise(resp, what)
        body = resp.json()
        if body.get("success"):
            return body
        code = body.get("code") or 500
        if code in (404, 409):
            # Synthesize the HTTP error the envelope is hiding — request
            # URL/method are the only fields any caller inspects.
            fake = httpx.Response(code, request=resp.request)
            raise httpx.HTTPStatusError(
                f"KG {what}: {body.get('message') or code}",
                request=resp.request, response=fake)
        raise RuntimeError(body.get("message") or f"KG service error ({code})")

    # ── Graph lifecycle ──

    def ensure_graph(self) -> None:
        """Create the graph if it doesn't exist (idempotent).

        FalkorDB graphs are created implicitly, so this just runs a trivial
        query against the target graph to guarantee it's there.
        """
        resp = httpx.post(
            f"{self._base}/{self._graph}/create",
            headers=self._headers,
            timeout=30,
        )
        self._raise(resp, "ensure_graph")
        log.info("KG graph ensured · %s", self._graph)

    def graph_info(self) -> dict | None:
        """Structural overview of this graph, or None when it doesn't exist.

        Read-only existence probe (shared-KB validation) that never creates:
        a missing graph stays missing. Unlike RAG, this service answers HTTP
        200 either way — the envelope decides (``success=false`` +
        ``code=404`` for a missing graph)."""
        resp = httpx.get(
            f"{self._base}/graphs/{self._graph}",
            headers=self._headers,
            timeout=15,
        )
        self._raise(resp, "graph_info")
        body = resp.json()
        if not body.get("success"):
            if body.get("code") == 404:
                return None
            raise RuntimeError(body.get("message") or "KG service error")
        return body.get("data")

    # ── Two-step ingest ──

    def upload_bundle(self, zip_bytes: bytes, filename: str = "bundle.zip") -> str:
        """Step 1: upload a zip/tar archive, get back a hosted HTTP URL.

        The KG service stores the file and returns a real download URL that
        its worker fetches later. Only archives are accepted — single files
        must be zipped first.
        """
        resp = httpx.post(
            f"{self._base}/uploads",
            headers=self._headers,
            files={"bundle": (filename, zip_bytes, "application/zip")},
            timeout=120,
        )
        self._raise(resp, f"upload_bundle {filename}")
        url = resp.json()["data"]["url"]
        log.info("🌐 KG bundle uploaded · %s · %d bytes", filename, len(zip_bytes))
        return url

    def ingest(self, url: str, processor: str = "matrix") -> str:
        """Step 2: submit the hosted URL for extraction into this graph.

        Returns ``task_id`` for polling. The ``processor`` selects which
        extraction worker handles this — Mortgage Work always uses ``matrix``.
        """
        resp = httpx.post(
            f"{self._base}/{self._graph}/ingest",
            headers=self._headers,
            json={"data": url, "processor": processor},
            timeout=30,
        )
        self._raise(resp, "ingest")
        task_id = resp.json()["data"]["task_id"]
        log.info("🌐 KG ingest submitted · task=%s · processor=%s", task_id, processor)
        return task_id

    # ── Task queries ──

    def task_status(self, task_id: str) -> str:
        """Return the raw status string ('PENDING', 'PROCESSING',
        'COMPLETED', 'FAILED', 'CANCELLED').

        A task the service no longer knows answers HTTP 200 + envelope
        ``code=404``; ``_envelope`` turns that into an ``HTTPStatusError``
        with ``status_code == 404`` so the poller's vanished-task branch
        fires instead of retrying forever."""
        resp = httpx.get(
            f"{self._base}/{self._graph}/ingest/{task_id}",
            headers=self._headers,
            timeout=15,
        )
        body = self._envelope(resp, f"task_status {task_id}")
        status = body["data"]["status"]
        log.debug("KG task %s → %s", task_id, status)
        return status

    def retry_task(self, task_id: str) -> None:
        """Re-enqueue a failed ingestion task. A vanished task surfaces as an
        envelope 404 → HTTPStatusError(404), which the indexer's retry path
        answers with a full re-upload."""
        resp = httpx.post(
            f"{self._base}/{self._graph}/ingest/{task_id}/retry",
            headers=self._headers,
            timeout=15,
        )
        self._envelope(resp, f"retry_task {task_id}")
        log.info("KG task retry · %s", task_id)

    def cancel_task(self, task_id: str) -> None:
        """Cancel an in-flight ingestion task.

        Called during document deletion so a task racing to completion
        doesn't re-create the nodes we just deleted. Only non-terminal tasks
        (PENDING/PROCESSING) are cancellable — the state machine rejects
        anything else with a 409 (HTTP or envelope), which we swallow: the
        delete that follows will clean up whatever the task produced.
        """
        resp = httpx.post(
            f"{self._base}/{self._graph}/ingest/{task_id}/cancel",
            headers=self._headers,
            timeout=15,
        )
        if resp.status_code == 409:
            log.debug("KG task cancel skipped (terminal) · %s", task_id)
            return  # already terminal — nothing left to cancel
        try:
            self._envelope(resp, f"cancel_task {task_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                log.debug("KG task cancel skipped (terminal) · %s", task_id)
                return
            raise
        log.info("KG task cancel · %s", task_id)

    # ── Query endpoints ──

    def locate(self, question: str, doc_ids: list[str] | None = None) -> dict:
        """Locate the documents relevant to a natural-language question.

        Thin wrapper for ``POST /{graph}/locate``. Runs NLQ against the graph
        and returns only located ``doc_ids`` plus a short statement — no
        qualification happens server-side; the caller verifies against the
        source documents itself. ``doc_ids`` is optional access-control
        scoping with the same semantics the old query endpoint had.

        NLQ generation makes this a slow call (tens of seconds), hence the
        generous timeout.
        """
        payload: dict = {"question": question}
        if doc_ids is not None:
            payload["doc_ids"] = doc_ids
        resp = httpx.post(
            f"{self._base}/{self._graph}/locate",
            headers=self._headers,
            json=payload,
            timeout=200,
        )
        self._raise(resp, "locate")
        return resp.json().get("data") or {}

    def query(self, question: str, doc_ids: list[str] | None = None) -> dict:
        """Ask a natural-language question against this graph.

        TODO: the service-side ``/{graph}/query`` API has changed and the
        caller now does locate + local source-document verification instead
        (see agents/tools/kg.py). Not integrating this in the short term —
        reintroduce only when the new query contract is settled.
        """
        raise NotImplementedError(
            "KG /{graph}/query is not integrated; use locate() instead"
        )

    # ── Document deletion ──

    def delete_document(self, doc_id: str) -> None:
        """Remove a document's nodes and edges from the knowledge graph.

        The graph API deletes by doc-id hash sets (``DELETE /{graph}/delete``
        with a ``doc_ids`` body) rather than per-document routes, so a single
        document travels as a one-element list. Synchronous on the service
        side — no worker queue involved. The doc_id is the same content-hash
        used by RAG, so the two deletes are always in sync.

        Note: ``httpx.request`` instead of ``httpx.delete`` — the top-level
        ``delete()`` helper doesn't accept a request body.
        """
        resp = httpx.request(
            "DELETE",
            f"{self._base}/{self._graph}/delete",
            headers=self._headers,
            json={"doc_ids": [doc_id]},
            timeout=30,
        )
        self._raise(resp, f"delete_document {doc_id}")
        log.info("KG document deleted · %s", doc_id)


# ── Raw-store browser (user-facing Knowledge Base) ──
#
# Structural spec for the matrix hierarchy, ported from browser/falkordb_viewer.py.
# Strictly linear backbone: Lender -> Product -> Requirement -> Group -> Condition -> Field.
_MATRIX_ROOT = {"label": "Lender", "rel": "OFFERS", "name": "name"}
_MATRIX_ITEM = {"label": "Product", "id": "product_id", "name": "product_name"}
_MATRIX_CHAIN = [
    ("HAS_REQUIREMENT", "Requirement"),
    ("HAS_GROUP", "Group"),
    ("HAS_CONDITION", "Condition"),
    ("ON_FIELD", "Field"),
]

# Preferred human-readable property per node label, with fallback to ``id``.
_DISPLAY_PROP: dict[str, str] = {
    "Lender": "name",
    "Product": "product_name",
    "Requirement": "title",
    "Group": "label",
    "Condition": "label",
    "Field": "path",
}


def _relations() -> tuple[dict[str, list[tuple[str, str]]], dict[str, str]]:
    """Direct-children map and per-label anchor id property for lazy expansion.

    Same derivation as the viewer: ``children[label]`` lists
    ``(relationship, child_label)`` reachable in one hop; ``id_props[label]``
    is the property a node of that label is matched by (RANGE-indexed on prod,
    so each anchor is an index seek, not a label scan).
    """
    children: dict[str, list[tuple[str, str]]] = {
        _MATRIX_ROOT["label"]: [(_MATRIX_ROOT["rel"], _MATRIX_ITEM["label"])],
    }
    id_props: dict[str, str] = {_MATRIX_ROOT["label"]: "id",
                                _MATRIX_ITEM["label"]: _MATRIX_ITEM["id"]}
    children[_MATRIX_ITEM["label"]] = list(_MATRIX_CHAIN[:1])
    for idx, (_rel, label) in enumerate(_MATRIX_CHAIN):
        id_props.setdefault(label, "id")
        children[label] = [_MATRIX_CHAIN[idx + 1]] if idx + 1 < len(_MATRIX_CHAIN) else []
    return children, id_props


class FalkorStoreClient:
    """Read-only tree browser over the raw FalkorDB store (user-facing
    Knowledge Base).

    Unlike ``KgClient`` (which talks to the KG service), this runs Cypher
    straight against FalkorDB via zig. The graph name is bound at construction
    and no method accepts another one, so a caller can only ever read the
    graph it was built for. Query templates are fixed per method — no raw
    Cypher from the outside. Ported from browser/falkordb_viewer.py.

    All public methods are synchronous: zig's ``execute`` is async, so the
    client owns one dedicated daemon event-loop thread and caches the zig
    ``Graph`` connection on it (the viewer does the same caching — rebuilding
    the connection on every hop would add ~2s of warmup per tree expansion).
    """

    QUERY_TIMEOUT = 30.0

    def __init__(self, base_uri: str, graph: str):
        self._uri = f"{base_uri.rstrip('/')}/{graph}"
        self._graph_obj = None          # zig.Graph, created lazily on the loop
        self._lock = asyncio.Lock()     # serializes commands on one connection
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="falkor-store")
        self._thread.start()

    # ── Async plumbing ──

    async def _query(self, cypher: str, params: dict | None = None):
        if self._graph_obj is None:
            from zig import Graph
            self._graph_obj = Graph(self._uri)
        async with self._lock:
            return await asyncio.wait_for(
                self._graph_obj.execute(cypher, params=params or {}),
                timeout=self.QUERY_TIMEOUT,
            )

    def _run(self, cypher: str, params: dict | None = None):
        """Bridge: run one read on the client's loop and block for the
        result. Hard cap slightly above QUERY_TIMEOUT so a wedged query
        surfaces as an error instead of hanging the UI thread."""
        fut = asyncio.run_coroutine_threadsafe(self._query(cypher, params), self._loop)
        return fut.result(timeout=self.QUERY_TIMEOUT + 10)

    # ── Read API ──

    def roots(self) -> list[dict]:
        """Lender list with per-lender product counts. OPTIONAL MATCH keeps
        lenders that currently offer nothing visible (count 0)."""
        cypher = (
            f"MATCH (r:{_MATRIX_ROOT['label']}) "
            f"OPTIONAL MATCH (r)-[:{_MATRIX_ROOT['rel']}]->(i:{_MATRIX_ITEM['label']}) "
            f"RETURN r.id AS root_id, r.{_MATRIX_ROOT['name']} AS name, count(i) AS count "
            f"ORDER BY toLower(name)"
        )
        result = self._run(cypher)
        return [
            {"id": rec.get("root_id"), "type": _MATRIX_ROOT["label"],
             "name": rec.get("name") or "(unnamed)", "count": rec.get("count", 0)}
            for rec in result.records
        ]

    def children(self, node_id: str, label: str) -> list[dict]:
        """Direct children of one node for on-demand tree expansion.

        Only id + display name are projected (never the full node), keeping
        each hop tiny; heavy props come via ``node()`` on selection. ``leaf``
        tells the UI whether a child can be expanded further. Raises
        ``KeyError`` on a label outside the matrix spec.
        """
        children_map, id_props = _relations()
        if label not in children_map:
            raise KeyError(f"unknown label '{label}'")
        id_prop = id_props[label]
        out: list[dict[str, Any]] = []
        for rel, child_label in children_map[label]:
            child_id_prop = id_props.get(child_label, "id")
            name_prop = _DISPLAY_PROP.get(child_label, child_id_prop)
            cypher = (
                f"MATCH (p:{label} {{{id_prop}: $id}})-[:{rel}]->(c:{child_label}) "
                f"RETURN c.{child_id_prop} AS id, c.{name_prop} AS name"
            )
            res = self._run(cypher, {"id": node_id})
            leaf = not children_map.get(child_label)
            for rec in res.records:
                cid = rec.get("id")
                name = rec.get("name")
                out.append({
                    "id": cid,
                    "type": child_label,
                    "name": str(name if name not in (None, "") else cid or child_label),
                    "leaf": leaf,
                })
        out.sort(key=lambda n: n["name"].lower())
        return out

    def node(self, node_id: str, label: str) -> dict | None:
        """Full property bag of a single node for the detail panel, or None
        when nothing matches."""
        _children_map, id_props = _relations()
        id_prop = id_props.get(label, "id")
        cypher = f"MATCH (n:{label} {{{id_prop}: $id}}) RETURN n LIMIT 1"
        res = self._run(cypher, {"id": node_id})
        if not res.records:
            return None
        raw = res.records[0].get("n")
        # zig returns a node as {"label": ..., "properties": {...}}
        props = raw.get("properties") if isinstance(raw, dict) and isinstance(raw.get("properties"), dict) else (raw or {})
        display = _DISPLAY_PROP.get(label, "id")
        name = props.get(display) or props.get("id") or label
        return {
            "id": props.get("id") or node_id,
            "type": label,
            "name": str(name),
            "props": props,
        }

    def stats(self) -> dict:
        """Counts for the header/toolbar: nodes, edges, lenders, products."""
        def _count(cypher: str) -> int:
            res = self._run(cypher)
            rec = res.records[0] if res.records else {}
            return int(rec.get("c", 0) or 0)
        return {
            "nodes": _count("MATCH (n) RETURN count(n) AS c"),
            "edges": _count("MATCH ()-[r]->() RETURN count(r) AS c"),
            "lenders": _count(f"MATCH (n:{_MATRIX_ROOT['label']}) RETURN count(n) AS c"),
            "products": _count(f"MATCH (n:{_MATRIX_ITEM['label']}) RETURN count(n) AS c"),
        }

    def close(self) -> None:
        """Stop the background loop. The cached connection dies with the
        thread; safe to call more than once."""
        self._loop.call_soon_threadsafe(self._loop.stop)
