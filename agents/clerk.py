"""clerk — the background scribe behind each client's ``ai/profile.ai``.

What it is
----------
An agent with one goal and a repository to explore, not a workflow. It is handed
a client and a list of commits it has not seen, and it decides for itself what to
read: the folder, the PDFs inside it, a program guideline under ``products/``, the
earlier version of a note. What comes back is one document.

It deliberately does *not* implement the ``Agent`` interface in base.py: there is
no user turn, nothing streams, no message history is kept. Reusing that shape
would only bend it out of purpose.

How it knows there is work
--------------------------
Git history is the only signal. Each ``profile.ai`` carries its own watermark in
the header (``as of <sha>``), so "is this client stale?" is one ``git log`` away,
per client — no shared cursor to corrupt, nothing lost when the machine changes,
and a client whose pass failed retries on its own without stalling the others.

The pathspec does two jobs at once::

    git log <as-of>..HEAD -- clients/<slug> ':(exclude)clients/<slug>/ai'

The first path scopes history to one client. Attribution comes from the files a
commit actually touched, never from what its message claims — so a repo-wide
commit (the seed, a pull, someone's commit from the shell) still lands on every
client it affected, even with no ``scope:`` line to read.

The exclusion is the loop breaker: clerk's own output lives under ``ai/``, so a
commit that only touched ``ai/`` falls out of clerk's own query. That single
pathspec replaces message parsing, "was this me?" bookkeeping and cascade depth
limits — the loop cannot form in the first place.

What is code and what is not
----------------------------
The model reads whatever it judges relevant; nothing here pre-digests files for
it. Two things stay in code, and only two:

*The watermark*, because deciding whether to spend a call at all cannot depend on
making one.

*The write*, because every tool clerk holds is read-only and this module puts the
result at the one path clerk owns — this client's ``ai/profile.ai``. That is what
makes repo-wide reading safe: browsing another borrower's folder cannot corrupt
this one's file when there is no way to write to it.

Why it never commits
--------------------
Writing the file is where clerk stops. Committing is the app process's job, whose
watcher picks the change up like any other outside write. Two processes running
git against one checkout would fight over ``index.lock`` for nothing, so the
checkout keeps exactly one writer.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import yaml
from rich.console import Console
from rich.markup import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from model_settings import _load as load_models_yaml  # noqa: E402
from tools import FileSystem, Git, Pdf, Reader  # noqa: E402
from workrepo import RepoError, _git, local_repo_path  # noqa: E402

# Ten minutes of silence is also the batching window: a burst of saves from one
# work session folds into a single pass per client instead of one pass per save.
TICK_SECS = 600
# The app clones/pulls on boot; sweeping before that finishes just wastes a pass.
FIRST_SWEEP_DELAY_SECS = 30
# Reading a folder's documents is many small tool calls — PDFs page by page, a
# diff, a guideline. Generous, because the alternative is a truncated document.
PASS_TIMEOUT_SECS = 420
MAX_TOOL_ITERATIONS = 40

_AS_OF_RE = re.compile(r"as of ([0-9a-f]{7,40})")

PROFILE_REL = "ai/profile.ai"

# ── Heartbeat log ──
# Every sweep says it woke, what it decided per client, and when it went back
# to sleep — a silent clerk and a dead clerk used to be indistinguishable from
# the terminal, and that cost a debugging session.
# soft_wrap: these are log lines — when stdout is a pipe (app.py owns the
# real terminal) rich would otherwise hard-wrap at a guessed 80 columns.
_console = Console(highlight=False, soft_wrap=True)


def _log(msg: str) -> None:
    """One clerk line: dim timestamp + magenta tag, message carries its own
    markup. Dynamic text (errors, model output) must arrive escape()d."""
    _console.print(f"[dim]{datetime.now():%H:%M:%S}[/dim] "
                   f"[bold magenta]clerk[/bold magenta] {msg}")

CLERK_PROMPT = """You are clerk, the scribe on a loan officer's desktop workbench.

You keep one client's `ai/profile.ai` current. The officer's assistant answers questions from that document instead of reopening the folder, so what you write is what it knows — a fact you leave out is a question it gets wrong, and a figure you guess is one it will repeat with confidence.

Working from: {root}
This client: {folder}
Loan programs and their guidelines live in products/.

Your tools are read-only, and what they open is this client's folder and products/ — the client's own documents, and the guidelines a program is judged against. Use git to find out what actually changed — the commit list says where to look, `show` gives you a file as it was, `diff` gives you the words that moved. Read the PDFs; the figures that matter are usually inside them, and a document you only list by filename tells the assistant nothing. For anything that is neither text nor PDF — a Word letter, an Excel rent roll, a photo of a paystub, a zip — `reader-read` turns it into Markdown; images come back transcribed by a vision model, so a photographed W-2 is figures, not a filename.

Check a PDF's `metadata` before you read it whole. A borrower's paystub is a page or two, but a lender's selling guide runs to over a thousand — on those, `search` and `read_pages` get you the clause you need, where `read_all` would spend your whole context on the 1,180 pages you didn't want. The PDF tools open documents in this client's folder and in products/; those are the two places a document can bear on this file. Address them the way everything else here is addressed — relative to the repository, as git reports them.

What the document has to get right:

- **Facts, each with the file it came from.** The officer's own thinking — which program they are leaning toward, what they suspect — is theirs, not a fact about the borrower. Cite the file you actually read: if a note claims a figure from a PDF, prefer opening the PDF, and if you cannot, make clear the claim is what you have.
- **Absence, stated.** When nothing on disk answers a field, write `unknown — <why>` instead of dropping the line or filling it with the likeliest value. The assistant has to be able to answer "the file doesn't say", and `unknown` is the only way it learns that.
- **Nothing lost.** You are updating a document, not composing a new one. Carry forward what still holds; a fact that quietly disappears in a rewrite is worse than a stale one, because nobody notices.

Shape — keep these sections in this order, one fact per line, each line ending in its own source, plus a date when the fact can go out of date.

A source is a path. Add ` @ <sha>` to it only for a fact you read *through git* — `show` or `diff` at a named commit — because there the sha is the version you actually looked at. A file you opened with the filesystem or PDF tools is the working copy, and the working copy runs ahead of the last commit: the officer's saves land on disk seconds before they are committed, so a sha pinned to one of those points at a version that may not contain what you just read. For those, the path alone.

## Loan
purpose, loan amount, stage, location, occupancy, target program

## Borrowers
one line per person: name · role · citizenship · employment type

## Income
qualifying income, front-end DTI, back-end DTI, what the income evidence consists of

## Credit
FICO, and when it was pulled

## Property
type, purchase price, appraisal status. Purchase price is what the home sells for and lives in a contract — a different fact from the loan amount, which is what is borrowed against it.

## Documents on file
one line per folder, naming the files in it

## Open items
what is missing or owed

## Context
Facts from natural language — call transcripts, notes, emails — that no field above can hold: intentions, promises, explanations, circumstances. A borrower saying "that deposit was from selling my car" belongs here, and so does a promise made three weeks ago that never landed. Date every entry: this kind of fact expires, and the reader can only tell if you say when.

Output the document body only, starting at `## Loan` — no preamble, no code fence, no title, and no `as of` line; the header is written for you."""


def _header(name: str, sha: str) -> str:
    """The watermark line is written here, not by the model — a hallucinated sha
    would quietly break every later sweep."""
    return (f"# {name} — clerk\n\n"
            f"> Maintained by clerk · as of {sha} · {date.today():%Y-%m-%d}\n"
            f"> Verifiable facts with sources; this is the single source of truth "
            f"for client knowledge.\n\n")


def _active_clients(root: Path) -> list[tuple[str, str]]:
    """(slug, display name) for every client still worth thinking about."""
    out = []
    for folder in sorted((root / "clients").iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        meta = {}
        try:
            meta = yaml.safe_load(
                (folder / "client.yaml").read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            pass        # unreadable metadata is no reason to ignore the folder
        if meta.get("stage") == "closed":
            continue    # a closed file has stopped earning its keep
        out.append((folder.name, str(meta.get("name") or folder.name)))
    return out


def _watermark(path: Path) -> str | None:
    """The sha this profile was last brought up to date with, if it exists."""
    try:
        found = _AS_OF_RE.search(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return found.group(1) if found else None


def _head(root: Path) -> str:
    res = _git(["rev-parse", "--short", "HEAD"], cwd=root)
    return res.stdout.strip() if res.returncode == 0 else ""


def _pending(root: Path, slug: str, as_of: str | None) -> str:
    """The commits this client has not been read for yet, with their files.

    This is the whole reason a pass runs, so it is worth one git call up front —
    the model then has somewhere to start and can drill in with its own tools.
    """
    rng = [f"{as_of}..HEAD"] if as_of else []
    res = _git(["log", *rng, "--format=%h %ad %s", "--date=short", "--name-only",
                "--", f"clients/{slug}", f":(exclude)clients/{slug}/ai"], cwd=root)
    if res.returncode != 0:
        # A watermark can stop resolving: history rewritten, a fresh shallow
        # clone, a hand-edited header. Re-read everything rather than sit idle.
        if as_of:
            _log(f"[yellow]{slug}: watermark {as_of} unusable, reading full history[/yellow]")
            return _pending(root, slug, None)
        return ""
    return res.stdout


def _default_ref() -> str | None:
    """First configured provider/model. clerk has no picker of its own, and a
    background job that demanded its own setting would just sit idle until
    somebody noticed it was configured wrong."""
    try:
        providers = load_models_yaml().get("providers") or {}
    except Exception:  # noqa: BLE001 — a broken settings file is not clerk's problem
        return None
    for provider, entry in providers.items():
        if not isinstance(entry, dict) or not entry.get("api_key"):
            continue
        models = entry.get("models") or []
        if models:
            return f"{provider}/{models[0]}"
    return None


def _body(text: str) -> str:
    """The document, out of whatever the model wrapped around it.

    Models narrate before they start ("Let me assemble the profile...") and fence
    the result even when told not to. Both are cosmetic, and throwing away a good
    document — plus the call that produced it — over a preamble is not.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].lstrip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    cut = text.find("## Loan")
    return text[cut:].strip() if cut > 0 else text


def _turn(slug: str, name: str, as_of: str | None, changes: str) -> str:
    if as_of:
        state = (f"The document already covers everything up to {as_of}. "
                 f"Read it at clients/{slug}/{PROFILE_REL} before you start — "
                 f"what it holds is what the assistant currently believes.\n\n"
                 f"New since then:")
    else:
        state = ("No profile exists yet. This is the first pass, so the whole "
                 "document is yours to write.\n\nThe history so far:")
    return (f"Client: {name} — clients/{slug}/\n\n"
            f"{state}\n\n{changes.strip() or '(nothing in the log — work from what is on disk)'}\n\n"
            "Look into whatever of this matters, then output the updated document body.")


async def _run_pass(root: Path, slug: str, name: str, as_of: str | None,
                    changes: str, uri: str, key: str) -> str:
    """One client's digest. Returns the document body the model produced."""
    # Imported per pass, not at module load: the agent service must still start
    # when the LLM stack is missing, and an idle clerk shouldn't pay for it.
    import chak

    # The two folders a pass is actually about: this client's, and products/ for
    # the guideline that says whether their numbers qualify. Another borrower's
    # paystub answers no question asked here, and all three tools are held to the
    # same pair — a file tool confined while history stays open is not confined.
    #
    # Every tool is read-only. The one file clerk writes is written below, by us.
    folders = (root / "clients" / slug, root / "products")

    conv = chak.Conversation(
        uri, api_key=key,
        system_prompt=CLERK_PROMPT.format(root=root, folder=f"clients/{slug}/"),
        tools=[FileSystem(*folders, base=root, mode="r"), Pdf(*folders, base=root),
               Reader(*folders, base=root, vision=uri, vision_api_key=key),
               Git(root, *folders)],
    )
    conv.tool.loop.max(MAX_TOOL_ITERATIONS)
    resp = await conv.asend(_turn(slug, name, as_of, changes),
                            timeout=PASS_TIMEOUT_SECS)
    return _body((getattr(resp, "content", "") or "").strip())


async def tick(resolve_model: Callable[[str], tuple[str, str]],
               only: str | None = None) -> int:
    """One sweep over the active clients. Returns how many were rewritten.

    `only` narrows the sweep to a single slug — what the assistant will use to
    settle one client on demand when a question arrives before the next tick.
    """
    try:
        root = local_repo_path()
    except RepoError:
        _log("[yellow]awake — no repo configured, back to sleep[/yellow]")
        return 0
    if not (root / "clients").is_dir():
        _log("[yellow]awake — nothing cloned yet, back to sleep[/yellow]")
        return 0            # nothing cloned yet
    ref = _default_ref()
    if not ref:
        _log("[yellow]awake — no model configured, back to sleep[/yellow]")
        return 0            # no model configured — stay quiet, this is background work
    head = _head(root)
    if not head:
        _log("[yellow]awake — repo has no HEAD yet, back to sleep[/yellow]")
        return 0

    clients = [(s, n) for s, n in _active_clients(root) if not only or s == only]
    _log(f"awake — sweeping [bold]{len(clients)}[/bold] active client(s) "
         f"at HEAD [cyan]{head}[/cyan] with [cyan]{escape(ref)}[/cyan]")

    done = 0
    for slug, name in clients:
        profile_path = root / "clients" / slug / PROFILE_REL
        as_of = _watermark(profile_path)
        if as_of == head:
            _log(f"  [dim]{escape(slug)} — up to date (as of {as_of})[/dim]")
            continue        # nothing at all has happened since the last sweep
        changes = _pending(root, slug, as_of)
        # HEAD moved but nothing here did: another client's commit, or clerk's
        # own write to ai/. Bumping the watermark would be a pointless commit.
        if as_of and not changes.strip():
            _log(f"  [dim]{escape(slug)} — no commits touched it since {as_of}[/dim]")
            continue
        n_commits = sum(1 for l in changes.splitlines()
                        if re.match(r"^[0-9a-f]{7,40} ", l))
        _log(f"  [bold]{escape(slug)}[/bold] — "
             + (f"{n_commits} new commit(s) since {as_of}" if as_of
                else f"no profile yet, first pass ({n_commits} commit(s) of history)")
             + " → running…")
        started = time.monotonic()
        try:
            uri, key = resolve_model(ref)
            body = await _run_pass(root, slug, name, as_of, changes, uri, key)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — one bad client must not end the sweep
            # The watermark stays put, so this client is retried next tick.
            _log(f"  [red]{escape(slug)} — pass failed after "
                 f"{time.monotonic() - started:.0f}s: "
                 f"{type(exc).__name__}: {escape(str(exc))}[/red]")
            continue
        if not body.startswith("## Loan"):
            # No document in there at all — a refusal, an apology, an error
            # relayed as prose. Writing it would replace a good profile with
            # text the assistant then goes on to trust. Leaving the watermark
            # alone means the next tick tries this client again.
            _log(f"  [red]{escape(slug)} — unusable response, skipped: "
                 f"{escape(body[:160])!r}[/red]")
            continue
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profile_path.write_text(_header(name, head) + body.rstrip() + "\n",
                                    encoding="utf-8")
        except OSError as exc:
            _log(f"  [red]{escape(slug)} — write failed: {escape(str(exc))}[/red]")
            continue
        _log(f"  [green]{escape(slug)} — profile.ai updated → as of {head} "
             f"({time.monotonic() - started:.0f}s)[/green]")
        done += 1
    return done


async def run_forever(resolve_model: Callable[[str], tuple[str, str]],
                      interval: int = TICK_SECS) -> None:
    """The tick, and the only scheduler clerk has."""
    _log(f"🖋️ started — first sweep in {FIRST_SWEEP_DELAY_SECS}s, "
         f"then every {interval // 60} min")
    await asyncio.sleep(FIRST_SWEEP_DELAY_SECS)
    while True:
        started = time.monotonic()
        try:
            n = await tick(resolve_model)
            _log(f"sweep done in {time.monotonic() - started:.0f}s — "
                 + (f"[green]{n} client(s) rewritten[/green]" if n
                    else "nothing to do")
                 + f", next in {interval // 60} min")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the loop outlives any single failure
            _log(f"[red]sweep failed: {type(exc).__name__}: {escape(str(exc))}[/red]")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    # One sweep now:  uv run python -m agents.clerk [slug]
    # The prompt is what needs iterating, and neither waiting out a tick nor
    # rewriting every client to inspect one makes that bearable.
    from agent_service import resolve_model  # local: avoids an import cycle

    _only = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"[clerk] {asyncio.run(tick(resolve_model, only=_only))} client(s) rewritten")
