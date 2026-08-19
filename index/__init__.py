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

All client singletons (``rag``, ``kg``) are created here from
``runtime_services`` (session-delivered credentials) and
``user.current_user()`` (identity) and injected into
``indexer``. Construction is LAZY — identity only exists after login, and
this package is imported at boot regardless, so the clients materialize on
first post-login use (``init`` / ``ensure_clients``), never at import.
"""
from __future__ import annotations

from runtime_services import kg_target, rag_target
from user import AuthError, current_user
from integration import KgClient, RagClient
from .state import init_db, calculate_file_hash
from . import indexer

# ── Client singletons ──
# Built from session credentials (runtime_services) + user (identity);
# shared across the module. indexer.py reads these via its module-level
# ``rag`` / ``kg`` attributes. None until a user is logged in — boot
# happens without one.

rag = None
kg = None
# User id the singletons above were built for. A logout/login cycle keeps
# this process alive, so identity must be checked on every ensure — otherwise
# the new user's uploads would silently land in the previous user's storage.
_client_owner = None


def ensure_clients() -> None:
    """Build (or rebuild, after a logout/login cycle) the RAG/KG singletons
    and re-inject them into the indexer. Idempotent while the SAME user stays
    logged in; a no-op before login so pre-login callers degrade instead of
    crashing. When the identity changes, the singletons are rebuilt for the
    new user's dataset/graph."""
    global rag, kg, _client_owner
    try:
        u = current_user()
    except AuthError:
        return  # not logged in yet — indexer's None-guards carry the gap
    if rag is not None and kg is not None and _client_owner == u.id:
        return
    rag_url, rag_key = rag_target()
    kg_url, kg_key = kg_target()
    rag = RagClient(rag_url, rag_key, u.rag_dataset_id)
    kg = KgClient(kg_url, kg_key, u.kg_graph_name)
    # Re-inject: indexer resolves these as module globals at call time.
    indexer.rag = rag
    indexer.kg = kg
    _client_owner = u.id
    # Fresh identity — the previous user's "dataset ready" gate must not let
    # this user's triggers fire before their own dataset exists.
    indexer._dataset_ready.clear()


def init(repo_root) -> None:
    """Initialize the SQLite database. Call once on boot after repo is ready.

    Idempotent — safe to call multiple times. Repo-ready implies logged-in,
    so this is also the natural point to materialize the clients.
    """
    from pathlib import Path
    ensure_clients()
    init_db(Path(repo_root))


# ── Public API (re-exported for convenience) ──
on_indexing_state = indexer.on_indexing_state
ensure_dataset = indexer.ensure_dataset
trigger = indexer.trigger
retry_failed = indexer.retry_failed
retry_one = indexer.retry_one
sync_with_server = indexer.sync_with_server
reconcile_disk = indexer.reconcile_disk
knowledge_summary = indexer.knowledge_summary
panel_rows = indexer.panel_rows
