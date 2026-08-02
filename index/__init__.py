"""Product indexing pipeline — RAG + KG auto-indexing on commit.

Module structure
----------------
  state.py    Pure SQLite: doc_id → task/status per side
  rag.py      RAG service HTTP client (vectors)
  kg.py       KG service HTTP client (knowledge graph)
  indexer.py  Business orchestration: trigger, poll, retry, state callbacks

Usage from the rest of the app::

    import index
    index.init(repo_root)             # call once on boot (after repo is ready)
    index.on_indexing_state(cb)       # register UI listener
    index.ensure_dataset()            # async — create RAG collection
    # ... later, from workrepo.flush_sync:
    index.trigger("products", entries)

All client singletons (``rag``, ``kg``) are created here from ``SERVICES``
and injected into ``indexer`` at import time.
"""
from __future__ import annotations

from config import SERVICES
from .state import init_db, calculate_file_hash
from .rag import RagClient
from .kg import KgClient
from . import indexer

# ── Client singletons ──
# Created once from config; shared across the module. indexer.py reads these
# via its module-level ``rag`` / ``kg`` attributes, which we set here.

rag = RagClient(
    SERVICES.rag_service_url,
    SERVICES.rag_api_key,
    SERVICES.rag_dataset_id,
)
kg = KgClient(
    SERVICES.kg_service_url,
    SERVICES.kg_api_key,
    SERVICES.rag_dataset_id,
)

# Inject into indexer so its functions can use them directly
indexer.rag = rag
indexer.kg = kg


def init(repo_root) -> None:
    """Initialize the SQLite database. Call once on boot after repo is ready.

    Idempotent — safe to call multiple times.
    """
    from pathlib import Path
    init_db(Path(repo_root))


# ── Public API (re-exported for convenience) ──
on_indexing_state = indexer.on_indexing_state
ensure_dataset = indexer.ensure_dataset
trigger = indexer.trigger
retry_failed = indexer.retry_failed
recover_stale = indexer.recover_stale
summary = indexer.summary
