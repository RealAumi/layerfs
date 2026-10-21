# dsh-dedup stride 1 — run 20261019T211605Z-s1

> **Verdict:** COMPLETE, one sample. All 157 states committed (Init plus 156
> Commits), every live state and every stored Commit matched its oracle, and
> the Commit list matched the ledger (156/156). Diagnostic host (arm64 Docker
> Desktop, load 6.0–10.2); not a qualifying result.

## Identity

The same as [stride 10](20261019T205842Z-s10.md): core `e5c7aaae05`
(daemon `431dc4f5…`, addon `242b4384…`), Sandbox image `sha256:5a1cf254f7b8…`,
runtime `sha256:d3773b4eac6a…`, Disposable Store with policy 16/8/8 (schema 22),
`LAYERFS_CONSTRUCTION_WORKERS=1`, SDK tracing off, Docker 29.5.2 with 8 CPUs and
8.32 GB. All 157 states, logical 4,936,693,030 B. `finish.mjs` follows
`nextPagePos` (the fix recorded in the [stride 3 record](20261019T210657Z-s3.md)).
Git 2.47.1 with the same repack command.

## Commands

| Step | Start (UTC) | End | Exit | 1-min load | States |
| --- | --- | --- | --- | --- | --- |
| setup | 21:16:07 | 21:16:08 | 0 | 6.20 | 1 (Init) |
| segment-1 | 21:16:14 | 21:17:37 | 0 | 6.26 | 2–55 (54) |
| segment-2 | 21:17:49 | 21:19:10 | 0 | 9.89 | 56–84 (29) |
| segment-3 | 21:19:16 | 21:20:41 | 0 | 8.84 | 85–106 (22) |
| segment-4 | 21:20:51 | 21:22:20 | 0 | 6.82 | 107–122 (16) |
| segment-5 | 21:22:27 | 21:23:49 | 0 | 8.96 | 123–140 (18) |
| segment-6 | 21:23:59 | 21:25:27 | 0 | 8.38 | 141–156 (16) |
| segment-7 | 21:25:33 | 21:25:44 | 0 | 7.72 | 157 (1) |
| history-1…5 | 21:25:51 | 21:31:59 | 0 | 6.21–10.16 | 66, 34, 27, 24, 5 Commits |
| finish | 21:32:06 | 21:32:07 | 0 | 6.01 | — |

Mount took 26.7–34.1 ms and unmount 14.3–34.3 ms per segment.

## Result

| Measure | Value |
| --- | ---: |
| Store allocated (one file, `store.sqlite`, no WAL after close) | **100,085,760 B** (apparent 100,081,664) |
| Store totals: stored payload / metadata (Commits) / Init metadata | 67,488,833 / 5,205,904 / 301,704 B |
| Neither payload nor metadata objects | 27,089,319 B |
| Git pack + index, all 157 trees | 51,985,325 + 3,083,340 = 55,068,665 B (objects allocated 57,012,224) |
| Store allocated ÷ Git pack + index | 1.818 |
| Logical ÷ Store allocated | 49.3× (Git 89.6×) |
| Init (state 1) | 155.1 ms |
| Σ Commit, 156 Commits | **97,919.6 ms** (628 ms average, max 2,806.0 ms at state 157) |
| Σ apply, 156 `sandbox.exec` | 219,383.6 ms |
| Σ verify, live (untimed check) | 198,932.3 ms |
| Σ verify, stored history (fork + fresh mount) | 340,532.6 ms |
| History proof | 156 / 156 PASS |

The Store's `logical` total is 4,936,675,219 B, 17,811 B below the
checkpoints' sum; as at strides 10 and 3, consistent with symlink targets not
counted as logical bytes, not investigated.

State 157 ran alone in segment 7, first after a fresh mount; its apply
(5,214 ms) and Commit (2,806 ms) are the run's slowest. Whether the first
state after a mount pays a cold overlay is not separated here.

Every 10th state, with the first and last (all 157 are in `states.csv`):

| State | Files | Logical B | Apply ms | Commit ms | newCanonical | newStored |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 276 | 1,499,109 | — | — | 1,537,477 | 507,058 |
| 11 | 875 | 6,673,153 | 492 | 223 | 3,938,996 | 321,413 |
| 21 | 1306 | 9,643,646 | 742 | 221 | 804,461 | 102,644 |
| 31 | 1656 | 11,884,284 | 505 | 202 | 859,357 | 58,376 |
| 41 | 2762 | 18,790,518 | 1,360 | 526 | 10,001,349 | 1,290,223 |
| 51 | 3462 | 21,988,692 | 846 | 359 | 4,527,696 | 404,163 |
| 61 | 4539 | 26,001,139 | 723 | 238 | 3,509,165 | 185,363 |
| 71 | 4795 | 27,706,674 | 1,003 | 491 | 3,099,191 | 186,331 |
| 81 | 5395 | 33,740,250 | 876 | 425 | 6,203,559 | 907,504 |
| 91 | 5739 | 36,248,756 | 1,496 | 826 | 11,057,942 | 686,927 |
| 101 | 6355 | 40,562,502 | 1,228 | 551 | 8,110,831 | 562,702 |
| 111 | 6828 | 44,387,600 | 1,718 | 656 | 8,769,034 | 354,122 |
| 121 | 7132 | 46,737,273 | 561 | 71 | 376,264 | 13,019 |
| 131 | 7880 | 50,909,855 | 2,301 | 1,430 | 13,307,945 | 608,528 |
| 141 | 8715 | 57,785,429 | 1,191 | 726 | 9,003,799 | 462,455 |
| 151 | 8934 | 61,430,643 | 1,396 | 797 | 7,441,840 | 400,343 |
| 157 | 9415 | 65,020,822 | 5,214 | 2,806 | 13,038,438 | 1,323,286 |

## Across the three strides

| Stride | States | Store allocated | Payload | Metadata | Other | Git pack + idx | Σ Commit |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 17 | 53,125,120 | 41,472,751 | 1,325,047 | 10,327,322 | 41,797,536 | 22.4 s |
| 3 | 53 | 69,455,872 | 51,897,185 | 2,457,063 | 15,101,624 | 48,169,384 | 45.1 s |
| 1 | 157 | 100,085,760 | 67,488,833 | 5,507,608 | 27,089,319 | 55,068,665 | 97.9 s |

Metadata includes Init's. "Other" is allocated minus payload minus metadata:
history rows, signatures, the object index and page slack. It grows with the
number of Commits (about 0.12–0.13 MB per added Commit between strides) and is 27% of the stride-1
Store; it is the largest difference from Git and is not broken down here.

## Context, not comparison

The 2026-10-07 in-process history run recorded 85,172,224 B and 185.19 s for
stride 1 (approved ceiling 92,342,273 B, original target 83,947,520 B). This
run is 17.5% larger and above that old ceiling, on a different route, depth,
pack layout and predecessor rule (see the README). It is a new baseline for
the SDK route; the old ceilings are not this suite's gates.

## Receipts

`benchmark-results/dsh-dedup/20261019T211605Z-s1/` (Git-ignored), the same
files as stride 10, with a complete `commits.json` (156); Git reference
`benchmark-results/dsh-dedup/git-reference/s1/result.json`. Volumes removed
after finish.
