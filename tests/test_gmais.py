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
from gmais.governance.redaction import extract_entities, redact_entities
from gmais.governance.tokens import issue_token
from gmais.llm import build_backend
from gmais.orchestrator import GMAISOrchestrator
from gmais.scenarios import generate_corpus
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


def test_entity_redaction_masks_named_entities():
    text = "Aldoria reporting indicates Beronia launched a raid."
    redacted, n, mapping = redact_entities(text, ["Aldoria", "Beronia"])
    assert n == 2
    assert "Aldoria" not in redacted and "Beronia" not in redacted
    assert "[ENTITY_1]" in redacted and "[ENTITY_2]" in redacted
    assert mapping["Aldoria"] == "[ENTITY_1]"


def test_extract_entities_skips_stopwords():
    ents = extract_entities("The Aldoria delegation met. Reliable sources confirm.")
    assert "Aldoria" in ents
    assert "The" not in ents and "Reliable" not in ents


def test_peer_event_is_authorised_but_entity_redacted():
    engine = PolicyEngine(theta_policy=0.6, sensitivity_threshold=0.7, secret="key")
    token = issue_token("worker", "analyse", "SECRET", "key")
    event = Event("worker", "worker_peers", "Aldoria struck Beronia", classification="OFFICIAL",
                  sensitivity=0.2, token=token, recipient_clearance="SECRET",
                  peer=True, entities=["Aldoria", "Beronia"])
    decision = engine.evaluate(event)
    assert decision.accepted == 1  # peers are authorised
    assert decision.entities_redacted == 2  # but entity labels are masked
    assert "Aldoria" not in decision.redacted_message


def test_governance_reduces_worker_to_worker_bias_exposure():
    cfg = GMAISConfig(scenarios_per_tier=4)
    corpus = generate_corpus(cfg.seed, cfg.scenarios_per_tier)
    orch = GMAISOrchestrator(build_backend("mock", seed=cfg.seed), cfg)
    from gmais.config import CELLS

    baseline = next(c for c in CELLS if c.name == "Baseline")
    full = next(c for c in CELLS if c.name == "Full")
    s = corpus[0]
    ungoverned = orch.analyze(s, baseline)
    governed = orch.analyze(s, full)
    # Without governance, entity names circulate among peers; with it, they are
    # redacted, so bias exposure drops to zero.
    assert ungoverned.peer_bias_exposure > 0
    assert ungoverned.entities_redacted == 0
    assert governed.peer_bias_exposure == 0
    assert governed.entities_redacted == ungoverned.peer_bias_exposure


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

    # Wall-clock columns are measurements of the host and are expected to
    # differ between runs; the determinism guarantee covers every analytical
    # column. MANIFEST.json records this same exemption list.
    def analytical(result):
        return [{k: v for k, v in row.items() if not k.startswith("measured_")}
                for row in result.observation_dicts()]

    assert analytical(a) == analytical(b)
    assert all(row["measured_governance_ms"] > 0
               for row in a.observation_dicts() if row["governance"] == 1)


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


# --------------------------------------------------------------------------- #
# Verified-source web search
# --------------------------------------------------------------------------- #
def test_verified_domain_allowlist():
    from gmais.web_search import is_verified

    assert is_verified("https://www.cisa.gov/advisory/x")
    assert is_verified("https://who.int/news")
    assert is_verified("https://defence.mod.gov.uk/report")
    assert not is_verified("https://example.com/blog")
    assert not is_verified("not-a-url")


def test_parse_user_sources_flags_verification():
    from gmais.web_search import parse_user_sources

    hits = parse_user_sources("https://un.org/a | corroborates\nhttps://blog.example/x")
    assert len(hits) == 2
    assert hits[0].verified and hits[0].snippet == "corroborates"
    assert not hits[1].verified


def test_search_returns_user_sources_without_network():
    from gmais.web_search import VerifiedSourceSearch, parse_user_sources

    search = VerifiedSourceSearch(parse_user_sources("https://state.gov/x | note"))
    hits = search.corroborate("any query")
    assert any(h.verified and h.origin == "analyst" for h in hits)


# --------------------------------------------------------------------------- #
# Multi-provider routing
# --------------------------------------------------------------------------- #
def test_multi_provider_falls_back_to_mock(monkeypatch):
    # No SDKs/keys here, so claude/openai are unavailable; the safety-net mock
    # is permitted only when GMAIS_ALLOW_MOCK is set.
    monkeypatch.setenv("GMAIS_ALLOW_MOCK", "1")
    from gmais.llm import build_multi_backend

    backend = build_multi_backend(["claude", "openai"], seed=1)
    assert backend.available_providers  # something is usable
    resp = backend.generate("hello", temperature=0.5, role="worker")
    assert resp.text and resp.provider


def test_multi_provider_requires_some_backend(monkeypatch):
    monkeypatch.delenv("GMAIS_ALLOW_MOCK", raising=False)
    monkeypatch.setattr(
        "gmais.llm.multi.MultiProviderBackend._try_build", lambda self, p: None
    )
    from gmais.llm import build_multi_backend

    with pytest.raises(RuntimeError):
        build_multi_backend(["claude"], seed=1)


# --------------------------------------------------------------------------- #
# Activity recorder and analytics narration
# --------------------------------------------------------------------------- #
def test_activity_recorder_streams_then_finishes():
    from gmais.activity import ActivityRecorder

    rec = ActivityRecorder()
    rec.emit("ingest", "loading", status="running")
    rec.emit("score", "done", status="done")
    rec.finish({"html": "<div>ok</div>"})
    items = list(rec.stream())
    activities = [i for i in items if not isinstance(i, tuple)]
    results = [i for i in items if isinstance(i, tuple) and i[0] == "result"]
    assert len(activities) == 2 and len(results) == 1
    assert results[0][1]["html"] == "<div>ok</div>"


def test_cell_analytics_mentions_hypotheses():
    from gmais.analytics_text import cell_analytics

    base = {"delta_latency": 0, "delta_tokens": 0}
    v = cell_analytics("V-only", {"correct": 0.9, "delta_tokens": 900, "bias_exposure": 5}, base)
    g = cell_analytics("G-only", {"correct": 0.3, "delta_latency": 30, "delta_tokens": 100, "bias_exposure": 0}, base)
    full = cell_analytics("Full", {"correct": 0.9, "delta_latency": 35, "delta_tokens": 110, "bias_exposure": 0}, base)
    assert "H1" in v
    assert "H2" in g and "Security Tax" in g
    assert "H3" in full or "interaction" in full


# --------------------------------------------------------------------------- #
# Observation-noise model (Section 3.2.4)
# --------------------------------------------------------------------------- #
def test_noise_is_deterministic_and_cell_invariant():
    """The same claim must be perturbed identically on every draw.

    This is what keeps the ablation contrast a pure function of configuration
    and the repeated-measures pairing valid.
    """

    from gmais.noise import NoiseModel

    cfg = GMAISConfig(scenarios_per_tier=3)
    a, b = NoiseModel.from_config(cfg), NoiseModel.from_config(cfg)
    source = {"provenance": "anonymous", "corroboration": 0,
              "contradicted": True, "plausible": False}
    for _ in range(5):
        assert (a.observed_source("L-000", "L-000-X0", source, True)
                == b.observed_source("L-000", "L-000-X0", source, True))
        assert a.perturb_grade("L-000", "L-000-T1", "B", "2") == \
            b.perturb_grade("L-000", "L-000-T1", "B", "2")
        assert a.worker_anchors("L-000", 1) == b.worker_anchors("L-000", 1)


def test_noise_can_be_disabled():
    from gmais.noise import NoiseModel

    off = NoiseModel.disabled(seed=1)
    source = {"provenance": "anonymous", "corroboration": 0,
              "contradicted": True, "plausible": False}
    assert off.observed_source("S", "C", source, True) is source
    assert off.perturb_grade("S", "C", "B", "2") == ("B", "2")
    assert off.worker_anchors("S", 0) is False


def test_noise_leaves_ground_truth_untouched():
    """Camouflage changes what the system *observes*, never the GTKG label."""

    from gmais.noise import NoiseModel

    cfg = GMAISConfig(scenarios_per_tier=5)
    corpus = generate_corpus(cfg.seed, cfg.scenarios_per_tier)
    noise = NoiseModel.from_config(cfg)
    for scenario in corpus:
        for claim in scenario.claims:
            observed = noise.observed_source(
                scenario.sid, claim.cid, claim.source, claim.is_injected)
            assert claim.is_injected == (claim.cid in scenario.injected_cids)
            assert set(observed) == set(claim.source)


def test_noise_produces_non_degenerate_detection():
    """Without noise, detection is perfect; with it, the task is non-trivial."""

    ideal = run_ablation(GMAISConfig(scenarios_per_tier=6, noise_enabled=False))
    noisy = run_ablation(GMAISConfig(scenarios_per_tier=6))
    assert ideal.per_cell_metrics["V-only"]["detection"]["f1"] == 1.0
    assert 0.0 < noisy.per_cell_metrics["V-only"]["detection"]["f1"] < 1.0


# --------------------------------------------------------------------------- #
# Governance closes the anchoring pathway
# --------------------------------------------------------------------------- #
def test_governance_eliminates_peer_anchoring():
    result = run_ablation(GMAISConfig(scenarios_per_tier=6))
    for obs in result.observations:
        if obs.governance == 1:
            assert obs.anchored_workers == 0, \
                "entity redaction must remove the anchoring cue"
            assert obs.peer_bias_exposure == 0
    assert any(o.anchored_workers > 0 for o in result.observations
               if o.governance == 0), "ungoverned cells must exhibit anchoring"


# --------------------------------------------------------------------------- #
# Wall-clock instrumentation (Section 3.3.4)
# --------------------------------------------------------------------------- #
def test_measured_governance_time_is_recorded_only_when_governed():
    result = run_ablation(GMAISConfig(scenarios_per_tier=4))
    for obs in result.observations:
        if obs.governance == 1:
            assert obs.measured_governance_ms > 0.0
            assert obs.governed_events > 0
        else:
            assert obs.measured_governance_ms == 0.0
            assert obs.governed_events == 0


def test_timing_reattribution_does_not_double_count():
    """Redaction time is charged to redaction and discharged from policy eval."""

    from gmais.timing import ComponentTimings

    t = ComponentTimings()
    t.add("policy_eval", 1000)
    t.reattribute("policy_eval", "redaction", 400)
    assert t.totals_ns["policy_eval"] == 600
    assert t.totals_ns["redaction"] == 400
    assert t.counts["policy_eval"] == 1  # the enclosing block still ran once


# --------------------------------------------------------------------------- #
# Inferential statistics
# --------------------------------------------------------------------------- #
def test_mcnemar_exact_matches_binomial():
    from gmais.stats import mcnemar_exact

    a = [1] * 10 + [0] * 10
    b = [1] * 10 + [1] * 10  # 10 discordant pairs, all favouring b
    test = mcnemar_exact(a, b, name="t")
    assert test.detail["n01_b_correct_only"] == 10
    assert test.detail["n10_a_correct_only"] == 0
    assert test.p_value == pytest.approx(2 * 0.5 ** 10)


def test_hodges_lehmann_ci_brackets_the_estimate():
    from gmais.stats import hodges_lehmann_ci

    diffs = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
    ci = hodges_lehmann_ci(diffs)
    assert ci.low <= ci.estimate <= ci.high
    assert ci.excludes_zero()


def test_brier_decomposition_reconstructs_the_score():
    from gmais.stats import brier_decomposition

    confidences = [0.1, 0.35, 0.5, 0.65, 0.9, 0.95, 0.2, 0.8]
    outcomes = [0, 0, 1, 1, 1, 1, 0, 1]
    d = brier_decomposition(confidences, outcomes)
    assert d.brier == pytest.approx(
        d.reliability - d.resolution + d.uncertainty, abs=1e-9)


def test_holm_bonferroni_is_monotone_and_conservative():
    from gmais.stats import PairedTest, holm_bonferroni

    tests = [PairedTest(f"t{i}", 10, "x", 0.0, p)
             for i, p in enumerate([0.001, 0.01, 0.04])]
    holm_bonferroni(tests)
    adjusted = [t.p_adjusted for t in tests]
    assert adjusted == sorted(adjusted)  # monotone in the sorted p order
    assert all(adj >= t.p_value for adj, t in zip(adjusted, tests))


def test_wilson_ci_handles_boundary_proportions():
    from gmais.stats import wilson_ci

    at_zero = wilson_ci(0, 50)
    assert at_zero.low == 0.0 and 0.0 < at_zero.high < 0.2  # exact at phat = 0
    at_one = wilson_ci(50, 50)
    assert at_one.high == 1.0 and 0.8 < at_one.low < 1.0


# --------------------------------------------------------------------------- #
# H1-H4 confirmatory layer
# --------------------------------------------------------------------------- #
def test_alignment_is_paired_within_scenario():
    from gmais.hypotheses import align, scenario_ids

    result = run_ablation(GMAISConfig(scenarios_per_tier=4))
    vectors = align(result, "latency_ms")
    lengths = {len(v) for v in vectors.values()}
    assert len(lengths) == 1
    assert lengths.pop() == len(scenario_ids(result))


def test_all_hypotheses_are_reported_with_adjusted_p_values():
    from gmais.hypotheses import CONFIRMATORY, run_all

    result = run_ablation(GMAISConfig(scenarios_per_tier=6))
    inference = run_all(result)
    assert inference["confirmatory_family_size"] == len(CONFIRMATORY)
    for key in ("H1", "H2", "H3", "H4"):
        assert inference[key]["verdict"] in {
            "SUPPORTED", "NOT SUPPORTED", "INCONCLUSIVE"}
    adjusted = [t["p_adjusted"] for k in ("H1", "H2", "H3")
                for t in inference[k]["tests"] if "p_adjusted" in t]
    assert len(adjusted) == len(CONFIRMATORY)
    assert all(0.0 <= p <= 1.0 for p in adjusted)


def test_alpha_sensitivity_spans_the_weighting():
    from gmais.hypotheses import alpha_sensitivity

    result = run_ablation(GMAISConfig(scenarios_per_tier=4))
    sweep = alpha_sensitivity(result)
    assert set(sweep) == {f"alpha={a:g}" for a in (0.0, 0.25, 0.5, 0.75, 1.0)}
    for cells in sweep.values():
        for entry in cells.values():
            assert entry["band"] in {
                "full-governance", "adaptive-governance", "minimal-governance"}


# --------------------------------------------------------------------------- #
# Results package
# --------------------------------------------------------------------------- #
def test_campaign_writes_a_checksummed_package(tmp_path):
    from gmais.campaign import run_campaign

    out = tmp_path / "pkg"
    package = run_campaign(
        GMAISConfig(scenarios_per_tier=3), outdir=str(out),
        with_figures=False, verbose=False)

    for name in ("observations.csv", "security_tax.csv", "results.json",
                 "REPORT.txt", "MANIFEST.json"):
        assert (out / name).exists(), name
    assert (out / "tables" / "all_tables.tex").exists()

    manifest = package["manifest"]
    assert manifest["campaign"]["observations"] == 36
    assert manifest["campaign"]["seed"] == GMAISConfig().seed
    for record in manifest["artefacts"].values():
        assert len(record["sha256"]) == 64
