"""mem — the memory agent behind conversation-derived knowledge.

What it is
----------
A background agent that sits between the chat layer and clerk, extracting
structured knowledge from LO ↔ QA conversations. It is the "论" (interpretation)
layer over the JSONL "账" (ledger): the raw transcript is the deterministic
record, and seeka Memos are the distilled intelligence clerk consumes.

Three-phase lifecycle (all inside seeka):
    note()   — raw conversation text, one per turn, written by the chat layer
    dream()  — LLM extraction + embedding + conflict resolution, on a tick
    recall() — semantic search, called by clerk before each pass

Storage lives inside the work-repo at ``<repo>/.seeka/`` so it is co-located
with the client data it is about. It is gitignored for now (device-local state,
like session.json), but the design is deliberate: un-ignore the directory and
memories sync across machines via git — a new laptop pulls the full history
without reprocessing a single conversation.

It deliberately does NOT implement the Agent interface in base.py: like clerk,
it is a batch job, not a conversation. No streaming, no message history, no
user turns. The only inputs are notes (from the chat layer) and the tick.

Browsing and editing memories is *not* here — that's the app's Memory tab,
which opens the same store directly (app.py). This module is the actor; a
viewer is not part of an actor's job. What the two sides share is only what
must not drift: ``SEEKA_DIR`` (workrepo.py) and ``embedding_target()``
(model_settings.py).

TODO — concurrent writers. The tick runs here, in the agent service; the Memory
tab's edits arrive in the app process, which holds its own handle to the same
``.seeka/``. seeka makes no cross-process guarantees today, so two writes
landing in the same instant could collide. Accepted for now: the tick is one
LLM call every two minutes and editing memories is a rare human action, so the
window is tiny. When seeka grows process-level locking we inherit it without
touching a line of this file.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from model_settings import _load as load_models_yaml  # noqa: E402
from model_settings import embedding_target, read_memory_config  # noqa: E402
from workrepo import SEEKA_DIR, RepoError, local_repo_path  # noqa: E402

log = logging.getLogger(__name__)

# ── Heartbeat log (mirrors clerk's pattern) ──
_console = Console(highlight=False, soft_wrap=True)

# Idle poll: conversations accumulate slower than file changes, and dream()
# is an LLM call — a longer interval avoids burning tokens on a single turn.
IDLE_POLL_SECS = 120


def _log(msg: str) -> None:
    """One mem line: dim timestamp + cyan tag, message carries its own markup."""
    _console.print(f"[dim]{datetime.now():%H:%M:%S}[/dim] "
                   f"[bold cyan]mem[/bold cyan] {msg}")


def _enabled() -> bool:
    """The Memory tab's switch. Off means "stop learning": no new notes, no
    dream. Reading what was already learned stays allowed — the LO should be
    able to look over the pile before deciding to throw it away."""
    try:
        return bool(read_memory_config().get("enabled"))
    except Exception:  # noqa: BLE001 — broken settings read as "off"
        return False


def _default_ref() -> str | None:
    """First configured provider/model — same pattern as clerk.

    mem does not get its own model picker; it reuses whatever the LO has
    already configured. A background job that demands its own setting would
    just sit idle until somebody noticed.
    """
    try:
        providers = load_models_yaml().get("providers") or {}
    except Exception:  # noqa: BLE001 — broken settings are not mem's problem
        return None
    for provider, entry in providers.items():
        if not isinstance(entry, dict) or not entry.get("api_key"):
            continue
        models = entry.get("models") or []
        if models:
            return f"{provider}/{models[0]}"
    return None


def _ensure_ignored(repo_root: Path) -> None:
    """Make sure ``.seeka/`` is in the work-repo's ``.gitignore``.

    Idempotent and side-effect-free: only writes when the line is missing.
    No git operations — the app's watcher/flush cycle picks up the .gitignore
    change like any other outside edit.
    """
    ignore = repo_root / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    if SEEKA_DIR + "/" in lines or f"/{SEEKA_DIR}/" in lines:
        return
    entry = f"\n# seeka memory — local state, ignored for now\n{SEEKA_DIR}/\n"
    with ignore.open("a", encoding="utf-8") as f:
        f.write(entry)


def get_memory(resolve_model: Callable[[str], tuple[str, str]] | None = None):
    """The agent's handle on the store, or None when it can't be opened.

    Not cached here: seeka keys instances by (path, namespace) and returns the
    live one, so calling this per turn costs a dict lookup. Keeping a second
    singleton alongside seeka's only created a way for the two to disagree —
    notably after forget(), which drops seeka's entry but couldn't drop ours.

    Returns None when there's no repo or no embedder configured. Every caller
    already treats that as "skip, try again next tick".
    """
    try:
        repo_root = local_repo_path()
    except RepoError:
        return None

    embedder = embedding_target()
    if embedder is None:
        return None
    embedding_uri, embedding_key = embedder

    seeka_path = repo_root / SEEKA_DIR
    first_run = not seeka_path.exists()
    if first_run:
        # Only the writer creates the store. Ordering matters: get the ignore
        # line down before seeka's makedirs, so the directory is never briefly
        # visible to the sync engine as untracked content.
        _ensure_ignored(repo_root)

    # The extraction model. Absent it, this handle can still store and recall,
    # just not dream — which is exactly the app process's situation.
    llm_uri, llm_key = None, None
    if resolve_model:
        ref = _default_ref()
        if ref:
            llm_uri, llm_key = resolve_model(ref)
        else:
            _log("[yellow]no model configured — notes will queue until one "
                 "is[/yellow]")

    from seeka import Memory
    from seeka.skills import GENERAL

    # Custom mortgage extraction skill — co-located with mem.py under
    # agents/skills/seeka/. GENERAL handles default extraction; the
    # mortgage skill narrows the focus to actionable LO signals.
    skill_path = str(Path(__file__).resolve().parent / "skills" / "seeka")

    mem = Memory(
        str(seeka_path),
        embedding_uri=embedding_uri,
        embedding_api_key=embedding_key,
        llm_uri=llm_uri,
        llm_api_key=llm_key,
        skills=[GENERAL, skill_path],
    )
    if first_run:
        _log(f"store created at {SEEKA_DIR}/ · embedder {embedding_uri}")
    return mem


# ── Public API ──────────────────────────────────────────────────────────────


async def note_turn(conv_id: str, user_text: str, assistant_text: str,
                    context: dict | None = None,
                    resolve_model: Callable[[str], tuple[str, str]] | None = None
                    ) -> None:
    """Called by the chat layer after each turn completes. Writes one note
    per turn — user text + assistant text joined as a conversation pair.

    Best-effort: a failed note never breaks the chat. The tool-call trace
    is not included (it's in the JSONL if ever needed).
    """
    if not _enabled():
        return
    try:
        mem = get_memory(resolve_model)
        if mem is None:
            return
        content = f"User: {user_text}\nAssistant: {assistant_text}"
        await mem.note(content, metadata={
            "conv_id": conv_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "context": context or {},
        })
    except Exception:
        log.warning("mem.note_turn failed", exc_info=True)


async def recall(query: str, n: int = 10,
                 resolve_model: Callable[[str], tuple[str, str]] | None = None
                 ) -> list[dict]:
    """Semantic search over stored memos. Returns plain dicts so callers
    (clerk, QA) don't need to import seeka's Memo type.

    Best-effort: a failed recall returns an empty list — clerk still has
    the client's files on disk to work from. Reading is allowed even with the
    switch off: what was already learned stays usable until it's deleted.
    """
    try:
        mem = get_memory(resolve_model)
        if mem is None:
            return []
        results = await mem.recall(query, n=n)
        return [{"content": r.content, "metadata": r.metadata} for r in results]
    except Exception:
        log.warning("mem.recall failed", exc_info=True)
        return []


async def run_forever(resolve_model: Callable[[str], tuple[str, str]],
                      idle_poll_secs: int = IDLE_POLL_SECS) -> None:
    """Independent tick — runs alongside clerk's loop in agent_service lifespan.

    Wakes every ``idle_poll_secs`` and fires ``dream(group_by="conv_id")``.
    seeka processes all pending notes: same-conv turns are concatenated into
    one LLM call, preserving full conversation context. The cadence is
    gentler than clerk's — conversations accumulate slower than file changes.
    """
    _log(f"started — poll every {idle_poll_secs}s")
    while True:
        await asyncio.sleep(idle_poll_secs)
        if not _enabled():
            continue
        try:
            mem = get_memory(resolve_model)
            if mem is None:
                continue
            started = time.monotonic()
            memos = await mem.dream(group_by="conv_id")
            if memos:
                _log(f"dream extracted {len(memos)} memo(s) "
                     f"in {time.monotonic() - started:.0f}s")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("mem dream failed", exc_info=True)
