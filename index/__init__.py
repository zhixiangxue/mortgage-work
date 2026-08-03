"""Product indexing pipeline — RAG + KG auto-indexing on commit.

Module structure
----------------
  state.py    Pure SQLite: doc_id → task/status per side
  indexer.py  Business orchestration: trigger, poll, retry, state callbacks

The RAG/KG HTTP clients live in the top-level ``integration`` package —
they're generic service adapters, not part of the indexing pipeline itself.

Usage from the rest of the app::

    import index
    index.init(repo_root)             # call once on boot (after repo is ready)
    index.on_indexing_state(cb)       # register UI listener
    index.ensure_dataset()            # async — create RAG collection
    # ... later, from workrepo.flush_sync:
    index.trigger("products", entries)

All client singletons (``rag``, ``kg``) are created here from ``SERVICES``
(infra config) and ``user.current_user()`` (identity) and injected into
``indexer`` at import time.
"""
from __future__ import annotations

from config import SERVICES
from user import current_user
from integration import KgClient, RagClient
from .state import init_db, calculate_file_hash
from . import indexer

# ── Client singletons ──
# Created once from config (infra) + user (identity); shared across the module.
# indexer.py reads these via its module-level ``rag`` / ``kg`` attributes.

_u = current_user()
rag = RagClient(
    SERVICES.rag_service_url,
    SERVICES.rag_api_key,
    _u.rag_dataset_id,
)
kg = KgClient(
    SERVICES.kg_service_url,
    SERVICES.kg_api_key,
    _u.kg_graph_name,
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
