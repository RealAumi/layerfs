# `fs-bench` paired result — `20261019T195401Z`

Status: **VALID**. Lower median is better.

This is a resident-FUSE microbenchmark. It excludes setup, Pull, Fork, mount startup, Workspace Commit, Push, Add, reopen, and persistent-space accounting.

## Provenance

| Candidate | Intended commit | Intended tree | Runner user | Command route | Provenance | Basis |
|---|---|---|---|---|---|---|
| `computer-upstream` | `de87919a4fd37242e960e13b7b3ba802d1eef0a0` | `4fb409d7e1356e1098439293d77d2fdc2dbf2190` | `0:0` | docker exec | **verified** | container image labels match the pinned Computer commit and tree; inspect evidence retained |
| `layerfs-core` | `e5c7aaae05229a9edd7a18eed6a94154b9f771b1` | `N/A` | `501:20` | sandbox.exec (@layerfs/sdk), Sandbox bench | **unverified** | container image inspected, but its revision label is absent or does not match the intended source |

The workload provenance is verified by the frozen upstream script SHA-256. Candidate provenance is never upgraded from caller metadata; only captured container/image evidence can mark it verified.

## Scenario medians

| Scenario | Computer upstream | LayerFS core | LayerFS speedup | Winner |
|---|---:|---:|---:|---|
| create 1000 files | 1396.237 ms | 413.045 ms | 3.380× | `layerfs-core` |
| stat 1000 files | 1677.186 ms | 1071.464 ms | 1.565× | `layerfs-core` |
| rm 1000 files | 1236.644 ms | 475.569 ms | 2.600× | `layerfs-core` |
| mkdir tree (10x10x10) | 1406.576 ms | 835.243 ms | 1.684× | `layerfs-core` |
| find tree | 1502.292 ms | 960.366 ms | 1.564× | `layerfs-core` |
| write 64 MiB | 127.213 ms | 160.366 ms | 0.793× | `computer-upstream` |
| copy 64 MiB | 351.906 ms | 598.285 ms | 0.588× | `computer-upstream` |
| read 64 MiB | 178.903 ms | 178.277 ms | 1.004× | `layerfs-core` |
| pure read 64 MiB | 78.430 ms | 7.430 ms | 10.556× | `layerfs-core` |
| pure copy 64 MiB | 224.266 ms | 209.114 ms | 1.072× | `layerfs-core` |
| overwrite 64 MiB | 168.876 ms | 110.922 ms | 1.522× | `layerfs-core` |
| git init + commit 100 files | 535.192 ms | 181.144 ms | 2.955× | `layerfs-core` |

## Summary

LayerFS won **10/12** scenarios and Computer won **2/12**; ties: **0**.

The convenience sum of scenario medians is 8883.721 ms for Computer and 5201.225 ms for LayerFS (1.708×). It is not an end-to-end agent-turn duration.

Raw-evidence SHA-256 values are recorded in `comparison.json`.
