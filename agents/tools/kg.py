"""Knowledge-graph locate + source-document verification tool.

Two-stage pipeline (the server-side ``/query`` answer engine is no longer
used):

1. ``locate`` — the graph resolves the question to candidate ``doc_ids``
   (coarse filter; NLQ-generated Cypher, no qualification server-side).
2. ``verify`` — each located doc_id is resolved to its local file via
   ``docindex`` (the work repo already holds the source documents, so no
   download step), and a dedicated LLM agent reads the source document to
   verify whether it actually supports the borrower scenario.

Fail-open like the server-side qualifier it mirrors (kg-service's
``kg/agents/matrix/qualify.py``): a document that cannot be read or verified
is reported as unverified, never silently dropped or falsely claimed.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from runtime_services import kg_target
from integration import KgClient

from .knowledge import KB, enabled_knowledge_bases

log = logging.getLogger(__name__)

# At most this many located documents are verified per call — locate can
# return a broad candidate set, and each verification reads a full document.
MAX_DOCS = 5
# Per-document verification budget; documents verify concurrently, so this
# bounds the verification stage as a whole. 150s proved too tight in
# practice — the agent needs several search/read cycles per matrix PDF.
QUALIFY_TIMEOUT = 300
QUALIFY_MAX_TOOL_TURNS = 20
# Evidence is free-form sub-agent prose — cap it so one chatty document
# cannot balloon the tool result the QA agent has to consume.
_MAX_EVIDENCE_CHARS = 800


class QualificationResult(BaseModel):
    """Structured verdict for one source document against the question."""

    verdict: Literal["PASS", "FAIL"]
    pages: list[int] = Field(default_factory=list)
    evidence: str = ""


_QUALIFIER_SYSTEM_PROMPT = """\
You are a mortgage product qualification specialist. Your job is to analyze
a guideline document and determine whether it supports a specific borrower
scenario described in a question.

## Process
1. Start with pdf-metadata to learn the document's size, then use pdf-search
   to find sections mentioning the borrower's loan type, income
   documentation method, or occupancy.
2. Check occupancy restrictions — some doc types or programs are only
   available for primary residence, not second home or investment.
3. Find the LTV/FICO/loan-amount grid for the matching occupancy + doc type.
4. Determine whether any tier in the grid supports ALL of the borrower's
   parameters simultaneously (LTV >= requested, FICO <= requested,
   amount >= requested).
5. Return PASS if a qualifying tier exists, FAIL otherwise.

## Tool usage
- When reading pages, always pass format="markdown". "text" is not a valid
  format, and "html" requires an extra dependency — if a read fails, retry
  once with format="markdown" and move on.
- Guideline PDFs are short (1-8 pages) — pdf-read_all is often faster than
  multiple pdf-search rounds.
- Be efficient: gather the needed sections, decide, and return your verdict.
  Do not re-read pages you already have.

## Rules
- A document FAILS if its guidelines explicitly restrict occupancy to
  "primary residence only" when the borrower wants a different occupancy.
- A document FAILS if no single tier supports all parameters simultaneously.
- A document PASSES when at least one tier matches all borrower criteria.
- When multiple tiers match, pick the one with the best (tightest) threshold
  the borrower still clears.
- If the document does not mention a constraint, treat it as satisfied
  (absence of a restriction is not a restriction).
- If the question asks for a specific value (e.g. "what is the maximum
  LTV?"), PASS means the document contains that answer; report the value in
  the evidence.
- Base the verdict only on what the document actually says. Record the page
  numbers of every section you relied on.
"""


def _ensure_docindex_loaded() -> None:
    """Same lazy load as tools/pdf.py — a KG call may be the first docindex
    consumer in this process."""
    import docindex
    if docindex.all_records():
        return
    from workrepo import local_repo_path
    try:
        docindex.init(local_repo_path())
    except Exception:
        pass


class KG:
    """Locate candidate documents in the knowledge graph, then verify the
    question against each document's source file."""

    name = "kg"
    description = (
        "Query the ingested mortgage underwriting matrix knowledge graph. "
        "Locates the guideline documents relevant to a structured product-"
        "matrix question, then reads and verifies each located source "
        "document to confirm whether it actually supports the borrower "
        "scenario. Use only for structured product-matrix questions over "
        "already-ingested and caller-visible documents: product fit, max "
        "LTV, loan amount, FICO, occupancy, purpose, geography, doc type, "
        "DSCR, DTI, cash-out, investor experience, housing history, and "
        "other underwriting constraints. This tool reads full documents and "
        "is SLOW (minutes) — ask one focused question per call. Do not use "
        "for general mortgage explanations, rates, calculations, raw PDF "
        "text search, non-ingested products, or final underwriting/legal "
        "advice."
    )

    def __init__(self, client: KgClient | None = None,
                 model_uri: str | None = None, api_key: str | None = None):
        """``model_uri``/``api_key`` drive the verification sub-agents and
        follow the owning agent's current session model; without them the
        tool degrades to locate-only. An injected ``client`` (tests) stays a
        single personal KB; the production path locates across every enabled
        knowledge base — personal plus read-only shared mounts, resolved per
        query (see _kbs) so settings changes reach live conversations."""
        self._client = client
        self._model_uri = model_uri
        self._api_key = api_key
        self._scope_doc_ids: list[str] | None = None

    def _kbs(self) -> list[tuple[KB, KgClient]]:
        """The enabled KBs, resolved per call — the owning QAAgent is cached
        per conversation and must not freeze the mount list at build time."""
        if self._client is not None:
            return [(KB(label="Personal", storage_id="", personal=True),
                     self._client)]
        url, key = kg_target()
        return [(kb, KgClient(url, key, kb.storage_id))
                for kb in enabled_knowledge_bases()]

    def __available__(self) -> frozenset[str]:
        """Expose only ``query`` to the LLM; ``set_scope`` stays internal.

        See tools/rag.py::RAG.__available__ for why this is required.
        """
        return frozenset({"query"})

    def set_scope(self, doc_ids: list[str] | None) -> None:
        """Set the hidden per-turn document boundary for graph queries."""
        self._scope_doc_ids = None if doc_ids is None else list(dict.fromkeys(doc_ids))

    async def query(self, question: str) -> str:
        """
        Query the ingested mortgage underwriting matrix knowledge graph.

        Locates the guideline documents relevant to the question, then reads
        each located source document and verifies whether it supports the
        borrower scenario — every returned verdict carries the evidence and
        page numbers it is based on.

        Use this tool only for structured mortgage product-matrix questions
        over already-ingested and caller-visible documents.

        Appropriate uses:
        - Determine which visible mortgage products may fit a borrower profile.
        - Query or compare product eligibility rules such as max LTV, loan amount,
          FICO, occupancy, loan purpose, geography, doc type, DSCR, DTI, cash-out,
          investor experience, housing history, and other underwriting constraints.
        - Ask about a named product's matrix rules or compare rules across visible
          products/lenders.

        Do NOT use this tool for:
        - General mortgage knowledge, definitions, or explanations.
        - Current rates, live lender availability, market data, credit scores, or
          non-ingested guideline updates.
        - Payment/APR/affordability calculations.
        - Raw PDF/HTML summarization or text search outside the structured graph.
        - Questions about products or lenders that are not known to be in the ingested
          document set.
        - Final underwriting, legal, financial, or compliance advice.

        This tool reads full source documents and is SLOW — it can take
        minutes. Ask one focused question per call and wait for the result.

        Selected lender/document scopes are applied automatically by the app.
        Do not ask the user for document IDs, and do not mention internal IDs.
        If selected materials exist but none are indexed, the tool returns no records.

        Good examples:
        - "Which visible products allow 760 FICO, 80% LTV, $1.2M loan amount,
           primary residence, purchase?"
        - "What is the max LTV for Fast and Easy Doc with 760 FICO?"
        - "Does this product allow cash-out for investment property?"

        Treat documents marked "not verified" as unconfirmed — their verdict
        is unknown, not positive. Treat empty results as "not found in the
        currently visible ingested KG data", not as proof that the rule or
        product does not exist.
        """
        question = (question or "").strip()
        if not question:
            log.warning("kg query called with an empty question")
            return "Please provide a concrete mortgage product or matrix question."
        kbs = self._kbs()
        if not kbs:
            return (
                "All knowledge bases are disabled in Settings → Knowledge, so "
                "no graph query is available."
            )
        if self._scope_doc_ids == [] and all(kb.personal for kb, _ in kbs):
            return "The knowledge graph has no indexed records for the selected materials."

        # ── Stage 1: locate across every enabled KB ──
        # The scope is the caller's own-materials boundary — it can only ever
        # contain personal doc_ids, so mounts locate unfiltered. A mount's
        # doc_ids resolve to files in THIS workspace when the same document
        # happens to live here too; otherwise they land in "unresolved" and
        # are reported honestly (fail-open, never silently dropped).
        t0 = asyncio.get_event_loop().time()
        # Fan out locate calls concurrently — a slow or dead mount must not
        # serialize into the turn's latency. Outcomes keep job order so the
        # personal-first precedence below is unchanged.
        jobs = [(kb, client, self._scope_doc_ids if kb.personal else None)
                for kb, client in kbs
                if not (kb.personal and self._scope_doc_ids == [])]
        outcomes = await asyncio.gather(
            *(asyncio.to_thread(client.locate, question, scope)
              for _, client, scope in jobs),
            return_exceptions=True)
        doc_ids: list[str] = []
        for (kb, client, scope), outcome in zip(jobs, outcomes):
            if isinstance(outcome, Exception):
                if kb.personal:
                    log.warning("kg locate error after %.1fs · %r · %s: %s",
                                asyncio.get_event_loop().time() - t0,
                                question[:100], type(outcome).__name__, outcome)
                    if len(kbs) == 1:
                        return (
                            f"Knowledge graph service is temporarily unavailable: "
                            f"{type(outcome).__name__}: {outcome}\n\n"
                            "Do not infer structured product relationships from memory while "
                            "the graph is unavailable. Use guideline evidence if available."
                        )
                else:
                    # A dead mount must never break the turn — skip it quietly.
                    log.warning("shared kb %s locate failed: %s: %s",
                                kb.label, type(outcome).__name__, outcome)
                continue
            ids = self._parse_doc_ids(outcome.get("doc_ids"))
            # Defense in depth: the service already applies the ACL, but a
            # located id outside the caller-visible set must never reach a file.
            if kb.personal and self._scope_doc_ids is not None:
                allowed = set(self._scope_doc_ids)
                ids = [d for d in ids if d in allowed]
            doc_ids.extend(ids)
        doc_ids = list(dict.fromkeys(doc_ids))
        # The raw NLQ Cypher is for debugging only — never surface it to
        # the caller's LLM, which could parrot it into the answer.
        log.info("kg locate · %.1fs · %r · %d doc_id(s) across %d kb(s)",
                 asyncio.get_event_loop().time() - t0, question[:100],
                 len(doc_ids), len(kbs))
        if not doc_ids:
            log.info("kg locate · no documents · %r", question[:100])
            return "The knowledge graph located no relevant documents for this question."

        # ── Stage 2: resolve doc_ids → local source files, then verify ──
        resolved, unresolved = self._resolve_sources(doc_ids)
        truncated = 0
        if len(resolved) > MAX_DOCS:
            truncated = len(resolved) - MAX_DOCS
            resolved = resolved[:MAX_DOCS]

        if not self._model_uri:
            return self._format_locate_only(resolved, unresolved, truncated)

        results = await asyncio.gather(
            *(self._verify_one(doc_id, path, question) for doc_id, path in resolved)
        )
        return self._format_report(resolved, results, unresolved, truncated)

    # ── Locate helpers ──

    @staticmethod
    def _parse_doc_ids(raw: object) -> list[str]:
        """Normalize the located doc_ids — the service may return a list or a
        JSON-encoded string, and order/duplicates must be preserved sanely."""
        if isinstance(raw, str) and raw:
            try:
                import json
                parsed = json.loads(raw)
                raw = parsed if isinstance(parsed, list) else [raw]
            except (ValueError, TypeError):
                raw = [raw]
        if not isinstance(raw, list):
            return []
        return list(dict.fromkeys(str(d) for d in raw if d))

    @staticmethod
    def _resolve_sources(doc_ids: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
        """Map located doc_ids to local workspace files via docindex.

        Returns ``(resolved, unresolved)`` — resolved is ordered
        ``(doc_id, repo_relative_path)`` pairs (products/ copies preferred,
        since product guidelines live there), unresolved is doc_ids with no
        file on disk.
        """
        import docindex
        _ensure_docindex_loaded()

        resolved: list[tuple[str, str]] = []
        unresolved: list[str] = []
        for doc_id in doc_ids:
            records = docindex.lookup(doc_id)
            picks = sorted(
                records,
                key=lambda r: (
                    0 if r["path"].startswith("products/") else
                    1 if r["path"].startswith("clients/") else 2,
                    r["path"],
                ),
            )
            chosen = None
            for rec in picks:
                abs_path = rec.get("abs_path") or ""
                if abs_path and Path(abs_path).is_file():
                    chosen = rec["path"]
                    break
            if chosen:
                resolved.append((doc_id, chosen))
            else:
                unresolved.append(doc_id)
        return resolved, unresolved

    # ── Verification ──

    async def _verify_one(self, doc_id: str, path: str,
                          question: str) -> QualificationResult | None:
        """Run one verification agent over a single source document.

        Returns None on any failure (timeout, model error, invalid output) —
        callers report that as "not verified", fail-open.
        """
        import chak
        from workrepo import local_repo_path
        from .filesystem import FileSystem
        from .pdf import Pdf
        from .reader import Reader

        root = local_repo_path()
        conv = chak.Conversation(
            self._model_uri,
            api_key=self._api_key,
            system_prompt=_QUALIFIER_SYSTEM_PROMPT,
            tools=[
                FileSystem(base=root, mode="r"),
                Pdf(base=root),
                Reader(base=root, vision=self._model_uri,
                       vision_api_key=self._api_key),
            ],
        )
        conv.tool.loop.max(QUALIFY_MAX_TOOL_TURNS)

        prompt = (
            f"Borrower question: {question}\n\n"
            f"Source document: {path}\n\n"
            "Analyze the source document and determine whether it supports "
            "the scenario described in the question. Search for the relevant "
            "sections (income documentation, occupancy restrictions, "
            "LTV/FICO/loan-amount grids) and verify whether any tier "
            "satisfies all of the question's criteria simultaneously. If the "
            "question asks for a specific value, find it in the document and "
            "report it with its page. Record the pages you relied on."
        )
        try:
            result = await asyncio.wait_for(
                conv.asend(prompt, returns=QualificationResult),
                timeout=QUALIFY_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.warning("kg verify timed out · %s · %ss", path, QUALIFY_TIMEOUT)
            return None
        except Exception:
            log.warning("kg verify failed · %s", path, exc_info=True)
            return None
        if result is not None:
            result.evidence = (result.evidence or "").strip()
        return result

    # ── Output formatting ──

    @staticmethod
    def _citations(doc_id: str, pages: list[int]) -> str:
        links = [f"[[{p}]](mai://{doc_id}/{p})" for p in pages]
        return ", ".join(links)

    def _format_locate_only(self, resolved: list[tuple[str, str]],
                            unresolved: list[str], truncated: int) -> str:
        """Degraded mode: no model configured, so only the locate half ran."""
        parts = [
            "The knowledge graph located the following relevant documents "
            "(verification was skipped — no model configured for it):"
        ]
        parts.extend(f"- {path}" for _doc_id, path in resolved)
        if unresolved:
            parts.append(
                "Located in the graph but not present in the local workspace: "
                + ", ".join(unresolved)
            )
        if truncated:
            parts.append(f"({truncated} more located document(s) were not listed.)")
        return "\n\n".join(parts)

    @staticmethod
    def _truncate(text: str) -> str:
        if len(text) <= _MAX_EVIDENCE_CHARS:
            return text
        return text[:_MAX_EVIDENCE_CHARS].rstrip() + " …(truncated)"

    def _format_report(self, resolved: list[tuple[str, str]],
                       results: list[QualificationResult | None],
                       unresolved: list[str], truncated: int) -> str:
        # One block per document; PASS blocks lead so the consuming LLM sees
        # the usable products first.  FAIL details are deliberately withheld —
        # a ruled-out document is unusable anyway, so its evidence only burns
        # caller context; a one-line path list still tells the caller it was
        # checked and failed, so nobody re-verifies it.
        passed: list[str] = []
        ruled_out: list[str] = []
        unverified: list[str] = []
        for (doc_id, path), result in zip(resolved, results):
            if result is None:
                unverified.append(
                    f"- {path}: verification did not complete — treat its "
                    "answer as unconfirmed, not positive."
                )
                continue
            if result.verdict != "PASS":
                ruled_out.append(path)
                continue
            block = [f"[{path}] Verdict: PASS"]
            if result.evidence:
                block.append("Evidence: " + self._truncate(result.evidence))
            if result.pages:
                block.append(f"Citations: {self._citations(doc_id, result.pages)}")
            passed.append("\n".join(block))

        parts = [
            f"Knowledge graph located {len(resolved) + len(unresolved)} relevant "
            f"document(s) for this question: {len(passed)} PASS"
            + (f", {len(ruled_out)} ruled out" if ruled_out else "")
            + (f", {len(unverified)} unverified." if unverified else ".")
        ]
        if passed:
            parts.append("Verified PASS:\n\n" + "\n\n".join(passed))
        if ruled_out:
            parts.append(
                "Checked and ruled out (guidelines do not support this "
                "scenario, no further detail): " + ", ".join(ruled_out)
            )
        if unverified:
            parts.append("Not verified:\n" + "\n".join(unverified))
        if unresolved:
            parts.append(
                "Located in the graph but not present in the local workspace "
                "(cannot be verified): " + ", ".join(unresolved)
            )
        if truncated:
            parts.append(
                f"({truncated} more located document(s) were skipped to keep "
                "verification bounded.)"
            )
        if not passed and not ruled_out and not unverified and not unresolved:
            parts.append("No documents could be located or verified for this question.")
        return "\n\n".join(parts)
