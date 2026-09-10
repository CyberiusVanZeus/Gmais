**Table 3.** Cost per observation. Modelled latency combines the inference cost model with the deployment governance cost model; measured governance latency is real elapsed wall-clock time through the mediation path.

| Cell | Latency (ms) | Δ vs baseline | Tokens | Δ vs baseline | Measured governance (ms) |
|:--|--:|--:|--:|--:|--:|
| Baseline | 3,404.9 | — | 1,372.2 | — | 0.0000 |
| V-only | 17,155.3 | +13,750.4  (+403.8%) | 2,971.5 | +1,599.3  (+116.5%) | 0.0000 |
| G-only | 3,560.6 | +155.7  (+4.6%) | 1,439.2 | +66.9  (+4.9%) | 0.7072 |
| Full | 15,627.7 | +12,222.8  (+359.0%) | 3,118.4 | +1,746.1  (+127.2%) | 1.0411 |
