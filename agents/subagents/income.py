"""IncomeAnalyzer — sub-agent wrapping the income-calc skill."""
from .base import SubAgent


class IncomeAnalyzer(SubAgent):
    """Analyze borrower income documents and calculate qualifying income."""

    name = "income-analyzer"
    description = (
        "Analyze borrower income documents (W-2, pay stubs, bank statements, "
        "tax returns) and calculate qualifying monthly income. Pass absolute "
        "file paths and the loan context (e.g. loan program, borrower type)."
    )
    SYSTEM_PROMPT = """\
You are an income analyst. Use the income-calc skill to read the provided
income documents and calculate qualifying monthly income.

Return a concise summary with:
- Qualifying monthly income (with the calculation method used)
- Key components (base pay, bonuses, self-employment income, etc.)
- Any caveats or missing information

Do not dump raw numbers from the documents — synthesize and summarize."""
    TIMEOUT_SECS = 180
