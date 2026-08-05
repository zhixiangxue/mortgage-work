"""One-off product-library backfill for QAAgent verification.

Default mode is dry-run. This script never changes .env and is not imported by
app startup. Use --apply --yes only after reviewing the printed target and file
list.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import SERVICES  # noqa: E402
from integration import KgClient, RagClient  # noqa: E402
from index.indexer import (  # noqa: E402
    SOURCE_EXTENSIONS,
    _guess_guideline,
    _org_from_path,
    build_single_file_zip,
)
from user import current_user  # noqa: E402
from workrepo import local_repo_path  # noqa: E402


def _iter_sources(products_dir: Path, limit: int | None = None) -> list[Path]:
    files = [
        p for p in products_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SOURCE_EXTENSIONS
    ]
    files.sort(key=lambda p: p.relative_to(products_dir).as_posix().lower())
    return files[:limit] if limit else files


def _rel(products_dir: Path, path: Path) -> str:
    return path.relative_to(products_dir).as_posix()


def dry_run(products_dir: Path, files: list[Path]) -> None:
    user = current_user()
    print("QA data backfill dry-run")
    print(f"Products directory: {products_dir}")
    print(f"RAG target: {SERVICES.rag_service_url} / dataset={user.rag_dataset_id}")
    print(f"KG target: {SERVICES.kg_service_url} / graph={user.kg_graph_name}")
    print(f"Files to upload: {len(files)}")
    for path in files:
        relpath = _rel(products_dir, path)
        print(f"- {relpath} | org={_org_from_path(relpath)} | guideline={_guess_guideline(relpath)}")
    if not files:
        print("No source files found. Add product/guideline documents under products/ first.")


def apply_backfill(products_dir: Path, files: list[Path]) -> None:
    user = current_user()
    rag = RagClient(SERVICES.rag_service_url, SERVICES.rag_api_key, user.rag_dataset_id)
    kg = KgClient(SERVICES.kg_service_url, SERVICES.kg_api_key, user.kg_graph_name)

    rag.ensure_dataset(description="Mortgage Work product library")
    kg.ensure_graph()

    for path in files:
        relpath = _rel(products_dir, path)
        org_name = _org_from_path(relpath)
        guideline = _guess_guideline(relpath)
        print(f"Uploading {relpath}")

        rag_result = rag.upload_document(path, metadata={
            "lender": org_name,
            "guideline": guideline,
            "overlays": [],
            "tags": [],
        })
        rag_doc_id = rag_result.get("doc_id")
        rag_task = rag.create_task(rag_doc_id)
        print(f"  RAG task: {rag_task}")

        zip_bytes = build_single_file_zip(org_name, path)
        bundle_url = kg.upload_bundle(zip_bytes, filename=f"{path.stem}.zip")
        kg_task = kg.ingest(bundle_url)
        print(f"  KG task: {kg_task}")

    print("Backfill submitted. Processing is asynchronous; check indexing/service status before QA testing.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill products/ into configured RAG/KG services.")
    parser.add_argument(
        "--products-dir",
        default=None,
        help="Directory containing product/guideline files. Defaults to the managed work repo's products/.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files for a small smoke batch.")
    parser.add_argument("--apply", action="store_true", help="Actually submit uploads and ingest tasks.")
    parser.add_argument("--yes", action="store_true", help="Required together with --apply.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    products_dir = Path(args.products_dir).resolve() if args.products_dir else (local_repo_path() / "products").resolve()
    if not products_dir.is_dir():
        print(f"Products directory not found: {products_dir}", file=sys.stderr)
        return 2
    files = _iter_sources(products_dir, args.limit or None)
    dry_run(products_dir, files)
    if not args.apply:
        print("Dry-run only. Re-run with --apply --yes to submit uploads.")
        return 0
    if not args.yes:
        print("Refusing to apply without --yes.", file=sys.stderr)
        return 2
    apply_backfill(products_dir, files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
