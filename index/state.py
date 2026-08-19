"""SQLite-backed indexing state — the local truth for what's indexed.

Why this exists
---------------
Every document committed to ``products/`` gets indexed by two external services
(RAG for vectors, KG for knowledge graph). Each side returns an async task_id
that we poll to completion. The mapping ``doc_id → (rag_task, kg_task)`` and
each side's status lives in a single SQLite file next to the work repo
(``~/MortgageWork/<repo>.index.db``). It deliberately lives OUTSIDE the git
work tree: repo re-clones and destructive git operations can't touch it, and
it can never be committed by accident. Each work repo maps to exactly one
location, so a sibling file namespaced by the repo name stays unambiguous.

The file is cheap to rebuild: if it's lost, documents can be re-indexed from
the products tree + ``docindex``. So it's a cache of "where are we in the
pipeline", not a source of truth for what files exist.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import xxhash

log = logging.getLogger(__name__)

# ── doc_id computation (byte-compatible with kg-service and docindex.py) ──

_DB_PATH: Path | None = None
_lock = threading.Lock()


def calculate_file_hash(file_path: Path | str, chunk_size: int = 8192) -> str:
    """xxh64 hex digest of the file — byte-compatible with RAG/KG services."""
    h = xxhash.xxh64()
    with open(file_path, "rb") as fp:
        while chunk := fp.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


# ── Schema ──

_SCHEMA = """
CREATE TABLE IF NOT EXISTS doc_index (
    doc_id         TEXT PRIMARY KEY,
    file_path      TEXT NOT NULL,
    rag_task       TEXT,
    rag_status     TEXT DEFAULT 'idle',
    rag_error      TEXT,
    rag_updated_at TEXT,
    kg_task        TEXT,
    kg_status      TEXT DEFAULT 'idle',
    kg_error       TEXT,
    kg_updated_at  TEXT,
    updated_at     TEXT NOT NULL
);
"""

# ── Presentation mapping ──
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


# ── Connection management ──

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(repo_root: Path) -> Path:
    """Open the SQLite file for this repo, creating it if needed.

    The DB sits NEXT TO the repo (``~/MortgageWork/<repo>.index.db``), not
    inside it — a file in the git work tree could be committed by accident
    and is wiped by a re-clone. Idempotent — safe to call on every boot.

    Older releases kept ``.index.db`` at the repo root; that file is moved
    here on first sight so existing status survives the relocation.
    """
    global _DB_PATH
    db_path = repo_root.parent / f"{repo_root.name}.index.db"
    legacy = repo_root / ".index.db"
    if legacy.is_file() and not db_path.exists():
        try:
            os.replace(legacy, db_path)
            log.info("index state migrated: %s → %s", legacy, db_path)
        except OSError as exc:
            # The move failed (permissions etc.) — keep reading the legacy
            # file rather than starting from a blank slate and re-uploading
            # everything.
            log.warning("index state migration failed (%s) — keeping %s",
                        exc, legacy)
            db_path = legacy
    _DB_PATH = db_path
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        # Columns that arrived after the first release — grow old DBs.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(doc_index)")}
        for col in ("rag_updated_at", "kg_updated_at", "rag_error", "kg_error"):
            if col not in cols:
                conn.execute(f"ALTER TABLE doc_index ADD COLUMN {col} TEXT")
    log.info("index state db ready · %s", db_path)
    return db_path


def _connect() -> sqlite3.Connection:
    if _DB_PATH is None:
        raise RuntimeError("init_db() has not been called yet")
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ready() -> bool:
    """Whether init_db() has opened the tracking DB for this repo yet —
    callers that may run before boot (post-pull hooks) check this first."""
    return _DB_PATH is not None


# ── CRUD ──

def upsert(doc_id: str, file_path: str,
           rag_task: str | None = None, kg_task: str | None = None) -> None:
    """Insert or update a row. Existing task_id/status values are preserved
    on update unless explicitly passed."""
    with _lock, _connect() as conn:
        existing = conn.execute(
            "SELECT rag_task, rag_status, kg_task, kg_status "
            "FROM doc_index WHERE doc_id = ?", (doc_id,)
        ).fetchone()

        now = _now()
        if existing:
            # Preserve existing tasks/status unless new ones are provided
            r_task = rag_task or existing["rag_task"]
            r_status = "indexing" if rag_task else existing["rag_status"]
            k_task = kg_task or existing["kg_task"]
            k_status = "indexing" if kg_task else existing["kg_status"]
            sets = ["file_path=?", "rag_task=?", "rag_status=?",
                    "kg_task=?", "kg_status=?", "updated_at=?"]
            params: list = [file_path, r_task, r_status, k_task, k_status, now]
            if rag_task:
                sets.append("rag_updated_at=?")
                params.append(now)
            if kg_task:
                sets.append("kg_updated_at=?")
                params.append(now)
            params.append(doc_id)
            conn.execute(
                f"UPDATE doc_index SET {', '.join(sets)} WHERE doc_id=?", params,
            )
        else:
            conn.execute(
                "INSERT INTO doc_index "
                "(doc_id, file_path, rag_task, rag_status, rag_updated_at, "
                "kg_task, kg_status, kg_updated_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (doc_id, file_path, rag_task,
                 "indexing" if rag_task else "idle", now if rag_task else None,
                 kg_task, "indexing" if kg_task else "idle", now if kg_task else None,
                 now),
            )


def set_status(doc_id: str, side: str, status: str,
               task_id: str | None = None, error: str | None = None) -> None:
    """Update one side's status (and optionally its task_id).

    ``error`` is a short failure key (``unavailable`` / ``timeout`` /
    ``vanished`` / ``unknown``) recorded alongside a failed-family status so
    the panel can explain the failure in plain words; moving to any other
    status clears it.
    """
    col_task = f"{side}_task"
    col_status = f"{side}_status"
    col_ts = f"{side}_updated_at"
    col_err = f"{side}_error"
    now = _now()
    sets = [f"{col_status}=?", f"{col_ts}=?", "updated_at=?"]
    params: list = [status, now, now]
    if task_id is not None:
        sets.insert(0, f"{col_task}=?")
        params.insert(0, task_id)
    # The error key mirrors the failed state — set together, clear together.
    sets.append(f"{col_err}=?")
    params.append((error or "unknown") if status in ("failed", "error") else None)
    params.append(doc_id)
    with _lock, _connect() as conn:
        conn.execute(
            f"UPDATE doc_index SET {', '.join(sets)} WHERE doc_id=?", params,
        )


def get_row(doc_id: str) -> dict | None:
    """Return one row as a dict, or None."""
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM doc_index WHERE doc_id=?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None


def get_row_by_path(file_path: str) -> dict | None:
    """Return the row matching ``file_path``, or None.

    Used by the delete path: the file is already gone from disk so we
    can't hash it — we find the tracking row by its last known path.
    """
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM doc_index WHERE file_path=?", (file_path,)
        ).fetchone()
        return dict(row) if row else None


def remove(doc_id: str) -> None:
    """Drop a document's tracking row (called after RAG delete succeeds)."""
    with _lock, _connect() as conn:
        conn.execute(
            "DELETE FROM doc_index WHERE doc_id=?", (doc_id,)
        )


def all_rows() -> list[dict]:
    """Every tracking row — used by the boot reconciliation pass that
    compares local status against what the RAG/KG services actually hold."""
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM doc_index").fetchall()
        return [dict(r) for r in rows]


def pending_count() -> int:
    """How many documents still have an indexing task in flight."""
    with _lock, _connect() as conn:
        return conn.execute(
            "SELECT count(*) FROM doc_index "
            "WHERE rag_status='indexing' OR kg_status='indexing'"
        ).fetchone()[0]


def failed_rows() -> list[dict]:
    """All rows with at least one side in 'failed' or 'error'."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM doc_index "
            "WHERE rag_status IN ('failed','error') "
            "OR kg_status IN ('failed','error')"
        ).fetchall()
        return [dict(r) for r in rows]


def stale_tasks() -> list[dict]:
    """Rows still 'indexing' — used on app restart to resume polling."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM doc_index "
            "WHERE rag_status='indexing' OR kg_status='indexing'"
        ).fetchall()
        return [dict(r) for r in rows]


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
    with _lock, _connect() as conn:
        total = conn.execute(
            "SELECT count(*) FROM doc_index"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT count(*) FROM doc_index "
            "WHERE rag_status='indexing' OR kg_status='indexing'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT count(*) FROM doc_index "
            "WHERE rag_status IN ('failed','error') "
            "OR kg_status IN ('failed','error')"
        ).fetchone()[0]
    return {"total": total, "pending": pending, "failed": failed}
