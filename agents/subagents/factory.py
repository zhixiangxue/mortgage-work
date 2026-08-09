"""Factory for building sub-agent instances from installed+enabled skills.

The factory is the single place that decides which sub-agents exist: it reads
``scan_skills()`` (the same source of truth the UI and skill manager use) and
instantiates a sub-agent only when its backing skill is both installed
(``.venv/`` present) and enabled (``skill.local.toml`` says so). A skill that
is missing or disabled produces no tool — the outer agent's prompt guides it
to work without that expert.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .asset import AssetAnalyzer
from .base import SubAgent
from .checklist import DocChecklistAnalyzer
from .credit import CreditAnalyzer
from .dti import DtiAnalyzer
from .eligibility import EligibilityAnalyzer
from .income import IncomeAnalyzer
from .ltv import LtvCltvAnalyzer
from .payment import PaymentAnalyzer

log = logging.getLogger(__name__)

# Mapping: skill id -> (sub-agent class, skill directory name)
_SUBAGENT_SPECS: dict[str, tuple[type[SubAgent], str]] = {
    "income-calc":            (IncomeAnalyzer,        "income-calc"),
    "credit-report-analyzer": (CreditAnalyzer,        "credit-report-analyzer"),
    "asset-calc":             (AssetAnalyzer,         "asset-calc"),
    "eligibility-calc":       (EligibilityAnalyzer,   "eligibility-calc"),
    "doc-checklist":          (DocChecklistAnalyzer,  "doc-checklist"),
    "dti-calculator":         (DtiAnalyzer,           "dti-calculator"),
    "ltv-cltv":               (LtvCltvAnalyzer,       "ltv-cltv"),
    "payment-calculator":     (PaymentAnalyzer,       "payment-calculator"),
}


def build_subagents(model_uri: str, api_key: str, root: Path) -> list[SubAgent]:
    """Create sub-agent instances for every skill that is both installed and enabled.

    Returns a list of SubAgent instances ready to drop into an agent's tool list.
    If no skills are available, returns an empty list — the caller (clerk)
    falls back to its base tools.
    """
    from skills_manager import MARKET_DIR, scan_skills

    # Build {skill_id: SkillInfo} for quick lookup
    available = {s.id: s for s in scan_skills()}

    agents: list[SubAgent] = []
    for skill_id, (cls, dir_name) in _SUBAGENT_SPECS.items():
        info = available.get(skill_id)
        if not info:
            log.debug("subagent skip: %s not found in market", skill_id)
            continue
        if not info.installed:
            log.info("subagent skip: %s not installed", skill_id)
            continue
        if not info.enabled:
            log.info("subagent skip: %s disabled", skill_id)
            continue
        skill_dir = str(MARKET_DIR / dir_name)
        agents.append(cls(
            skill_dir=skill_dir,
            model_uri=model_uri,
            api_key=api_key,
            root=root,
        ))
        log.info("subagent ready: %s", cls.name)

    return agents
