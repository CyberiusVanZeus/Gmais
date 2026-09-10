**Table 8.** Measured wall-clock cost of governance mediation, attributed by component. Timed with time.perf_counter_ns over every mediated event in the campaign.

| Component | Mean µs / event | % of mediation cost |
|:--|--:|--:|
| Policy evaluation fG(e) + HMAC verify | 15.334 | 18.9% |
| Audit chain SHA-256 append | 34.740 | 42.9% |
| Named-entity redaction | 10.468 | 12.9% |
| Mediation-queue bookkeeping | 3.169 | 3.9% |
| **End-to-end mediation** | **80.937** | **100.0%** |

*n = 2,358 mediated events on Linux-6.8.0-139-generic-x86_64-with-glibc2.39, CPython 3.12.3; measured clock resolution 39 ns.*
