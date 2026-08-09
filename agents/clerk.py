"""clerk — the background orchestrator behind each client's ``ai/profile.ai``.

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
from .tools import FileSystem, Git, Mem, Pdf, Reader  # noqa: E402
from workrepo import RepoError, _git, local_repo_path  # noqa: E402

# Idle poll interval: how often clerk wakes to check whether any client's
# watermark lags HEAD.  The check is git-only (zero tokens), so a short
# interval gives low latency without cost.
IDLE_POLL_SECS = 60
# Settle window: once changes are detected, clerk waits this long before
# starting a pass — a burst of saves from one work session folds into a
# single pass instead of one pass per save.  New commits during the window
# reset the timer, so an actively-editing LO never triggers a mid-session pass.
SETTLE_SECS = 120
# The app clones/pulls on boot; sweeping before that finishes just wastes a pass.
FIRST_SWEEP_DELAY_SECS = 30
# Reading a folder's documents is many small tool calls — PDFs page by page, a
# diff, a guideline. Generous, because the alternative is a truncated document.
# With sub-agents running serially (each ~60-90s), a full orchestration pass
# takes longer than the old single-conversation pass.
PASS_TIMEOUT_SECS = 600
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

CLERK_PROMPT = """You are clerk, the orchestrator behind each client's `ai/profile.ai`.

You keep one document current by directing specialist tools to do the reading and calculation, then synthesizing their results into one file. Not all specialists may be available — if a tool is missing, work with what you have and note the gap in the profile.

Working from: {root}
This client: {folder}
Loan programs and their guidelines live in products/.

## Your tools

Your tools fall into three groups:

1. **Sub-agent experts** (`income-analyzer`, `credit-analyzer`, `asset-analyzer`, `eligibility-analyzer`) — each reads documents inside its own context and returns a concise summary. Pass them absolute file paths and enough loan context to do their job. Their internal work never enters your context window — that is the whole point.

2. **Calculation tools** (`payment-calculator`, `dti-calculator`, `ltv-cltv`, `doc-checklist`) — deterministic scripts. Pass numbers in, get numbers out.

3. **Direct tools** (`filesystem`, `pdf`, `reader`, `git`) — use these yourself for things the experts don't cover: reading `client.yaml`, reading notes, listing files, checking git history.

Not all tools may be present — a skill that is not installed or not enabled produces no tool. Work with what you have.

## Determining program direction

Before using `eligibility-analyzer` or `doc-checklist`, determine the target program(s). Four levels of certainty:

1. **Explicit**: the intake note or `client.yaml` states the target program.
2. **Strong inference**: no explicit statement, but the document types strongly indicate a path (e.g. lease + market rent analysis, no W-2 → DSCR; bank statements instead of W-2 → Non-QM Bank Statement).
3. **Weak inference**: some hints but ambiguous.
4. **Unknown**: too little to infer.

State your confidence level and evidence in the profile. When uncertain, use base-level `doc-checklist` only and note what's needed to narrow down.

## Source citations

Every fact in the profile must end with its source, so a downstream tool (like the QA agent) can trace any conclusion back to its origin file without re-reading everything. Use this format:

- Facts from documents on disk: `— <repo-relative-path>`
  Example: `FICO 708 — credit/credit-report.pdf`
- Facts from a calculation tool: `— calc:<tool-name>`
  Example: `Back-end DTI 36.7% — calc:dti-calculator`
- Facts from a sub-agent's analysis: `— analyst:<sub-agent-name>`
  Example: `Qualifying income $12,417/mo — analyst:income-analyzer`
- Facts from a guideline PDF: `— <products-relative-path>`
  Example: `Min DSCR 1.25 — products/itrust/DSCR 10.22.24.pdf`
- Facts from natural language (notes, emails): `— <path> (<date>)`
  Example: `Borrower prefers bank statement route — notes/intake-call-0801.txt (2026-08-01)`
- Facts from conversation memory: `— conversation:{{conv_id}}`
  Example: `Loan amount corrected to $750K — conversation:c-20260731-2100`
- Facts inferred but not directly stated: mark with `(inferred)` after the source
  Example: `Program: Non-QM Bank Statement (inferred) — notes/intake-call-0801.txt`

## Workflow

1. Read `client.yaml` and `notes/` to understand the client and determine the program direction (4-level model).
1b. Check conversation signals (provided in the turn context) for corrections, decisions, or new information about this client that may not be on disk yet.
2. Read the existing `ai/profile.ai` (if updating) to see what the assistant currently believes — carry forward what still holds.
3. Use `git` to find out what actually changed since the last pass.
4. Delegate to the appropriate sub-agent experts — pass them absolute file paths and loan context.
5. Run calc tools for deterministic numbers (DTI, LTV, payment, doc checklist).
6. Synthesize everything into the profile document.

## Working memory — Scratchpad

Your context window is finite. When reading PDFs and long files, old tool results may be pruned. To avoid losing facts before you write the document:
- After receiving a sub-agent summary or reading a document, save key findings to your scratchpad immediately — concise section names like "income_summary", "credit_scores", "eligibility_result".
- Store distilled facts with their source, not raw text.
- Before writing the final document, check `scratchpad-list_sections` to recall everything you gathered.

## Document shape

Keep these sections in this order. Output the document body only, starting at `## Needs attention` — no preamble, no code fence, no title, and no `as of` line; the header is written for you.

## Needs attention
One-line items that block or risk the file, ordered by severity. Each item should say what's wrong and what's needed. If nothing needs attention, write "None".

## Status snapshot
Stage, program fit + confidence level (Explicit / Strong inference / Weak inference / Unknown), submission readiness summary (e.g. "3 items block submission, 2 to verify").

## Open items
### Blocks submission
Items that prevent loan submission — from `eligibility-analyzer` blockers and `doc-checklist` required gaps.
### Required before close
Standard purchase/close requirements not yet met.
### To verify
Items flagged by sub-agents as caveats or notes.

## Document checklist
A checklist showing what's collected vs. what's still needed. Use `[x]` for on-file, `[ ]` for missing. Group by category. Generate from `doc-checklist` output cross-referenced with actual files on disk.

Example:
### Identity
- [x] Driver license — identity/driver-license.pdf
- [ ] SSN verification — not yet received
### Income
- [x] CPA letter — income/cpa-letter.pdf
- [ ] 2-year business tax returns — not yet received

## Program compliance
Table per target product: `requirement | required | actual | margin | status`. Generated from `eligibility-analyzer` output. One row per requirement.

## The file
### Loan
Purpose, loan amount, stage, location, occupancy, target program. Facts from `client.yaml`.

### Borrowers
One line per person: name · role · citizenship · employment type.

### Income
Qualifying income summary from `income-analyzer` + the calculation chain. Each figure cited with its source.

### Credit
Summary from `credit-analyzer`. FICO, key tradelines, red flags.

### Assets
Summary from `asset-analyzer` + verdict (sufficient/insufficient with gap).

### Ratios
Output from `dti-calculator`, `ltv-cltv`, and `payment-calculator`. Front-end DTI, back-end DTI, LTV, CLTV, PITIA, monthly payment.

### Property
Type, purchase price, appraisal status. Purchase price is what the home sells for — a different fact from the loan amount.

### Documents on file
One line per folder, naming the files in it.

### Context
Facts from natural language — call transcripts, notes, emails — that no field above can hold: intentions, promises, explanations, circumstances. Date every entry: this kind of fact expires, and the reader can only tell if you say when.

## Rules

- **Facts, each with the file it came from.** The officer's own thinking — which program they are leaning toward, what they suspect — is theirs, not a fact about the borrower. Cite the file you actually read.
- **Absence, stated.** When nothing on disk answers a field, write `unknown — <why>` instead of dropping the line or filling it with the likeliest value.
- **Nothing lost.** You are updating a document, not composing a new one. Carry forward what still holds; a fact that quietly disappears in a rewrite is worse than a stale one, because nobody notices.

Output the document body only, starting at `## Needs attention`."""


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
        providers = load_models_yaml().get("llm") or {}
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
    cut = text.find("## Needs attention")
    return text[cut:].strip() if cut > 0 else text


def _turn(slug: str, name: str, as_of: str | None, changes: str,
          memories: list[dict] | None = None) -> str:
    if as_of:
        state = (f"The document already covers everything up to {as_of}. "
                 f"Read it at clients/{slug}/{PROFILE_REL} before you start — "
                 f"what it holds is what the assistant currently believes.\n\n"
                 f"New since then:")
    else:
        state = ("No profile exists yet. This is the first pass, so the whole "
                 "document is yours to write.\n\nThe history so far:")
    prompt = (f"Client: {name} — clients/{slug}/\n\n"
              f"{state}\n\n{changes.strip() or '(nothing in the log — work from what is on disk)'}")
    # Conversation signals — extracted from the LO's chat history by the memory
    # agent (mem). These may contain corrections, decisions, or new information
    # that is not yet on disk. They are supplementary, not authoritative.
    if memories:
        lines = [f"- {m['content']}" for m in memories]
        prompt += ("\n\n## Conversation signals (from memory agent)\n"
                   "These were extracted from the LO's chat history. "
                   "Use them as supplementary context — they may contain "
                   "corrections, decisions, or new information not yet on disk.\n"
                   + "\n".join(lines))
    prompt += "\n\nLook into whatever of this matters, then output the updated document body."
    return prompt


async def _run_pass(root: Path, slug: str, name: str, as_of: str | None,
                    changes: str, uri: str, key: str,
                    resolve_model: Callable[[str], tuple[str, str]] | None = None
                    ) -> str:
    """One client's digest. Returns the document body the model produced."""
    # Imported per pass, not at module load: the agent service must still start
    # when the LLM stack is missing, and an idle clerk shouldn't pay for it.
    import chak
    from chak.tools.std import Scratchpad
    from .context import ContractContextHandler
    from . import mem as mem_agent
    from .subagents import build_subagents

    # Pull conversation-derived memories relevant to this client. Best-effort:
    # a None mem (no model configured, repo not cloned) returns [] — clerk
    # still has the client's files to work from.
    memories = await mem_agent.recall(
        f"{name} loan profile corrections decisions preferences",
        resolve_model=resolve_model,
    )

    # The two folders a pass is actually about: this client's, and products/ for
    # the guideline that says whether their numbers qualify. Another borrower's
    # paystub answers no question asked here, and all three tools are held to the
    # same pair — a file tool confined while history stays open is not confined.
    #
    # Every tool is read-only. The one file clerk writes is written below, by us.
    folders = (root / "clients" / slug, root / "products")

    # Per-pass scratchpad in a temp dir: clerk's context is throwaway once the
    # profile is written, so the JSON need not survive past this pass.
    import tempfile
    scratch_path = Path(tempfile.mkdtemp(prefix="mw-clerk-")) / "scratchpad.json"
    scratchpad = Scratchpad(path=str(scratch_path), mode="rw")

    # Base tools — clerk uses these for flexible work: reading client.yaml,
    # notes, listing directories, reading a specific PDF page.
    base_tools = [FileSystem(*folders, base=root, mode="r"),
                  Pdf(*folders, base=root),
                  Reader(*folders, base=root, vision=uri, vision_api_key=key),
                  Git(root, *folders), Mem(), scratchpad]

    # Sub-agent tools — domain experts, each with its own Conversation.
    # Only created for skills that are installed AND enabled.
    sub_agents = build_subagents(model_uri=uri, api_key=key, root=root)

    tools = base_tools + sub_agents

    conv = chak.Conversation(
        uri, api_key=key,
        system_prompt=CLERK_PROMPT.format(root=root, folder=f"clients/{slug}/"),
        context_handler=ContractContextHandler(stub_threshold_tokens=2000),
        tools=tools,
    )
    conv.tool.loop.max(MAX_TOOL_ITERATIONS)
    resp = await conv.asend(_turn(slug, name, as_of, changes, memories=memories),
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
            body = await _run_pass(root, slug, name, as_of, changes, uri, key,
                                   resolve_model=resolve_model)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — one bad client must not end the sweep
            # The watermark stays put, so this client is retried next tick.
            _log(f"  [red]{escape(slug)} — pass failed after "
                 f"{time.monotonic() - started:.0f}s: "
                 f"{type(exc).__name__}: {escape(str(exc))}[/red]")
            continue
        if not body.startswith("## Needs attention"):
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


def _any_client_stale(root: Path, head: str) -> bool:
    """True if any active client's watermark lags HEAD and has real changes.

    The cheap probe that decides whether to arm the settle window — git-only,
    zero tokens.  Mirrors the skip logic in ``tick`` so the two never disagree
    about whether there is work to do.
    """
    for slug, _ in _active_clients(root):
        as_of = _watermark(root / "clients" / slug / PROFILE_REL)
        if as_of == head:
            continue
        changes = _pending(root, slug, as_of)
        if changes.strip():
            return True
    return False


async def run_forever(resolve_model: Callable[[str], tuple[str, str]],
                      idle_poll_secs: int = IDLE_POLL_SECS,
                      settle_secs: int = SETTLE_SECS) -> None:
    """Adaptive poll-and-settle loop — the only scheduler clerk has.

    Two phases:

    * **Idle** — wake every ``idle_poll_secs`` and check whether any client's
      watermark lags HEAD (git-only, zero tokens).  Nothing to do → back to
      sleep, so a short poll costs nothing.

    * **Settle** — the moment work is detected, arm a ``settle_secs`` cooldown
      that lets a burst of saves fold into one pass.  New commits during the
      window reset the timer, so an LO who keeps editing never triggers a
      mid-session pass.  When the window expires, run one full sweep and
      return to idle.
    """
    _log(f"🖋️ started — first sweep in {FIRST_SWEEP_DELAY_SECS}s, "
         f"poll every {idle_poll_secs}s, settle {settle_secs}s")
    await asyncio.sleep(FIRST_SWEEP_DELAY_SECS)

    settle_until: float | None = None   # None = idle; a monotonic deadline = settling
    settle_head: str | None = None      # HEAD captured when settle began

    while True:
        if settle_until is None:
            await asyncio.sleep(idle_poll_secs)
        else:
            # Inside the settle window: sleep just long enough to hit the
            # deadline, capped by the poll interval so a reset lands on time.
            remaining = settle_until - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(min(remaining, idle_poll_secs))

        # ── Probe (cheap, 0 tokens) ──
        try:
            root = local_repo_path()
        except RepoError:
            continue
        if not (root / "clients").is_dir():
            continue
        head = _head(root)
        if not head:
            continue

        if settle_until is None:
            # Idle: is anyone stale?
            if _any_client_stale(root, head):
                settle_until = time.monotonic() + settle_secs
                settle_head = head
                _log(f"changes detected at [cyan]{head}[/cyan] — "
                     f"settling for {settle_secs}s")
        elif time.monotonic() >= settle_until:
            # Settle window expired — run the pass now.
            started = time.monotonic()
            try:
                n = await tick(resolve_model)
                _log(f"sweep done in {time.monotonic() - started:.0f}s — "
                     + (f"[green]{n} client(s) rewritten[/green]" if n
                        else "nothing to do")
                     + f", next poll in {idle_poll_secs}s")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — the loop outlives any single failure
                _log(f"[red]sweep failed: {type(exc).__name__}: "
                     f"{escape(str(exc))}[/red]")
            settle_until = None
            settle_head = None
        elif head != settle_head:
            # New commits landed during the settle window — the LO is still
            # working, so push the deadline out for another full window.
            settle_until = time.monotonic() + settle_secs
            settle_head = head
            _log(f"new commits during settle — extending by {settle_secs}s")


if __name__ == "__main__":
    # One sweep now:  uv run python -m agents.clerk [slug]
    # The prompt is what needs iterating, and neither waiting out a tick nor
    # rewriting every client to inspect one makes that bearable.
    #
    # Direct mode:   uv run python -m agents.clerk --direct <slug>
    # Bypasses git/watermark entirely — hands _run_pass an empty change set so
    # clerk reads everything from disk. Prints the document to stdout and also
    # writes it to the client's ai/profile.ai, so you see the real result.

    import yaml as _yaml

    args = sys.argv[1:]
    _direct = "--direct" in args
    if _direct:
        args.remove("--direct")
    _only = args[0] if args else None

    from agent_service import resolve_model  # local: avoids an import cycle

    if _direct and _only:
        # Direct mode: skip tick(), call _run_pass with empty changes.
        root = local_repo_path()
        client_dir = root / "clients" / _only
        if not client_dir.is_dir():
            print(f"[clerk] no such client: {_only}")
            sys.exit(1)
        meta = _yaml.safe_load(
            (client_dir / "client.yaml").read_text(encoding="utf-8")) or {}
        name = str(meta.get("name") or _only)

        ref = _default_ref()
        if not ref:
            print("[clerk] no model configured")
            sys.exit(1)
        uri, key = resolve_model(ref)

        # Empty changes → _turn() says "nothing in the log — work from what is
        # on disk", which is exactly what we want: clerk reads everything.
        changes = ""
        print(f"[clerk] direct pass on {_only} ({name}) with {ref}…")
        started = time.monotonic()
        body = asyncio.run(_run_pass(root, _only, name, None, changes, uri, key,
                                     resolve_model=resolve_model))
        elapsed = time.monotonic() - started

        if not body.startswith("## Needs attention"):
            print(f"[clerk] unusable response ({elapsed:.0f}s):")
            print(body[:500])
            sys.exit(1)

        # Write to the client's ai/profile.ai (same as tick does).
        head = _head(root) or "direct"
        profile_path = client_dir / PROFILE_REL
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(_header(name, head) + body.rstrip() + "\n",
                                encoding="utf-8")
        print(f"[clerk] profile.ai written ({elapsed:.0f}s, as of {head})")
        print(f"[clerk] {profile_path}")
    else:
        print(f"[clerk] {asyncio.run(tick(resolve_model, only=_only))} client(s) rewritten")
