"""Sync model prices from token.app into model_prices.json.

Fetches https://token.app/api/models, reshapes the payload into the
per_1m_tokens_usd schema used by Conversation Inspector cost estimates,
and overwrites model_prices.json at the repo root.

Usage:
    uv run scripts/sync_model_prices.py            # fetch and write
    uv run scripts/sync_model_prices.py --dry-run   # fetch and report, no write
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

SOURCE_URL = "https://token.app/api/models"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "model_prices.json"

HEADER_SCHEMA = "per_1m_tokens_usd"
HEADER_NOTE = (
    "Generated from token.app API for Conversation Inspector cost estimates. "
    "Prices are display-only and may drift."
)


def fetch_models(url: str) -> dict:
    """Fetch the raw model list from the token.app API."""
    resp = httpx.get(url, timeout=30.0, headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def reshape(payload: dict) -> dict:
    """Convert the API payload into the model_prices.json structure."""
    models: dict[str, dict] = {}
    for m in payload.get("models", []):
        # Deprecated models are noise for cost estimates; skip them.
        if m.get("isDeprecated"):
            continue
        entry = {
            "input": m["inputPer1M"],
            "output": m["outputPer1M"],
            "name": m["name"],
            "provider": m["providerId"],
            "context_window": m["contextWindow"],
        }
        # Keep optional flags compact: only emit them when true.
        if m.get("isReasoning"):
            entry["reasoning"] = True
        if m.get("isVision"):
            entry["vision"] = True
        if m.get("isFree"):
            entry["free"] = True
        models[m["id"]] = entry

    now = datetime.now(timezone.utc)
    return {
        "schema": HEADER_SCHEMA,
        "note": HEADER_NOTE,
        "source": SOURCE_URL,
        "source_last_updated": payload.get("lastUpdated"),
        "updated": now.strftime("%Y-%m-%d"),
        "count": len(models),
        # Sorted keys keep the file diff-friendly and output deterministic.
        "models": dict(sorted(models.items())),
    }


def summarize_diff(old: dict | None, new: dict) -> None:
    """Print a short add/remove/change summary against the existing file."""
    if old is None:
        print(f"  (no existing file, writing {new['count']} models)")
        return
    old_models, new_models = old.get("models", {}), new["models"]
    added = sorted(set(new_models) - set(old_models))
    removed = sorted(set(old_models) - set(new_models))
    changed = sorted(
        k for k in old_models.keys() & new_models.keys()
        if old_models[k] != new_models[k]
    )
    print(f"  added:   {len(added)}")
    print(f"  removed: {len(removed)}")
    print(f"  changed: {len(changed)}")
    for section, ids in (("added", added), ("removed", removed), ("changed", changed)):
        for mid in ids[:10]:
            print(f"    [{section}] {mid}")
        if len(ids) > 10:
            print(f"    ... and {len(ids) - 10} more")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync model prices from token.app")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and report changes without writing the file")
    args = parser.parse_args()

    print(f"Fetching {SOURCE_URL} ...")
    payload = fetch_models(SOURCE_URL)

    result = reshape(payload)
    print(f"Fetched {len(payload.get('models', []))} models, "
          f"{result['count']} kept after filtering deprecated.")

    old = None
    if OUTPUT_PATH.exists():
        try:
            old = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("  warning: existing file is not valid JSON, it will be replaced.")

    summarize_diff(old, result)

    if old == result:
        print("No changes, file left untouched.")
        return 0

    if args.dry_run:
        print("Dry run: nothing written.")
        return 0

    OUTPUT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH} ({result['count']} models).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.HTTPError as exc:
        print(f"error: failed to fetch model prices: {exc}", file=sys.stderr)
        sys.exit(1)
