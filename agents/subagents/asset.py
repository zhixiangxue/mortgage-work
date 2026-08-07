"""AssetAnalyzer — sub-agent wrapping the asset-calc skill."""
from .base import SubAgent


class AssetAnalyzer(SubAgent):
    """Analyze borrower assets and verify funds to close."""

    name = "asset-analyzer"
    description = (
        "Analyze borrower asset documents (bank statements, investment "
        "accounts, retirement accounts) to verify funds to close and reserves. "
        "Pass absolute file paths and the loan context (purchase price, "
        "down payment, closing cost estimate)."
    )
    SYSTEM_PROMPT = """\
You are an asset analyst. Use the asset-calc skill to read the provided
asset documents and guideline requirements.

Return a concise summary with:
- Total verified liquid assets
- Funds required to close (down payment + closing costs)
- Reserve requirement and whether it is met
- Verdict: sufficient / insufficient (with gap amount if applicable)
- Any caveats (large undocumented deposits, gift funds, etc.)

Do not dump raw statement data — synthesize and summarize."""
    TIMEOUT_SECS = 180
