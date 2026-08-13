"""im — the IM gateway agent that auto-replies to messages from all platforms.

What it is
----------
A background agent that sits alongside clerk and mem in the agent_service
process.  It reads unread messages from every configured IM platform via a
linc ``Client``, waits for a debounce window so a burst of short messages folds
into one batch, then feeds the batch to a full QAAgent (same brain the web chat
uses) and sends the reply back through the same linc Client.

It deliberately does NOT implement the Agent interface in base.py: like clerk
and mem, it is a batch job — no user turns, no streaming to a websocket, no
message history of its own beyond what QAAgent holds in memory.

How it talks to linc
--------------------
The gateway (WebSocket connections to IM platforms) runs in the app.py process
under ``connector_service``.  This agent runs in agent_service and opens a linc
``Client`` against the same SQLite data directory.  WAL mode makes the two
processes safe concurrent readers/writers; the Client holds ``client.lock``
(exclusive flock) so it is the sole *reader* of unread messages — app.py never
calls ``pull()`` / ``claim_unread()``.

Debounce
--------
People type in bursts on IM: three short messages arrive over five seconds,
then silence.  Responding to each one individually would produce three
replies that don't see the full question.  The debounce window (default 15s)
starts on the first message and resets on each subsequent message; only when
the conversation goes quiet for the full window does the batch fire.

Attachments
-----------
linc adapters download attachments to ``.linc/attachments/``.  QAAgent's tools
(FileSystem, Pdf, Reader) are scoped to the work repo, so they cannot read
files under ``.linc/``.  This agent copies each attachment into
``<repo>/.tmp/im/<platform>/<conv_id>/`` before running QA, then passes the
repo-relative paths as ``files`` to ``QAAgent.run()`` — exactly the same path
the web chat uses for user-attached files.  The copies are never cleaned up;
``.tmp/`` is gitignored.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from chak import MessageChunk

from .qa import QAAgent

log = logging.getLogger(__name__)

# Poll interval for client.pull().  Same cadence as the old app.py loop.
POLL_SECS = 2.0
# How long the conversation must be quiet before a batch fires.
DEBOUNCE_SECS = 15.0
# Hard cap on a single QAAgent turn.  Same scale as clerk's 600s: a LO may
# ask the IM agent to update files, which means reading client.yaml, notes,
# profile.ai, possibly PDFs — the same multi-tool pipeline clerk runs.
PASS_TIMEOUT_SECS = 600
# Fallback when the model returns nothing usable.
_EMPTY_REPLY = "I wasn't able to process that — please try again."


@dataclass
class _ConvState:
    """Per-conversation buffer: messages waiting for the debounce window."""
    messages: list = field(default_factory=list)
    last_ts: float = 0.0


# QAAgent instances cached across batches so the model remembers prior turns
# within the same process lifetime.  Key = (platform, conv_id).
_conv_agents: dict[tuple[str, str], QAAgent] = {}


def _default_ref() -> str | None:
    """First configured provider/model — same logic as clerk/mem."""
    from model_settings import _load as load_models_yaml
    try:
        providers = load_models_yaml().get("llm") or {}
    except Exception:  # noqa: BLE001
        return None
    for provider, entry in providers.items():
        if not isinstance(entry, dict) or not entry.get("api_key"):
            continue
        models = entry.get("models") or []
        if models:
            return f"{provider}/{models[0]}"
    return None


def _tmp_dir(root: Path, platform: str, conv_id: str) -> Path:
    """Where attachments are copied so QAAgent's tools can read them."""
    d = root / ".tmp" / "im" / platform / conv_id
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _linc_history_to_chak(client, platform: str, conv_id: str,
                                limit: int = 50) -> list[dict]:
    """Convert linc history into chak Conversation.load() dicts.

    Returns simple {role, content} pairs — enough for the model to see prior
    turns.  Tool-call details are lost, but that is acceptable: the purpose is
    conversational continuity, not perfect replay.
    """
    from linc.core.models import InboundMessage, OutboundMessage

    try:
        msgs = await client.history(platform=platform, conv_id=conv_id, limit=limit)
    except Exception:  # noqa: BLE001
        log.warning("im: history load failed for %s/%s", platform, conv_id, exc_info=True)
        return []

    history: list[dict] = []
    for msg in sorted(msgs, key=lambda m: m.ts):
        text = (msg.content.text or "").strip() if msg.content else ""
        if not text:
            continue
        if isinstance(msg, InboundMessage):
            history.append({"role": "user", "content": text})
        elif isinstance(msg, OutboundMessage) and msg.status in ("sent", "pending"):
            history.append({"role": "assistant", "content": text})
    return history


async def _create_agent(root: Path, model_uri: str, api_key: str,
                        client, platform: str, conv_id: str) -> QAAgent:
    """Build a QAAgent for one IM conversation, seeding it with prior history."""
    from agents.subagents import build_subagents

    history = await _linc_history_to_chak(client, platform, conv_id)
    sub_agents = build_subagents(model_uri=model_uri, api_key=api_key, root=root)
    return QAAgent(
        model_uri, api_key,
        workdir=root,
        conv_id=f"im:{platform}:{conv_id}",
        history=history or None,
        extra_tools=sub_agents,
    )


async def _process_batch(client, key: tuple[str, str], state: _ConvState,
                         root: Path, resolve_model) -> None:
    """Run one batch of messages through QAAgent and send the reply back."""
    platform, conv_id = key

    # --- Collect and copy attachments into .tmp/im/<plat>/<conv>/ ---
    files: list[str] = []
    tmp = _tmp_dir(root, platform, conv_id)
    for msg in state.messages:
        for att in (msg.content.attachments or []):
            src = getattr(att, "path", None)
            if src and Path(src).is_file():
                dst = tmp / Path(src).name
                try:
                    shutil.copy2(src, dst)
                    files.append(str(dst.relative_to(root)))
                except OSError:
                    log.warning("im: failed to copy attachment %s", src, exc_info=True)

    # --- Merge text ---
    texts = []
    for msg in state.messages:
        t = (msg.content.text or "").strip() if msg.content else ""
        if t:
            texts.append(t)
    if not texts and not files:
        return  # nothing to say
    text = "\n".join(texts) if texts else "Please review the attached file(s)."

    # --- Get or create the QAAgent ---
    agent = _conv_agents.get(key)
    if agent is None:
        ref = _default_ref()
        if not ref:
            log.warning("im: no model configured — skipping %s/%s", platform, conv_id)
            return
        uri, api_key = resolve_model(ref)
        agent = await _create_agent(root, uri, api_key, client, platform, conv_id)
        _conv_agents[key] = agent

    # --- Run QA (non-streaming consumption) ---
    reply = ""
    try:
        async def _run():
            nonlocal reply
            async for ev in agent.run(text, files=files):
                if isinstance(ev, MessageChunk) and ev.is_final and ev.final_message:
                    reply = str(ev.final_message.content or "")

        await asyncio.wait_for(_run(), timeout=PASS_TIMEOUT_SECS)
    except asyncio.TimeoutError:
        log.warning("im: QA timed out for %s/%s after %ds",
                    platform, conv_id, PASS_TIMEOUT_SECS)
        reply = "I'm still working on that — could you repeat your question?"
    except Exception:  # noqa: BLE001
        log.exception("im: QA failed for %s/%s", platform, conv_id)
        return

    if not reply.strip():
        reply = _EMPTY_REPLY

    # --- Send reply back to IM ---
    try:
        await client.send(reply, platform=platform, conv_id=conv_id)
        log.info("im: replied to %s/%s (%d chars, %d files)",
                 platform, conv_id, len(reply), len(files))
    except Exception:  # noqa: BLE001
        log.exception("im: send failed for %s/%s", platform, conv_id)


async def run_forever(
    resolve_model: Callable[[str], tuple[str, str]],
    poll_secs: float = POLL_SECS,
    debounce_secs: float = DEBOUNCE_SECS,
) -> None:
    """Main loop — lives for as long as the agent_service process does.

    Wakes every ``poll_secs``, pulls unread messages across all platforms,
    buffers them per (platform, conv_id), and fires batches whose debounce
    window has elapsed.  If linc is not installed or no connectors are
    configured, the loop sleeps quietly — never crashes the process.
    """
    from connector_service import LINC_DATA_DIR
    from workrepo import RepoError, local_repo_path

    log.info("im: started — poll every %.0fs, debounce %.0fs", poll_secs, debounce_secs)

    while True:
        await asyncio.sleep(poll_secs)

        # --- Preconditions ---
        try:
            root = local_repo_path()
        except RepoError:
            continue

        ref = _default_ref()
        if not ref:
            continue  # no model — nothing to do

        if not LINC_DATA_DIR.exists():
            continue  # gateway has never run

        # --- Open a Client and run the poll-process cycle ---
        try:
            from linc import Client
        except ImportError:
            log.warning("im: linc not installed — staying idle")
            return

        pending: dict[tuple[str, str], _ConvState] = {}

        try:
            async with Client(LINC_DATA_DIR) as client:
                while True:
                    await asyncio.sleep(poll_secs)

                    # Pull new messages (claim — exclusive ownership)
                    try:
                        unread = await client.pull()
                    except Exception:  # noqa: BLE001
                        log.warning("im: pull failed", exc_info=True)
                        unread = []

                    now = time.time()
                    for msg in unread:
                        if getattr(msg.sender, "is_bot", False):
                            continue
                        has_text = bool((msg.content.text or "").strip()
                                        if msg.content else "")
                        has_att = bool(msg.content.attachments) if msg.content else False
                        if not has_text and not has_att:
                            continue
                        k = (msg.platform, msg.conv_id)
                        st = pending.setdefault(k, _ConvState())
                        st.messages.append(msg)
                        st.last_ts = now

                    # Fire batches whose quiet window has elapsed
                    ready = [k for k, v in pending.items()
                             if now - v.last_ts >= debounce_secs]
                    for k in ready:
                        st = pending.pop(k)
                        try:
                            await _process_batch(client, k, st, root, resolve_model)
                        except asyncio.CancelledError:
                            raise
                        except Exception:  # noqa: BLE001
                            log.exception("im: batch failed for %s/%s", *k)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            # Client lock contention, data dir removed mid-run, etc.  Back off
            # and retry on the next outer-loop iteration.
            log.warning("im: Client cycle failed, will retry", exc_info=True)
