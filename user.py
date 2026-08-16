"""Mock user service — single source of identity for the entire app.

Today: ``fetch_user()`` reads ``USER_ID`` / ``USER_NAME`` / ``WORK_REPO_URL``
from ``.env`` (loaded into ``os.environ`` by ``config.py``). Tomorrow: the same
function calls a real ``/auth/me`` endpoint, and nothing else in the codebase
changes — consumers always go through ``current_user()``, never through
``os.environ`` or ``SERVICES`` directly.

Architecture
------------
::

    app boot → user.fetch_user()  →  User(id, name, work_repo_url)
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
              rag_dataset_id       kg_graph_name         git identity
              (Qdrant collection)  (FalkorDB graph)      (name/email)

Both ``rag_dataset_id`` and ``kg_graph_name`` resolve to ``user_id``, so no
mapping table is ever needed — any code that knows the user can derive its
storage identifiers. Kept as properties on ``User`` so the naming convention
can change in one place.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """The currently authenticated user.

    Identity fields come from the (mock) auth service; the derived properties
    are computed from ``id`` so RAG/KG naming stays consistent without a
    separate convention table.
    """

    id: str
    name: str
    work_repo_url: str

    # ── Derived storage identifiers ──

    @property
    def rag_dataset_id(self) -> str:
        """Qdrant collection name for this user's vector data."""
        return self.id

    @property
    def kg_graph_name(self) -> str:
        """FalkorDB graph name for this user's knowledge graph."""
        return self.id

    @property
    def git_email(self) -> str:
        """Synthetic email for git commits (user_id@mortgagework.local)."""
        return f"{self.id}@mortgagework.local"


# ── Singleton ──

_current_user: User | None = None


def fetch_user() -> User:
    """Resolve the current user and cache it.

    **Mock implementation** — returns a hardcoded user. When a real auth
    service lands, replace the body with an HTTP call to ``/auth/me`` (or
    equivalent). The return type and the rest of the app stay unchanged.
    """
    global _current_user
    _current_user = User(
        id="zhixiang",
        name="Zhixiang Xue",
        # HTTPS, not SSH: demo machines won't have a deploy key for
        # git@github.com, and public repos clone fine over https without one.
        # International build:
        # work_repo_url="https://github.com/zhixiangxue/nmls-10293847.git",
        # China build (Codeup — GitHub is unreliable there). Codeup has no
        # anonymous access, so the URL carries a read/write personal access
        # token (user "oauth2" is a placeholder the server accepts). This
        # token ships in the demo distribution on purpose; rotate/revoke it
        # in Codeup → 个人设置 → 个人访问令牌 when per-user repos land.
        work_repo_url="https://oauth2:pt-JFpIeGam8Jqk5yScs0X64fw2_a2632667-e441-4317-b793-d452d96f9c92@codeup.aliyun.com/67a992d4136b5e5abf900e50/zhixiangxue/nmls-10293847.git",
    )
    return _current_user


def current_user() -> User:
    """Return the cached current user, fetching on first access if needed.

    Safe to call from any module at any time — viewers (separate processes),
    background threads, the main app. The first call in each process triggers
    ``fetch_user()``; subsequent calls return the cached instance.
    """
    if _current_user is None:
        return fetch_user()
    return _current_user
