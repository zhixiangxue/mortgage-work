"""Contract-driven context handler for research-loop conversations.

Mechanical (non-LLM) context compression keyed on completed
``scratchpad-save_*`` runs. Designed to work in tandem with chak's
``Scratchpad`` tool: the LLM digests large tool results (PDF pages, file
reads) and then emits a *run* of ``scratchpad-save_section`` calls to
persist the key findings. Once that save run has *completed* — i.e. a
non-save tool cycle follows it — the raw material before it is considered
digested and bulky ToolMessages from those cycles are stubbed with compact
placeholders.

Two levels of compression:

1. **Inter-turn** (``handle_turn``): once a complete round exists (final
   AIMessage without tool_calls), offload ToolMessages from that round.
2. **Intra-turn** (``handle_round``): within a single ``asend()`` tool loop,
   stub bulky ToolMessages from digested cycles (above a token threshold).

AIMessage(tool_calls) are always preserved so the LLM can see its own call
history. The rule is size-based, with **one exception**: any tool whose name
starts with ``scratchpad-`` is never stubbed. The scratchpad is the LLM's
external memory layer — stubbing its read results would make the model doubt
its own persisted notes and can trigger destructive save/remove loops.

This handler performs **no LLM calls**.
"""
from __future__ import annotations

from typing import List

from chak.context.handlers.base import BaseContextHandler
from chak.message import AIMessage, HumanMessage, Message, SystemMessage, ToolMessage

# Placeholder for inter-turn offloaded rounds.
_OFFLOAD_PLACEHOLDER = SystemMessage(
    content=(
        "[Context compression] Tool results from this round were consumed "
        "when the final structured output was produced.  Key findings should "
        "have been saved to the scratchpad. Use `scratchpad-list_sections` to "
        "see what is available, then `scratchpad-read_section` for specifics."
    )
)

# Stub template for offloaded tool results. Replaces bulky ToolMessage content
# while preserving tool_call_id so pairing integrity is maintained.
_TOOL_RESULT_STUB_TPL = (
    "[offloaded] {tool_name}({args_hint}) returned ~{tokens} tokens. "
    "The content itself is no longer in context. If you saved its findings, "
    "refer to your scratchpad sections; if anything you still need is "
    "missing, re-call the tool to read it again."
)

# Prefix chak uses for framework-level error results (invalid JSON args,
# tool-not-found, etc.). Long error messages usually just echo the original
# tool arguments verbatim — they should never accumulate in context.
_ERROR_PREFIX = "Error: "

# Tools whose results are treated as "memory access", not "content", and must
# never be stubbed. Rationale: the scratchpad is the LLM's external memory.
# Stubbing its read result makes some models treat the notes as throwaway and
# enter a destructive save/remove loop. Scratchpad has its own soft line limit
# so total token cost stays bounded.
_MEMORY_TOOL_PREFIX = "scratchpad-"

# Signal used to detect "the LLM has committed findings" — any tool call whose
# name starts with this prefix marks a save cycle. Consecutive save cycles
# form a *save run*; only once a run is followed by a non-save cycle is the
# material before it considered digested. That is the contract.
_SAVE_TOOL_PREFIX = "scratchpad-save_"

# tiktoken encoding used to estimate ToolMessage content size. Loaded lazily
# so import stays cheap.
_TIKTOKEN_ENCODING_NAME = "cl100k_base"
_encoder = None


def _count_tokens(text: str) -> int:
    """Return the tiktoken token count for *text*. Lazy-init the encoder."""
    global _encoder
    if _encoder is None:
        import tiktoken
        _encoder = tiktoken.get_encoding(_TIKTOKEN_ENCODING_NAME)
    return len(_encoder.encode(text))


class ContractContextHandler(BaseContextHandler):
    """Mechanical offloader for research-loop conversations.

    Two compression modes:

    * **Inter-turn** (``handle_turn``): replaces ToolMessages in completed
      rounds with a compact placeholder.
    * **Intra-turn** (``handle_round``): contract-driven cleanup keyed on
      *completed* ``scratchpad-save_*`` runs. A save run is complete once the
      LLM stops saving and does something else (typically a new read). Only
      cycles strictly before the last completed run are eligible for stubbing:
      bulky ToolMessages (content token count above ``stub_threshold_tokens``)
      are replaced with compact stubs while the AIMessage(tool_calls) is
      preserved.

    If the LLM has never completed a save run, the handler leaves the tool
    loop untouched (bulky error results excepted).

    A round is *complete* when it ends with an AIMessage that has no pending
    tool_calls.
    """

    def __init__(self, stub_threshold_tokens: int = 2000):
        super().__init__()
        self.stub_threshold_tokens = stub_threshold_tokens

    # ------------------------------------------------------------------
    # Intra-turn: stub stale tool results within the current tool loop
    # ------------------------------------------------------------------
    def handle_round(
        self,
        messages: List[Message],
        *,
        conversation_id: str = "",
        round_index: int = 0,
    ) -> List[Message]:
        """Called before every LLM round inside a tool loop.

        Contract: the LLM digests reads by emitting a run of
        ``scratchpad-save_*`` calls. Only when that run has *completed* (a
        non-save cycle follows it) do the cycles before it become stubbable.
        Cycles from the run onward are kept verbatim so the model never has
        to transcribe from memory. If no run has completed, nothing is
        stubbed except bulky error results.
        """
        cycles = self._split_into_cycles(messages)

        # cycles[0] is the prefix (system + human). Anything <= 1 tool cycle
        # is too small to be worth compressing.
        if len(cycles) <= 2:
            return messages

        prefix = cycles[0]
        tool_cycles = cycles[1:]

        # Index of the first cycle that is NOT yet digested.
        boundary = self._digested_boundary(tool_cycles)

        result: List[Message] = list(prefix)
        for i, cycle in enumerate(tool_cycles):
            if i < boundary:
                result.extend(self._stub_cycle(cycle))
            else:
                result.extend(self._stub_errors_only(cycle))
        return result

    def _digested_boundary(self, tool_cycles: List[List[Message]]) -> int:
        """Return the index of the first cycle that is not yet digested."""
        flags = [self._cycle_has_save(c) for c in tool_cycles]

        last_completed_save = -1
        seen_non_save_after = False
        for i in range(len(tool_cycles) - 1, -1, -1):
            if flags[i]:
                if seen_non_save_after:
                    last_completed_save = i
                    break
            else:
                seen_non_save_after = True

        if last_completed_save < 0:
            return 0

        # Walk back to the start of the run.
        run_start = last_completed_save
        while run_start - 1 >= 0 and flags[run_start - 1]:
            run_start -= 1
        return run_start

    @staticmethod
    def _cycle_has_save(cycle: List[Message]) -> bool:
        """True iff this cycle contains an AIMessage calling ``scratchpad-save_*``."""
        for msg in cycle:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.function.name.startswith(_SAVE_TOOL_PREFIX):
                        return True
        return False

    def _stub_errors_only(self, cycle: List[Message]) -> List[Message]:
        """Stub only bulky error tool results in a cycle; keep everything else."""
        result: List[Message] = []
        for msg in cycle:
            if isinstance(msg, ToolMessage):
                content = str(msg.content) if msg.content else ""
                if (
                    content.startswith(_ERROR_PREFIX)
                    and _count_tokens(content) > self.stub_threshold_tokens
                ):
                    tool_name, args_hint = self._lookup_tool_info(cycle, msg)
                    result.append(self._make_stub(msg, tool_name, args_hint, content))
                    continue
            result.append(msg)
        return result

    def _stub_cycle(self, cycle: List[Message]) -> List[Message]:
        """Stub bulky ToolMessages in a digested cycle, keep AIMessage intact."""
        result: List[Message] = []
        for msg in cycle:
            if isinstance(msg, ToolMessage):
                tool_name, args_hint = self._lookup_tool_info(cycle, msg)
                if tool_name.startswith(_MEMORY_TOOL_PREFIX):
                    result.append(msg)
                    continue
                content = str(msg.content) if msg.content else ""
                if _count_tokens(content) > self.stub_threshold_tokens:
                    result.append(self._make_stub(msg, tool_name, args_hint, content))
                else:
                    result.append(msg)
            else:
                result.append(msg)
        return result

    @staticmethod
    def _lookup_tool_info(cycle: List[Message], tool_msg: ToolMessage) -> tuple[str, str]:
        """Find the tool name and arguments for a ToolMessage by matching tool_call_id."""
        for msg in cycle:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.id == tool_msg.tool_call_id:
                        return tc.function.name, tc.function.arguments
        return "", ""

    @staticmethod
    def _make_stub(
        tool_msg: ToolMessage,
        tool_name: str,
        args_hint: str,
        content: str,
    ) -> ToolMessage:
        """Create a stub ToolMessage replacing bulky content with a compact hint."""
        token_count = _count_tokens(content)
        stub = _TOOL_RESULT_STUB_TPL.format(
            tool_name=tool_name or "unknown",
            args_hint=(args_hint or "")[:200],
            tokens=token_count,
        )
        return tool_msg.model_copy(update={"content": stub})

    @staticmethod
    def _split_into_cycles(messages: List[Message]) -> List[List[Message]]:
        """Split messages into [prefix, cycle1, cycle2, ...].

        prefix = system + human + any leading AI text without tool_calls.
        Each subsequent cycle = AIMessage(tool_calls) + its ToolMessages.
        """
        groups: List[List[Message]] = [[]]
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                groups.append([msg])
            elif isinstance(msg, ToolMessage) and len(groups) > 1:
                groups[-1].append(msg)
            else:
                groups[-1].append(msg)
        return groups

    # ------------------------------------------------------------------
    # Inter-turn: offload completed rounds between asend() calls
    # ------------------------------------------------------------------
    def handle_turn(
        self,
        messages: List[Message],
        *,
        conversation_id: str = "",
    ) -> List[Message]:
        if not messages:
            return []

        system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        conv_msgs = [m for m in messages if not isinstance(m, SystemMessage)]

        # Find round boundaries (HumanMessage → ... → final AIMessage)
        round_boundaries: list[tuple[int, int]] = []

        i = len(conv_msgs) - 1
        while i >= 0:
            msg = conv_msgs[i]
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                round_end = i
                round_start = round_end
                for j in range(round_end - 1, -1, -1):
                    if isinstance(conv_msgs[j], HumanMessage):
                        round_start = j
                        break
                round_boundaries.append((round_start, round_end))
                i = round_start - 1
            else:
                i -= 1

        round_boundaries.reverse()

        if not round_boundaries:
            return messages

        result: List[Message] = list(system_msgs)

        last_boundary_end = round_boundaries[-1][1]
        has_incomplete = last_boundary_end < len(conv_msgs) - 1

        digested_boundaries = round_boundaries[:-1] if has_incomplete else round_boundaries
        incomplete_boundary = round_boundaries[-1] if has_incomplete else None

        for round_start, round_end in digested_boundaries:
            for idx in range(round_start, round_end + 1):
                msg = conv_msgs[idx]
                if isinstance(msg, ToolMessage):
                    continue
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    continue
                result.append(msg)
            result.append(_OFFLOAD_PLACEHOLDER)

        if incomplete_boundary is not None:
            start = incomplete_boundary[0]
            for idx in range(start, len(conv_msgs)):
                result.append(conv_msgs[idx])
        elif round_boundaries:
            start = round_boundaries[-1][0]
            end = round_boundaries[-1][1]
            for idx in range(start, end + 1):
                result.append(conv_msgs[idx])

        return result
