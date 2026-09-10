**Table 1.** Ground-Truth Knowledge Graph and scenario corpus. Every scenario carries a known gold hypothesis and a known set of adversarially injected claims; the corpus is generated deterministically from the campaign seed.

| Complexity tier | Scenarios | Claims | Injected claims | Injection rate |
|:--|--:|--:|--:|--:|
| Low | 45 | 225 | 45 | 0.200 |
| Medium | 45 | 360 | 90 | 0.250 |
| High | 45 | 495 | 135 | 0.273 |
| **Total** | **135** | **1,080** | **270** | **0.250** |

*Pre-registered Section 3.2.2 tolerance conformance — flesch kincaid: 0%, temporal span: 100%, ambiguity index: 100%.*


**Table 2.** Per-cell performance across the 2×2 factorial ablation. Each cell contains one observation per scenario, so the four columns are matched within scenario.

| Cell | V | G | N | Accuracy | Rubric | Brier | Det. P | Det. R | Det. F1 |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Baseline | 0 | 0 | 135 | 0.1926 | 0.2638 | 0.2500 | 0.0000 | 0.0000 | 0.0000 |
| V-only | 1 | 0 | 135 | 0.7704 | 0.7377 | 0.1849 | 0.9848 | 0.7222 | 0.8333 |
| G-only | 0 | 1 | 135 | 0.3333 | 0.3271 | 0.2500 | 0.0000 | 0.0000 | 0.0000 |
| Full | 1 | 1 | 135 | 0.7704 | 0.7377 | 0.1849 | 0.9848 | 0.7222 | 0.8333 |

*Detection metrics are claim-level over the whole corpus; accuracy and Brier are observation-level. Cells without a Validator emit no detections by construction and a fixed 0.5 confidence.*


**Table 3.** Cost per observation. Modelled latency combines the inference cost model with the deployment governance cost model; measured governance latency is real elapsed wall-clock time through the mediation path.

| Cell | Latency (ms) | Δ vs baseline | Tokens | Δ vs baseline | Measured governance (ms) |
|:--|--:|--:|--:|--:|--:|
| Baseline | 571.9 | — | 1,051.7 | — | 0.0000 |
| V-only | 2,636.4 | +2,064.5  (+361.0%) | 1,947.3 | +895.6  (+85.2%) | 0.0000 |
| G-only | 592.9 | +21.0  (+3.7%) | 1,123.7 | +72.0  (+6.8%) | 0.6414 |
| Full | 2,678.4 | +2,106.5  (+368.3%) | 2,091.3 | +1,039.6  (+98.9%) | 0.8138 |


**Table 4.** Confirmatory tests of H1–H3 with Holm–Bonferroni adjustment across the six-test family. All tests are paired within scenario.

| Hypothesis / contrast | Test | n | Statistic | p | p (Holm) | Effect size | Estimate [95% CI] |
|:--|:--|--:|--:|--:|--:|--:|:--|
| H1 \| G=0: Baseline -> V-only | McNemar (exact) | 135 | 79.0 | < .0001 | < .0001 | odds ratio (discordant) = 53.000 | — |
| H1 \| G=1: G-only -> Full | McNemar (exact) | 135 | 60.0 | < .0001 | < .0001 | odds ratio (discordant) = 40.333 | — |
| H2 \| V=0: latency, Baseline -> G-only | Wilcoxon signed-rank | 135 | 0.0 | < .0001 | < .0001 | rank-biserial r = 1.000 | +21.000 [+21.000, +21.000] |
| H2 \| V=1: latency, V-only -> Full | Wilcoxon signed-rank | 135 | 0.0 | < .0001 | < .0001 | rank-biserial r = 1.000 | +42.000 [+42.000, +42.000] |
| H2: token consumption, ungoverned -> governed | Wilcoxon signed-rank | 135 | 0.0 | < .0001 | < .0001 | rank-biserial r = 1.000 | +108.000 [+108.000, +108.000] |
| H3: V x G interaction on latency (ms) | Wilcoxon signed-rank | 135 | 0.0 | < .0001 | < .0001 | rank-biserial r = 1.000 | +21.000 [+21.000, +21.000] |

*Estimate is the Hodges–Lehmann shift with the exact distribution-free signed-rank interval read off the Walsh averages; for McNemar the effect size is the discordant-pair odds ratio (Haldane–Anscombe corrected). A degenerate interval indicates a differential that is constant across scenarios by construction — see the note on the deployment cost model.*


**Table 5.** Factorial effect estimates with 95% bootstrap intervals, resampled over scenarios.

| Hypothesis | Quantity | Estimate | 95% CI | Excludes 0 |
|:--|--:|--:|--:|--:|
| H1 | validation main effect accuracy | +0.5074 | [+0.4259, +0.5852] | yes |
| H2 | governance main effect latency ms | +31.5000 | [+31.5000, +31.5000] | yes |
| H2 | governance main effect tokens | +108.0000 | [+108.0000, +108.0000] | yes |
| H2 | governance relative latency | +0.0377 | [+0.0366, +0.0388] | yes |
| H2 | governance relative tokens | +0.0694 | [+0.0680, +0.0709] | yes |
| H2 | measured governance ms full cell | +0.8138 | [+0.6301, +1.1411] | yes |
| H3 | interaction latency ms | +21.0000 | [+21.0000, +21.0000] | yes |
| H3 | interaction tokens | +72.0000 | [+72.0000, +72.0000] | yes |
| H3 | interaction correct | -0.1407 | [-0.2000, -0.0815] | yes |


**Table 6.** Security-Tax distribution and policy-band assignment (α = 0.5, β = 0.5; bands at 0.5 and 1.5).

| Cell | N | Mean ST | Median ST | SD | IQR | Range | Modal band | % in modal band |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| Baseline | 135 | -1.0137 | -1.0118 | 0.1332 | [-1.107, -0.922] | [-1.358, -0.715] | full governance | 100.0% |
| V-only | 135 | +0.8874 | +0.8831 | 0.2368 | [+0.712, +1.060] | [+0.362, +1.383] | adaptive governance | 94.8% |
| G-only | 135 | -0.9295 | -0.9276 | 0.1333 | [-1.022, -0.837] | [-1.272, -0.629] | full governance | 100.0% |
| Full | 135 | +1.0558 | +1.0545 | 0.2367 | [+0.884, +1.231] | [+0.532, +1.554] | adaptive governance | 97.0% |


**Table 7.** Robustness of the H4 band assignment to the Security-Tax weighting. A recommendation that survives the full sweep does not depend on the pre-registered choice of α.

| α (latency weight) | Baseline median ST → band | V-only median ST → band | G-only median ST → band | Full median ST → band |
|:--|--:|--:|--:|--:|
| 0 | -1.039 → full governance | +0.826 → adaptive governance | -0.888 → full governance | +1.113 → adaptive governance |
| 0.25 | -1.025 → full governance | +0.848 → adaptive governance | -0.907 → full governance | +1.073 → adaptive governance |
| 0.5 | -1.012 → full governance | +0.883 → adaptive governance | -0.928 → full governance | +1.054 → adaptive governance |
| 0.75 | -0.993 → full governance | +0.919 → adaptive governance | -0.942 → full governance | +1.025 → adaptive governance |
| 1 | -0.990 → full governance | +0.947 → adaptive governance | -0.970 → full governance | +0.987 → adaptive governance |


**Table 8.** Measured wall-clock cost of governance mediation, attributed by component. Timed with time.perf_counter_ns over every mediated event in the campaign.

| Component | Mean µs / event | % of mediation cost |
|:--|--:|--:|
| Policy evaluation fG(e) + HMAC verify | 15.334 | 18.9% |
| Audit chain SHA-256 append | 34.740 | 42.9% |
| Named-entity redaction | 10.468 | 12.9% |
| Mediation-queue bookkeeping | 3.169 | 3.9% |
| **End-to-end mediation** | **80.937** | **100.0%** |

*n = 2,358 mediated events on Linux-6.8.0-139-generic-x86_64-with-glibc2.39, CPython 3.12.3; measured clock resolution 39 ns.*


**Table 9.** Worker-to-worker need-to-know: named-entity redaction and the anchoring it interrupts.

| Cell | Entity mentions visible to peers | Entity mentions redacted | Workers anchored (mean) |
|:--|--:|--:|--:|
| Baseline | 14.0 | 0.0 | 0.541 |
| V-only | 14.0 | 0.0 | 0.541 |
| G-only | 0.0 | 14.0 | 0.000 |
| Full | 0.0 | 14.0 | 0.000 |

*Anchoring is the pathway through which governance can move analytical accuracy: masking the actor's name removes the cue an unvalidating Worker herds on.*
