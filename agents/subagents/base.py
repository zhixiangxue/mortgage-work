"""SubAgent base — a chak tool that wraps a domain skill inside its own Conversation.

Each sub-agent is a single-method tool (``invoke``) that any outer agent (clerk,
QA-agent) can add to its tool list.  Internally, a fresh chak Conversation is
created per call, the skill is loaded, the request is sent, and a concise text
summary comes back.  The inner conversation's context never leaks into the
outer agent's window — that is the whole reason this layer exists.

Designed for reuse: the base class has zero clerk-specific logic.  Any agent
that needs a domain expert instantiates the same sub-agent classes.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Max tool iterations inside a sub-agent's inner conversation.  A vision skill
# reading a multi-page PDF needs more than a handful, but an unbounded loop
# costs money.
_SUBAGENT_MAX_ITERATIONS = 25

# Context prefix prepended to every sub-agent's system prompt — tells the inner
# LLM where it is, where to find things, and how to address paths.  Without
# this the sub-agent has no idea what the repo layout looks like and starts
# guessing paths (which is how the first e2e test burned 25 iterations on
# "File not found" errors).
_CONTEXT_PREFIX = """\
Working from: {root}
Client documents are under clients/<slug>/ (e.g. clients/marcus-webb/income/).
Loan program guidelines and matrices are under products/ (e.g. products/itrust/).
All paths are relative to the repo root. Use filesystem-list_dir or filesystem-tree \
to explore before guessing — never assume a file exists from its name alone."""


class SubAgent:
    """A chak tool that wraps a domain skill inside its own Conversation.

    To any outer agent, this is just a tool with one method: ``invoke``.
    Internally, each call spins up a fresh chak Conversation with this
    sub-agent's system prompt, loads the ClaudeSkill, sends the request,
    and returns the final message text.

    Subclasses define:
        ``name``          — tool identifier (e.g. ``"income-analyzer"``)
        ``description``   — one-line description for the outer agent's tool list
        ``SYSTEM_PROMPT`` — system prompt for the inner Conversation
        ``TIMEOUT_SECS``  — per-call timeout (default 180)
    """

    name: str = ""
    description: str = ""
    SYSTEM_PROMPT: str = ""
    TIMEOUT_SECS: int = 180

    def __init__(self, skill_dir: str, model_uri: str, api_key: str,
                 root: Path):
        self._skill_dir = skill_dir
        self._model_uri = model_uri
        self._api_key = api_key
        self._root = root

    def __available__(self) -> frozenset[str]:
        return frozenset({"invoke"})

    async def invoke(self, request: str) -> str:
        """Send a natural-language request to this expert.

        Returns a concise text summary suitable for an orchestrator's context.
        On failure, returns an error string — never raises, so the outer
        agent's pass continues with the rest of its work.
        """
        import chak
        from chak.tools.std import Scratchpad
        from chak.tools.skills import ClaudeSkill, PyRunner
        from skills_manager import _venv_python
        from ..context import ContractContextHandler
        from ..tools import FileSystem, Pdf, Reader

        import tempfile

        # Fresh scratchpad per call — the inner conversation is throwaway.
        scratch_path = Path(tempfile.mkdtemp(prefix="mw-subagent-")) / "scratchpad.json"
        scratchpad = Scratchpad(path=str(scratch_path), mode="rw")

        # The skill runs with read access to the repo root — it may need to
        # read client documents and product guidelines.
        python_exe = str(_venv_python(Path(self._skill_dir)))
        skill = ClaudeSkill(self._skill_dir,
                            runner=PyRunner(python=python_exe))

        # Compose the system prompt: context prefix (where things are) +
        # subclass-specific role/expertise prompt.
        system_prompt = (
            _CONTEXT_PREFIX.format(root=self._root)
            + "\n\n"
            + self.SYSTEM_PROMPT
        )

        conv = chak.Conversation(
            self._model_uri,
            api_key=self._api_key,
            system_prompt=system_prompt,
            context_handler=ContractContextHandler(stub_threshold_tokens=2000),
            tools=[FileSystem(base=self._root, mode="r"),
                   Pdf(base=self._root),
                   Reader(base=self._root, vision=self._model_uri,
                          vision_api_key=self._api_key),
                   skill, scratchpad],
        )
        conv.tool.loop.max(_SUBAGENT_MAX_ITERATIONS)

        # Convergence nudge: the expert should analyze, summarize, and stop —
        # not iterate indefinitely on its own output.
        full_request = (
            f"{request}\n\n"
            f"Analyze the documents, use your skill tools, then return a concise "
            f"text summary. Do not repeat tool calls once you have the answer."
        )

        try:
            resp = await conv.asend(full_request, timeout=self.TIMEOUT_SECS)
            return (getattr(resp, "content", "") or "").strip()
        except Exception as exc:  # noqa: BLE001 — error isolation contract
            log.error("subagent %s invoke failed: %s", self.name, exc)
            return f"[{self.name} error: {type(exc).__name__}: {exc}]"
