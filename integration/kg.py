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

import logging

import httpx

log = logging.getLogger(__name__)


class KgClient:
    """Thin HTTP client for the KG service."""

    def __init__(self, base_url: str, api_key: str, graph: str):
        self._base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key} if api_key else {}
        self._graph = graph

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
        resp.raise_for_status()
        log.info("KG graph ensured · %s", self._graph)

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
        resp.raise_for_status()
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
        resp.raise_for_status()
        task_id = resp.json()["data"]["task_id"]
        log.info("🌐 KG ingest submitted · task=%s · processor=%s", task_id, processor)
        return task_id

    # ── Task queries ──

    def task_status(self, task_id: str) -> str:
        """Return the raw status string ('PENDING', 'PROCESSING',
        'COMPLETED', 'FAILED', 'CANCELLED')."""
        resp = httpx.get(
            f"{self._base}/{self._graph}/ingest/{task_id}",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        status = resp.json()["data"]["status"]
        log.debug("KG task %s → %s", task_id, status)
        return status

    def retry_task(self, task_id: str) -> None:
        """Re-enqueue a failed ingestion task."""
        resp = httpx.post(
            f"{self._base}/{self._graph}/ingest/{task_id}/retry",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        log.info("KG task retry · %s", task_id)

    def cancel_task(self, task_id: str) -> None:
        """Cancel an in-flight ingestion task.

        Called during document deletion so a task racing to completion
        doesn't re-create the nodes we just deleted. Only non-terminal tasks
        (PENDING/PROCESSING) are cancellable — the state machine rejects
        anything else with a 409, which we swallow: the delete that follows
        will clean up whatever the task produced.
        """
        resp = httpx.post(
            f"{self._base}/{self._graph}/ingest/{task_id}/cancel",
            headers=self._headers,
            timeout=15,
        )
        if resp.status_code == 409:
            log.debug("KG task cancel skipped (terminal) · %s", task_id)
            return  # already terminal — nothing left to cancel
        resp.raise_for_status()
        log.info("KG task cancel · %s", task_id)

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
        resp.raise_for_status()
        log.info("KG document deleted · %s", doc_id)
