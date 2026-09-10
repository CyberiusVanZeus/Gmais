# Limitations and Practical Applicability

Addresses reviewer item 6. Limitations L1–L3 were discovered *by executing* the
campaign rather than anticipated in the design; they are stated first, and stated
plainly, because each of them bounds a claim the manuscript makes.

---

## L1 — The bounded-rationality stopping rule never engaged, so the cost estimates are upper bounds

**Evidence.** In **0 of 135** scenarios did the Validator halt before its
iteration cap; all 270 validated observations ran the full four critique
iterations. Observed ACH convergence peaked at **0.722** against a rule binding
at 0.75 (median 0.312). Compounding this, the critique loop is **idempotent**:
the ACH matrix is rebuilt each pass from unchanged evidence and unchanged
grades, so iterations 2–4 reproduce iteration 1 exactly.

**Consequence.** Roughly three-quarters of validation's cost — **≈672 tokens
(32.1% of Full-cell consumption)** and ~1,548 ms per observation — buys nothing.
**The H2 and H3 cost estimates are therefore upper bounds.** A Validator whose
loop genuinely refined its evidence, or whose stopping rule engaged, would show
materially lower validation cost and a smaller super-additive interaction. The
*direction* of every effect is unaffected, and the accuracy results are
untouched, since the analytical product is identical however many times the loop
runs.

**Not repaired here.** Re-tuning the convergence threshold after observing that
it never fires would convert a pre-registered constant into a post-hoc fitted
one. The correct fix is architectural — the critique loop must actually revise
its evidence between passes, e.g. by re-grading contested claims in light of the
previous pass's diagnosticity — and belongs to a subsequent design cycle, not to
a results chapter.

---

## L2 — End-to-end latency is modelled, not measured

**Evidence.** The campaign runs on a deterministic backend. Governance mediation,
Admiralty grading, ACH evaluation, audit chaining and redaction are all **really
executed and really measured** (≈85 µs/event, median of 9 campaigns, 39 ns clock
resolution). Time inside the language model is not: it comes from an explicit
cost model.

**Consequence.** The **relative** overheads (+3.77% latency, +6.94% tokens) are
computed against a modelled inference baseline. Under a real serving stack the
absolute latencies would be far larger and the *relative* governance overhead
correspondingly **smaller**, since the fixed mediation cost would be divided by a
much larger denominator. The reported relative latency tax is thus conservative —
it will not grow under real inference.

Token counts are on firmer ground: they are structural (message and metadata
volume), not timing-dependent.

**Mitigation.** The separation is enforced in the schema, not merely in prose:
`latency_ms` and `measured_*` are distinct columns, and no figure or table mixes
them. The artefact accepts a real backend (`--backend openai`, or any
OpenAI-compatible local server) and re-running the campaign against one is the
natural next step. We did not do so here: the credentials available did not
authenticate, and reporting model-served numbers we could not obtain would be
worse than reporting modelled ones we label honestly.

---

## L3 — The corpus failed one of its own pre-registered tolerances

**Evidence.** Flesch–Kincaid conformance is **0/135** (observed grade 16.23–17.90
against a pre-registered 8–12 band), and FK does not separate the tiers
(16.95 / 17.22 / 16.91).

**Consequence.** One of the five Section 3.2.2 normalisation dimensions is
inert. The stratification the campaign achieved is by **evidential volume** —
claim count, injection count, word count — not by linguistic complexity. Claims
about behaviour across "complexity tiers" should be read accordingly: they are
claims about how the system scales with *evidence volume*. This also weakens the
§3.2.2 argument that latency differentials reflect governance overhead rather
than input variance, since one controlled dimension was not in fact controlled.

Combined with the finding that the Security Tax is essentially flat across tiers
(§4.5), the practical impact on the conclusions is small — but the design claim
as written is not supported.

---

## L4 — The gold hypothesis is always the benign one

Every scenario fixes H1 (benign) as the gold answer, and injected claims always
push toward H2 (hostile). A system with a fixed prior favouring benign
explanations would therefore score well without doing any analysis. Worker
tie-breaking favours the lexicographically first hypothesis, which is H1 — so
part of the Baseline's 0.193 accuracy is structural rather than analytical.

This does not threaten the *contrasts* (all cells share the bias, and the design
is paired), but it does mean **absolute accuracy figures are not portable** and
should not be read as a system capability. A corpus balancing gold assignment
across benign and hostile outcomes is required before any absolute accuracy claim
is made.

---

## L5 — The Security Tax is corpus-relative and not comparable across studies

ST is a **z-score of cost differentials against a within-tier baseline**. Its
scale is defined entirely by the dispersion of the campaign that produced it.
An ST of +1.05 means "about one standard deviation above this corpus's mean
differential", not a transferable quantity.

The bands (0.5, 1.5) are therefore a **decision aid calibrated on this corpus,
not a validated deployment standard.** They must be re-derived per deployment.
The manuscript previously implied otherwise; §5.2 has been corrected.

What *is* transferable is the α-robustness result (§4.5): the band ordering is
stable across the full weighting sweep, so the *method* survives reweighting even
though the *values* do not travel.

---

## L6 — Single-seed campaign

All 540 observations come from one seed (20260605). The seed fixes both the
corpus and the noise draws, so reported intervals capture within-campaign
scenario variability but **not** between-corpus variability. The correct
robustness check is a multi-seed campaign with seed as a random effect. The
harness supports this (`--seed`); it was not run here.

---

## L7 — Simulated adversary and a two-tier topology

The injection model is a static corpus perturbation, not an adaptive adversary
responding to the defence. Real information operations adapt; camouflage rates
would not stay fixed at 0.18 once a defender starts filtering on provenance.
Detection results should be read as performance against a **non-adaptive**
adversary, which is an optimistic bound.

The architecture is likewise a specific two-tier topology with three workers and
one validator. Governance costs scale with the number of mediated events, which
is fixed by that topology (6 ungoverned, 12 governed). Denser topologies would
mediate more events and pay proportionally more — the per-event figure (112 µs)
transfers; the per-observation figure does not.

---

## L8 — Confidence is well-ordered but not well-calibrated

The Murphy decomposition (§4.2) shows validation improving the Brier score
entirely through **resolution** (0.000 → 0.158) while its **reliability term
worsens** (0.094 → 0.166). GMAIS's confidences discriminate correct from
incorrect judgements but are miscalibrated in level.

For intelligence work this distinction is not academic: a stated 0.85 confidence
that is empirically 0.72 will be read by a consumer as 0.85. The system's
confidences are usable for **ranking** competing products and **not** yet usable
as **absolute** probability statements in an assessment. Post-hoc recalibration
(isotonic or Platt scaling on a held-out split) is the obvious remedy and is not
implemented.

---

## L9 — Component-level timing attribution is below the measurement's resolving power

**Evidence.** Repeating the identical campaign nine times on one idle host: the
*total* mediation cost is stable to within 1.45× (68.8–99.9 µs/event), but
individual components swing by up to 3.6× and the component ranking is not
stable between runs. The audit chain's share of mediation ranges 27.4%–45.7%.

**Consequence.** The aggregate measurement is reportable; the component split is
not. Any claim of the form "component X dominates governance cost" is
unsupported by this instrumentation, and one such claim has been withdrawn from
an earlier draft of these results. The operations run in the tens of
microseconds, comparable to the perturbation from CPU frequency scaling and
cache state.

**Mitigation and remedy.** A 12-observation warm-up discard is applied per
campaign, which reduced the total's spread from 2.1× to 1.45×, and
`python -m gmais.cli timing --repeats N` makes the stability check
reproducible — a reader can confirm the instability rather than take it on
trust. Resolving components properly would require a dedicated microbenchmark
harness (pinned CPU, disabled frequency scaling, many thousands of isolated
iterations per component), not instrumentation embedded in a full campaign.

This limitation is methodological rather than architectural: it bounds what the
*measurement* can say, not what the system does.

---

# Practical applicability

What the evidence supports, and what it does not.

### Governance is cheap enough to deploy by default

Mediation costs **≈85 µs per inter-agent event** (median of 9 campaigns) and
**+3.77%** end-to-end latency, with audit-chain integrity holding across all 270 governed
observations. For any analytical workload with a human in the loop, a ~4%
latency increase for authenticated delegation, need-to-know enforcement and a
tamper-evident audit trail is not a meaningful trade. Both ungoverned cells sit
at 100% in the full-governance band. **The binding constraint is tokens (+6.94%),
not time** — governance costs money more than it costs latency, which inverts
the framing the manuscript began with.

### Do not optimise governance components on this evidence

An earlier draft reported the audit chain as 58.3% of mediation cost and
recommended that implementers optimise the cryptographic record rather than the
policy engine. **That recommendation is withdrawn.** Repeating the campaign nine
times, the audit chain's share ranges 27.4%–45.7% and the component ranking is
not stable between runs (L9). At the median it is the largest single component,
which is suggestive, but the measurement does not support a component-level
optimisation recommendation. What it does support is the aggregate: mediation
costs on the order of 10⁻⁴ s per event, which is what the deployment argument
needs.

### Do not justify governance on accuracy

The sub-additive interaction (§4.4) is the finding with the sharpest deployment
consequence. Governance improves accuracy by +0.140 without a Validator and by
**exactly zero** with one. Where structured validation is already present,
governance must be justified on **auditability, need-to-know and authenticated
delegation** — the properties validation does not provide — and not on
analytical quality. Conversely, in systems that cannot afford a validator,
need-to-know redaction is a **cheap partial substitute**: it recovers +0.140
accuracy for ~4% latency by closing the peer-anchoring pathway, and that is a
genuinely useful result for resource-constrained deployments.

### Deploying both costs more than the sum of the parts

Governance mediates validator traffic too, so combining the mechanisms is
super-additive on cost (+21.0 ms beyond additivity) while sub-additive on
benefit. Budget for the combination directly; do not add the separately measured
costs.

### What must be established before operational use

1. Re-run against a real inference backend (L2) and with multiple seeds (L6);
   resolve component timings on a dedicated harness if component-level
   optimisation is intended (L9).
2. Recalibrate confidence before any absolute probability is shown to a consumer
   (L8).
3. Re-derive the Security-Tax bands on the target deployment's own corpus (L5).
4. Rebuild the corpus with balanced gold assignment (L4) and a corrected
   readability profile (L3) before quoting absolute accuracy.
5. Fix the Validator's critique loop (L1) — the current implementation pays for
   four iterations and uses one.

None of these is a reason to withhold the architecture or the measurement
method, which are the contributions. They are the reasons the *numbers* should
be read as a characterisation of this artefact on this corpus rather than as
operational performance figures.
