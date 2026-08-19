"""HTTP clients for the external services this app integrates with.

Each module is a pure wrapper around one service's REST API — no business
logic, no local state. Callers decide *when* to call and *what* to do with
results.

  rag.py   RAG service — vector datasets and document processing
           (+ QdrantStoreClient: read-only browser over the raw Qdrant store)
  kg.py    KG service — knowledge-graph ingestion on FalkorDB
           (+ FalkorStoreClient: read-only browser over the raw FalkorDB store)
"""
from .kg import FalkorStoreClient, KgClient
from .rag import QdrantStoreClient, RagClient

__all__ = ["FalkorStoreClient", "KgClient", "QdrantStoreClient", "RagClient"]
