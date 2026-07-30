"""Agent abstractions for Mortgage Work.

The wire service (agent_service.py) owns transport and persistence; what
happens between a user turn and the final answer is an Agent's business.
Today there is one implementation (SimpleAgent — a single chak Conversation
with read-only file tools); richer agents (planners, multi-conversation
pipelines) plug in behind the same interface.
"""
from .base import Agent
from .simple import SimpleAgent

__all__ = ["Agent", "SimpleAgent"]
