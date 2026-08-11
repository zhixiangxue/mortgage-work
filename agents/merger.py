"""merger — LLM-powered git rebase conflict resolver.

What it is
----------
An on-demand agent with one job: resolve git rebase conflicts intelligently.
When two machines edit the same files and the sync engine hits a conflict, the
merger is summoned.  It reads the conflicted files, understands what each side
changed, and produces a merged version that keeps all meaningful content —
preferring the current machine's values when both sides touched the same line.

It is NOT a long-running service.  It is a function: ``merge(root)``, called
by the sync engine only when a rebase fails, and it returns success/failure so
the engine knows whether to push or fall back to force-push.

Why LLM
-------
A simple "ours" or "theirs" strategy throws away one side's data.  An LLM can
read both versions of a mortgage document (client.yaml, profile.ai, notes)
and produce a merge that preserves field values, structural additions, and
context — the kind of merge a human LO would do if they knew git.

Safety
------
The agent holds two tools: ``git`` (log/show/diff + status/show_stage/add/
rebase_continue/rebase_abort) and ``filesystem`` (read/write).  It cannot run
arbitrary shell commands, cannot touch files outside the work repo, and cannot
commit — git write is limited to staging resolved files and continuing the
rebase the sync engine started.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ── System prompt ────────────────────────────────────────────────────────────

MERGE_PROMPT = """\
You are resolving git rebase conflicts in a mortgage loan officer's workspace.

## First step — ALWAYS start here
Run `git-status`.  If it shows NO conflicted files (no "UU", "DD", "AU",
"UD", "DU", "AA" markers), reply "No conflicts to resolve." and STOP.
Do NOT explore the repository, list files, or read history.

## Context (only when conflicts exist)
- Cloud-drive sync: two machines may edit files independently.
- Documents are plain text: .yaml configs, .md notes, .ai agent profiles.
- OURS (current machine) is authoritative for data VALUES.
- THEIRS (remote) may carry structural improvements or new content — keep those.

## Steps (only when git-status shows conflicts)
1. For every conflicted file:
   a. Read the three versions with `git-show_stage`:
      - stage 1 = common ancestor (BASE)
      - stage 2 = our version (OURS / HEAD)
      - stage 3 = their version (THEIRS / incoming)
   b. Produce a single merged file — synthesize, don't concatenate.
   c. Write the merged content with `filesystem-write_file`.
   d. Stage with `git-add`.
   e. Run `git-status` again to confirm the file is no longer conflicted.
2. When all files are resolved, run `git-rebase_continue`.
   - If it succeeds but new conflicts appear → repeat from step 1.
   - If it FAILS:
     * Read the error — "nothing to commit" means re-check status and re-add.
     * For other errors, check `git-status` for missed conflicted files.
     * Retry once.  If it still fails, run `git-rebase_abort` and report failure.

## Non-UU conflicts
`git-status` may also show these states:
- "DD", "DU", "UD" (delete/modify):
  If OURS deleted it → accept deletion.  If THEIRS deleted it but OURS
  modified it → keep OURS (data is more valuable than a deletion).
- "AA", "AU", "UA" (add/add or rename):
  Keep OURS content, accept THEIRS rename/path when applicable.

## Merge rules
- Preserve ALL content from both sides — never drop information.
- When both sides touched the same field, prefer OURS for VALUES,
  keep THEIRS for structural additions (new sections, new fields, reordering).
- Never invent data — only combine what already exists.
- If a conflict is irreconcilable, keep OURS and add a comment:
  `# MERGE NOTE: dropped THEIRS value in favor of OURS. Review advised.`
- Do NOT create new files.  Only resolve files already listed by `git-status`.
- Do NOT attempt to merge binary files — skip them and report.

## When you are done
Reply with a short summary: which files you resolved, any irreconcilable
conflicts that need human review, and any files you could not resolve."""

# ── Model resolution ─────────────────────────────────────────────────────────


def _resolve_model(model_ref: str | None = None) -> tuple[str, str]:
    """``"openai/gpt-4o"`` → ``(chak_uri, api_key)``.

    When *model_ref* is None, the first configured model is used — the merger
    is a background task; it doesn't need the user's currently-selected model,
    just any working LLM.
    """
    import model_settings

    data = model_settings._load()
    llm = data.get("llm", {})
    if not llm:
        raise ValueError("no LLM configured — add a provider in Settings")

    if model_ref and "/" in model_ref:
        provider, model = model_ref.split("/", 1)
    else:
        # Pick the first available
        provider, config = next(iter(llm.items()))
        if not isinstance(config, dict):
            raise ValueError(f"invalid config for provider: {provider}")
        models = config.get("models", [])
        if not models:
            raise ValueError(f"no models listed for provider: {provider}")
        model = models[0]

    entry = llm.get(provider, {})
    if not isinstance(entry, dict) or not entry.get("api_key"):
        raise ValueError(f"provider not configured: {provider}")
    base_url = str(entry.get("base_url", "")).strip()
    uri = f"{provider}@{base_url or '~'}:{model}"
    return uri, str(entry["api_key"])


# ── Async core ───────────────────────────────────────────────────────────────

async def _merge(root: Path, uri: str, key: str) -> dict:
    """Give the LLM git+filesystem tools and let it resolve every conflict."""
    import chak
    from chak.tools.std import FileSystem
    from .tools import Git

    # ── Tools ────────────────────────────────────────────────────────────
    git = Git(root, mode="rw")
    fs = FileSystem(workdir=str(root))

    conv = chak.Conversation(uri, api_key=key, tools=[git, fs])
    conv.tool.loop.max(40)

    try:
        response = await conv.asend(MERGE_PROMPT, timeout=300)
        content = getattr(response, "content", "") or ""
    except Exception as exc:
        log.warning("🐙 merger LLM call failed · %s", exc)
        return {"ok": False, "error": f"LLM call failed: {exc}"}

    # The LLM resolved conflicts inline via its tools; if rebase --continue
    # succeeded there's nothing more to do here.  The caller checks the repo
    # state.
    log.info("🐙 merger resolved rebase conflict")
    return {"ok": True, "summary": content.strip()[:500]}


# ── Sync entry point (called from workrepo.py's worker thread) ───────────────

def merge(root: str | Path,
          model_ref: str | None = None) -> dict:
    """Resolve git rebase conflicts in *root* with an LLM.

    Called by the sync engine when ``git pull --rebase`` leaves conflicted
    files.  The LLM reads every conflicted file, merges both sides, and
    continues the rebase.

    Parameters
    ----------
    root:
        The work-repo checkout directory.
    model_ref:
        ``"openai/gpt-4o"`` or None to use the first configured model.

    Returns
    -------
    ``{"ok": True, "summary": "..."}`` on success,
    ``{"ok": False, "error": "..."}`` on failure (caller falls back to
    force-push).
    """
    root = Path(root).resolve()
    if not root.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}

    try:
        uri, key = _resolve_model(model_ref)
    except Exception as exc:
        log.warning("🐙 merger model resolution failed · %s", exc)
        return {"ok": False, "error": f"model resolution failed: {exc}"}

    return asyncio.run(_merge(root, uri, key))
