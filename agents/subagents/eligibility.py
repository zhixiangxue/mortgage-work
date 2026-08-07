"""EligibilityAnalyzer — sub-agent wrapping the eligibility-calc skill."""
from .base import SubAgent


class EligibilityAnalyzer(SubAgent):
    """Check borrower eligibility against program guidelines."""

    name = "eligibility-analyzer"
    description = (
        "Check a borrower's profile against a specific loan program's "
        "eligibility guidelines. Pass absolute paths to guideline documents "
        "and a summary of the borrower's profile (income, credit, assets, "
        "property, loan amount)."
    )
    SYSTEM_PROMPT = """\
You are an eligibility analyst. Use the eligibility-calc skill to read the
provided program guidelines and compare them against the borrower's profile.

Return a concise summary with:
- Program name and guideline source
- Pass/fail verdict
- Each requirement checked: required value, actual value, margin, status
- Any blockers (hard fails that prevent qualification)
- Any conditions or notes

Do not dump raw guideline text — synthesize the comparison and summarize."""
    TIMEOUT_SECS = 180
