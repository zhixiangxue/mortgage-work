"""Read-only git history, as a tool.

Why read-only
-------------
The verbs a repo-management tool wants — clone, pull, checkout — are exactly the
ones an unattended agent must not have. This checkout is already managed by the
app's sync engine: a `checkout` would move HEAD under a running window, and a
`pull` would race the engine's own. History, on the other hand, is the one thing
an agent genuinely needs and cannot get anywhere else: a folder shows what is
true now, git shows what *changed*, which is the whole question when you are
catching up on work somebody else did.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


# Diffs and file dumps have no natural size. A seed commit or a rewritten
# document can run to megabytes, which buys nothing and costs a context window.
MAX_CHARS = 20_000
TIMEOUT_SECS = 30


class Git:
    """Read a git repository's history — commits, file changes, past versions."""

    name = "git"
    description = (
        "Read the work repository's history: which commits touched which files, "
        "what a commit changed, and what a file looked like at any point. "
        "Read-only — nothing here modifies the repository."
    )

    def __init__(self, repo: str | Path, *scope: str | Path):
        """Args: the checkout, then the folders history may be read for.

        Scope matters as much here as it does for a file tool. ``show`` prints
        any file at any revision and a bare ``log`` names every path in the
        repository, so history is a second way into the same documents — and
        confining the file tools while leaving this one open confines nothing.
        No scope means the whole repository.

        The first argument really is the repository here, unlike the ``base`` the
        file tools take: a pathspec is repo-relative by definition and git cannot
        read outside its own checkout, so scope inside the repo is git's
        constraint rather than this class's choice. Passing a folder from
        elsewhere raises, and should.
        """
        self._repo = Path(repo).resolve()
        # Kept repo-relative, which is the form a pathspec takes.
        self._scope = [Path(s).resolve().relative_to(self._repo).as_posix()
                       for s in scope]

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
                                 timeout=TIMEOUT_SECS)
        except (OSError, subprocess.SubprocessError) as exc:
            return f"git failed: {exc}"
        if res.returncode != 0:
            return f"git error: {(res.stderr or res.stdout).strip()}"
        out = res.stdout.strip()
        if len(out) > MAX_CHARS:
            # Say so explicitly — silently cut output reads like a complete
            # answer, and the model would conclude the rest does not exist.
            return (out[:MAX_CHARS]
                    + f"\n\n[truncated at {MAX_CHARS} characters — narrow the "
                      f"request with a path or a smaller range to see the rest]")
        return out or "(no output — nothing matched)"

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
            git.show("aa70555", path="clients/sarah-mitchell/PROFILE.md")
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
            git.diff("aa70555", path="clients/sarah-mitchell/PROFILE.md")
        """
        if not since:
            return "git error: a starting commit is required"
        spec = self._pathspec(path)
        if isinstance(spec, str):
            return spec
        return self._run("diff", since, until or "HEAD", *spec)
