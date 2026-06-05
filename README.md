# GMAIS — Governance-Mediated Intelligence Analysis System

A reference implementation of the architecture and evaluation protocol described in
the thesis *"Governance-Mediated Intelligence Analysis System (GMAIS): Empirical
Quantification of the Multi-Agent Security Tax in Intelligence Workflows."*

GMAIS is a **Minimum Viable Architecture** that embeds declassified intelligence
tradecraft — Admiralty source grading, Analysis of Competing Hypotheses (ACH),
need-to-know governance and end-to-end auditability — inside a multi-agent
analytical pipeline, and instruments it to **quantify the multi-agent Security
Tax** through a pre-registered 2×2 factorial ablation.

> The core pipeline runs on the **Python 3.11 standard library alone** with a
> deterministic, offline backend, so the entire factorial ablation reproduces
> without a GPU, an API key, or network access. Point it at a quantised local
> model (GGUF Q4_K_M via llama.cpp / LM Studio / Ollama) for real inference.

---

## Architecture

The system is formalised as a constrained tuple **M = ⟨A, S, E, G, P⟩** (Section
3.3.1) and realised as a two-tier topology with an asynchronous governance
mediation queue:

```
            ┌──────────────────────────────────────────────┐
 OSINT  ──► │  ORCHESTRATOR  (apex, web-of-intelligence)   │
 scenario   └───────┬───────────────────────────┬──────────┘
 (normalised)       │                           │
            ┌───────▼────────┐         ┌────────▼─────────┐
            │  WORKER TIER   │  events │  GOVERNANCE LAYER │  (G)
            │  (concurrent,  ├────────►│  fG(e): tokens +  │
            │   T = 0.7)     │         │  need-to-know +   │
            └───────┬────────┘         │  sensitivity ≥ θ  │
                    │                  │  + hash-chained   │
            ┌───────▼────────┐         │  audit log        │
            │  VALIDATOR     │  events │                   │
            │  (T = 0.2):    ├────────►└───────────────────┘
            │  Admiralty +   │
            │  ACH + bounded │
            │  rationality   │
            └────────────────┘
```

| Factor | Mechanism | Hypothesis |
|--------|-----------|------------|
| **Validation** (V) | Validator Agent: Admiralty grading, ACH diagnosticity, calibration | H1 — effect on analytical accuracy |
| **Governance** (G) | Governance Layer: authenticated delegation, need-to-know, audit | H2 — latency & token overhead |
| **V × G** | Governance mediates validator traffic too | H3 — interaction |
| **Security Tax** | `ST = α·z(ΔL) + β·z(ΔC)` | H4 — policy-threshold bands |

The four factorial cells — **Baseline** (0,0), **V-only** (1,0), **G-only**
(0,1) and **Full** (1,1) — are run by a single orchestrator; the contrast is a
pure function of configuration.

## Module map

| Module | Thesis section | Responsibility |
|--------|----------------|----------------|
| `gmais/config.py` | 3.1.5 | Factorial cells, tiers, all pre-registered thresholds |
| `gmais/scenarios.py` | 3.2.2 | OSINT corpus + complexity stratification + adversarial injection |
| `gmais/gtkg.py` | 3.2.1 | Ground Truth Knowledge Graph (SQLite) + graded rubric |
| `gmais/admiralty.py` | 2.3.5 | Admiralty Code (reliability A–F × credibility 1–6, independent axes) |
| `gmais/ach.py` | 2.3.6 | Analysis of Competing Hypotheses + Heuer's 7 diagnostic questions |
| `gmais/agents/worker.py` | 3.3.1 | Concurrent Worker tier (T = 0.7) |
| `gmais/agents/validator.py` | 2.1 / 3.3 | Validator with bounded-rationality stopping |
| `gmais/governance/` | 3.3.1 | Delegation tokens, `fG(e)` policy, hash-chained audit, mediation queue |
| `gmais/orchestrator.py` | 3.3.1 | Per-cell wiring of the pipeline |
| `gmais/metrics.py` | 3.3.4/3.3.5 | Confusion matrix, Brier, Security Tax (Eq. 3.2–3.8) |
| `gmais/ablation.py` | 3.3.3 | Algorithm 1: the factorial ablation runner |
| `gmais/analysis.py` | 3.3.6/3.3.7 | Effect estimates, policy bands, non-parametric triangulation |
| `gmais/llm/` | 3.3.2 | Pluggable backend (deterministic mock / OpenAI-compatible) |
| `gmais/webapp.py` | — | Flask UI for interactive per-cell comparison |

## Quick start

```sh
pip install -r requirements.txt        # optional; core needs only stdlib

# Run the full 2x2 factorial ablation (thesis default: 45 scenarios/tier => 540 obs)
python -m gmais.cli run --per-tier 45

# A fast smoke run
python -m gmais.cli run --per-tier 10

# Inspect one scenario through the Full GMAIS cell
python -m gmais.cli analyze --sid M-001

# Build the Ground Truth Knowledge Graph and print its stats
python -m gmais.cli gtkg --per-tier 45

# Export the observation matrix
python -m gmais.cli export --per-tier 45 --out results.csv
```

### Web interface

```sh
python -m gmais.webapp        # http://localhost:5000
```

Pick a scenario and see all four factorial cells side by side: predicted
hypothesis, detected injections, latency/token differentials (the Security-Tax
inputs), governance redactions and the audit-chain attestation.

### Real local inference

Run any OpenAI-compatible server (e.g. `llama.cpp`'s `server` hosting a GGUF
Q4_K_M model), then:

```sh
export GMAIS_LLM_BASE_URL=http://localhost:8080/v1
export GMAIS_LLM_MODEL=your-local-model
python -m gmais.cli run --per-tier 45 --backend openai
```

## Reproducibility

* **Deterministic seeding** across the whole campaign (`--seed`, default
  `20260605`); identical runs produce identical observation matrices.
* **Pre-registered constants** (ST weights and bands, θ_policy, validator
  stopping rules) are collected in `gmais/config.py`.
* **Sensitivity** over the Security-Tax weight: `--alpha` (β = 1 − α).

## What is and isn't included

This artefact implements the **architecture** and the **descriptive +
non-parametric** evaluation layer (per-cell metrics, Security-Tax distribution,
factorial point estimates, Friedman/Wilcoxon with Holm–Bonferroni, policy-band
mapping). The thesis's **primary** inference is Bayesian hierarchical modelling
with a log-normal likelihood over the 540-observation campaign; that requires a
PPL (Stan/PyMC) and is out of scope for the offline core. The exported
observation matrix is the input to that fit.

## Tests

```sh
python -m pytest tests/ -q
```

## Legacy interface

The original single-prompt OpenAI analyst (`app.py`, `llm_engine.py`,
`intelligence_agents.py`, …) is retained for reference and still runs with an
`OPENAI_API_KEY`. GMAIS supersedes it with the governed, instrumented
multi-agent architecture above.

## License

MIT License.
