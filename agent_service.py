"""Agent service — the chat backend, a local WebSocket server around chak.

Why a separate process
-----------------------
Same pattern as the browser/ viewers: app.py spawns this with the venv's
Python and the frontend talks to it directly over ws://127.0.0.1:<AGENT_PORT>.
That keeps chat working in the plain-browser dev mode (:5273, no pywebview
bridge) and keeps streaming/interruption out of the bridge's request-reply
model. API keys are read here from ~/MortgageWork/settings/models.yaml and
never cross the wire — the frontend only ever sends a "provider/model" ref.

Conversations
-------------
One chak ``Conversation`` per conv_id (chak's own mental model — no separate
thread concept). Persistence is one JSONL per conversation at
``<repo>/conversations/<conv_id>.jsonl``:

    {"type":"meta","id":...,"title":...,"created":...,"context":...,"model":...}
    {chak message dump}            # one line per message, appended per turn
    {"type":"meta", ...}           # meta may repeat; last meta wins

The file lands inside the work repo, so the existing watcher/sync engine
commits and pushes it like any other document — this service never writes git.
It only ever reads history (see clerk below); the checkout keeps one writer.

Background work
---------------
clerk (agents/clerk.py) rides along as a task on this process's lifespan: it
already has chak, the keys and the model resolver, and being off the UI process
means a sweep never competes with the window for the GIL. It writes files, never
commits — the app's watcher picks those up like any other outside edit.

Protocol (JSON over WS)
-----------------------
client → server:
    {type:"new",  context:{client?, view}}          → {type:"conv", meta, messages}
    {type:"open", conv_id}                          → {type:"conv", meta, messages}
    {type:"list"}                                   → {type:"convs", items}
    {type:"send", conv_id, model, text, pills:[{scope,path,name,dir}],
     quotes:[{text,scope,path}]}
    {type:"cancel", conv_id}
    {type:"delete", conv_id, turn_id}               → {type:"conv", meta, messages}

server → client (during a send):
    {type:"chunk", conv_id, content}
    {type:"tool_start"|"tool_end"|"tool_error", conv_id, ...}
    {type:"done", conv_id, message, meta}
    {type:"cancelled", conv_id, message}
    {type:"title", conv_id, title}      # late — LLM retitle after the 1st turn
    {type:"error", conv_id?, error}

The thinking happens in agents/ (SimpleAgent: persona + read-only FileSystem
and Pdf tools over the work repo). Attached pills travel as repo-relative
paths in the prompt — the agent reads them through its tools, no attachments.
The user's structured input (typed text + pills + quotes) is stamped onto the
turn's HumanMessage as custom.display, so the UI re-renders it as components
instead of showing the composed prompt.

Run standalone:  uv run python agent_service.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import socket
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from log import setup_logging  # noqa: E402
from config import SERVICES  # noqa: E402
from model_settings import SettingsError, _load as load_models_yaml  # noqa: E402
from workrepo import RepoError, local_repo_path  # noqa: E402

log = logging.getLogger(__name__)

from agents import SimpleAgent, clerk  # noqa: E402
import chak  # noqa: E402
from chak import MessageChunk  # noqa: E402
from chak.message import (ToolCallErrorEvent, ToolCallStartEvent,  # noqa: E402
                          ToolCallSuccessEvent)

# ── Conversation store (JSONL under <repo>/conversations/) ──────────────────

_CONV_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def conversations_dir() -> Path:
    root = local_repo_path()
    d = root / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _conv_path(conv_id: str) -> Path:
    # The id becomes a filename — reject anything that could escape the dir.
    if not _CONV_ID_RE.match(conv_id or ""):
        raise ValueError(f"bad conv_id: {conv_id!r}")
    return conversations_dir() / f"{conv_id}.jsonl"


def new_conv_id() -> str:
    return f"c-{datetime.now():%Y%m%d-%H%M}-{secrets.token_hex(2)}"


def read_conv(conv_id: str) -> tuple[dict | None, list[dict]]:
    """(last-meta-wins meta, message dumps) from one JSONL. Unparsable lines
    are skipped — a half-written trailing line must not kill the whole thread."""
    path = _conv_path(conv_id)
    if not path.exists():
        return None, []
    meta, messages = None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "meta":
            meta = obj
        else:
            messages.append(obj)
    return meta, messages


def append_lines(conv_id: str, objs: list[dict]) -> None:
    path = _conv_path(conv_id)
    with path.open("a", encoding="utf-8") as f:
        for obj in objs:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def rewrite_conv(conv_id: str, meta: dict, messages: list[dict]) -> None:
    """Deletion is the one thing the append-only JSONL can't express —
    rewrite the whole file (atomically: temp + replace, a crash mid-write
    must not eat the transcript)."""
    path = _conv_path(conv_id)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for obj in [meta, *messages]:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    tmp.replace(path)


def list_convs() -> list[dict]:
    items = []
    for path in conversations_dir().glob("*.jsonl"):
        meta, _ = read_conv(path.stem)
        if not meta:
            continue
        items.append({
            "id": meta.get("id", path.stem),
            "title": meta.get("title", path.stem),
            "context": meta.get("context") or {},
            "updated": int(path.stat().st_mtime),
        })
    items.sort(key=lambda x: x["updated"], reverse=True)
    return items


def make_title(context: dict, text: str) -> str:
    """Instant placeholder title — the first user message, truncated, client-
    prefixed. Shows the moment the turn lands; a background LLM retitle
    (see _retitle) replaces it seconds later when a model is reachable."""
    text = " ".join(text.split())
    if len(text) > 42:
        text = text[:42].rstrip() + "…"
    client = (context.get("client") or {}).get("name") if context else ""
    return f"{client} · {text}" if client else (text or "New Chat")


# ── LLM titling (fire-and-forget after the first turn) ─────────────────────

_TITLE_PROMPT = """Write a title for this conversation: 3–6 words, same language as the user's message, plain text — no quotes, no trailing punctuation, nothing but the title itself.

User: {question}

Assistant: {answer}"""

# Keep strong refs — asyncio only weak-refs its tasks, a titling call must not
# be garbage-collected mid-flight.
_retitle_tasks: set[asyncio.Task] = set()


def _clean_title(raw: str) -> str:
    """Models decorate: quotes, a 'Title:' echo, trailing periods. Strip all
    of it and cap the length — an empty result means 'keep the fallback'."""
    t = " ".join(str(raw or "").split())
    t = re.sub(r"^(?:title\s*[:：]\s*)", "", t, flags=re.I)
    t = t.strip("\"'“”‘’「」 。.！!？?")
    if len(t) > 42:
        t = t[:42].rstrip() + "…"
    return t


async def _retitle(ws: WebSocket, lc: LiveConv, question: str, answer: str,
                   model_ref: str) -> None:
    """One cheap, tool-free LLM call → a real title for the thread. Best-effort
    by design: any failure leaves the truncated fallback in place, and the
    conversation itself is long since persisted."""
    try:
        uri, key = resolve_model(model_ref)
        conv = chak.Conversation(uri, api_key=key)
        resp = await conv.asend(_TITLE_PROMPT.format(
            question=" ".join(question.split())[:600],
            answer=" ".join(answer.split())[:1200]), timeout=30)
        title = _clean_title(getattr(resp, "content", ""))
        if not title:
            return
        client = ((lc.meta.get("context") or {}).get("client") or {}).get("name")
        title = f"{client} · {title}" if client else title
        if title == lc.meta.get("title"):
            return
        lc.update_meta(title=title)
        await _send_json(ws, {"type": "title", "conv_id": lc.id, "title": title})
    except Exception as exc:  # noqa: BLE001 — a failed retitle is not an event
        log.warning("title %s: %s: %s", lc.id, type(exc).__name__, exc)


def _spawn_retitle(ws: WebSocket, lc: LiveConv, question: str, answer: str,
                   model_ref: str) -> None:
    task = asyncio.create_task(_retitle(ws, lc, question, answer, model_ref))
    _retitle_tasks.add(task)
    task.add_done_callback(_retitle_tasks.discard)


# ── Model resolution (models.yaml → chak URI, keys stay server-side) ────────

def resolve_model(ref: str) -> tuple[str, str]:
    """"provider/model" → (chak URI, api_key). Same yaml + URI form as
    model_settings.check_provider, so a picked model always resolves the way
    Check proved it does."""
    if not ref or "/" not in ref:
        raise SettingsError("no model selected — configure one in Settings")
    provider, model = ref.split("/", 1)
    entry = (load_models_yaml()["providers"].get(provider)) or {}
    if not isinstance(entry, dict) or not entry.get("api_key"):
        raise SettingsError(f"provider not configured: {provider}")
    base_url = str(entry.get("base_url") or "").strip()
    uri = f"{provider}@{base_url or '~'}:{model}"
    return uri, str(entry["api_key"])


# ── Pills → repo-relative paths (the agent reads them via its tools) ────────

def pill_relpaths(pills: list[dict]) -> list[str]:
    """Validate each pill against the repo and return the path the agent's
    tools understand — relative to the repo root, forward slashes.

    A pill may name a folder too: dropping a whole client (scope, path="")
    or any tree directory attaches it as a path the agent explores with its
    own list/tree tools — same contract as files, no pre-digestion here."""
    root = local_repo_path().resolve()
    rels = []
    for pill in pills or []:
        scope = str(pill.get("scope") or "")
        relpath = str(pill.get("path") or "")
        prefix = root / ("products" if scope == "products" else f"clients/{scope}")
        p = (prefix / relpath).resolve()
        # A pill names a repo path and nothing else — no traversal, no symlink out.
        if root not in p.parents:
            raise ValueError(f"pill outside the work repo: {scope}/{relpath}")
        if not p.exists():
            raise ValueError(f"attached path not found: {scope}/{relpath}")
        rel = p.relative_to(root).as_posix()
        rels.append(rel + "/" if p.is_dir() else rel)
    return rels


# ── Skill tools (loaded once, reused by every conversation) ────────────────

# The market repo is cloned/pulled and skill tools built once at process
# startup. Every SimpleAgent gets the same list — skills are global
# capabilities, not per-conversation state.  A failed load (no network, a
# broken skill) degrades to an empty list so chat keeps working.
_skill_tools_cache: list | None = None


def _get_skill_tools() -> list:
    """Return the cached skill tool list, building it on first call.

    Runs the full ensure_skills() pipeline (clone/pull + auto-install) so the
    agent service is self-sufficient — app.py does not need to know about the
    market repo, only this service does.
    """
    global _skill_tools_cache
    if _skill_tools_cache is None:
        try:
            from skills_manager import ensure_skills, load_skill_tools
            ensure_skills()
            _skill_tools_cache = load_skill_tools()[0]
        except Exception as exc:  # noqa: BLE001 — skills are additive, not load-bearing
            log.error("agent skill load failed: %s", exc)
            _skill_tools_cache = []
    return _skill_tools_cache


def refresh_skill_tools() -> list:
    """Force a re-scan and rebuild. Called after install/uninstall/toggle so
    the next conversation picks up the change without a process restart."""
    global _skill_tools_cache
    try:
        from skills_manager import load_skill_tools
        _skill_tools_cache = load_skill_tools()[0]
    except Exception as exc:  # noqa: BLE001
        log.error("agent skill refresh failed: %s", exc)
        _skill_tools_cache = []
    return _skill_tools_cache


# ── Live conversations (memory cache over the JSONL) ────────────────────────

class LiveConv:
    """One live Agent plus the bookkeeping the JSONL needs: which model built
    it, how many messages are already on disk, and its meta line."""

    def __init__(self, conv_id: str, meta: dict):
        self.id = conv_id
        self.meta = meta
        self.model_ref: str | None = None
        self.agent: SimpleAgent | None = None
        self.persisted = 0          # messages already written to the JSONL

    def ensure(self, model_ref: str, loaded: list[dict]) -> SimpleAgent:
        """(Re)build the Agent for this model. A model switch is a new Agent
        carrying the same messages — chak has no in-place swap."""
        if self.agent is not None and self.model_ref == model_ref:
            return self.agent
        uri, key = resolve_model(model_ref)
        prior = self.agent.dump() if self.agent is not None else loaded
        self.agent = SimpleAgent(uri, key, workdir=local_repo_path(),
                                 conv_id=self.id,
                                 context=self.meta.get("context") or {},
                                 history=prior or None,
                                 extra_tools=_get_skill_tools())
        self.model_ref = model_ref
        return self.agent

    def persist_new(self) -> None:
        """Append everything the Agent holds beyond what's on disk —
        including the system message on the very first turn."""
        dump = self.agent.dump() if self.agent else []
        fresh = dump[self.persisted:]
        if not fresh:
            return
        if not _conv_path(self.id).exists():
            append_lines(self.id, [self.meta])
        append_lines(self.id, fresh)
        self.persisted = len(dump)

    def update_meta(self, **fields) -> None:
        """Meta is append-only: write a fresh line, readers take the last."""
        self.meta = {**self.meta, **fields}
        if _conv_path(self.id).exists():
            append_lines(self.id, [self.meta])


_live: dict[str, LiveConv] = {}


def get_live(conv_id: str) -> LiveConv:
    lc = _live.get(conv_id)
    if lc is None:
        meta, messages = read_conv(conv_id)
        if meta is None:
            raise ValueError(f"no such conversation: {conv_id}")
        lc = LiveConv(conv_id, meta)
        lc.persisted = len(messages)
        _live[conv_id] = lc
    return lc


# ── WebSocket handler ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """clerk lives for as long as the service does."""
    task = asyncio.create_task(clerk.run_forever(resolve_model))
    try:
        yield
    finally:
        # Without this, shutdown waits on whatever LLM call the sweep is mid-way
        # through — up to PASS_TIMEOUT_SECS of a window that already closed.
        task.cancel()


app = FastAPI(title="Mortgage Work Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


async def _send_json(ws: WebSocket, obj: dict) -> None:
    await ws.send_text(json.dumps(obj, ensure_ascii=False))


async def handle_new(ws: WebSocket, data: dict) -> None:
    conv_id = new_conv_id()
    meta = {
        "type": "meta",
        "id": conv_id,
        "title": "New Chat",
        "created": datetime.now().isoformat(timespec="seconds"),
        "context": data.get("context") or {},
        "model": None,
    }
    # Memory only until the first send — an abandoned New Chat leaves no file
    _live[conv_id] = LiveConv(conv_id, meta)
    await _send_json(ws, {"type": "conv", "meta": meta, "messages": []})


async def handle_open(ws: WebSocket, data: dict) -> None:
    conv_id = str(data.get("conv_id") or "")
    lc = _live.get(conv_id)
    meta, messages = read_conv(conv_id) if _CONV_ID_RE.match(conv_id) else (None, [])
    if meta is None and lc is None:
        raise ValueError(f"no such conversation: {conv_id}")
    if lc is None:
        lc = LiveConv(conv_id, meta)
        lc.persisted = len(messages)
        _live[conv_id] = lc
    await _send_json(ws, {"type": "conv", "meta": lc.meta, "messages": messages})


async def handle_delete(ws: WebSocket, data: dict) -> None:
    """Drop one whole turn (user question + tool rounds + answer share a
    turn_id — chak's grouping makes the cascade the natural unit) and answer
    with the refreshed conversation."""
    conv_id = str(data.get("conv_id") or "")
    turn_id = str(data.get("turn_id") or "")
    if not turn_id:
        raise ValueError("no turn_id — nothing to delete")
    lc = get_live(conv_id)
    if lc.agent is not None:
        lc.agent.delete_turn(turn_id)
        dump = lc.agent.dump()
    else:
        # Not touched this session — operate straight on the file
        _, messages = read_conv(conv_id)
        dump = [m for m in messages if m.get("turn_id") != turn_id]
    if _conv_path(conv_id).exists():
        rewrite_conv(conv_id, lc.meta, dump)
    lc.persisted = len(dump)
    await _send_json(ws, {"type": "conv", "meta": lc.meta, "messages": dump})


async def run_send(ws: WebSocket, lc: LiveConv, data: dict) -> None:
    """One streamed turn. Runs as a task so `cancel` can interrupt it."""
    text = str(data.get("text") or "")
    model_ref = str(data.get("model") or "")
    _, loaded = read_conv(lc.id) if _conv_path(lc.id).exists() else (None, [])
    agent = lc.ensure(model_ref, loaded)
    files = pill_relpaths(data.get("pills") or [])
    quotes = [q for q in (data.get("quotes") or []) if isinstance(q, dict)]
    # What the composer actually held — stamped onto the HumanMessage so the
    # thread renders pills/quotes as components, not the composed prompt.
    display = {"text": text, "pills": data.get("pills") or [], "quotes": quotes}
    first_turn = lc.persisted == 0
    partial: list[str] = []
    try:
        final_message = None
        async for ev in agent.run(text, files, quotes):
            if isinstance(ev, MessageChunk):
                # Non-final chunks include intermediate tool-round text; the
                # frontend shows it live and swaps in final_message at done.
                if ev.content and not ev.is_final:
                    partial.append(ev.content)
                    await _send_json(ws, {"type": "chunk", "conv_id": lc.id,
                                          "content": ev.content})
                if ev.is_final and ev.final_message is not None:
                    final_message = ev.final_message
            elif isinstance(ev, ToolCallStartEvent):
                await _send_json(ws, {"type": "tool_start", "conv_id": lc.id,
                                      "tool": ev.tool_name, "call_id": ev.call_id,
                                      "arguments": ev.arguments})
            elif isinstance(ev, ToolCallSuccessEvent):
                await _send_json(ws, {"type": "tool_end", "conv_id": lc.id,
                                      "tool": ev.tool_name, "call_id": ev.call_id,
                                      "result": ev.result})
            elif isinstance(ev, ToolCallErrorEvent):
                await _send_json(ws, {"type": "tool_error", "conv_id": lc.id,
                                      "tool": ev.tool_name, "call_id": ev.call_id,
                                      "error": ev.error})
        # Turn is complete — now make it durable, then tell the frontend.
        agent.stamp_display(display)
        if first_turn:
            lc.meta = {**lc.meta, "title": make_title(lc.meta.get("context") or {}, text),
                       "model": model_ref}
        elif lc.meta.get("model") != model_ref:
            lc.update_meta(model=model_ref)
        lc.persist_new()
        done_msg = (final_message.model_dump(mode="json")
                    if final_message is not None else {"role": "assistant",
                                                       "content": "".join(partial)})
        await _send_json(ws, {"type": "done", "conv_id": lc.id,
                              "message": done_msg, "meta": lc.meta})
        # The fallback title above is a truncation of the question — now that
        # the answer exists, let the model write a real one in the background.
        if first_turn:
            _spawn_retitle(ws, lc, text, str(done_msg.get("content") or ""),
                           model_ref)
    except asyncio.CancelledError:
        # Stop pressed mid-stream. chak appends a turn's messages only after
        # it completes, so nothing of this turn is in the history yet — the
        # agent reconstructs the question + partial answer as one turn.
        if agent is not None:
            ai = agent.mark_cancelled(text, files, quotes, "".join(partial))
            agent.stamp_display(display)
            if first_turn:
                lc.meta = {**lc.meta, "title": make_title(lc.meta.get("context") or {}, text),
                           "model": model_ref}
            lc.persist_new()
            await _send_json(ws, {"type": "cancelled", "conv_id": lc.id,
                                  "message": ai.model_dump(mode="json"),
                                  "meta": lc.meta})
        raise


class Session:
    """One WS connection (the app has exactly one). Owns the in-flight tasks
    so a disconnect can cancel whatever is still streaming."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.tasks: dict[str, asyncio.Task] = {}

    async def dispatch(self, data: dict) -> None:
        msg_type = data.get("type")
        if msg_type == "new":
            await handle_new(self.ws, data)
        elif msg_type == "open":
            await handle_open(self.ws, data)
        elif msg_type == "list":
            await _send_json(self.ws, {"type": "convs", "items": list_convs()})
        elif msg_type == "send":
            conv_id = str(data.get("conv_id") or "")
            lc = get_live(conv_id)
            if conv_id in self.tasks and not self.tasks[conv_id].done():
                raise ValueError("a reply is already streaming — stop it first")
            task = asyncio.create_task(run_send(self.ws, lc, data))
            self.tasks[conv_id] = task
            task.add_done_callback(lambda t: self._reap(conv_id, t))
        elif msg_type == "cancel":
            task = self.tasks.get(str(data.get("conv_id") or ""))
            if task and not task.done():
                task.cancel()
        elif msg_type == "delete":
            conv_id = str(data.get("conv_id") or "")
            if conv_id in self.tasks and not self.tasks[conv_id].done():
                raise ValueError("a reply is streaming — stop it first")
            await handle_delete(self.ws, data)
        else:
            raise ValueError(f"unknown message type: {msg_type}")

    def _reap(self, conv_id: str, task: asyncio.Task) -> None:
        self.tasks.pop(conv_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            # The task can't answer anymore; report on its behalf.
            log.error("agent reply task failed", exc_info=exc)
            asyncio.ensure_future(_send_json(self.ws, {
                "type": "error", "conv_id": conv_id, "error": str(exc)}))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    session = Session(ws)
    try:
        while True:
            try:
                data = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                await _send_json(ws, {"type": "error", "error": "invalid JSON"})
                continue
            try:
                await session.dispatch(data)
            except (SettingsError, RepoError, ValueError) as exc:
                await _send_json(ws, {"type": "error",
                                      "conv_id": data.get("conv_id"),
                                      "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 — one bad message must not drop the socket
                log.exception("agent dispatch failed")
                await _send_json(ws, {"type": "error",
                                      "conv_id": data.get("conv_id"),
                                      "error": f"agent error: {exc}"})
    except WebSocketDisconnect:
        pass
    finally:
        for task in session.tasks.values():
            task.cancel()


def _wait_for_port(host: str, port: int, timeout: float = 20.0) -> None:
    """Block until the port is bindable. Restarting the app races the old
    instance's teardown: the fresh service spawns while the dying one still
    holds the port, and dying on Errno 10048 here leaves chat offline for the
    whole session. Waiting out the handover costs a second, not the feature."""
    deadline = time.monotonic() + timeout
    while True:
        # Plain bind, no SO_REUSEADDR: on Windows that flag lets the probe
        # "succeed" against a live listener, which is exactly the lie we're
        # here to avoid — this probe must fail precisely when uvicorn would.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return
            except OSError:
                if time.monotonic() >= deadline:
                    log.error("agent port %s still busy after %.0fs — giving up", port, timeout)
                    sys.exit(1)
                time.sleep(0.5)


if __name__ == "__main__":
    setup_logging()
    _wait_for_port("127.0.0.1", SERVICES.agent_port)
    log.info("agent ws://127.0.0.1:%s/ws", SERVICES.agent_port)
    uvicorn.run(app, host="127.0.0.1", port=SERVICES.agent_port,
                log_level="warning")
