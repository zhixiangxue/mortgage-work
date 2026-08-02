"""KG service client — pure HTTP wrapper, no business logic.

Wraps the knowledge-graph API (default :8001). Like RAG, document ingest is
two-step: ``upload_bundle`` hosts a zip archive and returns a downloadable URL,
then ``ingest`` submits that URL as an async task. The caller (indexer.py)
packs individual product files into single-file zips with a manifest before
handing bytes here.
"""
from __future__ import annotations

import httpx


class KgClient:
    """Thin HTTP client for the KG service."""

    def __init__(self, base_url: str, api_key: str, graph: str):
        self._base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key} if api_key else {}
        self._graph = graph

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
        return resp.json()["data"]["url"]

    def ingest(self, url: str, processor: str = "matrix") -> str:
        """Step 2: submit the hosted URL for extraction.

        Returns ``task_id`` for polling. The ``processor`` selects which
        extraction worker handles this — Mortgage Work always uses ``matrix``.
        """
        resp = httpx.post(
            f"{self._base}/ingest",
            headers={**self._headers, "Content-Type": "application/json"},
            json={
                "data": url,
                "processor": processor,
                "graph": self._graph,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"]["task_id"]

    # ── Task queries ──

    def task_status(self, task_id: str) -> str:
        """Return the raw status string ('PENDING', 'PROCESSING',
        'COMPLETED', 'FAILED')."""
        resp = httpx.get(
            f"{self._base}/ingest/{task_id}",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"]["status"]

    def retry_task(self, task_id: str) -> None:
        """Re-enqueue a failed ingestion task."""
        resp = httpx.post(
            f"{self._base}/ingest/{task_id}/retry",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
