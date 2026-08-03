"""HTTP clients for the external services this app integrates with.

Each module is a pure wrapper around one service's REST API — no business
logic, no local state. Callers decide *when* to call and *what* to do with
results.

  rag.py   RAG service — vector datasets and document processing
  kg.py    KG service — knowledge-graph ingestion on FalkorDB
"""
from .kg import KgClient
from .rag import RagClient

__all__ = ["KgClient", "RagClient"]
