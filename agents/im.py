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

Client targeting
----------------
Unlike the web chat, an IM batch has no UI context saying which client the
LO is looking at.  Before each QA run the batch text is matched against the
client folders (slug parts plus ``client.yaml`` names); one unambiguous match
is prepended as a ``client_hint`` carrying the folder's actual subdirectory
listing plus the reuse-first principle — the agent picks the landing spot,
no directory name is assumed here — otherwise a generic hint lists every
client folder.  Together with the write landing policy in tools/filesystem.py
this keeps IM-driven updates out of the repo root and out of client-folder
roots.
"""
from __future__ import annotations

import asyncio
import logging
import re
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
    """First configured provider/model — shared settings.llm.llm_target()."""
    from settings.llm import llm_target
    try:
        return llm_target()
    except Exception:  # noqa: BLE001
        return None


def _tmp_dir(root: Path, platform: str, conv_id: str) -> Path:
    """Where attachments are copied so QAAgent's tools can read them."""
    d = root / ".tmp" / "im" / platform / conv_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _client_hint(root: Path, text: str) -> str:
    """Resolve which client a batch mentions and build a targeting hint.

    IM messages carry no UI context — unlike the web chat, which prepends the
    client the LO is currently viewing.  So the batch text is matched against
    the client folders deterministically: slug parts and the ``name:`` line in
    each client.yaml.  One unambiguous match yields a targeted hint carrying
    FACTS, not rules: the folder's actual subdirectory listing goes into the
    context and the agent decides where the content lands — reuse what the LO
    already created, create something new only if nothing fits.  Naming
    conventions vary per client (notes/ vs 6-notes/), so no directory name is
    ever assumed here.  Anything else yields a generic hint listing every
    client folder, so the model never has to guess the layout or invent a
    path.
    """
    clients_dir = root / "clients"
    if not clients_dir.is_dir():
        return ""

    haystack = text.lower()
    scored: list[tuple[int, str]] = []
    for d in sorted(clients_dir.iterdir()):
        if not d.is_dir():
            continue
        slug = d.name
        tokens = {t for t in slug.lower().split("-") if len(t) >= 3}
        try:
            raw = (d / "client.yaml").read_text(encoding="utf-8")
        except OSError:
            raw = ""
        m = re.search(r"^name:\s*(.+)$", raw, re.MULTILINE)
        if m:
            tokens |= {t.lower() for t in m.group(1).split() if len(t) >= 2}
        score = sum(1 for t in tokens if t in haystack)
        if score:
            scored.append((score, slug))

    if len(scored) == 1:
        slug = scored[0][1]
        today = time.strftime("%Y-%m-%d")
        folder = clients_dir / slug
        try:
            subs = sorted(d.name for d in folder.iterdir() if d.is_dir())
        except OSError:
            subs = []
        listing = ", ".join(f"{s}/" for s in subs) or "none yet"
        return (
            f"[Context hint: this message updates client \"{slug}\" "
            f"(folder clients/{slug}/). Subdirectories the loan officer "
            f"already has there: {listing}. Save any new or updated file for "
            f"this client INSIDE that folder — prefer reusing the existing "
            f"subdirectory that fits the content type; create a new one only "
            f"if none of them fits. The folder root holds client.yaml and "
            f"README.md only. Suggested note filename: {today}-<topic>.md. "
            f"Only after the write actually succeeded, state the saved path "
            f"in your reply; if it failed or you did not write, say so "
            f"honestly. If the message is about a different client, ignore "
            f"this hint.]"
        )

    slugs = [d.name for d in sorted(clients_dir.iterdir()) if d.is_dir()]
    listing = ", ".join(f"clients/{s}/" for s in slugs) or "none"
    return (
        f"[Context hint: client folders available: {listing}. If this message "
        f"updates a client's information, save files under the matching "
        f"client folder — list that folder first and prefer reusing the "
        f"existing subdirectory that fits the content type; create a new one "
        f"only if none fits. Never save at the repo root or directly in the "
        f"client folder root. Only after the write actually succeeded, state "
        f"the saved path in your reply; if it failed or you did not write, "
        f"say so honestly. If you cannot determine which client is meant, "
        f"ask in your reply.]"
    )


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
        hint = _client_hint(root, text)

        async def _run():
            nonlocal reply
            async for ev in agent.run(text, files=files, client_hint=hint):
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
