"""RAG service client — pure HTTP wrapper, no business logic.

Wraps the RAG API (default :8000) that manages vector datasets and document
processing. Every method is a thin pass-through to one REST endpoint; the
caller (index/indexer.py) decides *when* to call them and *what* to do with
results.

Two-step upload contract
------------------------
RAG's document pipeline is split: ``upload_document`` registers the file and
returns a ``doc_id`` (with content-based dedup), then ``create_task`` kicks
off asynchronous parsing. The two steps exist so re-uploads of identical
content are cheap (dedup short-circuits) but task creation is explicit.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


class RagClient:
    """Thin HTTP client for the RAG service.

    All network errors surface as exceptions — the caller catches them and
    records ``status='error'`` in SQLite. A service-side processing failure
    surfaces later as ``task_status() == 'FAILED'``.
    """

    def __init__(self, base_url: str, api_key: str, dataset_id: str):
        self._base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key} if api_key else {}
        self._dataset_id = dataset_id

    def _raise(self, resp: httpx.Response, what: str) -> None:
        """raise_for_status with the response body in the log.

        ``httpx.HTTPStatusError`` alone carries no body text, so a 500 from
        the service was previously undiagnosable without server logs. The
        body (truncated) is where the real reason lives — missing deps,
        validation errors, queue state.
        """
        if resp.is_error:
            body = resp.text[:400].replace("\n", " ")
            log.error("RAG %s → HTTP %s · %s", what, resp.status_code, body)
        resp.raise_for_status()

    # ── Dataset lifecycle ──

    def ensure_dataset(self, description: str = "") -> None:
        """Create the dataset if it doesn't exist (idempotent via 409)."""
        resp = httpx.post(
            f"{self._base}/datasets",
            headers=self._headers,
            json={
                "name": self._dataset_id,
                "dataset_id": self._dataset_id,
                "description": description,
                "engine": "qdrant",
            },
            timeout=30,
        )
        # 200 = created/existing (create-or-get), 409 = same dataset_id with
        # a different name — both fine for our idempotent boot call
        if resp.status_code not in (200, 409):
            self._raise(resp, "ensure_dataset")
        log.info("RAG dataset ensured · %s", self._dataset_id)

    def dataset_info(self) -> dict | None:
        """Dataset metadata, or None when the dataset doesn't exist.

        Read-only existence probe (shared-KB validation) — a 404 simply means
        nobody has indexed anything under this id yet."""
        resp = httpx.get(
            f"{self._base}/datasets/{self._dataset_id}",
            headers=self._headers,
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        self._raise(resp, "dataset_info")
        return resp.json().get("data")

    def list_documents(self) -> list[dict]:
        """Every document registered in this dataset (read-only)."""
        resp = httpx.get(
            f"{self._base}/datasets/{self._dataset_id}/documents",
            headers=self._headers,
            timeout=30,
        )
        self._raise(resp, "list_documents")
        return resp.json().get("data") or []

    # ── Two-step document upload ──

    def upload_document(self, file_path: Path, metadata: dict) -> dict:
        """Step 1: upload file bytes, get back {doc_id, is_duplicate}.

        The same content always maps to the same doc_id; RAG returns
        ``is_duplicate=True`` when it's already seen the bytes.
        """
        with open(file_path, "rb") as f:
            resp = httpx.post(
                f"{self._base}/datasets/{self._dataset_id}/documents/upload",
                headers=self._headers,
                files={"file": (file_path.name, f)},
                data={"metadata": json.dumps(metadata)},
                timeout=120,
            )
        self._raise(resp, f"upload {file_path.name}")
        data = resp.json()["data"]
        log.info("🧠 RAG upload ok · %s · doc_id=%s%s", file_path.name,
                 data.get("doc_id"), " · duplicate" if data.get("is_duplicate") else "")
        return data

    def create_task(self, doc_id: str,
                    mode: str = "classic",
                    reader: str = "pymupdf4llm") -> str:
        """Step 2: enqueue a processing task for an uploaded document.

        Returns ``task_id`` for polling.
        """
        resp = httpx.post(
            f"{self._base}/datasets/{self._dataset_id}/documents/{doc_id}/tasks",
            headers=self._headers,
            params={"mode": mode, "reader": reader},
            timeout=30,
        )
        self._raise(resp, f"create_task doc={doc_id}")
        task_id = resp.json()["data"]["task_id"]
        log.info("🧠 RAG task created · doc_id=%s · task=%s", doc_id, task_id)
        return task_id

    # ── Task queries ──

    def task_status(self, task_id: str) -> str:
        """Return the raw status string (e.g. 'PENDING', 'PROCESSING',
        'COMPLETED', 'FAILED')."""
        resp = httpx.get(
            f"{self._base}/tasks/{task_id}",
            headers=self._headers,
            timeout=15,
        )
        self._raise(resp, f"task_status {task_id}")
        status = resp.json()["data"]["status"]
        log.debug("RAG task %s → %s", task_id, status)
        return status

    def retry_task(self, task_id: str) -> None:
        """Re-dispatch a terminal-state task to the worker (reset to
        PENDING)."""
        resp = httpx.post(
            f"{self._base}/tasks/{task_id}/retry",
            headers=self._headers,
            timeout=15,
        )
        self._raise(resp, f"retry_task {task_id}")
        log.info("RAG task retry · %s", task_id)

    def cancel_task(self, task_id: str) -> None:
        """Cancel an in-flight processing task.

        Called during document deletion so a task racing to completion
        doesn't re-create the vectors we just deleted. Only non-terminal
        tasks (PENDING/PROCESSING) are cancellable — a task that already
        settled gets a 409, which we swallow: the delete that follows will
        clean up whatever it produced.
        """
        resp = httpx.post(
            f"{self._base}/tasks/{task_id}/cancel",
            headers=self._headers,
            timeout=15,
        )
        if resp.status_code == 409:
            log.debug("RAG task cancel skipped (terminal) · %s", task_id)
            return  # already terminal — nothing left to cancel
        self._raise(resp, f"cancel_task {task_id}")
        log.info("RAG task cancel · %s", task_id)

    # ── Query endpoints ──

    def query(self, query: str, top_k: int = 15,
              filters: dict | None = None) -> list[dict]:
        """Pure vector retrieval over this dataset.

        This is the read path used by the QA agent. It intentionally stays a
        thin REST adapter: callers decide how to format evidence and how to
        handle empty results.

        Vector-only on purpose: the service's ``/query/fusion`` hybrid path
        also hits its Meilisearch BM25 index, which 500s whenever the index
        is missing or empty (index_not_found) — a server-side fragility the
        read path must not depend on.
        """
        resp = httpx.post(
            f"{self._base}/datasets/{self._dataset_id}/query/vector",
            headers=self._headers,
            json={
                "query": query,
                "top_k": top_k,
                "filters": filters or {},
            },
            timeout=60,
        )
        self._raise(resp, "query")
        return resp.json().get("data") or []

    # ── Document deletion ──

    def delete_document(self, doc_id: str) -> None:
        """Remove a document and its vector units from the dataset.

        The service answers 409 if the document still has active
        dependencies — callers should resolve those before retrying.
        """
        resp = httpx.delete(
            f"{self._base}/datasets/{self._dataset_id}/documents/{doc_id}",
            headers=self._headers,
            timeout=30,
        )
        self._raise(resp, f"delete_document {doc_id}")
        log.info("RAG document deleted · %s", doc_id)


class QdrantStoreClient:
    """Read-only browser over the raw Qdrant store (user-facing Knowledge Base).

    Unlike ``RagClient`` (which talks to the RAG service), this talks straight
    to Qdrant's HTTP API. The collection name is bound at construction and no
    method accepts another one, so a caller can only ever read the collection
    it was built for — the isolation guarantee lives in the type, not in
    caller discipline. Only GET/scroll is exposed: no search, no writes.
    Query shapes ported from browser/qdrant_viewer.py.
    """

    def __init__(self, base_url: str, api_key: str, collection: str):
        self._base = base_url.rstrip("/")
        self._headers = {"api-key": api_key} if api_key else {}
        self._collection = collection

    def _get(self, path: str) -> dict:
        """GET a Qdrant endpoint and unwrap its ``{"result": ...}`` envelope."""
        resp = httpx.get(f"{self._base}{path}", headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("result", {})

    def _post(self, path: str, body: dict) -> dict:
        resp = httpx.post(f"{self._base}{path}", headers=self._headers,
                          json=body, timeout=30)
        resp.raise_for_status()
        return resp.json().get("result", {})

    def info(self) -> dict:
        """Collection metadata for the pane header: point count, status and
        the vector config flattened to (name, size, distance) rows — Qdrant
        has a single-unnamed-vector shape and a named-vectors shape."""
        info = self._get(f"/collections/{self._collection}")
        config = info.get("config") or {}
        vectors = (config.get("params") or {}).get("vectors") or {}
        if "size" in vectors:  # single unnamed vector
            rows = [{"name": "(default)", "size": vectors.get("size"),
                     "distance": vectors.get("distance")}]
        else:
            rows = [{"name": name, "size": spec.get("size"),
                     "distance": spec.get("distance")}
                    for name, spec in vectors.items() if isinstance(spec, dict)]
        return {
            "points": info.get("points_count"),
            "status": info.get("status"),
            "vectors": rows,
        }

    def scroll(self, limit: int = 25, offset=None) -> dict:
        """One page of points (full payload, no vectors) + ``next`` cursor.

        Qdrant cursors are opaque point ids and strictly forward-only —
        exactly what the frontend's infinite scroll needs. ``next`` is None
        when the collection is exhausted.
        """
        limit = max(1, min(int(limit), 200))
        body: dict = {"limit": limit, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        result = self._post(f"/collections/{self._collection}/points/scroll", body)
        return {"points": [self._shape(p) for p in result.get("points", [])],
                "next": result.get("next_page_offset")}

    @staticmethod
    def _shape(point: dict) -> dict:
        """Flatten the RAG service's payload into the customer-facing row.

        Raw payload nests the chunk text under ``content`` and the source
        file under ``metadata.document.file_name`` — both are surfaced at the
        top level (``text`` / ``file_name``) so the browser renders a plain
        table instead of raw JSON. Everything else passes through untouched.
        """
        payload = dict(point.get("payload") or {})
        if "content" in payload:
            payload["text"] = payload.pop("content")
        doc = ((payload.get("metadata") or {}).get("document") or {})
        if doc.get("file_name"):
            payload["file_name"] = doc["file_name"]
        return {"id": point.get("id"), "payload": payload}

