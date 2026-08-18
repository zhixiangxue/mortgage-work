"""Work-repo engine: managed clone, validation, and client/product scanning.

This is the layer that turns the git repo into what the UI shows. Design
rules it implements (see the work repo's README for the full spec):

* The repo is the single source of truth. Nothing here persists anything
  outside the repo — scanning rebuilds the full picture from disk each time.
* The local checkout is MANAGED: it always lives at
  ``~/MortgageWork/<repo-name>/``, derived from WORK_REPO_URL. First boot
  clones; later boots fast-forward pull. A pull that can't fast-forward
  self-heals (blockers parked aside, diverged commits rebased) and only then
  degrades to offline mode (the local copy keeps working) — a sync failure
  must never be permanent, and never blocks the app.
* A client exists iff its folder exists. A missing/broken client.yaml only
  flags the client for repair — it never hides it.

Run standalone for a smoke test:

    uv run python workrepo.py
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

import yaml

from config import SERVICES
from user import current_user

log = logging.getLogger(__name__)

# Remote URLs may carry embedded credentials (Codeup ships no anonymous
# access, so the demo token lives in work_repo_url). Strip user:pass from
# any text headed for logs, boot events, or UI-facing error messages.
_CRED_RE = re.compile(r"\b(https?://)[^/\s@]+:[^/\s@]+@")


def redact(text: str) -> str:
    return _CRED_RE.sub(r"\1", text or "")


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
HIDDEN_FILES = {"client.yaml", "index.jsonl"}

# Workspace instructions — LO-authored preferences injected into the chat
# agent's system prompt. Lives at the repo root, human-owned, git-synced.
AGENTS_FILE = "AGENTS.md"

# Conversation-derived memory (seeka: vector store + archive). Inside the repo
# so it sits with the client data it is about; gitignored for now, but that's a
# choice rather than a constraint — un-ignore it and memories follow the LO to a
# new machine. Both the memory agent and the app open this same directory, which
# is why the name lives here with the rest of the repo layout instead of in
# either caller.
SEEKA_DIR = ".seeka"

# Extensions rendered as text in the viewer; anything else ships as base64.
TEXT_EXTENSIONS = {".md", ".txt", ".ai", ".yaml", ".yml", ".eml", ".csv", ".json", ".html", ".htm"}

# Upper bound for what we push through the JS bridge in one call — a base64
# payload beyond this would visibly freeze the webview.
MAX_FILE_BYTES = 40 * 1024 * 1024


class RepoError(RuntimeError):
    """Fatal work-repo problem the UI should surface (bad URL, clone failed…)."""


# ── Git plumbing ──
#
# Rule for every network step below: the app must open (and stay usable) with
# no GitHub at all. So reachability is probed with a short, cheap request first,
# and only a remote that already answered gets the generous budget a real
# fetch/push needs. A demo laptop on a captive portal costs one probe, not a
# hang — the local checkout is a complete copy of the work either way.

# Cheapest question git can ask the network ("is anybody there?"). Generous on
# purpose: the SSH handshake alone can take several seconds on a hotel network,
# and mistaking a slow-but-working remote for a dead one is the worse error —
# nobody is waiting on this, boot already opened on the local copy.
PROBE_TIMEOUT_SECS = 15
# Transfer budget, spent only after a successful probe.
NET_TIMEOUT_SECS = 90
# First run has to download everything; the only step allowed to take minutes.
CLONE_TIMEOUT_SECS = 600
# How long a structural check waits for a sibling process's clone to land its
# checkout. Keep under CLONE_TIMEOUT_SECS: the sibling either finishes or dies
# within its own timeout, and we want to report a failure, not hang forever.
CLONE_WAIT_SECS = 480
# One sync round (pull + push) reuses a single probe result.
REACHABLE_TTL_SECS = 20


# Bundled MinGit (Windows): shipped inside the frozen package so a fresh box
# works with zero installs. scripts/bootstrap_mingit.ps1 fetches the vendor
# tree at build time; the spec packs it into _internal/vendor/mingit/.
_RESOLVED_GIT: str | None = None


def _git_binary() -> str:
    """Which git to run: bundled MinGit first, system git as fallback.

    Bundled wins whenever it is present so behavior never depends on what
    the machine happens to have installed. Resolved once per process.
    """
    global _RESOLVED_GIT
    if _RESOLVED_GIT:
        return _RESOLVED_GIT
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    bundled = base / "vendor" / "mingit" / "cmd" / "git.exe"
    if bundled.is_file():
        _RESOLVED_GIT = str(bundled)
        log.info("workrepo: using bundled MinGit (%s)", bundled)
    else:
        _RESOLVED_GIT = "git"
    return _RESOLVED_GIT


def _git_env() -> dict:
    # Force non-interactive git: a hidden password/hostkey prompt must fail
    # fast (we handle the error) instead of hanging the app on boot.
    env = os.environ | {
        "GIT_TERMINAL_PROMPT": "0",
        # rebase --continue opens an editor by default; without this it hangs
        # forever waiting for a commit-message edit that nobody can type.
        "GIT_EDITOR": "true",
        # Stable English messages — the pull rescue below parses git's stderr,
        # and a localized "would be overwritten" would sail right past it.
        "LC_ALL": "C",
        "GIT_SSH_COMMAND": os.environ.get(
            "GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10"),
    }
    git = _git_binary()
    if git != "git":
        # Bundled MinGit: its helpers (git-remote-https, git-upload-pack…)
        # must resolve from the vendor tree, not whatever PATH happens to
        # hold — on a fresh box PATH holds nothing.
        env["PATH"] = str(Path(git).parent) + os.pathsep + env.get("PATH", "")
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill git *and* the transport it spawned (ssh / git-remote-https).

    Killing only git leaves the transport alive holding the output pipes, and
    reading those pipes is what a timeout has to do next — that is how a
    "timeout" quietly turns back into a hang.
    """
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001 — already gone, or no permission; fall through
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.communicate(timeout=5)     # reap, now that nothing holds the pipes
    except Exception:  # noqa: BLE001 — a stuck reap must not become our problem
        pass


def _run_git(args: list[str], cwd: Path | None, timeout: int, text: bool):
    """git with a timeout that actually holds. Returns (returncode, out, err)."""
    try:
        proc = subprocess.Popen(
            [_git_binary(), *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            # git speaks UTF-8; text mode would otherwise decode with the OS locale
            # and blow up on a non-ASCII filename or a "→" in one of our messages.
            text=text, encoding="utf-8" if text else None,
            errors="replace" if text else None, env=_git_env(),
            # Own process group, so a timeout can take the whole tree down.
            start_new_session=sys.platform != "win32")
    except FileNotFoundError:
        # No git anywhere — the bundled MinGit is missing (mac build, or a
        # stripped package) and the system has none. Report it as a failed
        # command (127 = command not found) so every caller's existing error
        # handling applies; the stderr message travels up to the boot gate.
        msg = "git is not installed — install git first (xcode-select --install on macOS)"
        return 127, "" if text else b"", msg if text else msg.encode()
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        log.warning("workrepo git %s timed out after %ss", args[0], timeout)
        msg = f"git {args[0]} timed out after {timeout}s"
        # 124 is what timeout(1) reports. Every caller here already handles
        # "git said no", and none of them can do anything useful with a raised
        # TimeoutExpired — so a wedged network costs `timeout` seconds and
        # nothing more.
        return 124, "" if text else b"", msg if text else msg.encode()


def _git(args: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    code, out, err = _run_git(args, cwd, timeout, text=True)
    return subprocess.CompletedProcess(args, code, out, err)


def _git_bytes(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Same, undecoded — for reading file contents out of history (PDFs)."""
    code, out, err = _run_git(args, cwd, 120, text=False)
    return subprocess.CompletedProcess(args, code, out, err)


def _last_line(text: str | None, fallback: str = "no answer") -> str:
    lines = (text or "").strip().splitlines()
    return lines[-1] if lines else fallback


def repo_name(url: str) -> str:
    """Last path segment of the remote, without the .git suffix."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.git$", "", name)


def _normalized_repo(url: str) -> tuple[str, str] | None:
    """(host, path) for a git URL, so ssh and https spellings of the same
    public repo compare equal: git@github.com:owner/repo.git ≍
    https://github.com/owner/repo.git. Returns None for URLs we can't parse."""
    url = url.strip()
    if url.startswith("git@"):
        # scp-style: git@github.com:owner/repo.git
        host, _, path = url.partition(":")
        host = host.rsplit("@", 1)[-1]
    else:
        m = re.match(r"^(?:https?|ssh|git)://(?:[^@/]+@)?([^/:]+)/(.+)$", url)
        if not m:
            return None
        host, path = m.group(1), m.group(2)
    return host.lower(), path.rstrip("/")


def same_repo(a: str, b: str) -> bool:
    """Do two remote URLs point at the same repository?"""
    na, nb = _normalized_repo(a), _normalized_repo(b)
    return na is not None and na == nb


def git_available() -> bool:
    """Is git on PATH? A demo box without Xcode CLT fails every git step —
    detect once so the boot gate can say 'install git' instead of timing out."""
    return _git(["--version"], timeout=10).returncode == 0


def local_repo_path() -> Path:
    u = current_user()
    if not u.work_repo_url:
        raise RepoError("WORK_REPO_URL is not configured (.env)")
    return WORKSPACE_ROOT / repo_name(u.work_repo_url)


# True once a network step failed — the UI says "local copy" and the status-bar
# click retries. Reset by the next successful pull/push.
_offline = False
_reach_cache: tuple[float, bool] = (0.0, False)


def is_offline() -> bool:
    """Did the last network attempt fail? (What the status bar reports.)"""
    return _offline


def forget_reachability() -> None:
    """Drop the cached probe result so an explicit "sync now" really re-tries
    instead of trusting a 20-second-old "no network"."""
    global _reach_cache
    _reach_cache = (0.0, False)


def remote_reachable(root: Path | None = None) -> bool:
    """Is the remote answering right now?

    Every network step goes through this gate: if the answer is no, we stay on
    the local copy immediately instead of sitting on a pull or a push that was
    going to time out anyway. `ls-remote` asks for nothing but a ref list, so a
    healthy remote answers in well under a second.
    """
    global _reach_cache
    ts, ok = _reach_cache
    if time.monotonic() - ts < REACHABLE_TTL_SECS:
        return ok
    try:
        url = current_user().work_repo_url
        root = root or local_repo_path()
    except RepoError:
        return False
    # Before the first clone there is no "origin" to ask about — probe the URL.
    cloned = (root / ".git").is_dir()
    res = _git(["ls-remote", "--exit-code", "-q", "origin" if cloned else url, "HEAD"],
               cwd=root if cloned else None, timeout=PROBE_TIMEOUT_SECS)
    ok = res.returncode == 0
    _reach_cache = (time.monotonic(), ok)
    if not ok:
        log.warning("workrepo remote unreachable: %s", redact(_last_line(res.stderr)))
    return ok


# The paths a merge refuses to overwrite — tab-indented under git's complaint,
# relative to the repo root (every pull here runs with cwd=root).
_UNTRACKED_BLOCK_RE = re.compile(
    r"untracked working tree files would be overwritten by \w+:\n"
    r"((?:[ \t]+[^\n]+\n?)+)")


def _unquote_git_path(rel: str) -> str:
    """Undo git's C-style quoting of non-ASCII paths in its messages
    (\"cl\\303\\251ment.pdf\" → clément.pdf)."""
    if len(rel) > 1 and rel.startswith('"') and rel.endswith('"'):
        try:
            return (rel[1:-1].encode("latin-1", "backslashreplace")
                    .decode("unicode_escape").encode("latin-1").decode("utf-8"))
        except (UnicodeError, ValueError):
            return rel[1:-1]
    return rel


def _sideline_blockers(root: Path, stderr: str) -> int:
    """Park the untracked files a pull refuses to overwrite; return how many.

    The one pull failure retrying can never fix: a file that exists here
    untracked (a session.json from an older build, a stray copy) now exists
    tracked on the remote, and from then on every merge aborts before touching
    anything — a permanent deadlock. The remote's version is the truth (the
    repo is the source of truth by design), but the local bytes could still be
    someone's work, so they're parked under ~/MortgageWork/.sync-conflict/
    instead of deleted, and the pull gets retried.
    """
    m = _UNTRACKED_BLOCK_RE.search(stderr or "")
    if not m:
        return 0
    backup = (WORKSPACE_ROOT / ".sync-conflict" / root.name
              / datetime.now().strftime("%Y%m%d-%H%M%S"))
    parked = 0
    for line in m.group(1).splitlines():
        rel = _unquote_git_path(line.strip())
        src = root / rel
        if not src.exists():
            continue
        dest = backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dest))
            parked += 1
        except OSError as exc:
            log.warning("workrepo could not park %s: %s", rel, exc)
    if parked:
        log.info("workrepo parked %d pull blocker(s) → %s", parked, backup)
    return parked


def _needs_rescue(stderr: str) -> bool:
    """Failures --ff-only can never clear on its own, no matter how often it
    retries: diverged histories, or dirty tracked files sitting in the merge's
    way. Anything else (transfer died, auth) keeps the normal retry path."""
    s = stderr or ""
    return ("fast-forward" in s or "divergent" in s
            or "would be overwritten" in s)


def _needs_push_force(stderr: str) -> bool:
    """Push rejected because the remote has commits we don't (non-fast-forward).
    Only true when the remote explicitly refused the update — network blips
    and auth failures are not divergence and should not trigger a force."""
    s = stderr or ""
    return "rejected" in s or "fast-forward" in s or "non-fast-forward" in s


def _rebase_pull(root: Path) -> subprocess.CompletedProcess:
    """Settle a diverged checkout: replay unpushed local commits on top of the
    remote — nothing already published is rewritten — with autostash parking
    any uncommitted tracked edits around the operation. A real content
    conflict aborts back to the exact pre-pull state and stays offline for a
    human: self-healing must never turn into self-inflicted merge markers.
    -c instead of --autostash so gits older than 2.27 play too.
    """
    args = ["-c", "rebase.autoStash=true", "pull", "--rebase"]
    res = _git(args, cwd=root, timeout=NET_TIMEOUT_SECS)
    if res.returncode != 0 and _sideline_blockers(root, res.stderr):
        res = _git(args, cwd=root, timeout=NET_TIMEOUT_SECS)
    if res.returncode != 0:
        # Never leave a half-done rebase behind — it would wedge every later
        # commit and pull. A no-op when the rebase never started.
        _git(["rebase", "--abort"], cwd=root)
    return res


def _pull(root: Path) -> bool:
    """Bring the checkout up to date if — and only if — the remote is answering.

    Fast-forward is the happy path; when it can't, the rescue ladder above
    (park untracked blockers → rebase diverged commits) runs before giving up,
    so no single stray file or offline stretch can wedge sync forever.
    Never raises: a boot that can't reach GitHub still has to open the app. The
    return value is only bookkeeping for the offline flag.
    """
    global _offline
    # Clear any rebase a prior crash or buggy merger left behind — a stuck
    # rebase makes every subsequent git operation fail and locks the repo.
    recover_stuck_rebase(root)
    if not remote_reachable(root):
        _offline = True
        _emit("offline", str(_ahead_count(root)))
        return False
    res = _git(["pull", "--ff-only"], cwd=root, timeout=NET_TIMEOUT_SECS)
    if res.returncode != 0 and _sideline_blockers(root, res.stderr):
        res = _git(["pull", "--ff-only"], cwd=root, timeout=NET_TIMEOUT_SECS)
    if res.returncode != 0 and _needs_rescue(res.stderr):
        res = _rebase_pull(root)
    if res.returncode != 0:
        # Transfer died mid-way, or a rescue that chose to stand down.
        # Fetch to keep remote refs current so a force-push can proceed
        # cleanly on the next flush instead of wedging sync forever.
        _git(["fetch", "origin"], cwd=root, timeout=NET_TIMEOUT_SECS)
        log.warning("workrepo pull skipped (diverged, will force-push local): %s",
                    _last_line(res.stderr, 'unknown'))
        _offline = True
        _emit("offline", str(_ahead_count(root)))
        return False
    _offline = False
    if "already up to date" not in res.stdout.lower():
        log.info("📥 pull · new changes landed")
        # New files landed outside flush_sync — reconcile the content index
        # so their doc_ids resolve immediately (KG/RAG locate → local file).
        # Skipped while docindex hasn't booted yet; that init reconciles too.
        try:
            import docindex
            if docindex.all_records():
                docindex.reconcile(root)
        except Exception as exc:
            log.warning("docindex reconcile after pull failed: %s", exc)
    return True


def _untrack_session(root: Path) -> None:
    """Heal a published session.json.

    session.json is device state and must never sync (see the session block at
    the bottom of this file) — but once any machine publishes it, every other
    machine's own untracked copy blocks every pull it makes, forever. Untrack
    it, ignore it, and let the fix ride out with the next push so the whole
    fleet heals; the file itself stays on disk as the device state it is.
    """
    if _git(["ls-files", "--error-unmatch", "--", SESSION_FILE],
            cwd=root).returncode != 0:
        return
    with _flush_lock:       # never interleave with a flush's own add+commit
        _git(["rm", "--cached", "-q", "--", SESSION_FILE], cwd=root)
        ignore = root / ".gitignore"
        lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
        if f"/{SESSION_FILE}" not in lines:
            ignore.write_text("\n".join(lines + [f"/{SESSION_FILE}"]) + "\n",
                              encoding="utf-8")
            _git(["add", "--", ".gitignore"], cwd=root)
        u = current_user()
        res = _git(["-c", f"user.name={u.name}",
                    "-c", f"user.email={u.git_email}",
                    "commit", "-m",
                    f"chore: stop syncing {SESSION_FILE} (device state)"], cwd=root)
    if res.returncode != 0:
        log.warning("sync untrack %s failed: %s", SESSION_FILE, _last_line(res.stderr))
    else:
        log.info("sync untracked %s — device state, never synced", SESSION_FILE)


def ensure_repo(pull: bool = True) -> Path:
    """Clone-or-pull the managed checkout and validate its structure.

    `pull=False` skips the network round-trip — boot uses it so the UI never
    waits on SSH; a background sync pulls right after. Pull failures are
    non-fatal (offline mode); clone failures and structural problems raise
    RepoError.
    """
    url = current_user().work_repo_url
    path = local_repo_path()

    # No git binary = nothing below can ever succeed. Fail before the first
    # network probe so the boot gate shows the real problem, not a timeout.
    if not git_available():
        raise RepoError(
            "git is not installed on this machine — install git first "
            "(macOS: xcode-select --install), then retry")

    if not (path / ".git").is_dir():
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        # The one step with no local copy to fall back on, so it really does
        # need the network. Say that plainly instead of timing out anonymously.
        if not remote_reachable(path):
            raise RepoError(f"first run needs network access to {redact(url)}")
        # A stray non-git directory at the target (a sibling process created
        # <repo>/conversations or .seeka before the first clone landed) makes
        # git refuse: "destination path already exists and is not an empty
        # directory". Park it aside, clone, then fold its contents back in —
        # the first-run race must self-heal, not strand the app forever.
        parked = None
        if path.is_dir():
            if any(path.iterdir()):
                parked = path.parent / f"{path.name}.preclone-{int(time.time())}"
                path.rename(parked)
            else:
                path.rmdir()
        log.info("workrepo cloning %s → %s", redact(url), path)
        _emit_boot("cloning", redact(url))
        res = _git(["clone", url, str(path)], timeout=CLONE_TIMEOUT_SECS)
        if res.returncode != 0:
            # Restore the parked directory so the next boot can retry instead
            # of losing whatever the racing process already wrote there.
            if parked is not None and parked.is_dir() and not path.exists():
                parked.rename(path)
            raise RepoError(f"clone failed: {redact(res.stderr.strip())}")
        # Fold the parked contents (e.g. conversations written during the race)
        # back into the fresh checkout; anything the repo already ships wins.
        if parked is not None and parked.is_dir():
            for item in parked.iterdir():
                dest = path / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            try:
                parked.rmdir()
            except OSError:
                pass    # non-empty leftovers stay parked; next boot can reuse them
    else:
        # Same path but different remote: two identities colliding is an error,
        # but a URL spelling change (ssh → https for demo machines) is just a
        # migration — repoint origin and move on. Read the LOCAL config value:
        # `remote get-url` applies ~/.gitconfig url.insteadOf rewrites (a
        # machine that forces ssh:// over https:// would make it report ssh
        # forever and re-trigger this migration every boot).
        res = _git(["config", "--local", "--get", "remote.origin.url"], cwd=path)
        if res.returncode == 0 and res.stdout.strip() != url:
            if not same_repo(res.stdout.strip(), url):
                raise RepoError(f"{path} tracks {redact(res.stdout.strip())}, expected {redact(url)}")
            log.info("workrepo repointing origin %s → %s", redact(res.stdout.strip()), redact(url))
            repointed = _git(["remote", "set-url", "origin", url], cwd=path)
            if repointed.returncode != 0:
                log.warning("workrepo origin repoint failed: %s",
                            redact(_last_line(repointed.stderr)))
        if pull:
            _emit_boot("pulling")
            _pull(path)
            _untrack_session(path)

    # Structure check, with patience: a sibling process (agent worker racing
    # this boot) may be mid-clone — .git exists but HEAD doesn't resolve yet,
    # and the checkout lands LAST. Waiting beats failing: the overlay shows
    # "downloading" the whole time, and a dead network surfaces as a clone
    # timeout elsewhere, never as a misleading "not a work repo" here.
    missing = [r for r in ("clients", "products") if not (path / r).is_dir()]
    if missing:
        head_ok = False
        deadline = time.monotonic() + CLONE_WAIT_SECS
        while time.monotonic() < deadline:
            head_ok = _git(["rev-parse", "--verify", "HEAD"], cwd=path).returncode == 0
            if head_ok and not [r for r in missing if not (path / r).is_dir()]:
                break
            time.sleep(2)
        # A clone that died mid-checkout (user killed the app on first boot) or
        # a manually wiped worktree leaves a valid .git but no files. If nothing
        # is committed locally, restoring the worktree from HEAD is safe and
        # instant; local commits are someone's work — keep them and let the
        # user decide. -f is deliberate: a clone whose checkout died on a
        # products/index.jsonl we wrote mid-clone leaves that file untracked at
        # the exact path HEAD wants to restore, and a plain checkout refuses to
        # overwrite it. With no local commits to lose, force-restoring the tree
        # is the whole point.
        if head_ok and _ahead_count(path) == 0:
            _emit_boot("restoring")
            res = _git(["checkout", "-f", "HEAD", "--", "."], cwd=path, timeout=90)
            if res.returncode == 0:
                log.info("workrepo restored incomplete worktree from HEAD")

    for required in ("clients", "products"):
        if not (path / required).is_dir():
            raise RepoError(f"not a work repo (missing {required}/): {path}")
    # Heal leftovers from a previous first-run race: a parked preclone dir
    # whose contents never got folded back (clone died, the retry re-cloned
    # fresh, and the parked copy sat there ever since). Its contents were
    # written by OUR earlier boot — fold them into the checkout, repo wins on
    # name collisions, then drop the empty shell.
    def _fold_item(src: Path, dst: Path) -> None:
        """Move src into dst, recursing through dirs that exist on both sides."""
        if src.is_dir() and dst.is_dir():
            for child in src.iterdir():
                _fold_item(child, dst / child.name)
            try:
                src.rmdir()   # now an empty shell (children moved or recursed)
            except OSError:
                pass         # collision files stayed behind; they live on in the shell
            return
        if not dst.exists():
            shutil.move(str(src), str(dst))

    for leftover in sorted(path.parent.glob(f"{path.name}.preclone-*")):
        for item in leftover.iterdir():
            _fold_item(item, path / item.name)
        try:
            leftover.rmdir()
            log.info("workrepo folded leftover %s", leftover.name)
        except OSError:
            # Only name-collision files (repo version won) remain — keep the
            # shell so a human can inspect it; it can never block a boot.
            log.warning("workrepo leftover %s not empty, kept for inspection",
                        leftover.name)
    # Conversations live at the repo top level, next to clients/ and products/.
    # Created on demand (not required) so older repos stay valid; the agent
    # service writes JSONL files here and the sync engine picks them up.
    (path / "conversations").mkdir(exist_ok=True)
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
    # client.yaml is the client's anchor — pin it to the top
    nodes.sort(key=lambda n: n["name"] != "client.yaml")
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
        # What the Edit Client modal pre-fills, in the form's own labels —
        # the strings above are display formatting, not editable facts.
        "edit": _edit_form(meta),
        "tree": build_tree(folder, status),
    }


def _edit_form(meta: dict) -> dict:
    """client.yaml → the New/Edit Client form's field shape (labels, not keys).
    Tolerant of half-broken metadata: every field falls back to the form's own
    default, so Edit doubles as the repair path for a mangled yaml."""
    borrowers = [b for b in (meta.get("borrowers") or []) if isinstance(b, dict)]
    primary = next((b for b in borrowers if b.get("role") != "co_borrower"), {})
    co = next((b for b in borrowers if b.get("role") == "co_borrower"), None)
    contact = meta.get("contact") if isinstance(meta.get("contact"), dict) else {}
    amount = meta.get("amount")
    return {
        "name": str(meta.get("name") or ""),
        "phone": str(contact.get("phone") or ""),
        "email": str(contact.get("email") or ""),
        "purpose": FORM_PURPOSES.get(meta.get("purpose"), "Purchase"),
        "citizenship": CITIZENSHIP_LABELS.get(primary.get("citizenship"), "US Citizen"),
        "amount": f"${amount:,}" if isinstance(amount, (int, float)) else "",
        "co": ({"name": str(co.get("name") or ""),
                "citizenship": CITIZENSHIP_LABELS.get(co.get("citizenship"), "US Citizen")}
               if co else None),
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
    log.info("✏️ edit · %s · %s", relpath, scope)
    return {"ok": True}


def write_pdf(scope: str, relpath: str, b64: str) -> dict:
    """Persist a filled PDF form back over its file. The viewer only saves
    what it already opened, so the target must exist and be a .pdf — this is
    an overwrite channel, never a create one. Bytes ride the bridge base64'd
    (same reason as upload_files: webview Files have no disk path)."""
    target = _resolve_scoped(scope, relpath)
    if target.suffix.lower() != ".pdf":
        raise RepoError(f"not a PDF: {target.name}")
    if not target.is_file():
        raise RepoError(f"no such file: {relpath}")
    data = base64.b64decode(b64 or "")
    if len(data) > MAX_FILE_BYTES:
        raise RepoError(f"{target.name} is too large ({len(data) // 1048576} MB)")
    # A truncated or garbage payload must not eat a client's document
    if not data.startswith(b"%PDF"):
        raise RepoError("not PDF data — refusing to overwrite")
    target.write_bytes(data)
    queue_sync(scope, relpath)
    log.info("✏️ pdf filled · %s · %s", relpath, scope)
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


def _unique_parens(folder: Path, name: str) -> str:
    """untitled.txt → untitled(1).txt → untitled(2).txt when taken.
    The parenthesised counter the OS uses for pasted files."""
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    else:
        ext = "." + ext
    candidate, i = name, 1
    while (folder / candidate).exists():
        candidate = f"{stem}({i}){ext}"
        i += 1
    return candidate


def _upload_rel_parts(item: dict) -> list[str]:
    """Validate a dropped upload path one component at a time.

    Drag/drop directories arrive as repo-relative paths such as
    ``aaa/bank/jan.pdf``. Treat every segment as untrusted bridge input:
    no empty parts, no traversal, and the same reserved-name policy as any
    human-typed tree operation. The caller decides whether the final segment
    is a directory marker or a file name; validation is identical either way.
    """
    raw = str(item.get("path") or item.get("name") or "").replace("\\", "/")
    parts = raw.split("/")
    if not parts or any(part == "" for part in parts):
        raise RepoError("invalid upload path")
    return [_check_name(part) for part in parts]


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
    log.info("➕ new file · %s · %s", rel, scope)
    return {"ok": True, "path": rel}


def paste_text(scope: str, dirrel: str, content: str) -> dict:
    """Drop clipboard text into a folder as untitled.txt. Repeated pastes into
    the same folder get untitled(1).txt, untitled(2).txt — the parenthesised
    counter a user expects from every OS, so pasted transcripts never silently
    overwrite each other."""
    folder = _scoped_dir(scope, dirrel)
    name = _unique_parens(folder, "untitled.txt")
    target = folder / name
    target.write_text(content, encoding="utf-8")
    rel = _rel(scope, target)
    queue_sync(scope, rel, "add")
    log.info("📋 paste text · %s · %s", rel, scope)
    return {"ok": True, "path": rel}


def create_folder(scope: str, dirrel: str = "", name: str = "new-folder") -> dict:
    """New folder. No queue_sync: git tracks files, not directories, so an empty
    folder has nothing to commit — it rides along with its first file."""
    folder = _scoped_dir(scope, dirrel)
    target = folder / _unique(folder, _check_name(name))
    target.mkdir()
    rel = _rel(scope, target)
    log.info("➕ new folder · %s · %s", rel, scope)
    return {"ok": True, "path": rel}


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
    log.info("🚚 rename · %s → %s", relpath, rel)
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
    log.info("🚚 move · %s → %s", relpath, rel)
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
    log.info("🗑️ delete · %s · %s", relpath, scope)
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
    log.info("➕ duplicate · %s · %s", rel, scope)
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
    log.info("➕ copy · %s · %s", rel, scope)
    return {"ok": True, "path": rel}


# Directory for OS files dropped into chat — not a client scope, not synced.
# Files land here so the agent can read them through its normal tools, without
# polluting a client folder or waiting for a commit round-trip. Gitignored.
TMP_DIR = ".tmp"


def _ensure_tmp(root: Path) -> Path:
    """Create the .tmp directory if missing and make sure git ignores it.

    Idempotent: mkdir + gitignore check run every time because the cost is
    trivial and the alternative is a confusing crash the first time a user
    drops a file into chat on a fresh checkout.
    """
    tmp = root / TMP_DIR
    tmp.mkdir(exist_ok=True)
    ignore = root / ".gitignore"
    entry = f"/{TMP_DIR}/"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    if entry not in lines:
        ignore.write_text("\n".join(lines + [entry]) + "\n", encoding="utf-8")
    return tmp


def upload_files(scope: str, dirrel: str, files: list[dict]) -> dict:
    """Drag & drop / paste upload.

    Backwards-compatible payloads still look like ``{"name": ..., "b64": ...}``.
    Directory-aware drops may send ``{"path": "aaa/bank/jan.pdf", "b64": ...}``
    plus directory markers ``{"path": "aaa/bank", "dir": True}`` so empty
    folders and folder pills work too.

    Existing directories are merged; existing files never get overwritten —
    conflicts use OS-style parenthesised names (``jan(1).pdf``).
    """
    root = local_repo_path()
    if scope == "tmp":
        folder = _ensure_tmp(root)
        tmp_scope = True
    else:
        folder = _scoped_dir(scope, dirrel)
        tmp_scope = False

    dir_map: dict[tuple[str, ...], tuple[str, ...]] = {}
    roots: list[dict] = []
    roots_seen: set[tuple[str, str]] = set()
    written: list[Path] = []

    def remember_root(path: str, name: str, is_dir: bool) -> None:
        key = ("dir" if is_dir else "file", path)
        if key in roots_seen:
            return
        roots_seen.add(key)
        roots.append({"path": path, "name": name, "dir": is_dir})

    def ensure_dir(parts: list[str]) -> tuple[Path, list[str]]:
        current = folder
        out: list[str] = []
        for idx, part in enumerate(parts):
            src_key = tuple(parts[:idx + 1])
            mapped = dir_map.get(src_key)
            if mapped:
                out = list(mapped)
                current = folder.joinpath(*out)
                continue

            name = part
            target = current / name
            if target.exists() and not target.is_dir():
                name = _unique_parens(current, name)
                target = current / name
            target.mkdir(exist_ok=True)
            out.append(name)
            dir_map[src_key] = tuple(out)
            current = target
        return current, out

    for item in files or []:
        parts = _upload_rel_parts(item)
        if item.get("dir"):
            _, out_parts = ensure_dir(parts)
            if out_parts:
                root_name = out_parts[0]
                remember_root(root_name, root_name, True)
            continue

        parent, out_parent = ensure_dir(parts[:-1])
        filename = _unique_parens(parent, parts[-1])
        data = base64.b64decode(item.get("b64") or "")
        if len(data) > MAX_FILE_BYTES:
            raise RepoError(f"{filename} is too large ({len(data) // 1048576} MB)")
        target = parent / filename
        target.write_bytes(data)
        written.append(target)

        if out_parent:
            root_name = out_parent[0]
            remember_root(root_name, root_name, True)
        else:
            remember_root(filename, filename, False)

    if not tmp_scope:
        # Tmp files are gitignored — no sync, no commit, no round-trip.
        for target in written:
            queue_sync(scope, _rel(scope, target), "add")
    log.info("⬆️ upload · %d file(s), %d root item(s) · %s", len(written), len(roots),
             f"{TMP_DIR}/" if tmp_scope else (dirrel or "/"))
    paths = [_rel(scope, target) if not tmp_scope else target.relative_to(folder).as_posix()
             for target in written]
    return {"ok": True, "count": len(written),
            "names": [Path(path).name for path in paths],
            "paths": paths, "roots": roots}


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
    log.info("⬆️ add files · %d file(s) · %s", len(written), dirrel or "/")
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


def open_external(scope: str, relpath: str) -> dict:
    """Open a file in the OS default application (Word → Microsoft Word, etc.)."""
    target = _resolve_scoped(scope, relpath)
    if not target.is_file():
        raise RepoError(f"no such file: {relpath}")
    if sys.platform == "win32":
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
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
        rows.append([when, "YOU" if who == current_user().name else who.upper(), what, sha])
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
    log.info("♻️ restore · %s · %s", relpath, sha[:7])
    return {"ok": True, "path": relpath}


# ── Client creation (the folder IS the client) ──
#
# One folder per client, holding structured facts (client.yaml) and whatever
# documents the LO drops in. Five document buckets scaffold the mortgage data
# collection flow — they are advisory, not a system dependency: LOs can rename,
# delete, or reorganize them freely. clerk builds ai/profile.ai later from
# whatever documents actually arrive, wherever they live. Nothing is registered
# anywhere else — creating a client is creating a folder.

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

# Stored keys back to the labels the form shows — what pre-fills Edit Client.
# FORM_PURPOSES differs from PURPOSE_LABELS on purpose: the form says
# "Cash-Out Refinance", the client list abbreviates to "Cash-out Refi".
FORM_PURPOSES = {
    "purchase": "Purchase",
    "refinance": "Refinance",
    "cash_out_refinance": "Cash-Out Refinance",
    "heloc": "HELOC",
    "investment": "Investment Property",
}

CITIZENSHIP_LABELS = {
    "us_citizen": "US Citizen",
    "permanent_resident": "Permanent Resident",
    "non_permanent_resident": "Non-Permanent Resident",
    "foreign_national": "Foreign National",
}

# Five document buckets every client starts with, ordered the way a mortgage
# file collects material. git tracks files not folders, so each gets a
# .gitkeep — otherwise the structure would exist on this machine only.
# These are advisory scaffolding: LOs can rename, delete, or reorganize them.
DOC_BUCKETS = (
    "1-identity",   # Identity & occupancy verification
    "2-income",     # Income & employment documents
    "3-assets",     # Assets & source of funds
    "4-credit",     # Credit & liabilities
    "5-property",   # Property & title
)


def slugify(name: str) -> str:
    """Folder name from a person's name — same rule as the frontend's slugify."""
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()))


def create_client(data: dict) -> dict:
    """Scaffold clients/<slug>/ from the New Client form."""
    facts = _form_facts(data)
    name = facts["name"]
    slug = slugify(name)
    if not slug:
        raise RepoError(f"could not make a folder name from {name!r}")
    root = ensure_repo(pull=False)
    folder = root / "clients" / slug
    if folder.exists():
        raise RepoError(f"{slug} already exists")

    meta = {"schema": 1, "name": name, "purpose": facts["purpose"], "stage": "lead"}
    if facts["digits"]:
        meta["amount"] = int(facts["digits"])
    if facts["contact"]:
        meta["contact"] = facts["contact"]
    meta["borrowers"] = facts["borrowers"]
    meta["created"] = date.today()

    folder.mkdir(parents=True)
    _write_client_yaml(folder, meta)
    for bucket in DOC_BUCKETS:
        (folder / bucket).mkdir()
        (folder / bucket / ".gitkeep").touch()

    # One commit for the whole scaffold — "a client folder was created" is what
    # actually happened.
    queue_sync(slug, "client folder", "create")
    log.info("👤 client created · %s (%s)", name, slug)
    return {"ok": True, "id": slug}


def _form_facts(data: dict) -> dict:
    """The client.yaml facts the New/Edit Client form owns — parsed once,
    shared by create and update so the two can never drift apart."""
    name = (data.get("name") or "").strip()
    if not name:
        raise RepoError("client name required")
    purpose = PURPOSE_KEYS.get((data.get("purpose") or "").strip().lower(), "purchase")
    citizenship = CITIZENSHIP_KEYS.get((data.get("citizenship") or "").strip().lower(),
                                       "us_citizen")
    digits = re.sub(r"[^0-9]", "", str(data.get("amount") or ""))
    co = data.get("co") or None

    # Role is stated, not left to list order. The form already knows it — primary
    # and co-borrower arrive through separate inputs — and dropping it here left
    # two entries distinguishable only by position, which is not a fact anything
    # can read. The wording is the 1003's own: borrower and co-borrower.
    borrowers = [{"name": name, "role": "borrower", "citizenship": citizenship}]
    if co and (co.get("name") or "").strip():
        borrowers.append({
            "name": co["name"].strip(),
            "role": "co_borrower",
            "citizenship": CITIZENSHIP_KEYS.get((co.get("citizenship") or "").strip().lower(),
                                                "us_citizen"),
        })

    contact = {k: v.strip() for k in ("phone", "email") if (v := data.get(k) or "").strip()}
    return {"name": name, "purpose": purpose, "digits": digits,
            "contact": contact, "borrowers": borrowers}


def _write_client_yaml(folder: Path, meta: dict) -> None:
    (folder / "client.yaml").write_text(
        "# Machine-managed by Mortgage Work — do not edit by hand.\n"
        "# Free-form notes belong in ai/profile.ai; this file only holds structured facts.\n"
        + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
        encoding="utf-8")


def update_client(slug: str, data: dict) -> dict:
    """Rewrite the form-owned facts of clients/<slug>/client.yaml in place.

    The folder name is the client's identity and never changes — a renamed
    person keeps their slug, so nothing that points at the folder (tabs,
    pills, history) goes stale. Fields the form doesn't own (stage, created,
    keys other machinery added) carry over untouched; a broken or missing
    yaml is rebuilt from the form, which makes Edit double as the repair path.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug or ""):
        raise RepoError(f"bad client id: {slug!r}")
    folder = local_repo_path() / "clients" / slug
    if not folder.is_dir():
        raise RepoError(f"no such client: {slug}")
    facts = _form_facts(data)
    try:
        meta = yaml.safe_load((folder / "client.yaml").read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            meta = {}
    except Exception:  # noqa: BLE001 — unreadable yaml: rebuild it from the form
        meta = {}
    meta.setdefault("schema", 1)
    meta["name"] = facts["name"]
    meta["purpose"] = facts["purpose"]
    meta.setdefault("stage", "lead")
    if facts["digits"]:
        meta["amount"] = int(facts["digits"])
    else:
        meta.pop("amount", None)        # cleared in the form = cleared in the file
    if facts["contact"]:
        meta["contact"] = facts["contact"]
    else:
        meta.pop("contact", None)
    meta["borrowers"] = facts["borrowers"]
    meta.setdefault("created", date.today())
    _write_client_yaml(folder, meta)
    queue_sync(slug, "client.yaml", "save")
    log.info("👤 client updated · %s", slug)
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
    log.info("🗑️ client deleted · %s", slug)
    return {"ok": True, "id": slug}


# ── Sync engine (save → commit → push, "Dropbox with a git ledger") ──
#
# Every explicit save queues its file here; a debounce window folds a burst of
# saves into one commit per scope. Messages are deterministic and structured
# (title + key/value body) so the history doubles as machine-readable context
# for agents later — the diff carries the *what*, the trailer carries the
# *who/where*.
#
# Commit is immediate (local safety, zero cost). Push is gated so a busy work
# session does not pay one network round-trip per save: it fires when enough
# commits have piled up, when enough time has passed since the last push, or
# when a human explicitly asks for it (sync button, boot, shutdown). Push
# failures are silent by design: commits pile up locally and ride out with
# the next successful flush (offline mode).

SYNC_DEBOUNCE_SECS = 3.0

# Push batching — commits land instantly, but the remote hears about them in
# batches instead of one at a time.
PUSH_BATCH_THRESHOLD = 5       # push when this many commits sit unpushed
PUSH_MIN_INTERVAL_SECS = 120   # …or when this many seconds pass since last push

# scope -> {entry: (action, source)}. An entry is the relpath that changed, or
# "old → new" for the moves. Last action wins: a file saved then deleted inside
# one window reads as a delete, which is what the diff will show anyway.
_pending: dict[str, dict[str, tuple[str, str]]] = {}
_pending_lock = threading.Lock()
_debounce_timer: threading.Timer | None = None
_flush_lock = threading.Lock()          # one flush at a time; timer + manual overlap
_state_callback = None                  # app.py mirrors states into the status bar
_last_push_time: float = 0.0            # monotonic; 0.0 → "never — first push goes through"


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


# ── Boot progress ──
# First run does real work (clone, pull, repair) that can take minutes, and
# the frontend shows it on the boot overlay — a user staring at the window
# must see WHAT the backend is doing, not a frozen curtain or an early error.
_boot_callback = None


def on_boot_progress(callback) -> None:
    """Register a listener for boot-progress events: callback(stage, detail).
    Stages: cloning / pulling / restoring / scanning / retrying."""
    global _boot_callback
    _boot_callback = callback


def _emit_boot(stage: str, detail: str = "") -> None:
    if _boot_callback:
        try:
            _boot_callback(stage, detail)
        except Exception:  # noqa: BLE001 — UI mirroring must never break boot
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
        _debounce_timer = threading.Timer(SYNC_DEBOUNCE_SECS,
                                          lambda: flush_sync(force_push=False))
        _debounce_timer.daemon = True
        _debounce_timer.start()
    _emit("busy")


def _scope_prefix(scope: str) -> list[str]:
    if scope in ("products", "conversations"):
        return [scope]
    if scope == "repo":
        # Repo-root files that ride in the "repo" scope — each one is a
        # standalone file (not a directory), so git add -A gets them all.
        return [AGENTS_FILE, ".gitignore"]
    return [f"clients/{scope}"]


def _split_scope(rel: str) -> tuple[str, str] | None:
    """`clients/sarah-mitchell/income/x.pdf` → ("sarah-mitchell", "income/x.pdf").
    None for anything no client or the product library owns (repo-level files
    like random dotfiles; the known repo-root files map to the "repo" scope)."""
    if rel in (AGENTS_FILE, ".gitignore"):
        return "repo", rel
    parts = rel.split("/")
    if parts[0] in ("products", "conversations") and len(parts) > 1:
        return parts[0], "/".join(parts[1:])
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


def _rebase_in_progress(root: Path) -> bool:
    """True when a rebase is paused mid-flight (conflicts pending or not)."""
    return (root / ".git" / "rebase-merge").exists() or \
           (root / ".git" / "rebase-apply").exists()


def recover_stuck_rebase(root: Path) -> None:
    """Detect and clear a rebase left paused by a prior crash or bug.

    A stuck rebase blocks every later pull, commit, and push — the repo is
    locked until a human runs ``git rebase --continue`` or ``--abort`` by
    hand. This is the self-healing version: if conflicts are already resolved
    (the common case — the merger did its job but forgot the final
    ``--continue``), finish the rebase and salvage the work; only if that
    fails do we abort, so the sync engine can proceed instead of wedging
    forever.
    """
    if not _rebase_in_progress(root):
        return
    log.warning("workrepo found a stuck rebase — attempting recovery")
    # GIT_EDITOR=true is set in _git_env, so --continue won't hang on an
    # editor prompt even if git wants to open the commit-message editor.
    _git(["rebase", "--continue"], cwd=root, timeout=30)
    if _rebase_in_progress(root):
        log.warning("workrepo rebase --continue failed — aborting to unblock sync")
        _git(["rebase", "--abort"], cwd=root)
    else:
        log.info("workrepo recovered stuck rebase — continued successfully")


def _try_llm_merge(root: Path) -> bool:
    """Summon the LLM merger agent to resolve a rebase conflict.

    Called when ``git pull --rebase`` leaves conflicted files — the rebase
    is paused (NOT aborted) so the agent can read base/ours/theirs and
    produce a merged version.

    Returns True if the agent resolved all conflicts and continued the
    rebase successfully, False if it gave up or no LLM is configured.
    """
    try:
        from agents.merger import merge as llm_merge
    except Exception:
        log.info("🐙 merger agent not available — force-push")
        return False

    try:
        result = llm_merge(root)
        if not result.get("ok"):
            log.warning("🐙 merger failed · %s", result.get("error", "unknown"))
            # The LLM gave up but may have left the rebase paused — abort so
            # the caller's force-push isn't blocked by a mid-flight rebase.
            if _rebase_in_progress(root):
                _git(["rebase", "--abort"], cwd=root)
            return False

        # The LLM claims success — but LLMs routinely resolve every conflict
        # and stage the files, then forget the final ``git rebase --continue``.
        # Verify the rebase actually landed before reporting success: an
        # abandoned rebase blocks every subsequent push and leaves the repo
        # wedged until a human notices.
        if _rebase_in_progress(root):
            log.info("🐙 merger ok but rebase still in progress — continuing ourselves")
            cont = _git(["rebase", "--continue"], cwd=root, timeout=60)
            if _rebase_in_progress(root):
                log.warning("🐙 rebase --continue failed after merger: %s",
                            _last_line(cont.stderr, "unknown"))
                _git(["rebase", "--abort"], cwd=root)
                return False

        log.info("🐙 merger resolved conflict · %s", result.get("summary", ""))
        return True
    except Exception as exc:
        log.warning("🐙 merger exception · %s", exc)
        if _rebase_in_progress(root):
            _git(["rebase", "--abort"], cwd=root)
        return False


def flush_sync(force_push: bool = False) -> None:
    """Commit pending scopes and push — including strays from prior sessions.

    Commits are always immediate (local safety, zero cost). Push is gated by
    a batch threshold / time interval so a burst of saves does not become a
    burst of network round-trips; pass ``force_push=True`` when the caller
    speaks for a human who wants everything on the remote right now (sync
    button, boot flush, process exit).
    """
    global _offline, _last_push_time
    with _flush_lock:
        with _pending_lock:
            batches = {s: dict(p) for s, p in _pending.items()}
            _pending.clear()
        try:
            root = local_repo_path()
        except RepoError:
            return

        # Clear any rebase a prior crash or buggy merger left behind. The
        # debounce path reaches flush_sync without going through _pull, so
        # this is the only gate that catches a stuck rebase before a push.
        recover_stuck_rebase(root)

        for scope, entries in batches.items():
            prefixes = _scope_prefix(scope)
            # Update the content index before staging — the index file change
            # should ride in the same commit as the file changes it reflects.
            # Wrapped so an indexer hiccup never touches the git pipeline.
            try:
                import docindex
                docindex.update(root, scope, entries)
            except Exception:
                log.warning("docindex update failed", exc_info=True)
            _git(["add", "-A", "--", *prefixes], cwd=root)
            # The index file lives under products/ but may be modified by a
            # client-scope change; make sure it's always staged.
            _git(["add", "--", "products/index.jsonl"], cwd=root)
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
            body = "\n".join([f"scope: {', '.join(prefixes)}"]
                             + [f"{v}: {', '.join(grouped[v])}" for v in verbs]
                             + [f"source: {', '.join(sorted(sources))}"])
            u = current_user()
            res = _git(["-c", f"user.name={u.name}",
                        "-c", f"user.email={u.git_email}",
                        "commit", "-m", title, "-m", body], cwd=root)
            if res.returncode != 0:
                log.error("sync commit failed for %s: %s", scope, redact(res.stderr.strip()))
            else:
                log.info("📦 commit · %s", title)
                if scope == "products":
                    # Commit succeeded — fire async indexing for product docs.
                    # Wrapped so an indexer hiccup never touches the git pipeline.
                    try:
                        import index
                        index.trigger(scope, entries)
                    except Exception as exc:
                        log.error("index trigger failed: %s", exc)

        ahead = _ahead_count(root)
        if ahead == 0:
            # Nothing to send. Still not "synced" if this round never reached
            # the remote — claiming otherwise is how a demo ends up looking
            # broken instead of looking offline.
            _emit("offline" if _offline else "ok", "0")
            return
        # Push gate: commits are safe locally, so the remote only hears about
        # them in batches — unless a human asked for it. The gate is a number
        # (enough commits piled up), a clock (enough time since last push), or
        # the force flag (boot, sync button, shutdown).
        now = time.monotonic()
        if not (force_push
                or ahead >= PUSH_BATCH_THRESHOLD
                or now - _last_push_time >= PUSH_MIN_INTERVAL_SECS):
            # Defer the push — the pending commits ride out with the next
            # batch, the next interval tick, or the next manual sync.
            _emit("offline" if _offline else "ok", str(ahead))
            return
        _emit("busy")
        # Same gate as the pull: an unreachable remote is answered in one short
        # probe, not by a push that hangs. The commits are already safe locally.
        if not remote_reachable(root):
            _offline = True
            _emit("offline", str(_ahead_count(root)))
            return
        # Cloud-drive model: two machines working at the same time is normal.
        # Try a clean rebase first — when the same files weren't touched on
        # both sides the history stays linear with no manual step.
        #
        # When a rebase hits a real content conflict, summon the LLM merger
        # agent to resolve it intelligently — it reads both versions of every
        # conflicted file and produces a merge that keeps all meaningful
        # content.  If the merger fails (or no LLM is configured), fall back
        # to force-push: the machine pushing right now is authoritative.
        _git(["fetch", "origin"], cwd=root, timeout=NET_TIMEOUT_SECS)
        behind_res = _git(["rev-list", "--count", "HEAD..@{u}"], cwd=root)
        force = False
        if behind_res.returncode == 0:
            behind_n = int(behind_res.stdout.strip() or "0")
            if behind_n > 0:
                log.info("sync remote ahead by %d commit(s) — rebasing before push", behind_n)
                # Do the rebase ourselves instead of through _rebase_pull so
                # conflicted files stay on disk for the merger to read.
                rebase_args = ["-c", "rebase.autoStash=true", "pull", "--rebase"]
                rebase_res = _git(rebase_args, cwd=root, timeout=NET_TIMEOUT_SECS)
                if rebase_res.returncode != 0 and _sideline_blockers(root, rebase_res.stderr):
                    rebase_res = _git(rebase_args, cwd=root, timeout=NET_TIMEOUT_SECS)
                if rebase_res.returncode != 0:
                    # Rebase hit a content conflict — the LLM merger reads both
                    # sides and writes a combined version. This step can run for
                    # minutes, so tell the UI before it starts: otherwise the
                    # sync indicator's own timeout flips it to a misleading
                    # "offline" while the merge is still working.
                    _emit("resolving")
                    merged = _try_llm_merge(root)
                    if not merged:
                        # LLM couldn't resolve — abort and force-push
                        _git(["rebase", "--abort"], cwd=root)
                        log.warning("sync rebase conflict — force-pushing local (cloud-drive model): %s",
                                    _last_line(rebase_res.stderr, 'unknown'))
                        force = True
        # Rebased or already in sync — push should be a clean fast-forward,
        # unless a conflict forced us to overwrite.
        res = _git(["push", "--force-with-lease"] if force else ["push"],
                   cwd=root, timeout=NET_TIMEOUT_SECS)
        # Tight race: someone pushed between our fetch and our push. Retry
        # the full cycle once — most races resolve on the second attempt.
        if res.returncode != 0 and _needs_push_force(res.stderr):
            log.warning("sync push rejected — retrying fetch+rebase")
            _git(["fetch", "origin"], cwd=root, timeout=NET_TIMEOUT_SECS)
            retry_res = _rebase_pull(root)
            if retry_res.returncode == 0:
                res = _git(["push"], cwd=root, timeout=NET_TIMEOUT_SECS)
            else:
                # Conflict on retry — local still wins.
                log.warning("sync retry rebase conflict — force-pushing local")
                res = _git(["push", "--force-with-lease"], cwd=root, timeout=NET_TIMEOUT_SECS)
        if res.returncode == 0:
            _last_push_time = time.monotonic()
            _offline = False
            _emit("ok")
            log.info("📤 push · %d commit(s)", ahead)
        else:
            # Offline / auth hiccup: the ledger is safe locally, retry rides
            # on the next save or the next manual sync click.
            log.warning("sync push skipped: %s", redact(_last_line(res.stderr, 'unknown')))
            _offline = True
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
        log.warning("watch watchdog not installed — live tree updates disabled")
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
            log.warning("watch rescan failed: %s", exc)
        # The change may not have come from the app at all — back it up anyway
        try:
            n = queue_external()
            if n:
                log.info("watch queued %d external change(s)", n)
        except Exception as exc:  # noqa: BLE001 — same: never kill the watcher
            log.warning("watch queue failed: %s", exc)

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
    log.info("watch watching %s", root)
    return True


def workspace_snapshot(pull: bool = True) -> dict:
    """Everything the frontend needs on boot, in one JSON-serializable blob."""
    root = ensure_repo(pull=pull)
    _emit_boot("scanning")
    # One status read for the whole snapshot — every tree in here is painted
    # from it, so the colors can't disagree between clients and products.
    status = git_status(root)
    active, closed = scan_clients(root, status)
    return {
        "user": {"id": current_user().id, "name": current_user().name,
                 "email": current_user().email},
        "repo": {"path": str(root), "url": current_user().work_repo_url},
        # Working from the local copy because the remote didn't answer. The
        # snapshot itself is complete either way — this only tells the status
        # bar which story to tell, and that a manual sync is worth a click.
        "offline": _offline,
        "clients": active,
        "closed": closed,
        "productTree": scan_products(root, status),
        # Whether the LO has written workspace instructions yet — the frontend
        # uses this to decide between the bootstrap template and live content.
        "agentsMd": (root / AGENTS_FILE).is_file(),
        "session": read_session(root),
    }


# —— Workspace instructions (AGENTS.md) ——
#
# The LO's personal preferences and rules, injected into the chat agent's
# system prompt on every new conversation. Lives at the repo root, so it
# syncs across machines the same way everything else does. Unlike
# machine-managed files (client.yaml, .docs.yaml) this one is human-authored
# and human-owned — the IDE never writes it, only reads.


def read_agents_md() -> dict:
    """Read AGENTS.md from the repo root.

    Returns {content, exists} — ``exists`` lets the frontend decide whether
    to show a bootstrap template or the file's actual contents.
    """
    path = local_repo_path() / AGENTS_FILE
    if not path.is_file():
        return {"content": "", "exists": False}
    return {"content": path.read_text(encoding="utf-8"), "exists": True}


def write_agents_md(content: str) -> dict:
    """Persist AGENTS.md at the repo root and queue sync.

    A brand-new repo doesn't have the file yet, so this is a create-or-
    overwrite — unlike the scoped ``write_file`` which refuses a non-existent
    target. The repo scope in queue_sync handles staging just this one file.
    """
    path = local_repo_path() / AGENTS_FILE
    path.write_text(content, encoding="utf-8")
    queue_sync("repo", AGENTS_FILE)
    log.info("✏️ edit · AGENTS.md · repo")
    return {"ok": True}


# —— UI session (open tabs, focused client, chat) ——
# Device state, not work product: it lives at the repo root, OUTSIDE every
# synced scope (clients/ products/ conversations/), so the sync engine never
# commits it — tab switches must not spam the git history.
SESSION_FILE = "session.json"


def read_session(root: Path | None = None) -> dict | None:
    try:
        path = (root or local_repo_path()) / SESSION_FILE
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except Exception:  # noqa: BLE001 — a corrupt session must never block boot
        return None


def write_session(state: dict) -> dict:
    if not isinstance(state, dict):
        raise RepoError("session state must be an object")
    path = local_repo_path() / SESSION_FILE
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}


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
