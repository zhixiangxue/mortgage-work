"""Work-repo engine: managed clone, validation, and client/product scanning.

This is the layer that turns the git repo into what the UI shows. Design
rules it implements (see the work repo's README for the full spec):

* The repo is the single source of truth. Nothing here persists anything
  outside the repo — scanning rebuilds the full picture from disk each time.
* The local checkout is MANAGED: it always lives at
  ``~/MortgageWork/<repo-name>/``, derived from WORK_REPO_URL. First boot
  clones; later boots fast-forward pull. A failed pull degrades to offline
  mode (the local copy keeps working) instead of blocking the app.
* A client exists iff its folder exists. A missing/broken client.yaml only
  flags the client for repair — it never hides it.

Run standalone for a smoke test:

    uv run python workrepo.py
"""
from __future__ import annotations

import base64
import mimetypes
import os
import re
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

import yaml

from config import SERVICES

WORKSPACE_ROOT = Path.home() / "MortgageWork"

# Mirror of the frontend's EXT_TYPE (store.js) so tree nodes carry the same
# type tokens the components already style.
EXT_TYPE = {
    "pdf": "pdf", "md": "md", "yml": "yml", "yaml": "yml", "eml": "eml",
    "png": "img", "jpg": "img", "jpeg": "img", "gif": "img", "webp": "img",
    "txt": "txt", "ai": "ai",
}

PURPOSE_LABELS = {
    "purchase": "Purchase",
    "refinance": "Refinance",
    "cash_out_refinance": "Cash-out Refi",
    "heloc": "HELOC",
    "investment": "Investment",
}

STAGE_LABELS = {"lead": "New Lead", "docs": "Collecting Docs", "active": "Active"}

# Reserved machine-managed files that never show up in the LO-facing tree.
HIDDEN_FILES = {"client.yaml"}

# Extensions rendered as text in the viewer; anything else ships as base64.
TEXT_EXTENSIONS = {".md", ".txt", ".ai", ".yaml", ".yml", ".eml", ".csv", ".json", ".html", ".htm"}

# Upper bound for what we push through the JS bridge in one call — a base64
# payload beyond this would visibly freeze the webview.
MAX_FILE_BYTES = 40 * 1024 * 1024


class RepoError(RuntimeError):
    """Fatal work-repo problem the UI should surface (bad URL, clone failed…)."""


# ── Git plumbing ──

def _git(args: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    # Force non-interactive git: a hidden password/hostkey prompt must fail
    # fast (we handle the error) instead of hanging the app on boot.
    env = os.environ | {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": os.environ.get(
            "GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10"),
    }
    return subprocess.run(["git", *args], cwd=cwd, timeout=timeout,
                          capture_output=True, text=True, env=env)


def repo_name(url: str) -> str:
    """Last path segment of the remote, without the .git suffix."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.git$", "", name)


def local_repo_path() -> Path:
    if not SERVICES.work_repo_url:
        raise RepoError("WORK_REPO_URL is not configured (.env)")
    return WORKSPACE_ROOT / repo_name(SERVICES.work_repo_url)


def ensure_repo(pull: bool = True) -> Path:
    """Clone-or-pull the managed checkout and validate its structure.

    `pull=False` skips the network round-trip — boot uses it so the UI never
    waits on SSH; a background sync pulls right after. Pull failures are
    non-fatal (offline mode); clone failures and structural problems raise
    RepoError.
    """
    url = SERVICES.work_repo_url
    path = local_repo_path()

    if not (path / ".git").is_dir():
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        print(f"[workrepo] cloning {url} → {path}")
        res = _git(["clone", url, str(path)])
        if res.returncode != 0:
            raise RepoError(f"clone failed: {res.stderr.strip()}")
    else:
        # Same path but different remote = two identities collided; refuse
        # rather than silently mixing books of business.
        res = _git(["remote", "get-url", "origin"], cwd=path)
        if res.returncode == 0 and res.stdout.strip() != url:
            raise RepoError(f"{path} tracks {res.stdout.strip()}, expected {url}")
        if pull:
            res = _git(["pull", "--ff-only"], cwd=path, timeout=60)
            if res.returncode != 0:
                # Offline or diverged — keep working locally, sync engine deals later
                print(f"[workrepo] pull skipped: {res.stderr.strip().splitlines()[-1] if res.stderr else 'unknown'}")

    for required in ("clients", "products"):
        if not (path / required).is_dir():
            raise RepoError(f"not a work repo (missing {required}/): {path}")
    return path


# ── Scanning ──

def _humanize(ts: float) -> str:
    """Timestamps the way an LO reads them: 2h ago / Yesterday / Jul 25."""
    delta = time.time() - ts
    if delta < 90:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 172800:
        return "Yesterday"
    if delta < 604800:
        return f"{int(delta // 86400)}d ago"
    return datetime.fromtimestamp(ts).strftime("%b %d")


def _fmt_amount(value) -> str:
    return f"${value:,}" if isinstance(value, (int, float)) else str(value or "—")


def _last_touched(folder: Path) -> float:
    """Newest mtime of any visible file — 'last activity' without git."""
    latest = folder.stat().st_mtime
    for p in folder.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            latest = max(latest, p.stat().st_mtime)
    return latest


def _missing_count(folder: Path) -> int:
    """Open items = unchecked boxes in the AI-maintained checklist."""
    checklist = folder / "ai" / "missing-docs.ai"
    if not checklist.is_file():
        return 0
    try:
        return len(re.findall(r"^\s*- \[ \]", checklist.read_text(), re.MULTILINE))
    except OSError:
        return 0


def build_tree(folder: Path) -> list[dict]:
    """File tree in the exact node shape the frontend components render.

    Dotfiles and reserved machine files stay invisible — the LO sees their
    working files, not our bookkeeping.
    """
    nodes = []
    entries = sorted(folder.iterdir(),
                     key=lambda p: (p.is_dir(), p.name.lower()))  # files first, then dirs
    for entry in entries:
        if entry.name.startswith(".") or entry.name in HIDDEN_FILES:
            continue
        if entry.is_dir():
            nodes.append({"name": entry.name, "type": "dir",
                          "children": build_tree(entry)})
        else:
            ext = entry.suffix.lstrip(".").lower()
            nodes.append({"name": entry.name, "type": EXT_TYPE.get(ext, "md")})
    # PROFILE.md is the client's face — pin it to the top like the IDE mock
    nodes.sort(key=lambda n: n["name"] != "PROFILE.md")
    return nodes


def _load_client(folder: Path) -> dict:
    slug = folder.name
    meta, broken = {}, False
    yaml_path = folder / "client.yaml"
    try:
        meta = yaml.safe_load(yaml_path.read_text()) or {}
    except Exception:
        # Missing or unparsable metadata: the client still exists (folder is
        # the existence test); flag it so the UI can offer an AI repair.
        broken = True

    stage = meta.get("stage", "lead")
    if stage == "closed":
        closed_on = meta.get("closed")
        label = f"Closed {closed_on:%m/%d}" if isinstance(closed_on, date) else "Closed"
    else:
        label = STAGE_LABELS.get(stage, stage.title())

    return {
        "id": slug,
        "name": meta.get("name") or slug.replace("-", " ").title(),
        "purpose": PURPOSE_LABELS.get(meta.get("purpose"), str(meta.get("purpose", "—")).title()),
        "amount": _fmt_amount(meta.get("amount")),
        "stage": stage,
        "stageLbl": label,
        "city": meta.get("city", "—"),
        "missing": _missing_count(folder),
        "touched": _humanize(_last_touched(folder)),
        "broken": broken,
        "tree": build_tree(folder),
    }


def scan_clients(root: Path) -> tuple[list[dict], list[dict]]:
    """(active, closed) client lists, newest activity first."""
    active, closed = [], []
    for folder in sorted((root / "clients").iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        client = _load_client(folder)
        (closed if client["stage"] == "closed" else active).append(client)
    active.sort(key=lambda c: c["touched"])  # humanized strings sort poorly; refined later
    return active, closed


def scan_products(root: Path) -> list[dict]:
    """Product library tree: one top-level dir per lender."""
    return build_tree(root / "products")


def _resolve_scoped(scope: str, relpath: str) -> Path:
    """Resolve a tree-relative path and pin it inside its scope folder.
    The tree is the only trusted path source, but never trust what crossed
    the JS bridge."""
    root = local_repo_path()
    base = (root / "products") if scope == "products" else (root / "clients" / scope)
    target = (base / relpath).resolve()
    if not target.is_relative_to(base.resolve()):
        raise RepoError(f"path escapes workspace: {relpath}")
    return target


def read_file(scope: str, relpath: str) -> dict:
    """File content for the viewer. scope = client slug or "products".

    Text files return a string; binaries (PDF, images) return base64 with a
    mime type so the frontend can build a blob URL.
    """
    target = _resolve_scoped(scope, relpath)
    if not target.is_file():
        raise RepoError(f"no such file: {relpath}")
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise RepoError(f"{target.name} is {size // 1048576} MB — too large to preview")

    ext = target.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        # Tolerate stray non-UTF8 bytes (exported emails etc.) — a lossy view
        # beats an error dialog for preview purposes.
        return {"kind": "text", "name": target.name,
                "content": target.read_text(errors="replace")}
    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return {"kind": "binary", "name": target.name, "mime": mime,
            "b64": base64.b64encode(target.read_bytes()).decode()}


def write_file(scope: str, relpath: str, content: str) -> dict:
    """Persist an edited text file. Only text kinds are editable, and the
    machine-managed files stay off limits — the editor never sees them, but
    defense in depth costs one line."""
    target = _resolve_scoped(scope, relpath)
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        raise RepoError(f"not an editable file type: {target.name}")
    if target.name in HIDDEN_FILES or target.name.startswith("."):
        raise RepoError(f"machine-managed file: {target.name}")
    if not target.is_file():
        raise RepoError(f"no such file: {relpath}")
    target.write_text(content)
    return {"ok": True}


def workspace_snapshot(pull: bool = True) -> dict:
    """Everything the frontend needs on boot, in one JSON-serializable blob."""
    root = ensure_repo(pull=pull)
    active, closed = scan_clients(root)
    return {
        "user": {"id": SERVICES.user_id, "name": SERVICES.user_name},
        "repo": {"path": str(root), "url": SERVICES.work_repo_url},
        "clients": active,
        "closed": closed,
        "productTree": scan_products(root),
    }


if __name__ == "__main__":
    snap = workspace_snapshot()
    print(f"\nrepo:    {snap['repo']['path']}")
    print(f"user:    {snap['user']['id']} ({snap['user']['name']})")
    print(f"clients: {len(snap['clients'])} active, {len(snap['closed'])} closed")
    for c in snap["clients"] + snap["closed"]:
        flag = " ⚠ broken client.yaml" if c["broken"] else ""
        print(f"  - {c['id']}: {c['name']} · {c['purpose']} {c['amount']} · "
              f"{c['stageLbl']} · missing {c['missing']} · {c['touched']}{flag}")
    lenders = [n["name"] for n in snap["productTree"] if n["type"] == "dir"]
    print(f"lenders: {', '.join(lenders)}")
