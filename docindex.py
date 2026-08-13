"""Content-addressed file index for the work repo.

Maintains ``products/index.jsonl`` — a flat NDJSON lookup table mapping
``doc_id`` (xxh64 content hash) to every path that file lives at. Updated
incrementally on every file CRUD inside ``flush_sync``, so the index change
rides in the same commit as the file change it reflects.

The hash is byte-compatible with:

* ``index/state.py::calculate_file_hash`` — the RAG/KG indexing pipeline
* ``cas/hasher.py::compute_file_hash`` — the S3 content-addressed store

All three stream the file through ``xxhash.xxh64`` in 8 KB chunks; xxhash is
a pure sequential streaming hash, so the chunk size is irrelevant to the
digest.

Boot calls ``init()`` once the repo is ready; ``flush_sync`` calls
``update()`` per scope before staging; agents call ``lookup()`` to resolve a
doc_id they saw in context back to a concrete file path.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import xxhash

log = logging.getLogger(__name__)

# The index file lives under products/ — it's reference data, not client work.
INDEX_RELPATH = "products/index.jsonl"

# Directories whose files are indexed. These mirror the synced scopes in
# workrepo._split_scope / _scope_prefix.
_SCAN_DIRS = ("clients", "products", "conversations")

# In-memory state — two indexes over the same record set:
#   _records:   repo-relative path → full record dict
#   _by_doc_id: doc_id → set of repo-relative paths (reverse lookup)
_records: dict[str, dict] = {}
_by_doc_id: dict[str, set[str]] = {}

_root: Path | None = None
_lock = threading.Lock()


# ── Hash (identical to index/state.py and cas/hasher.py) ──

def _hash_file(full_path: Path) -> str:
    """xxh64 hex digest of the file content."""
    h = xxhash.xxh64()
    with open(full_path, "rb") as fp:
        while chunk := fp.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Boot ──

def init(root: Path) -> None:
    """Load the existing index into memory, or rebuild from disk if missing.

    Call once on boot after the repo is ready. Idempotent. Refuses to run
    while the checkout is still landing: writing products/index.jsonl
    mid-clone makes git's checkout refuse to finish ("untracked file would
    be overwritten"), so callers that race the first clone degrade to
    "index not loaded yet" and retry on the next call.
    """
    global _root
    _root = root
    if not (root / "clients").is_dir():
        log.info("docindex: checkout not ready, skipping init")
        return
    index_path = root / INDEX_RELPATH
    if not index_path.is_file():
        log.info("docindex: index file missing, rebuilding from disk")
        rebuild(root)
        return
    _load(root)


def _load(root: Path) -> None:
    """Parse index.jsonl into the in-memory indexes."""
    with _lock:
        _records.clear()
        _by_doc_id.clear()
        index_path = root / INDEX_RELPATH
        raw = index_path.read_text(encoding="utf-8")
        for line_no, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                log.warning("docindex: skipping unparseable line %d", line_no)
                continue
            path = rec.get("path")
            if not path:
                continue
            _records[path] = rec
            _by_doc_id.setdefault(rec["doc_id"], set()).add(path)
        log.info("docindex: loaded %d records", len(_records))


# ── Full rebuild ──

def rebuild(root: Path) -> None:
    """Scan every file under the synced directories and rebuild the index.

    Used on first boot (no index file yet) or as a manual safety net.
    """
    with _lock:
        _records.clear()
        _by_doc_id.clear()
        count = 0
        for scope_dir in _SCAN_DIRS:
            base = root / scope_dir
            if not base.is_dir():
                continue
            for f in base.rglob("*"):
                if not f.is_file() or f.name.startswith("."):
                    continue
                rp = f.relative_to(root).as_posix()
                if rp == INDEX_RELPATH:
                    continue
                try:
                    doc_id = _hash_file(f)
                except OSError as exc:
                    log.warning("docindex: cannot hash %s: %s", rp, exc)
                    continue
                _records[rp] = {
                    "doc_id": doc_id,
                    "path": rp,
                    "size": f.stat().st_size,
                    "indexed_at": _now_iso(),
                }
                _by_doc_id.setdefault(doc_id, set()).add(rp)
                count += 1
        _write(root)
        log.info("docindex: rebuilt with %d records", count)


# ── Persistence ──

def _write(root: Path) -> None:
    """Rewrite index.jsonl from the in-memory records (sorted by path)."""
    index_path = root / INDEX_RELPATH
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(_records[p], ensure_ascii=False)
             for p in sorted(_records)]
    body = "\n".join(lines)
    if lines:
        body += "\n"
    index_path.write_text(body, encoding="utf-8")


# ── Single-record primitives (callers must hold _lock) ──

def _upsert(repo_path: str, full_path: Path) -> bool:
    """Hash the file and insert/update its record. Returns True if the
    in-memory state changed (new path or changed content)."""
    try:
        doc_id = _hash_file(full_path)
    except OSError as exc:
        log.warning("docindex: cannot hash %s: %s", repo_path, exc)
        return False
    existing = _records.get(repo_path)
    if existing and existing["doc_id"] == doc_id:
        return False  # content unchanged — no update needed
    _records[repo_path] = {
        "doc_id": doc_id,
        "path": repo_path,
        "size": full_path.stat().st_size,
        "indexed_at": _now_iso(),
    }
    _by_doc_id.setdefault(doc_id, set()).add(repo_path)
    return True


def _remove(repo_path: str) -> bool:
    """Remove a record by path. Returns True if a record was actually removed."""
    rec = _records.pop(repo_path, None)
    if not rec:
        return False
    paths = _by_doc_id.get(rec["doc_id"])
    if paths:
        paths.discard(repo_path)
        if not paths:
            del _by_doc_id[rec["doc_id"]]
    return True


def _index_path(root: Path, repo_path: str) -> bool:
    """Index one repo-relative path: hash it if it's a file, scan if a
    directory, remove if gone. Returns True if anything changed."""
    full = root / repo_path
    if full.is_file():
        if full.name.startswith(".") or repo_path == INDEX_RELPATH:
            return False
        return _upsert(repo_path, full)
    if full.is_dir():
        changed = False
        for f in full.rglob("*"):
            if not f.is_file() or f.name.startswith("."):
                continue
            rp = f.relative_to(root).as_posix()
            if rp == INDEX_RELPATH:
                continue
            if _upsert(rp, f):
                changed = True
        return changed
    # Not a file, not a dir — stale record or placeholder like "client folder"
    return _remove(repo_path)


# ── Incremental update (called from workrepo.flush_sync) ──

def _scope_prefix(scope: str) -> str:
    """Mirror of workrepo._scope_prefix — products/conversations are top-level,
    everything else is clients/<slug>."""
    if scope in ("products", "conversations"):
        return scope
    return f"clients/{scope}"


def update(root: Path, scope: str, entries: dict[str, tuple[str, str]]) -> bool:
    """Apply a batch of file changes to the index.

    Called from ``flush_sync`` *before* ``git add``, so the index file change
    lands in the same commit as the file changes it reflects. ``entries`` has
    the same shape as workrepo's pending queue: ``{entry: (action, source)}``,
    where entry may be a plain path, ``"old → new"`` (move/rename), or
    ``"path @ sha"`` (restore).

    Returns True if the index file was modified.
    """
    prefix = _scope_prefix(scope)
    changed = False

    with _lock:
        for entry, (action, _source) in entries.items():
            # Move / rename: entry is "old → new"
            if "\u2192" in entry:  # → (U+2192)
                sides = [s.strip() for s in entry.split("\u2192")]
                old_rp = f"{prefix}/{sides[0]}"
                new_rp = f"{prefix}/{sides[-1]}"
                # Remove old path and any children (directory move)
                if _remove(old_rp):
                    changed = True
                for p in [p for p in _records if p.startswith(old_rp + "/")]:
                    if _remove(p):
                        changed = True
                # Index the new location
                if _index_path(root, new_rp):
                    changed = True
                continue

            # Restore: entry is "path @ sha"
            rp = entry.split(" @ ")[0].strip()
            repo_path = f"{prefix}/{rp}"

            if action == "delete":
                if _remove(repo_path):
                    changed = True
                # Directory delete — purge children
                for p in [p for p in _records if p.startswith(repo_path + "/")]:
                    if _remove(p):
                        changed = True
            else:
                # add / save / restore / create — hash whatever is on disk
                if _index_path(root, repo_path):
                    changed = True

        if changed:
            _write(root)

    return changed


# ── Lookup API ──

def _with_abs(rec: dict) -> dict:
    """Return a copy of rec with abs_path set (repo root + relative path).

    The stored ``path`` stays repo-relative for git portability; callers that
    need to open the file on disk use ``abs_path``.
    """
    out = dict(rec)
    if _root is not None:
        out["abs_path"] = str(_root / rec["path"])
    return out


def lookup(doc_id: str) -> list[dict]:
    """Resolve a doc_id to all records that share it.

    A doc_id can map to multiple paths (the same file copied to several
    clients). Each record includes ``abs_path`` (absolute filesystem path).
    Returns an empty list if nothing matches.
    """
    with _lock:
        paths = _by_doc_id.get(doc_id, set())
        return [_with_abs(_records[p]) for p in paths if p in _records]


def lookup_path(repo_path: str) -> dict | None:
    """Resolve a repo-relative path to its index record, or None.

    The returned record includes ``abs_path`` (absolute filesystem path).
    """
    with _lock:
        rec = _records.get(repo_path)
        return _with_abs(rec) if rec else None


def all_records() -> list[dict]:
    """Return a snapshot of every record (sorted by path). Each record
    includes ``abs_path``. Mainly for debugging / administrative inspection."""
    with _lock:
        return [_with_abs(_records[p]) for p in sorted(_records)]
