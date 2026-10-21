# Range 059 · **watch** · attempt 1

**Matches git ✓** · daemon `c41a86d23822` · image `d3773b4e` · plan v2 · continued from r058 (live Store)
dsh `544d3f826`..`538488506` · **63 commits** (9 mainline, 54 side) · 2026-07-30 → 2026-07-31
Areas changed: `packages/client` 25% · `/` 14% · `packages/host` 8% · other 53%
**Phase P3** · **Git ✓** · **Node ✓** (P1–P6: 17 pass, 0 stop, 0 NOT_RUN over 4 points) · **Content 0.15×** · **Churn 0.00**
**Time split:** play 161.5 s · git 131.2 s · Node 237.6 s · verify 17.4 s

| Latest version | Store on disk | Space amplification | Added this range | Commits | Time |
| --- | --- | --- | --- | --- | --- |
| **873.1 MiB** (+2.1 MiB) | **1.68 GiB** (+23.1 MiB) | **1.96×** (prev 1.94×) | **25.5 MiB** | **720** (total 70,240) | **387.9 s** tooling (total 229.8 min) |

**Checks:** 12 pass · 7 watch: Speed sandbox.exec — · uncontended: 1.63× baseline (no phase); Scaling insufficient same-binary points: 2 of 3 (daemon c41a86d23822); also not judged: oneshot_exec: 2 of 3 points of probe version 1; Counters insufficient same-binary points: 2 of 3 (daemon c41a86d23822); Contended work not judged: no contended class has 3 ranges of 5+ calls with per-call SQL; SQL per call (sql.call); Directory share 0.564; Range growth 25.5 MiB; median not judged: 1 of 3 earlier ranges; Snapshot time 5515 ms for 1466.3 MiB new; size exponent not judged (2 snapshots)
**D-6 triggers** (none): max candidate paths in a merge not traced (needs a candidate-path count on branch.merge (e.g. daemon timing `merge.paths` carrying `candidates`)) (trips > 50,000) · max lane hold of the merge at publish not traced (needs a span for the publication-lane hold inside branch.publish (e.g. daemon timing `publish.lane`, ms)) (trips > 500 ms) · Capacity/ObjectLimitExceeded/Busy from 8 merges: 0 (trips at 1)
**Moved most:** ▲ fs.write p95 +183% · ▼ probe fork −61% · ▼ probe stat −46%
**Budget:** 60 of 202 ranges · projected total 16.8 h (budget 16.8 h) · disk 53% of budget at range 202

## 1. Correctness

| Check | Result |
| --- | --- |
| Tree vs git | **5,294 tracked files match** (blob id and mode) |
| History | 3 lanes merged, 2 publishes |
| Steps | 1,679 / 1,679 outcomes as planned |
| Conflicts | **4 / 4 planned hit · 0 unplanned** |
| Unit tests | **30 / 30 equal to native** |
| Installed tree | against the native replay of the on-top chain (lead, lane points, repair): **equal to native** (the repair's P1) · the lead's chain alone (context; without the lane points' installs and builds): 3317 package groups equal · not byte-compared: 3 pnpm state file(s) · by target: 433 bin shims, 4789 links · output root ×0, verification age ×1 |
| Last-writer-wins (`/.lww`) | unchanged (61 lines from 4 .gitignore files) · **158 picks** in 3 merges (158 under node_modules) · re-installed after the merge |
| Ignored files | — (installs not played in P3) |
| Milestone | — |
| Git | **HEAD = checkpoint `538488506`** · 130 commits written for 130 dsh commits · status clean · fresh mount read back 0 · lane guard 0 · git clean 88 untracked, unignored (888,140 B) |
| Install inputs (NODE_RULE §3; reported, not gated) | not recorded |
| Conflicts by path class | Tracked 0 · Install outputs 158 · Build outputs 0 · `.git` 0 |

### Node and git proofs

Each proof runs the same command natively on the identical tree id (NODE_RULE §6); a proof not run is `NOT_RUN`, never pass.

| Lane | Point | Tree | Install inputs | P1 | P2 | P3 | P4 | P5 | P6 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r059-1-packages-client | end | `6a755cf07604` | `a9293bd1b927` | pass (436 normalized) | pass | pass | pass | pass | n/a |
| r059-2-root | end | `9306f9e76fc8` | `2e80bb3c6021` | pass (436 normalized) | pass | n/a | pass | pass | n/a |
| r059-3-agents-notes | end | `13d95030b7e6` | `a9293bd1b927` | pass (436 normalized) | pass | pass | pass | pass | n/a |
| lead | repair | `d62250f36a72` | `null` | n/a | pass | n/a | n/a | pass | pass (137,756 rewritten) |

P5 skip list (failing natively, set at calibration): `packages/client/ui-permission/tests/browser-plugin.spec.ts` (fails natively) · `packages/client/ui-permission/tests/permission-row.spec.tsx` (fails natively) · `packages/client/ui-command/tests/browser-plugin.spec.ts` (fails natively) · `packages/client/ui-primitives/tests/web-block.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-matrix.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-scenarios.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/assembly-surfaces.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/web-card.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-toolview-slot.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-code-subcalls.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-bar.spec.tsx` (fails natively) · `packages/client/ui-models/tests/onboarding-dialog.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/skeleton.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/diff-card.spec.tsx` (fails natively) · `packages/client/ui-command/tests/popup-view.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-tool-row.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/terminal-card.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/apply-inject.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/queue-dock.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-view.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/workspace-browser.spec.tsx` (fails natively) · `packages/core/session/tests/fork.spec.ts` (fails natively) · `packages/context/workspace-context/tests/workspace-context.spec.ts` (fails natively) · `packages/ui/tui/tests/tui.spec.ts` (fails natively).

## 2. Activity

**2,423 calls** · **154 steps** by **8 agents + lead** on **3 Branches + main** · **198 Workspaces** (99% one-shot, 0 open at end)
**File changes:** +47 added · 568 modified · −8 deleted · 10.1 MiB written · fs 572 : Sandbox 51 (**11 : 1**, reported only in P3)
**Execs:** 519 (JS 59 · shell 460) · 3 non-zero exits · install 0 · test runs 5 · version figures 14 (tooling)

**Calls by category**

| Category | Calls | Writes | Reads | Outcomes |
| --- | --- | --- | --- | --- |
| fs | 853 | 585 | 268 | Committed 585 · NoSuchPath 9 · Text 30 |
| sandbox | 1,114 | 714 | 4 | commit 195 (Committed 150, UpToDate 44, Conflict 1) · exec 519 (exit:0 516, exit:2 3) · mount 198 (Mounted 198) · status 4 · unmount 198 (Unmounted 198) |
| branch | 446 | 33 | 413 | diff_branches 9 · diff_commits 404 · fork 23 (Forked 23) · merge 8 (Merged 8) · publish 2 (Added 2) |
| project | 9 | 0 | 9 | list_commits 9 |
| operator | 1 | 0 | 1 | store.stats 1 |
| **Total** | **2,423** | **1,332** | **695** |  |

**Branches**

| Branch | Agents | Steps | Commits | Merged into main | Published |
| --- | --- | --- | --- | --- | --- |
| r059-1-packages-client | a01 a02 a03 | 43 | 233 | ✓ | ✓ |
| r059-2-root | a04 a05 | 38 | 178 | ✓ | — |
| r059-3-agents-notes | a06 a07 a08 | 66 | 199 | ✓ | — |
| main | lead | 7 | 110 | — | ✓ |

**Conflicts**

| Kind | Hit / planned | Where | Resolved in |
| --- | --- | --- | --- |
| Commit Conflict | 1 / 1 | r059-3, a06 after a08 | 0.1 s |
| Stale clean merge | 1 / 1 | r059-3, a06 a07 | merged cleanly |
| Decoy edit | 1 / 1 | r059-3, a08 a06 | replaced before the checkpoint |
| Merge / publish race | 1 / 1 | lead merge of r059-2 vs r059-1 publish | 3.3 s, merged again |
| **Unplanned** | **0** | — | — |

**Agents**

| Agent | Branch | Steps | fs | sandbox | branch | project | Commits | Conflicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a01 | r059-1 | 19 | 7 | 12 | 0 | 0 | 122 | — |
| a02 | r059-1 | 11 | 5 | 6 | 0 | 0 | 63 | — |
| a03 | r059-1 | 13 | 5 | 8 | 0 | 0 | 48 | — |
| a04 | r059-2 | 21 | 10 | 11 | 0 | 0 | 99 | — |
| a05 | r059-2 | 17 | 8 | 9 | 0 | 0 | 79 | — |
| a06 | r059-3 | 22 | 9 | 13 | 0 | 0 | 43 | commit-conflict, stale-clean-merge, decoy |
| a07 | r059-3 | 30 | 14 | 16 | 0 | 0 | 112 | stale-clean-merge |
| a08 | r059-3 | 14 | 8 | 6 | 0 | 0 | 44 | commit-conflict, decoy |
| lead | main | 7 | 1 | 0 | 6 | 0 | 110 | merge-race |
| **Total** |  | **154** | **67** | **81** | **6** | **0** | **720** | **4** |

Scale-probe Commits (setup and samples): **22**, not range work and not counted above.


**Execs by tool:** git 106 · pnpm 1 · tsc 3 · vitest 5 · other 404

| Lane | git status | git diff | git add | git rm --cached | Lane commits | Loose objects |
| --- | --- | --- | --- | --- | --- | --- |
| r059-2-root | 27 | 27 | 27 | 1 | 27 | 256 |
| r059-3-agents-notes | 42 | 42 | 42 | 0 | 42 | 526 |
| r059-1-packages-client | 30 | 30 | 30 | 0 | 30 | 497 |
| **lead** | — | — | — | — | 130 commit-tree | index rebuild ✓ · repack ✓ |

| Lane | Installs | Refreshes | tsc -b | vitest points | Test files | Equal to native |
| --- | --- | --- | --- | --- | --- | --- |
| r059-1-packages-client | 0 | 1 | 1 | 1 | 98 | 98 / 98 |
| r059-2-root | 1 | 0 | 1 | 1 | 29 | 29 / 29 |
| r059-3-agents-notes | 0 | 1 | 1 | 1 | 40 | 40 / 40 |
| **lead repair** | 1 | — | 1 | — | — | 137,756 files rewritten |

## 3. Storage

**3a. Overview**

|  | Previous (r058) | Now | Change |
| --- | --- | --- | --- |
| Latest version (tracked / `node_modules` / build / `.git`) | 871.1 MiB (29.8 MiB / 692.1 MiB / 27.8 MiB / 121.4 MiB) | 873.1 MiB (30.1 MiB / 692.1 MiB / 28.0 MiB / 123.0 MiB) | +2.1 MiB |
| Version figures from | — | full: snapshot cross-check | — |
| Files / directories / symlinks | 65,037 / 10,097 / 4,788 | 65,110 / 10,099 / 4,797 | +73 / +2 / +9 |
| Largest file / largest directory | 23.5 MiB / 2,252 entries | 23.5 MiB (`node_modules/.pnpm/@rolldown+binding-linux-arm64-gnu@1.1.1/node_modules/@rolldown/binding-linux-arm64-gnu/rolldown-binding.linux-arm64-gnu.node`) / 2,252 entries (`node_modules/.pnpm/@mistralai+mistralai@2.2.6_@opentelemetry+api@1.9.0/node_modules/@mistralai/mistralai/esm/models/components`) | — |
| **Store on disk** (allocated, sealed) | 1.65 GiB | 1.68 GiB | +23.1 MiB |
| **Space amplification** (total · tracked) | 1.94× · tracked 4.93× | 1.96× · tracked 4.92× | 0.02 |
| Head cost / history cost | — | — (needs a reachability walk of the sealed file; not built) / — | — |
| **Stored per byte changed** (content / metadata / shared) | — | **6.13** (0.63 / 0.17 / 0.87) | 0.83× the median range |
| **Stored per Commit** | 18.9 KiB | 32.7 KiB | — |
| Metadata share | 0.45 | 0.45 | this range 0.56 |
| History: Commits / Layers / Branches | 69,520 | 70,240 / 41 / 987 | +720 |
| Projection at range 202 (estimate: study model, per-Commit cost × planned Commits + install and build forecast) | — | 12.27 GiB (Commits 9.71 GiB · installs 823.2 MiB · build 91.1 MiB) | — |
| Disk guard floor at range 202 (headroom: 256 MiB per range minimum) / disk budget | — | 37.40 GiB / 53% | — |
| Snapshot | — | r059, 1.43 GiB new blocks | — |

**3b. Where the bytes are**

| Part | Bytes | × latest version | Change this range |
| --- | --- | --- | --- |
| Content | 935.1 MiB | 1.07 | +8.7 MiB |
| Metadata | 157.9 MiB | 0.18 | +2.5 MiB |
| Index rows | 539.5 MiB | 0.62 | +10.8 MiB |
| Waste | 80.8 MiB | 0.09 | +1.1 MiB |
| Other | 2.1 MiB | 0.00 | +28.0 KiB |
| **Total = Store on disk** | **1.68 GiB** | **= 1.96** space amplification | +23.1 MiB |

Exact: from the sealed file.

**3c. By source**

| Source | Latest version | Stored (content + metadata) | Amplification | Head cost | Added this range | Changed this range | Stored per byte changed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Tracked | 30.1 MiB | 148.2 MiB (76.6 MiB + 71.6 MiB) | 4.92× | — | 1.2 MiB | 4.2 MiB | 0.30 |
| `node_modules` | 692.1 MiB | 241.9 MiB (201.5 MiB + 40.4 MiB) | 0.35× | — | 984.2 KiB | 0.3 KiB | 3574.00 |
| Build output | 28.0 MiB | 37.0 MiB (34.0 MiB + 3.0 MiB) | 1.32× | — | 1.1 MiB | 9.6 MiB | 0.11 |
| `.git` | 123.0 MiB | 608.4 MiB (579.6 MiB + 28.8 MiB) | 4.95× | — | 7.8 MiB | 0.0 KiB | — |
| Shared (index rows + waste + other) | — | 622.4 MiB | — (not divided) | — | 11.9 MiB | — | — |
| Unattributed (Saves without traced sizes) | — | 57.5 MiB | — | — | — | — | — |
| **Total** | — | **1.68 GiB** | **= 1.97×** space amplification | — | — | — | — |

Sources by the Commit that wrote them (an install Commit is `node_modules`, a build Commit build output). Any comparison with git uses the Tracked row only.

**3d. What's inside**

| Object | Total | Added | Avg size | Reused (dedupe hits) | As delta |
| --- | --- | --- | --- | --- | --- |
| Whole files | 227,524 | +2,979 | 6.5 KiB | 0 (derived) | 55% |
| Chunks (large files) | 78,581 | +922 | 16.1 KiB | — | 53% |
| Large-file extents | 18,636 | — | 0.4 KiB | — | — |
| Directories | 572,266 | 3,724 (with inodes, pooled) | 0.3 KiB | — | 50% |
| Inodes and attributes | 462,113 | ↑ pooled | 2.9 KiB | — | — |
| Symlinks | 2,537 | +4,810 | 0.1 KiB | — | — |

Delta: 2.9% at depth cap · 12% of refused bases stopped by budget · `node_modules` reinstall: absolute: 918016 new stored bytes for 140 raw changed bytes of 7 changed packages (6557.257×; raw under 1 MiB)

**3e. Git and Node (P3)**

| Measure | Value |
| --- | --- |
| Tracked only (amplification of the tracked source; comparable with ranges 0–14) | 4.92× (148.2 MiB for 30.1 MiB) |
| Store growth per git commit (index / loose objects / pack) | 2.9 KiB / 3.6 KiB / 6.9 KiB over 229 git commits |
| **Content ratio** (stored content ÷ distinct new content; ≤1.x, watch > 2×, act > 5×) | 0.15× |
| **Churn ratio** (stored ÷ bytes Node churn rewrote) | 0.00 (2.0 MiB stored for 2.03 GiB rewritten) |
| Native-disk equivalence (stored ÷ lanes × one native checkout) | 0.65 (3 lanes × 873.1 MiB) |
| Metadata per file / per Commit (budget from the dev range) | 0.0 KiB / 3.3 KiB (budget not set) |

## 4. Speed

Daemon `c41a86d23822` · p50 / p95 · ratio to baseline (dominant size class) in brackets

| write | read | list | Commit (one-shot) | mount | merge | exec (FUSE ÷ native) |
| --- | --- | --- | --- | --- | --- | --- |
| 11.5 ms / 65.0 ms (1.10×) | 3.3 ms / 5.3 ms (1.06×) | 4.3 ms / 8.4 ms (0.96×) | 23.1 ms / 76.0 ms (1.00×) | 10.5 ms / 17.7 ms (0.93×) | 432 ms / 432 ms (0.95×) | — (native comparison in P3; exec 40.8 ms / 1520 ms) |
| SQL p50: 194 stmts | 58 stmts | 67 stmts | 226 stmts | 45 stmts | 9,110 stmts | — |

**Commit cost:** 15.89 ms per changed file · **One-shot Workspace** (mount + exec + commit + unmount): 861 ms p50 over 198
**Slowest:** sandbox.exec 41191 ms · sandbox.exec 32584 ms · sandbox.exec 31261 ms · checkpoint diff_commits 0.11 ms and 1.68 statements per entry (74,141 entries per page)
**Scaling:** not judged: fewer than 3 same-binary ranges (16 probes)

**Git and Node** (LayerFS ÷ native on the identical tree; ×base compares only with the P3 re-baseline)

| Operation | LayerFS p50 / p95 | Native p50 / p95 | ÷ native (p50) | #362 case ÷ native |
| --- | --- | --- | --- | --- |
| git status (cold) | 437 ms / 437 ms | — / — | — | git / status-cold: — |
| git status (steady) | 558 ms / 913 ms | — / — | — | git / status-steady: — |
| git add | 42.0 ms / 96.0 ms | — / — | — | git / add: — |
| git commit (lane) | 47.0 ms / 75.0 ms | — / — | — | git / commit: — |
| lead writes main | 5958 ms / 5958 ms | — / — | — | — |
| repack | 1999 ms / 1999 ms | — / — | — | — |
| pnpm install (incremental) | 4131 ms / 4131 ms | 2157 ms / 2157 ms | 1.92× | pnpm-reinstall / cold: — |
| pnpm refresh | 3410 ms / 3410 ms | 2184 ms / 2184 ms | 1.56× | pnpm-reinstall / steady: — |
| tsc -b | 8056 ms / 8056 ms | 6441 ms / 7054 ms | 1.25× | tsc-b / cold: — |
| vitest | 6156 ms / 6156 ms | 3957 ms / 3957 ms | 1.56× | vitest / cold: — |

**Health:** 0 Workspaces open · 0 overlay files left · daemons 2 MB (+0 MB) over 5 of 5 Sandboxes · 15 open files · WAL before seal 0.0 KiB
**Resilience:** Busy 0 · EAGAIN 0 · refused unmount 0 · writer wait — · lane hold — per Commit (p50 / p95) · daemon RSS max 2 MB, median 2 MB over 1 daemons · overlay max — · unmount 13.3 ms / 25.2 ms

### Speed as history grows

Range 15 is the reference (owner 2026-10-19; a watch row, not a gate). Uncontended calls; read syscalls per solo in-process call stand in for SQLite page-cache misses (no hit/miss counter is reported by the binary); Workspace calls read in the daemon's process, so they have none here.

| Range | Commits | Store MiB | fs.write ≤1 KiB p50 ms (×r15) · VM steps · reads/call | fs.write ≤8 KiB p50 ms (×r15) · VM steps · reads/call | fs.write ≤64 KiB p50 ms (×r15) · VM steps · reads/call | fs.read ≤8 KiB p50 ms (×r15) · VM steps · reads/call | sandbox.mount p50 ms (×r15) · VM steps · reads/call | sandbox.commit 1 file (Committed) p50 ms (×r15) · VM steps · reads/call | branch.merge p50 ms (×r15) · VM steps · reads/call |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 015.a4 | 12851 | 207.8 | 5.90 (1.00×) · 6031 · not recorded | 6.21 (1.00×) · 6202 · not recorded | 7.29 (1.00×) · 6942 · not recorded | 1.99 (1.00×) · 3468 · not recorded | 9.12 (1.00×) · 1391 · not recorded | 8.34 (1.00×) · 5058 · not recorded | not split by class (before range 18) |
| 016.a3 | 14766 | 243.7 | 7.83 (1.33×) · 6936 · not recorded | 8.02 (1.29×) · 6716 · not recorded | 8.79 (1.21×) · 6961 · not recorded | 2.52 (1.26×) · 3468 · not recorded | 10.30 (1.13×) · 1337 · not recorded | 9.16 (1.10×) · 4389 · not recorded | not split by class (before range 18) |
| 017.a2 | 15811 | 265.7 | 10.12 (1.71×) · 6649 · not recorded | 9.42 (1.52×) · 6674 · not recorded | 10.07 (1.38×) · 7505 · not recorded | 2.91 (1.46×) · 3610 · not recorded | 11.52 (1.26×) · 1337 · not recorded | 10.18 (1.22×) · 5108 · not recorded | not split by class (before range 18) |
| 018.a6 | 17442 | 329.4 | 7.23 (1.23×) · 7012 · 308 (13 solo) | 7.31 (1.18×) · 6681 · 272 (125 solo) | 8.33 (1.14×) · 7276 · 340 (134 solo) | 2.48 (1.24×) · 3475 · — (0 solo) | 9.64 (1.06×) · 1337 · — (daemon) | 9.40 (1.13×) · 5265 · — (daemon) | 2709.77 (—×) · 15044810 · 26378 (3 solo) |
| 019.a4 | 18401 | 354.7 | 8.18 (1.39×) · 5950 · 250 (11 solo) | 8.63 (1.39×) · 6703 · 302 (93 solo) | 9.84 (1.35×) · 7721 · 357 (108 solo) | 3.23 (1.62×) · 4209 · 60 (2 solo) | 11.03 (1.21×) · 1337 · — (daemon) | 9.98 (1.20×) · 4896 · — (daemon) | 803.54 (—×) · 1377824 · 7245 (4 solo) |
| 020.a2 | 19322 | 374.1 | 7.09 (1.20×) · 6694 · 244 (50 solo) | 7.68 (1.24×) · 6821 · 267 (106 solo) | 8.57 (1.17×) · 7330 · 294 (92 solo) | 2.43 (1.22×) · 3716 · 207 (1 solo) | 10.00 (1.10×) · 1337 · — (daemon) | 9.37 (1.12×) · 5130 · — (daemon) | 888.05 (—×) · 1899898 · 9363 (3 solo) |
| 021.a2 | 20774 | 406.1 | 9.35 (1.58×) · 7305 · 274 (9 solo) | 8.02 (1.29×) · 5651 · 265 (69 solo) | 9.12 (1.25×) · 7036 · 322 (54 solo) | 2.20 (1.11×) · 3028 · — (0 solo) | 11.71 (1.28×) · 1337 · — (daemon) | 9.72 (1.16×) · 5225 · — (daemon) | 1007.13 (—×) · 844072 · 9186 (4 solo) |
| 022.a1 | 23062 | 444.9 | 7.04 (1.19×) · 5812 · 234 (17 solo) | 7.11 (1.14×) · 5968 · 218 (106 solo) | 8.58 (1.18×) · 6594 · 283 (105 solo) | 1.90 (0.95×) · 2092 · 63 (2 solo) | 10.46 (1.15×) · 1337 · — (daemon) | 9.07 (1.09×) · 4334 · — (daemon) | 1654.50 (—×) · 2513563 · 16357 (3 solo) |
| 023.a1 | 24522 | 506.8 | 7.57 (1.28×) · 5717 · 216 (7 solo) | 7.31 (1.18×) · 5936 · 261 (45 solo) | 7.92 (1.09×) · 6044 · 311 (37 solo) | 2.25 (1.13×) · 2690 · 179 (1 solo) | 9.78 (1.07×) · 1362 · — (daemon) | 9.51 (1.14×) · 4280 · — (daemon) | 283.86 (—×) · 464325 · 8582 (3 solo) |
| 024.a1 | 25762 | 537.2 | 7.75 (1.31×) · 6210 · 204 (27 solo) | 7.40 (1.19×) · 6347 · 242 (105 solo) | 7.97 (1.09×) · 6562 · 255 (134 solo) | 2.74 (1.38×) · 3257 · 78 (4 solo) | 11.01 (1.21×) · 1425 · — (daemon) | 9.24 (1.11×) · 3987 · — (daemon) | 455.67 (—×) · 674403 · 8922 (3 solo) |
| 025.a1 | 27563 | 627.9 | 9.69 (1.64×) · 7543 · 236 (1 solo) | 8.21 (1.32×) · 5480 · 251 (10 solo) | 8.21 (1.13×) · 5279 · 310 (6 solo) | 3.04 (1.53×) · 3708 · — (0 solo) | 11.06 (1.21×) · 1362 · — (daemon) | 9.32 (1.12×) · 3909 · — (daemon) | 229.07 (—×) · 361898 · 6093 (3 solo) |
| 026.a1 | 29975 | 669.9 | 6.47 (1.10×) · 6137 · 222 (56 solo) | 6.76 (1.09×) · 6376 · 256 (222 solo) | 7.59 (1.04×) · 6682 · 294 (198 solo) | 2.36 (1.19×) · 3365 · 79 (1 solo) | 10.01 (1.10×) · 1362 · — (daemon) | 8.93 (1.07×) · 5092 · — (daemon) | 333.81 (—×) · 621744 · 11927 (3 solo) |
| 027.a2 | 30629 | 688.0 | 7.75 (1.31×) · 6978 · 228 (24 solo) | 8.12 (1.31×) · 7581 · 288 (119 solo) | 8.98 (1.23×) · 7186 · 327 (41 solo) | 2.71 (1.36×) · 3304 · — (0 solo) | 10.03 (1.10×) · 1362 · — (daemon) | 10.59 (1.27×) · 5757 · — (daemon) | 392.93 (—×) · 655226 · 8832 (3 solo) |
| 028.a2 | 32548 | 737.6 | 6.63 (1.12×) · 5906 · 230 (9 solo) | 6.89 (1.11×) · 5882 · 223 (70 solo) | 8.07 (1.11×) · 6405 · 309 (100 solo) | 2.35 (1.18×) · 3179 · 46 (8 solo) | 10.04 (1.10×) · 1362 · — (daemon) | 10.11 (1.21×) · 4374 · — (daemon) | 268.20 (—×) · 418356 · 8462 (4 solo) |
| 029.a1 | 33478 | 774.1 | 9.40 (1.59×) · 8741 · 379 (13 solo) | 8.42 (1.36×) · 6823 · 370 (55 solo) | 8.70 (1.19×) · 6867 · 351 (26 solo) | 2.57 (1.29×) · 3834 · 55 (2 solo) | 10.23 (1.12×) · 1362 · — (daemon) | 8.83 (1.06×) · 4530 · — (daemon) | 454.73 (—×) · 806701 · 10820 (4 solo) |
| 030.a1 | 35023 | 803.7 | 11.61 (1.97×) · 6627 · 246 (20 solo) | 8.70 (1.40×) · 6083 · 271 (95 solo) | 8.80 (1.21×) · 6033 · 300 (131 solo) | 3.05 (1.53×) · 3118 · 48 (2 solo) | 12.55 (1.38×) · 1362 · — (daemon) | 10.40 (1.25×) · 4431 · — (daemon) | 319.45 (—×) · 470795 · 10330 (3 solo) |
| 031.a1 | 35351 | 835.9 | 10.84 (1.84×) · 9623 · — (0 solo) | 7.16 (1.15×) · 5428 · 604 (5 solo) | 7.65 (1.05×) · 5813 · 375 (2 solo) | 2.45 (1.23×) · 3199 · — (0 solo) | 9.88 (1.08×) · 1362 · — (daemon) | 8.96 (1.07×) · 3894 · — (daemon) | 2.22 (—×) · 517 · 29 (2 solo) |
| 032.a1 | 36538 | 870.9 | 8.46 (1.43×) · 7501 · 364 (16 solo) | 8.20 (1.32×) · 7234 · 347 (148 solo) | 8.68 (1.19×) · 7395 · 379 (121 solo) | 2.78 (1.39×) · 3904 · — (0 solo) | 10.21 (1.12×) · 1362 · — (daemon) | 8.89 (1.07×) · 4608 · — (daemon) | 411.44 (—×) · 721312 · 10559 (4 solo) |
| 033.a1 | 37184 | 890.5 | 8.67 (1.47×) · 6143 · 211 (1 solo) | 7.75 (1.25×) · 6430 · 313 (52 solo) | 8.79 (1.20×) · 6155 · 349 (41 solo) | 2.20 (1.10×) · 2939 · — (0 solo) | 10.93 (1.20×) · 1362 · — (daemon) | 9.95 (1.19×) · 3945 · — (daemon) | 275.58 (—×) · 323482 · 7567 (3 solo) |
| 034.a1 | 38594 | 922.8 | 8.67 (1.47×) · 7209 · 251 (12 solo) | 7.74 (1.25×) · 6773 · 286 (41 solo) | 8.25 (1.13×) · 6167 · 285 (64 solo) | 2.67 (1.34×) · 3236 · 109 (3 solo) | 9.90 (1.09×) · 1362 · — (daemon) | 11.18 (1.34×) · 5652 · — (daemon) | 323.49 (—×) · 478357 · 9655 (3 solo) |
| 035.a1 | 39429 | 946.2 | 9.31 (1.58×) · 7774 · 496 (3 solo) | 7.08 (1.14×) · 6352 · 374 (14 solo) | 7.95 (1.09×) · 6919 · 379 (35 solo) | 2.90 (1.45×) · 3561 · — (0 solo) | 9.60 (1.05×) · 1362 · — (daemon) | 9.73 (1.17×) · 5136 · — (daemon) | 1.65 (—×) · 517 · 42 (2 solo) |
| 036.a1 | 42419 | 983.6 | 4.94 (0.84×) · 4436 · 191 (10 solo) | 5.16 (0.83×) · 4546 · 179 (108 solo) | 5.66 (0.78×) · 4695 · 263 (58 solo) | 2.39 (1.20×) · 3015 · — (0 solo) | 9.14 (1.00×) · 1362 · — (daemon) | — (—×) · — · — (daemon) | 293.22 (—×) · 516618 · 9785 (3 solo) |
| 037.a1 | 44313 | 1021.6 | 6.90 (1.17×) · 5915 · 256 (17 solo) | 6.49 (1.04×) · 5682 · 260 (104 solo) | 7.31 (1.00×) · 6249 · 347 (75 solo) | 2.35 (1.18×) · 3344 · 46 (3 solo) | 9.89 (1.08×) · 1362 · — (daemon) | 8.00 (0.96×) · 5229 · — (daemon) | 336.24 (—×) · 498534 · 11405 (4 solo) |
| 038.a2 | 45294 | 1047.5 | 6.63 (1.12×) · 6925 · 193 (4 solo) | 6.80 (1.09×) · 6457 · 292 (38 solo) | 6.77 (0.93×) · 5696 · 451 (13 solo) | 2.04 (1.02×) · 3306 · 205 (1 solo) | 9.79 (1.07×) · 1362 · — (daemon) | 8.32 (1.00×) · 4461 · — (daemon) | 333.42 (—×) · 424298 · 9993 (3 solo) |
| 039.a1 | 46731 | 1087.5 | 8.82 (1.49×) · 8311 · 303 (20 solo) | 7.84 (1.26×) · 7620 · 370 (39 solo) | 8.44 (1.16×) · 7734 · 470 (23 solo) | 2.39 (1.20×) · 3326 · 93 (2 solo) | 9.97 (1.09×) · 1362 · — (daemon) | 8.24 (0.99×) · 4332 · — (daemon) | 271.77 (—×) · 460242 · 11032 (4 solo) |
| 040.a1 | 48092 | 1115.5 | 7.50 (1.27×) · 6245 · 256 (10 solo) | 7.75 (1.25×) · 6643 · 357 (37 solo) | 8.52 (1.17×) · 7129 · 416 (40 solo) | 2.57 (1.29×) · 3394 · — (0 solo) | 9.38 (1.03×) · 1362 · — (daemon) | 8.97 (1.08×) · 4484 · — (daemon) | 299.26 (—×) · 446500 · 10520 (4 solo) |
| 041.a1 | 48936 | 1146.6 | 8.71 (1.47×) · 6751 · 270 (18 solo) | 8.10 (1.30×) · 5915 · 374 (42 solo) | 9.30 (1.28×) · 6306 · 383 (58 solo) | 2.31 (1.16×) · 3228 · 125 (1 solo) | 9.74 (1.07×) · 1362 · — (daemon) | 9.90 (1.19×) · 4616 · — (daemon) | 308.48 (—×) · 515638 · 11672 (3 solo) |
| 042.a1 | 50146 | 1182.0 | 7.38 (1.25×) · 6433 · 273 (34 solo) | 7.64 (1.23×) · 6300 · 317 (104 solo) | 7.43 (1.02×) · 5793 · 297 (61 solo) | 2.54 (1.27×) · 3075 · 83 (5 solo) | 10.05 (1.10×) · 1362 · — (daemon) | 9.72 (1.17×) · 4266 · — (daemon) | 464.11 (—×) · 737059 · 13057 (4 solo) |
| 043.a1 | 51610 | 1223.8 | 7.04 (1.19×) · 6937 · 276 (27 solo) | 7.41 (1.19×) · 6674 · 345 (49 solo) | 7.43 (1.02×) · 6556 · 343 (100 solo) | 2.42 (1.21×) · 3278 · 189 (2 solo) | 8.87 (0.97×) · 1362 · — (daemon) | 9.28 (1.11×) · 4581 · — (daemon) | 348.56 (—×) · 554099 · 12963 (3 solo) |
| 044.a2 | 52850 | 1254.5 | 7.31 (1.24×) · 7053 · 256 (20 solo) | 6.85 (1.10×) · 6738 · 308 (64 solo) | 7.35 (1.01×) · 6625 · 381 (79 solo) | 2.16 (1.08×) · 3080 · 54 (3 solo) | 8.76 (0.96×) · 1362 · — (daemon) | 8.74 (1.05×) · 4260 · — (daemon) | 166.26 (—×) · 357340 · 8322 (3 solo) |
| 045.a1 | 53964 | 1286.9 | 7.24 (1.23×) · 7087 · 286 (16 solo) | 6.95 (1.12×) · 7135 · 317 (77 solo) | 7.55 (1.04×) · 6871 · 305 (76 solo) | 2.38 (1.20×) · 3611 · 94 (9 solo) | 8.87 (0.97×) · 1362 · — (daemon) | 9.39 (1.13×) · 4995 · — (daemon) | 305.33 (—×) · 485040 · 12305 (3 solo) |
| 046.a1 | 54791 | 1312.2 | 7.64 (1.29×) · 8172 · 168 (2 solo) | 7.70 (1.24×) · 7367 · 303 (32 solo) | 8.00 (1.10×) · 6914 · 301 (66 solo) | 2.71 (1.36×) · 3485 · 79 (7 solo) | 8.82 (0.97×) · 1362 · — (daemon) | 8.56 (1.03×) · 4699 · — (daemon) | 307.16 (—×) · 466212 · 11223 (3 solo) |
| 047.a1 | 56578 | 1359.1 | 8.35 (1.41×) · 7640 · 335 (21 solo) | 8.40 (1.35×) · 7202 · 410 (88 solo) | 8.54 (1.17×) · 6821 · 418 (67 solo) | 2.54 (1.28×) · 3466 · 131 (1 solo) | 9.45 (1.04×) · 1362 · — (daemon) | 11.63 (1.39×) · 5490 · — (daemon) | 433.20 (—×) · 654351 · 15082 (4 solo) |
| 048.a1 | 58088 | 1390.3 | 8.33 (1.41×) · 7008 · 378 (15 solo) | 7.76 (1.25×) · 6851 · 262 (85 solo) | 9.03 (1.24×) · 6564 · 313 (61 solo) | 2.81 (1.41×) · 3334 · 111 (7 solo) | 9.90 (1.08×) · 1362 · — (daemon) | 9.04 (1.08×) · 4602 · — (daemon) | 327.87 (—×) · 344822 · 9703 (3 solo) |
| 049.a1 | 59295 | 1426.0 | 8.07 (1.37×) · 6352 · 328 (10 solo) | 8.18 (1.32×) · 6850 · 307 (54 solo) | 8.84 (1.21×) · 7371 · 362 (51 solo) | 3.27 (1.64×) · 4122 · 75 (7 solo) | 9.92 (1.09×) · 1362 · — (daemon) | 10.33 (1.24×) · 4329 · — (daemon) | 213.34 (—×) · 334840 · 7279 (4 solo) |
| 050.a1 | 60450 | 1462.0 | 7.36 (1.25×) · 7605 · 383 (12 solo) | 8.30 (1.34×) · 7756 · 375 (45 solo) | 8.39 (1.15×) · 6315 · 414 (17 solo) | 2.75 (1.38×) · 3950 · 225 (3 solo) | 9.61 (1.05×) · 1362 · — (daemon) | 8.81 (1.06×) · 3657 · — (daemon) | 459.51 (—×) · 530087 · 12571 (3 solo) |
| 051.a1 | 61383 | 1486.0 | 8.40 (1.42×) · 7415 · 341 (22 solo) | 7.57 (1.22×) · 6531 · 238 (89 solo) | 7.62 (1.04×) · 6446 · 278 (97 solo) | 2.55 (1.28×) · 3609 · 71 (8 solo) | 9.41 (1.03×) · 1362 · — (daemon) | 10.36 (1.24×) · 5130 · — (daemon) | 361.34 (—×) · 426337 · 10118 (3 solo) |
| 052.a1 | 62546 | 1527.8 | 8.42 (1.43×) · 7262 · 342 (30 solo) | 7.84 (1.26×) · 6616 · 294 (59 solo) | 8.42 (1.15×) · 6023 · 385 (71 solo) | 2.54 (1.28×) · 3082 · — (0 solo) | 9.94 (1.09×) · 1362 · — (daemon) | 8.67 (1.04×) · 4221 · — (daemon) | 367.37 (—×) · 482357 · 12922 (3 solo) |
| 053.a1 | 63409 | 1550.9 | 8.89 (1.51×) · 7121 · 293 (18 solo) | 8.78 (1.41×) · 6567 · 421 (50 solo) | 10.08 (1.38×) · 6512 · 450 (40 solo) | 2.67 (1.34×) · 4309 · 235 (2 solo) | 10.60 (1.16×) · 1362 · — (daemon) | 9.77 (1.17×) · 4992 · — (daemon) | 247.84 (—×) · 324874 · 8146 (3 solo) |
| 054.a1 | 64802 | 1581.6 | 7.91 (1.34×) · 6951 · 232 (25 solo) | 8.69 (1.40×) · 6748 · 292 (52 solo) | 9.06 (1.24×) · 6801 · 344 (57 solo) | 2.41 (1.21×) · 3590 · 53 (2 solo) | 9.82 (1.08×) · 1362 · — (daemon) | 8.88 (1.06×) · 5205 · — (daemon) | 367.61 (—×) · 504299 · 12592 (4 solo) |
| 055.a1 | 65543 | 1604.4 | 9.52 (1.61×) · 7149 · 262 (24 solo) | 10.65 (1.71×) · 7457 · 339 (83 solo) | 9.23 (1.27×) · 5796 · 333 (56 solo) | 3.19 (1.60×) · 4074 · 77 (6 solo) | 10.30 (1.13×) · 1362 · — (daemon) | 9.66 (1.16×) · 3942 · — (daemon) | 422.43 (—×) · 350398 · 10094 (3 solo) |
| 056.a1 | 66733 | 1634.0 | 10.66 (1.81×) · 7896 · 313 (11 solo) | 10.31 (1.66×) · 7283 · 341 (25 solo) | 10.65 (1.46×) · 6820 · 413 (30 solo) | 3.04 (1.52×) · 3866 · 35 (2 solo) | 11.63 (1.27×) · 1362 · — (daemon) | 8.99 (1.08×) · 4188 · — (daemon) | 457.77 (—×) · 382689 · 11272 (4 solo) |
| 057.a1 | 67927 | 1662.7 | 8.31 (1.41×) · 7370 · 369 (21 solo) | 8.37 (1.35×) · 6968 · 411 (60 solo) | 9.24 (1.27×) · 7403 · 435 (75 solo) | 2.85 (1.43×) · 4010 · 128 (2 solo) | 9.97 (1.09×) · 1437 · — (daemon) | 8.64 (1.04×) · 5397 · — (daemon) | 513.59 (—×) · 634430 · 15544 (3 solo) |
| 058.a3 | 69520 | 1692.3 | 8.04 (1.36×) · 7195 · 302 (64 solo) | 7.82 (1.26×) · 6899 · 309 (172 solo) | 9.18 (1.26×) · 7267 · 336 (125 solo) | 2.80 (1.41×) · 3324 · 82 (1 solo) | 10.46 (1.15×) · 1362 · — (daemon) | 8.70 (1.04×) · 3999 · — (daemon) | 469.95 (—×) · 752096 · 15476 (3 solo) |
| 059.a1 | 70240 | 1715.3 | 9.33 (1.58×) · 7428 · 341 (18 solo) | 9.30 (1.50×) · 7507 · 355 (40 solo) | 9.63 (1.32×) · 7267 · 408 (37 solo) | 3.29 (1.65×) · 4034 · — (0 solo) | 10.20 (1.12×) · 1362 · — (daemon) | 9.08 (1.09×) · 4557 · — (daemon) | 432.16 (—×) · 391525 · 12008 (3 solo) |

**WAL across each class this range:** fs.write ≤1 KiB 4288952 → 4120032 B · fs.write ≤8 KiB 4161232 → 4120032 B · fs.write ≤64 KiB 4194304 → 4120032 B · fs.read ≤8 KiB 4194304 → 4194304 B · sandbox.mount 4194304 → 2797512 B · sandbox.commit 1 file (Committed) 4194304 → 4194304 B · branch.merge 61832 → 3547352 B
**Host load (1-min, recorded, not waited on):** macOS 6.28 at the first command → 5.75 after the last (max 6.92 over 8 commands) · Docker VM 1.64 → 1.34

**Control probe** (one sample per arm, same window and binaries; (a) the range 15 Store, (b) the range's). Gap: each clone is copied just before its arm, which warms the OS cache equally in both, so the control cannot see a cold-read effect of a larger Store (storage reads are 0 in both arms); it compares warm-cache work only.

| Sample | (a) Commits · MiB | (b) Commits · MiB | fs.write ≤1 KiB: (a) / (b) p50 ms · (b)/(a) · reads/call (a)/(b) | fs.write ≤8 KiB: (a) / (b) p50 ms · (b)/(a) · reads/call (a)/(b) | fs.read ≤8 KiB: (a) / (b) p50 ms · (b)/(a) · reads/call (a)/(b) | Host load (macOS) | Watch |
| --- | --- | --- | --- | --- | --- | --- | --- |
| control-017.diag-15v17 | 12851 · 207.8 | 15811 · 265.7 | failed: (a) 0 of ? calls ok, (b) 0 ok | failed: (a) 0 of ? calls ok, (b) 0 ok | 2.79 (1.00× first) / 2.43 · 0.87× · 73/57 | 9.15 → 9.53 | not judged (failed calls) |
| control-017.diag-15v17-2 | 12851 · 207.8 | 15811 · 265.7 | 6.21 (1.00× first) / 6.63 · 1.07× · 114/112 | 6.39 (1.00× first) / 6.40 · 1.00× · 109/110 | 2.59 (0.93× first) / 2.32 · 0.89× · 73/57 | 11.39 → 10.96 | pass |
| control-018.a1 | 12851 · 207.8 | 17442 · 328.3 | 6.63 (1.07× first) / 7.01 · 1.06× · 113/112 | 6.46 (1.01× first) / 6.41 · 0.99× · 108/108 | 2.74 (0.98× first) / 2.53 · 0.92× · 73/70 | 10.05 → 10.05 | pass |
| control-018.a2 | 12851 · 207.8 | 17442 · 328.4 | 6.23 (1.00× first) / 6.62 · 1.06× · 116/111 | 6.37 (1.00× first) / 6.24 · 0.98× · 110/109 | 2.41 (0.86× first) / 2.35 · 0.97× · 73/67 | 9.83 → 9.69 | pass |
| control-018.a3 | 12851 · 207.8 | 17442 · 328.3 | 6.67 (1.08× first) / 6.47 · 0.97× · 109/111 | 6.72 (1.05× first) / 6.49 · 0.97× · 109/109 | 2.73 (0.98× first) / 2.61 · 0.96× · 73/70 | 8.25 → 8.25 | pass |
| control-018.a4 | 12851 · 207.8 | 17442 · 328.7 | 6.53 (1.05× first) / 6.95 · 1.06× · 110/129 | 6.44 (1.01× first) / 6.80 · 1.06× · 109/110 | 2.60 (0.93× first) / 2.89 · 1.11× · 73/71 | 10.05 → 10.29 | pass |
| control-018.a6 | 12851 · 207.8 | 17442 · 329.4 | 6.35 (1.02× first) / 6.26 · 0.99× · 115/116 | 6.28 (0.98× first) / 5.97 · 0.95× · 108/111 | 3.14 (1.13× first) / 2.24 · 0.71× · 73/77 | 6.84 → 6.84 | pass |
| control-019.a3 | 12851 · 207.8 | 18401 · 354.4 | 5.85 (0.94× first) / 5.96 · 1.02× · 113/116 | 5.50 (0.86× first) / 6.08 · 1.11× · 108/113 | 2.39 (0.86× first) / 2.31 · 0.96× · 74/75 | 10.18 → 11.45 | pass |
| control-019.a4 | 12851 · 207.8 | 18401 · 354.7 | 6.15 (0.99× first) / 7.52 · 1.22× · 111/138 | 6.76 (1.06× first) / 6.60 · 0.98× · 108/111 | 2.80 (1.01× first) / 2.51 · 0.90× · 74/76 | 10.96 → 10.57 | pass |
| control-020.a1 | 12851 · 207.8 | 19322 · 374.2 | 6.10 (0.98× first) / 7.15 · 1.17× · 112/141 | 6.20 (0.97× first) / 5.95 · 0.96× · 109/110 | 2.48 (0.89× first) / 2.40 · 0.97× · 70/79 | 10.08 → 9.76 | pass |
| control-020.a2 | 12851 · 207.8 | 19322 · 374.1 | 5.49 (0.88× first) / 6.81 · 1.24× · 113/115 | 5.82 (0.91× first) / 5.75 · 0.99× · 108/112 | 1.96 (0.70× first) / 1.94 · 0.99× · 70/80 | 9.23 → 8.97 | pass |
| control-021.a2 | 12851 · 207.8 | 20774 · 406.1 | 6.48 (1.04× first) / 5.93 · 0.92× · 113/110 | 6.26 (0.98× first) / 5.98 · 0.96× · 107/110 | 2.28 (0.82× first) / 1.97 · 0.86× · 77/86 | 9.19 → 9.19 | pass |
| control-022.a1 | 12851 · 207.8 | 23062 · 442.2 | 6.19 (1.00× first) / 7.39 · 1.20× · 116/115 | 5.89 (0.92× first) / 6.35 · 1.08× · 109/113 | 2.51 (0.90× first) / 2.16 · 0.86× · 92/81 | 9.12 → 8.71 | pass |
| control-023.a1 | 12851 · 207.8 | 24522 · 506.8 | 5.66 (0.91× first) / 5.42 · 0.96× · 114/117 | 5.41 (0.85× first) / 5.50 · 1.02× · 110/116 | 2.86 (1.03× first) / 2.28 · 0.80× · 76/81 | 10.38 → 10.38 | pass |
| control-024.a1 | 12851 · 207.8 | 25762 · 534.5 | 5.86 (0.94× first) / 5.67 · 0.97× · 113/130 | 5.72 (0.90× first) / 5.98 · 1.05× · 111/119 | 2.63 (0.95× first) / 2.54 · 0.97× · 75/78 | 12.49 → 12.13 | pass |
| control-025.a1 | 12851 · 207.8 | 27563 · 627.9 | 10.27 (1.65× first) / 10.70 · 1.04× · 115/119 | 10.78 (1.69× first) / 9.42 · 0.87× · 109/115 | 6.32 (2.27× first) / 6.64 · 1.05× · 75/100 | 11.62 → 12.06 | pass |
| control-026.a1 | 12851 · 207.8 | 29975 · 667.3 | 5.04 (0.81× first) / 6.12 · 1.22× · 115/148 | 5.36 (0.84× first) / 5.56 · 1.04× · 110/119 | 2.24 (0.80× first) / 2.39 · 1.06× · 73/90 | 7.87 → 8.12 | pass |
| control-027.a1 | 12851 · 207.8 | 30629 · 688.1 | 5.59 (0.90× first) / 6.36 · 1.14× · 115/134 | 5.84 (0.91× first) / 6.16 · 1.05× · 108/124 | 2.58 (0.93× first) / 2.33 · 0.90× · 68/80 | 9.22 → 8.97 | pass |
| control-027.a2 | 12851 · 207.8 | 30629 · 688.0 | 6.10 (0.98× first) / 5.69 · 0.93× · 113/129 | 5.39 (0.84× first) / 5.73 · 1.06× · 111/122 | 2.12 (0.76× first) / 1.84 · 0.87× · 68/76 | 11.42 → 10.90 | pass |
| control-028.a1 | 12851 · 207.8 | 32548 · 737.6 | 5.91 (0.95× first) / 6.25 · 1.06× · 115/120 | 5.90 (0.92× first) / 5.67 · 0.96× · 112/118 | 2.56 (0.92× first) / 3.11 · 1.22× · 67/126 | 7.82 → 7.67 | pass |
| control-028.a2 | 12851 · 207.8 | 32548 · 737.6 | 6.12 (0.99× first) / 5.88 · 0.96× · 113/122 | 5.56 (0.87× first) / 5.64 · 1.01× · 110/120 | 2.14 (0.77× first) / 2.71 · 1.26× · 67/127 | 8.05 → 8.05 | pass |
| control-029.a1 | 12851 · 207.8 | 33478 · 771.5 | 5.60 (0.90× first) / 6.23 · 1.11× · 112/135 | 5.49 (0.86× first) / 5.69 · 1.04× · 109/120 | 2.54 (0.91× first) / 2.67 · 1.05× · 71/111 | 6.98 → 8.74 | pass |
| control-030.a1 | 12851 · 207.8 | 35023 · 803.7 | 6.52 (1.05× first) / 6.57 · 1.01× · 115/145 | 5.74 (0.90× first) / 5.93 · 1.03× · 109/122 | 2.34 (0.84× first) / 2.64 · 1.13× · 66/96 | 8.48 → 8.48 | pass |
| control-031.a1 | 12851 · 207.8 | 35351 · 835.9 | 5.70 (0.92× first) / 6.21 · 1.09× · 114/149 | 5.63 (0.88× first) / 6.05 · 1.07× · 110/121 | 2.25 (0.81× first) / 2.54 · 1.13× · 69/87 | 8.96 → 8.88 | pass |
| control-032.a1 | 12851 · 207.8 | 36538 · 868.0 | 6.10 (0.98× first) / 5.38 · 0.88× · 112/149 | 5.68 (0.89× first) / 5.18 · 0.91× · 109/124 | 2.23 (0.80× first) / 2.07 · 0.93× · 72/105 | 7.71 → 7.49 | pass |
| control-033.a1 | 12851 · 207.8 | 37184 · 890.5 | 4.97 (0.80× first) / 5.69 · 1.14× · 113/146 | 4.97 (0.78× first) / 5.09 · 1.02× · 110/125 | 2.22 (0.80× first) / 2.59 · 1.17× · 87/101 | 11.27 → 11.01 | pass |
| control-034.a1 | 12851 · 207.8 | 38594 · 919.9 | 6.44 (1.04× first) / 6.01 · 0.93× · 115/148 | 5.11 (0.80× first) / 5.24 · 1.02× · 111/126 | 2.34 (0.84× first) / 2.42 · 1.03× · 72/106 | 12.20 → 11.47 | pass |
| control-035.a1 | 12851 · 207.8 | 39429 · 946.2 | 5.19 (0.84× first) / 5.65 · 1.09× · 116/128 | 5.27 (0.83× first) / 4.88 · 0.93× · 111/125 | 2.06 (0.74× first) / 2.45 · 1.19× · 72/112 | 8.02 → 7.78 | pass |
| control-036.a1 | 12851 · 207.8 | 42419 · 980.9 | 5.88 (0.95× first) / 5.68 · 0.97× · 113/236 | 5.55 (0.87× first) / 5.36 · 0.96× · 109/129 | 2.03 (0.73× first) / 2.34 · 1.15× · 62/130 | 6.20 → 6.67 | watch (fs.write ≤1 KiB, fs.read ≤8 KiB) |
| control-037.a1 | 12851 · 207.8 | 44313 · 1021.6 | 5.21 (0.84× first) / 5.51 · 1.06× · 115/135 | 4.95 (0.77× first) / 5.01 · 1.01× · 110/126 | 2.30 (0.82× first) / 2.45 · 1.06× · 74/117 | 6.41 → 7.18 | pass |
| control-038.a1 | 12851 · 207.8 | 44313 · 1047.7 | 5.49 (0.88× first) / 5.82 · 1.06× · 112/147 | 5.80 (0.91× first) / 4.91 · 0.85× · 109/125 | 2.34 (0.84× first) / 2.54 · 1.09× · 75/115 | 7.06 → 7.21 | pass |
| control-038.a2 | 12851 · 207.8 | 45294 · 1047.5 | 5.38 (0.87× first) / 6.70 · 1.25× · 114/146 | 4.88 (0.76× first) / 5.01 · 1.03× · 110/123 | 2.65 (0.95× first) / 2.43 · 0.92× · 75/116 | 6.58 → 6.53 | pass |
| control-039.a1 | 12851 · 207.8 | 46731 · 1084.9 | 5.66 (0.91× first) / 5.67 · 1.00× · 113/133 | 5.27 (0.82× first) / 5.60 · 1.06× · 108/123 | 2.26 (0.81× first) / 2.62 · 1.16× · 75/137 | 6.90 → 6.75 | pass |
| control-040.a1 | 12851 · 207.8 | 48092 · 1115.5 | 5.35 (0.86× first) / 5.33 · 1.00× · 113/131 | 4.95 (0.77× first) / 4.91 · 0.99× · 110/122 | 2.10 (0.76× first) / 2.11 · 1.00× · 70/116 | 6.23 → 6.21 | pass |
| control-041.a1 | 12851 · 207.8 | 48936 · 1143.9 | 5.63 (0.91× first) / 5.34 · 0.95× · 113/130 | 5.32 (0.83× first) / 5.27 · 0.99× · 110/127 | 2.36 (0.85× first) / 2.64 · 1.12× · 72/135 | 7.33 → 7.33 | pass |
| control-042.a1 | 12851 · 207.8 | 50146 · 1182.0 | 5.32 (0.86× first) / 5.16 · 0.97× · 114/135 | 4.82 (0.75× first) / 5.29 · 1.10× · 108/124 | 2.13 (0.77× first) / 2.10 · 0.98× · 72/123 | 5.48 → 5.28 | pass |
| control-043.a1 | 12851 · 207.8 | 51610 · 1221.4 | 5.00 (0.81× first) / 5.39 · 1.08× · 114/153 | 4.88 (0.76× first) / 5.16 · 1.06× · 110/127 | 1.95 (0.70× first) / 2.23 · 1.14× · 79/120 | 5.43 → 5.23 | pass |
| control-044.a2 | 12851 · 207.8 | 52850 · 1254.5 | 5.58 (0.90× first) / 6.18 · 1.11× · 113/155 | 5.01 (0.78× first) / 4.88 · 0.97× · 110/131 | 2.18 (0.78× first) / 2.01 · 0.92× · 81/111 | 5.11 → 5.19 | pass |
| control-045.a1 | 12851 · 207.8 | 53964 · 1283.6 | 5.24 (0.84× first) / 5.00 · 0.95× · 115/131 | 4.73 (0.74× first) / 5.15 · 1.09× · 109/124 | 2.14 (0.77× first) / 2.36 · 1.10× · 81/115 | 5.00 → 4.76 | pass |
| control-046.a1 | 12851 · 207.8 | 54791 · 1312.2 | 4.73 (0.76× first) / 5.07 · 1.07× · 114/130 | 4.75 (0.74× first) / 4.57 · 0.96× · 109/127 | 2.08 (0.75× first) / 2.06 · 0.99× · 93/105 | 4.32 → 4.38 | pass |
| control-047.a1 | 12851 · 207.8 | 56578 · 1356.7 | 15.13 (2.44× first) / 5.85 · 0.39× · 114/127 | 9.49 (1.49× first) / 6.35 · 0.67× · 109/125 | 3.13 (1.12× first) / 3.46 · 1.10× · 89/130 | 12.40 → 14.05 | pass |
| control-048.a1 | 12851 · 207.8 | 58088 · 1390.3 | 5.27 (0.85× first) / 4.91 · 0.93× · 113/128 | 4.58 (0.72× first) / 4.72 · 1.03× · 111/125 | 2.30 (0.83× first) / 3.17 · 1.38× · 89/164 | 7.99 → 7.67 | pass |
| control-049.a1 | 12851 · 207.8 | 59295 · 1423.3 | 5.78 (0.93× first) / 5.60 · 0.97× · 114/139 | 5.80 (0.91× first) / 5.66 · 0.98× · 109/127 | 2.72 (0.98× first) / 3.27 · 1.20× · 89/164 | 16.50 → 15.82 | pass |
| control-050.a1 | 12851 · 207.8 | 60450 · 1462.0 | 8.62 (1.39× first) / 6.89 · 0.80× · 114/131 | 12.07 (1.89× first) / 7.13 · 0.59× · 110/126 | 6.75 (2.42× first) / 5.18 · 0.77× · 90/161 | 6.45 → 7.13 | pass |
| control-051.a1 | 12851 · 207.8 | 61383 · 1486.0 | 6.69 (1.08× first) / 5.70 · 0.85× · 116/156 | 5.60 (0.88× first) / 4.93 · 0.88× · 112/127 | 2.61 (0.94× first) / 2.92 · 1.12× · 90/144 | 7.43 → 7.15 | pass |
| control-052.a1 | 12851 · 207.8 | 62546 · 1527.8 | 5.48 (0.88× first) / 6.37 · 1.16× · 116/130 | 5.38 (0.84× first) / 5.50 · 1.02× · 111/127 | 2.69 (0.96× first) / 2.85 · 1.06× · 90/145 | 8.02 → 7.62 | pass |
| control-053.a1 | 12851 · 207.8 | 63409 · 1550.9 | 5.28 (0.85× first) / 6.45 · 1.22× · 113/142 | 5.34 (0.84× first) / 5.66 · 1.06× · 111/125 | 2.77 (0.99× first) / 2.78 · 1.00× · 90/123 | 7.87 → 7.64 | pass |
| control-054.a1 | 12851 · 207.8 | 64802 · 1581.6 | 5.87 (0.95× first) / 5.30 · 0.90× · 116/129 | 6.10 (0.95× first) / 5.30 · 0.87× · 110/124 | 2.46 (0.88× first) / 2.92 · 1.19× · 74/117 | 9.96 → 9.48 | pass |
| control-055.a1 | 12851 · 207.8 | 65543 · 1604.4 | 5.43 (0.87× first) / 5.86 · 1.08× · 116/132 | 5.58 (0.87× first) / 5.82 · 1.04× · 111/128 | 2.47 (0.88× first) / 3.15 · 1.28× · 74/109 | 5.70 → 5.75 | pass |
| control-056.a1 | 12851 · 207.8 | 66733 · 1634.0 | 8.03 (1.29× first) / 7.10 · 0.88× · 121/135 | 7.29 (1.14× first) / 8.01 · 1.10× · 112/129 | 3.08 (1.11× first) / 3.14 · 1.02× · 72/124 | 5.59 → 5.86 | pass |
| control-057.a1 | 12851 · 207.8 | 67927 · 1662.7 | 8.61 (1.39× first) / 5.59 · 0.65× · 113/130 | 5.75 (0.90× first) / 5.64 · 0.98× · 111/128 | 2.60 (0.93× first) / 4.08 · 1.57× · 72/112 | 8.25 → 8.15 | pass |
| control-058.a3 | 12851 · 207.8 | 69520 · 1692.3 | 5.99 (0.96× first) / 6.24 · 1.04× · 114/144 | 5.47 (0.86× first) / 6.33 · 1.16× · 110/129 | 2.48 (0.89× first) / 3.18 · 1.28× · 72/121 | 7.25 → 6.99 | pass |
| control-059.a1 | 12851 · 207.8 | 70240 · 1715.3 | 6.49 (1.05× first) / 6.64 · 1.02× · 115/131 | 6.49 (1.02× first) / 6.33 · 0.98× · 111/129 | 3.15 (1.13× first) / 3.14 · 1.00× · 76/118 | 8.98 → 8.50 | pass |

**Watch row** (control (b)/(a) p50 over 1.25×, or (b)'s reads per call over 2× (a)'s): pass (sample control-059.a1)

## 5. Findings and action

**Optimization:** none — no problems found.

### Open issues touching this range

| Id | Issue | Owner | Next step |
| --- | --- | --- | --- |
| F-002 | full-scan steps on hot paths | lead | see BUGS.md |
| F-006 | health cannot judge overlay files left | the builder | measure it per range, REPORT_FORMAT.md |
| F-007 | Trends were never written | the builder | see BUGS.md |
| F-013 | per-entry gate trips on a fixed per-checkpoint cost | lead | see BUGS.md |
| F-014 | the "one-file" `diff_commits` probe had a drifting input | lead | see BUGS.md |
| F-020 | Store calls cross a Sandbox for no reason | the fixer | now (the builder keeps playing P2 on the current route until the switch) |
| F-025 | Commits queue behind in-lane merges whose path search walks the tree | the fixer | now; fix 1 (top-down path naming) first, then lane narrowing, reads off the writer queue, and fixed per-call costs |
| F-030 | `daemon[].fuse.served` on traced exec lines is cumulative | the builder checks the `oneshot_exec` probe split | 08de4f038 |
| F-031 | the replay's Workspaces have no `.git` | the builder | after the P3 dev checks, measuring Store growth per git commit (index, loose objects, packs) and the wall time added per range |
| F-032 | deleting a base tree over FUSE costs ~0.7 ms per entry | the fixer | after item 7, with per-op timing first (D0) |
| F-033 | `MAXIMUM_LINEAGE_ROWS` | the fixer | queued after that confirmation**; the lead places it in the item order |
| F-034 | a fresh mount path per mount leaves absolute paths stale | lead | see BUGS.md |
| F-035 | fs read calls scan one byte at a time and re-walk pages | lead | see BUGS.md |
| F-036 | concurrent first installs from two daemons: one Commit fails "object … is not stored" | lead | see BUGS.md |
| F-042 | exec over committed content is slow: vitest 3.7×, `tsc -b` 1.5× native; base reads grow with directory size | the #352 lead and fixer**; the lead places it | see BUGS.md |
| F-044 | a kernel reply computed before a merged install can land after its invalidation | #359** | D-9 lane |
| F-045 | hard-linked files are never entry-cached on the pinned image's kernel | lead | see BUGS.md |
| F-046 | a terminal unmount in two mount tests fails intermittently | lead | see BUGS.md |
| F-047 | `fp21_detach_stages` fails 0/2 after the A1 merge | unassigned** | A1 owner #354 or the lead |
| F-048 | an Unmount without `discard` is refused after an mtime-only Commit | lead | see BUGS.md |
| F-049 | `fp31` TooSmall's staged premise races an early kernel FORGET | unassigned | see BUGS.md |
| F-050 | a full-case `cost.mjs` run warms the daemon cache for its LayerFS arm | unassigned** | the cost harness owner, or #362 |
| F-051 | `kernel_coherence` `size_never_shrinks_under_concurrent_append_and_refusals_stay_refused` failed once | unassigned | see BUGS.md |
| F-052 | a chmod is lost when the other side edits the same file | lead | see BUGS.md |
| F-053 | the SDK discovery lock outlives its Guard across a fork→exec window | lead | see BUGS.md |
| F-054 | a Sandbox's PID 1 never reaps orphaned processes | lead | see BUGS.md |
| F-055 | direct_locking_real's oracle assumes an order the test does not make | lead | see BUGS.md |
| F-056 | a build that rewrites identical outputs is redone after every remount | lead | see BUGS.md |
| F-057 | newest-wins over pnpm's install state lets the repair keep stale hoisting | lead | see BUGS.md |
| F-058 | the native repair chain ran the lanes on top of each other | lead | see BUGS.md |
| F-059 | lanes' stale build output outlives the repair, and the point oracle's base cannot carry it | lead | see BUGS.md |
| F-060 | the native repair chain never applied the consolidation's reconcile | lead | see BUGS.md |

### Lead's note (written by the lead; never empty unless the verdict is pass)

- **a1 (`p3-main-x-c`, daemon `c41a86d2`, addon `a1078e69`, main `d06a2b81fa` binaries): WATCH, terminal.** Checkpoint ok, git ✓. Node: 3 lane points P1–P5 pass and repair P6 pass; 17 pass, 0 stop. Control `control-059.a1` passes. Native first passed with no fix.
- **The first range judged only against the d06a2b81fa re-baseline.** Scaling and Counters have 2 of 3 same-binary points and are not judged yet.
- **Speed watch:** `sandbox.exec` uncontended 1.63× baseline, with no phase.
- **Timing-sensitive list (SCRIPTS §16):** `skill-local-watcher.spec.ts` is not in any of r59's calibrated run lists; no lane point touched `packages/skill`. It was not run, so there is nothing to judge.
- **Lane exec on the new binaries (liaison condition).** p3-main-x never played r59, so the old binaries have no same-point times. The native same-tree run is the in-range control:

  | Point | vitest ms (files) | tsc ms | vitest / native | tsc / native | host load |
  | --- | --- | --- | --- | --- | --- |
  | `r059-1-packages-client.end` | 17,924 (98) | 7,345 | 1.82× | 1.14× | 6.1–6.9 |
  | `r059-2-root.end` | 6,156 (29) | 9,795 | 1.86× | 1.39× | 6.7–6.9 |
  | `r059-3-agents-notes.end` | 5,895 (40) | 8,056 | 1.49× | 1.34× | 6.7–6.9 |

  - For reference, the old binaries (`p3-main-x`) at r55–r57 ran vitest 1.21–3.86× and tsc 1.20–2.57× native, at load 8–12. r58 a3 ran 2.70–3.17× and 1.75–2.14×, at load 7.6–10.
  - At load 6–7, r59 is inside the old binaries' range. So far this does not read as a binary slowdown above 25%; r60 adds three more points.
- **F-063 active:** chunk PREFIX 446 against FULL 213, over 99 lane git Commits (96 with a PREFIX chunk). f063.mjs exit 0.
- **Storage watch:**

  | | r59 | r58 a3 |
  | --- | --- | --- |
  | Store | +23.1 MiB | +29.6 MiB |
  | `.git` stored | +7.8 MiB | |
  | Index rows | +10.8 MiB (→ 539.5 MiB) | |

  Added this range: 25.5 MiB.
- **Clean:** git clean found 88 untracked, unignored files (888,140 B) before the `-d` clean.
- **Steps:**
  - Lead 3 s. Cuts 30, 45 and 52: 27, 15 and 67 s; the cuts avoid the stale-clean-merge at 0–9 and the commit-conflict at 24.6–25.4. Lanes 66 s.
  - Repair 138 s (install 41.2, build 32.6, tests 2.5).
  - Verify 21 s. Finish 62 s of 90 s.
  - Host load 5.8–6.9.
- **Snapshot:** 1,466.3 MiB new, 5.5 s.


## Appendix

### A. Checks

| Check | Value | Threshold | Result |
| --- | --- | --- | --- |
| Correctness | tree ok; steps 1679/1679; conflicts 4/4; tests 30/30 equal to native | all | pass |
| Health | 0 open, 0 overlays | 0, 0, flat | pass |
| Speed | sandbox.exec — · uncontended: 1.63× baseline (no phase) | ≤ 1.2× | watch |
| Scaling | insufficient same-binary points: 2 of 3 (daemon c41a86d23822); also not judged: oneshot_exec: 2 of 3 points of probe version 1 | < 0.15 | watch |
| Counters | insufficient same-binary points: 2 of 3 (daemon c41a86d23822) | < 0.05 | watch |
| Contended work | not judged: no contended class has 3 ranges of 5+ calls with per-call SQL; SQL per call (sql.call) | < 0.05 (SQL work against tree size) | watch |
| Directory share | 0.564 | < 0.5 | watch |
| Reinstall growth | absolute: 918016 new stored bytes for 140 raw changed bytes of 7 changed packages (6557.257×; raw under 1 MiB) | ≤ 2× changed packages; ≤ 1 MiB with none or under 1 MiB raw | pass |
| Delta at cap | 0.0295 (budget 0.122) | < 0.1 | pass |
| Range growth | 25.5 MiB; median not judged: 1 of 3 earlier ranges | ≤ 3× median, ≤ 2 GiB | watch |
| Snapshot time | 5515 ms for 1466.3 MiB new; size exponent not judged (2 snapshots) | < 0.15 | watch |
| Disk projection | 0.53 | < 0.8 | pass |
| Wall projection | 1 | ≤ 1 (p3 budget) | pass |
| Git | HEAD = checkpoint; 130 commits; clean; 0 read back; 0 guard violations | HEAD = checkpoint, commits = dsh, clean, 0 read back, 0 guard | pass |
| Node proofs | 17 pass · 0 stop · 0 NOT_RUN over 4 points | P1–P6 pass at every point | pass |
| `.git` conflicts | 0 (tracked 0 · install 158 · build 0; tracked judged by Correctness) | 0 | pass |
| Resilience | Busy 0 · EAGAIN 0 · refused unmount 0 | 0 Busy, EAGAIN, refused unmount | pass |
| Content ratio | 0.15× | ≤ 2× (act > 5×) | pass |
| Install inputs (reported, not gated) | not recorded | none until NODE_RULE §3 is decided | pass |

Played vs planned:

| Count | Played | Planned |
| --- | --- | --- |
| Steps (bash calls) | 154 | 154 |
| Lanes / agents | 3 / 8 | 3 / 8 |
| LayerFS Commits | 720 | 609 |
| Workspaces (one-shot share) | 198 (0.99) | 80 (0.975) |
| Reads | 219 | 219 |
| Reconcile writes | 103 | 103 |
| Left out (not played in this phase) | install 1, tests 1 | — |

### B. Latency by method and size class

Binary: daemon `c41a86d23822` (attempt 1). Each call's own input is its size class; ×base compares the same operation and class only.

| Operation | Size class | n | p50 | p95 | p99 | max | ×base p50 | ×base p95 | Depth slope | Tree slope | SQL p50: statements / VM steps / full-scan steps | FUSE opcodes p50 per exec | Per unit (p50) | Slowest phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| branch.diff_branches | >64 entries · contended | 1 | 423.93 | 423.93 | 423.93 | 423.93 | no baseline | no baseline | — | — | 10,838 / 411,102 / 0 | — | 1.7233 ms per entrie | — |
| branch.diff_branches | >64 entries · uncontended | 8 | 23.88 | 415.57 | 415.57 | 676.19 | 0.43× | 0.88× | — | — | 231 / 21,238 / 0 | — | 0.0991 ms per entrie | — |
| branch.diff_commits | 17–64 entries · uncontended | 1 | 15.49 | 15.49 | 15.49 | 15.49 | 0.90× | 0.90× | — | — | 193 / 21,676 / 0 | — | 0.8606 ms per entrie | sdk.compare |
| branch.diff_commits | >64 entries · uncontended | 398 | 20.04 | 50.22 | 95.85 | 404.68 | 0.89× | 0.96× | — | — | 306 / 34,776 / 0 | — | 0.1095 ms per entrie | sdk.compare |
| branch.fork | — · uncontended | 7 | 0.75 | 1.96 | 1.96 | 4.34 | 0.98× | 1.44× | — | — | 16 / 274 / 0 | — | — | — |
| branch.list_commits | 17–64 entries · uncontended | 2 | 1.02 | 1.02 | 1.02 | 1.26 | 0.77× | 0.77× | — | — | 70 / 1,298 / 0 | — | 0.0512 ms per entrie | — |
| branch.merge | 17–64 entries · Merged · uncontended | 1 | 1.14 | 1.14 | 1.14 | 1.14 | 0.71× | 0.71× | — | — | 35 / 517 / 0 | — | 0.0223 ms per entrie | — |
| branch.merge | >64 entries · Merged (new Commit) · uncontended | 2 | 432.16 | 432.16 | 432.16 | 456.07 | 0.95× | 0.95× | — | — | 9,110 / 391,525 / 0 | — | 4.036 ms per entrie | branch.merge |
| branch.publish | — · uncontended | 2 | 7.08 | 7.08 | 7.08 | 30.95 | 0.74× | 0.74× | — | — | 50 / 1,042 / 0 | — | — | — |
| fs.apply | >512 KiB · uncontended | 1 | 32.47 | 32.47 | 32.47 | 32.47 | 0.97× | 0.97× | — | — | 181 / 12,211 / 0 | — | 0 ms per byte | commit |
| fs.apply | ≤1 KiB · contended | 1 | 103.49 | 103.49 | 103.49 | 103.49 | 6.23× | 5.20× | — | — | 2,481 / 204,038 / 8,191 | — | 0.2078 ms per byte | commit |
| fs.apply | ≤8 KiB · contended | 1 | 21.89 | 21.89 | 21.89 | 21.89 | 1.26× | 0.77× | — | — | 287 / 73,815 / 8,191 | — | 0.0082 ms per byte | commit |
| fs.diff_files | ≤1 KiB · contended | 2 | 8.97 | 8.97 | 8.97 | 16.73 | 1.26× | 1.05× | — | — | 174 / 9,877 / 0 | — | — | sdk.read |
| fs.diff_files | ≤1 KiB · uncontended | 11 | 8.95 | 11.70 | 11.70 | 12.93 | 1.08× | 0.96× | — | — | 185 / 10,160 / 0 | — | 0.0087 ms per byte | sdk.read |
| fs.diff_files | ≤64 KiB · contended | 3 | 13.84 | 13.84 | 13.84 | 15.49 | 1.02× | 0.80× | — | — | 298 / 18,867 / 0 | — | 0.0004 ms per byte | sdk.read |
| fs.diff_files | ≤64 KiB · uncontended | 9 | 10.78 | 11.66 | 11.66 | 18.98 | 1.11× | 0.79× | — | — | 246 / 13,033 / 0 | — | 0.0008 ms per byte | sdk.read |
| fs.diff_files | ≤8 KiB · contended | 5 | 8.91 | 9.41 | 9.41 | 14.60 | 0.91× | 0.96× | — | — | 187 / 9,753 / 0 | — | 0.0011 ms per byte | sdk.read |
| fs.diff_files | ≤8 KiB · uncontended | 4 | 8.90 | 12.10 | 12.10 | 16.05 | 1.03× | 0.99× | — | — | 185 / 12,165 / 0 | — | 0.0019 ms per byte | sdk.read |
| fs.glob | 17–64 files · contended | 1 | 18.97 | 18.97 | 18.97 | 18.97 | 2.36× | 2.28× | — | — | 409 / 30,104 / 0 | — | 0.3647 ms per file | — |
| fs.glob | 17–64 files · uncontended | 7 | 7.24 | 9.89 | 9.89 | 10.32 | 1.22× | 1.66× | — | — | 96 / 9,913 / 0 | — | 0.175 ms per file | — |
| fs.glob | 2–4 files · contended | 1 | 3.38 | 3.38 | 3.38 | 3.38 | 0.81× | 0.81× | — | — | 53 / 4,331 / 0 | — | 1.1277 ms per file | — |
| fs.glob | 2–4 files · uncontended | 5 | 3.41 | 5.57 | 5.57 | 7.09 | 1.15× | 1.36× | — | — | 57 / 4,506 / 0 | — | 1.6485 ms per file | — |
| fs.glob | 5–16 files · contended | 5 | 4.75 | 6.73 | 6.73 | 7.41 | 1.51× | 2.14× | — | — | 101 / 8,927 / 0 | — | 0.4204 ms per file | — |
| fs.glob | 5–16 files · uncontended | 8 | 4.03 | 4.61 | 4.61 | 4.65 | 0.98× | 0.80× | — | — | 55 / 5,021 / 0 | — | 0.4507 ms per file | — |
| fs.glob | >64 files · contended | 3 | 10.09 | 10.09 | 10.09 | 12.29 | 1.38× | 1.38× | — | — | 216 / 16,147 / 0 | — | 0.0223 ms per file | — |
| fs.glob | >64 files · uncontended | 11 | 4.82 | 8.16 | 8.16 | 13.31 | 0.62× | 0.35× | — | — | 71 / 5,408 / 0 | — | 0.015 ms per file | — |
| fs.grep | 1 files · contended | 1 | 5.42 | 5.42 | 5.42 | 5.42 | no baseline | no baseline | — | — | 66 / 7,438 / 0 | — | 5.415 ms per file | sdk.lines |
| fs.grep | 17–64 files · contended | 3 | 17.41 | 17.41 | 17.41 | 21.09 | 1.71× | 1.71× | — | — | 245 / 15,211 / 0 | — | 0.3402 ms per file | sdk.lines |
| fs.grep | 17–64 files · uncontended | 6 | 9.81 | 14.49 | 14.49 | 20.50 | 1.04× | 0.85× | — | — | 199 / 12,281 / 0 | — | 0.2356 ms per file | sdk.lines |
| fs.grep | 2–4 files · contended | 1 | 7.37 | 7.37 | 7.37 | 7.37 | 1.67× | 1.67× | — | — | 115 / 7,216 / 0 | — | 1.8417 ms per file | sdk.lines |
| fs.grep | 2–4 files · uncontended | 3 | 4.45 | 4.45 | 4.45 | 4.94 | 1.03× | 0.99× | — | — | 98 / 5,050 / 0 | — | 1.1135 ms per file | sdk.lines |
| fs.grep | 5–16 files · contended | 2 | 6.26 | 6.26 | 6.26 | 7.57 | 1.22× | 1.22× | — | — | 184 / 8,910 / 0 | — | 0.5047 ms per file | sdk.lines |
| fs.grep | 5–16 files · uncontended | 12 | 4.36 | 6.82 | 6.82 | 7.51 | 0.81× | 0.64× | — | — | 85 / 5,757 / 0 | — | 0.6227 ms per file | sdk.lines |
| fs.grep | >64 files · contended | 5 | 34.77 | 49.22 | 49.22 | 73.15 | 1.34× | 1.31× | — | — | 968 / 49,182 / 0 | — | 0.1184 ms per file | sdk.lines |
| fs.grep | >64 files · uncontended | 4 | 17.16 | 38.58 | 38.58 | 44.87 | 0.77× | 0.83× | — | — | 527 / 18,347 / 0 | — | 0.1191 ms per file | sdk.lines |
| fs.list | 1 entries · uncontended | 1 | 3.84 | 3.84 | 3.84 | 3.84 | 1.05× | 1.05× | — | — | 61 / 5,019 / 0 | — | 3.842 ms per entrie | — |
| fs.list | 17–64 entries · contended | 6 | 5.16 | 8.36 | 8.36 | 16.69 | 0.98× | 1.17× | — | — | 108 / 7,784 / 0 | — | 0.1481 ms per entrie | — |
| fs.list | 17–64 entries · uncontended | 9 | 4.30 | 6.45 | 6.45 | 7.34 | 1.03× | 0.70× | — | — | 62 / 5,222 / 0 | — | 0.0861 ms per entrie | — |
| fs.list | 2–4 entries · uncontended | 4 | 3.13 | 3.23 | 3.23 | 4.96 | 1.05× | 1.06× | — | — | 50 / 3,822 / 0 | — | 1.045 ms per entrie | — |
| fs.list | 5–16 entries · contended | 7 | 5.54 | 7.72 | 7.72 | 14.52 | 1.09× | 0.69× | — | — | 93 / 7,179 / 0 | — | 0.5538 ms per entrie | — |
| fs.list | 5–16 entries · uncontended | 14 | 3.56 | 5.56 | 5.56 | 5.63 | 0.96× | 0.81× | — | — | 61 / 6,219 / 0 | — | 0.4012 ms per entrie | — |
| fs.read | ≤1 KiB · contended | 3 | 2.33 | 2.33 | 2.33 | 3.80 | 0.59× | 0.59× | — | — | 57 / 4,175 / 0 | — | 0.0032 ms per byte | sdk.lines |
| fs.read | ≤1 KiB · uncontended | 5 | 3.63 | 4.04 | 4.04 | 4.05 | 1.12× | 0.97× | — | — | 64 / 3,989 / 0 | — | 0.0042 ms per byte | sdk.lines |
| fs.read | ≤64 KiB · contended | 1 | 3.52 | 3.52 | 3.52 | 3.52 | 1.22× | 1.22× | — | — | 67 / 4,398 / 0 | — | 0.0002 ms per byte | sdk.lines |
| fs.read | ≤64 KiB · uncontended | 7 | 2.96 | 3.42 | 3.42 | 3.45 | 1.11× | 1.28× | — | — | 54 / 3,854 / 0 | — | 0.0002 ms per byte | sdk.lines |
| fs.read | ≤8 KiB · contended | 5 | 4.57 | 5.35 | 5.35 | 6.77 | 1.27× | 0.67× | — | — | 83 / 5,613 / 0 | — | 0.0021 ms per byte | sdk.lines |
| fs.read | ≤8 KiB · uncontended | 12 | 3.29 | 5.28 | 5.28 | 6.51 | 1.06× | 0.60× | — | — | 57 / 4,034 / 0 | — | 0.0012 ms per byte | sdk.lines |
| fs.rm | 1 files · contended | 3 | 23.70 | 23.70 | 23.70 | 49.00 | 1.49× | 0.94× | — | — | 520 / 33,275 / 0 | — | 23.705 ms per file | commit |
| fs.rm | 1 files · uncontended | 5 | 12.18 | 13.96 | 13.96 | 23.38 | 1.33× | 0.78× | — | — | 166 / 8,932 / 0 | — | 12.18 ms per file | files.change |
| fs.stat | ≤1 KiB · contended | 2 | 4.55 | 4.55 | 4.55 | 10.79 | 1.42× | 1.42× | — | — | 143 / 6,279 / 0 | — | 0.0089 ms per byte | — |
| fs.stat | ≤1 KiB · uncontended | 7 | 3.51 | 3.66 | 3.66 | 4.14 | 1.15× | 0.78× | — | — | 62 / 4,216 / 0 | — | 0.007 ms per byte | — |
| fs.stat | ≤512 KiB · contended | 1 | 2.53 | 2.53 | 2.53 | 2.53 | 0.63× | 0.63× | — | — | 51 / 3,196 / 0 | — | 0 ms per byte | — |
| fs.stat | ≤64 KiB · contended | 3 | 2.90 | 2.90 | 2.90 | 8.09 | 1.16× | 1.16× | — | — | 44 / 3,862 / 0 | — | 0.0003 ms per byte | — |
| fs.stat | ≤64 KiB · uncontended | 7 | 2.44 | 2.77 | 2.77 | 3.33 | 0.90× | 0.62× | — | — | 46 / 3,698 / 0 | — | 0.0002 ms per byte | — |
| fs.stat | ≤8 KiB · contended | 5 | 4.98 | 10.96 | 10.96 | 15.43 | 1.94× | 3.73× | — | — | 82 / 5,436 / 0 | — | 0.0029 ms per byte | — |
| fs.stat | ≤8 KiB · uncontended | 7 | 2.90 | 3.03 | 3.03 | 3.56 | 1.13× | 0.84× | — | — | 48 / 3,762 / 0 | — | 0.0007 ms per byte | — |
| fs.write | >512 KiB · uncontended | 2 | 12.18 | 12.18 | 12.18 | 21.71 | 0.97× | 0.91× | — | — | 146 / 6,089 / 0 | — | 0 ms per byte | commit |
| fs.write | ≤1 KiB · contended | 36 | 25.43 | 178.25 | 178.78 | 187.64 | 1.43× | 1.52× | — | — | 552 / 39,006 / 0 | — | 0.0475 ms per byte | commit |
| fs.write | ≤1 KiB · uncontended | 62 | 9.33 | 13.90 | 16.01 | 17.59 | 1.04× | 0.64× | — | — | 159 / 7,428 / 0 | — | 0.0183 ms per byte | commit |
| fs.write | ≤512 KiB · contended | 12 | 20.50 | 71.10 | 71.10 | 127.84 | 1.05× | 0.80× | — | — | 485 / 31,539 / 0 | — | 0.0002 ms per byte | commit |
| fs.write | ≤512 KiB · uncontended | 20 | 14.21 | 20.24 | 20.24 | 21.18 | 1.25× | 0.81× | — | — | 177 / 9,968 / 0 | — | 0.0001 ms per byte | commit |
| fs.write | ≤64 KiB · contended | 83 | 20.51 | 74.94 | 133.86 | 206.06 | 1.37× | 1.56× | — | — | 440 / 25,740 / 0 | — | 0.0015 ms per byte | commit |
| fs.write | ≤64 KiB · uncontended | 118 | 9.63 | 16.86 | 22.46 | 28.04 | 1.10× | 0.90× | — | — | 166 / 7,267 / 0 | — | 0.0006 ms per byte | files.change |
| fs.write | ≤8 KiB · contended | 99 | 19.61 | 77.94 | 167.21 | 213.86 | 1.43× | 2.05× | — | — | 436 / 28,952 / 0 | — | 0.006 ms per byte | commit |
| fs.write | ≤8 KiB · uncontended | 130 | 9.30 | 16.52 | 20.54 | 27.30 | 1.10× | 0.94× | — | — | 157 / 7,507 / 0 | — | 0.0029 ms per byte | commit |
| operator.store.stats | — · uncontended | 1 | 0.78 | 0.78 | 0.78 | 0.78 | 1.07× | 1.07× | — | — | 3 / 61 / 0 | — | — | — |
| sandbox.commit | 0 files · Committed · contended | 25 | 33.87 | 57.27 | 62.31 | 62.97 | 1.07× | 1.15× | — | — | 499 / 43,823 / 82 | — | — | commit |
| sandbox.commit | 0 files · Committed · uncontended | 75 | 27.42 | 47.45 | 75.98 | 196.53 | 1.00× | 1.21× | — | — | 326 / 22,999 / 0 | — | — | commit |
| sandbox.commit | 0 files · UpToDate · contended | 9 | 3.41 | 4.43 | 4.43 | 4.69 | 0.90× | 0.79× | — | — | 6 / 71 / 0 | — | — | observe.after |
| sandbox.commit | 0 files · UpToDate · uncontended | 35 | 3.66 | 6.46 | 7.07 | 8.53 | 0.97× | 1.10× | — | — | 6 / 71 / 0 | — | — | observe.after |
| sandbox.commit | 1 files · Committed · contended | 5 | 15.79 | 21.08 | 21.08 | 31.02 | 1.54× | 1.16× | — | — | 175 / 6,633 / 0 | — | 15.788 ms per file | commit |
| sandbox.commit | 1 files · Committed · uncontended | 16 | 9.08 | 11.23 | 11.23 | 11.79 | 0.89× | 0.86× | — | — | 125 / 4,557 / 0 | — | 9.083 ms per file | commit |
| sandbox.commit | 1 files · Conflict · contended | 1 | 433.51 | 433.51 | 433.51 | 433.51 | 1.57× | 1.57× | — | — | 17,183 / 665,662 / 0 | — | 433.507 ms per file | commit |
| sandbox.commit | 2–4 files · Committed · contended | 4 | 15.80 | 16.15 | 16.15 | 16.54 | 1.02× | 0.55× | — | — | 165 / 6,575 / 0 | — | 5.383 ms per file | commit |
| sandbox.commit | 2–4 files · Committed · uncontended | 7 | 10.90 | 13.73 | 13.73 | 16.34 | 1.09× | 1.12× | — | — | 199 / 7,252 / 0 | — | 5.4495 ms per file | commit |
| sandbox.commit | 5–16 files · Committed · contended | 1 | 14.20 | 14.20 | 14.20 | 14.20 | 0.35× | 0.35× | — | — | 212 / 8,326 / 0 | — | 2.84 ms per file | commit |
| sandbox.commit | — · Committed · uncontended | 12 | 116.55 | 1295.25 | 1295.25 | 16320.06 | 1.09× | 0.91× | — | — | 1,275 / 70,557 / 0 | — | — | commit |
| sandbox.exec | 0 files · contended | 173 | 716.02 | 1224.60 | 5184.25 | 5326.01 | 0.96× | 1.17× | — | — | — | 4,703 | — | — |
| sandbox.exec | 0 files · uncontended | 141 | 36.24 | 924.84 | 1357.95 | 7572.09 | 0.97× | 1.20× | — | — | — | 4838.30 | — | — |
| sandbox.exec | 1 files · contended | 28 | 36.59 | 63.74 | 65.66 | 66.83 | 1.01× | 1.11× | — | — | — | 5.70 | 36.588 ms per file | — |
| sandbox.exec | 1 files · uncontended | 51 | 37.87 | 57.28 | 65.09 | 72.07 | 1.04× | 0.91× | — | — | — | 5 | 37.869 ms per file | — |
| sandbox.exec | 17–64 files · uncontended | 3 | 64.06 | 64.06 | 64.06 | 68.56 | 0.81× | 0.81× | — | — | — | 95 | 3.2031 ms per file | — |
| sandbox.exec | 2–4 files · contended | 16 | 49.86 | 64.31 | 64.31 | 67.46 | 1.17× | 0.96× | — | — | — | 12.30 | 16.743 ms per file | — |
| sandbox.exec | 2–4 files · uncontended | 35 | 36.37 | 55.98 | 56.22 | 66.64 | 0.79× | 0.84× | — | — | — | 9.30 | 14.0548 ms per file | — |
| sandbox.exec | 5–16 files · contended | 7 | 56.81 | 83.85 | 83.85 | 85.47 | 1.13× | 1.19× | — | — | — | 40 | 8.5472 ms per file | — |
| sandbox.exec | 5–16 files · uncontended | 14 | 52.90 | 70.39 | 70.39 | 78.81 | 0.83× | 0.83× | — | — | — | 33 | 6.833 ms per file | — |
| sandbox.exec | — · contended | 7 | 5893.65 | 8054.73 | 8054.73 | 31261.48 | 0.59× | 0.26× | — | — | — | 50963.90 | — | — |
| sandbox.exec | — · uncontended | 34 | 548.41 | 29935.34 | 32583.80 | 41191.09 | 1.57× | 1.63× | — | — | — | 44069.20 | — | — |
| sandbox.mount | — · contended | 54 | 12.60 | 19.08 | 20.44 | 84.56 | 1.05× | 0.87× | — | — | 62 / 1,701 / 82 | — | — | sandbox.mount.bind |
| sandbox.mount | — · uncontended | 134 | 10.20 | 15.19 | 19.60 | 23.67 | 0.93× | 0.88× | — | — | 45 / 1,362 / 82 | — | — | observe.after |
| sandbox.status | — · uncontended | 4 | 3.54 | 4.13 | 4.13 | 42.29 | 0.77× | 0.64× | — | — | 0 / 0 / 0 | — | — | observe.after |
| sandbox.unmount | — · contended | 38 | 13.46 | 18.82 | 19.15 | 19.87 | 0.98× | 0.81× | — | — | 0 / 0 / 0 | — | — | observe.after |
| sandbox.unmount | — · uncontended | 150 | 13.46 | 26.71 | 189.98 | 230.55 | 0.89× | 0.94× | — | — | 0 / 0 / 0 | — | — | observe.after |

| Method | Category | Calls | Bytes in | Bytes out | Files / entries | Outcomes |
| --- | --- | --- | --- | --- | --- | --- |
| branch.diff_branches | branch | 9 | 0.0 KiB | 481.5 KiB | 2,151 | ok 9 |
| branch.diff_commits | branch | 404 | 0.0 KiB | 22.3 MiB | 75,176 | ok 404 |
| branch.fork | branch | 23 | 0.0 KiB | 0.0 KiB | 0 | Forked 23 |
| branch.list_commits | project | 9 | 0.0 KiB | 84.4 KiB | 143 | ok 9 |
| branch.merge | branch | 8 | 0.0 KiB | 0.0 KiB | 0 | Merged 8 |
| branch.publish | branch | 2 | 0.0 KiB | 0.0 KiB | 0 | Added 2 |
| fs.apply | fs | 15 | 1.1 MiB | 0.0 KiB | 26 | Committed 15 |
| fs.diff_files | fs | 39 | 0.0 KiB | 352.6 KiB | 30 | NoSuchPath 9, Text 30 |
| fs.glob | fs | 51 | 0.0 KiB | 53.6 KiB | 653 | ok 51 |
| fs.grep | fs | 47 | 0.0 KiB | 194.5 KiB | 775 | ok 47 |
| fs.list | fs | 53 | 0.0 KiB | 295.7 KiB | 1,964 | ok 53 |
| fs.read | fs | 38 | 0.0 KiB | 175.0 KiB | 38 | ok 38 |
| fs.rm | fs | 8 | 0.0 KiB | 0.0 KiB | 8 | Committed 8 |
| fs.stat | fs | 40 | 0.0 KiB | 8.9 KiB | 40 | ok 40 |
| fs.write | fs | 562 | 9.5 MiB | 0.0 KiB | 562 | Committed 562 |
| operator.store.stats | operator | 1 | 0.0 KiB | 0.0 KiB | 0 | ok 1 |
| sandbox.commit | sandbox | 195 | 0.0 KiB | 0.0 KiB | 0 | Committed 150, UpToDate 44, Conflict 1 |
| sandbox.exec | sandbox | 519 | 1.8 MiB | 6.0 MiB | 0 | exit:0 516, exit:2 3 |
| sandbox.mount | sandbox | 198 | 0.0 KiB | 0.0 KiB | 0 | Mounted 198 |
| sandbox.status | sandbox | 4 | 0.0 KiB | 0.0 KiB | 0 | ok 4 |
| sandbox.unmount | sandbox | 198 | 0.0 KiB | 0.0 KiB | 0 | Unmounted 198 |

### C. Scale probes

Binary: daemon `c41a86d23822`.

Load average (1-min, runner (Docker VM kernel)): start 1.64 · end 1.34.

| Probe | ms (median) | Samples | Load 1-min | Counters (first sample) |
| --- | --- | --- | --- | --- |
| stat | 1.146 | 15.682 · 1.614 · 1.122 · 1.146 · 1.012 | 2.02–2.02 | statements 32, vm_steps 1069, fullscan_steps 0, sorts 0, returned_rows 89 |
| read | 1.288 | 1.444 · 1.288 · 1.134 · 1.438 · 1.188 | 2.02–2.02 | statements 18, vm_steps 766, fullscan_steps 0, sorts 0, returned_rows 75 |
| list_small | 1.061 | 1.244 · 1.061 · 1.042 · 1.021 · 1.623 | 2.02–2.02 | statements 18, vm_steps 775, fullscan_steps 0, sorts 0, returned_rows 75 |
| list_largest | 14.091 | 16.635 · 13.553 · 14.091 · 14.816 · 13.469 | 2.02–2.02 | statements 201, vm_steps 28826, fullscan_steps 0, sorts 0, returned_rows 2673 |
| grep_scoped | 1.847 | 1.96 · 1.48 · 1.847 · 1.894 · 1.766 | 2.02–2.02 | statements 23, vm_steps 921, fullscan_steps 0, sorts 0, returned_rows 84 |
| glob_scoped | 1.442 | 2.222 · 1.384 · 1.225 · 1.693 · 1.442 | 2.02–2.02 | statements 17, vm_steps 754, fullscan_steps 0, sorts 0, returned_rows 74 |
| grep_tree | 5803.958 | 6745.464 · 6247.975 · 5803.958 · 5523.803 · 5712.176 | 1.62–1.94 | statements 66751, vm_steps 4866683, fullscan_steps 0, sorts 0, returned_rows 480013 |
| glob_tree | 12.721 | 14.32 · 11.798 · 12.793 · 12.721 · 11.631 | 1.62–1.62 | statements 166, vm_steps 23746, fullscan_steps 0, sorts 0, returned_rows 2320 |
| diff_files | 4.93 | 5.065 · 5.288 · 4.916 · 4.648 · 4.93 | 1.62–1.62 | statements 90, vm_steps 4480, fullscan_steps 0, sorts 0, returned_rows 450 |
| list_commits | 0.682 | 1.663 · 0.72 · 0.682 · 0.665 · 0.595 | 1.62–1.62 | statements 70, vm_steps 1298, fullscan_steps 0, sorts 0, returned_rows 52 |
| diff_commits | 2.243 | 3.072 · 2.228 · 2.167 · 2.243 · 2.29 | 1.62–1.62 | statements 68, vm_steps 2258, fullscan_steps 0, sorts 0, returned_rows 245 |
| fork | 0.697 | 1.05 · 0.697 · 0.473 · 0.659 · 0.77 | 1.62–1.62 | statements 16, vm_steps 274, fullscan_steps 0, sorts 0, returned_rows 7 |
| merge | 27.782 | 30.325 · 27.782 · 29.359 · 27.041 · 25.669 | 1.62–1.62 | statements 523, vm_steps 23239, fullscan_steps 0, sorts 0, returned_rows 1719 |
| oneshot_mount_unmount | 17.026 | 20.317 · 15.224 · 19.17 · 16.548 · 17.026 | 1.62–1.62 | statements 66, vm_steps 2289, fullscan_steps 82, sorts 2, returned_rows 225 |
| oneshot_commit | 74.445 | 81.785 · 73.67 · 68.769 · 74.445 · 76.62 | 1.62–1.62 | statements 191, vm_steps 12484, fullscan_steps 82, sorts 2, returned_rows 931 |
| oneshot_exec | — |  ·  ·  ·  ·  | 1.62–1.62 | statements 0, vm_steps 0, fullscan_steps 0, sorts 0, returned_rows 0 |

### D. Storage internals

From the sealed file at snapshot r059: 439,127 pages of 4,096 B, 0 free · Commits 71,250 · Branches 1,530 · Layers 72 · compression 3.80× (canonical ÷ stored).

| Role | Objects | Canonical bytes |
| --- | --- | --- |
| 1 | 227,524 | 1.42 GiB |
| 2 | 78,581 | 1.20 GiB |
| 3 | 18,584 | 8.0 MiB |
| 4 | 52 | 10.3 KiB |
| 5 | 18,465 | 1.9 MiB |
| 6 | 200,266 | 962.0 MiB |
| 7 | 570,509 | 139.3 MiB |
| 8 | 1,757 | 515.3 KiB |
| 9 | 154,031 | 345.5 MiB |
| 10 | 76,529 | 9.4 MiB |
| 11 | 12,822 | 1.7 MiB |
| 13 | 2,537 | 208.4 KiB |

| Pack domain | Packs | Bytes |
| --- | --- | --- |
| 0 | 73,417 | 157.9 MiB |
| 1 | 76,989 | 935.1 MiB |

| Table or index | Pages | Bytes | Unused |
| --- | --- | --- | --- |
| pack | 292,621 | 1.12 GiB | 41.1 MiB |
| inode_value | 88,271 | 344.8 MiB | 6.6 MiB |
| binding_hint | 27,056 | 105.7 MiB | 9.9 MiB |
| object_location | 18,509 | 72.3 MiB | 7.7 MiB |
| commit | 5,962 | 23.3 MiB | 3.7 MiB |
| file_digest | 1,719 | 6.7 MiB | 772.2 KiB |
| commit_lineage | 1,534 | 6.0 MiB | 705.8 KiB |
| commit_runs | 1,492 | 5.8 MiB | 757.7 KiB |
| commit_identity | 1,096 | 4.3 MiB | 474.7 KiB |
| content_signature | 157 | 628.0 KiB | 9.7 KiB |
| branch | 67 | 268.0 KiB | 44.2 KiB |
| branch_names | 25 | 100.0 KiB | 18.3 KiB |
| branch_identity | 17 | 68.0 KiB | 8.0 KiB |
| run_merges | 9 | 36.0 KiB | 9.6 KiB |
| history_meta | 8 | 32.0 KiB | 2.1 KiB |
| sqlite_schema | 6 | 24.0 KiB | 7.7 KiB |
| layer | 5 | 20.0 KiB | 7.2 KiB |
| absorbed_heights | 4 | 16.0 KiB | 7.7 KiB |
| absorbed | 4 | 16.0 KiB | 7.7 KiB |
| layers_source | 3 | 12.0 KiB | 5.7 KiB |

### E. Stage times

**Time 387.9 s** (tooling): play 163.1 · consolidate 133.5 · verify 30.0 · probes 31.2 · tests 0.0 · seal + snapshot 13.2 · report 16.9

387.88 s tooling: prepare 1.62 · play 161.48 · consolidate 133.56 · verify 17.36 (diff_commits + full compareTree) · version walk 12.65 · probes 31.16 · metrics 0.78 · seal 1.38 · sealed figures 6.20 · snapshot copy 5.59 · report 0.56

### F. Attempts

| # | Binary | Started | Result | Reason |
| --- | --- | --- | --- | --- |
| 1 | c41a86d23822da1da70e03eb843938d51ddba522de5a8aa598911d3d3b24f851 | 2026-10-20T13:08:52.653Z | watch | Speed: sandbox.exec — · uncontended: 1.63× baseline (no phase); Scaling: insufficient same-binary points: 2 of 3 (daemon c41a86d23822); also not judged: oneshot_exec: 2 of 3 points of probe version 1; Counters: insufficient same-binary points: 2 of 3 (daemon c41a86d23822); Contended work: not judged: no contended class has 3 ranges of 5+ calls with per-call SQL; SQL per call (sql.call); Directory share: 0.564; Range growth: 25.5 MiB; median not judged: 1 of 3 earlier ranges; Snapshot time: 5515 ms for 1466.3 MiB new; size exponent not judged (2 snapshots) |

### G. Evidence

- `~/lfs-history/metrics/range-059.a1.json`
- trace `~/lfs-history/runs/p3-main-x-c/trace/range-059.a1.jsonl` · runner log `~/lfs-history/runs/p3-main-x-c/play.log` · snapshot manifest `/Users/yifanxu/lfs-history/snapshots/range-059.json`

### H. Git internals

Seed pack: — objects, — (counted apart from lane objects).

| Lane | Objects | Index bytes |
| --- | --- | --- |
| r059-2-root | 256 | 652.6 KiB |
| r059-3-agents-notes | 526 | 655.7 KiB |
| r059-1-packages-client | 497 | 654.9 KiB |

| git command | ms | lstat |
| --- | --- | --- |
| `git status --porcelain` | 558.0 | 5,268 |
| `git diff --stat` | 45.0 | 5,263 |
| `git add -f` | 42.0 | — |
| `git rm --cached` | 11.0 | — |
| `git commit` | 47.0 | 5,265 |

### I. Proof details

| Lane | Point | Proof | Result | Detail | Native cached |
| --- | --- | --- | --- | --- | --- |
| r059-1-packages-client | end | P1 | pass | — | — |
| r059-1-packages-client | end | P2 | pass | exit 0 | — |
| r059-1-packages-client | end | P3 | pass | 300 bookkeeping path(s) | — |
| r059-1-packages-client | end | P4 | pass | 450 emitted files, exit 2 | — |
| r059-1-packages-client | end | P5 | pass | 98 files | — |
| r059-1-packages-client | end | P6 | n/a | not a repair | — |
| r059-2-root | end | P1 | pass | — | — |
| r059-2-root | end | P2 | pass | exit 0 | — |
| r059-2-root | end | P3 | n/a | an install, not a refresh | — |
| r059-2-root | end | P4 | pass | 140 emitted files, exit 2 | — |
| r059-2-root | end | P5 | pass | 29 files | — |
| r059-2-root | end | P6 | n/a | not a repair | — |
| r059-3-agents-notes | end | P1 | pass | — | — |
| r059-3-agents-notes | end | P2 | pass | exit 0 | — |
| r059-3-agents-notes | end | P3 | pass | 300 bookkeeping path(s) | — |
| r059-3-agents-notes | end | P4 | pass | 153 emitted files, exit 2 | — |
| r059-3-agents-notes | end | P5 | pass | 40 files | — |
| r059-3-agents-notes | end | P6 | n/a | not a repair | — |
| lead | repair | P1 | n/a | folded into P6 | — |
| lead | repair | P2 | pass | exit 0 | — |
| lead | repair | P3 | n/a | a repair, not a no-op | — |
| lead | repair | P4 | n/a | folded into P6 | — |
| lead | repair | P5 | pass | 30 files | — |
| lead | repair | P6 | pass | P1 pass, P4 pass (2397 emitted files, exit 0) | — |

### J. Conflicts by path class

No conflicts by path recorded.
