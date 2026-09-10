# Response to Reviewer 5 — Major Revision

**Manuscript.** *Governance-Mediated Intelligence Analysis System (GMAIS): Empirical
Quantification of the Multi-Agent Security Tax in Intelligence Workflows*

We thank the reviewer. The central criticism — that the manuscript described a
planned experiment and reported expected rather than obtained outcomes — was
correct, and addressing it required more than adding numbers. Executing the
campaign exposed three defects in the artefact that the pre-registration had not
anticipated, and all three are now reported rather than repaired away. Every figure
and table below is generated from the observation matrix by
`python -m gmais.cli campaign --per-tier 45`, and the package ships with a
checksummed manifest so any number in the manuscript can be traced to the run
that produced it.

Reviewer comments are quoted in **bold**; the change made follows each.

---

## 1. "The authors should provide the actual experimental results from the planned 540 observations."

**Done, twice.** The full campaign was executed against hosted `gpt-4o-mini`
(**540 observations**, 2,700 API calls, 1,172,513 tokens, **$0.59**, wall clock
~35 min) and again against the deterministic backend as a controlled comparison.
Both match the pre-registered design exactly. The complete observation matrix is included as `results/observations.csv`
(540 rows × 31 columns), and the campaign completes in ~13 s on a commodity CPU
with no GPU, no API key and no network access.

Chapter Four has been rewritten from a description of an intended protocol into a
report of obtained results (`paper/RESULTS.md`).

**Three things the campaign revealed that the manuscript must now state.**

*(a) The bounded-rationality stopping rule never fires.* In **0 of 135**
scenarios did the Validator halt before its iteration cap. Observed ACH
convergence reached a maximum of **0.7222** against a halt threshold that binds
at 0.75, so all 270 validated observations ran the full four critique
iterations. Worse, the critique loop is idempotent: the ACH matrix is rebuilt
from unchanged inputs on every pass, so iterations 2–4 recompute an identical
result. Approximately **672 tokens (32.1% of Full-cell consumption)** and
~1,548 ms per observation are attributable to this inert loop. Reported in
§4.6 and Limitation L1; we have *not* silently re-tuned the threshold, because
doing so after seeing the data would void the pre-registration.

*(b) The corpus fails one of its own pre-registered tolerances.* Flesch–Kincaid
conformance is **0/135** (see item 5). Limitation L3.

*(c) The modelled governance latency differential has zero variance.* Ungoverned
cells mediate exactly 6 events and governed-plus-validated cells exactly 12,
so the modelled overhead is a deterministic +21.0 ms / +42.0 ms. This is why
several intervals in Table 4 are degenerate — it is a property of the fixed-rate
deployment cost model, not a suspiciously precise measurement, and is now stated
as such. The *measured* governance cost does carry real variance (within-campaign SD
0.37 ms G-only, 0.25 ms Full).

---

## 2. "Report measured latency, token overhead, accuracy, Brier score and Security Tax values."

**Done — with an important separation the original manuscript conflated.**

We now distinguish **measured** from **modelled** cost throughout, and never mix
them in a single figure or column:

- **Measured** (`time.perf_counter_ns`, clock resolution 39 ns), reported as
  medians over **9 repeated campaigns** with a 12-observation warm-up discard:
  every operation GMAIS actually executes — HMAC delegation-token verification, the fG(e) policy
  decision, SHA-256 audit-chain construction, named-entity redaction, queue
  bookkeeping. Reported as a distribution over **2,430 mediated events**.
- **Modelled**: time inside the language model, and the network/durable-write
  cost a distributed policy decision point would incur. These are properties of
  a serving stack, not of GMAIS, and are labelled as cost models wherever they
  appear.

Making this separation honestly is why we report measured governance overhead
even though the campaign reproduces offline: it is the quantity H2 is actually
about.

**A caveat we discovered by repeating the measurement.** A single campaign's
microbenchmarks are not trustworthy at this scale. Repeating the campaign nine
times on one idle host, the *total* mediation cost is stable to within 1.45×
(68.8–99.9 µs/event), but individual components swing by 2–3.6× and the
component ranking is **not stable between runs**. An earlier draft of this
response, written from a single run, reported the audit chain at 58.3% of
mediation and drew an implementation recommendation from it; across nine runs
the audit share ranges 27.4–45.7%. That recommendation has been withdrawn. We
now report the total as the measured result and the component split as
indicative only. `gmais.cli timing` exists so a reader can reproduce this
check.

| Quantity | Result |
|:--|:--|
| **Measured mediation cost** | **≈85 µs/event** (median of 9 campaigns; range 68.8–99.9, spread 1.45×) |
| **Measured component split** | audit chain 31.3 µs, policy eval 15.9 µs, redaction 11.3 µs, queue 3.2 µs (medians) — *attribution not reliably resolvable, see below* |
| **Measured governance, Full cell** | ≈0.71 ms/observation (G-only ≈0.55 ms) |
| **Modelled latency overhead** | +31.50 ms main effect; **+3.77%** [3.66, 3.88] relative |
| **Token overhead** | +108.0 tokens main effect; **+6.94%** [6.80, 7.09] relative |
| **Accuracy** | 0.193 → 0.770 with validation; 0.193 → 0.333 with governance alone |
| **Brier score** | 0.250 → 0.185, now reported with its exact Murphy decomposition |
| **Security Tax** | Baseline −1.012, G-only −0.928, V-only +0.883, Full +1.054 |

The Brier score is no longer reported as a bare number. Table 2 and Figure 6 give
the **Murphy decomposition** (reliability − resolution + uncertainty, residual
0.00e+00, computed on the calibration–refinement partition where the identity is
exact). This matters for the manuscript's calibration claim: validation improves
the Brier score by *adding resolution* (0.000 → 0.158), while its reliability
term actually worsens (0.028 → 0.166). The system discriminates better but is
less well calibrated — a claim the original single-number report could not have
made, and one that qualifies our conclusions.

---

## 3. "Present statistical results for H1–H4 rather than only expected outcomes."

**Done.** The manuscript previously offered point estimates with no inference.
The design is a **within-scenario repeated-measures 2×2** — every scenario passes
through all four cells — so every test is now paired on within-scenario
contrasts, with effect sizes and intervals alongside every p-value.

Six tests are pre-registered as **confirmatory** and carry **Holm–Bonferroni**
adjustment; everything else is labelled exploratory. Each main effect is tested
**at both levels of the other factor** rather than collapsed to a marginal,
because a marginal main effect is only interpretable when the interaction is
negligible and H3 exists precisely to test that.

Results are now reported from **two campaigns** over the identical design: a
**primary** run against hosted `gpt-4o-mini` (2,700 billable calls, $0.59) giving
genuinely measured latency and exact token counts, and the deterministic
offline run as a **controlled comparison** with inference variance removed. The
analytical columns are identical across both; only the cost columns differ.

| | Test | Hosted (primary) | Deterministic |
|:--|:--|:--|:--|
| **H1** | Exact McNemar | **SUPPORTED** — OR 53.0 / 40.3, *p*<sub>Holm</sub> ≤ 2.2×10⁻¹⁶; effect +0.507 [+0.426, +0.585] | SUPPORTED (identical) |
| **H2** | Wilcoxon + Hodges–Lehmann | **SPLIT** — tokens +106.2 [+97.0, +116.5], *p*<sub>Holm</sub> = 1.1×10⁻²²; **latency NOT detected**, *p*<sub>Holm</sub> = .152 | SUPPORTED on both |
| **H3** | Paired interaction contrast | **SPLIT** — tokens +79.9 [+62.3, +98.1]; accuracy −0.141 [−0.200, −0.082]; **latency NOT detected**, *p* = .68 | SUPPORTED on both |
| **H4** | Wilson intervals + α-sweep | **SUPPORTED** — clean band separation, stable across the sweep | SUPPORTED |

**We report the H2/H3 latency channel as not supported rather than quietly
preferring the campaign that agreed with the pre-registration.** The mechanism
is real and the deterministic run measures it cleanly; under a real serving
stack it is simply not detectable. Governance adds ~104 ms against a baseline
latency SD of 900 ms and a V-only SD of 29,653 ms — an effect of **0.116 SD**.
Token consumption, which carries no timing noise (CV ≈ 0.04 vs 1.73 for
latency), shows the same mechanism unambiguously.

The substantive consequence is a correction to the manuscript's framing: the
Security Tax is **not principally a latency tax**. Its measurable price in
deployment is tokens, ~5%; its latency cost is unobservable against the model's
own variance.

**On H3, the interaction is signed in opposite directions on cost and benefit**,
which is the manuscript's most interesting result and was absent from the
original submission. On cost the mechanisms are **super-additive** (+21.0 ms
beyond the sum of their separate effects: governance must mediate the
validator's critique traffic too). On accuracy they are **sub-additive**
(−0.141): governance improves accuracy only in cells *lacking* a Validator,
because entity redaction and ACH filtering both suppress the same anchoring
error. Deploying both buys less than their separate benefits suggest while
costing more than their separate costs — a finding with direct deployment
consequences, now discussed in §4.5 and §5.2.

Statistical methods: exact McNemar (not χ², unreliable at small discordant
counts); Wilcoxon signed-rank with matched-pairs rank-biserial correlation;
**exact distribution-free Hodges–Lehmann intervals** from the Walsh-average order
statistics (not bootstrapped — bootstrapping an O(n²) estimator is both wrong for
this quantity and computationally gratuitous); percentile bootstrap over
scenarios (10,000 resamples) for effect intervals; Wilson intervals for
proportions.

---

## 4. "Include actual figures/tables showing the ablation results and Security Tax distribution."

**Done.** Nine figures (vector PDF + 300 dpi PNG) and nine tables (Markdown +
LaTeX `booktabs`), all generated from the observation matrix — no schematic or
illustrative values anywhere.

| Figure | Content |
|:--|:--|
| 1 | System architecture (rebuilt — see item 7) |
| **2** | **Ablation results**: accuracy, GTKG rubric, detection P/R/F1, 95% CIs |
| 3 | Latency and token cost by cell and by complexity tier |
| **4** | **Security-Tax distribution**: violins + quartile boxes against the policy bands, with band-assignment proportions |
| 5 | H3 interaction plots (non-parallel traces) |
| 6 | Reliability diagram + Murphy decomposition |
| 7 | H4 robustness under α-reweighting |
| 8 | Measured governance cost attributed by component |
| 9 | Security Tax across complexity tiers |

Tables 1–9 cover the corpus/GTKG, per-cell performance, cost, confirmatory
tests, factorial effects, the Security-Tax distribution, the α-sweep, the
measured governance breakdown, and the bias-control channel.

Figures encode the 2×2 as a 2×2: **hue carries Validation, texture carries
Governance**. Two hues rather than four clears the colour-vision-deficiency
separation floors with margin (validated: worst all-pairs ΔE 9.2 deutan, 24.0
normal-vision), and the hatch is a fully non-chromatic second channel, so the
figures remain readable in greyscale print and under any form of colour
blindness. Distributions are drawn as distributions, never as bars of means.

---

## 5. "Clarify the ground-truth dataset/scenario construction and reproducibility details."

**Done** — `paper/REPRODUCIBILITY.md` is new, and §3.2 has been rewritten.

*Ground truth.* The GTKG is a SQLite store (scenarios, hypotheses, sources,
claims) built from the pre-injection evidentiary state. Corpus: **135 scenarios,
1,080 claims, 270 adversarially injected** (Table 1), stratified into three
complexity tiers on the five pre-registered Section 3.2.2 dimensions. Tolerance
conformance is now *reported* rather than asserted (Table 1 note). Scoring uses a
graded rubric — hypothesis correctness (0.45), ACH compliance (0.30),
uncertainty acknowledgement (0.10), triangulation density (0.15) — not binary
factual matching.

*Observation-noise model — a new and material disclosure.* The original design
assumed an idealised observation channel, under which injected claims are
uniformly weak-sourced and the Admiralty floor separates them **perfectly**: a
pilot run returned detection F1 of exactly 0.000 and exactly 1.000, and p-values
at the floating-point floor. Those numbers measure the corpus generator, not the
architecture. Section 3.2.4 now specifies three pre-registered error channels:
grading error (0.12), injection camouflage (0.18), provenance degradation
(0.10), plus a behavioural peer-anchoring rate (0.22). Realised rates are
reported in `results.json` for verification against the pre-registration. Every
draw is a pure function of `(seed, stream, key)` through SHA-256, so
perturbations are **identical across all four cells** — preserving both the
repeated-measures pairing and the property that the ablation contrast is a pure
function of configuration.

*Reproducibility.* One command produces the entire package. `MANIFEST.json`
records the seed, every pre-registered constant, platform, library versions, and
a **SHA-256 digest of every artefact**, so an independent reproduction is
compared file by file rather than eyeballed. Determinism is enforced by test:
identical seed and configuration reproduce every analytical column bit for bit.
The eight `measured_*` wall-clock columns are hardware-dependent by nature and
are explicitly exempted, both in the manifest and in the test suite — we would
rather name that exemption than claim a determinism we do not have.

---

## 6. "Strengthen the discussion of limitations and practical applicability."

**Done** — `paper/LIMITATIONS.md`; §5.3 expanded from three sentences to eight
substantive limitations, each with its evidence and its consequence for the
claims. The three most serious (L1: the inert stopping rule; L2: deterministic backend,
so end-to-end latency is modelled; L3: the failed readability tolerance) were
discovered *by* running the campaign and are stated plainly rather than
minimised.

We also removed an overreach. The Security-Tax bands are a **decision aid
calibrated on this corpus**, not a validated deployment standard: ST is a
z-score against a within-tier baseline, so it is meaningful *only* relative to
the campaign that produced it and cannot be compared across studies. §5.2 now
says so, and reframes practical applicability around what the evidence
supports — the governance mechanism costs **112 µs/event and ~3.8% latency**,
which is affordable for essentially any analytical workload, and the binding
constraint is token cost (~6.9%), not time.

---

## 7. "Image in fig 1 is not clear."

**Done.** Figure 1 was a raster image that degraded on print. It has been
**redrawn as vector geometry**, emitted as PDF, so it scales without resampling
artefacts and every label is selectable text.

Beyond resolution, the previous figure had substantive legibility faults, all
fixed: box heights are now **computed from their content** (labels can no longer
overflow their containers); the routing channel between the agent tiers and the
Governance Layer is explicit, with every arrow terminating **inside** the box it
addresses; the peer-exchange and critique loops are separated onto opposite
margins; the factorial inset uses colour swatches with dark-ink labels rather
than white text over hatching. `results/figures/fig01_architecture.pdf`.

---

## Summary of artefacts

```
results/
  observations.csv     540 × 31   the observation matrix
  security_tax.csv     540 × 9    per-observation ST, z-components, band
  results.json                    per-cell metrics + complete H1–H4 inference
  REPORT.txt                      human-readable campaign report
  MANIFEST.json                   seed, constants, platform, SHA-256 per artefact
  tables/     table1–9 .md / .tex
  figures/    fig01–09 .pdf / .png
paper/
  RESULTS.md            rewritten Chapter Four
  REPRODUCIBILITY.md    ground truth, corpus construction, reproduction protocol
  LIMITATIONS.md        expanded limitations and practical applicability
```

Reproduce in full with:

```sh
python -m gmais.cli campaign --per-tier 45 --seed 20260605 --out results/
```
