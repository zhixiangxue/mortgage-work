"""Knowledge-graph query tool for Mortgage QA agents."""
from __future__ import annotations

import json
from typing import Any

from config import SERVICES
from integration import KgClient
from user import current_user


class KG:
    """Ask structured questions against the mortgage product knowledge graph."""

    name = "kg"
    description = (
        "Query the ingested mortgage underwriting matrix knowledge graph. Use "
        "only for structured product-matrix questions over already-ingested and "
        "caller-visible documents: product fit, max LTV, loan amount, FICO, "
        "occupancy, purpose, geography, doc type, DSCR, DTI, cash-out, investor "
        "experience, housing history, and other underwriting constraints. Do not "
        "use for general mortgage explanations, rates, calculations, raw PDF text "
        "search, non-ingested products, or final underwriting/legal advice."
    )

    def __init__(self, client: KgClient | None = None, max_records: int = 20):
        if client is None:
            user = current_user()
            client = KgClient(
                SERVICES.kg_service_url,
                SERVICES.kg_api_key,
                user.kg_graph_name,
            )
        self._client = client
        self._max_records = max_records
        self._scope_doc_ids: list[str] | None = None

    def __available__(self) -> frozenset[str]:
        """Expose only ``query`` to the LLM; ``set_scope`` stays internal.

        See tools/rag.py::RAG.__available__ for why this is required.
        """
        return frozenset({"query"})

    def set_scope(self, doc_ids: list[str] | None) -> None:
        """Set the hidden per-turn document boundary for graph queries."""
        self._scope_doc_ids = None if doc_ids is None else list(dict.fromkeys(doc_ids))

    def query(self, question: str) -> str:
        """
        Query the ingested mortgage underwriting matrix knowledge graph.

        Use this tool only for structured mortgage product-matrix questions over
        already-ingested and caller-visible documents.

        Appropriate uses:
        - Determine which visible mortgage products may fit a borrower profile.
        - Query or compare product eligibility rules such as max LTV, loan amount,
          FICO, occupancy, loan purpose, geography, doc type, DSCR, DTI, cash-out,
          investor experience, housing history, and other underwriting constraints.
        - Ask about a named product's matrix rules or compare rules across visible
          products/lenders.
        - Retrieve structured product metadata and source-backed eligibility records.

        Do NOT use this tool for:
        - General mortgage knowledge, definitions, or explanations.
        - Current rates, live lender availability, market data, credit scores, or
          non-ingested guideline updates.
        - Payment/APR/affordability calculations.
        - Raw PDF/HTML summarization or text search outside the structured graph.
        - Questions about products or lenders that are not known to be in the ingested
          document set.
        - Final underwriting, legal, financial, or compliance advice.

        Selected lender/document scopes are applied automatically by the app.
        Do not ask the user for document IDs, and do not mention internal IDs.
        If selected materials exist but none are indexed, the tool returns no records.

        Good examples:
        - "Which visible products allow 760 FICO, 80% LTV, $1.2M loan amount,
           primary residence, purchase?"
        - "What is the max LTV for Fast and Easy Doc with 760 FICO?"
        - "Compare DSCR requirements across the visible products."
        - "Does this product allow cash-out for investment property?"

        Treat empty results as "not found in the currently visible ingested KG data",
        not as proof that the rule or product does not exist. Prefer structured
        records for grounding, and use any returned prompt_context to interpret matrix
        eligibility logic.
        """
        question = (question or "").strip()
        if not question:
            return "Please provide a concrete mortgage product or matrix question."
        if self._scope_doc_ids == []:
            return "The knowledge graph has no indexed records for the selected materials."
        try:
            data = self._client.query(question, doc_ids=self._scope_doc_ids)
        except Exception as exc:  # noqa: BLE001 - tool output must degrade gracefully
            return (
                f"Knowledge graph service is temporarily unavailable: "
                f"{type(exc).__name__}: {exc}\n\n"
                "Do not infer structured product relationships from memory while "
                "the graph is unavailable. Use guideline evidence if available."
            )
        return self._format_response(data)

    def _format_response(self, data: dict[str, Any]) -> str:
        if not data:
            return "The knowledge graph returned no structured answer or records."
        answer = str(data.get("answer") or "").strip()
        statement = str(data.get("statement") or "").strip()
        prompt_context = str(data.get("prompt_context") or "").strip()
        records = data.get("records") or []

        parts: list[str] = []
        if answer:
            parts.append("Answer:\n" + answer)
        if records:
            shown = records[:self._max_records] if isinstance(records, list) else records
            parts.append(
                "Structured records:\n"
                + json.dumps(shown, ensure_ascii=False, indent=2, default=str)
            )
            if isinstance(records, list) and len(records) > self._max_records:
                parts.append(f"Records truncated: showing {self._max_records} of {len(records)}.")
        if prompt_context:
            parts.append("Context used by graph engine:\n" + prompt_context)
        if statement:
            parts.append("Generated graph statement:\n" + statement)
        return "\n\n".join(parts) if parts else "The knowledge graph returned no usable content."
