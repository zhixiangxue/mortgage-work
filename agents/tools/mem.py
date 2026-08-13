"""Memory search tool — lets agents recall facts from past conversations.

Read-only by design: writing happens automatically via the chat layer
(mem.note_turn), so agents can search what was already learned without
ever modifying the memory store.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Reach back to the project root so model_settings / workrepo are importable
# from the tool layer — same pattern as agents/mem.py, one extra parent dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from model_settings import embedding_target  # noqa: E402
from workrepo import SEEKA_DIR, RepoError, local_repo_path  # noqa: E402


class Mem:
    """Search conversation memories for client facts, corrections, and decisions."""

    name = "memory"
    description = (
        "Search the LO's conversation memories — facts, corrections, decisions, "
        "and preferences the LO shared in earlier conversations. Use this when "
        "you suspect the LO mentioned something relevant before that may not be "
        "on disk yet (e.g. a verbal correction, a strategy decision, a client "
        "detail that hasn't been written into the file)."
    )

    def __init__(self) -> None:
        self._mem = None

    # ── lazy init ───────────────────────────────────────────────────────────

    def _get_mem(self):
        """Construct a read-only seeka Memory handle from settings.yaml config.

        No LLM — this handle can recall but not dream.  The extraction model
        belongs to mem.py (the background agent); the tool layer only searches
        what was already learned.
        """
        if self._mem is not None:
            return self._mem
        try:
            repo_root = local_repo_path()
        except RepoError:
            return None
        embedder = embedding_target()
        if embedder is None:
            return None
        embedding_uri, embedding_key = embedder
        seeka_path = repo_root / SEEKA_DIR
        if not seeka_path.exists():
            return None  # nothing has been learned yet — not an error
        skill_path = str(
            Path(__file__).resolve().parent.parent / "skills" / "seeka"
        )
        from seeka import Memory
        self._mem = Memory(
            str(seeka_path),
            embedding_uri=embedding_uri,
            embedding_api_key=embedding_key,
            llm_uri=None,
            llm_api_key=None,
            skills=[skill_path],
        )
        return self._mem

    # ── the one method the model sees ───────────────────────────────────────

    async def recall(self, query: str) -> str:
        """Search conversation memories for relevant facts.

        Args:
            query: Natural-language search query. Be specific — name the client
                   if you know who you're asking about.

        Returns:
            Numbered list of matching memories with dates, or a message saying
            nothing was found.
        """
        mem = self._get_mem()
        if mem is None:
            return "Memory search is not available — no embedding provider configured."

        try:
            results = await mem.recall(query, n=10)
        except Exception:
            return "Memory search failed."

        if not results:
            return "No relevant conversation memories found for this query."

        lines = []
        for i, r in enumerate(results, 1):
            content = r.content
            ts = (r.metadata.get("ts") or "")[:10]
            suffix = f"  ({ts})" if ts else ""
            lines.append(f"{i}. {content}{suffix}")
        return "\n\n".join(lines)
