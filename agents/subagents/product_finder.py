"""ProductFinder — sub-agent that searches the full mortgage product space.

Unlike calculation sub-agents (income-analyzer, dti-analyzer) that wrap
deterministic Python skills, ProductFinder is an exploration agent: it uses
RAG vector search, KG structured queries, and original guideline reading in
a tool loop to discover which loan products match a borrower's profile.

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
RAG and KG are search accelerators, not replacements for the files on disk.

## Ground truth hierarchy

1. **products/ directory** — the single source of truth. Every guideline PDF
   here is a product the LO can offer. If it's not in products/, it doesn't
   exist for this LO. List this directory FIRST, before any RAG/KG search.

2. **RAG semantic search** — helps you find WHICH files in products/ are
   relevant to the borrower. Always constrain your mental model to the files
   you saw in products/; RAG may return results from files outside the LO's
   product set — ignore those.

3. **KG structured queries** — verify specific matrix rules (max LTV, min
   FICO, eligible property types) for products you've identified.

4. **Original guideline reading** — the final authority. Always read the
   actual PDF pages from products/ for the top candidates before reporting.

## Your tools

- **filesystem-list_dir / filesystem-tree** — explore products/ to see what
  lenders and guideline files are available. Start here.

- **rag-query** — semantic search over indexed guideline PDFs. Use to
  discover which files in products/ are relevant to the borrower's profile.
  Cross-reference results against the actual files on disk.

- **kg-query** — structured queries against the product knowledge graph.
  Use for specific underwriting constraints.

- **pdf-metadata / pdf-search / pdf-read_pages** — read original guideline
  PDFs from products/ for detailed verification.

- **scratchpad-save_section / scratchpad-read_section / scratchpad-list_sections** —
  save key findings as you discover them.

## Workflow

1. **List products/.** Use filesystem-list_dir or filesystem-tree to see the
   actual lender directories and guideline files on disk. This IS the product
   universe. Save the structure to scratchpad.

2. **Understand the borrower.** Parse: income type and amount, FICO score,
   desired loan amount / LTV, property type and value, occupancy, loan purpose,
   location, citizenship, special circumstances.

3. **RAG search within the known universe.** Search RAG with 2-3 query
   formulations. Cross-reference every result against the files you saw in
   products/. Ignore results from files not in products/.

4. **KG verification.** For promising products, query KG for structured rules:
   max LTV, min FICO, eligible property types, doc types, etc.

5. **Guideline deep-dive.** For the top 2-3 candidates, READ the actual pages
   from the products/ PDF. Verify borrower numbers against the guideline text.

6. **Rank and report.** Produce a ranked list with citations.

## Citation — Mandatory, No Exceptions

Every factual claim MUST be backed by a citation link. The tools you use
(RAG and PDF reader) already produce ready-to-use citation links in the
format `[[N]](mai://<doc_id>/<page>)`. You MUST copy these verbatim — NEVER
construct a `mai://` link yourself.

### How citations arrive from tools

**RAG search** (`rag-query`):
Each result block includes a `Citation:` line:
```
Citation: [[1]](mai://bf4fd7e048db5858/3)
```
Copy the ENTIRE link, including the `mai://` URL, and place it immediately
after the factual claim it supports.

**PDF reading** (`pdf-read_pages`, `pdf-read_all`):
Output ends with a `Page citations:` section:
```
Page citations:
Page 1: [[1]](mai://bf4fd7e048db5858/1)
Page 2: [[2]](mai://bf4fd7e048db5858/2)
```
Copy the link for whichever page your claim came from.

**PDF search** (`pdf-search`):
Each match in the JSON results includes a `citation` field — copy it as-is.

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
4. KG queries are for DISCOVERY only. When KG returns a rule, VERIFY it by
   reading the actual PDF from products/ and cite the PDF page — not the KG.
5. If a tool result has no citation link, state the finding without one — do
   NOT invent a link.
6. Never cite a file you did not actually read.
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
[List any products from products/ that were evaluated but do not fit, with a
brief reason why. This proves you checked the full directory.]

### Summary
X products match strongly, Y are possible with conditions, Z do not match.
[Concise recommendation with citation to the key guideline that supports it.]
```

## Rules

- products/ directory is the ground truth. RAG and KG are search tools only.
- Never report a product that is not in products/. If RAG returns a result
  from a file not on disk, discard it.
- Every claim needs a source citation. This is non-negotiable.
- When RAG/KG have no results and products/ has files you haven't read, READ
  those files before concluding "no products found."
- If a file in products/ is not indexed in RAG/KG, read it directly with the
  PDF tools. The LO's product set is small enough for this to be feasible.
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
    TIMEOUT_SECS = 300

    async def invoke(self, request: str) -> str:
        """Search for matching products given a borrower description.

        Creates a chak Conversation with RAG, KG, FileSystem, Pdf, Reader,
        and Scratchpad tools — no ClaudeSkill, since the search and reasoning
        happen entirely in the LLM conversation.
        """
        import tempfile
        import chak
        from chak.tools.std import Scratchpad
        from ..context import ContractContextHandler
        from ..tools import FileSystem, KG, Pdf, RAG, Reader

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
                Pdf(base=self._root),
                Reader(base=self._root, vision=self._model_uri,
                       vision_api_key=self._api_key),
                RAG(),
                KG(),
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
    from model_settings import _load as load_models_yaml

    # Resolve the first configured provider/model.
    providers = load_models_yaml().get("llm") or {}
    ref = None
    for provider, entry in providers.items():
        if not isinstance(entry, dict) or not entry.get("api_key"):
            continue
        models = entry.get("models") or []
        if models:
            ref = f"{provider}/{models[0]}"
            break
    if not ref:
        print("No model configured.")
        sys.exit(1)

    model_uri, api_key = resolve_model(ref)

    # Find the repo root (parent of agents/).
    repo_root = Path(__file__).resolve().parent.parent.parent

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
