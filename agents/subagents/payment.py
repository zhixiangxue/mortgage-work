"""PaymentAnalyzer — sub-agent wrapping the payment-calculator skill."""
from .base import SubAgent


class PaymentAnalyzer(SubAgent):
    """Calculate the full monthly mortgage payment (PITIA)."""

    name = "payment-analyzer"
    description = (
        "Calculate the full monthly housing payment (PITIA) including "
        "principal & interest, property tax, insurance, PMI, and HOA. Also "
        "computes LTV and PMI requirement. Pass the loan amount, interest "
        "rate, term, home value, and optional tax/insurance/HOA values."
    )
    SYSTEM_PROMPT = """\
You are a payment analyst. Use the payment-calculator skill to calculate
the full monthly housing payment (PITIA).

Gather the loan amount, interest rate, term, home value, property tax,
insurance, and HOA from provided documents if not given directly.

Return a concise summary with:
- Monthly principal & interest (P&I)
- Monthly property tax
- Monthly insurance
- Monthly PMI (if applicable, based on LTV)
- Monthly HOA
- Total PITIA
- LTV and down payment percentage

Do not dump raw script output — interpret the results."""
    TIMEOUT_SECS = 120
