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
import shutil
import subprocess
import sys
import threading
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

def _git_env() -> dict:
    # Force non-interactive git: a hidden password/hostkey prompt must fail
    # fast (we handle the error) instead of hanging the app on boot.
    return os.environ | {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": os.environ.get(
            "GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10"),
    }


def _git(args: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, timeout=timeout,
                          capture_output=True, text=True,
                          # git speaks UTF-8; text=True would otherwise decode
                          # with the OS locale and blow up on a non-ASCII
                          # filename or a "→" in one of our own messages.
                          encoding="utf-8", errors="replace", env=_git_env())


def _git_bytes(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Same, undecoded — for reading file contents out of history (PDFs)."""
    return subprocess.run(["git", *args], cwd=cwd, timeout=120,
                          capture_output=True, env=_git_env())


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
        return len(re.findall(r"^\s*- \[ \]", checklist.read_text(encoding="utf-8"), re.MULTILINE))
    except OSError:
        return 0


# ── Git status (source-control colors in the tree) ──

# Node tokens the frontend already styles: "new" → green name + U,
# "mod" → amber name + M. Folders inherit the loudest child (VS Code does the
# same), so a change stays visible while its folder is collapsed.
GIT_RANK = {"": 0, "mod": 1, "new": 2}


def git_status(root: Path) -> dict[Path, str]:
    """Working-tree status keyed by absolute path, in the frontend's tokens.

    One call feeds a whole scan. Deletions are dropped — there is no row left
    to paint — and a failed call degrades to "no colors" rather than an error:
    the tree matters more than its decoration.
    """
    # -z: NUL-separated records, so no quoting/escaping to undo (paths here are
    # user-named and full of spaces). -uall lists files inside a new folder
    # individually, which is what the rows need.
    res = _git(["status", "--porcelain", "-z", "-uall"], cwd=root)
    if res.returncode != 0:
        return {}
    status: dict[Path, str] = {}
    records = res.stdout.split("\0")
    i = 0
    while i < len(records):
        rec = records[i]
        i += 1
        if len(rec) < 4:
            continue
        code, rel = rec[:2], rec[3:]
        if "R" in code or "C" in code:
            i += 1          # rename/copy carries its source path as an extra record
        if "D" in code:
            continue
        status[root / rel] = "new" if (code == "??" or "A" in code
                                      or "R" in code or "C" in code) else "mod"
    return status


def build_tree(folder: Path, status: dict[Path, str] | None = None) -> list[dict]:
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
            children = build_tree(entry, status)
            node = {"name": entry.name, "type": "dir", "children": children}
            # Roll the loudest child change up so collapsed folders still speak
            rollup = max((c.get("git", "") for c in children),
                         key=lambda s: GIT_RANK.get(s, 0), default="")
            if rollup:
                node["git"] = rollup
            nodes.append(node)
        else:
            ext = entry.suffix.lstrip(".").lower()
            node = {"name": entry.name, "type": EXT_TYPE.get(ext, "md")}
            state = (status or {}).get(entry)
            if state:
                node["git"] = state
            nodes.append(node)
    # PROFILE.md is the client's face — pin it to the top like the IDE mock
    nodes.sort(key=lambda n: n["name"] != "PROFILE.md")
    return nodes


def file_status() -> dict[str, dict[str, str]]:
    """Repaint data for the tree, scoped the way the frontend addresses nodes:
    ``{scope: {tree-relative path: state}}`` (scope = client slug or products).

    Cheap enough to call on every sync-state change — one git invocation, no
    directory walk — which is what keeps the colors honest after a commit.
    """
    root = local_repo_path()
    out: dict[str, dict[str, str]] = {}
    for path, state in git_status(root).items():
        parts = path.relative_to(root).parts
        if parts[0] == "products":
            scope, rel = "products", parts[1:]
        elif parts[0] == "clients" and len(parts) > 2:
            scope, rel = parts[1], parts[2:]
        else:
            continue        # repo-level files have no row in any tree
        if not rel or rel[-1] in HIDDEN_FILES or any(p.startswith(".") for p in rel):
            continue
        out.setdefault(scope, {})["/".join(rel)] = state
    return out


def _load_client(folder: Path, status: dict[Path, str] | None = None) -> dict:
    slug = folder.name
    meta, broken = {}, False
    yaml_path = folder / "client.yaml"
    try:
        meta = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
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

    touched_ts = _last_touched(folder)
    return {
        "id": slug,
        "name": meta.get("name") or slug.replace("-", " ").title(),
        "purpose": PURPOSE_LABELS.get(meta.get("purpose"), str(meta.get("purpose", "—")).title()),
        "amount": _fmt_amount(meta.get("amount")),
        "stage": stage,
        "stageLbl": label,
        "city": meta.get("city", "—"),
        "missing": _missing_count(folder),
        "touched": _humanize(touched_ts),
        "touchedTs": touched_ts,
        "broken": broken,
        "tree": build_tree(folder, status),
    }


def scan_clients(root: Path, status: dict[Path, str] | None = None) -> tuple[list[dict], list[dict]]:
    """(active, closed) client lists, newest activity first."""
    active, closed = [], []
    for folder in sorted((root / "clients").iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        client = _load_client(folder, status)
        (closed if client["stage"] == "closed" else active).append(client)
    # Mail-client ordering: the case the LO (or the agent) touched last is the
    # one they're working — sort on the raw mtime, not the humanized label.
    # Closed folders go quiet after closing, so mtime ≈ close date there too.
    active.sort(key=lambda c: c["touchedTs"], reverse=True)
    closed.sort(key=lambda c: c["touchedTs"], reverse=True)
    return active, closed


def scan_products(root: Path, status: dict[Path, str] | None = None) -> list[dict]:
    """Product library tree: one top-level dir per lender."""
    return build_tree(root / "products", status)


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
                "content": target.read_text(encoding="utf-8", errors="replace")}
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
    target.write_text(content, encoding="utf-8")
    queue_sync(scope, relpath)
    return {"ok": True}


# ── File operations (the tree's write side) ──
#
# House rules, shared by everything below:
#  * paths are re-resolved and pinned inside their scope (_resolve_scoped) and
#    names are validated — nothing that crossed the JS bridge is trusted;
#  * nothing ever overwrites: a collision gets an IDE-style -2, -3… suffix;
#  * disk first, then queue_sync. The frontend never patches its tree from the
#    return value — it rescans — so a failure here can't leave the UI claiming
#    a file that isn't on disk.

def _check_name(name: str) -> str:
    """Validate a single path component typed by a human."""
    name = (name or "").strip().rstrip(".")     # trailing dots are invalid on Windows
    if not name:
        raise RepoError("name required")
    if "/" in name or "\\" in name or name in (".", ".."):
        raise RepoError(f"invalid name: {name}")
    if name.startswith("."):
        raise RepoError("names starting with . are reserved")
    if name in HIDDEN_FILES:
        raise RepoError(f"{name} is machine-managed")
    return name


def _unique(folder: Path, name: str) -> str:
    """report.pdf → report-2.pdf when taken. Nothing is ever clobbered."""
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    else:
        ext = "." + ext
    candidate, i = name, 2
    while (folder / candidate).exists():
        candidate = f"{stem}-{i}{ext}"
        i += 1
    return candidate


def _rel(scope: str, target: Path) -> str:
    """Tree-relative path with forward slashes — the address the UI speaks."""
    return target.relative_to(_resolve_scoped(scope, "")).as_posix()


def _scoped_dir(scope: str, dirrel: str) -> Path:
    folder = _resolve_scoped(scope, dirrel)
    if not folder.is_dir():
        raise RepoError(f"no such folder: {dirrel or '.'}")
    return folder


def _scoped_existing(scope: str, relpath: str) -> Path:
    """An existing file or folder inside the scope, never the scope root itself
    (deleting or renaming a client from the tree is not a file operation)."""
    if not relpath:
        raise RepoError("path required")
    target = _resolve_scoped(scope, relpath)
    if not target.exists():
        raise RepoError(f"no such path: {relpath}")
    if target.name in HIDDEN_FILES:
        raise RepoError(f"{target.name} is machine-managed")
    return target


def create_file(scope: str, dirrel: str = "", name: str = "untitled.md") -> dict:
    """New empty file. The UI drops straight into inline rename afterwards, so
    the default name only has to be harmless."""
    folder = _scoped_dir(scope, dirrel)
    target = folder / _unique(folder, _check_name(name))
    target.touch()
    rel = _rel(scope, target)
    queue_sync(scope, rel, "add")
    return {"ok": True, "path": rel}


def create_folder(scope: str, dirrel: str = "", name: str = "new-folder") -> dict:
    """New folder. No queue_sync: git tracks files, not directories, so an empty
    folder has nothing to commit — it rides along with its first file."""
    folder = _scoped_dir(scope, dirrel)
    target = folder / _unique(folder, _check_name(name))
    target.mkdir()
    return {"ok": True, "path": _rel(scope, target)}


def rename_path(scope: str, relpath: str, new_name: str) -> dict:
    target = _scoped_existing(scope, relpath)
    new_name = _check_name(new_name)
    if new_name == target.name:
        return {"ok": True, "path": relpath}
    dest = target.parent / new_name
    # samefile guard: on Windows/macOS "income" and "Income" are the same entry,
    # and a case-only rename is legitimate.
    if dest.exists() and not dest.samefile(target):
        raise RepoError(f"{new_name} already exists here")
    target.rename(dest)
    rel = _rel(scope, dest)
    queue_sync(scope, f"{relpath} → {rel}", "rename")
    return {"ok": True, "path": rel}


def move_path(scope: str, relpath: str, destdir: str = "") -> dict:
    """Move into another folder in the same scope (drag & drop in the tree)."""
    src = _scoped_existing(scope, relpath)
    folder = _scoped_dir(scope, destdir)
    if src == folder or folder.is_relative_to(src):
        raise RepoError("can't move a folder into itself")
    if src.parent == folder:
        return {"ok": True, "path": relpath}        # already there
    dest = folder / _unique(folder, src.name)
    shutil.move(str(src), str(dest))
    rel = _rel(scope, dest)
    queue_sync(scope, f"{relpath} → {rel}", "move")
    return {"ok": True, "path": rel}


def delete_path(scope: str, relpath: str) -> dict:
    """Delete for real. Recoverable from git history if it was ever committed —
    which is the whole point of committing on every change."""
    target = _scoped_existing(scope, relpath)
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    queue_sync(scope, relpath, "delete")
    return {"ok": True, "path": relpath}


def duplicate_path(scope: str, relpath: str) -> dict:
    src = _scoped_existing(scope, relpath)
    stem, dot, ext = src.name.rpartition(".")
    if not dot or src.is_dir():
        stem, ext = src.name, ""
    else:
        ext = "." + ext
    dest = src.parent / _unique(src.parent, f"{stem}-copy{ext}")
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    rel = _rel(scope, dest)
    queue_sync(scope, rel, "add")
    return {"ok": True, "path": rel}


def copy_path(scope: str, relpath: str, destdir: str = "") -> dict:
    """Copy into another folder in the same scope — the tree clipboard's paste.

    Pasting back into the source folder is a duplicate, which already has a
    naming rule (-copy), so it defers to it instead of inventing a second one.
    """
    src = _scoped_existing(scope, relpath)
    folder = _scoped_dir(scope, destdir)
    if folder == src.parent:
        return duplicate_path(scope, relpath)
    if folder.is_relative_to(src):
        raise RepoError("can't copy a folder into itself")
    dest = folder / _unique(folder, src.name)
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    rel = _rel(scope, dest)
    queue_sync(scope, rel, "add")
    return {"ok": True, "path": rel}


def upload_files(scope: str, dirrel: str, files: list[dict]) -> dict:
    """Drag & drop / paste: `files` = [{"name":…, "b64":…}].

    A webview File object exposes no disk path (unlike Electron), so dropped
    bytes have to ride the bridge as base64. `add_files` is the cheap native
    route for the same job.
    """
    folder = _scoped_dir(scope, dirrel)
    written = []
    for item in files or []:
        name = _unique(folder, _check_name(item.get("name")))
        data = base64.b64decode(item.get("b64") or "")
        if len(data) > MAX_FILE_BYTES:
            raise RepoError(f"{name} is too large ({len(data) // 1048576} MB)")
        (folder / name).write_bytes(data)
        written.append(_rel(scope, folder / name))
    for rel in written:
        queue_sync(scope, rel, "add")
    return {"ok": True, "count": len(written),
            "names": [r.rsplit("/", 1)[-1] for r in written]}


def add_files(scope: str, dirrel: str, sources: list[str]) -> dict:
    """Copy files in by absolute path — what the native file dialog returns."""
    folder = _scoped_dir(scope, dirrel)
    written = []
    for source in sources or []:
        src = Path(source)
        if not src.is_file():
            continue
        dest = folder / _unique(folder, _check_name(src.name))
        shutil.copy2(src, dest)
        written.append(_rel(scope, dest))
    for rel in written:
        queue_sync(scope, rel, "add")
    return {"ok": True, "count": len(written),
            "names": [r.rsplit("/", 1)[-1] for r in written]}


def reveal_path(scope: str, relpath: str = "") -> dict:
    """Show the path in the OS file manager — the escape hatch every IDE has."""
    target = _resolve_scoped(scope, relpath)
    if not target.exists():
        raise RepoError(f"no such path: {relpath}")
    if sys.platform == "win32":
        # /select, wants the item itself; Explorer exits 1 even on success
        subprocess.Popen(["explorer", f"/select,{target}"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)])
    return {"ok": True}


def file_history(scope: str, relpath: str, limit: int = 25) -> dict:
    """git log for one path as the columns the History panel shows:
    when · who · what · revision. --follow keeps a renamed file's past attached."""
    target = _resolve_scoped(scope, relpath)
    root = local_repo_path()
    rel = target.relative_to(root).as_posix()
    args = ["log", f"-{limit}", "--date=format:%b %d, %H:%M",
            "--pretty=format:%h%x1f%ad%x1f%an%x1f%s"]
    if target.is_file():
        args.append("--follow")     # only meaningful for a single file
    res = _git(args + ["--", rel], cwd=root)
    if res.returncode != 0:
        raise RepoError("no history yet")
    rows = []
    for line in res.stdout.splitlines():
        sha, _, rest = line.partition("\x1f")
        when, _, rest = rest.partition("\x1f")
        who, _, what = rest.partition("\x1f")
        # Our own commits are the LO's own edits — say so, like the UI does
        rows.append([when, "YOU" if who == SERVICES.user_name else who.upper(), what, sha])
    return {"rows": rows}


def _path_at(root: Path, sha: str, rel: str) -> str:
    """The name `rel` went by at `sha`. History follows a file through its
    renames, so a revision from before one has to be read under the old name."""
    res = _git(["log", "--follow", "--name-only", "--pretty=format:%x01%H", "--", rel], cwd=root)
    for block in res.stdout.split("\x01")[1:]:
        lines = [line for line in block.splitlines() if line.strip()]
        if lines and lines[0].startswith(sha) and len(lines) > 1:
            return lines[1]
    return rel


def restore_version(scope: str, relpath: str, sha: str) -> dict:
    """Bring a path back to how it looked in one commit.

    Nothing in the ledger is rewritten: the restore lands as a new change on
    top, so "undo" is itself a versioned event — the property that lets an LO
    click Restore without having to understand git.
    """
    if not re.fullmatch(r"[0-9a-f]{7,40}", (sha or "").strip()):
        raise RepoError("bad revision")
    target = _resolve_scoped(scope, relpath)
    root = local_repo_path()
    rel = target.relative_to(root).as_posix()
    if target.is_dir():
        # A folder comes back through the index; files added later stay put,
        # git has no opinion about them and neither do we.
        res = _git(["checkout", sha, "--", rel], cwd=root)
        if res.returncode != 0:
            detail = res.stderr.strip().splitlines()[-1] if res.stderr else sha
            raise RepoError(f"could not restore: {detail}")
    else:
        # Write the old bytes under the *current* name: the file may have been
        # renamed (or deleted) since, and "make it look like it did then" is
        # what Restore promises.
        blob = _git_bytes(["show", f"{sha}:{_path_at(root, sha, rel)}"], root)
        if blob.returncode != 0:
            raise RepoError(f"could not restore: {relpath} isn't in {sha}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob.stdout)
    queue_sync(scope, f"{relpath} @ {sha}", "restore")
    return {"ok": True, "path": relpath}


# ── Client creation (the folder IS the client) ──
#
# One folder per client, and it holds everything: the structured facts we manage
# (client.yaml), the LO-facing summary (PROFILE.md) and the document buckets.
# Nothing is registered anywhere else — creating a client is creating a folder.

# The modal's labels, mapped to the keys client.yaml stores
PURPOSE_KEYS = {
    "purchase": "purchase",
    "refinance": "refinance",
    "cash-out refinance": "cash_out_refinance",
    "heloc": "heloc",
    "investment property": "investment",
}

CITIZENSHIP_KEYS = {
    "us citizen": "us_citizen",
    "permanent resident": "permanent_resident",
    "non-permanent resident": "non_permanent_resident",
    "foreign national": "foreign_national",
}

# Buckets every client starts with. git tracks files, not folders, so each gets
# a .gitkeep — otherwise the structure would exist on this machine only.
CLIENT_FOLDERS = ("income", "assets", "credit", "ai")


def slugify(name: str) -> str:
    """Folder name from a person's name — same rule as the frontend's slugify."""
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


def create_client(data: dict) -> dict:
    """Scaffold clients/<slug>/ from the New Client form."""
    name = (data.get("name") or "").strip()
    if not name:
        raise RepoError("client name required")
    slug = slugify(name)
    if not slug:
        raise RepoError(f"could not make a folder name from {name!r}")
    root = ensure_repo(pull=False)
    folder = root / "clients" / slug
    if folder.exists():
        raise RepoError(f"{slug} already exists")

    purpose = PURPOSE_KEYS.get((data.get("purpose") or "").strip().lower(), "purchase")
    citizenship = CITIZENSHIP_KEYS.get((data.get("citizenship") or "").strip().lower(),
                                       "us_citizen")
    digits = re.sub(r"[^0-9]", "", str(data.get("amount") or ""))
    co = data.get("co") or None

    borrowers = [{"name": name, "citizenship": citizenship}]
    if co and (co.get("name") or "").strip():
        borrowers.append({
            "name": co["name"].strip(),
            "citizenship": CITIZENSHIP_KEYS.get((co.get("citizenship") or "").strip().lower(),
                                                "us_citizen"),
        })

    meta = {"schema": 1, "name": name, "purpose": purpose, "stage": "lead"}
    if digits:
        meta["amount"] = int(digits)
    contact = {k: v.strip() for k in ("phone", "email") if (v := data.get(k) or "").strip()}
    if contact:
        meta["contact"] = contact
    meta["borrowers"] = borrowers
    meta["created"] = date.today()

    folder.mkdir(parents=True)
    (folder / "client.yaml").write_text(
        "# Machine-managed by Mortgage Work — do not edit by hand.\n"
        "# Free-form notes belong in PROFILE.md; this file only holds structured facts.\n"
        + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    (folder / "PROFILE.md").write_text(_profile_scaffold(name, purpose, digits, borrowers),
                                       encoding="utf-8")
    for bucket in CLIENT_FOLDERS:
        (folder / bucket).mkdir()
        (folder / bucket / ".gitkeep").touch()

    # One entry, not one per file: the commit also carries the .gitkeep files,
    # and "a client folder was created" is what actually happened.
    queue_sync(slug, "client folder", "create")
    return {"ok": True, "id": slug}


def delete_client(slug: str) -> dict:
    """Remove a client folder and everything in it.

    The one delete that isn't a path *inside* a scope, so it validates the slug
    itself rather than leaning on `_resolve_scoped`. Recoverable the same way
    everything else is — the commit before this one still has the folder.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug or ""):
        raise RepoError(f"bad client id: {slug!r}")
    folder = local_repo_path() / "clients" / slug
    if not folder.is_dir():
        raise RepoError(f"no such client: {slug}")
    shutil.rmtree(folder)
    queue_sync(slug, "client folder", "delete")
    return {"ok": True, "id": slug}


def _profile_scaffold(name: str, purpose: str, digits: str, borrowers: list[dict]) -> str:
    """The client's opening page: what we know now, and what we're waiting for.
    Plain markdown on purpose — the LO edits it, and so will the agent later."""
    facts = [PURPOSE_LABELS.get(purpose, purpose.title())]
    if digits:
        facts.append(f"${int(digits):,} target")
    if len(borrowers) > 1:
        facts.append(f"with {borrowers[1]['name']} (co-borrower)")
    return (f"# {name}\n\n"
            f"{' · '.join(facts)}.\n\n"
            "## Snapshot\n\n"
            "- New lead, no documents on file yet\n\n"
            "## Open items\n\n"
            "- Income documents (paystubs, W-2s or bank statements)\n"
            "- Credit pull\n\n"
            "## Timeline\n\n"
            f"- {date.today():%m/%d} — file opened\n")


# ── Sync engine (save → commit → push, "Dropbox with a git ledger") ──
#
# Every explicit save queues its file here; a debounce window folds a burst of
# saves into one commit per scope. Messages are deterministic and structured
# (title + key/value body) so the history doubles as machine-readable context
# for agents later — the diff carries the *what*, the trailer carries the
# *who/where*. Push failures are silent by design: commits pile up locally and
# ride out with the next successful flush (offline mode).

SYNC_DEBOUNCE_SECS = 3.0

# scope -> {entry: (action, source)}. An entry is the relpath that changed, or
# "old → new" for the moves. Last action wins: a file saved then deleted inside
# one window reads as a delete, which is what the diff will show anyway.
_pending: dict[str, dict[str, tuple[str, str]]] = {}
_pending_lock = threading.Lock()
_debounce_timer: threading.Timer | None = None
_flush_lock = threading.Lock()          # one flush at a time; timer + manual overlap
_state_callback = None                  # app.py mirrors states into the status bar


def on_sync_state(callback) -> None:
    """Register a listener for sync-state changes: callback(state, detail).
    States: busy / ok / offline."""
    global _state_callback
    _state_callback = callback


def _emit(state: str, detail: str = "") -> None:
    if _state_callback:
        try:
            _state_callback(state, detail)
        except Exception:  # noqa: BLE001 — UI mirroring must never break the flush
            pass


def queue_sync(scope: str, entry: str, action: str = "save",
               source: str = "human-edit") -> None:
    """Note a change and (re)arm the debounce — called on the bridge's worker
    thread right after a successful disk write. `action` becomes the verb in the
    commit message (save / add / rename / move / delete), `source` the line that
    says whether a person in the app did it or it arrived from outside."""
    global _debounce_timer
    with _pending_lock:
        _pending.setdefault(scope, {})[entry] = (action, source)
        if _debounce_timer:
            _debounce_timer.cancel()
        _debounce_timer = threading.Timer(SYNC_DEBOUNCE_SECS, flush_sync)
        _debounce_timer.daemon = True
        _debounce_timer.start()
    _emit("busy")


def _scope_prefix(scope: str) -> str:
    return "products" if scope == "products" else f"clients/{scope}"


def _split_scope(rel: str) -> tuple[str, str] | None:
    """`clients/sarah-mitchell/income/x.pdf` → ("sarah-mitchell", "income/x.pdf").
    None for anything no client or the product library owns (repo-level files)."""
    parts = rel.split("/")
    if parts[0] == "products" and len(parts) > 1:
        return "products", "/".join(parts[1:])
    if parts[0] == "clients" and len(parts) > 2:
        return parts[1], "/".join(parts[2:])
    return None


def _mentions(entry: str) -> list[str]:
    """The paths a pending entry names — a move reads "old → new", a restore
    "path @ sha"."""
    return [side.split(" @ ")[0].strip() for side in entry.split("→")]


def queue_external() -> int:
    """Queue whatever changed on disk without passing through us: a file dropped
    into the folder from Explorer, an agent writing to the checkout, Word saving
    over a document, work done while the app was closed.

    A backup can't depend on the app being the one that made the change, so the
    working tree goes through the same debounce every in-app write uses. Changes
    the app already queued are left alone — it knows what the user actually did
    better than `git status` does (a rename is a rename, not a delete and an add).
    """
    try:
        root = local_repo_path()
    except RepoError:
        return 0
    res = _git(["status", "--porcelain", "-z", "-uall"], cwd=root)
    if res.returncode != 0:
        return 0
    with _pending_lock:
        known = {s: [m for e in p for m in _mentions(e)] for s, p in _pending.items()}
    queued = 0
    records = res.stdout.split("\0")
    i = 0
    while i < len(records):
        rec = records[i]
        i += 1
        if len(rec) < 4:
            continue
        code, rel = rec[:2], rec[3:]
        if "R" in code or "C" in code:
            i += 1          # rename/copy carries its source path as an extra record
        scoped = _split_scope(rel)
        if not scoped:
            continue
        scope, path = scoped
        # Ours already, either by name or because it sits under a folder we moved
        if any(path == m or path.startswith(m + "/") for m in known.get(scope, [])):
            continue
        verb = ("add" if code == "??" or "A" in code
                else "delete" if "D" in code else "save")
        queue_sync(scope, path, verb, source="filesystem")
        queued += 1
    return queued


def _ahead_count(root: Path) -> int:
    """Local commits the remote hasn't seen (0 when no upstream is set)."""
    res = _git(["rev-list", "--count", "@{u}..HEAD"], cwd=root)
    return int(res.stdout.strip()) if res.returncode == 0 else 0


def flush_sync() -> None:
    """Commit pending scopes and push — including strays from prior sessions."""
    with _flush_lock:
        with _pending_lock:
            batches = {s: dict(p) for s, p in _pending.items()}
            _pending.clear()
        try:
            root = local_repo_path()
        except RepoError:
            return

        for scope, entries in batches.items():
            prefix = _scope_prefix(scope)
            _git(["add", "-A", "--", prefix], cwd=root)
            # Identical content re-saved (or an empty folder, which git doesn't
            # track) → nothing staged → no empty commit
            if _git(["diff", "--cached", "--quiet"], cwd=root).returncode == 0:
                continue
            # One line per verb, so a mixed batch stays readable: what the LO did
            # is in the subject, the full inventory is in the body.
            grouped: dict[str, list[str]] = {}
            sources: set[str] = set()
            for entry, (action, source) in sorted(entries.items()):
                grouped.setdefault(action, []).append(entry)
                sources.add(source)
            verbs = sorted(grouped)
            verb = verbs[0] if len(verbs) == 1 else "update"
            subject = grouped[verbs[0]][0] if len(entries) == 1 else f"{len(entries)} files"
            title = f"{verb}({scope}): {subject}"
            body = "\n".join([f"scope: {prefix}"]
                             + [f"{v}: {', '.join(grouped[v])}" for v in verbs]
                             + [f"source: {', '.join(sorted(sources))}"])
            res = _git(["-c", f"user.name={SERVICES.user_name}",
                        "-c", f"user.email={SERVICES.user_id}@mortgagework.local",
                        "commit", "-m", title, "-m", body], cwd=root)
            if res.returncode != 0:
                print(f"[sync] commit failed for {scope}: {res.stderr.strip()}")

        if _ahead_count(root) == 0:
            _emit("ok")
            return
        _emit("busy")
        res = _git(["push"], cwd=root, timeout=60)
        if res.returncode == 0:
            _emit("ok")
        else:
            # Offline / auth hiccup: the ledger is safe locally, retry rides
            # on the next save or the next manual sync click.
            last = res.stderr.strip().splitlines()[-1] if res.stderr else "unknown"
            print(f"[sync] push skipped: {last}")
            _emit("offline", str(_ahead_count(root)))


# ── Filesystem watch (disk is the truth, the UI follows) ──
#
# Most writes never pass through us: files copied in from Explorer, an agent
# writing to the checkout, a `git pull` landing new documents. So the tree is
# rebuilt from disk on every change instead of being patched by hand — the
# only way a UI can't drift into showing files that aren't there (or hiding
# files that are).

WATCH_DEBOUNCE_SECS = 0.5

_observer = None
_watch_timer: threading.Timer | None = None
_watch_lock = threading.Lock()


def start_watch(callback) -> bool:
    """Watch the checkout; call `callback()` once changes settle.

    Idempotent, and best-effort by design: without a working watcher the UI
    simply refreshes on the usual triggers (boot, view switch, sync) instead
    of live, so a failure here is worth a log line and nothing more.
    """
    global _observer
    if _observer is not None:
        return True
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("[watch] watchdog not installed — live tree updates disabled")
        return False
    try:
        root = local_repo_path()
    except RepoError:
        return False
    if not root.is_dir():
        return False        # nothing cloned yet; the first snapshot re-arms us

    def fire():
        global _watch_timer
        with _watch_lock:
            _watch_timer = None
        try:
            callback()
        except Exception as exc:  # noqa: BLE001 — a bad rescan must not kill the watcher
            print(f"[watch] rescan failed: {exc}")
        # The change may not have come from the app at all — back it up anyway
        try:
            n = queue_external()
            if n:
                print(f"[watch] queued {n} external change(s)")
        except Exception as exc:  # noqa: BLE001 — same: never kill the watcher
            print(f"[watch] queue failed: {exc}")

    git_dir = f"{os.sep}.git"

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            global _watch_timer
            # .git churns on every add/commit/push we make ourselves; watching
            # it would turn each sync into a snapshot storm.
            if git_dir + os.sep in event.src_path or event.src_path.endswith(git_dir):
                return
            # "Directory modified" carries no information we render — and it is
            # how .git activity leaks out (its parent gets touched). Every real
            # change to a row also emits its own file/dir create-delete-move
            # event, so dropping these loses nothing.
            if event.is_directory and event.event_type == "modified":
                return
            # A folder copy arrives as a burst of events — coalesce them into
            # one rescan, and let an ongoing burst push the deadline out.
            with _watch_lock:
                if _watch_timer:
                    _watch_timer.cancel()
                _watch_timer = threading.Timer(WATCH_DEBOUNCE_SECS, fire)
                _watch_timer.daemon = True
                _watch_timer.start()

    obs = Observer()
    obs.schedule(Handler(), str(root), recursive=True)
    obs.daemon = True
    obs.start()
    _observer = obs
    print(f"[watch] watching {root}")
    return True


def workspace_snapshot(pull: bool = True) -> dict:
    """Everything the frontend needs on boot, in one JSON-serializable blob."""
    root = ensure_repo(pull=pull)
    # One status read for the whole snapshot — every tree in here is painted
    # from it, so the colors can't disagree between clients and products.
    status = git_status(root)
    active, closed = scan_clients(root, status)
    return {
        "user": {"id": SERVICES.user_id, "name": SERVICES.user_name},
        "repo": {"path": str(root), "url": SERVICES.work_repo_url},
        "clients": active,
        "closed": closed,
        "productTree": scan_products(root, status),
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
