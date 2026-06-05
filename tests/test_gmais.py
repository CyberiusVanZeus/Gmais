"""Test suite for the GMAIS artefact.

Covers the tradecraft primitives (Admiralty grading, ACH), the governance
mechanisms (delegation tokens, policy fG(e), hash-chained audit), the
Security-Tax computation, and the end-to-end factorial ablation, including the
deterministic-seeding guarantee the thesis relies on.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from gmais.ablation import run_ablation
from gmais.ach import ACHMatrix, CONSISTENT, Evidence, INCONSISTENT
from gmais.admiralty import AdmiraltyGrade, grade_source
from gmais.analysis import factorial_effects, policy_recommendation, security_tax_summary
from gmais.config import GMAISConfig
from gmais.governance.audit import AuditLog
from gmais.governance.policy import Event, PolicyEngine
from gmais.governance.tokens import issue_token
from gmais.metrics import ConfusionMatrix, brier_score, compute_security_tax


# --------------------------------------------------------------------------- #
# Admiralty Code
# --------------------------------------------------------------------------- #
def test_admiralty_dimensional_independence():
    # A reliable, well-corroborated source -> high grade.
    good = grade_source({"provenance": "official", "corroboration": 3,
                         "contradicted": False, "plausible": True})
    # A weak, contradicted source -> low grade.
    bad = grade_source({"provenance": "anonymous", "corroboration": 0,
                        "contradicted": True, "plausible": False})
    assert good.confidence > bad.confidence
    assert good.reliability < bad.reliability  # 'A' < 'E' lexically
    assert bad.credibility == "5"  # contradicted -> improbable


def test_admiralty_grade_validation():
    with pytest.raises(ValueError):
        AdmiraltyGrade("Z", "1")
    with pytest.raises(ValueError):
        AdmiraltyGrade("A", "9")


# --------------------------------------------------------------------------- #
# Analysis of Competing Hypotheses
# --------------------------------------------------------------------------- #
def test_ach_selects_least_inconsistent():
    matrix = ACHMatrix({"H1": "benign", "H2": "hostile"})
    matrix.add_evidence(Evidence("e1", "supports H1", 0.9,
                                 {"H1": CONSISTENT, "H2": INCONSISTENT}))
    matrix.add_evidence(Evidence("e2", "supports H1", 0.8,
                                 {"H1": CONSISTENT, "H2": INCONSISTENT}))
    result = matrix.evaluate()
    assert result.selected == "H1"
    assert 0.0 <= result.convergence <= 1.0
    assert all(result.diagnostic_checks.values())


def test_ach_requires_two_hypotheses():
    with pytest.raises(ValueError):
        ACHMatrix({"H1": "only one"})


# --------------------------------------------------------------------------- #
# Governance: tokens, policy, audit
# --------------------------------------------------------------------------- #
def test_delegation_token_signature():
    token = issue_token("worker", "analyse", "SECRET", "key")
    assert token.verify("key")
    assert not token.verify("wrong-key")
    token.scope = "tamper"  # mutate after signing
    assert not token.verify("key")


def test_policy_accepts_compliant_event():
    engine = PolicyEngine(theta_policy=0.6, sensitivity_threshold=0.7, secret="key")
    token = issue_token("worker", "analyse", "SECRET", "key")
    event = Event("worker", "validator", "msg", classification="OFFICIAL",
                  sensitivity=0.2, token=token, recipient_clearance="SECRET")
    decision = engine.evaluate(event)
    assert decision.accepted == 1
    assert decision.redacted_message == "msg"


def test_policy_redacts_on_need_to_know_violation():
    engine = PolicyEngine(theta_policy=0.6, sensitivity_threshold=0.7, secret="key")
    token = issue_token("worker", "analyse", "SECRET", "key")
    event = Event("worker", "validator", "secret payload", classification="SECRET",
                  sensitivity=0.2, token=token, recipient_clearance="UNCLASSIFIED")
    decision = engine.evaluate(event)
    assert decision.accepted == 0
    assert "need-to-know" in decision.reason
    assert decision.redacted_message == "[REDACTED BY GOVERNANCE LAYER]"


def test_policy_redacts_on_bad_token():
    engine = PolicyEngine(theta_policy=0.6, sensitivity_threshold=0.7, secret="key")
    token = issue_token("worker", "analyse", "SECRET", "different-secret")
    event = Event("worker", "validator", "msg", token=token)
    assert engine.evaluate(event).accepted == 0


def test_audit_chain_integrity_and_tamper_detection():
    log = AuditLog()
    for i in range(5):
        log.record(sender="a", recipient="b", decision=1, reason="ok", message=f"m{i}")
    assert log.verify_integrity()
    assert len(log) == 5
    # Tamper with a middle entry.
    log._entries[2].decision = 0
    assert not log.verify_integrity()


# --------------------------------------------------------------------------- #
# Metrics and Security Tax
# --------------------------------------------------------------------------- #
def test_confusion_matrix_metrics():
    cm = ConfusionMatrix(tp=8, fp=2, fn=2, tn=8)
    assert cm.accuracy == 0.8
    assert cm.precision == 0.8
    assert cm.recall == 0.8
    assert round(cm.f1, 3) == 0.8


def test_brier_score_bounds():
    assert brier_score([1.0, 1.0], [1, 1]) == 0.0
    assert brier_score([0.0, 0.0], [1, 1]) == 1.0


def test_security_tax_weights_sum_to_one():
    with pytest.raises(ValueError):
        GMAISConfig(st_alpha=0.6, st_beta=0.6)


def test_security_tax_ordering():
    # Governed observations must carry higher ST than baseline ones.
    obs = []
    for i in range(10):
        obs.append({"scenario_id": f"s{i}", "tier": "low", "cell": "Baseline",
                    "latency_ms": 100 + i, "tokens": 1000 + i})
        obs.append({"scenario_id": f"s{i}", "tier": "low", "cell": "Full",
                    "latency_ms": 300 + i, "tokens": 2000 + i})
    st = compute_security_tax(obs, alpha=0.5, beta=0.5, band_low=0.5, band_high=1.5)
    base = [r.security_tax for r in st if r.cell == "Baseline"]
    full = [r.security_tax for r in st if r.cell == "Full"]
    assert sum(full) / len(full) > sum(base) / len(base)


# --------------------------------------------------------------------------- #
# End-to-end ablation
# --------------------------------------------------------------------------- #
def test_ablation_runs_and_shapes():
    config = GMAISConfig(scenarios_per_tier=6)
    result = run_ablation(config)
    assert len(result.observations) == 6 * 3 * 4  # tiers x cells
    assert set(result.per_cell_metrics) == {"Baseline", "V-only", "G-only", "Full"}


def test_ablation_is_deterministic():
    cfg = GMAISConfig(scenarios_per_tier=5)
    a = run_ablation(cfg)
    b = run_ablation(cfg)
    assert a.observation_dicts() == b.observation_dicts()


def test_validation_improves_accuracy_and_detection():
    result = run_ablation(GMAISConfig(scenarios_per_tier=8))
    m = result.per_cell_metrics
    # H1: validation lifts hypothesis accuracy.
    assert m["V-only"]["hypothesis_accuracy"] >= m["Baseline"]["hypothesis_accuracy"]
    # Validation enables injection detection; baseline detects nothing.
    assert m["Baseline"]["detection"]["f1"] == 0.0
    assert m["V-only"]["detection"]["f1"] > 0.5


def test_governance_increases_cost():
    result = run_ablation(GMAISConfig(scenarios_per_tier=8))
    effects = factorial_effects(result)
    # H2: governance is a non-negative tax on latency and tokens.
    assert effects.governance_latency_effect_ms > 0
    assert effects.governance_token_effect > 0


def test_audit_intact_across_governed_cells():
    result = run_ablation(GMAISConfig(scenarios_per_tier=6))
    failures = sum(m["audit_failures"] for m in result.per_cell_metrics.values())
    assert failures == 0


def test_policy_recommendation_present_for_governed_cells():
    result = run_ablation(GMAISConfig(scenarios_per_tier=6))
    recs = policy_recommendation(result)
    assert "Full" in recs and "Baseline" not in recs
    summary = security_tax_summary(result)
    assert summary["Full"]["mean_st"] > summary["Baseline"]["mean_st"]
