"""RAG query tool for Mortgage QA agents.

Queries every enabled knowledge base in one call: the user's personal KB
plus any shared mounts (other accounts, read-only — see ``knowledge.py``).
Personal results lead; each mount contributes its own labelled section.
The per-turn document scope filters the personal KB only — a caller-visible
boundary can never contain someone else's documents.
"""
from __future__ import annotations

import logging
from typing import Any

from config import SERVICES
from integration import RagClient
from utils.locate import locate_pdf_page

from .knowledge import KB, enabled_knowledge_bases

log = logging.getLogger(__name__)


def _no_result_message() -> str:
    return (
        "No directly relevant guideline evidence was found in the vector search.\n\n"
        "Important: this is a sampling-based search result. Do not invent or "
        "substitute general industry practice. If the final answer depends on a "
        "specific lender, agency, or guideline rule, say that the available "
        "materials did not surface a clear rule."
    )


def _no_kb_message() -> str:
    return (
        "All knowledge bases are disabled in Settings → Knowledge, so no "
        "guideline search is available. Answer only conceptual questions and "
        "say that knowledge search is turned off."
    )


def _tool_error_message(err: Exception) -> str:
    return (
        f"Guideline search service is temporarily unavailable: {type(err).__name__}: {err}\n\n"
        "Do not guess any mortgage guideline or eligibility rule while the "
        "knowledge service is unavailable. You may answer only conceptual "
        "questions that do not require a specific lender, agency, or guideline source."
    )


class RAG:
    """Search mortgage guidelines and lender program documents for evidence."""

    name = "rag"
    description = (
        "Search mortgage guidelines, agency rules, lender overlays, product "
        "matrices, and program documents. Use before making eligibility or "
        "guideline claims. Returns evidence chunks with source details and citations."
    )

    def __init__(self, client: RagClient | None = None, top_k: int = 15):
        # An injected client (tests) stays a single anonymous personal KB;
        # the production path resolves the full enabled list per construction.
        if client is not None:
            self._kbs: list[tuple[KB, RagClient]] = [
                (KB(label="Personal", storage_id="", personal=True), client)
            ]
        else:
            self._kbs = [
                (kb, RagClient(SERVICES.rag_service_url,
                               SERVICES.rag_api_key, kb.storage_id))
                for kb in enabled_knowledge_bases()
            ]
        self._top_k = top_k
        self._scope_doc_ids: list[str] | None = None

    def __available__(self) -> frozenset[str]:
        """Expose only ``query`` to the LLM.

        ``set_scope`` is an internal control agents/qa.py uses to install the
        hidden per-turn document boundary — chak's NativeObjectTool discovers
        every public method by default, so without this it would show up as
        a callable ``rag-set_scope`` tool the model could invoke itself
        (with a made-up doc_id, since it never sees real ones).
        """
        return frozenset({"query"})

    def set_scope(self, doc_ids: list[str] | None) -> None:
        """Set the hidden per-turn document boundary for retrieval.

        ``None`` means no explicit boundary. An empty list is a real boundary
        with no indexed documents and should return no personal evidence —
        shared mounts are outside the boundary by definition and still answer.
        """
        self._scope_doc_ids = None if doc_ids is None else list(dict.fromkeys(doc_ids))

    def _filters(self) -> dict:
        if self._scope_doc_ids is None:
            return {}
        if not self._scope_doc_ids:
            return {"doc_id": {"$in": []}}
        if len(self._scope_doc_ids) == 1:
            return {"doc_id": self._scope_doc_ids[0]}
        return {"doc_id": {"$in": self._scope_doc_ids}}

    def query(self, question: str) -> str:
        """Search mortgage knowledge for evidence relevant to a question.

        Args:
            question: A complete English search question about mortgage
                guidelines, lender programs, overlays, eligibility, or matrices.

        Returns:
            Evidence chunks with document/source metadata and citations. If no
            evidence is found, returns an explicit no-evidence instruction.
        """
        question = (question or "").strip()
        if not question:
            return "Please provide a concrete mortgage guideline question to search."
        if not self._kbs:
            return _no_kb_message()
        # Empty boundary with nothing mounted: the precise "selected
        # materials" wording beats a generic no-evidence message.
        if self._scope_doc_ids == [] and all(kb.personal for kb, _ in self._kbs):
            return (
                "No indexed documents were found in the selected materials. "
                "Answer only if the user provided enough information outside the knowledge search."
            )

        sections: list[str] = []
        visible_index = 1
        for kb, client in self._kbs:
            # The scope is the caller's own-materials boundary — it can only
            # ever contain personal doc_ids, so mounts query unfiltered.
            if kb.personal and self._scope_doc_ids == []:
                continue  # empty boundary: the personal side has nothing to give
            filters = self._filters() if kb.personal else {}
            try:
                results = client.query(question, top_k=self._top_k, filters=filters)
            except Exception as exc:  # noqa: BLE001 - tool output must degrade gracefully
                if kb.personal:
                    sections.append(_tool_error_message(exc))
                else:
                    # A dead mount must never break the turn — skip it quietly.
                    log.warning("shared kb %s query failed: %s: %s",
                                kb.label, type(exc).__name__, exc)
                continue
            blocks, visible_index = self._format_results(results, visible_index)
            if not blocks:
                continue
            if kb.personal:
                sections.append(blocks)
            else:
                sections.append(
                    f"Results from shared knowledge base: {kb.label} (read-only)\n\n"
                    + blocks)
        return "\n\n---\n\n".join(sections) or _no_result_message()

    def _format_results(self, results: list[dict[str, Any]],
                        start_index: int = 1) -> tuple[str, int]:
        """Format one KB's hits; numbering continues across KB sections so
        citations stay unique within a merged answer."""
        parts: list[str] = []
        visible_index = start_index
        for item in results:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            metadata = item.get("metadata") or {}
            document = metadata.get("document") or {}
            custom = metadata.get("custom") or {}
            doc_id = str(item.get("doc_id") or "")
            unit_id = str(item.get("unit_id") or "")
            score = item.get("score")
            doc_name = (
                document.get("file_name")
                or document.get("name")
                or custom.get("file_name")
                or doc_id
                or "document"
            )
            source = self._source_label(custom, doc_name)
            page = locate_pdf_page(doc_id, content)
            citation = f"[[{visible_index}]](mai://{doc_id}/{page})" if doc_id and page else ""
            header = [f"[Result {visible_index}]", f"Source: {source}", f"Document: {doc_name}"]
            if doc_id:
                header.append(f"Document ID: {doc_id}")
            if page:
                header.append(f"Page: {page}")
            if score is not None:
                header.append(f"Score: {score}")
            if unit_id:
                header.append(f"Unit ID: {unit_id}")
            if citation:
                header.append(f"Citation: {citation}")
            parts.append("\n".join(header) + "\n\nContent:\n" + content)
            visible_index += 1
        return "\n\n---\n\n".join(parts), visible_index

    @staticmethod
    def _source_label(custom: dict[str, Any], fallback: str) -> str:
        lender = custom.get("lender") or custom.get("org_name")
        guideline = custom.get("guideline")
        if lender:
            return f"Lender's Program ({lender})"
        if guideline:
            return f"Agency Guideline ({guideline})"
        return fallback
