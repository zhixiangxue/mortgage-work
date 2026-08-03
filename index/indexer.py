"""Business orchestration for product document indexing.

This module ties together three layers:
  - ``state``    : SQLite-backed status tracking (doc_id → task/status per side)
  - ``rag``      : RAG service HTTP client (vector indexing)
  - ``kg``       : KG service HTTP client (knowledge graph ingestion)

The entry point is :func:`trigger`, called from ``workrepo.flush_sync`` after a
successful git commit. It fires indexing asynchronously so the user's save
flow is never blocked. A background poller watches tasks to completion and
pushes state changes to the frontend via the ``on_indexing_state`` callback.

Design rules
------------
* Indexing failures **never** affect git or the IDE — they're caught and
  recorded as ``status='error'`` (no task_id) or ``status='failed'`` (task
  exists, processing failed).
* Each document is processed independently per side: RAG failure doesn't
  block KG, and vice versa.
* Moves are ignored — content is the identity, and a renamed file keeps its
  doc_id.
"""
from __future__ import annotations

import io
import json
import zipfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import state
from .rag import RagClient
from .kg import KgClient

# Injected by __init__.py at module load time
rag: RagClient = None  # type: ignore[assignment]
kg: KgClient = None  # type: ignore[assignment]

# Source extensions — same set as docs_index.py / kg-service
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".md", ".txt", ".doc", ".docx", ".html", ".htm"}
)

POLL_INTERVAL = 5  # seconds between status checks

# ── State callback (mirrors workrepo.on_sync_state / _emit) ──

_indexing_callback = None


def on_indexing_state(callback):
    """Register a listener: callback(state, detail, indexing, failed).

    States: "busy"(N pending) / "ok" / "failed"(N failed)
    ``indexing`` and ``failed`` are lists of products-relative paths for
    painting markers on tree nodes (spinner / bang).
    """
    global _indexing_callback
    _indexing_callback = callback


def _emit(state: str, detail: str = "",
          indexing: list[str] | None = None,
          failed: list[str] | None = None) -> None:
    if _indexing_callback:
        try:
            _indexing_callback(state, detail, indexing or [], failed or [])
        except Exception:
            pass  # a UI callback error must never break indexing


def _emit_current() -> None:
    """Read SQLite and push the current indexing snapshot to the frontend.

    Called after every state transition (upload, poll result, retry) so the
    status bar count and the tree markers always reflect ground truth.
    """
    s = state.summary()
    idx_files = state.indexing_paths()
    fail_files = state.failed_paths()
    if s["failed"]:
        _emit("failed", str(s["failed"]), idx_files, fail_files)
    elif s["pending"]:
        _emit("busy", str(s["pending"]), idx_files, fail_files)
    else:
        _emit("ok", "", [], [])


# ── Bundle packing (single-file zip + manifest for KG) ──

def build_single_file_zip(org_name: str, file_path: Path) -> bytes:
    """Pack one file + ``_manifest.json`` into a zip for KG ingest.

    KG only accepts archives, so even a single document must be zipped.
    The manifest carries a single ``pages`` entry.
    """
    manifest = {
        "org_name": org_name,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "pages": [
            {
                "file": file_path.name,
                "title": file_path.stem.replace("_", " ").replace("-", " ").title(),
                "source_url": "",
                "chars": 0,  # KG computes this itself
                "attachments": [],
            }
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.write(file_path, file_path.name)
    return buf.getvalue()


# ── Helpers ──

def _org_from_path(relpath: str) -> str:
    """First segment of a products-relative path = lender/agency name."""
    return relpath.split("/", 1)[0] if "/" in relpath else relpath


# RAG requires guideline to be one of these exact enum values.
_GUIDELINE_VALUES = ("FHA", "FannieMae", "FreddieMac", "USDA", "VA")
# Fuzzy matches — keys are lowercased substrings found in path/file names.
_GUIDELINE_HINTS = {
    "fha": "FHA",
    "fannie": "FannieMae", "fennie": "FannieMae", "fanniemae": "FannieMae",
    "freddie": "FreddieMac", "freddiemac": "FreddieMac",
    "usda": "USDA",
    "va ": "VA", "/va": "VA", "\\va": "VA",
}


def _guess_guideline(relpath: str) -> str:
    """Infer the agency guideline from the file path, defaulting to FannieMae.

    Most Non-QM / Non-Conforming product sheets are underwritten against
    FannieMae as the baseline, so it's the safe fallback when the path
    doesn't name an agency explicitly.
    """
    lower = relpath.lower()
    for hint, value in _GUIDELINE_HINTS.items():
        if hint in lower:
            return value
    return "FannieMae"


def _is_source_file(relpath: str) -> bool:
    """Whether this file is in the SOURCE_EXTENSIONS set."""
    return Path(relpath).suffix.lower() in SOURCE_EXTENSIONS


# ── Dataset lifecycle ──

# Set True once ensure_dataset() succeeds. Prevents a race where a commit
# fires trigger() before the RAG collection has been created.
_dataset_ready = threading.Event()


def ensure_dataset() -> None:
    """Create the RAG dataset if it doesn't exist (idempotent). Called on boot.

    Sets ``_dataset_ready`` on success so ``trigger()`` knows it's safe to
    upload. If this fails (service offline), trigger will record 'error' and
    the user can retry later via the reload icon.
    """
    if rag is None:
        return
    try:
        rag.ensure_dataset(description="Mortgage Work product library")
        _dataset_ready.set()
        print("[index] dataset ready")
    except Exception as exc:
        print(f"[index] ensure_dataset failed: {exc}")


# ── Core: index one document to both sides ──

def _index_one(relpath: str, products_root: Path) -> None:
    """Upload one file to RAG (two-step) and KG (two-step), record in SQLite.

    RAG and KG are independent — a failure on one side doesn't block the
    other. Each side catches its own exceptions and records 'error'.
    """
    file_path = products_root / relpath
    if not file_path.is_file() or not _is_source_file(relpath):
        return

    doc_id = state.calculate_file_hash(file_path)
    org_name = _org_from_path(relpath)
    guideline = _guess_guideline(relpath)
    state.upsert(doc_id, relpath)

    # ── RAG: upload → create task ──
    # Wait for dataset to exist (boot might still be creating it). 10s is
    # plenty for a POST that returns 409 when the collection already exists.
    rag_task = None
    if not _dataset_ready.wait(timeout=10):
        print(f"[index] dataset not ready, skipping RAG for {relpath}")
        state.set_status(doc_id, "rag", "error")
    else:
        try:
            result = rag.upload_document(file_path, metadata={
                "lender": org_name, "guideline": guideline, "overlays": [], "tags": []
            })
            rag_doc_id = result.get("doc_id", doc_id)
            is_dup = result.get("is_duplicate", False)
            existing = state.get_row(doc_id)
            if is_dup and existing and existing.get("rag_status") == "done":
                pass  # already fully indexed — skip task creation
            else:
                rag_task = rag.create_task(rag_doc_id)
                state.set_status(doc_id, "rag", "indexing", rag_task)
        except Exception as exc:
            print(f"[index] RAG upload failed for {relpath}: {exc}")
            state.set_status(doc_id, "rag", "error")

    # ── KG: pack zip → upload bundle → ingest ──
    try:
        zip_bytes = build_single_file_zip(org_name, file_path)
        url = kg.upload_bundle(zip_bytes, filename=f"{file_path.stem}.zip")
        kg_task = kg.ingest(url)
        state.set_status(doc_id, "kg", "indexing", kg_task)
    except Exception as exc:
        print(f"[index] KG ingest failed for {relpath}: {exc}")
        state.set_status(doc_id, "kg", "error")


def _delete_one(relpath: str) -> None:
    """Delete a document from both RAG and KG, then remove its tracking row.

    If a task is still running (upload finished, processing in flight), it is
    cancelled first so it doesn't re-create the data we just deleted. The file
    is already gone from disk at this point, so we look up the row by
    ``file_path`` to get the ``doc_id``. If no row exists, there's nothing to
    clean — the file was never indexed.
    """
    row = state.get_row_by_path(relpath)
    if row is None:
        return
    doc_id = row["doc_id"]

    # ── Cancel in-flight tasks before deleting ──
    # A task racing to completion would re-create the data we're about to
    # wipe. Cancel both sides independently — a failure on one shouldn't
    # skip the other.
    if row.get("rag_status") == "indexing" and row.get("rag_task"):
        try:
            rag.cancel_task(row["rag_task"])
        except Exception as exc:
            print(f"[index] RAG cancel failed for {doc_id}: {exc}")
    if row.get("kg_status") == "indexing" and row.get("kg_task"):
        try:
            kg.cancel_task(row["kg_task"])
        except Exception as exc:
            print(f"[index] KG cancel failed for {doc_id}: {exc}")

    # ── Delete from RAG ──
    try:
        rag.delete_document(doc_id)
    except Exception as exc:
        print(f"[index] RAG delete failed for {doc_id}: {exc}")

    # ── Delete from KG ──
    try:
        kg.delete_document(doc_id)
    except Exception as exc:
        print(f"[index] KG delete failed for {doc_id}: {exc}")

    state.remove(doc_id)


# ── Trigger entry point ──

def trigger(scope: str, entries: dict[str, tuple[str, str]]) -> None:
    """Called from flush_sync after a successful git commit.

    ``entries`` = {relpath: (action, source)} where action is add/save/delete/move.
    Only ``products`` scope is processed; other scopes are ignored.
    """
    if scope != "products" or rag is None or kg is None:
        return

    # Collect the actual changes we care about
    to_index: list[str] = []
    to_delete: list[str] = []
    for relpath, (action, _source) in entries.items():
        if not _is_source_file(relpath):
            continue
        if action == "delete":
            to_delete.append(relpath)
        elif action in ("add", "save"):
            to_index.append(relpath)
        # "move" is ignored — content unchanged, doc_id unchanged

    if not to_index and not to_delete:
        return

    threading.Thread(
        target=_run_index, args=(to_index, to_delete), daemon=True
    ).start()


def _run_index(to_index: list[str], to_delete: list[str]) -> None:
    """Background worker: process all changed files, then start polling."""
    from workrepo import local_repo_path

    try:
        products_root = local_repo_path() / "products"
    except Exception as exc:
        print(f"[index] cannot resolve products root: {exc}")
        return

    if to_index:
        # Emit "busy" immediately so the spinner shows before the first
        # (potentially slow) upload completes. Without this, _emit_current()
        # would see zero pending rows and flash the spinner off.
        _emit("busy", str(len(to_index)))
        for relpath in to_index:
            try:
                _index_one(relpath, products_root)
                _emit_current()  # refresh count + tree markers per file
            except Exception as exc:
                print(f"[index] unexpected error indexing {relpath}: {exc}")

    for relpath in to_delete:
        try:
            _delete_one(relpath)
        except Exception as exc:
            print(f"[index] unexpected error deleting {relpath}: {exc}")
    if to_delete:
        _emit_current()

    _poll_tasks()


# ── Poller ──

_poll_lock = threading.Lock()


def _poll_tasks() -> None:
    """Poll all 'indexing' tasks until they settle, updating SQLite + emitting."""
    if not _poll_lock.acquire(blocking=False):
        return  # another poller is already running

    try:
        while True:
            stale = state.stale_tasks()
            if not stale:
                break

            for row in stale:
                doc_id = row["doc_id"]
                # RAG side
                if row.get("rag_status") == "indexing" and row.get("rag_task"):
                    try:
                        st = rag.task_status(row["rag_task"]).upper()
                        if st in ("COMPLETED", "DONE", "SUCCESS"):
                            state.set_status(doc_id, "rag", "done")
                        elif st in ("FAILED", "ERROR"):
                            state.set_status(doc_id, "rag", "failed")
                    except Exception:
                        pass  # network blip — try again next cycle

                # KG side
                if row.get("kg_status") == "indexing" and row.get("kg_task"):
                    try:
                        st = kg.task_status(row["kg_task"]).upper()
                        if st in ("COMPLETED", "DONE", "SUCCESS"):
                            state.set_status(doc_id, "kg", "done")
                        elif st in ("FAILED", "ERROR"):
                            state.set_status(doc_id, "kg", "failed")
                    except Exception:
                        pass

            if state.pending_count() == 0:
                break
            _emit_current()  # refresh mid-poll so markers update live
            time.sleep(POLL_INTERVAL)

        # Emit final state
        _emit_current()
    finally:
        _poll_lock.release()


# ── Manual retry (triggered by frontend reload icon) ──

def retry_failed() -> None:
    """Re-attempt all failed/errored documents.

    * ``failed`` (has task_id) → call the service's retry endpoint.
    * ``error``  (no task_id)  → re-run the full upload pipeline.
    """
    from workrepo import local_repo_path

    rows = state.failed_rows()
    if not rows:
        return

    try:
        products_root = local_repo_path() / "products"
    except Exception as exc:
        print(f"[index] cannot resolve products root: {exc}")
        return

    _emit_current()

    # Make sure the RAG dataset exists before retrying — the original failure
    # might have been because the service was down at boot time.
    if not _dataset_ready.is_set():
        ensure_dataset()

    for row in rows:
        doc_id = row["doc_id"]
        relpath = row["file_path"]

        # RAG
        if row["rag_status"] == "failed" and row.get("rag_task"):
            try:
                rag.retry_task(row["rag_task"])
                state.set_status(doc_id, "rag", "indexing")
            except Exception as exc:
                print(f"[index] RAG retry failed for {doc_id}: {exc}")
        elif row["rag_status"] == "error":
            # Re-run full upload
            try:
                _index_one(relpath, products_root)
            except Exception as exc:
                print(f"[index] RAG re-index failed for {relpath}: {exc}")

        # KG
        if row["kg_status"] == "failed" and row.get("kg_task"):
            try:
                kg.retry_task(row["kg_task"])
                state.set_status(doc_id, "kg", "indexing")
            except Exception as exc:
                print(f"[index] KG retry failed for {doc_id}: {exc}")
        elif row["kg_status"] == "error":
            try:
                _index_one(relpath, products_root)
            except Exception as exc:
                print(f"[index] KG re-index failed for {relpath}: {exc}")

    _poll_tasks()


# ── App restart recovery ──

def recover_stale() -> None:
    """On app boot, resume polling for tasks left 'indexing' by a crash.

    Also re-checks 'error' rows in case the service was down and is now back.
    """
    stale = state.stale_tasks()
    failed = state.failed_rows()
    if not stale and not failed:
        return

    if stale:
        print(f"[index] recovering {len(stale)} in-flight tasks")
        _poll_tasks()

    # Error rows: the service might be back online now — re-index them
    errored = [r for r in failed if r.get("rag_status") == "error"
               or r.get("kg_status") == "error"]
    if errored:
        print(f"[index] retrying {len(errored)} previously-errored documents")
        retry_failed()


# ── Summary for frontend ──

def summary() -> dict:
    """Compact status snapshot: {total, pending, failed}."""
    return state.summary()
