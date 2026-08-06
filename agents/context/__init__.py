"""Context management strategies for agent conversations.

Each handler implements chak's ``BaseContextHandler`` interface
(``handle_turn`` + ``handle_round``). The wire service (agent_service.py)
constructs one handler per conversation and passes it to the chak
Conversation; chak calls it before every LLM round.

Available strategies:

- :class:`~agents.context.contract.ContractContextHandler` — mechanical
  offloader keyed on completed scratchpad-save runs.
"""
from __future__ import annotations

from .contract import ContractContextHandler

__all__ = ["ContractContextHandler"]
