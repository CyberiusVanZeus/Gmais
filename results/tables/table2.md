**Table 2.** Per-cell performance across the 2×2 factorial ablation. Each cell contains one observation per scenario, so the four columns are matched within scenario.

| Cell | V | G | N | Accuracy | Rubric | Brier | Det. P | Det. R | Det. F1 |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Baseline | 0 | 0 | 135 | 0.1926 | 0.2638 | 0.2500 | 0.0000 | 0.0000 | 0.0000 |
| V-only | 1 | 0 | 135 | 0.7704 | 0.7377 | 0.1849 | 0.9848 | 0.7222 | 0.8333 |
| G-only | 0 | 1 | 135 | 0.3333 | 0.3271 | 0.2500 | 0.0000 | 0.0000 | 0.0000 |
| Full | 1 | 1 | 135 | 0.7704 | 0.7377 | 0.1849 | 0.9848 | 0.7222 | 0.8333 |

*Detection metrics are claim-level over the whole corpus; accuracy and Brier are observation-level. Cells without a Validator emit no detections by construction and a fixed 0.5 confidence.*
