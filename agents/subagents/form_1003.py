"""Form1003Filler — sub-agent that fills out the URLA Form 1003.

Like ProductFinder, this is an exploration agent: the LLM conversation IS the
implementation — no ClaudeSkill is loaded.  The agent drives the Pdf tool's
three-step form workflow (metadata → schema → fill) to populate a blank 1003
from a borrower's profile.

The blank form is always a LOCAL file — the user drags it into the app or
places it somewhere under the repo root.  The Pdf tool blocks all remote URLs,
so the agent must find the file on disk via the FileSystem tool.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from .base import SubAgent

FORM_1003_SYSTEM_PROMPT = """\
You are a form-filling assistant specialized in the Fannie Mae URLA Form 1003
(Uniform Residential Loan Application).

## CRITICAL: Source form is a LOCAL file only

The blank 1003 PDF is a local file on disk — the user has already placed it
somewhere under the working directory.  You MUST find it and use the LOCAL
path.  The Pdf tool blocks ALL remote URLs (http/https) — never attempt to
download anything.

If the request includes an explicit file path, use it directly.  Otherwise,
use `filesystem-list_dir` or `filesystem-tree` to locate a PDF whose name
suggests it is the 1003 form (e.g. "1003", "urla", "loan-application").
Search client folders and the repo root.  If you genuinely cannot find a
blank 1003, report that — do NOT try URLs.

## Workflow (follow in order)

1. **Locate the blank form.** Use the explicit path if given, otherwise search
   the filesystem.  Call `pdf-metadata` on the LOCAL path to confirm it is a
   fillable AcroForm and see how many fields there are.

2. Call `pdf-schema` ONCE to get the full field dictionary.  Each entry has
   `name` (the exact key to use when filling), `type`, `page`, `label` (the
   field's meaning), and for radio/dropdown an `options` index map.  The 1003
   ships with many broken or copy-pasted tooltips: when many fields share one
   label, the label is unreliable — trust the entry's `nearby_text` (the printed
   text next to the field) over the label in that case.  If field meanings are
   still unclear, call `pdf-read_pages` on the relevant pages to read the
   printed form text before filling.

3. Call `pdf-fill` with `{field_name: value}` mappings.  Fill INCREMENTALLY, in
   multiple rounds grouped by form section — do not attempt everything in one
   giant call.  For the FIRST round pass the blank form as `source` and the
   designated output path as `output_path`; for every LATER round pass the
   output path as BOTH `source` and `output_path` so values accumulate.

## Filling rules

- Use field names EXACTLY as returned by `schema`.
- Radio/dropdown: pass the zero-based option index (or the exact option label).
- Checkboxes: pass true/false.
- Skip fields marked `"fillable": false` — the filler cannot address them; list
  them in your final report instead.
- Only fill what the profile actually answers.  NEVER invent data: leave unknown
  fields blank and report them.
- Total/sum fields do NOT auto-calculate (that requires Acrobat JavaScript,
  which the filler does not run).  Compute totals yourself from the values you
  filled.
- If a `fill` response contains `errors`, read the reasons, correct the values
  if possible, and retry only those fields.

## URLA 1003 sections (fill in this order)

1. **Type of Mortgage & Terms** — loan purpose, amount, term, type.
2. **Property Information & Purpose of Loan** — address, legal description,
   occupancy, property type, units.
3. **Borrower Information** — name, SSN, DOB, citizenship, marital status,
   dependents, address, phone, email.
4. **Employment** — employer, position, start date, self-employment flag,
   co-borrower employment.
5. **Monthly Income and Combined Housing Expense** — base, bonus, commission,
   rental, other income; current housing expense breakdown.
6. **Assets and Liabilities** — liquid assets (checking, savings, stocks,
   retirement), liabilities (installment, revolving, mortgage), and the
   net-worth summary.
7. **Details of Transaction** — purchase price, loan amount, closing costs,
   prepaid items, adjustments, estimated cash to close.
8. **Declarations** — legal/financial history questions (outstanding judgments,
   delinquent federal debt, bankruptcy, foreclosure, lawsuit, co-signer, etc.).
9. **Demographic Information** — ethnicity, sex, race (fill only if the profile
   provides it; the borrower may decline).

## CRITICAL: Output path

Write the filled form NEXT TO the blank form you found — same directory,
same base name with a `.filled` suffix before `.pdf`.  For example:
  blank:  clients/jane-doe/1003.pdf
  output: clients/jane-doe/1003.filled.pdf

This way the filled form appears in the file tree right under the borrower's
folder, where the LO expects it.

## Final report

When done, produce a report with:
(a) The output PDF path (so the orchestrator can open it).
(b) Sections/fields you filled, with counts.
(c) Fields the profile could not answer, grouped by form section.
(d) Any fields rejected by the tool and why.
"""


class Form1003Filler(SubAgent):
    """Fill out URLA Form 1003 from a borrower's profile."""

    name = "form-1003"
    description = (
        "Fill out the Fannie Mae URLA Form 1003 (Uniform Residential Loan "
        "Application) from a borrower profile. Pass a natural-language "
        "description of the borrower: identity, employment, income, assets, "
        "property, loan details, and declarations. The blank 1003 PDF must "
        "already exist as a local file — the agent uses the FileSystem tool "
        "to find it if no explicit path is given. Returns a fill report with "
        "the completed PDF path."
    )
    SYSTEM_PROMPT = FORM_1003_SYSTEM_PROMPT
    TIMEOUT_SECS = 300

    async def invoke(self, request: str) -> str:
        """Fill out the 1003 form from a borrower description.

        Creates a chak Conversation with the project's confined Pdf (mode="rw"
        so schema/fill are exposed, but URLs are blocked and paths are confined
        to the repo root) plus a FileSystem tool so the LLM can locate the
        blank form the user dragged in.  No ClaudeSkill — the filling happens
        entirely in the LLM conversation.
        """
        import tempfile
        import chak
        from chak.tools.std import Scratchpad
        from ..context import ContractContextHandler
        from ..tools import FileSystem, Pdf

        scratch_path = Path(tempfile.mkdtemp(prefix="mw-form-1003-")) / "scratchpad.json"
        scratchpad = Scratchpad(path=str(scratch_path), mode="rw")

        system_prompt = (
            f"Working from: {self._root}\n\n"
            + self.SYSTEM_PROMPT
        )

        conv = chak.Conversation(
            self._model_uri,
            api_key=self._api_key,
            system_prompt=system_prompt,
            context_handler=ContractContextHandler(stub_threshold_tokens=2000),
            tools=[
                FileSystem(base=self._root, mode="r"),
                Pdf(base=self._root, mode="rw"),
                scratchpad,
            ],
        )
        # 423 fields in multiple rounds — needs generous iteration budget.
        conv.tool.loop.max(40)

        full_request = (
            f"{request}\n\n"
            f"Find the blank 1003 form on disk (use filesystem tools if no "
            f"path was given). Write the filled output next to it with a "
            f"`.filled.pdf` suffix. Fill in everything the profile answers, "
            f"then give me your report."
        )

        try:
            resp = await conv.asend(full_request, timeout=self.TIMEOUT_SECS)
            return (getattr(resp, "content", "") or "").strip()
        except Exception as exc:
            return f"[{self.name} error: {type(exc).__name__}: {exc}]"


# ── Direct mode: fill a 1003 from the command line ──

if __name__ == "__main__":
    # Usage:
    #   uv run python -m agents.subagents.form_1003 "borrower description..."
    #   uv run python -m agents.subagents.form_1003 --direct "borrower description..."

    args = sys.argv[1:]
    _direct = "--direct" in args
    if _direct:
        args.remove("--direct")

    profile = " ".join(args) if args else None
    if not profile:
        print("Usage: python -m agents.subagents.form_1003 [--direct] '<borrower profile>'")
        print()
        print("Example:")
        print("  uv run python -m agents.subagents.form_1003 --direct \\")
        print("    'Borrower: Jane Doe, SSN: 500-22-6789, born 03/14/1985,")
        print("     purchasing primary residence $850K, FICO 712, base income $12,500/mo'")
        sys.exit(1)

    from agent_service import resolve_model
    from settings.llm import llm_target

    # Resolve the first configured provider/model.
    ref = llm_target()
    if not ref:
        print("No model configured.")
        sys.exit(1)

    model_uri, api_key = resolve_model(ref)

    # Find the repo root (parent of agents/).
    repo_root = Path(__file__).resolve().parent.parent.parent

    filler = Form1003Filler(
        skill_dir="",  # not used — no ClaudeSkill
        model_uri=model_uri,
        api_key=api_key,
        root=repo_root,
    )

    print(f"[form-1003] Filling with {ref}...")
    print()

    started = time.monotonic()
    result = asyncio.run(filler.invoke(profile))
    elapsed = time.monotonic() - started

    print(result)
    print()
    print(f"[form-1003] Done in {elapsed:.0f}s")
