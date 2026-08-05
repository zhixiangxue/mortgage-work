"""The Agent interface — what the wire service programs against.

An Agent is conversation-scoped: constructed once per (conversation, model)
pair, fed one user turn at a time, and streamed back as chak events. It owns
everything cognitive: the system prompt, the tools, how attached files are
surfaced to the model. The service owns everything else: sockets, JSONL
persistence, model→credentials resolution, task lifecycle.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Sequence


class Agent(ABC):
    """One conversation's brain.

    Implementations wrap whatever machinery they need (a chak Conversation
    today, a pipeline of them tomorrow) behind three capabilities: run a turn,
    dump state for persistence, and record an interrupted turn.
    """

    @abstractmethod
    def run(self, text: str, files: Sequence[str] = (),
            quotes: Sequence[dict] = (),
            scope_doc_ids: Sequence[str] | None = None) -> AsyncIterator[Any]:
        """Run one user turn; yield chak stream events as they happen.

        ``files`` are repo-relative paths the user attached — how they reach
        the model (prompt text, attachments, tool hints) is up to the agent.
        ``scope_doc_ids`` is the hidden per-turn RAG/KG document boundary
        resolved from the same attachments: ``None`` means unrestricted,
        an empty sequence means "attached, but nothing indexed". It never
        rides in the prompt — only tools with knowledge-search capability
        read it, through their own ``set_scope`` method.
        Yields MessageChunk / ReasoningChunk / ToolCall*Event objects; the
        MessageChunk with ``is_final=True`` carries the turn's final message.
        Cancellation arrives as asyncio.CancelledError at any await point.
        """

    @abstractmethod
    def dump(self) -> list[dict]:
        """Full message history as JSON-ready dicts (chak dump format)."""

    @abstractmethod
    def mark_cancelled(self, text: str, files: Sequence[str], partial: str) -> Any:
        """Record an interrupted turn. chak only appends a turn's messages
        after it completes, so a cancelled turn must be reconstructed: the
        user's question (text+files, composed the same way run() sends it)
        plus a plain assistant message holding whatever streamed (never
        fabricated tool calls — tool_calls without results would poison the
        next request). Returns the appended assistant message."""

    @abstractmethod
    def delete_turn(self, turn_id: str) -> None:
        """Drop every message of one turn (chak groups a user message, its
        tool rounds and the final answer under one turn_id). Whole turns are
        the only safe deletion unit — removing part of one would strand
        tool_calls without results."""
