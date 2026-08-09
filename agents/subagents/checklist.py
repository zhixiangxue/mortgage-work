"""DocChecklistAnalyzer — sub-agent wrapping the doc-checklist skill."""
from .base import SubAgent


class DocChecklistAnalyzer(SubAgent):
    """Generate a required documents checklist for a mortgage application."""

    name = "checklist-analyzer"
    description = (
        "Generate a required documents checklist based on loan type "
        "(Conventional/FHA/VA/USDA) and borrower situation. Pass the loan "
        "program and any relevant borrower details (self-employed, investment "
        "property, first-time homebuyer, etc.)."
    )
    SYSTEM_PROMPT = """\
You are a document checklist specialist. Use the doc-checklist skill to
generate a tailored required-documents checklist for the loan application.

Return a concise summary with:
- Required documents (must have before submission)
- Recommended documents (strengthen the file)
- Conditional documents (only if certain circumstances apply)
- Any gaps where the current file is missing a required document

Do not dump raw JSON output — group by category and explain why each
document is needed."""
    TIMEOUT_SECS = 120
