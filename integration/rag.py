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
            resp.raise_for_status()
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
        resp.raise_for_status()
        return resp.json().get("data")

    def list_documents(self) -> list[dict]:
        """Every document registered in this dataset (read-only)."""
        resp = httpx.get(
            f"{self._base}/datasets/{self._dataset_id}/documents",
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
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
        resp.raise_for_status()
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
        resp.raise_for_status()
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
        resp.raise_for_status()
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
        resp.raise_for_status()
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
        resp.raise_for_status()
        log.info("RAG task cancel · %s", task_id)

    # ── Query endpoints ──

    def query(self, query: str, top_k: int = 15,
              filters: dict | None = None, min_score: float = 0.0) -> list[dict]:
        """Hybrid retrieval over this dataset.

        This is the read path used by the QA agent. It intentionally stays a
        thin REST adapter: callers decide how to format evidence and how to
        handle empty results.
        """
        resp = httpx.post(
            f"{self._base}/datasets/{self._dataset_id}/query/fusion",
            headers=self._headers,
            json={
                "query": query,
                "top_k": top_k,
                "filters": filters or {},
                "min_score": min_score,
            },
            timeout=60,
        )
        resp.raise_for_status()
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
        resp.raise_for_status()
        log.info("RAG document deleted · %s", doc_id)
