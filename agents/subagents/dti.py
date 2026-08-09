"""DtiAnalyzer — sub-agent wrapping the dti-calculator skill."""
from .base import SubAgent


class DtiAnalyzer(SubAgent):
    """Calculate Debt-to-Income (DTI) ratios from income and debt data."""

    name = "dti-analyzer"
    description = (
        "Calculate front-end and back-end Debt-to-Income (DTI) ratios. Pass "
        "monthly qualifying income, monthly housing payment (PITIA), and any "
        "monthly debt obligations. Read income documents and debt information "
        "from provided file paths if the raw numbers are not yet available."
    )
    SYSTEM_PROMPT = """\
You are a DTI analyst. Use the dti-calculator skill to calculate
debt-to-income ratios.

Read income documents and debt information from the provided files if
needed, extract the relevant numbers, then call the skill script with the
correct JSON input.

Return a concise summary with:
- Front-end DTI (housing / income)
- Back-end DTI ((housing + debts) / income)
- Total monthly debts broken down by obligation
- Qualification status against Conventional (28/36), FHA (31/43), and
  VA (41%) thresholds

Do not dump raw script output — interpret the results."""
    TIMEOUT_SECS = 120
