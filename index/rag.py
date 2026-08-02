"""RAG service client — pure HTTP wrapper, no business logic.

Wraps the RAG API (default :8000) that manages vector datasets and document
processing. Every method is a thin pass-through to one REST endpoint; the
caller (indexer.py) decides *when* to call them and *what* to do with results.

Two-step upload contract
------------------------
RAG's document pipeline is split: ``upload_document`` registers the file and
returns a ``doc_id`` (with content-based dedup), then ``create_task`` kicks off
asynchronous parsing. The two steps exist so re-uploads of identical content
are cheap (dedup short-circuits) but task creation is explicit.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx


class RagClient:
    """Thin HTTP client for the RAG service.

    All network errors surface as exceptions — the caller (indexer.py) catches
    them and records ``status='error'`` in SQLite. A service-side processing
    failure surfaces later as ``task_status() == 'failed'``.
    """

    def __init__(self, base_url: str, api_key: str, dataset_id: str):
        self._base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key} if api_key else {}
        self._dataset_id = dataset_id

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
        # 200 = created, 409 = already exists — both fine
        if resp.status_code not in (200, 409):
            resp.raise_for_status()

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
        resp.raise_for_status()
        return resp.json()["data"]

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
        resp.raise_for_status()
        return resp.json()["data"]["task_id"]

    # ── Task queries ──

    def task_status(self, task_id: str) -> str:
        """Return the raw status string (e.g. 'PENDING', 'PROCESSING',
        'COMPLETED', 'FAILED')."""
        resp = httpx.get(
            f"{self._base}/tasks/{task_id}",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"]["status"]

    def retry_task(self, task_id: str) -> None:
        """Re-dispatch a failed task to the worker."""
        resp = httpx.post(
            f"{self._base}/tasks/{task_id}/retry",
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()

    # ── Document deletion ──

    def delete_document(self, doc_id: str) -> None:
        """Remove a document and its vector units from the dataset."""
        resp = httpx.delete(
            f"{self._base}/datasets/{self._dataset_id}/documents/{doc_id}",
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
