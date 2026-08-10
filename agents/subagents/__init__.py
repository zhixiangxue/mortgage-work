"""Sub-agent package — domain expert tools wrapping mortgage skills.

Each sub-agent is a chak tool with one method (``invoke``) that runs a skill
inside its own Conversation. The factory builds them on demand, skipping any
skill that is not installed or not enabled.
"""
from .asset import AssetAnalyzer
from .base import SubAgent
from .checklist import DocChecklistAnalyzer
from .credit import CreditAnalyzer
from .dti import DtiAnalyzer
from .eligibility import EligibilityAnalyzer
from .factory import build_subagents
from .income import IncomeAnalyzer
from .ltv import LtvCltvAnalyzer
from .payment import PaymentAnalyzer
from .product_finder import ProductFinder

__all__ = [
    "SubAgent",
    "IncomeAnalyzer",
    "CreditAnalyzer",
    "AssetAnalyzer",
    "EligibilityAnalyzer",
    "DocChecklistAnalyzer",
    "DtiAnalyzer",
    "LtvCltvAnalyzer",
    "PaymentAnalyzer",
    "ProductFinder",
    "build_subagents",
]
