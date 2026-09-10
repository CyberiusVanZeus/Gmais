**Table 8.** Measured wall-clock cost of governance mediation, attributed by component. Timed with time.perf_counter_ns over every mediated event in the campaign.

| Component | Mean µs / event | % of mediation cost |
|:--|--:|--:|
| Policy evaluation fG(e) + HMAC verify | 24.134 | 25.2% |
| Audit chain SHA-256 append | 39.082 | 40.8% |
| Named-entity redaction | 14.285 | 14.9% |
| Mediation-queue bookkeeping | 4.013 | 4.2% |
| **End-to-end mediation** | **95.873** | **100.0%** |

*n = 2,358 mediated events on Linux-6.8.0-139-generic-x86_64-with-glibc2.39, CPython 3.12.3; measured clock resolution 40 ns.*
