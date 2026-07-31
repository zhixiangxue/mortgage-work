"""SimpleAgent — one chak Conversation with tools over the work repo.

Design decisions (agreed with the chak team, see their Q&A):
- No chak Attachments. Attached files are passed as repo-relative paths in
  the prompt; the model reads them itself through the tools. One mental
  model — everything is a file under the working directory.
- Tools: FileSystem(base=workdir, mode="rw") enforces the directory boundary
  natively — full read/write inside the repo, nothing outside it (writes are
  recoverable: the repo is git-versioned and synced). PDFs are read through the
  confined, read-only Pdf in tools/ — shared with clerk, so both agents read
  documents through the same boundary.
- Interrupt safety: mark_cancelled appends a plain-text assistant message
  only. chak appends (assistant tool_calls + tool results) atomically after
  tools finish, so a cancelled turn can never leave orphaned tool_calls.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Sequence

import chak
from chak import AIMessage, FIFOContextHandler, HumanMessage
from tools import FileSystem, Pdf

from .base import Agent

# The JSONL on disk keeps the full transcript; this only bounds the LLM's
# window. A turn = one user message plus everything until the next one.
MAX_CONTEXT_TURNS = 20
# One user turn should never need more tool rounds than this (chak default
# is 50; a loan-file question is a handful of reads, runaway loops cost money)
MAX_TOOL_ITERATIONS = 30

PERSONA = """You are the AI assistant inside Mortgage Work, a loan officer's desktop workbench. You help with mortgage files: reviewing client documents, income analysis, missing-document checklists, product/guideline lookups and drafting messages.

Working directory: {workdir}
Everything lives under it: client files in clients/<client-id>/, product and guideline documents in products/. Use your tools to look things up — list_dir/tree/find/grep to locate files, read_file for text, the pdf tools for PDFs — and to do the work: write_file/edit_file when the user asks you to draft, fix or update something. Always pass paths relative to the working directory. You must never access anything outside the working directory; the tools enforce this.

Check a PDF's metadata before reading it whole. Client documents are short, but a lender's guideline in products/ can run to over a thousand pages — search and read_pages find the clause you need, where read_all would bury the answer and the rest of the conversation with it.

Rules:
- Be concise and concrete; loan officers read answers between calls.
- When the user references a file, read it before answering — ground every statement in actual file content.
- Never invent numbers that should come from a document.
- Only write or change files the user asked for; never delete or overwrite anything else.
- Answer in the language the user writes in."""


class SimpleAgent(Agent):
    """The V1 agent: persona + workdir-confined tools, no orchestration."""

    def __init__(self, model_uri: str, api_key: str, *, workdir: str | Path,
                 conv_id: str | None = None, context: dict | None = None,
                 history: list[dict] | None = None):
        workdir = Path(workdir).resolve()
        self._conv = chak.Conversation(
            model_uri, api_key=api_key, id=conv_id,
            # The system message rides in the history once persisted; only a
            # brand-new conversation needs it composed here.
            system_prompt=None if history else self._system_prompt(workdir, context or {}),
            context_handler=FIFOContextHandler(keep_recent_turns=MAX_CONTEXT_TURNS),
            tools=[FileSystem(base=workdir, mode="rw"), Pdf(base=workdir)],
        )
        if history:
            self._conv.load(history)
        self._conv.tool.loop.max(MAX_TOOL_ITERATIONS)

    @staticmethod
    def _system_prompt(workdir: Path, context: dict) -> str:
        client = context.get("client") or {}
        # Spell out the exact directory — display names ("Sarah Mitchell")
        # tempt the model into guessing paths that don't exist.
        where = (f"client file: {client.get('name')} "
                 f"(files under clients/{client.get('id')}/)") if client.get("id") \
            else "the product library" if context.get("view") == "products" \
            else "the whole book of business"
        return PERSONA.format(workdir=workdir) + \
            f"\n\nThis conversation was opened on {where}."

    async def run(self, text: str, files: Sequence[str] = ()) -> AsyncIterator[Any]:
        stream = await self._conv.asend(self._compose(text, files),
                                        stream=True, event=True)
        async for ev in stream:
            yield ev

    @staticmethod
    def _compose(text: str, files: Sequence[str]) -> str:
        """Attached files become a path list the model can feed its tools."""
        if not files:
            return text
        listing = "\n".join(f"- {f}" for f in files)
        return (f"{text}\n\n"
                f"Attached files (paths relative to the working directory):\n{listing}")

    def dump(self) -> list[dict]:
        return self._conv.dump()

    def mark_cancelled(self, text: str, files: Sequence[str], partial: str) -> AIMessage:
        # chak appends a turn's messages atomically after it completes, so a
        # cancelled turn usually left nothing behind — not even the user's
        # question. Reconstruct it (same composed prompt a finished turn would
        # have stored) unless some chak path did append it already, and give
        # both halves one turn_id so the pair deletes as a unit.
        composed = self._compose(text, files)
        last = self._conv.messages[-1] if self._conv.messages else None
        if isinstance(last, HumanMessage) and last.content == composed:
            turn = last.turn_id or str(uuid.uuid4())
            last.turn_id = turn
        else:
            turn = str(uuid.uuid4())
            self._conv.messages.append(HumanMessage(content=composed, turn_id=turn))
        ai = AIMessage(content=partial, custom={"cancelled": True}, turn_id=turn)
        self._conv.messages.append(ai)
        return ai

    def delete_turn(self, turn_id: str) -> None:
        if not turn_id:
            raise ValueError("no turn_id — refusing to delete")
        # chak's official turn removal: cascades over the whole turn, never
        # touches system messages, raises on a stale/unknown turn_id.
        self._conv.remove_turn(turn_id)
