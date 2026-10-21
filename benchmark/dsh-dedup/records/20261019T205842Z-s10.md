# dsh-dedup stride 10 — run 20261019T205842Z-s10

> **Verdict:** COMPLETE, one sample. All 17 states committed (Init plus 16
> Commits), every live state and every stored Commit matched its oracle.
> Diagnostic host (arm64 Docker Desktop, load 9–10); not a qualifying result.

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK | `sdk/js/src` at that commit, run from worktree branch `fs-bench-sdk-main` (harness files uncommitted) |
| Sandbox image | `sha256:5a1cf254f7b8…` = fs-bench image `sha256:66aeb6bb…` + `/corpus` (157 states) |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8, schema 22; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Host | Docker 29.5.2, Docker Desktop, kernel 6.12.76-linuxkit, 8 CPUs, 8.32 GB |
| Corpus | `checkpoint-manifest.json` 157 states; selection `1, 11, …, 151, 157` (17), logical 561,010,345 B |
| Git | 2.47.1, `repack -a -d -f -F --window=10 --depth=50 --threads=2` |

## Commands

| Step | Start (UTC) | End | Exit | 1-min load |
| --- | --- | --- | --- | --- |
| setup | 20:58:44 | 20:58:47 | 0 | 10.02 |
| segment-1 | 20:58:52 | 21:00:17 | 0 | 9.94 |
| history-1 | 21:00:23 | 21:01:12 | 0 | 9.15 |
| finish | 21:01:16 | 21:01:17 | 0 | 9.72 |

Segment 1 took all 16 states in 85 s. The 80 s budget is checked before a
state starts, so the last state ran past it; the command stayed under its
115 s alarm.

## Result

| Measure | Value |
| --- | ---: |
| Store allocated (one file, `store.sqlite`, no WAL after close) | **53,125,120 B** |
| Store totals: stored payload / metadata (Commits) / Init metadata | 41,472,751 / 1,020,244 / 304,803 B |
| Git pack + index, same 17 trees | 40,240,616 + 1,556,920 = 41,797,536 B (objects allocated 42,704,896) |
| Store allocated ÷ Git pack + index | 1.271 |
| Init (state 1, 1,499,109 B) | 200.5 ms |
| Σ Commit, 16 Commits | **22,425.8 ms** (max 2,937.0 ms, state 141) |
| Σ apply, 16 `sandbox.exec` | 39,849.6 ms |
| Σ verify (untimed check) | 22,552.7 ms |
| Mount / unmount (segment 1) | 30.0 / 26.5 ms |
| History proof: fork + mount + verify each Commit | 16 / 16 PASS |

Σ `newStored` over Init and the 16 Commits is 41,472,751 B, equal to the
Store's `stored` total. The Store's `logical` total is 561,008,218 B, 2,127 B
below the checkpoints' sum; Init alone records 1,499,065 B for state 1's
1,499,109 B (44 B, the size of its four symlinks' targets), so the gap is
consistent with symlink targets not counted as logical file bytes. Not
investigated further.

About 10.3 MB of the allocated file (53,125,120 − 41,472,751 − 1,020,244 −
304,803) is neither payload nor metadata objects: history rows, signatures,
the object index and page slack. Not broken down here.

| State | Ordinal | Files | Logical B | Apply ms | Commit ms | newCanonical | newStored | Overwritten / created / removed |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 100 | 276 | 1,499,109 | — | — | 1,537,477 | 508,055 | Init |
| 11 | 1100 | 875 | 6,673,153 | 802 | 272 | 6,669,820 | 1,705,005 | 74 / 755 / 156 |
| 21 | 2100 | 1306 | 9,643,646 | 859 | 373 | 8,977,384 | 1,366,211 | 551 / 440 / 9 |
| 31 | 3100 | 1656 | 11,884,284 | 940 | 428 | 9,854,415 | 1,042,707 | 675 / 389 / 39 |
| 41 | 4100 | 2762 | 18,790,518 | 2,224 | 865 | 17,352,795 | 2,804,120 | 844 / 1490 / 384 |
| 51 | 5100 | 3462 | 21,988,692 | 1,884 | 786 | 16,240,636 | 2,466,327 | 1111 / 831 / 131 |
| 61 | 6100 | 4539 | 26,001,139 | 2,482 | 1,046 | 18,878,022 | 2,640,496 | 1276 / 1348 / 271 |
| 71 | 7100 | 4795 | 27,706,674 | 1,547 | 774 | 13,689,168 | 1,130,502 | 1216 / 339 / 83 |
| 81 | 8100 | 5395 | 33,740,250 | 1,768 | 1,009 | 19,948,854 | 2,740,116 | 1371 / 629 / 29 |
| 91 | 9100 | 5739 | 36,248,756 | 1,701 | 1,008 | 18,166,583 | 1,465,046 | 1441 / 359 / 15 |
| 101 | 10100 | 6355 | 40,562,502 | 3,152 | 1,773 | 28,710,263 | 3,259,954 | 2752 / 993 / 377 |
| 111 | 11100 | 6828 | 44,387,600 | 2,637 | 1,816 | 29,833,263 | 2,789,755 | 2719 / 1032 / 559 |
| 121 | 12100 | 7132 | 46,737,273 | 2,873 | 1,954 | 30,542,542 | 2,195,149 | 2726 / 832 / 528 |
| 131 | 13100 | 7880 | 50,909,855 | 3,952 | 2,646 | 39,943,081 | 3,942,153 | 3538 / 1765 / 1017 |
| 141 | 14100 | 8715 | 57,785,429 | 5,514 | 2,937 | 42,302,308 | 5,388,928 | 3233 / 2005 / 1170 |
| 151 | 15100 | 8934 | 61,430,643 | 3,664 | 2,414 | 39,215,101 | 2,895,168 | 3416 / 765 / 546 |
| 157 | 15632 | 9415 | 65,020,822 | 3,843 | 2,317 | 38,465,915 | 3,133,059 | 2357 / 2019 / 1538 |

## Context, not comparison

The 2026-10-07 in-process history run recorded 50,692,096 B and 33.71 s for
stride 10 (approved ceiling 54,278,964 B, original target 49,344,512 B). That
driver differs in route, depth (8/4), pack layout (GroupRowsIndexed),
predecessors (every changed file) and similarity lookup (off); see the
README. This run is a new baseline for the SDK route.

## Receipts

`benchmark-results/dsh-dedup/20261019T205842Z-s10/` (Git-ignored):
`identity.txt`, `deploy.env`, `selection.json`, `commands.log`,
`ledger.jsonl`, `segments.jsonl`, `history.jsonl`, `commits.json`,
`store-files.txt`, `store.json`, `states.csv`, `summary.json`, each step's
`.out`/`.err`. Git reference: `benchmark-results/dsh-dedup/git-reference/s10/result.json`.
Volumes removed 21:01:52Z.
