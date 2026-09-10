**Table 3.** Cost per observation. Modelled latency combines the inference cost model with the deployment governance cost model; measured governance latency is real elapsed wall-clock time through the mediation path.

| Cell | Latency (ms) | Δ vs baseline | Tokens | Δ vs baseline | Measured governance (ms) |
|:--|--:|--:|--:|--:|--:|
| Baseline | 571.9 | — | 1,051.7 | — | 0.0000 |
| V-only | 2,636.4 | +2,064.5  (+361.0%) | 1,947.3 | +895.6  (+85.2%) | 0.0000 |
| G-only | 592.9 | +21.0  (+3.7%) | 1,123.7 | +72.0  (+6.8%) | 0.6414 |
| Full | 2,678.4 | +2,106.5  (+368.3%) | 2,091.3 | +1,039.6  (+98.9%) | 0.8138 |
