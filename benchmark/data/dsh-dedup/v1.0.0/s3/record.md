# dsh-dedup stride 3 — run 20261019T210657Z-s3

> **Verdict:** COMPLETE, one sample, with one harness receipt defect. All 53
> states committed (Init plus 52 Commits), every live state and every stored
> Commit matched its oracle. `commits.json` lists only 47 of the 52 Commits
> (harness bug, below). Diagnostic host (arm64 Docker Desktop, load 7.6–12.6);
> not a qualifying result.

## Identity

The same as [stride 10](20261019T205842Z-s10.md): core `e5c7aaae05`
(daemon `431dc4f5…`, addon `242b4384…`), Sandbox image `sha256:5a1cf254f7b8…`,
runtime `sha256:d3773b4eac6a…`, Disposable Store with policy 16/8/8 (schema 22),
`LAYERFS_CONSTRUCTION_WORKERS=1`, SDK tracing off, Docker 29.5.2 with 8 CPUs and
8.32 GB. Selection `range(1, 158, 3)`: 53 states, logical 1,676,767,835 B.
Git 2.47.1 with the same repack command.

## Commands

| Step | Start (UTC) | End | Exit | 1-min load | States |
| --- | --- | --- | --- | --- | --- |
| setup | 21:06:59 | 21:07:01 | 0 | 10.24 | 1 (Init) |
| segment-1 | 21:07:07 | 21:08:28 | 0 | 10.16 | 4–97 (32) |
| segment-2 | 21:08:34 | 21:10:02 | 0 | 7.64 | 100–139 (14) |
| segment-3 | 21:10:07 | 21:10:50 | 0 | 12.58 | 142–157 (6) |
| history-1 | 21:10:56 | 21:12:16 | 0 | 11.54 | 43 Commits |
| history-2 | 21:12:22 | 21:13:17 | 0 | 9.59 | 9 Commits |
| finish | 21:13:23 | 21:13:24 | 0 | 10.68 | — |

## Result

| Measure | Value |
| --- | ---: |
| Store allocated (one file, `store.sqlite`, no WAL after close) | **69,455,872 B** (apparent 69,451,776) |
| Store totals: stored payload / metadata (Commits) / Init metadata | 51,897,185 / 2,147,114 / 309,949 B |
| Neither payload nor metadata objects | 15,101,624 B (stride 10: 10.3 MB) |
| Git pack + index, same 53 trees | 45,911,624 + 2,257,760 = 48,169,384 B (objects allocated 49,709,056) |
| Store allocated ÷ Git pack + index | 1.442 |
| Logical ÷ Store allocated | 24.1× (Git 34.8×) |
| Init (state 1) | 177.3 ms |
| Σ Commit, 52 Commits | **45,096.5 ms** (0.87 s average, max 2,677.0 ms) |
| Σ apply, 52 `sandbox.exec` | 90,652.1 ms |
| Σ verify, live (untimed check) | 74,036.9 ms |
| Σ verify, stored history (fork + fresh mount) | 132,101.8 ms |
| Mount / unmount per segment | 32.3, 27.5, 46.8 / 19.0, 32.9, 34.0 ms |
| History proof | 52 / 52 PASS |

The Store's `logical` total is 1,676,761,730 B, 6,105 B below the
checkpoints' sum. As at stride 10 this is consistent with symlink targets not
counted as logical bytes; not investigated.

The bytes that are neither payload nor metadata grew from 10.3 MB (16
Commits) to 15.1 MB (52 Commits). They are not broken down here.

Every 4th state, with the first and last (all 53 are in `states.csv`):

| State | Files | Logical B | Apply ms | Commit ms | newCanonical | newStored |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 276 | 1,499,109 | — | — | 1,537,477 | 507,004 |
| 4 | 457 | 2,755,845 | 823 | 128 | 2,557,456 | 619,476 |
| 16 | 1247 | 10,134,737 | 1,154 | 254 | 6,086,738 | 827,868 |
| 28 | 1269 | 9,571,603 | 492 | 262 | 4,648,901 | 271,713 |
| 40 | 2243 | 15,681,938 | 999 | 390 | 6,558,330 | 553,423 |
| 52 | 4002 | 23,613,843 | 1,746 | 947 | 13,943,980 | 2,275,704 |
| 64 | 4549 | 26,000,202 | 708 | 236 | 2,266,037 | 145,074 |
| 76 | 4517 | 25,923,390 | 1,566 | 821 | 1,361,705 | 165,377 |
| 88 | 5742 | 36,405,983 | 1,069 | 455 | 6,593,045 | 384,611 |
| 100 | 6251 | 39,891,045 | 1,376 | 842 | 11,213,028 | 1,147,003 |
| 112 | 6859 | 44,749,450 | 5,916 | 2,581 | 32,700,725 | 4,050,492 |
| 124 | 7461 | 48,051,442 | 4,834 | 2,475 | 33,969,242 | 2,761,290 |
| 136 | 7884 | 50,949,657 | 2,352 | 1,243 | 7,074,713 | 238,090 |
| 148 | 9044 | 60,711,815 | 1,524 | 556 | 7,320,959 | 617,555 |
| 157 | 9415 | 65,020,822 | 1,658 | 879 | 12,324,667 | 807,679 |

## Receipt defect: Commit list truncated

`branch.list_commits` ends a page at its reply budget as well as at
`pageSize`, and says so with `hasMore` / `nextPagePos`
(`layerfs-store-service/src/history/branch.rs`). This run's `finish.mjs` asked
for one 1000-item page and ignored `hasMore`, so `commits.json` holds the
newest 47 Commits and lacks states 4, 7, 10, 13 and 16. The Store was removed
before this was noticed; the list was not re-read. The ledger holds all 52
Commit records (id, parent, sizes), and the history proof forked and verified
each of them, those five included. `finish.mjs` now follows `nextPagePos` and
fails if the list does not match the ledger; stride 10 (16 Commits, one page)
was not affected.

## Context, not comparison

The 2026-10-07 in-process history run recorded 64,245,760 B and 66.84 s for
stride 3 (approved ceiling 70,427,034 B, original target 64,024,576 B). This
run is 8.1% larger on a different route, depth, pack layout and predecessor
rule (see the README); it is a new baseline for the SDK route.

## Receipts

`benchmark-results/dsh-dedup/20261019T210657Z-s3/` (Git-ignored), the same
files as stride 10; Git reference `benchmark-results/dsh-dedup/git-reference/s3/result.json`.
Volumes removed after finish.
