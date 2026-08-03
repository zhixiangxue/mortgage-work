"""SQLite-backed indexing state — the local truth for what's indexed.

Why this exists
---------------
Every document committed to ``products/`` gets indexed by two external services
(RAG for vectors, KG for knowledge graph). Each side returns an async task_id
that we poll to completion. The mapping ``doc_id → (rag_task, kg_task)`` and
each side's status lives here — a single SQLite file at the repo root, next to
``session.json``, never committed (it sits outside every synced scope).

The file is cheap to rebuild: if it's lost, documents can be re-indexed from
``.docs.yaml`` + the products tree. So it's a cache of "where are we in the
pipeline", not a source of truth for what files exist.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import xxhash

# ── doc_id computation (byte-compatible with kg-service and docs_index.py) ──

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
    rag_updated_at TEXT,
    kg_task        TEXT,
    kg_status      TEXT DEFAULT 'idle',
    kg_updated_at  TEXT,
    updated_at     TEXT NOT NULL
);
"""


# ── Connection management ──

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(repo_root: Path) -> Path:
    """Create the SQLite file at the repo root if it doesn't exist.

    Returns the db path. Idempotent — safe to call on every boot.
    """
    global _DB_PATH
    db_path = repo_root / ".index.db"
    _DB_PATH = db_path
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        # Per-side timestamps arrived after the first release — grow old DBs.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(doc_index)")}
        for col in ("rag_updated_at", "kg_updated_at"):
            if col not in cols:
                conn.execute(f"ALTER TABLE doc_index ADD COLUMN {col} TEXT")
    return db_path


def _connect() -> sqlite3.Connection:
    if _DB_PATH is None:
        raise RuntimeError("init_db() has not been called yet")
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


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
               task_id: str | None = None) -> None:
    """Update one side's status (and optionally its task_id)."""
    col_task = f"{side}_task"
    col_status = f"{side}_status"
    col_ts = f"{side}_updated_at"
    if task_id is not None:
        with _lock, _connect() as conn:
            conn.execute(
                f"UPDATE doc_index SET {col_task}=?, {col_status}=?, {col_ts}=?, "
                f"updated_at=? WHERE doc_id=?", (task_id, status, _now(), _now(), doc_id),
            )
    else:
        with _lock, _connect() as conn:
            conn.execute(
                f"UPDATE doc_index SET {col_status}=?, {col_ts}=?, updated_at=? "
                f"WHERE doc_id=?", (status, _now(), _now(), doc_id),
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


def indexing_paths() -> list[str]:
    """File paths (products-relative) that still have work in flight.

    Used to paint the spinner marker on tree nodes so the user can see
    *which* documents are indexing, not just a count.
    """
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT file_path FROM doc_index "
            "WHERE rag_status='indexing' OR kg_status='indexing'"
        ).fetchall()
        return [r["file_path"] for r in rows]


def failed_paths() -> list[str]:
    """File paths (products-relative) with at least one side failed/errored.

    Used to paint the ``!`` marker on tree nodes — clicking it triggers a
    manual retry.
    """
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT file_path FROM doc_index "
            "WHERE rag_status IN ('failed','error') "
            "OR kg_status IN ('failed','error')"
        ).fetchall()
        return [r["file_path"] for r in rows]


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
