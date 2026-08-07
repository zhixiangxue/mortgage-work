"""CreditAnalyzer — sub-agent wrapping the credit-report-analyzer skill."""
from .base import SubAgent


class CreditAnalyzer(SubAgent):
    """Extract credit data from credit reports."""

    name = "credit-analyzer"
    description = (
        "Analyze a borrower's credit report to extract FICO scores, "
        "tradelines, payment history, and red flags. Pass the absolute path "
        "to the credit report PDF."
    )
    SYSTEM_PROMPT = """\
You are a credit analyst. Use the credit-report-analyzer skill to read the
provided credit report.

Return a concise summary with:
- FICO score(s) and which bureau
- Key tradelines (housing, auto, credit cards) with balances and payment status
- Any derogatory marks, collections, or red flags
- Debt obligations that would appear in a DTI calculation

Do not dump raw report data — synthesize and summarize."""
    TIMEOUT_SECS = 120
