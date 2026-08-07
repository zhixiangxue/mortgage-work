"""Agent abstractions for Mortgage Work.

The wire service (agent_service.py) owns transport and persistence; what
happens between a user turn and the final answer is an Agent's business.
QAAgent is the interactive implementation; clerk runs as a background batch
job. Richer agents (planners, multi-agent pipelines) plug in behind the same
interface.
"""
from .base import Agent
from .qa import QAAgent

__all__ = ["Agent", "QAAgent"]
