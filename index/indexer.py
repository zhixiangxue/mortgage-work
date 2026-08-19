"""Business orchestration for product document indexing.

This module ties together three layers:
  - ``state``       : SQLite-backed status tracking (doc_id → task/status per side)
  - ``integration`` : RAG / KG service HTTP clients (vectors + knowledge graph)

The entry point is :func:`trigger`, called from ``workrepo.flush_sync`` after a
successful git commit. It fires indexing asynchronously so the user's save
flow is never blocked. A background poller watches tasks to completion and
pushes state changes to the frontend via the ``on_indexing_state`` callback.

Design rules
------------
* Indexing failures **never** affect git or the IDE — they're caught and
  recorded as ``status='error'`` (no task_id) or ``status='failed'`` (task
  exists, processing failed).
* A task the service reports as CANCELLED settles to ``status='cancelled'``
  — terminal but not a failure: it carries no retry chip and no tree
  marker, since a deliberate cancel means "don't index this", not "try
  again".
* A task still ``indexing`` after ``TASK_TIMEOUT`` (2h) is abandoned —
  cancelled server-side and marked ``failed`` — so a wedged worker queue
  can't pin the UI spinner forever. Same for tasks the service no longer
  knows (404): polling can never settle, so they fail fast and the retry
  chip re-uploads.
* Each document is processed independently per side: RAG failure doesn't
  block KG, and vice versa.
* Moves are ignored — content is the identity, and a renamed file keeps its
  doc_id.
* The services are derived caches and can be wiped/rebuilt at any time, so
  boot runs :func:`sync_with_server` — one reconciling pass against disk
  and the data plane — before resuming polls and retries.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import state
from integration import KgClient, RagClient

log = logging.getLogger(__name__)

# Injected by __init__.py at module load time
rag: RagClient = None  # type: ignore[assignment]
kg: KgClient = None  # type: ignore[assignment]

# Source extensions — same set as kg-service
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".md", ".txt", ".doc", ".docx", ".html", ".htm"}
)

POLL_INTERVAL = 5  # seconds between status checks

# A task parked in 'indexing' longer than this is abandoned: cancelled on the
# service (best effort) and marked failed locally. Real processing finishes
# in minutes; two hours means the worker queue is wedged and no poll cycle
# will ever settle it.
TASK_TIMEOUT = 2 * 60 * 60

# ── State callback (mirrors workrepo.on_sync_state / _emit) ──

_indexing_callback = None


def on_indexing_state(callback):
    """Register a listener: callback(summary, rows).

    ``summary`` is the knowledge_summary dict {total, processing, failed,
    pending, canceled} driving the status-bar chip; ``rows`` is panel_rows()
    — the full per-document table for the Knowledge Base panel. Every push
    carries both, so the chip and the panel can never disagree.
    """
    global _indexing_callback
    _indexing_callback = callback


def _emit_current(processing_override: int | None = None) -> None:
    """Read SQLite and push the current knowledge snapshot to the frontend.

    Called after every state transition (upload, poll result, retry) so the
    status-bar chip and the panel always reflect ground truth.

    ``processing_override`` claims in-flight work before SQLite knows about
    it — a batch thread counts its files here so the chip's number never
    dips off between serial uploads. The override only ever RAISES the
    count; settled rows still show through.
    """
    if _indexing_callback is None:
        return
    s = state.knowledge_summary()
    if processing_override is not None:
        s["processing"] = max(s["processing"], processing_override)
    try:
        _indexing_callback(s, state.panel_rows())
    except Exception:
        pass  # a UI callback error must never break indexing


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


def _error_key(exc: Exception) -> str:
    """Classify an exception into the short failure key the panel explains
    in plain words: ``unavailable`` / ``vanished`` / ``unknown``.
    (``timeout`` is only ever written by :func:`_abandon`.)"""
    if isinstance(exc, httpx.HTTPStatusError):
        return "vanished" if exc.response.status_code == 404 else "unavailable"
    if isinstance(exc, httpx.HTTPError):
        return "unavailable"  # connect / timeout / transport — unreachable
    return "unknown"


# ── Service lifecycle ──

# Set True once ensure_dataset() succeeds. Prevents a race where a commit
# fires trigger() before the RAG collection has been created. KG needs no
# such gate — FalkorDB creates graphs implicitly on first ingest.
_dataset_ready = threading.Event()


def ensure_dataset() -> None:
    """Create the RAG dataset and KG graph if missing (idempotent). Boot call.

    Sets ``_dataset_ready`` on success so ``trigger()`` knows it's safe to
    upload. If this fails (service offline), trigger will record 'error' and
    the user can retry later via the reload icon. The KG graph check is best
    effort — a failure there never blocks RAG uploads.
    """
    if rag is None:
        return
    try:
        rag.ensure_dataset(description="Mortgage Work product library")
        _dataset_ready.set()
        log.info("dataset ready")
    except Exception as exc:
        log.error("ensure_dataset failed: %s", exc)
    try:
        kg.ensure_graph()
        log.info("graph ready")
    except Exception as exc:
        log.error("ensure_graph failed: %s", exc)


# ── Core: index one document to both sides ──

def _remove_from_services(row: dict) -> None:
    """Best-effort: cancel in-flight tasks and drop stored data for one row.

    The single deletion primitive for every path where a document must
    disappear downstream of the cursor: watcher-driven deletes, superseded
    versions, boot pruning. In-flight tasks are cancelled first so a task
    racing to completion can't re-create the data being wiped. Each step is
    independent — a failure on one side never skips the others.
    """
    doc_id = row["doc_id"]
    if row.get("rag_status") == "indexing" and row.get("rag_task") and rag is not None:
        try:
            rag.cancel_task(row["rag_task"])
        except Exception as exc:
            log.warning("cancel failed during removal · %s: %s", doc_id, exc)
    if row.get("kg_status") == "indexing" and row.get("kg_task") and kg is not None:
        try:
            kg.cancel_task(row["kg_task"])
        except Exception as exc:
            log.warning("cancel failed during removal · %s: %s", doc_id, exc)
    if rag is not None:
        try:
            rag.delete_document(doc_id)
        except Exception as exc:
            log.warning("RAG delete failed during removal · %s: %s", doc_id, exc)
    if kg is not None:
        try:
            kg.delete_document(doc_id)
        except Exception as exc:
            log.warning("KG delete failed during removal · %s: %s", doc_id, exc)


def _retire_superseded(relpath: str, new_doc_id: str) -> None:
    """Drop the tracking row (and server data) of a file's previous version.

    Content is the identity: when a file is saved with new content it gets a
    NEW doc_id, and the old version's row would otherwise linger in SQLite
    forever while its document stays searchable server-side — the classic
    local-vs-server drift. Side failures are swallowed: the new version's
    upload proceeds regardless.
    """
    prev = state.get_row_by_path(relpath)
    if prev is None or prev["doc_id"] == new_doc_id:
        return
    log.info("superseded version · %s · old doc_id=%s → new doc_id=%s",
             relpath, prev["doc_id"], new_doc_id)
    _remove_from_services(prev)
    state.remove(prev["doc_id"])


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
    _retire_superseded(relpath, doc_id)
    state.upsert(doc_id, relpath)
    log.info("index start · %s · doc_id=%s", relpath, doc_id)

    _index_rag(doc_id, relpath, file_path, org_name, _guess_guideline(relpath))
    _index_kg(doc_id, relpath, file_path, org_name)


def _index_rag(doc_id: str, relpath: str, file_path: Path,
               org_name: str, guideline: str) -> None:
    """RAG two-step upload; records 'indexing' or 'error' on the rag side."""
    # Wait for dataset to exist (boot might still be creating it). 10s is
    # plenty for a POST that returns 409 when the collection already exists.
    if not _dataset_ready.wait(timeout=10):
        log.warning("dataset not ready, skipping RAG for %s", relpath)
        state.set_status(doc_id, "rag", "error", error="unavailable")
        return
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
        log.error("RAG upload failed for %s: %s", relpath, exc)
        state.set_status(doc_id, "rag", "error", error=_error_key(exc))


def _index_kg(doc_id: str, relpath: str, file_path: Path, org_name: str) -> None:
    """KG two-step ingest; records 'indexing' or 'error' on the kg side."""
    try:
        zip_bytes = build_single_file_zip(org_name, file_path)
        url = kg.upload_bundle(zip_bytes, filename=f"{file_path.stem}.zip")
        kg_task = kg.ingest(url)
        state.set_status(doc_id, "kg", "indexing", kg_task)
    except Exception as exc:
        log.error("KG ingest failed for %s: %s", relpath, exc)
        state.set_status(doc_id, "kg", "error", error=_error_key(exc))


def _delete_one(relpath: str) -> None:
    """Delete a document from both services, then remove its tracking row.

    Watcher-driven delete: the file is already gone from disk at this point,
    so we look up the row by ``file_path`` to get the ``doc_id``. If no row
    exists, there's nothing to clean — the file was never indexed.
    """
    row = state.get_row_by_path(relpath)
    if row is None:
        return
    _remove_from_services(row)
    state.remove(row["doc_id"])


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
        log.error("cannot resolve products root: %s", exc)
        return

    if to_index:
        log.info("indexing batch started · %d file(s): %s",
                 len(to_index), ", ".join(to_index))
        # Claim the in-flight count immediately so the chip shows before the
        # first (potentially slow) upload completes.
        _emit_current(processing_override=len(to_index))
        for relpath in to_index:
            try:
                _index_one(relpath, products_root)
                _emit_current()  # refresh count + panel rows per file
            except Exception:
                log.exception("unexpected error indexing %s", relpath)

    for relpath in to_delete:
        try:
            _delete_one(relpath)
        except Exception:
            log.exception("unexpected error deleting %s", relpath)
    if to_delete:
        _emit_current()

    _poll_tasks()


# ── Poller ──

_poll_lock = threading.Lock()


def _age_seconds(row: dict, side: str) -> float:
    """Seconds since this side last entered 'indexing'.

    Per-side timestamp; falls back to the row-wide ``updated_at`` for rows
    written before the per-side columns existed. Unparseable clocks return
    0 — we never abandon a task over bad metadata.
    """
    raw = row.get(f"{side}_updated_at") or row.get("updated_at")
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(raw)).total_seconds()
    except Exception:
        return 0.0


def _abandon(doc_id: str, side: str, task_id: str, relpath: str) -> None:
    """Give up on a task parked in 'indexing' beyond TASK_TIMEOUT.

    Cancels server-side (best effort — clears the wedged queue entry if the
    service is alive) and marks the side failed locally so the UI shows the
    retry chip instead of spinning forever.
    """
    client = rag if side == "rag" else kg
    try:
        client.cancel_task(task_id)
    except Exception as exc:
        log.error("%s cancel after timeout failed for %s: %s",
                  side.upper(), doc_id, exc)
    state.set_status(doc_id, side, "failed", error="timeout")
    log.warning("%s indexing timed out · %s · task=%s — cancelled, marked failed",
                side.upper(), relpath, task_id)


def _poll_tasks() -> None:
    """Poll all 'indexing' tasks until they settle, updating SQLite + emitting."""
    if not _poll_lock.acquire(blocking=False):
        return  # another poller is already running

    try:
        while True:
            stale = state.stale_tasks()
            if not stale:
                break

            transitions = 0
            for row in stale:
                doc_id = row["doc_id"]
                relpath = row["file_path"]
                for side, client in (("rag", rag), ("kg", kg)):
                    if row.get(f"{side}_status") != "indexing" or not row.get(f"{side}_task"):
                        continue
                    task = row[f"{side}_task"]
                    if _age_seconds(row, side) > TASK_TIMEOUT:
                        _abandon(doc_id, side, task, relpath)
                        transitions += 1
                        continue
                    try:
                        st = client.task_status(task).upper()
                        if st in ("COMPLETED", "DONE", "SUCCESS"):
                            state.set_status(doc_id, side, "done")
                            transitions += 1
                            log.info("%s task done · %s · task=%s",
                                     side.upper(), relpath, task)
                        elif st in ("FAILED", "ERROR"):
                            state.set_status(doc_id, side, "failed", error="unknown")
                            transitions += 1
                            log.warning("%s task settled as %s · %s · task=%s — marked failed",
                                        side.upper(), st, relpath, task)
                        elif st == "CANCELLED":
                            # Cancelled on purpose (user or another actor),
                            # not a fault — terminal but NOT 'failed': no
                            # retry chip, the node goes back to its plain
                            # badge. Contrast _abandon(), where *we* give up
                            # on a wedged task and deliberately keep the
                            # retry path.
                            state.set_status(doc_id, side, "cancelled")
                            transitions += 1
                            log.info("%s task cancelled · %s · task=%s",
                                     side.upper(), relpath, task)
                        # PENDING/PROCESSING: keep polling silently
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 404:
                            # Service lost the task (restart/purge) — no poll
                            # cycle can ever settle it; fail so retry can
                            # re-upload.
                            state.set_status(doc_id, side, "failed", error="vanished")
                            transitions += 1
                            log.warning("%s task vanished server-side · %s · task=%s — marked failed",
                                        side.upper(), relpath, task)
                        else:
                            log.debug("%s poll transient HTTP %s · task=%s — next cycle",
                                      side.upper(), exc.response.status_code, task)
                    except Exception as exc:
                        # network blip — try again next cycle
                        log.debug("%s poll error · task=%s · %s — next cycle",
                                  side.upper(), task, exc)

            if state.pending_count() == 0:
                break
            # Push only when something actually changed — a quiet cycle has
            # nothing new to paint, and unconditional pushes redraw identical
            # markers every 5s for no reason.
            if transitions:
                _emit_current()
            time.sleep(POLL_INTERVAL)

        # Emit final state
        _emit_current()
        s = state.summary()
        log.info("poll settled · total=%d pending=%d failed=%d",
                 s["total"], s["pending"], s["failed"])
    finally:
        _poll_lock.release()


# ── Manual retry ──

def retry_failed() -> int:
    """Re-attempt all failed/errored documents, side by side.

    * ``failed`` (has task_id) → service retry endpoint; if the task no
      longer exists server-side (404), fall back to a full re-upload.
    * ``error``  (no task_id)  → full re-upload pipeline for that side.

    Returns the number of documents picked up (0 = nothing to retry). This
    bulk path serves boot self-healing (sync_with_server); the Knowledge
    Base panel retries per side through :func:`retry_one` instead. The work
    runs in a background thread; polling takes over once every side has
    been re-submitted.
    """
    rows = state.failed_rows()
    if not rows:
        log.info("retry requested — no failed documents")
        return 0

    from workrepo import local_repo_path
    try:
        products_root = local_repo_path() / "products"
    except Exception as exc:
        log.error("retry aborted — cannot resolve products root: %s", exc)
        return 0

    log.info("retry started · %d document(s): %s",
             len(rows), ", ".join(r["file_path"] for r in rows))
    # Claim the work BEFORE the first network call — leaving the chip on its
    # old counts until the first upload returns reads as a dead button when
    # the service answers fast (or is still down).
    _emit_current(processing_override=len(rows))
    threading.Thread(
        target=_do_retry, args=(rows, products_root), daemon=True
    ).start()
    return len(rows)


def _do_retry(rows: list[dict], products_root: Path) -> None:
    """Background half of retry_failed: re-submit each side, then poll."""
    # Make sure the RAG dataset exists before retrying — the original failure
    # might have been because the service was down at boot time.
    if not _dataset_ready.is_set():
        ensure_dataset()

    for r in rows:
        # Re-read per row: the poller may have settled a side since the
        # snapshot was taken, and re-submitting off a stale status would
        # duplicate work on the servers.
        fresh = state.get_row(r["doc_id"])
        if fresh is None:
            continue  # retired or pruned meanwhile
        _retry_side(fresh, "rag", products_root)
        _retry_side(fresh, "kg", products_root)
        # Per-row refresh so the UI tracks progress while retries grind
        # through many files — without this the chip sits frozen between
        # the first emit and _poll_tasks, reading as "click did nothing".
        _emit_current()

    _poll_tasks()


def _retry_side(row: dict, side: str, products_root: Path) -> None:
    """Re-attempt one side of a failed/errored row (see retry_failed)."""
    doc_id, relpath = row["doc_id"], row["file_path"]
    status, task = row[f"{side}_status"], row.get(f"{side}_task")
    client = rag if side == "rag" else kg

    if status == "failed" and task:
        try:
            client.retry_task(task)
            state.set_status(doc_id, side, "indexing")
            return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                log.error("%s retry failed for %s: %s", side.upper(), doc_id, exc)
                return
            log.warning("%s task vanished server-side · %s — re-uploading",
                        side.upper(), relpath)
        except Exception as exc:
            log.error("%s retry failed for %s: %s", side.upper(), doc_id, exc)
            return
    elif status != "error":
        return

    # Full (re-)upload for this side only
    file_path = products_root / relpath
    if not file_path.is_file() or not _is_source_file(relpath):
        return
    org_name = _org_from_path(relpath)
    if side == "rag":
        _index_rag(doc_id, relpath, file_path, org_name, _guess_guideline(relpath))
    else:
        _index_kg(doc_id, relpath, file_path, org_name)


def retry_one(doc_id: str, side: str) -> str:
    """Retry exactly one side of one document — the Knowledge Base panel's
    failed-chip click.

    Same semantics as the bulk path: a side with a task_id calls the service
    retry endpoint (404 falls back to a full re-upload); a side without one
    re-uploads from disk. Runs synchronously (upload + task creation are
    fast; the slow part is server processing) and returns the side's fresh
    DISPLAY status — ``processing`` when the re-submission took, still
    ``failed`` when the service refused, so the frontend can bounce its
    optimistic chip and toast the reason. Unknown doc/side raise — the API
    layer turns that into an error payload.
    """
    if side not in ("rag", "kg"):
        raise ValueError(f"unknown side: {side!r}")
    row = state.get_row(doc_id)
    if row is None:
        raise ValueError(f"unknown document: {doc_id}")
    relpath = row["file_path"]
    if row.get(f"{side}_status") not in ("failed", "error"):
        # Nothing to retry on this side — report truth, never pretend.
        return state.display_status(row.get(f"{side}_status"))

    log.info("retry one · %s · %s side · doc_id=%s", relpath, side.upper(), doc_id)
    # The original failure may have been "service down at boot" — the RAG
    # dataset gate is re-checked before touching that side.
    if side == "rag" and not _dataset_ready.is_set():
        ensure_dataset()

    from workrepo import local_repo_path
    products_root = local_repo_path() / "products"
    _retry_side(row, side, products_root)

    fresh = state.get_row(doc_id) or {}
    _emit_current()
    # The re-submitted task needs a poller; _poll_lock makes this a no-op
    # when one is already running. Never block the API call on polling.
    threading.Thread(target=_poll_tasks, daemon=True).start()
    return state.display_status(fresh.get(f"{side}_status"))


# ── Boot sync: one pass aligning local rows with truth ──
#
# Truth flows ONE WAY: disk (products/, git) → cursor (SQLite) → services
# (RAG/KG, derived caches). Disk and services are never compared directly —
# every check goes through the cursor. Boot sync walks the two edges of
# that pipeline separately:
#
#   edge 1, disk → cursor : rows whose file left disk are pruned;
#                           files the cursor missed are adopted
#   edge 2, cursor → services : per-state matrix below
#
# The TASK plane of edge 2 is owned by _poll_tasks — this pass only adds
# what the task API cannot answer:
#
#   local state   truth probe                 action
#   ───────────   ─────────────────────────   ────────────────────────
#   indexing      task API (task_status)      resume polling (poller)
#   failed/error  —                           re-upload      (retry)
#   cancelled     —                           skip (terminal decision)
#   done          DATA plane: still present?  re-queue if not (this pass)
#
# Why 'done' needs a data-plane probe: a settled task answers COMPLETED
# forever, even after the backing store is wiped (FalkorDB restarted without
# persistence, dataset re-created). "local done + server empty" is exactly
# the silent loss this sync exists to catch.
#
# KG note: the KG API exposes node counts but no document listing (a precise
# GET /{graph}/documents does not exist yet), so its wipe verdict stays
# conservative — only "graph present AND empty" re-queues. See
# _check_kg_data_plane.

def _prune_gone_files() -> list[dict]:
    """Edge 1 cleanup (disk → DB): drop rows whose file left products/.

    Covers deletions the watcher never processed (made while the app was
    closed, from another machine, etc.). The removal propagates down the
    whole pipeline — server data included — otherwise a row disappears but
    its document stays searchable forever. Returns the surviving rows.
    """
    try:
        from workrepo import local_repo_path
        products_root = local_repo_path() / "products"
    except Exception as exc:
        log.warning("sync: products root unavailable — prune skipped (%s)", exc)
        return state.all_rows()
    if not products_root.is_dir():
        # A missing products/ is not evidence that every file was deleted —
        # refuse to act rather than mass-prune off a bad signal.
        log.warning("sync: products/ missing — prune skipped")
        return state.all_rows()
    rows = state.all_rows()
    gone = [r for r in rows if not (products_root / r["file_path"]).is_file()]
    for r in gone:
        log.info("pruned tracking row — file no longer on disk · %s · doc_id=%s",
                 r["file_path"], r["doc_id"])
        _remove_from_services(r)
        state.remove(r["doc_id"])
    return state.all_rows() if gone else rows


def _adopt_missing_files() -> None:
    """Edge 1 completion (disk → cursor): create rows for files we missed.

    The iron guarantee — every committed source file owns a tracking row —
    has three holes this pass plugs: the app crashed between commit and row
    creation, the DB file itself was lost, or files landed via git pull
    while the app was closed. Adopted rows start ``error`` on both sides so
    the boot re-upload below (the normal retry channel) does the real work —
    no separate "catch-up" pipeline. A file whose row exists under a stale
    doc_id (content changed while we weren't watching) is retired and
    re-adopted exactly like the watcher path would.
    """
    try:
        from workrepo import local_repo_path
        products_root = local_repo_path() / "products"
    except Exception as exc:
        log.warning("sync: products root unavailable — adopt skipped (%s)", exc)
        return
    if not products_root.is_dir():
        return  # same refusal as the prune pass — absence is not evidence

    known_paths = {r["file_path"]: r for r in state.all_rows()}
    adopted = 0
    for path in sorted(products_root.rglob("*")):
        if not path.is_file():
            continue
        relpath = path.relative_to(products_root).as_posix()
        if not _is_source_file(relpath):
            continue
        doc_id = state.calculate_file_hash(path)
        if state.get_row(doc_id) is not None:
            continue  # already tracked — the normal path covered it
        prev = known_paths.pop(relpath, None)
        if prev is not None:
            log.info("superseded while closed · %s · old doc_id=%s → new doc_id=%s",
                     relpath, prev["doc_id"], doc_id)
            _remove_from_services(prev)
            state.remove(prev["doc_id"])
        state.upsert(doc_id, relpath)
        state.set_status(doc_id, "rag", "error", error="unknown")
        state.set_status(doc_id, "kg", "error", error="unknown")
        adopted += 1
        log.info("adopted missing file · %s · doc_id=%s", relpath, doc_id)
    if adopted:
        log.info("sync: adopted %d file(s) the cursor had missed", adopted)
        _emit_current()


def _check_rag_data_plane(rows: list[dict]) -> None:
    """Done rows must still exist in the RAG dataset; re-queue the missing.

    Exact diff — RAG exposes a document listing. A 404 is itself a verdict:
    dataset gone means every locally-done rag side is stale. Any other
    failure yields no verdict (re-run at next boot).
    """
    done = [r for r in rows if r.get("rag_status") == "done"]
    if not done:
        return
    try:
        server_docs = {d.get("doc_id") for d in rag.list_documents()}
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            log.warning("sync: RAG listing failed — drift check skipped (%s)", exc)
            return
        server_docs = set()  # dataset itself gone → all done rows are stale
    except Exception as exc:
        log.warning("sync: RAG listing failed — drift check skipped (%s)", exc)
        return
    missing = [r for r in done if r["doc_id"] not in server_docs]
    for r in missing:
        state.set_status(r["doc_id"], "rag", "error", error="vanished")
        log.warning("RAG drift · %s · doc_id=%s done locally, absent server-side "
                    "— re-queued", r["file_path"], r["doc_id"])
    if missing:
        _emit_current()
    else:
        log.info("sync: %d done row(s) verified present in RAG dataset", len(done))


def _check_kg_data_plane(rows: list[dict]) -> None:
    """Conservative wipe detection for KG.

    Only "graph present AND empty" proves a wipe. "Graph absent" is NOT a
    wipe verdict: this system has a documented failure mode where the
    service registry loses the graph while FalkorDB still holds the data —
    re-ingesting on top of that would duplicate nodes. ``ensure_graph``
    runs first so a freshly-wiped FalkorDB (whose graph boot hasn't been
    re-created yet) lands in the detectable present-but-empty branch.
    """
    done = [r for r in rows if r.get("kg_status") == "done"]
    if not done:
        return
    try:
        kg.ensure_graph()  # idempotent — absorbs the race with boot graph creation
        info = kg.graph_info()
    except Exception as exc:
        log.warning("sync: KG graph probe failed — drift check skipped (%s)", exc)
        return
    if info is None:
        log.warning("sync: KG graph absent from service registry while %d row(s) "
                    "done locally — ambiguous (registry loss fakes this); no action",
                    len(done))
        return
    if int(info.get("node_count") or 0) == 0:
        for r in done:
            state.set_status(r["doc_id"], "kg", "error", error="vanished")
        log.warning("KG drift · graph present but empty while %d row(s) done "
                    "locally — all kg sides re-queued", len(done))
        _emit_current()
    else:
        log.info("sync: KG graph present (%s nodes) — coarse check passed",
                 info.get("node_count"))


def sync_with_server() -> None:
    """Boot reconciler: align local rows with truth, then resume the work.

    Runs once at startup — the app-closed window is the only time drift can
    accumulate unwatched. Steps: prune gone files → adopt files the cursor
    missed (the iron guarantee's safety net) → verify done rows against the
    data plane (RAG exact, KG conservative) → resume task polling →
    re-upload everything failed/errored, including what adopt and the
    data-plane checks just queued. Probes are best-effort: no service
    answer means no verdict, and the check simply re-runs at next boot.
    """
    rows = _prune_gone_files()
    _adopt_missing_files()
    rows = state.all_rows()
    if rag is not None:
        _check_rag_data_plane(rows)
    if kg is not None:
        _check_kg_data_plane(rows)

    stale = state.stale_tasks()
    if stale:
        log.info("sync: resuming poll for %d in-flight task row(s)", len(stale))
        _poll_tasks()

    failed = state.failed_rows()
    if failed:
        log.info("sync: re-uploading %d failed/errored document(s)", len(failed))
        retry_failed()
    else:
        log.info("sync: index state aligned — nothing to resume or re-upload")
        # Nothing else will emit today — hand the boot snapshot to the
        # status-bar chip right here.
        _emit_current()


# ── Snapshots for frontend ──

def knowledge_summary() -> dict:
    """Document-level counts {total, processing, failed, pending, canceled}
    — drives the status-bar chip."""
    return state.knowledge_summary()


def panel_rows() -> list[dict]:
    """Every tracking row in the panel's vocabulary — the Knowledge Base
    panel's data source."""
    return state.panel_rows()
