"""Indexing state — the local truth for what's indexed, kept in index.jsonl.

Why this exists
---------------
Every product document committed to ``products/`` gets indexed by two
external services (RAG for vectors, KG for knowledge graph). Each side
returns an async task_id that we poll to completion. The mapping
``doc_id → (rag_task, kg_task)`` and each side's status used to live in a
machine-local SQLite file; it now lives FLAT on the document's record in
the repo-root ``index.jsonl`` (maintained by ``docindex``) — one
git-synced table instead of a second database to lose, migrate or corrupt.

This module is a facade over ``docindex`` that keeps the pipeline's
row-shaped vocabulary (one row per doc_id, products-relative paths,
idle/indexing/done/failed statuses) so the orchestration in
``indexer.py`` stays untouched.

The state is cheap to rebuild: if index.jsonl is lost, documents are
re-synced from the products tree + the RAG listing at next boot. So it's
a cache of "where are we in the pipeline", not a source of truth for
what files exist.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import docindex
import xxhash

log = logging.getLogger(__name__)

# ── doc_id computation (byte-compatible with kg-service and docindex.py) ──


def calculate_file_hash(file_path: Path | str, chunk_size: int = 8192) -> str:
    """xxh64 hex digest of the file — byte-compatible with RAG/KG services."""
    h = xxhash.xxh64()
    with open(file_path, "rb") as fp:
        while chunk := fp.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


# ── Vocabulary ──

# Source extensions — same set as kg-service. Only these files under
# products/ carry indexing state.
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".md", ".txt", ".doc", ".docx", ".html", ".htm"}
)

# The tracking fields a record carries on top of doc_id/path/size —
# exactly the columns the retired SQLite doc_index table had.
STATE_FIELDS = (
    "rag_task", "rag_status", "rag_error", "rag_updated_at",
    "kg_task", "kg_status", "kg_error", "kg_updated_at",
    "updated_at",
)

# The DB speaks pipeline vocabulary; the Knowledge Base panel speaks status
# vocabulary. One single translation table keeps the chips, the filter tabs
# and the backend logs saying the same thing.
_DISPLAY = {
    "idle": "pending",
    "indexing": "processing",
    "done": "done",
    "failed": "failed",
    "error": "failed",      # upload never reached the service — same face
    "cancelled": "canceled",
}


def display_status(raw: str | None) -> str:
    """Internal status value → UI word (see _DISPLAY)."""
    return _DISPLAY.get(raw or "", "pending")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Boot readiness ──
#
# No database to open anymore — the flag only records that the indexing
# pipeline has booted for this repo, so pre-boot callers (post-pull hooks)
# still have the same gate they always had.

_READY = False


def init_db(repo_root: Path) -> Path:
    """Mark the indexing state as ready for this repo.

    Kept under the old name so call sites don't churn; the storage moved
    to index.jsonl (via docindex) and there is nothing to open. Idempotent.
    """
    global _READY
    _READY = True
    log.info("index state ready · %s/index.jsonl", repo_root)
    return Path(repo_root) / docindex.INDEX_RELPATH


def ready() -> bool:
    """Whether the indexing pipeline has booted for this repo —
    callers that may run before boot (post-pull hooks) check this first."""
    return _READY


# ── Path vocabulary ──
# Callers (indexer.py) speak products-relative paths; index.jsonl records
# are repo-relative. The translation lives here and nowhere else.

def _repo_path(file_path: str) -> str:
    return f"products/{file_path}"


def _rel_path(repo_path: str) -> str:
    return repo_path[len("products/"):] if repo_path.startswith("products/") \
        else repo_path


def _is_tracked(repo_path: str) -> bool:
    """Whether this record is an indexable product document."""
    return (repo_path.startswith("products/")
            and Path(repo_path).suffix.lower() in SOURCE_EXTENSIONS)


def _row_from_record(rec: dict) -> dict:
    """Record on disk → row in the pipeline vocabulary (missing state
    fields synthesize to the idle defaults a fresh SQLite row had)."""
    return {
        "doc_id": rec.get("doc_id"),
        "file_path": _rel_path(rec.get("path", "")),
        "rag_task": rec.get("rag_task"),
        "rag_status": rec.get("rag_status") or "idle",
        "rag_error": rec.get("rag_error"),
        "rag_updated_at": rec.get("rag_updated_at"),
        "kg_task": rec.get("kg_task"),
        "kg_status": rec.get("kg_status") or "idle",
        "kg_error": rec.get("kg_error"),
        "kg_updated_at": rec.get("kg_updated_at"),
        "updated_at": rec.get("updated_at") or rec.get("indexed_at"),
    }


# ── Row set ──
# Several paths can share one doc_id (identical content copied around);
# the pipeline thinks in documents, so rows are deduped by doc_id. The
# lexicographically first tracked path is the canonical one — deterministic
# across machines, which matters now that the table is git-synced.

def _doc_records() -> dict[str, dict]:
    """Tracked product records grouped by doc_id → canonical record."""
    out: dict[str, dict] = {}
    for rec in docindex.all_records():
        rp = rec.get("path", "")
        if not _is_tracked(rp):
            continue
        doc_id = rec.get("doc_id")
        if not doc_id:
            continue
        cur = out.get(doc_id)
        if cur is None or rp < cur.get("path", ""):
            out[doc_id] = rec
    return out


# ── CRUD ──

def upsert(doc_id: str, file_path: str,
           rag_task: str | None = None, kg_task: str | None = None) -> None:
    """Ensure the document's record exists and merge in fresh task_ids.

    Existing task/status values are preserved on update unless explicitly
    passed — same merge semantics as the old SQLite row.
    """
    if not docindex.ensure_loaded():
        return
    repo_path = _repo_path(file_path)
    docindex.ensure_record(doc_id, repo_path)
    rec = docindex.get_record(repo_path) or {}
    now = _now()
    fields: dict = {"updated_at": now}
    if rag_task:
        fields.update({"rag_task": rag_task, "rag_status": "indexing",
                       "rag_updated_at": now})
    elif not rec.get("rag_status"):
        fields["rag_status"] = "idle"
    if kg_task:
        fields.update({"kg_task": kg_task, "kg_status": "indexing",
                       "kg_updated_at": now})
    elif not rec.get("kg_status"):
        fields["kg_status"] = "idle"
    docindex.patch_doc(doc_id, fields)


def set_status(doc_id: str, side: str, status: str,
               task_id: str | None = None, error: str | None = None) -> None:
    """Update one side's status (and optionally its task_id).

    ``error`` is a short failure key (``unavailable`` / ``timeout`` /
    ``vanished`` / ``unknown``) recorded alongside a failed-family status so
    the panel can explain the failure in plain words; moving to any other
    status clears it.
    """
    if not docindex.ensure_loaded():
        return
    now = _now()
    fields = {
        f"{side}_status": status,
        f"{side}_updated_at": now,
        "updated_at": now,
        # The error key mirrors the failed state — set together, clear together.
        f"{side}_error": (error or "unknown") if status in ("failed", "error") else None,
    }
    if task_id is not None:
        fields[f"{side}_task"] = task_id
    docindex.patch_doc(doc_id, fields)


def get_row(doc_id: str) -> dict | None:
    """Return the document's row, or None."""
    if not docindex.ensure_loaded():
        return None
    rec = _doc_records().get(doc_id)
    return _row_from_record(rec) if rec else None


def get_row_by_path(file_path: str) -> dict | None:
    """Return the row matching ``file_path``, or None.

    Used by the delete path: the file is already gone from disk so we
    can't hash it — we find the tracking row by its last known path.
    """
    if not docindex.ensure_loaded():
        return None
    rec = docindex.get_record(_repo_path(file_path))
    if rec is None or not _is_tracked(rec.get("path", "")):
        return None
    return _row_from_record(rec)


def remove(doc_id: str) -> None:
    """Drop a document's tracking state (called after RAG delete succeeds).

    Only the state fields go — the record itself is the content index and
    belongs to docindex's lifecycle (file gone ⇒ record gone happens there).
    """
    if not docindex.ensure_loaded():
        return
    docindex.clear_doc_fields(doc_id, list(STATE_FIELDS))


def all_rows() -> list[dict]:
    """One row per tracked document — used by the boot reconciliation pass
    that compares local status against what the RAG/KG services actually
    hold."""
    if not docindex.ensure_loaded():
        return []
    return [_row_from_record(rec) for rec in _doc_records().values()]


def pending_count() -> int:
    """How many documents still have an indexing task in flight."""
    return sum(1 for r in all_rows()
               if r["rag_status"] == "indexing" or r["kg_status"] == "indexing")


def failed_rows() -> list[dict]:
    """All rows with at least one side in 'failed' or 'error'."""
    return [r for r in all_rows()
            if r["rag_status"] in ("failed", "error")
            or r["kg_status"] in ("failed", "error")]


def stale_tasks() -> list[dict]:
    """Rows still 'indexing' — used on app restart to resume polling."""
    return [r for r in all_rows()
            if r["rag_status"] == "indexing" or r["kg_status"] == "indexing"]


def panel_rows() -> list[dict]:
    """Every tracking row in the panel's vocabulary — the Knowledge Base
    panel renders this verbatim. Statuses are translated (see _DISPLAY),
    newest activity first."""
    rows = [
        {
            "doc_id": r["doc_id"],
            "file_path": r["file_path"],
            "rag_status": display_status(r["rag_status"]),
            "kg_status": display_status(r["kg_status"]),
            "rag_error": r.get("rag_error") or "",
            "kg_error": r.get("kg_error") or "",
            "updated_at": r["updated_at"],
        }
        for r in all_rows()
    ]
    rows.sort(key=lambda r: r["updated_at"] or "", reverse=True)
    return rows


# Document-level classification for the status-bar chip and the filter tabs:
# a document lands in exactly one bucket, whichever of its two sides shouts
# loudest. Same priority everywhere, so the counts can never disagree.
_BUCKET_PRIORITY = ("failed", "processing", "pending", "canceled")


def document_bucket(rag_status: str, kg_status: str) -> str:
    """Classify a document from its two display statuses ('' → done)."""
    sides = {rag_status, kg_status}
    for bucket in _BUCKET_PRIORITY:
        if bucket in sides:
            return bucket
    return "done"


def knowledge_summary() -> dict:
    """Document-level counts for the status-bar chip:
    ``{total, processing, failed, pending, canceled}``."""
    counts = {"total": 0, "processing": 0, "failed": 0, "pending": 0, "canceled": 0}
    for r in all_rows():
        counts["total"] += 1
        bucket = document_bucket(
            display_status(r["rag_status"]), display_status(r["kg_status"]),
        )
        if bucket != "done":
            counts[bucket] += 1
    return counts


def summary() -> dict:
    """A compact status snapshot for the frontend."""
    rows = all_rows()
    return {
        "total": len(rows),
        "pending": sum(1 for r in rows
                       if r["rag_status"] == "indexing"
                       or r["kg_status"] == "indexing"),
        "failed": sum(1 for r in rows
                      if r["rag_status"] in ("failed", "error")
                      or r["kg_status"] in ("failed", "error")),
    }
