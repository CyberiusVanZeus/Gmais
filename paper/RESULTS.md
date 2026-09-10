# Chapter Four — Results

## 4.0 Two campaigns

This chapter reports **two** campaigns over the identical 540-observation design,
because they answer different questions and disagree in an informative way.

| | Backend | What it establishes |
|:--|:--|:--|
| **Primary** | hosted `gpt-4o-mini`, 2,700 billable calls, $0.59 | Obtained results under **real inference**, with genuinely measured end-to-end latency and exact API token counts |
| **Controlled comparison** | deterministic offline backend | The same design with inference-time variance removed, isolating the governance mechanism's own cost |

The analytical columns are **identical across both** — accuracy 0.1926 / 0.7704 /
0.3333 / 0.7704 in either run — because the tradecraft logic is Python and does
not consume model output (see L10). The backends differ only in the cost columns.
That is precisely what makes the pair informative: the deterministic campaign
measures the governance mechanism, and the hosted campaign measures whether that
cost is *detectable* in deployment.

**The headline result of the pair is that it is not, on the latency channel.**
Governance adds ~104 ms; real inference latency has a standard deviation of
900 ms at baseline and 29,653 ms under validation. The effect is **0.116 SD** —
real, but buried. On the token channel, which carries no timing noise, the same
mechanism is unmistakable.

Results below are from the **primary (hosted)** campaign unless labelled
otherwise.

---

All results in this chapter come from a single campaign executed with

```sh
python -m gmais.cli campaign --per-tier 45 --seed 20260605 --out results/
```

producing **540 observations**: 135 scenarios (45 per complexity tier) taken
through each of the four factorial cells. Numbers are quoted from
`results/results.json`; tables and figures are generated from
`results/observations.csv` and reproduced in `results/tables/` and
`results/figures/`.

Throughout, **measured** and **modelled** quantities are kept apart. Measured
figures are real elapsed wall-clock time through code GMAIS executes, taken with
`time.perf_counter_ns` (measured clock resolution 39 ns). Modelled figures come
from an explicit cost model — for language-model inference, and for the
network and durable-write cost a distributed policy decision point would incur.
Both are legitimate, but only the first is a measurement, and no table or figure
mixes them.

---

## 4.1 Corpus and ground truth

The Ground-Truth Knowledge Graph holds **135 scenarios, 270 hypotheses, 1,080
claims** and their source records, of which **270 claims (25.0%) are
adversarially injected** (Table 1). Injection density rises with tier by design
(0.200 low, 0.250 medium, 0.273 high).

Of the three checkable Section 3.2.2 tolerances, two hold at 100% (temporal span
≤ 72 h; ambiguity index in [0.15, 0.35]) and **one fails outright**:
Flesch–Kincaid conformance is **0/135**, with observed grade level 16.23–17.90
against a pre-registered 8–12 band. Readability also fails to separate the tiers
(median FK 16.95 / 17.22 / 16.91). The stratification that the campaign actually
achieved is therefore one of *evidential volume* — claim count, injection count,
word count — and not of linguistic complexity. This is reported rather than
corrected, since re-tuning the generator after seeing the data would void the
pre-registration; its consequences are taken up in Limitation L3.

The observation channel is perturbed by the pre-registered noise model of
Section 3.2.4. Realised rates match their targets: camouflage 0.219 (target
0.18), provenance degradation 0.095 (target 0.10).

---

## 4.2 H1 — Validation and analytical accuracy

> *Embedding structured validation raises analytical accuracy relative to an
> unvalidated multi-agent baseline.*

**H1 is SUPPORTED.**

Hypothesis accuracy rises from **0.193** (Baseline) to **0.770** (V-only), and
from 0.333 (G-only) to 0.770 (Full). Because the design is paired within
scenario, the confirmatory test is an **exact McNemar** test on discordant pairs:

| Contrast | Discordant (b-only / a-only) | Odds ratio | *p* | *p*<sub>Holm</sub> |
|:--|--:|--:|--:|--:|
| Baseline → V-only (G = 0) | 79 / 1 | 53.0 | < .0001 | < .0001 |
| G-only → Full (G = 1) | 60 / 1 | 40.3 | < .0001 | < .0001 |

The validation main effect on accuracy is **+0.507 [+0.426, +0.585]** (95%
bootstrap over scenarios). On the graded GTKG rubric — which credits ACH
compliance, uncertainty acknowledgement and triangulation rather than only
hypothesis correctness — the shift is **+0.475 [+0.450, +0.525]**
(rank-biserial *r* = 0.994).

Detection of injected claims is the mechanism. Unvalidated cells emit no
detections at all (precision, recall, F1 = 0 by construction: the Worker tier
performs no source assessment). Validated cells achieve **precision 0.985,
recall 0.722, F1 0.833**. The recall shortfall is exactly what the noise model
predicts: 21.9% of injected claims arrive laundered through plausible-looking
provenance, and those are the ones the Admiralty floor lets through. Detection is
therefore hard but not intractable — which is the point of introducing the
channel at all (§3.2.4).

**Calibration.** The Brier score improves from 0.250 to 0.185. Reported alone,
that number would overstate the case. The Murphy decomposition (exact; residual
0.00e+00) shows *why* it improves:

| Cell | Brier | Reliability ↓ | Resolution ↑ | Uncertainty |
|:--|--:|--:|--:|--:|
| Baseline | 0.2500 | 0.0945 | 0.0000 | 0.1555 |
| G-only | 0.2500 | 0.0278 | 0.0000 | 0.2222 |
| V-only | 0.1849 | 0.1664 | 0.1584 | 0.1769 |
| Full | 0.1849 | 0.1664 | 0.1584 | 0.1769 |

Validation buys its improvement entirely through **resolution** (0.000 → 0.158):
the Validator's confidence discriminates correct from incorrect judgements, which
the fixed 0.5 confidence of an unvalidated cell cannot do at all. But its
**reliability term worsens** (0.094 → 0.166) — the stated confidences are
systematically miscalibrated relative to observed frequency, visible as
departure from the diagonal in Figure 6. The thesis's calibration claim must
therefore be narrowed: GMAIS produces confidences that *rank* well but are not
*well calibrated in level*, and the manuscript should not claim the latter.

---

## 4.3 H2 — Governance overhead

> *Governance mediation imposes a measurable and quantifiable latency and token
> overhead.*

**H2 is SPLIT: SUPPORTED on tokens, NOT SUPPORTED on latency.**

This is the chapter's most important correction to the pre-registered
expectation, and it only became visible under real inference.

| Channel | Effect | Test | Verdict |
|:--|:--|:--|:--|
| **Tokens** | **+106.2 [+97.0, +116.5]**, +5.07% relative | *p*<sub>Holm</sub> = 1.1×10⁻²² | **SUPPORTED** |
| **Latency** | +103.9 ms [−0.4, +217.9] (V=0); +215.4 [−127.1, +505.1] (V=1) | *p*<sub>Holm</sub> = .152 / .378 | **NOT SUPPORTED** |

The reason is signal-to-noise, not absence of effect:

| Cell | Latency mean | Latency SD | CV | Token mean | Token SD | CV |
|:--|--:|--:|--:|--:|--:|--:|
| Baseline | 3,405 ms | 900 | 0.26 | 1,372 | 84 | 0.061 |
| G-only | 3,561 ms | 940 | 0.26 | 1,439 | 86 | 0.060 |
| V-only | 17,155 ms | 29,653 | **1.73** | 2,972 | 121 | 0.041 |
| Full | 15,628 ms | 7,772 | 0.50 | 3,118 | 117 | 0.037 |

Token consumption is almost noiseless (CV ≈ 0.04–0.06) because it is structural:
message and metadata volume are fixed by the topology. Latency under a hosted
API is not — the coefficient of variation reaches 1.73 in the V-only cell, where
four sequential critique calls each carry independent queueing and scheduling
delay. The governance latency effect is **0.116 baseline SD**; the campaign is
not powered to detect it, and the main-effect interval is correspondingly
useless (−685.9 ms [−3,710.7, +1,178.4], point estimate negative through noise
alone).

**Deployment reading:** governance's latency cost is not merely affordable, it
is *unobservable* against the model's own variance. Its real, measurable price
is tokens — about 5%. The manuscript's framing of the Security Tax as principally
a latency tax is not supported by evidence from a real serving stack.

Against the deterministic backend, where inference variance is removed by
construction, the same mechanism is cleanly detectable on both channels
(*p*<sub>Holm</sub> < .0001, +3.77% latency, +6.94% tokens). Both statements are
true; they measure different things.

### Measured cost

Governance mediation was timed over **2,430 mediated events per campaign**,
repeated across **9 campaigns** with a 12-observation warm-up discard
(`python -m gmais.cli timing --per-tier 45 --repeats 9`).

End-to-end mediation costs **≈85 µs per event** (median; range 68.8–99.9 across
the nine campaigns, spread 1.45×). Per observation, measured governance costs
**≈0.71 ms** in the Full cell and ≈0.55 ms in G-only.

| Component | Median µs/event | Range | Spread |
|:--|--:|:--|--:|
| Audit chain (SHA-256 append + verify) | 31.3 | 22.5 – 44.8 | 2.0× |
| Policy evaluation fG(e) + HMAC verify | 15.9 | 12.6 – 33.1 | 2.6× |
| Named-entity redaction | 11.3 | 9.5 – 32.5 | 3.4× |
| Mediation-queue bookkeeping | 3.2 | 2.9 – 10.3 | 3.6× |
| **End-to-end** | **84.5** | **68.8 – 99.9** | **1.45×** |

**The component attribution is not reliably resolvable and should not be relied
on.** The total is stable to within 1.45×, but individual components swing by up
to 3.6× between otherwise identical runs, and the component *ranking* is not
stable across the nine campaigns: the audit chain's share of mediation ranges
27.4%–45.7%. At the median the audit chain is the largest single component, but
this is an indication, not an established result, and no implementation
recommendation is drawn from it. The operations being timed run in the tens of
microseconds, close enough to the effects of CPU frequency scaling and cache
state that separating them would need a dedicated microbenchmark harness rather
than instrumentation embedded in a full campaign.

What the measurement does support is the aggregate: **governance mediation costs
on the order of 10⁻⁴ s per inter-agent event**, which is the quantity the
deployment argument in §5 rests on.

### Modelled cost and relative overhead

| Quantity | Estimate | 95% CI |
|:--|--:|:--|
| Governance main effect, latency | +31.50 ms | [+31.50, +31.50] |
| Governance main effect, tokens | +108.0 | [+108.0, +108.0] |
| **Relative latency overhead** | **+3.77%** | [+3.66, +3.88] |
| **Relative token overhead** | **+6.94%** | [+6.80, +7.09] |

All three confirmatory tests reject at *p*<sub>Holm</sub> < .0001 with
rank-biserial *r* = 1.00: governance raised cost in **every one of the 135
scenarios**, without exception.

The degenerate intervals on the absolute effects require comment, since a
reviewer is right to be suspicious of a CI of zero width. They are a property of
the cost model, not a measurement artefact: ungoverned cells mediate exactly 6
events and governed-and-validated cells exactly 12, so at a fixed 3.5 ms per
event the modelled differential is arithmetically constant. The *measured*
governance cost, which is a genuine measurement, has real dispersion within a
campaign (SD 0.37 ms G-only, 0.25 ms Full) as well as
between campaigns (§4.3). Where governance overhead is reported with a range
elsewhere in this chapter, it is the measured quantity.

**Audit integrity held across all 270 governed observations** — no chain
verification failed.

---

## 4.4 H3 — The V × G interaction

> *Validation and governance interact rather than combining additively.*

**H3 is SPLIT, on the same channel logic as H2**: the interaction is
unmistakable on tokens (+79.9 [+62.3, +98.1], *p* = 7.9×10⁻¹³) and undetectable
on latency (*p*<sub>Holm</sub> = .68, interval −7,667 to +1,954 — pure noise).
The accuracy interaction stands at **−0.141 [−0.200, −0.082]**.

Read on the channels where it is measurable, the finding is unchanged and
remains the campaign's most consequential: the interaction is **signed in
opposite directions on cost and on benefit**.

The interaction contrast is formed within each scenario as
(Full − V-only) − (G-only − Baseline), giving 135 values tested against zero:

| Outcome | Interaction | 95% CI | Sign |
|:--|--:|:--|:--|
| Latency (ms) | **+21.00** | [+21.00, +21.00] | super-additive |
| Tokens | **+72.00** | [+72.00, +72.00] | super-additive |
| Accuracy | **−0.141** | [−0.200, −0.082] | sub-additive |

*(latency: p<sub>Holm</sub> < .0001, confirmatory; tokens and accuracy exploratory)*

**On cost, the mechanisms compound.** Adding governance to a validated system
costs +42.0 ms, twice the +21.0 ms it costs an unvalidated one, because the
Governance Layer must mediate the Validator's critique traffic in addition to
worker traffic — 12 events rather than 6.

**On accuracy, they are redundant.** Governance improves accuracy by +0.140 when
no Validator is present (0.193 → 0.333) and by **exactly zero** when one is
(0.770 → 0.770). The pathway is specific and traceable: without mediation,
worker-to-worker peer traffic carries the actor's name, and a Worker doing no
source validation herds onto the entity-anchored hypothesis. Need-to-know
redaction masks the name and closes that pathway — anchored workers fall from a
mean of 0.541 per observation to **0** under governance, and peer bias exposure
to 0 (Table 9). But ACH filtering already suppresses the same error, so where a
Validator is present the governance benefit has nothing left to remove.

The deployment consequence is stated directly: **deploying both mechanisms costs
more than the sum of their separate costs while buying less than the sum of
their separate accuracy benefits.** Governance must therefore be justified on
what validation does *not* provide — auditability, need-to-know enforcement,
authenticated delegation — and not on analytical accuracy, for which it is
largely redundant once validation is in place.

---

## 4.5 H4 — Security Tax and policy bands

> *The Security Tax partitions configurations into interpretable policy bands.*

**H4 is SUPPORTED.**

With the pre-registered weighting (α = β = 0.5) and bands at 0.5 and 1.5:

| Cell | Mean ST | Median ST [95% CI] | SD | Modal band | Share |
|:--|--:|:--|--:|:--|--:|
| Baseline | −1.014 | −1.012 [−1.035, −0.974] | 0.133 | full governance | 100% |
| G-only | −0.929 | −0.928 [−0.950, −0.889] | 0.133 | full governance | 100% |
| V-only | +0.887 | +0.883 [+0.821, +0.939] | 0.237 | adaptive governance | 95% |
| Full | +1.056 | +1.054 [+0.985, +1.109] | 0.237 | adaptive governance | 97% |

The bands separate the configurations cleanly (Figure 4). Governance alone sits
deep in the full-governance band: its cost is low enough that there is no reason
not to deploy it. Validation is what moves a configuration into the adaptive
band, and the Full cell sits highest.

**The ordering is robust to the weighting.** Under an α-sweep from 0 (tokens
only) to 1 (latency only), every cell retains its band assignment at every value
tested (Table 7, Figure 7) — the recommendation does not depend on the
pre-registered choice of α.

**The tax does not, however, scale with complexity.** Median ST for the Full
cell is 1.033 (low), 1.082 (medium), 1.061 (high) — essentially flat, and not
monotonic (Figure 9). This is partly by construction: ST is z-standardised
*within tier*, so a differential that grows in absolute terms with problem size
is renormalised away. It is also substantive: the number of mediated events is
fixed by the agent topology (6 ungoverned, 12 governed) and does not grow with
claim count, so governance overhead is close to constant per analysis while the
analysis itself gets longer. The practical reading is that **the Security Tax is
a property of the configuration, not of the problem** — which is convenient for
policy (one band assignment covers the workload) but means ST should not be
compared across corpora or studies, since the z-standardisation makes it
meaningful only relative to the campaign that produced it.

---

## 4.6 The bounded-rationality stopping rule did not operate

The Validator is specified to halt when ACH convergence ≥ 0.85 or the confidence
interval narrows below 0.15, capped at four critique iterations (§2.1, §3.3).
**In 0 of 135 scenarios did it halt early.** All 270 validated observations ran
the full four iterations.

The cause is that observed ACH convergence never approaches the threshold:
median 0.312, maximum **0.722**, against a rule that binds at 0.75. The
satisficing halt is therefore unreachable on this corpus with these thresholds.

A second and more serious defect compounds it: **the critique loop is
idempotent.** The ACH matrix is rebuilt on each pass from the same surviving
evidence and the same Admiralty grades, so iterations 2–4 recompute a result
identical to iteration 1. They consume tokens and latency and change nothing.

The cost is quantifiable. Validation adds 895.6 tokens and 2,064.5 ms per
observation over baseline; roughly three-quarters of that — **≈672 tokens, 32.1%
of Full-cell token consumption**, and ~1,548 ms — is attributable to redundant
recomputation. **The H2 and H3 cost estimates are therefore upper bounds**: a
Validator whose critique loop genuinely refined its evidence, or whose stopping
rule engaged, would show materially lower validation cost, and the super-additive
interaction of §4.4 would shrink accordingly. The *direction* of every effect is
unaffected, and the accuracy results are untouched, since the analytical product
is identical whether the loop runs once or four times.

This defect was found by executing the campaign, not by inspection, and is
carried into Limitations as L1.

---

## 4.7 Summary

| Hypothesis | Verdict | Principal evidence |
|:--|:--|:--|
| **H1** Validation raises accuracy | **SUPPORTED** (both campaigns) | +0.507 [+0.426, +0.585]; McNemar OR 53.0 / 40.3, *p*<sub>Holm</sub> ≤ 2.2×10⁻¹⁶ |
| **H2** Governance imposes measurable overhead | **SPLIT** — tokens SUPPORTED, latency NOT | Tokens +106.2 [+97.0, +116.5], *p*<sub>Holm</sub> = 1.1×10⁻²²; latency *p*<sub>Holm</sub> = .152, effect 0.116 SD |
| **H3** The mechanisms interact | **SPLIT** — tokens SUPPORTED, latency NOT | Tokens +79.9 [+62.3, +98.1]; accuracy −0.141 [−0.200, −0.082]; latency *p* = .68 |
| **H4** ST maps to policy bands | **SUPPORTED** (both campaigns) | Clean band separation, stable across the full α-sweep |

Under the deterministic backend H2 and H3 are supported on **both** channels; the
split appears only under real inference, and is a statement about detectability
in deployment rather than about the mechanism.

Three caveats travel with these conclusions and are developed in
`LIMITATIONS.md`: the cost estimates are upper bounds because the Validator's
stopping rule never engaged (L1); end-to-end latency is modelled rather than
measured because the campaign ran on a deterministic backend (L2); and the
corpus failed its own readability tolerance, so one stratification dimension is
inert (L3).
