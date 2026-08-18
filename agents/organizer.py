"""organizer — LLM-powered file organizer for client root directories.

What it is
----------
An on-demand agent with one job: move loose files in a client's root directory
into the appropriate subdirectories.  It hands the LLM ``FileSystem`` and
``Bash`` tools; the model autonomously lists files, classifies them by semantic
category, and moves them into existing directories — matching the user's
chosen organizational structure instead of imposing its own.

Why LLM, not regex
------------------
A regex cannot tell whether ``tax-2025.pdf`` belongs in ``2-income/`` or a
custom ``tax-returns/`` directory the LO created — a model with ``list_dir``
can see existing directories and treat their names as intentional signals.

Token economy
-------------
The LLM sees and classifies every file itself, so token cost scales with
file count.  In practice the prompt is ~500 tokens and each list/move call
adds ~100–200 tokens of context — lightweight enough for 20–40 file folders.

Safety
------
``FileSystem.move`` is ``shutil.move`` under the hood — atomic within the
same filesystem, safe across devices.  The ``Bash`` tool has deny-patterns
for ``rm -rf`` and friends.  The prompt explicitly says "never delete files."
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

# Files the agent must never touch, even if they sit loose at the root
EXCLUDE_NAMES: set[str] = {"client.yaml", "PROFILE.md", "README.md"}

ORGANIZER_PROMPT = """\
You are organizing a mortgage loan client folder.

## What goes where (semantic categories — NOT directory names)
These categories describe what each kind of document IS.  Use them to match
files to the directory that fits best, regardless of the directory's name.

- Identity & occupancy: driver license, passport, COE/DD-214, business
  license, residency verification, occupancy affidavits
- Income & employment: W-2, paystubs, 1099, tax returns, VOE, CPA letters,
  pension / Social Security / disability, rental / lease income
- Assets & funds: bank statements, brokerage statements, IRA/401k,
  gift letters, donor documents
- Credit & liabilities: credit reports, liabilities
- Property & title: purchase contracts, appraisals, deeds, disclosures,
  mortgage statements, Schedule E
- Notes & intake: intake forms, interview notes, LO working notes
- AI: AI-generated content, profile files

## Steps
1. **List** the directory with `tree` or `list_dir` and study EVERY
   existing subdirectory.  These directories are the user's intentional
   organization — your job is to fit files INTO them, not to replace them.
2. **Classify** each loose file (files NOT already inside a subdirectory):
   - Match the file to the EXISTING directory whose semantic category fits
     best.  The filename is the primary signal; file contents are secondary.
   - If multiple existing directories could fit, pick the most specific one.
   - If a file truly fits NO existing directory, you may create ONE new
     directory for it — but only as a last resort, and only if the file
     cannot reasonably go anywhere else.
   - Skip system files: client.yaml, PROFILE.md, README.md.
3. **Move** each file with the `filesystem-move` tool.
   Destination format: `target_directory/filename`.
4. **Summarize** the result in one short sentence: how many files moved
   into which directories.

## Rules
- All paths are relative to the root directory — do NOT include the
  folder name itself in paths.
- Never delete files — only move them.
- Never touch files already inside a subdirectory.
- NEVER create a directory that duplicates an existing directory's purpose.
  If `1-identity/` already holds identity documents, do NOT create
  `identity/` — move files into `1-identity/` instead.
- The user's existing directory names ARE correct.  Do not rename, replace,
  or supplement them with "standard" alternatives.
"""


def _resolve_model(model_ref: str) -> tuple[str, str]:
    """``"openai/gpt-4o"`` → ``(chak_uri, api_key)``."""
    if not model_ref or "/" not in model_ref:
        raise ValueError("no model selected — pick one in the chat panel")
    provider, model = model_ref.split("/", 1)
    from settings.llm import llm_entry
    entry = llm_entry(provider)
    if entry is None or not entry.get("api_key"):
        raise ValueError(f"provider not configured: {provider}")
    base_url = str(entry.get("base_url", "")).strip()
    uri = f"{provider}@{base_url or '~'}:{model}"
    return uri, str(entry["api_key"])


async def _organize(root: Path, uri: str, key: str,
                    on_progress: Callable | None = None,
                    queue_sync_fn: Callable | None = None,
                    ) -> dict:
    """Async core: give LLM tools, stream events, track progress."""
    import chak
    from chak.tools.std import FileSystem, Bash
    from chak.message import (ToolCallStartEvent, ToolCallSuccessEvent,
                               ToolCallErrorEvent)

    # ── Tools ──────────────────────────────────────────────────────────
    fs = FileSystem(workdir=str(root))
    bash = Bash(timeout=30, working_dir=str(root))

    prompt = ORGANIZER_PROMPT

    conv = chak.Conversation(uri, api_key=key, tools=[fs, bash])
    conv.tool.loop.max(60)

    moved: list[dict] = []
    errors: list[dict] = []
    clusters: set[str] = set()
    _pending: list[tuple[str, str]] = []  # FIFO queue for batched move calls

    if on_progress:
        on_progress("classifying", "scanning...", "")

    try:
        async for event in await conv.asend(prompt, event=True):
            if isinstance(event, ToolCallStartEvent):
                name = event.tool_name or ""
                args = event.arguments or {}

                if "move" in name:
                    src = args.get("src", "")
                    dst = args.get("dst", "")
                    fname = Path(src).name if src else ""
                    tdir = ""
                    if dst:
                        dp = Path(dst)
                        tdir = dp.parent.name if dp.parent != Path(".") else ""
                    if fname and tdir:
                        _pending.append((fname, tdir))
                        if on_progress:
                            on_progress("moving", fname, tdir)

                elif name == "bash":
                    cmd = args.get("command", "")[:80]
                    if on_progress:
                        on_progress("classifying", cmd, "")

            elif isinstance(event, ToolCallSuccessEvent):
                if _pending and "move" in (event.tool_name or ""):
                    fname, tdir = _pending.pop(0)
                    moved.append({"file": fname, "target": tdir})
                    clusters.add(tdir)
                    if on_progress:
                        on_progress("done", fname, tdir)
                    # Best-effort git sync
                    if queue_sync_fn:
                        try:
                            scope = root.name
                            rel = f"{fname} → {tdir}/{fname}"
                            queue_sync_fn(scope, rel, "move")
                        except Exception:
                            pass

            elif isinstance(event, ToolCallErrorEvent):
                if _pending and "move" in (event.tool_name or ""):
                    fname, tdir = _pending.pop(0)
                    err = str(getattr(event, "error", "") or "")
                    errors.append({"file": fname, "target": tdir, "error": err})
                    if on_progress:
                        on_progress("error", fname, tdir)

    except Exception as exc:
        return {"ok": False, "error": f"organizer failed: {exc}"}

    return {
        "ok": True,
        "moved": len(moved),
        "clusters": sorted(clusters),
        "errors": errors,
        "files": moved,
    }


def organize(root: Path,
             model_ref: str,
             on_progress: Callable[[str, str, str], None] | None = None,
             queue_sync_fn: Callable[[str, str, str], None] | None = None,
             ) -> dict:
    """Classify and move loose files in *root* into appropriate subdirectories.

    Parameters
    ----------
    root:
        The client folder (e.g. ``~/MortgageWork/clients/james-emily-whitfield``).
    model_ref:
        Model reference like ``"openai/gpt-4o"``.
    on_progress:
        Called as ``on_progress("classifying"|"moving"|"done"|"error", ...)``
        during the run.
    queue_sync_fn:
        Called after each successful move for git history.

    Returns
    -------
    ``{"ok": True, "moved": N, "clusters": [...], "errors": [...]}``
    """
    if not root.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}

    uri, key = _resolve_model(model_ref)

    return asyncio.run(_organize(root, uri, key,
                                 on_progress=on_progress,
                                 queue_sync_fn=queue_sync_fn))
