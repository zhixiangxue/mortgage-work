"""organizer — LLM-powered file organizer for client root directories.

What it is
----------
An on-demand agent with one job: move loose files in a client's root directory
into the appropriate subdirectories.  It hands the LLM ``FileSystem`` and
``Bash`` tools; the model autonomously lists files, classifies them by name,
creates directories, and moves everything into place — one tool call at a time.

Why LLM, not regex
------------------
A regex cannot tell whether ``tax-2025.pdf`` belongs in ``income/`` or a
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

# Standard cluster directories — the agent knows about these and can create
# any that are missing.  Custom directories the LO already created are ALSO
# valid targets — the agent discovers them via list_dir / tree.
STANDARD_DIRS: list[str] = [
    "identity", "income", "assets", "credit", "property", "notes", "ai",
]

ORGANIZER_PROMPT = """\
You are organizing a mortgage loan client folder.

## Standard categories
- identity/ — driver license, passport, COE/DD-214, business license,
  residency verification, occupancy affidavits
- income/ — W-2, paystubs, 1099, tax returns, VOE, CPA letters,
  pension / Social Security / disability, rental / lease income
- assets/ — bank statements, brokerage statements, IRA/401k,
  gift letters, donor documents
- credit/ — credit reports
- property/ — purchase contracts, appraisals, deeds, disclosures,
  mortgage statements, Schedule E
- notes/ — intake forms, interview notes, LO working notes
- ai/ — AI-generated content, profile files

## Steps
1. **List** the directory with `tree` or `list_dir` so you can see every
   file and subdirectory.
2. **Classify** each loose file (files NOT inside a subdirectory).
   - The filename is the primary signal.
   - Existing custom directories (beyond the 7 standards) are LO choices —
     prefer them when they are more specific than a standard directory.
     Example: put tax forms in `tax-returns/` if it exists, not `income/`.
   - Skip system files: client.yaml, PROFILE.md, README.md.
3. **Create** any standard directories that do not exist yet (use `bash`
   with `mkdir`, one directory per command).
4. **Move** each file with the `filesystem-move` tool.
   Destination format: `target_directory/filename`.
5. **Summarize** the result in one short sentence: how many files moved
   into which directories.

## Rules
- All paths are relative to the root directory — do NOT include the
  folder name itself in paths.
- Never delete files — only move them.
- Never touch files already inside a subdirectory.
- Never suggest creating new custom directories.
"""


def _resolve_model(model_ref: str) -> tuple[str, str]:
    """``"openai/gpt-4o"`` → ``(chak_uri, api_key)``."""
    if not model_ref or "/" not in model_ref:
        raise ValueError("no model selected — pick one in the chat panel")
    provider, model = model_ref.split("/", 1)
    import model_settings
    data = model_settings._load()
    entry = data.get("llm", {}).get(provider, {})
    if not isinstance(entry, dict) or not entry.get("api_key"):
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
