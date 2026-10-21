# Unmount single samples

> **Status:** Dated local observations; intermittent unmount behavior remains unqualified.

Every Workspace created in the one full run appears below. Durations include the
CLI/container control round trip; cache/host scheduling was uncontrolled. These
are individual correctness observations, not a latency or reliability gate.
The two daemon-kill rows are not successful explicit unmount samples.

| Order | Container | Namespace | Outcome | Control wall ms |
| --- | --- | --- | --- | --- |
| 1 | cxi-b2 | 1 | clean | 50.385 |
| 2 | cxi-b1 | 1 | no explicit unmount: daemon killed by restart scenario | — |
| 3 | cxi-b2 | 2 | clean | 55.591 |
| 4 | cxi-b2 | 3 | clean | 49.247 |
| 5 | cxi-b2 | 4 | clean | 46.630 |
| 6 | cxi-b2 | 5 | clean | 75.808 |
| 7 | cxi-b2 | 6 | clean | 46.960 |
| 8 | cxi-b2 | 7 | clean | 53.314 |
| 9 | cxi-b2 | 8 | clean | 51.404 |
| 10 | cxi-b2 | 9 | clean | 47.517 |
| 11 | cxi-b2 | 10 | clean | 35.233 |
| 12 | cxi-b2 | 11 | clean | 42.396 |
| 13 | cxi-b2 | 12 | clean | 37.543 |
| 14 | cxi-b2 | 13 | clean | 47.244 |
| 15 | cxi-b2 | 14 | clean | 41.907 |
| 16 | cxi-b2 | 15 | clean | 45.016 |
| 17 | cxi-b2 | 16 | clean | 49.172 |
| 18 | cxi-b1 | 2 | clean | 40.208 |
| 19 | cxi-b1 | 3 | clean | 38.440 |
| 20 | cxi-b1 | 4 | no explicit unmount: daemon killed by restart scenario | — |
| 21 | cxi-b1 | 1 | clean | 36.247 |
| 22 | cxi-b1 | 2 | clean | 41.902 |
| 23 | cxi-b1 | 3 | clean | 87.959 |
| 24 | cxi-b1 | 4 | clean | 34.556 |
| 25 | cxi-b1 | 5 | clean | 39.246 |

Full Workspace identities, outputs and timing are in [unmount-samples.json](unmount-samples.json);
attempt/return records are in [mount-control-samples.jsonl](mount-control-samples.jsonl).
Namespace numbers restart with the daemon; Workspace identity disambiguates them.
