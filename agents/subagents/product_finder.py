"""ProductFinder — sub-agent that searches the full mortgage product space.

Unlike calculation sub-agents (income-analyzer, dti-analyzer) that wrap
deterministic Python skills, ProductFinder is an exploration agent: it uses
RAG vector search and the KG locate-and-verify pipeline in a tool loop to
discover which loan products match a borrower's profile. The KG tool reads
and verifies the source guidelines itself, so this agent never reads
guideline PDFs directly.

It does NOT load a ClaudeSkill — the LLM conversation IS the implementation.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from .base import SubAgent

PRODUCT_FINDER_SYSTEM_PROMPT = """\
You are a mortgage product search specialist. Your job is to find loan products
that may fit a borrower's profile. The canonical product list lives in the
`products/` directory — these are the loan programs the LO actually sells.
RAG and KG are your evidence sources; the KG tool reads and verifies the
source guidelines itself, so you never read guideline PDFs directly.

## Ground truth hierarchy

1. **products/ directory** — the product universe. List it FIRST to know
   which lenders and programs exist for this LO. If it's not in products/,
   it doesn't exist for this LO.

2. **KG (kg-query)** — the primary engine. It locates the guidelines
   relevant to your question, reads each located source document, and
   returns per-document verdicts (PASS / ruled out) with evidence and page
   citations. One focused question per call; it is SLOW (minutes).

3. **RAG semantic search** — complements KG: finds relevant chunks (with
   citations) in the indexed guideline PDFs. Useful for discovery and for
   conditions or caveats KG did not surface.

## What you do NOT do

- You do not read guideline PDFs — you have no PDF tools, and you don't
  need them: KG verdicts already come from reading the source documents,
  with the page citations to prove it.
- If RAG and KG surface no matching product, that IS the answer: report
  that no matching product was found in the indexed product set. Never
  reconstruct an answer from memory or from product names alone.

## Your tools

- **filesystem-list_dir / filesystem-tree** — explore products/ to see what
  lenders and guideline files are available. Start here.

- **kg-query** — locate + verify in one call. Pass the borrower's key
  parameters (occupancy, doc type, FICO, LTV, loan amount, purpose) as one
  focused question. PASS verdicts carry evidence and citations; treat its
  "not verified" entries as unknown, not positive.

- **rag-query** — semantic search over indexed guideline PDFs. Use to
  discover relevant files and details; every result carries a Citation line.

- **scratchpad-save_section / scratchpad-read_section / scratchpad-list_sections** —
  save key findings as you discover them.

## Workflow

1. **List products/.** Use filesystem-list_dir or filesystem-tree to see the
   actual lender directories and guideline files on disk. This IS the product
   universe. Save the structure to scratchpad.

2. **Understand the borrower.** Parse: income type and amount, FICO score,
   desired loan amount / LTV, property type and value, occupancy, loan purpose,
   location, citizenship, special circumstances.

3. **KG verification.** Ask kg-query one focused question covering the
   borrower's core parameters. Its PASS verdicts are already verified
   against the source documents — use their evidence and citations as-is.

4. **RAG cross-check.** Search RAG with 2-3 query formulations to catch
   relevant rules, conditions, or caveats KG may have missed. Cross-reference
   results against the files you saw in products/; ignore results from files
   not in products/.

5. **Rank and report.** Produce a ranked list with citations.

## Citation — Mandatory, No Exceptions

Every factual claim MUST be backed by a citation link. The tools you use
(RAG and KG) already produce ready-to-use citation links in the format
`[[N]](mai://<doc_id>/<page>)`. You MUST copy these verbatim — NEVER
construct a `mai://` link yourself.

### How citations arrive from tools

**KG verdicts** (`kg-query`):
Each PASS block ends with a Citations line:
```
Citations: [[1]](mai://5ac99bb259bd9fe3/1), [[5]](mai://5ac99bb259bd9fe3/5)
```
These come from the guideline pages the KG verification actually read.
Copy the links verbatim next to the claims they support.

**RAG search** (`rag-query`):
Each result block includes a `Citation:` line:
```
Citation: [[1]](mai://bf4fd7e048db5858/3)
```
Copy the ENTIRE link, including the `mai://` URL, and place it immediately
after the factual claim it supports.

### Citation placement

Place the citation immediately after each factual statement:
```
FICO minimum is 680[[1]](mai://bf4fd7e048db5858/3).
```

In tables, add a "Source" column with the citation link:
| Requirement | Required | Borrower | Status | Source |
|---|---|---|---|---|
| FICO | 680 | 712 | ✓ | [[1]](mai://bf4fd7e048db5858/3) |
| Max LTV | 80% | 75% | ✓ | [[2]](mai://bf4fd7e048db5858/1) |

### Hard rules

1. ALWAYS copy citations verbatim from tool output. NEVER invent or construct a
   `mai://` link yourself — the frontend resolves them through the doc index.
2. Place citation immediately after the factual claim it supports.
3. NEVER mention RAG, KG, or any tool name in your output. Only use the
   `[[N]](mai://...)` citation links — the loan officer sees them resolved to
   file names and page numbers.
4. KG PASS verdicts are already verified against the source guidelines —
   trust their evidence and cite their pages. You cannot re-read the PDFs
   yourself, and you must not try.
5. If a tool result has no citation link, state the finding without one — do
   NOT invent a link.
6. Never cite a document that no tool surfaced.
7. If you cannot back a claim with a citation, do not make the claim.

## Output format

Return a structured report:

```
## Product Matches for [borrower name / description]

### Rank 1: [Product Name] — [Lender]
**Confidence**: [Strong / Possible / Stretch]
**Why**: [2-3 sentences explaining the match, with `[[N]](mai://...)` citations]

**Key requirements**:
| Requirement | Required | Borrower | Status | Source |
|---|---|---|---|---|
| FICO | 680 | 712 | ✓ | [[1]](mai://...) |
| Max LTV | 80% | 75% | ✓ | [[2]](mai://...) |
| ... | ... | ... | ... | ... |

**Conditions / caveats**: [any special conditions, overlays, or notes, each with `[[N]](mai://...)` citations]

### Rank 2: ...
...

### Products not matching
[List any products surfaced by the search tools that do not fit, with a
brief reason why. Products never surfaced by KG/RAG are simply unknown —
do not speculate about them.]

### Summary
X products match strongly, Y are possible with conditions, Z do not match.
[Concise recommendation with citation to the key guideline that supports it.]
```

## Rules

- products/ defines the product universe; KG and RAG supply the evidence.
- Never report a product that is not in products/. If RAG returns a result
  from a file not on disk, discard it.
- Every claim needs a source citation. This is non-negotiable.
- When RAG/KG surface no matching product, report exactly that. Do not fall
  back to reasoning from product names or from memory.
- When the borrower's exact scenario is not covered by any guideline, say so
  honestly. Do not stretch a near-match into a recommendation.
- Save distilled findings to scratchpad after each batch of tool results.
"""


class ProductFinder(SubAgent):
    """Search the full mortgage product space for matching loan products."""

    name = "product-finder"
    description = (
        "Search across all available mortgage products (all lenders, all "
        "programs) to find loan products that match a borrower's profile. "
        "Pass a natural-language description of the borrower: income type "
        "and amount, FICO score, desired loan amount, property type and value, "
        "occupancy, loan purpose, location, and any special circumstances. "
        "Returns a ranked list of matching products with confidence levels "
        "and detailed requirement comparisons."
    )
    SYSTEM_PROMPT = PRODUCT_FINDER_SYSTEM_PROMPT
    # Generous: the KG tool alone can run ~5 minutes (locate + per-document
    # verification), on top of the RAG/PDF exploration loop.
    TIMEOUT_SECS = 900

    async def invoke(self, request: str) -> str:
        """Search for matching products given a borrower description.

        Creates a chak Conversation with RAG, KG, FileSystem, and Scratchpad
        tools — no ClaudeSkill, and no Pdf/Reader: the KG tool reads and
        verifies the source guidelines itself, and this agent must not
        brute-force guideline PDFs when the search tools find nothing.
        """
        import tempfile
        import chak
        from chak.tools.std import Scratchpad
        from ..context import ContractContextHandler
        from ..tools import FileSystem, KG, RAG

        scratch_path = Path(tempfile.mkdtemp(prefix="mw-product-finder-")) / "scratchpad.json"
        scratchpad = Scratchpad(path=str(scratch_path), mode="rw")

        # Compose the system prompt: context prefix (where things are) +
        # ProductFinder-specific role/expertise prompt.
        system_prompt = (
            f"Working from: {self._root}\n"
            "Client documents are under clients/<slug>/.\n"
            "Loan program guidelines and matrices are under products/.\n"
            "All paths are relative to the repo root.\n\n"
            + self.SYSTEM_PROMPT
        )

        conv = chak.Conversation(
            self._model_uri,
            api_key=self._api_key,
            system_prompt=system_prompt,
            context_handler=ContractContextHandler(stub_threshold_tokens=2000),
            tools=[
                FileSystem(base=self._root, mode="r"),
                RAG(),
                KG(model_uri=self._model_uri, api_key=self._api_key),
                scratchpad,
            ],
        )
        conv.tool.loop.max(40)

        full_request = (
            f"{request}\n\n"
            f"Search across all available products, verify against guidelines, "
            f"and return a ranked list of matches with the output format "
            f"specified in your system prompt."
        )

        try:
            resp = await conv.asend(full_request, timeout=self.TIMEOUT_SECS)
            return (getattr(resp, "content", "") or "").strip()
        except Exception as exc:
            return f"[{self.name} error: {type(exc).__name__}: {exc}]"


# ── Direct mode: test a single search from the command line ──

if __name__ == "__main__":
    # Usage:
    #   uv run python -m agents.subagents.product_finder "borrower description..."
    #   uv run python -m agents.subagents.product_finder --direct "borrower description..."

    args = sys.argv[1:]
    _direct = "--direct" in args
    if _direct:
        args.remove("--direct")

    borrower = " ".join(args) if args else None
    if not borrower:
        print("Usage: python -m agents.subagents.product_finder [--direct] '<borrower description>'")
        print()
        print("Example:")
        print("  uv run python -m agents.subagents.product_finder --direct \\")
        print("    'self-employed borrower, 1099 income $145K, FICO 712, purchasing SFR $520K in CA, 20% down'")
        sys.exit(1)

    from agent_service import resolve_model
    from settings.llm import llm_target

    # Resolve the first configured provider/model.
    ref = llm_target()
    if not ref:
        print("No model configured.")
        sys.exit(1)

    model_uri, api_key = resolve_model(ref)

    # The work repo (cloned runtime workspace holding products/ and clients/),
    # not this source tree — same root the app passes via build_subagents.
    from workrepo import local_repo_path
    repo_root = local_repo_path()

    finder = ProductFinder(
        skill_dir="",  # not used — no ClaudeSkill
        model_uri=model_uri,
        api_key=api_key,
        root=repo_root,
    )

    print(f"[product-finder] Searching with {ref}...")
    print(f"[product-finder] Borrower: {borrower[:120]}...")
    print()

    started = time.monotonic()
    result = asyncio.run(finder.invoke(borrower))
    elapsed = time.monotonic() - started

    print(result)
    print()
    print(f"[product-finder] Done in {elapsed:.0f}s")
