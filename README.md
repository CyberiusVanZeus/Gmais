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
| **Governance** (G) | Governance Layer: authenticated delegation, need-to-know (incl. worker-to-worker named-entity redaction), audit | H2 — latency & token overhead |
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
| `gmais/governance/redaction.py` | 3.3.1 | Worker-to-worker need-to-know: named-entity redaction for bias control |
| `gmais/orchestrator.py` | 3.3.1 | Per-cell wiring of the pipeline |
| `gmais/metrics.py` | 3.3.4/3.3.5 | Confusion matrix, Brier, Security Tax (Eq. 3.2–3.8) |
| `gmais/noise.py` | 3.2.4 | Pre-registered observation-noise model (grading error, injection camouflage, peer anchoring) |
| `gmais/timing.py` | 3.3.4 | Wall-clock instrumentation (`perf_counter_ns`); measured vs modelled cost |
| `gmais/ablation.py` | 3.3.3 | Algorithm 1: the factorial ablation runner |
| `gmais/analysis.py` | 3.3.6/3.3.7 | Effect estimates, policy bands, non-parametric triangulation |
| `gmais/stats.py` | 3.3.6 | McNemar, Wilcoxon, exact Hodges–Lehmann intervals, bootstrap, Murphy decomposition, Holm |
| `gmais/hypotheses.py` | 3.3.6 | Confirmatory tests of H1–H4 with multiplicity control |
| `gmais/figures.py` | 4 | Publication figures (vector PDF + 300 dpi PNG) |
| `gmais/campaign.py` | 3.3 | One-command reproducible results package |
| `gmais/llm/` | 3.3.2 | Pluggable backends: Claude, OpenAI, local, deterministic mock |
| `gmais/llm/multi.py` | 3.3.2 | Round-robin multi-provider router with local fallback |
| `gmais/web_search.py` | 2.3.5 | Validator corroboration vs verified-source allowlist + analyst sources |
| `gmais/activity.py` | — | Operational activity recorder feeding the live SSE feed |
| `gmais/analytics_text.py` | 3.3 | Per-cell academic analytics narration |
| `gmais/webapp.py` | — | Flask operator console (runs, providers, web search, SSE, results) |
| `wsgi.py` | — | WSGI entry point for hosting on a cloud server (gunicorn) |

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

# Full reproducible results package: matrix, H1-H4 inference,
# 9 tables (Markdown + LaTeX), 9 figures, checksummed manifest  (~13 s)
python -m gmais.cli campaign --per-tier 45 --seed 20260605 --out results/
```

### Results package

`campaign` is the entry point for reproducing the reported evaluation:

```
results/
  observations.csv   540 x 31   the observation matrix
  security_tax.csv   540 x 9    per-observation ST, z-components, band
  results.json                  per-cell metrics + complete H1-H4 inference
  REPORT.txt                    human-readable campaign report
  MANIFEST.json                 seed, constants, platform, SHA-256 per artefact
  tables/  table1-9.{md,tex}    publication tables (LaTeX uses booktabs)
  figures/ fig01-09.{pdf,png}   vector + 300 dpi raster
```

Identical seed and configuration reproduce every **analytical** column bit for
bit. The eight `measured_*` wall-clock columns are hardware-dependent and are
exempted explicitly, both in `MANIFEST.json` and in the test suite.

See `paper/` for the write-up built on this package: `RESULTS.md` (Chapter Four),
`REPRODUCIBILITY.md`, `LIMITATIONS.md` and `RESPONSE_TO_REVIEWERS.md`.

### Web interface

```sh
python -m gmais.webapp        # http://localhost:5000
```

The interface is an **operator console**:

* **Manual run count** — enter the number of runs (scenarios; each is taken
  through all four cells) and press *Activate Run*.
* **Multi-provider LLM** — tick any combination of **Claude / OpenAI / local**.
  Calls are distributed **round-robin** across the selected providers and fall
  back to a local model on failure. Light models are the default (Claude Haiku,
  `gpt-4o-mini`).
* **Validator web search** — toggle corroboration against an allowlist of
  **verified government/institution sources** (`.gov`, `.mil`, `.int`, `un.org`,
  `who.int`, …), and paste **analyst-supplied sources** (`url | note`) for the
  Validator to use.
* **Live operational activity feed** — a Server-Sent-Events stream shows every
  behind-the-scenes step (ingest → worker spawn → Admiralty grading → web
  search → ACH → governance mediation → audit → scoring) in real time until the
  result renders.
* **Results** — an aggregate per-cell table, **each row annotated with an
  academic analytics description** of what it shows (which hypothesis it informs
  and how to read its figures), plus a **scenario-by-scenario Ground Truth
  Knowledge Graph** (claims, Admiralty grades, veracity, injection flags) for
  direct comparison against what each cell concluded.

Provider credentials (set the ones you use):

```sh
export ANTHROPIC_API_KEY=...        # Claude (light Haiku model)
export OPENAI_API_KEY=...           # hosted OpenAI (light gpt-4o-mini)
export GMAIS_LOCAL_BASE_URL=http://localhost:8080/v1   # local OpenAI-compatible server
```

### Deployment on a cloud server (no Docker)

A WSGI entry point (`wsgi.py`) is provided. On your host:

```sh
pip install -r requirements.txt
# Threaded workers are required so the SSE activity feed streams concurrently:
gunicorn -w 2 --threads 8 --timeout 120 -b 0.0.0.0:5000 wsgi:app
```

Tune the demo corpus size or backend via environment variables:
`GMAIS_WEB_PER_TIER` (default 5), `GMAIS_BACKEND` (`mock` | `openai`), `PORT`.
Put it behind nginx/Caddy for TLS as usual. (A typical systemd unit just runs
the `gunicorn` line above as your service `ExecStart`.)

### Worker-to-worker need-to-know (bias control)

Beyond agent→validator mediation, the Governance Layer enforces need-to-know on
**worker-to-worker** peer exchange: when a Worker shares its synthesis with
peers, proper-noun **named entities are redacted** (`Beronia` → `[ENTITY_2]`)
before transmission. Peers receive the analytical substance — claims,
corroboration, hypothesis support — but not the actor identities that could
anchor them to priors, reducing inter-agent bias and herding on a named party.
The `peer_bias_exposure` metric (entity mentions still visible to peers) drops
to zero under governance and is reported per observation.

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

This artefact implements the **architecture** and the full **frequentist
evaluation layer**: per-cell metrics, the Security-Tax distribution, factorial
effect estimates with bootstrap intervals, and confirmatory tests of H1–H4
(exact McNemar, Wilcoxon signed-rank with exact Hodges–Lehmann intervals, Wilson
intervals, the Murphy calibration decomposition) under Holm–Bonferroni
multiplicity control.

The thesis's **primary** inference is Bayesian hierarchical modelling with a
log-normal likelihood; that requires a PPL (Stan/PyMC) and is out of scope for
the offline core. The exported observation matrix is the input to that fit.

**Measured vs modelled.** Governance mediation, Admiralty grading, ACH, audit
chaining and redaction are really executed and really timed
(`time.perf_counter_ns`). Language-model inference latency and the distributed
deployment cost of a policy decision point are **cost models**, carried in
separate columns and never mixed into a measured figure. Point the harness at a
real backend (`--backend openai`) for end-to-end measured latency.

## Tests

```sh
python -m pytest tests/ -q        # 46 tests
```

## Legacy interface

The original single-prompt OpenAI analyst (`app.py`, `llm_engine.py`,
`intelligence_agents.py`, …) is retained for reference and still runs with an
`OPENAI_API_KEY`. GMAIS supersedes it with the governed, instrumented
multi-agent architecture above.

## License

MIT License.
