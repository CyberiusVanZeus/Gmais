"""Central configuration for the Governance-Mediated Intelligence Analysis System.

Every tunable in GMAIS is collected here so that the 2x2 factorial ablation
described in Chapter Three of the thesis can be reproduced exactly. Values that
the thesis pre-registers (factorial cells, complexity tiers, Security Tax
weights and bands, validator bounded-rationality thresholds, the governance
compliance parameter theta_policy) are encoded as named constants rather than
scattered through the code, so an independent reviewer can audit them in one
place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


# --------------------------------------------------------------------------- #
# Factorial design: Validation x Governance (Section 1.3.1, 3.1.5)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FactorialCell:
    """One cell of the 2x2 ablation.

    ``validation`` toggles the Validator Agent (H1); ``governance`` toggles the
    Governance Layer (H2). The four cells are Baseline (0,0), V-only (1,0),
    G-only (0,1) and Full GMAIS (1,1).
    """

    name: str
    validation: bool
    governance: bool

    @property
    def code(self) -> str:
        return f"V{int(self.validation)}G{int(self.governance)}"


#: The four pre-registered factorial cells, in canonical order.
CELLS: Tuple[FactorialCell, ...] = (
    FactorialCell("Baseline", validation=False, governance=False),
    FactorialCell("V-only", validation=True, governance=False),
    FactorialCell("G-only", validation=False, governance=True),
    FactorialCell("Full", validation=True, governance=True),
)

#: The baseline cell (V=0, G=0) against which Security-Tax differentials are taken.
BASELINE_CELL: FactorialCell = CELLS[0]

#: Complexity tiers used for stratification and condition-wise z-scoring (3.2.2).
TIERS: Tuple[str, ...] = ("low", "medium", "high")


# --------------------------------------------------------------------------- #
# Admiralty Code (Section 2.3.5 / 2.3.6, AJP-2.1)
# --------------------------------------------------------------------------- #
#: Source-reliability letters A (reliable) -> E (unreliable), F = cannot judge.
ADMIRALTY_RELIABILITY: Tuple[str, ...] = ("A", "B", "C", "D", "E", "F")
#: Information-credibility digits 1 (confirmed) -> 5 (improbable), 6 = cannot judge.
ADMIRALTY_CREDIBILITY: Tuple[str, ...] = ("1", "2", "3", "4", "5", "6")


# --------------------------------------------------------------------------- #
# Governance Layer policy parameters (Section 3.3.1)
# --------------------------------------------------------------------------- #
#: Classification ladder for need-to-know mediation; index = clearance level.
CLASSIFICATION_LEVELS: Tuple[str, ...] = (
    "UNCLASSIFIED",
    "OFFICIAL",
    "CONFIDENTIAL",
    "SECRET",
)


@dataclass
class GMAISConfig:
    """Runtime configuration for an ablation campaign."""

    # --- Reproducibility ------------------------------------------------- #
    seed: int = 20260605  # deterministic seeding (Algorithm 1, step 3)

    # --- Worker tier ----------------------------------------------------- #
    n_workers: int = 3
    worker_temperature: float = 0.7  # exploratory hypothesis generation (3.3.2)

    # --- Validator ------------------------------------------------------- #
    validator_temperature: float = 0.2  # deterministic assessment (3.3.2)
    # Bounded-rationality stopping rules (Simon, 1955; thesis Section 2.1):
    ci_width_threshold: float = 0.15  # halt when CI width < 0.15
    convergence_threshold: float = 0.85  # halt when hypothesis convergence >= 0.85
    max_critique_iterations: int = 4

    # --- Governance ------------------------------------------------------ #
    theta_policy: float = 0.60  # P(compliance | e) >= theta_policy  (Eq. 3.1)
    sensitivity_threshold: float = 0.70  # information-sensitivity ceiling
    delegation_secret: str = "gmais-delegation-key"  # HMAC key for tokens
    queue_saturation_margin: float = 0.15  # adaptive rate-limit margin (3.3.1)

    # --- Security Tax weights and bands (Section 3.3.4 / 3.3.7) ----------- #
    st_alpha: float = 0.5  # weight on z(latency differential)
    st_beta: float = 0.5  # weight on z(token differential); alpha + beta = 1
    st_band_low: float = 0.5  # ST < 0.5  -> full governance
    st_band_high: float = 1.5  # ST > 1.5  -> minimal governance

    # --- Scenario corpus ------------------------------------------------- #
    scenarios_per_tier: int = 45  # 45 x 3 tiers x 4 cells = 540 observations

    # --- LLM backend ----------------------------------------------------- #
    backend: str = "mock"  # "mock" | "openai"
    model: str = "gmais-mva-q4_k_m"

    def __post_init__(self) -> None:
        if abs((self.st_alpha + self.st_beta) - 1.0) > 1e-9:
            raise ValueError(
                f"Security-Tax weights must satisfy alpha + beta = 1 "
                f"(got {self.st_alpha} + {self.st_beta})"
            )

    @property
    def total_observations(self) -> int:
        return self.scenarios_per_tier * len(TIERS) * len(CELLS)


DEFAULT_CONFIG = GMAISConfig()
