"""Per-lender document index for the work repo's products/ tree.

Why this exists
---------------
Agents locate source documents by ``doc_id`` — the xxh64 content hash of the
file, byte-for-byte identical to what kg-service computes (see
``kg/agents/hash.py``: same algorithm, same streaming, same extension filter).
Without a file ↔ doc_id map the agent can name a doc_id but nobody can open
the file behind it. Each lender folder therefore carries a machine-managed
``.docs.yaml`` mapping every source file (recursively) to its doc_id.

The dotfile name is deliberate: kg-service's ``hash_directory`` skips names
starting with ``.`` or ``_``, so the index never pollutes the hash set it
describes.

Sync is incremental: a file is only re-hashed when its (size, mtime) changed,
so refreshing a big product library on every save stays cheap. Content is the
identity — renames keep the doc_id, edits change it.

Usage
-----
    uv run python docs_index.py                   # sync $WORK_REPO_PATH or ./sample-work-repo
    uv run python docs_index.py --repo /path/to/work-repo
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import xxhash
import yaml

log = logging.getLogger(__name__)

# Mirror of kg-service's SOURCE_EXTENSIONS — the two sides must agree on what
# counts as a source document or the doc_id sets drift.
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".md", ".txt", ".doc", ".docx", ".html", ".htm"}
)

INDEX_NAME = ".docs.yaml"


def calculate_file_hash(file_path: Path | str, chunk_size: int = 8192) -> str:
    """xxh64 hex digest of the file — byte-compatible with kg-service."""
    hash_func = xxhash.xxh64()
    with open(file_path, "rb") as fp:
        while chunk := fp.read(chunk_size):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def _source_files(lender_dir: Path) -> list[Path]:
    """Source documents under a lender folder, recursively, stable order."""
    files = []
    for path in lender_dir.rglob("*"):
        if not path.is_file():
            continue
        # Same skip rule as kg-service: dotfiles and _artifacts are bookkeeping
        if path.name.startswith(("_", ".")):
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        files.append(path)
    return sorted(files, key=lambda p: str(p.relative_to(lender_dir)))


def load_index(lender_dir: Path) -> dict[str, dict]:
    """Existing index entries keyed by relative file path ({} if absent/broken)."""
    index_file = lender_dir / INDEX_NAME
    if not index_file.exists():
        return {}
    try:
        data = yaml.safe_load(index_file.read_text(encoding="utf-8")) or {}
        return {d["file"]: d for d in data.get("docs", []) if "file" in d}
    except Exception:
        # A corrupt index is not precious — it's fully derivable, rebuild it
        return {}


def sync_lender(lender_dir: Path) -> tuple[int, int]:
    """Bring one lender folder's .docs.yaml in line with its files.

    Returns (total_docs, rehashed_count). Writes only when content changed so
    untouched folders produce no git noise.
    """
    old = load_index(lender_dir)
    docs, rehashed = [], 0
    for path in _source_files(lender_dir):
        rel = str(path.relative_to(lender_dir))
        stat = path.stat()
        prev = old.get(rel)
        # (size, mtime) unchanged → trust the recorded doc_id, skip the read
        if prev and prev.get("size") == stat.st_size and prev.get("mtime") == int(stat.st_mtime):
            doc_id = prev["doc_id"]
        else:
            doc_id = calculate_file_hash(path)
            rehashed += 1
        docs.append({"file": rel, "doc_id": doc_id,
                     "size": stat.st_size, "mtime": int(stat.st_mtime)})

    if [old.get(d["file"]) for d in docs] == docs and len(old) == len(docs):
        return len(docs), 0  # byte-identical index, don't touch the file

    payload = {"schema": 1, "docs": docs}
    header = ("# Machine-managed by Mortgage Work — do not edit by hand.\n"
              "# Maps every source document to its doc_id (xxh64 content hash,\n"
              "# same algorithm as kg-service) so agents can resolve doc_id → file.\n")
    (lender_dir / INDEX_NAME).write_text(
        header + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    return len(docs), rehashed


def sync_products(repo_path: Path) -> None:
    """Sync .docs.yaml for every lender folder under <repo>/products/."""
    products = repo_path / "products"
    if not products.is_dir():
        raise SystemExit(f"not a work repo (no products/): {repo_path}")
    for lender_dir in sorted(p for p in products.iterdir() if p.is_dir()):
        total, rehashed = sync_lender(lender_dir)
        log.info("docs-index %s: %d docs (%d hashed)", lender_dir.name, total, rehashed)


def main() -> None:
    default_repo = os.environ.get("WORK_REPO_PATH", "sample-work-repo")
    parser = argparse.ArgumentParser(description="Sync per-lender .docs.yaml indexes")
    parser.add_argument("--repo", default=default_repo,
                        help="work repo root (default: $WORK_REPO_PATH or ./sample-work-repo)")
    args = parser.parse_args()
    sync_products(Path(args.repo).expanduser().resolve())


if __name__ == "__main__":
    from log import setup_logging
    setup_logging()
    main()
