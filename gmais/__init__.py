"""GMAIS - Governance-Mediated Intelligence Analysis System.

A Minimum Viable Architecture that operationalises declassified intelligence
tradecraft (Admiralty source grading, Analysis of Competing Hypotheses,
need-to-know governance and end-to-end auditability) inside a resource-
constrained multi-agent pipeline, instrumented to quantify the multi-agent
Security Tax via a 2x2 factorial ablation.

Implements the architecture and evaluation protocol specified in the thesis
"Governance-Mediated Intelligence Analysis System (GMAIS): Empirical
Quantification of the Multi-Agent Security Tax in Intelligence Workflows."
"""

from __future__ import annotations

from .ablation import AblationResult, run_ablation
from .analysis import build_report, factorial_effects, policy_recommendation, security_tax_summary
from .config import CELLS, DEFAULT_CONFIG, GMAISConfig
from .orchestrator import AnalysisResult, GMAISOrchestrator

__version__ = "0.1.0"

__all__ = [
    "run_ablation",
    "AblationResult",
    "build_report",
    "factorial_effects",
    "policy_recommendation",
    "security_tax_summary",
    "GMAISConfig",
    "DEFAULT_CONFIG",
    "CELLS",
    "GMAISOrchestrator",
    "AnalysisResult",
]
