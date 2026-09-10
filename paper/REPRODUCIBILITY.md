# Reproducibility: Ground Truth, Corpus Construction and Reproduction Protocol

Addresses reviewer item 5. The claim this document supports is narrow and
checkable: **every number in Chapter Four is regenerable from a seed with one
command, and any deviation is localisable to a named file.**

---

## 1. Reproducing the campaign

```sh
git clone <repository> && cd Gmais
python -m pip install -r requirements.txt      # core needs stdlib only
python -m gmais.cli campaign --per-tier 45 --seed 20260605 --out results/
```

Runtime ≈ 13 s on a commodity CPU. No GPU, no API key, no network access.
`--no-figures` drops the matplotlib requirement entirely.

### What is produced

| Artefact | Contents |
|:--|:--|
| `observations.csv` | 540 × 31 — the observation matrix |
| `security_tax.csv` | 540 × 9 — per-observation ST, z-components, band |
| `results.json` | per-cell metrics + the complete H1–H4 inference |
| `REPORT.txt` | human-readable campaign report |
| `MANIFEST.json` | seed, all constants, platform, library versions, SHA-256 per artefact |
| `tables/table1–9.{md,tex}` | publication tables (LaTeX uses `booktabs`) |
| `figures/fig01–09.{pdf,png}` | vector + 300 dpi raster |

### Verifying a reproduction

`MANIFEST.json` carries a SHA-256 digest of every artefact, so a reproduction is
checked file by file rather than by eye:

```sh
python - <<'PY'
import hashlib, json
m = json.load(open("results/MANIFEST.json"))
for name, rec in m["artefacts"].items():
    got = hashlib.sha256(open(f"results/{name}","rb").read()).hexdigest()
    print(("OK   " if got == rec["sha256"] else "DIFF "), name)
PY
```

**Determinism guarantee and its one exemption.** Identical seed and
configuration reproduce every *analytical* column bit for bit; this is enforced
by `tests/test_gmais.py::test_ablation_is_deterministic`. The eight `measured_*`
wall-clock columns are measurements of the host machine and **will** differ
between runs and between machines. They are named explicitly in
`MANIFEST.json → reproduce.hardware_dependent_columns`. We state the exemption
rather than claim a determinism the artefact does not have.

---

## 2. The Ground-Truth Knowledge Graph (§3.2.1)

The GTKG is the authoritative reference against which every output is scored — a
SQLite store over four tables, built from the **pre-injection evidentiary
state**, so ground truth is fixed before any adversarial content exists.

| Table | Key | Contents |
|:--|:--|:--|
| `scenarios` | `sid` | tier, gold hypothesis, prose |
| `hypotheses` | `(sid, hid)` | competing hypotheses (≥ 2 per scenario, mutually exclusive) |
| `sources` | `(sid, cid)` | provenance + Admiralty reliability × credibility |
| `claims` | `cid` | text, veracity, **injection flag**, hypothesis supported |

Realised corpus: **135 scenarios · 270 hypotheses · 1,080 claims · 270 injected
(25.0%)**.

### Scoring rubric

Grading is deliberately not binary factual matching, because intelligence
tradecraft judges the *process* as well as the answer:

| Component | Weight | Definition |
|:--|--:|:--|
| Factual accuracy | 0.45 | selected hypothesis == gold |
| ACH compliance | 0.30 | injected claims rejected, penalised 0.5× for over-rejection |
| Uncertainty acknowledgement | 0.10 | a calibrated confidence in (0, 1) was supplied |
| Triangulation density | 0.15 | share of accepted claims with ≥ 2 independent corroborations |

The false-positive penalty matters: a system that flags everything scores no
better than one that flags nothing.

---

## 3. Scenario construction (§3.2.2)

Each scenario is an OSINT problem: sourced claims, some adversarially injected,
and two competing hypotheses with a known gold answer. Generation is
deterministic in the campaign seed.

**Per-tier shape.**

| Tier | Sources | True claims | Injected | Target ambiguity | Target words |
|:--|--:|--:|--:|--:|--:|
| Low | 3 | 4 | 1 | 0.18 | 180 |
| Medium | 5 | 6 | 2 | 0.26 | 260 |
| High | 7 | 8 | 3 | 0.33 | 360 |

**Entities.** Actors and reporters are drawn from a fictional pool (Aldoria,
Beronia, …) so the corpus exercises named-entity redaction without invoking real
actors or triggering analyst priors about real states.

**Hypotheses.** Each scenario pairs a benign explanation (H1, always the gold
answer) with a hostile one (H2). Injected claims push toward H2. The gold answer
is fixed at H1 by construction, which is a design limitation in its own right —
see L4 in `LIMITATIONS.md`.

**Blinding (§3.2.3).** Injected claims are structurally distinguishable from
genuine ones only through their source record — weak provenance, no
corroboration, contradiction by established evidence — never through their
position, their identifiers or their phrasing. The claim list is shuffled before
the prose is assembled.

**Complexity metrics.** Five pre-registered dimensions are computed per
scenario: word count, named-entity density, Flesch–Kincaid grade, temporal span,
ambiguity index.

**Realised conformance — including one failure.**

| Tolerance | Requirement | Conformance |
|:--|:--|--:|
| Temporal span | ≤ 72 h | **100%** |
| Ambiguity index | 0.15 – 0.35 | **100%** |
| Flesch–Kincaid | 8 – 12 | **0%** |

Observed FK grade is 16.23–17.90 (median 17.03), and does not separate the tiers
(16.95 / 17.22 / 16.91). The generator's template prose is too syntactically
dense for the target band. **The stratification the campaign achieved is by
evidential volume, not linguistic complexity.** This is reported, not corrected:
re-tuning the generator after observing the results would void the
pre-registration. See L3.

---

## 4. The observation-noise model (§3.2.4)

This section is new and material to interpreting the results.

**Why it exists.** GMAIS grades sources with a deterministic function of the
source record. Run against an idealised observation channel — where every
injected claim is weak-sourced, uncorroborated and contradicted — the Admiralty
floor separates injected from genuine claims *perfectly*. A pilot run returned
detection F1 of **exactly 0.000** without validation and **exactly 1.000** with
it, and every paired test at the floating-point floor. Those numbers measure the
corpus generator, not the architecture.

The response is not to weaken the architecture but to stop assuming a perfect
observation channel. Three documented error modes are injected:

| Channel | Rate | Justification | Realised |
|:--|--:|:--|--:|
| Grading error (±1 Admiralty step, axes independent) | 0.12 | Baker, McKendry & Mace (1968) | — |
| Injection camouflage (laundered provenance) | 0.18 | competent adversaries do not publish anonymously | **0.219** |
| Provenance degradation (genuine but poorly sourced) | 0.10 | real reporting is not uniformly well-sourced | **0.095** |
| Peer anchoring (behavioural, not observational) | 0.22 | the herding the Governance Layer exists to interrupt | — |

**Determinism contract.** Every draw is a pure function of
`(seed, stream, key parts)` through SHA-256. Three consequences follow, and all
three are load-bearing:

1. A campaign is bit-for-bit reproducible from its seed.
2. A given claim is perturbed **identically in all four cells** — so the ablation
   contrast remains a pure function of configuration, and the repeated-measures
   pairing the paired tests depend on is preserved.
3. No global RNG state is consumed, so thread scheduling in the concurrent
   Worker tier cannot perturb the draw sequence.

Ground truth is never touched. Camouflage changes what the system *observes*;
`Claim.is_injected` in the GTKG is unaffected, which is what allows detection to
genuinely fail. Enforced by `test_noise_leaves_ground_truth_untouched`.

Set `noise_enabled=False` to recover the idealised channel.

---

## 5. Measurement protocol (§3.3.4)

**Measured** — `time.perf_counter_ns`, the highest-resolution monotonic clock
available; measured resolution on the campaign host **39 ns**. Timed
independently: worker tier, validator, policy evaluation, audit chain,
redaction, queue. Redaction is timed by the callee and *re-attributed* out of the
enclosing policy measurement so it is never double-counted
(`test_timing_reattribution_does_not_double_count`).

Individual operations run in the microsecond range, near the clock floor, so no
single sample is trusted. Two safeguards apply. Within a campaign, the first 12
governed observations are discarded as warm-up (cold caches and first-touch
allocation otherwise bias the mean, and bias it unevenly across components); the
remaining **2,430 per-event samples** are aggregated. Across campaigns, the
measurement is repeated:

```sh
python -m gmais.cli timing --per-tier 45 --repeats 9 --out results/timing.json
```

This reports each component's median, range and spread ratio, and whether the
component ranking was stable. It is how the instability documented in Limitation
L9 was found — the total is stable to 1.45×, the per-component split is not — and
it is included so a reader can reproduce that check rather than accept a single
run's numbers.

**Modelled** — inference latency (a property of the serving stack) and the
deployment governance cost model (3.5 ms per event plus a 6.0 ms serialisation
penalty, standing for the network hop to a policy decision point and a durable
audit append that an in-process implementation does not incur). These are cost
models and are labelled as such wherever they appear.

The two are carried in separate columns and never combined in one figure.

---

## 6. Statistical protocol (§3.3.6)

The design is a **within-scenario repeated-measures 2×2**; the resampling and
pairing unit is therefore the scenario, never the observation.

| Purpose | Method | Rationale |
|:--|:--|:--|
| Paired binary accuracy | Exact McNemar | χ² approximation unreliable at small discordant counts |
| Paired continuous cost | Wilcoxon signed-rank | no distributional assumption beyond symmetry |
| Location shift | **Exact Hodges–Lehmann interval** from Walsh-average order statistics | the interval that *matches* the signed-rank test; bootstrapping an O(n²) estimator is both inappropriate and gratuitous |
| Effect intervals | Percentile bootstrap, 10,000 resamples over scenarios | scenario is the unit of independence |
| Proportions | Wilson score interval | Wald misbehaves near 0 and 1, where several band proportions sit |
| Calibration | Murphy decomposition on the calibration–refinement partition | the identity is exact only on distinct forecast values, not on fixed-width bins |
| Multiplicity | Holm–Bonferroni over 6 confirmatory tests | uniformly more powerful than Bonferroni at equal FWER |

Confirmatory tests are pre-registered and listed in
`gmais.hypotheses.CONFIRMATORY`; everything else is labelled exploratory in both
the report and `results.json`, so a reader can see exactly which claims the
correction covers.

Each main effect is tested **at both levels of the other factor** rather than as
a marginal, since a marginal main effect is interpretable only when the
interaction is negligible — and H3 exists to test precisely that.

---

## 7. Test suite

```sh
python -m pytest tests/ -q        # 46 tests
```

Covering the tradecraft primitives, governance mechanisms, determinism (with its
stated exemption), the noise model's determinism and ground-truth invariance,
the timing re-attribution, every statistical routine against known values, and
end-to-end package generation with checksum verification.
