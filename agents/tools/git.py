"""Git history tool — read-only for agents, read-write for the merger.

Why read-only by default
------------------------
The verbs a repo-management tool wants — clone, pull, checkout — are exactly the
ones an unattended agent must not have. This checkout is already managed by the
app's sync engine: a `checkout` would move HEAD under a running window, and a
`pull` would race the engine's own. History, on the other hand, is the one thing
an agent genuinely needs and cannot get anywhere else: a folder shows what is
true now, git shows what *changed*, which is the whole question when you are
catching up on work somebody else did.

``mode="rw"`` adds a narrow set of write operations (add, rebase
--continue/--abort) specifically for the LLM-powered conflict resolver —
gated by ``__available__`` so a read-only agent never sees them.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# Diffs and file dumps have no natural size. A seed commit or a rewritten
# document can run to megabytes, which buys nothing and costs a context window.
MAX_CHARS = 20_000
TIMEOUT_SECS = 30

# Windowed frozen builds have no console — without this every git.exe
# flashes its own window while the agent works.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class Git:
    """Git repository tool — read-only history by default, merge writes when
    ``mode="rw"``."""

    name = "git"

    _READ_DESC = (
        "Read the work repository's history: which commits touched which files, "
        "what a commit changed, and what a file looked like at any point. "
        "Read-only — nothing here modifies the repository."
    )
    _RW_DESC = (
        "Git repository operations for conflict resolution. "
        "Read history (log, show, diff) and manage a rebase in progress: "
        "list conflicted files, read the three versions of a conflicted file "
        "(base / ours / theirs), stage resolved files, and continue or abort "
        "the rebase."
    )

    def __init__(self, repo: str | Path, *scope: str | Path,
                 mode: str = "r"):
        """Args: the checkout, folders history may be read for, and the mode.

        ``mode="r"`` (default): read-only log / show / diff — the clerk agent
        uses this so it can read history but never touch the repository.

        ``mode="rw"``: full read-write — the merger agent uses this during
        conflict resolution.  ``__available__`` gates every write method so
        the LLM only sees what its mode permits.

        Scope matters as much here as it does for a file tool. ``show`` prints
        any file at any revision and a bare ``log`` names every path in the
        repository, so history is a second way into the same documents — and
        confining the file tools while leaving this one open confines nothing.
        No scope means the whole repository.
        """
        self._repo = Path(repo).resolve()
        self._scope = [Path(s).resolve().relative_to(self._repo).as_posix()
                       for s in scope]
        self._mode = mode
        self.description = self._RW_DESC if mode == "rw" else self._READ_DESC

    def __available__(self) -> frozenset[str]:
        """Expose only the methods the caller's mode permits.

        ``"r"`` → read-only history (clerk agent).
        ``"rw"`` → full read + merge write (merger agent).
        """
        if self._mode == "r":
            return frozenset({"log", "show", "diff"})
        return frozenset({
            "log", "show", "diff",
            "status", "show_stage", "add",
            "rebase_continue", "rebase_abort",
        })

    # ── path-scope gate ─────────────────────────────────────────────────

    def _pathspec(self, path: str) -> list[str] | str:
        """The trailing ``-- <paths>`` of a git command, or an error to hand back.

        With no path given the scope becomes the pathspec: a bare log would
        otherwise walk the whole repository, which during a per-client pass
        means other borrowers' files listed by name.
        """
        if not self._scope:
            return ["--", path] if path else []
        if not path:
            return ["--", *self._scope]
        want = (self._repo / path).resolve()
        if any(want.is_relative_to(self._repo / s) for s in self._scope):
            return ["--", path]
        return (f"git error: '{path}' is outside the readable set: "
                f"{', '.join(self._scope)}")

    def _run(self, *args: str) -> str:
        """One git invocation. Failures come back as text: a wrong revision is
        something the model should read and correct, not an exception that ends
        its turn."""
        try:
            res = subprocess.run(["git", *args], cwd=self._repo,
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 # GIT_EDITOR=true so rebase --continue doesn't
                                 # hang waiting for a commit-message edit.
                                 env={**os.environ, "GIT_EDITOR": "true"},
                                 creationflags=_NO_WINDOW,
                                 timeout=TIMEOUT_SECS)
        except (OSError, subprocess.SubprocessError) as exc:
            return f"git failed: {exc}"
        if res.returncode != 0:
            return f"git error: {(res.stderr or res.stdout).strip()}"
        out = res.stdout.strip()
        if len(out) > MAX_CHARS:
            return (out[:MAX_CHARS]
                    + f"\n\n[truncated at {MAX_CHARS} characters — narrow the "
                      f"request with a path or a smaller range to see the rest]")
        return out or "(no output — nothing matched)"

    # ── read-only operations (always available) ─────────────────────────

    def log(self, path: str = "", since: str = "", limit: int = 20) -> str:
        """List commits, newest first, with the files each one touched.

        Args:
            path: Limit to commits that touched this path (a file or a folder).
                Empty means everything this tool can read.
            since: A commit to start after, exclusive — you get everything from
                just after it up to HEAD. Empty means all history.
            limit: Maximum number of commits to return.

        Returns:
            One block per commit: short sha, date, subject, then its file paths.

        Example:
            git.log(path="clients/sarah-mitchell", since="aa70555")
        """
        args = ["log", f"-{max(1, limit)}", "--format=%h %ad %s",
                "--date=short", "--name-only"]
        if since:
            args.append(f"{since}..HEAD")
        spec = self._pathspec(path)
        if isinstance(spec, str):
            return spec
        return self._run(*args, *spec)

    def show(self, commit: str, path: str = "") -> str:
        """Show what a commit did, or what a file contained at that commit.

        Args:
            commit: A short or full sha, or a ref like HEAD.
            path: With a path, returns that file's full content as of this
                commit — how to see a document's earlier version. Empty returns
                the commit's message and a summary of the files it changed.

        Returns:
            File content, or the commit's metadata and change summary.

        Example:
            git.show("aa70555", path="clients/sarah-mitchell/ai/profile.ai")
        """
        if not commit:
            return "git error: a commit is required"
        spec = self._pathspec(path)
        if isinstance(spec, str):
            return spec
        if path:
            return self._run("show", f"{commit}:{path}")
        return self._run("show", "--stat", "--format=fuller", commit, *spec)

    def diff(self, since: str, until: str = "HEAD", path: str = "") -> str:
        """Show the actual line-by-line changes between two commits.

        Use this to see *what* a change said, once log has told you where it
        happened — the text a note gained, the figure a document now carries.

        Args:
            since: The earlier commit.
            until: The later commit. Defaults to HEAD.
            path: Limit the diff to this file or folder. Strongly recommended:
                a repo-wide diff is mostly noise. Binary files (PDFs) report as
                changed without content — read those with the pdf tools.

        Returns:
            A unified diff.

        Example:
            git.diff("aa70555", path="clients/sarah-mitchell/ai/profile.ai")
        """
        if not since:
            return "git error: a starting commit is required"
        spec = self._pathspec(path)
        if isinstance(spec, str):
            return spec
        return self._run("diff", since, until or "HEAD", *spec)

    # ── merge operations (only in mode="rw") ────────────────────────────

    def status(self) -> str:
        """Show working-tree status, highlighting conflicted files.

        Returns the output of ``git status`` — conflicted files are marked
        with ``UU`` (both modified).  Use this first to see what needs
        resolving.
        """
        return self._run("status")

    def show_stage(self, stage: int, path: str) -> str:
        """Read one version of a conflicted file from git's index.

        Args:
            stage: 1 = common ancestor (base), 2 = our version (HEAD),
                   3 = their version (the incoming branch).
            path: The conflicted file, repo-relative.

        Returns:
            The full file content at that stage.

        Example:
            git.show_stage(2, path="clients/smith/income/paystub.md")
        """
        if stage not in (1, 2, 3):
            return "git error: stage must be 1 (base), 2 (ours), or 3 (theirs)"
        return self._run("show", f":{stage}:{path}")

    def add(self, path: str) -> str:
        """Stage a resolved file so the rebase can continue.

        Call this AFTER writing the merged content back to disk — it tells
        git the conflict is resolved for this file.

        Args:
            path: The resolved file, repo-relative.

        Returns:
            Empty on success, or an error.
        """
        if not path:
            return "git error: a path is required"
        return self._run("add", path)

    def rebase_continue(self) -> str:
        """Continue the rebase after all conflicts are resolved.

        Call this once — after every conflicted file has been resolved and
        staged with ``add``.  If more conflicts appear in later commits the
        rebase will stop again; call ``status`` to check.

        Returns:
            Empty on success, or an error (e.g. unstaged files remain).
        """
        return self._run("rebase", "--continue")

    def rebase_abort(self) -> str:
        """Abort the rebase entirely and return to the pre-rebase state.

        Use this only as a last resort when conflicts cannot be resolved.
        All in-progress work is discarded and the branch returns to where
        it was before the rebase started.

        Returns:
            Empty on success, or an error.
        """
        return self._run("rebase", "--abort")
