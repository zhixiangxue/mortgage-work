"""LtvCltvAnalyzer — sub-agent wrapping the ltv-cltv skill."""
from .base import SubAgent


class LtvCltvAnalyzer(SubAgent):
    """Calculate Loan-to-Value (LTV) and Combined LTV (CLTV) ratios."""

    name = "ltv-analyzer"
    description = (
        "Calculate LTV and CLTV ratios from loan amount and property value. "
        "Handles multiple liens (HELOC, second mortgage). Pass the loan amount, "
        "home value or purchase price, and details of any subordinate liens."
    )
    SYSTEM_PROMPT = """\
You are an LTV/CLTV analyst. Use the ltv-cltv skill to calculate
loan-to-value ratios.

Read loan documents (purchase contract, notes, client.yaml) to find the
loan amount and property value if not provided directly.

Return a concise summary with:
- LTV (first mortgage / home value)
- CLTV (all loans / home value)
- HCLTV if a HELOC is present
- Down payment percentage
- PMI requirement status (required if LTV > 80%, cancellation threshold)

Do not dump raw script output — interpret the results."""
    TIMEOUT_SECS = 120
