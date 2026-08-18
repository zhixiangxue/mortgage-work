"""User service — single source of identity for the entire app.

``current_user()`` resolves whoever logged in on this machine. The identity
comes from the auth service (``server/``): email-code login → the service
provisions the user's private work repo → the payload lands in the OS
keychain via ``auth.py``. A cold boot reads it back; nothing else in the
codebase talks to the auth service or the keychain directly.

Architecture
------------
::

    login (email code) → auth service → session payload → keychain
                                                              │
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

Logged-out machines: ``fetch_user()`` returns None and ``current_user()``
raises ``AuthError`` — the app boots anyway and shows the login screen; all
identity-needing paths (repo sync, indexing) are gated behind login.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import auth
import xxhash

log = logging.getLogger(__name__)


class AuthError(RuntimeError):
    """No user is logged in on this machine."""


def user_id_from_email(email: str) -> str:
    """Deterministic user id for an email: xxh64 of the canonical form.

    MUST stay in lockstep with ``_user_id`` in ``server/main.py`` — the auth
    service mints ids with the same formula. The app only needs the reverse
    direction to migrate legacy shared-KB entries, which older settings
    files addressed by email instead of knowledge-base ID.
    """
    return xxhash.xxh64((email or "").strip().lower().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class User:
    """The currently authenticated user.

    Identity fields come from the auth service's session payload; the derived
    properties are computed from ``id`` so RAG/KG naming stays consistent
    without a separate convention table.
    """

    id: str
    name: str
    work_repo_url: str
    email: str = ""
    region: str = ""

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
        """Email for git commits — the real one when known (it is, post-auth),
        synthetic only as a fallback."""
        return self.email or f"{self.id}@mortgagework.local"


# ── Singleton ──

_current_user: User | None = None


def _user_from_session(payload: dict) -> User:
    """Map the auth service's session payload onto our User shape."""
    u = payload.get("user", {})
    return User(
        id=u.get("id", ""),
        name=u.get("name", ""),
        # The service returns a clone-ready URL — credentials already
        # embedded where the host requires them (github/codeup), a plain
        # path for local pilot repos.
        work_repo_url=payload.get("work_repo_url", ""),
        email=u.get("email", ""),
        region=u.get("region", ""),
    )


def fetch_user() -> User | None:
    """Resolve the logged-in user from the stored session and cache it.

    Returns None (never raises) when this machine has never logged in — boot
    needs to reach the login screen with no identity at all.
    """
    global _current_user
    payload = auth.load_session()
    if not payload or not payload.get("work_repo_url"):
        _current_user = None
        return None
    _current_user = _user_from_session(payload)
    return _current_user


def apply_session(payload: dict) -> User:
    """Adopt a fresh login payload right after a successful verify — the app
    continues without a restart, and ``auth.save_session`` has already
    persisted it for the next boot."""
    global _current_user
    _current_user = _user_from_session(payload)
    log.info("logged in as %s (%s)", _current_user.name, _current_user.id)
    return _current_user


def clear() -> None:
    """Drop the in-memory identity (logout). The stored session is cleared
    separately via ``auth.clear_session``."""
    global _current_user
    _current_user = None


def is_logged_in() -> bool:
    """Cheap login check for boot gates — resolves the session on first call
    in this process, then answers from the cache."""
    if _current_user is None:
        fetch_user()
    return _current_user is not None


def current_user() -> User:
    """Return the cached current user, fetching on first access if needed.

    Safe to call from any module at any time — viewers (separate processes),
    background threads, the main app. The first call in each process triggers
    ``fetch_user()``; subsequent calls return the cached instance. Raises
    ``AuthError`` when nobody is logged in — call sites reachable before
    login must check ``is_logged_in()`` first.
    """
    if _current_user is None:
        fetch_user()
    if _current_user is None:
        raise AuthError("not logged in")
    return _current_user
