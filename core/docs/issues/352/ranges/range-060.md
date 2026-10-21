# Range 060 · **optimize** · attempt 1

**Matches git ✓** · daemon `c41a86d23822` · image `d3773b4e` · plan v2 · continued from r059 (live Store)
dsh `b121adcf1`..`c263dcdd4` · **79 commits** (13 mainline, 66 side) · 2026-07-30 → 2026-07-31
Areas changed: `docs` 24% · `examples/acp-agent` 11% · `/` 10% · other 56%
**Phase P3** · **Git ✓** · **Node ✓** (P1–P6: 22 pass, 0 stop, 0 NOT_RUN over 5 points) · **Content 0.17×** · **Churn 0.00**
**Time split:** play 133.0 s · git 179.7 s · Node 323.2 s · verify 18.9 s

| Latest version | Store on disk | Space amplification | Added this range | Commits | Time |
| --- | --- | --- | --- | --- | --- |
| **877.6 MiB** (+4.5 MiB) | **1.71 GiB** (+30.6 MiB) | **1.99×** (prev 1.96×) | **33.9 MiB** | **1,153** (total 71,393) | **374.8 s** tooling (total 236.1 min) |

**Checks:** 12 pass · 6 watch: Speed fs.grep 5–16 files · uncontended: 2.16× baseline (sdk.lines); Scaling not judged: stat (chain-bounded): 3 of 9 points: a bound needs a full metadata delta-cap period (8) plus one; Counters oneshot_mount_unmount.vm_steps: depth exponent 0.49; Contended work not judged: no contended class has 3 ranges of 5+ calls with per-call SQL over a tree that grew 1.5× (10 classes too narrow); SQL per call (sql.call); Range growth 33.9 MiB; median not judged: 2 of 3 earlier ranges; Wall projection 1 · 1 optimize/stop: Snapshot time
**D-6 triggers** (none): max candidate paths in a merge not traced (needs a candidate-path count on branch.merge (e.g. daemon timing `merge.paths` carrying `candidates`)) (trips > 50,000) · max lane hold of the merge at publish not traced (needs a span for the publication-lane hold inside branch.publish (e.g. daemon timing `publish.lane`, ms)) (trips > 500 ms) · Capacity/ObjectLimitExceeded/Busy from 9 merges: 0 (trips at 1)
**Moved most:** ▲ stored added +33% · ▲ probe fork +30% · ▲ probe glob_scoped +29%
**Budget:** 61 of 202 ranges · projected total 16.9 h (budget 16.8 h) · disk 53% of budget at range 202

## 1. Correctness

| Check | Result |
| --- | --- |
| Tree vs git | **5,352 tracked files match** (blob id and mode) |
| History | 4 lanes merged, 1 publish |
| Steps | 2,515 / 2,515 outcomes as planned |
| Conflicts | **3 / 3 planned hit · 0 unplanned** |
| Unit tests | **30 / 30 equal to native** |
| Installed tree | against the native replay of the on-top chain (lead, lane points, repair): **equal to native** (the repair's P1) · the lead's chain alone (context; without the lane points' installs and builds): 3334 package groups equal · not byte-compared: 3 pnpm state file(s) · by target: 433 bin shims, 4806 links · output root ×0, verification age ×1 |
| Last-writer-wins (`/.lww`) | unchanged (61 lines from 4 .gitignore files) · **238 picks** in 4 merges (238 under node_modules) · re-installed after the merge |
| Ignored files | — (installs not played in P3) |
| Milestone | — |
| Git | **HEAD = checkpoint `c263dcdd4`** · 159 commits written for 159 dsh commits · status clean · fresh mount read back 0 · lane guard 0 · git clean 88 untracked, unignored (905,628 B) |
| Install inputs (NODE_RULE §3; reported, not gated) | not recorded |
| Conflicts by path class | Tracked 0 · Install outputs 238 · Build outputs 0 · `.git` 0 |

### Node and git proofs

Each proof runs the same command natively on the identical tree id (NODE_RULE §6); a proof not run is `NOT_RUN`, never pass.

| Lane | Point | Tree | Install inputs | P1 | P2 | P3 | P4 | P5 | P6 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r060-1-examples-acp-agent | end | `875d1693a71b` | `2e80bb3c6021` | pass (436 normalized) | pass | pass | pass | pass | n/a |
| r060-3-agents-notes | end | `3918f6cfb1c1` | `2e80bb3c6021` | pass (436 normalized) | pass | pass | pass | pass | n/a |
| r060-2-packages-client | end | `fe30e3c63776` | `2e80bb3c6021` | pass (436 normalized) | pass | pass | pass | pass | n/a |
| r060-4-apps-web | end | `b3dbc53c9508` | `6fa88eb76d34` | pass (438 normalized) | pass | n/a | pass | pass | n/a |
| lead | repair | `5556cc8e1132` | `null` | n/a | pass | n/a | n/a | pass | pass (138,082 rewritten) |

P5 skip list (failing natively, set at calibration): `packages/telemetry/session-telemetry-otel/tests/user-id.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-fork.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-view.spec.ts` (fails natively) · `packages/ui/user-approval/tests/approval.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-search.spec.ts` (fails natively) · `packages/subagent/subagent-inprocess/tests/inheritance.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-workspace.spec.ts` (fails natively) · `packages/bash/bash-sandbox/tests/sandbox.spec.ts` (fails natively) · `packages/ui/tui/tests/tui.spec.ts` (fails natively) · `packages/fs/fs-sandbox/tests/fs-sandbox.spec.ts` (fails natively) · `packages/client/ui-settings/tests/apply.spec.ts` (fails natively) · `packages/client/ui-settings/tests/settings-root.spec.tsx` (fails natively) · `packages/pty/pty-local/tests/index.spec.ts` (fails natively) · `packages/pty/pty-local/tests/local.spec.ts` (fails natively) · `packages/client/ui-primitives/tests/diff-block.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/web-block.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-code-subcalls.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-toolview-slot.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/web-card.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/assembly-surfaces.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-branch-tails.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/diff-card.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-tool-row.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-view.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-bar.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/apply-inject.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/terminal-card.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/read-card.spec.tsx` (fails natively) · `packages/client/connection/tests/fixture.spec.ts` (fails natively) · `packages/client/ui-models/tests/onboarding-dialog.spec.tsx` (fails natively) · `packages/client/ui-command/tests/popup-view.spec.tsx` (fails natively) · `packages/client/ui-goal/tests/browser-plugin.spec.tsx` (fails natively) · `packages/client/ui-goal/tests/goalbar.spec.tsx` (fails natively) · `packages/client/ui-models/tests/apply.spec.ts` (fails natively) · `packages/client/ui-models/tests/components.spec.tsx` (fails natively) · `packages/client/ui-models/tests/invariant.spec.ts` (fails natively) · `packages/client/ui-models/tests/onboarding-dialog.spec.tsx` (fails natively) · `packages/client/ui-models/tests/readiness.spec.ts` (fails natively) · `packages/client/ui-models/tests/store.spec.ts` (fails natively) · `packages/client/ui-permission/tests/browser-plugin.spec.ts` (fails natively) · `packages/client/ui-permission/tests/permission-row.spec.tsx` (fails natively) · `packages/client/ui-permission/tests/settings-store.spec.ts` (fails natively) · `packages/client/ui-plan/tests/plan-mode-control.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/rows.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/workspace-browser.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/workspace-picker.spec.tsx` (fails natively) · `packages/host/apiproxy/tests/api-proxy-approval.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-blank.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-cold.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-commands.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-config.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-fork.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-models.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-projections.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-rename.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-search.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-view.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-workspace.spec.ts` (fails natively) · `packages/host/apiproxy/tests/client-handler.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/adapter.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/dynamic-config.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/loader-composition.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/adapter.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/dynamic-config.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/loader-composition.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/sdk-options.spec.ts` (fails natively) · `packages/llm/llm-retry/tests/transport-recovery.spec.ts` (fails natively).

## 2. Activity

**3,347 calls** · **216 steps** by **10 agents + lead** on **4 Branches + main** · **276 Workspaces** (99% one-shot, 0 open at end)
**File changes:** +73 added · 938 modified · −15 deleted · 19.2 MiB written · fs 940 : Sandbox 86 (**11 : 1**, reported only in P3)
**Execs:** 734 (JS 78 · shell 656) · 4 non-zero exits · install 0 · test runs 5 · version figures 14 (tooling)

**Calls by category**

| Category | Calls | Writes | Reads | Outcomes |
| --- | --- | --- | --- | --- |
| fs | 1,315 | 953 | 362 | Committed 953 · Text 45 · NoSuchPath 13 |
| sandbox | 1,566 | 1,009 | 5 | commit 275 (Committed 214, UpToDate 60, Conflict 1) · exec 734 (exit:0 730, exit:2 4) · mount 276 (Mounted 276) · status 5 · unmount 276 (Unmounted 276) |
| branch | 455 | 34 | 421 | diff_branches 14 · diff_commits 407 · fork 24 (Forked 24) · merge 9 (Merged 9) · publish 1 (Added 1) |
| project | 10 | 0 | 10 | list_commits 10 |
| operator | 1 | 0 | 1 | store.stats 1 |
| **Total** | **3,347** | **1,996** | **799** |  |

**Branches**

| Branch | Agents | Steps | Commits | Merged into main | Published |
| --- | --- | --- | --- | --- | --- |
| r060-1-examples-acp-agent | a01 a02 | 25 | 232 | ✓ | — |
| r060-2-packages-client | a03 a04 a05 | 67 | 255 | ✓ | — |
| r060-3-agents-notes | a06 a07 | 48 | 242 | ✓ | — |
| r060-4-apps-web | a08 a09 a10 | 69 | 262 | ✓ | — |
| main | lead | 7 | 162 | — | ✓ |

**Conflicts**

| Kind | Hit / planned | Where | Resolved in |
| --- | --- | --- | --- |
| Commit Conflict | 1 / 1 | r060-2, a03 after a04 | 0.1 s |
| Stale clean merge | 1 / 1 | r060-2, a03 a04 | merged cleanly |
| Decoy edit | 1 / 1 | r060-2, a03 a05 | replaced before the checkpoint |
| Merge / publish race | 0 / 0 | — | — |
| **Unplanned** | **0** | — | — |

**Agents**

| Agent | Branch | Steps | fs | sandbox | branch | project | Commits | Conflicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a01 | r060-1 | 10 | 5 | 5 | 0 | 0 | 20 | — |
| a02 | r060-1 | 15 | 8 | 7 | 0 | 0 | 212 | — |
| a03 | r060-2 | 20 | 7 | 13 | 0 | 0 | 118 | commit-conflict, stale-clean-merge, decoy |
| a04 | r060-2 | 27 | 11 | 16 | 0 | 0 | 77 | commit-conflict, stale-clean-merge |
| a05 | r060-2 | 20 | 11 | 9 | 0 | 0 | 60 | decoy |
| a06 | r060-3 | 29 | 16 | 13 | 0 | 0 | 182 | — |
| a07 | r060-3 | 19 | 10 | 9 | 0 | 0 | 60 | — |
| a08 | r060-4 | 17 | 8 | 9 | 0 | 0 | 65 | — |
| a09 | r060-4 | 13 | 6 | 7 | 0 | 0 | 23 | — |
| a10 | r060-4 | 39 | 15 | 24 | 0 | 0 | 174 | — |
| lead | main | 7 | 1 | 0 | 6 | 0 | 162 | — |
| **Total** |  | **216** | **98** | **112** | **6** | **0** | **1,153** | **3** |

Scale-probe Commits (setup and samples): **22**, not range work and not counted above.


**Execs by tool:** git 153 · pnpm 1 · tsc 4 · vitest 5 · other 571

| Lane | git status | git diff | git add | git rm --cached | Lane commits | Loose objects |
| --- | --- | --- | --- | --- | --- | --- |
| r060-2-packages-client | 46 | 46 | 46 | 0 | 46 | 564 |
| r060-3-agents-notes | 34 | 34 | 34 | 0 | 34 | 520 |
| r060-1-examples-acp-agent | 17 | 17 | 17 | 1 | 17 | 475 |
| r060-4-apps-web | 48 | 48 | 48 | 3 | 48 | 474 |
| **lead** | — | — | — | — | 159 commit-tree | index rebuild ✓ · repack ✓ |

| Lane | Installs | Refreshes | tsc -b | vitest points | Test files | Equal to native |
| --- | --- | --- | --- | --- | --- | --- |
| r060-1-examples-acp-agent | 0 | 1 | 1 | 1 | 25 | 25 / 25 |
| r060-3-agents-notes | 0 | 1 | 1 | 1 | 46 | 46 / 46 |
| r060-2-packages-client | 0 | 1 | 1 | 1 | 70 | 70 / 70 |
| r060-4-apps-web | 1 | 0 | 1 | 1 | 75 | 75 / 75 |
| **lead repair** | 1 | — | 1 | — | — | 138,082 files rewritten |

## 3. Storage

**3a. Overview**

|  | Previous (r059) | Now | Change |
| --- | --- | --- | --- |
| Latest version (tracked / `node_modules` / build / `.git`) | 873.1 MiB (30.1 MiB / 692.1 MiB / 28.0 MiB / 123.0 MiB) | 877.6 MiB (31.8 MiB / 692.1 MiB / 28.2 MiB / 125.5 MiB) | +4.5 MiB |
| Version figures from | — | full: snapshot cross-check | — |
| Files / directories / symlinks | 65,110 / 10,099 / 4,797 | 65,202 / 10,102 / 4,814 | +92 / +3 / +17 |
| Largest file / largest directory | 23.5 MiB / 2,252 entries | 23.5 MiB (`node_modules/.pnpm/@rolldown+binding-linux-arm64-gnu@1.1.1/node_modules/@rolldown/binding-linux-arm64-gnu/rolldown-binding.linux-arm64-gnu.node`) / 2,252 entries (`node_modules/.pnpm/@mistralai+mistralai@2.2.6_@opentelemetry+api@1.9.0/node_modules/@mistralai/mistralai/esm/models/components`) | — |
| **Store on disk** (allocated, sealed) | 1.68 GiB | 1.71 GiB | +30.6 MiB |
| **Space amplification** (total · tracked) | 1.96× · tracked 4.92× | 1.99× · tracked 4.73× | 0.02 |
| Head cost / history cost | — | — (needs a reachability walk of the sealed file; not built) / — | — |
| **Stored per byte changed** (content / metadata / shared) | — | **5.64** (0.88 / 0.20 / 0.87) | 0.77× the median range |
| **Stored per Commit** | 32.7 KiB | 27.0 KiB | — |
| Metadata share | 0.45 | 0.46 | this range 0.50 |
| History: Commits / Layers / Branches | 70,240 | 71,393 / 42 / 1,020 | +1,153 |
| Projection at range 202 (estimate: study model, per-Commit cost × planned Commits + install and build forecast) | — | 10.63 GiB (Commits 8.03 GiB · installs 819.2 MiB · build 90.5 MiB) | — |
| Disk guard floor at range 202 (headroom: 256 MiB per range minimum) / disk budget | — | 37.18 GiB / 53% | — |
| Snapshot | — | r060, 1.46 GiB new blocks | — |

**3b. Where the bytes are**

| Part | Bytes | × latest version | Change this range |
| --- | --- | --- | --- |
| Content | 948.8 MiB | 1.08 | +13.7 MiB |
| Metadata | 161.2 MiB | 0.18 | +3.3 MiB |
| Index rows | 551.7 MiB | 0.63 | +12.2 MiB |
| Waste | 82.1 MiB | 0.09 | +1.4 MiB |
| Other | 2.1 MiB | 0.00 | +40.0 KiB |
| **Total = Store on disk** | **1.71 GiB** | **= 1.99** space amplification | +30.6 MiB |

Exact: from the sealed file.

**3c. By source**

| Source | Latest version | Stored (content + metadata) | Amplification | Head cost | Added this range | Changed this range | Stored per byte changed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Tracked | 31.8 MiB | 150.7 MiB (78.0 MiB + 72.8 MiB) | 4.73× | — | 2.5 MiB | 6.0 MiB | 0.42 |
| `node_modules` | 692.1 MiB | 242.9 MiB (201.5 MiB + 41.4 MiB) | 0.35× | — | 1.0 MiB | 0.6 KiB | 1604.20 |
| Build output | 28.2 MiB | 38.1 MiB (35.0 MiB + 3.1 MiB) | 1.35× | — | 1.1 MiB | 9.6 MiB | 0.11 |
| `.git` | 125.5 MiB | 620.6 MiB (590.9 MiB + 29.7 MiB) | 4.95× | — | 12.2 MiB | 0.0 KiB | — |
| Shared (index rows + waste + other) | — | 636.0 MiB | — (not divided) | — | 13.6 MiB | — | — |
| Unattributed (Saves without traced sizes) | — | 57.7 MiB | — | — | — | — | — |
| **Total** | — | **1.71 GiB** | **= 1.99×** space amplification | — | — | — | — |

Sources by the Commit that wrote them (an install Commit is `node_modules`, a build Commit build output). Any comparison with git uses the Tracked row only.

**3d. What's inside**

| Object | Total | Added | Avg size | Reused (dedupe hits) | As delta |
| --- | --- | --- | --- | --- | --- |
| Whole files | 231,223 | +4,172 | 6.6 KiB | 0 (derived) | 51% |
| Chunks (large files) | 79,883 | +1,485 | 16.1 KiB | — | 51% |
| Large-file extents | 18,828 | — | 0.4 KiB | — | — |
| Directories | 585,959 | 4,476 (with inodes, pooled) | 0.3 KiB | — | 54% |
| Inodes and attributes | 470,572 | ↑ pooled | 2.9 KiB | — | — |
| Symlinks | 2,538 | +4,874 | 0.1 KiB | — | — |

Delta: 3.1% at depth cap · 17% of refused bases stopped by budget · `node_modules` reinstall: absolute: 918683 new stored bytes for 389 raw changed bytes of 14 changed packages (2361.653×; raw under 1 MiB)

**3e. Git and Node (P3)**

| Measure | Value |
| --- | --- |
| Tracked only (amplification of the tracked source; comparable with ranges 0–14) | 4.73× (150.7 MiB for 31.8 MiB) |
| Store growth per git commit (index / loose objects / pack) | 2.2 KiB / 4.7 KiB / 8.4 KiB over 304 git commits |
| **Content ratio** (stored content ÷ distinct new content; ≤1.x, watch > 2×, act > 5×) | 0.17× |
| **Churn ratio** (stored ÷ bytes Node churn rewrote) | 0.00 (2.1 MiB stored for 2.76 GiB rewritten) |
| Native-disk equivalence (stored ÷ lanes × one native checkout) | 0.50 (4 lanes × 877.6 MiB) |
| Metadata per file / per Commit (budget from the dev range) | 0.0 KiB / 2.8 KiB (budget not set) |

## 4. Speed

Daemon `c41a86d23822` · p50 / p95 · ratio to baseline (dominant size class) in brackets

| write | read | list | Commit (one-shot) | mount | merge | exec (FUSE ÷ native) |
| --- | --- | --- | --- | --- | --- | --- |
| 10.7 ms / 47.0 ms (1.11×) | 3.4 ms / 5.0 ms (1.06×) | 4.4 ms / 8.9 ms (1.18×) | 23.8 ms / 76.8 ms (1.04×) | 10.9 ms / 21.4 ms (0.94×) | 443 ms / 473 ms (1.04×) | — (native comparison in P3; exec 40.9 ms / 1140 ms) |
| SQL p50: 175 stmts | 65 stmts | 70 stmts | 241 stmts | 54 stmts | 9,786 stmts | — |

**Commit cost:** 13.53 ms per changed file · **One-shot Workspace** (mount + exec + commit + unmount): 860 ms p50 over 276
**Slowest:** sandbox.exec 44345 ms · sandbox.exec 35880 ms · sandbox.exec 33428 ms · checkpoint diff_commits 0.12 ms and 1.72 statements per entry (74,331 entries per page)
**Scaling:** 12 of 15 probes flat · `glob_scoped` 6.26 · `diff_files` 2.48 · `oneshot_commit` 2.35

**Git and Node** (LayerFS ÷ native on the identical tree; ×base compares only with the P3 re-baseline)

| Operation | LayerFS p50 / p95 | Native p50 / p95 | ÷ native (p50) | #362 case ÷ native |
| --- | --- | --- | --- | --- |
| git status (cold) | 515 ms / 515 ms | — / — | — | git / status-cold: — |
| git status (steady) | 537 ms / 735 ms | — / — | — | git / status-steady: — |
| git add | 42.0 ms / 91.0 ms | — / — | — | git / add: — |
| git commit (lane) | 47.0 ms / 76.0 ms | — / — | — | git / commit: — |
| lead writes main | 7803 ms / 7803 ms | — / — | — | — |
| repack | 3467 ms / 3467 ms | — / — | — | — |
| pnpm install (incremental) | 3717 ms / 3717 ms | 2032 ms / 2032 ms | 1.83× | pnpm-reinstall / cold: — |
| pnpm refresh | 3370 ms / 3370 ms | 2221 ms / 2221 ms | 1.52× | pnpm-reinstall / steady: — |
| tsc -b | 8435 ms / 8716 ms | 5821 ms / 6149 ms | 1.45× | tsc-b / cold: — |
| vitest | 9012 ms / 11637 ms | 4164 ms / 6166 ms | 2.16× | vitest / cold: — |

**Health:** 0 Workspaces open · 0 overlay files left · daemons 2 MB (+0 MB) over 5 of 5 Sandboxes · 15 open files · WAL before seal 0.0 KiB
**Resilience:** Busy 0 · EAGAIN 0 · refused unmount 0 · writer wait — · lane hold — per Commit (p50 / p95) · daemon RSS max 2 MB, median 2 MB over 1 daemons · overlay max — · unmount 14.3 ms / 29.4 ms

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
| 060.a1 | 71393 | 1746.0 | 9.64 (1.63×) · 7449 · 286 (28 solo) | 9.38 (1.51×) · 7067 · 358 (94 solo) | 9.01 (1.24×) · 7035 · 464 (49 solo) | 3.31 (1.66×) · 4255 · 197 (3 solo) | 10.31 (1.13×) · 1362 · — (daemon) | 8.86 (1.06×) · 3876 · — (daemon) | 443.19 (—×) · 497051 · 13571 (4 solo) |

**WAL across each class this range:** fs.write ≤1 KiB 4173592 → 4194192 B · fs.write ≤8 KiB 4173592 → 4194192 B · fs.write ≤64 KiB 4120032 → 4194192 B · fs.read ≤8 KiB 4173592 → 4194304 B · sandbox.mount 4173592 → 3028232 B · sandbox.commit 1 file (Committed) 4173592 → 4194304 B · branch.merge 0 → 4194192 B
**Host load (1-min, recorded, not waited on):** macOS 6.23 at the first command → 7.84 after the last (max 10.34 over 9 commands) · Docker VM 1.57 → 1.91

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
| control-060.a1 | 12851 · 207.8 | 71393 · 1746.0 | 5.47 (0.88× first) / 5.06 · 0.93× · 113/144 | 5.37 (0.84× first) / 5.12 · 0.95× · 112/130 | 2.47 (0.89× first) / 2.87 · 1.16× · 76/120 | 9.49 → 9.29 | pass |

**Watch row** (control (b)/(a) p50 over 1.25×, or (b)'s reads per call over 2× (a)'s): pass (sample control-060.a1)

## 5. Findings and action

### Finding 060.a1 · optimize

**1. Trigger** (attempt 1, daemon `c41a86d23822`)

| Check | Value | Threshold |
| --- | --- | --- |
| Snapshot time | 5812 ms for 1499.0 MiB new; size exponent 1.226 | < 0.15 |

Diagnosis pending: `finding-060.a1.json`.

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

- **a1 (`p3-main-x-c`, daemon `c41a86d2`, addon `a1078e69`, main `d06a2b81fa` binaries): OPTIMIZE, terminal under the fast-mode ruling (row recorded). This is the last range of the #352 replay (owner, 2026-10-20: stop at range 60).** Checkpoint ok, git ✓. Node: 4 lane points P1–P5 pass and repair P6 pass. Control `control-060.a1` passes. Native first passed with no fix.
- **Optimize row, Snapshot time: size exponent 1.226 against a threshold below 0.15.** The three same-binary snapshots:

  | Range | New | Copy |
  | --- | --- | --- |
  | r58 | 1,461.3 MiB | 5,339 ms |
  | r59 | 1,466.3 MiB | 5,515 ms |
  | r60 | 1,499.0 MiB | 5,812 ms |

  - That is 3.65, 3.76 and 3.88 ms per new MiB. Size grew 2.6% over the window and time 8.9%.
  - The exponent is fitted over a narrow size spread, so a few hundred ms of copy variance (host load 6.9–10.3) moves it a lot. It is recorded as is. A 5.8 s copy is tooling time, not a product operation.
- **Counters watch:** `oneshot_mount_unmount.vm_steps`, depth exponent 0.49. Statements are 68, 66 and 68 over r58–r60 (cold-mount open item).
- **Speed watch:** `fs.grep` 5–16 files, uncontended, 2.16× baseline (sdk.lines).
- **Timing-sensitive list (SCRIPTS §16):** `skill-local-watcher.spec.ts` is not in any of r60's calibrated run lists, so it was not run.
- **Lane exec on the new binaries (liaison condition):** p3-main-x has no r60 points, so the native same-tree run is the control.

  | Point | vitest ms (files) | tsc ms | vitest / native | tsc / native | host load |
  | --- | --- | --- | --- | --- | --- |
  | `r060-1-examples-acp-agent.end` | 8,391 (25) | 7,483 | 3.59× | 1.68× | 6.9–10.3 |
  | `r060-3-agents-notes.end` | 11,637 (46) | 8,716 | 2.79× | 1.50× | 6.9–10.3 |
  | `r060-2-packages-client.end` | 18,248 (70) | 8,435 | 2.44× | 1.69× | 6.9–10.3 |
  | `r060-4-apps-web.end` | 9,012 (75) | 17,216 | 1.46× | 2.80× | 6.9–10.3 |

  - The old binaries at r55–r57 ran vitest 1.21–3.86× and tsc 1.20–2.57× native, at load 8–12. r60's vitest ratios are inside that range.
  - The tsc ratio at `apps-web` (2.80×) is 9% above the old maximum, at a load that rose to 10.3 during the lanes.
  - Over r59–r60 (seven points), the new binaries are not more than 25% slower at similar load. The new binaries have no same-point old-binary times at r59–r60.
- **F-063 active:** chunk PREFIX 628 against FULL 306, over 145 lane git Commits (140 with a PREFIX chunk). f063.mjs exit 0.
- **Storage watch:**

  | | r60 | r59 |
  | --- | --- | --- |
  | Store | +30.6 MiB | +23.1 MiB |
  | `.git` stored | +12.2 MiB | +7.8 MiB |
  | Index rows | +12.2 MiB (→ 551.7 MiB) | +10.8 MiB |

  Added this range: 33.9 MiB. Space amplification is 1.99×.
- **Clean:** git clean found 88 untracked, unignored files (905,628 B) before the `-d` clean.
- **Steps:**
  - Lead 3 s. Cuts 20, 40, 55 and 68: 23, 16, 14 and 16 s; they avoid the stale-clean-merge at 0–3, the decoy at 29.8–30 and the commit-conflict at 73.6–74.4. Lanes 80 s.
  - Repair 148 s (install 44.4, build 32.0, tests 2.6).
  - Verify 23 s. Finish 65 s of 90 s.
  - Host load 6.2–10.3.
- **Snapshot:** 1,499.0 MiB new, 5.8 s. It is p3-main-x-c's final snapshot, kept.


## Appendix

### A. Checks

| Check | Value | Threshold | Result |
| --- | --- | --- | --- |
| Correctness | tree ok; steps 2515/2515; conflicts 3/3; tests 30/30 equal to native | all | pass |
| Health | 0 open, 0 overlays | 0, 0, flat | pass |
| Speed | fs.grep 5–16 files · uncontended: 2.16× baseline (sdk.lines) | ≤ 1.2× | watch |
| Scaling | not judged: stat (chain-bounded): 3 of 9 points: a bound needs a full metadata delta-cap period (8) plus one | < 0.15 | watch |
| Counters | oneshot_mount_unmount.vm_steps: depth exponent 0.49 | < 0.05 | watch |
| Contended work | not judged: no contended class has 3 ranges of 5+ calls with per-call SQL over a tree that grew 1.5× (10 classes too narrow); SQL per call (sql.call) | < 0.05 (SQL work against tree size) | watch |
| Directory share | 0.499 | < 0.5 | pass |
| Reinstall growth | absolute: 918683 new stored bytes for 389 raw changed bytes of 14 changed packages (2361.653×; raw under 1 MiB) | ≤ 2× changed packages; ≤ 1 MiB with none or under 1 MiB raw | pass |
| Delta at cap | 0.031 (budget 0.1653) | < 0.1 | pass |
| Range growth | 33.9 MiB; median not judged: 2 of 3 earlier ranges | ≤ 3× median, ≤ 2 GiB | watch |
| Snapshot time | 5812 ms for 1499.0 MiB new; size exponent 1.226 | < 0.15 | optimize |
| Disk projection | 0.53 | < 0.8 | pass |
| Wall projection | 1 | ≤ 1 (p3 budget) | watch |
| Git | HEAD = checkpoint; 159 commits; clean; 0 read back; 0 guard violations | HEAD = checkpoint, commits = dsh, clean, 0 read back, 0 guard | pass |
| Node proofs | 22 pass · 0 stop · 0 NOT_RUN over 5 points | P1–P6 pass at every point | pass |
| `.git` conflicts | 0 (tracked 0 · install 238 · build 0; tracked judged by Correctness) | 0 | pass |
| Resilience | Busy 0 · EAGAIN 0 · refused unmount 0 | 0 Busy, EAGAIN, refused unmount | pass |
| Content ratio | 0.17× | ≤ 2× (act > 5×) | pass |
| Install inputs (reported, not gated) | not recorded | none until NODE_RULE §3 is decided | pass |

Played vs planned:

| Count | Played | Planned |
| --- | --- | --- |
| Steps (bash calls) | 216 | 217 |
| Lanes / agents | 4 / 10 | 4 / 10 |
| LayerFS Commits | 1153 | 993 |
| Workspaces (one-shot share) | 276 (0.99) | 111 (0.982) |
| Reads | 313 | 313 |
| Reconcile writes | 154 | 154 |
| Left out (not played in this phase) | install 1, tests 1 | — |

### B. Latency by method and size class

Binary: daemon `c41a86d23822` (attempt 1). Each call's own input is its size class; ×base compares the same operation and class only.

| Operation | Size class | n | p50 | p95 | p99 | max | ×base p50 | ×base p95 | Depth slope | Tree slope | SQL p50: statements / VM steps / full-scan steps | FUSE opcodes p50 per exec | Per unit (p50) | Slowest phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| branch.diff_branches | >64 entries · uncontended | 14 | 31.84 | 529.77 | 529.77 | 665.96 | 0.58× | 1.12× | 19.42 | 28.32 | 443 / 36,558 / 0 | — | 0.1316 ms per entrie | — |
| branch.diff_commits | >64 entries · contended | 2 | 388.45 | 388.45 | 388.45 | 408.82 | 0.78× | 0.78× | — | — | 9,599 / 357,799 / 0 | — | 1.8949 ms per entrie | sdk.compare |
| branch.diff_commits | >64 entries · uncontended | 400 | 23.08 | 57.08 | 95.08 | 570.75 | 1.03× | 1.09× | 2.63 | 3.70 | 308 / 35,502 / 0 | — | 0.1243 ms per entrie | sdk.compare |
| branch.fork | — · uncontended | 8 | 0.93 | 2.53 | 2.53 | 4.55 | 1.22× | 1.85× | 5.78 | 8.26 | 16 / 274 / 0 | — | — | — |
| branch.list_commits | 17–64 entries · uncontended | 3 | 1.06 | 1.06 | 1.06 | 3.70 | 0.80× | 0.80× | 6.40 | 9.41 | 70 / 1,298 / 0 | — | 0.053 ms per entrie | — |
| branch.merge | >64 entries · Merged (new Commit) · uncontended | 3 | 473.45 | 473.45 | 473.45 | 608.33 | 1.04× | 1.04× | 0.76 | 1.00 | 10,637 / 550,905 / 0 | — | 4.7823 ms per entrie | branch.merge |
| branch.merge | >64 entries · Merged · uncontended | 1 | 2.01 | 2.01 | 2.01 | 2.01 | 1.34× | 1.34× | — | — | 35 / 517 / 0 | — | 0.018 ms per entrie | — |
| branch.publish | — · uncontended | 1 | 7.76 | 7.76 | 7.76 | 7.76 | 0.81× | 0.81× | -33.75 | -49.99 | 45 / 1,015 / 0 | — | — | — |
| fs.apply | >512 KiB · uncontended | 1 | 33.85 | 33.85 | 33.85 | 33.85 | 1.01× | 1.01× | -13.16 | -19.51 | 199 / 13,494 / 0 | — | 0 ms per byte | commit |
| fs.apply | ≤1 KiB · uncontended | 1 | 11.62 | 11.62 | 11.62 | 11.62 | 1.14× | 1.14× | — | — | 188 / 12,971 / 0 | — | 0.0517 ms per byte | commit |
| fs.apply | ≤512 KiB · uncontended | 1 | 11.53 | 11.53 | 11.53 | 11.53 | no baseline | no baseline | — | — | 155 / 10,140 / 0 | — | 0.0002 ms per byte | commit |
| fs.apply | ≤8 KiB · contended | 1 | 8.72 | 8.72 | 8.72 | 8.72 | 0.50× | 0.31× | -13.50 | -18.75 | 177 / 8,490 / 0 | — | 0.003 ms per byte | commit |
| fs.apply | ≤8 KiB · uncontended | 2 | 9.42 | 9.42 | 9.42 | 16.60 | 1.04× | 0.86× | — | — | 201 / 10,989 / 0 | — | 0.0081 ms per byte | files.change |
| fs.diff_files | ≤1 KiB · contended | 3 | 10.33 | 10.33 | 10.33 | 11.37 | 1.45× | 1.21× | — | — | 224 / 11,061 / 0 | — | — | sdk.read |
| fs.diff_files | ≤1 KiB · uncontended | 18 | 10.06 | 11.97 | 11.97 | 14.50 | 1.21× | 0.99× | 6.86 | 9.99 | 208 / 10,897 / 0 | — | 0.0252 ms per byte | sdk.read |
| fs.diff_files | ≤64 KiB · contended | 5 | 13.33 | 14.26 | 14.26 | 19.18 | 0.98× | 0.83× | 7.12 | 10.56 | 260 / 13,725 / 0 | — | 0.0003 ms per byte | sdk.read |
| fs.diff_files | ≤64 KiB · uncontended | 12 | 9.76 | 14.25 | 14.25 | 16.44 | 1.01× | 0.97× | 1.07 | 1.71 | 214 / 13,126 / 0 | — | 0.0005 ms per byte | sdk.read |
| fs.diff_files | ≤8 KiB · contended | 4 | 10.38 | 11.45 | 11.45 | 11.64 | 1.06× | 1.17× | — | — | 286 / 13,217 / 0 | — | 0.0024 ms per byte | sdk.read |
| fs.diff_files | ≤8 KiB · uncontended | 11 | 11.57 | 12.95 | 12.95 | 14.10 | 1.34× | 1.06× | 8.27 | 11.88 | 210 / 11,777 / 0 | — | 0.005 ms per byte | sdk.read |
| fs.glob | 1 files · uncontended | 1 | 2.84 | 2.84 | 2.84 | 2.84 | 0.97× | 0.97× | — | — | 47 / 3,128 / 0 | — | 2.837 ms per file | — |
| fs.glob | 17–64 files · contended | 3 | 6.22 | 6.22 | 6.22 | 24.07 | 0.77× | 0.75× | -15.01 | -20.73 | 121 / 9,588 / 0 | — | 0.3453 ms per file | — |
| fs.glob | 17–64 files · uncontended | 8 | 6.29 | 9.27 | 9.27 | 9.39 | 1.06× | 1.56× | -11.50 | -16.81 | 112 / 10,410 / 0 | — | 0.1806 ms per file | — |
| fs.glob | 2–4 files · contended | 2 | 3.64 | 3.64 | 3.64 | 4.97 | 0.87× | 0.87× | — | — | 61 / 3,970 / 0 | — | 1.2133 ms per file | — |
| fs.glob | 2–4 files · uncontended | 2 | 3.97 | 3.97 | 3.97 | 8.22 | 1.34× | 0.97× | 7.17 | 10.39 | 52 / 5,367 / 0 | — | 0.9932 ms per file | — |
| fs.glob | 5–16 files · contended | 2 | 5.09 | 5.09 | 5.09 | 7.91 | 1.61× | 1.61× | 7.82 | 11.47 | 139 / 6,381 / 0 | — | 0.5086 ms per file | — |
| fs.glob | 5–16 files · uncontended | 13 | 3.93 | 7.41 | 7.41 | 8.75 | 0.95× | 1.29× | 1.78 | 2.66 | 58 / 5,713 / 0 | — | 0.5973 ms per file | — |
| fs.glob | >64 files · contended | 3 | 9.78 | 9.78 | 9.78 | 10.54 | 1.34× | 1.34× | 24.39 | 36.09 | 120 / 16,591 / 0 | — | 0.0338 ms per file | — |
| fs.glob | >64 files · uncontended | 19 | 7.22 | 18.72 | 18.72 | 31.13 | 0.93× | 0.80× | 19.66 | 28.53 | 109 / 13,792 / 0 | — | 0.08 ms per file | — |
| fs.grep | 1 files · uncontended | 2 | 2.12 | 2.12 | 2.12 | 3.84 | 0.80× | 0.80× | — | — | 43 / 2,582 / 0 | — | 2.117 ms per file | sdk.lines |
| fs.grep | 17–64 files · contended | 2 | 21.89 | 21.89 | 21.89 | 29.40 | 2.14× | 2.14× | 23.11 | 33.85 | 280 / 16,796 / 0 | — | 0.5251 ms per file | sdk.lines |
| fs.grep | 17–64 files · uncontended | 5 | 12.56 | 12.60 | 12.60 | 31.75 | 1.33× | 0.74× | 1.43 | 1.79 | 210 / 14,896 / 0 | — | 0.5041 ms per file | sdk.lines |
| fs.grep | 2–4 files · contended | 1 | 4.86 | 4.86 | 4.86 | 4.86 | 1.10× | 1.10× | -0.44 | -0.10 | 146 / 7,478 / 0 | — | 1.6183 ms per file | sdk.lines |
| fs.grep | 2–4 files · uncontended | 4 | 3.67 | 5.28 | 5.28 | 5.29 | 0.85× | 1.17× | -8.15 | -11.79 | 87 / 5,562 / 0 | — | 1.7617 ms per file | sdk.lines |
| fs.grep | 5–16 files · contended | 4 | 5.97 | 9.37 | 9.37 | 20.24 | 1.17× | 1.83× | 8.83 | 13.11 | 198 / 12,326 / 0 | — | 0.7468 ms per file | sdk.lines |
| fs.grep | 5–16 files · uncontended | 11 | 5.65 | 22.92 | 22.92 | 39.99 | 1.05× | 2.16× | -8.37 | -12.71 | 124 / 6,653 / 0 | — | 0.8436 ms per file | sdk.lines |
| fs.grep | >64 files · contended | 5 | 43.76 | 52.68 | 52.68 | 54.42 | 1.69× | 1.40× | 21.65 | 31.70 | 1,005 / 49,344 / 0 | — | 0.1605 ms per file | sdk.lines |
| fs.grep | >64 files · uncontended | 16 | 27.10 | 43.56 | 43.56 | 44.29 | 1.22× | 0.93× | 7.89 | 11.06 | 570 / 31,142 / 0 | — | 0.1109 ms per file | sdk.lines |
| fs.list | 1 entries · uncontended | 1 | 4.29 | 4.29 | 4.29 | 4.29 | 1.18× | 1.18× | 19.74 | 29.03 | 58 / 4,801 / 0 | — | 4.286 ms per entrie | — |
| fs.list | 17–64 entries · contended | 6 | 4.69 | 8.91 | 8.91 | 12.94 | 0.89× | 1.25× | 7.07 | 10.57 | 103 / 6,627 / 0 | — | 0.0939 ms per entrie | — |
| fs.list | 17–64 entries · uncontended | 18 | 4.93 | 8.52 | 8.52 | 8.92 | 1.18× | 0.92× | 5.00 | 7.21 | 72 / 6,503 / 0 | — | 0.1247 ms per entrie | — |
| fs.list | 2–4 entries · contended | 1 | 4.44 | 4.44 | 4.44 | 4.44 | 1.57× | 1.57× | — | — | 234 / 14,334 / 0 | — | 1.1098 ms per entrie | — |
| fs.list | 2–4 entries · uncontended | 5 | 3.81 | 4.03 | 4.03 | 4.58 | 1.27× | 1.32× | 6.66 | 9.59 | 56 / 4,908 / 0 | — | 1.3427 ms per entrie | — |
| fs.list | 5–16 entries · contended | 5 | 4.07 | 4.20 | 4.20 | 14.86 | 0.80× | 0.37× | 5.97 | 9.23 | 76 / 5,745 / 0 | — | 0.7002 ms per entrie | — |
| fs.list | 5–16 entries · uncontended | 18 | 3.88 | 7.63 | 7.63 | 7.69 | 1.04× | 1.11× | 3.54 | 5.11 | 64 / 5,782 / 0 | — | 0.4367 ms per entrie | — |
| fs.read | ≤1 KiB · contended | 4 | 3.39 | 4.52 | 4.52 | 5.77 | 0.86× | 1.15× | -1.63 | -2.90 | 65 / 4,193 / 0 | — | 0.0036 ms per byte | sdk.lines |
| fs.read | ≤1 KiB · uncontended | 6 | 3.46 | 4.55 | 4.55 | 4.77 | 1.06× | 1.09× | 2.11 | 3.19 | 67 / 4,197 / 0 | — | 0.0044 ms per byte | sdk.lines |
| fs.read | ≤64 KiB · contended | 1 | 3.69 | 3.69 | 3.69 | 3.69 | 1.28× | 1.28× | — | — | 67 / 4,038 / 0 | — | 0.0003 ms per byte | sdk.lines |
| fs.read | ≤64 KiB · uncontended | 6 | 3.07 | 3.54 | 3.54 | 3.64 | 1.15× | 1.32× | 1.05 | 1.51 | 59 / 4,140 / 0 | — | 0.0003 ms per byte | sdk.lines |
| fs.read | ≤8 KiB · contended | 6 | 3.72 | 4.36 | 4.36 | 5.04 | 1.04× | 0.55× | 2.77 | 4.37 | 122 / 6,422 / 0 | — | 0.0007 ms per byte | sdk.lines |
| fs.read | ≤8 KiB · uncontended | 28 | 3.31 | 4.61 | 5.96 | 8.72 | 1.06× | 0.53× | 5.80 | 8.57 | 60 / 4,255 / 0 | — | 0.0012 ms per byte | sdk.lines |
| fs.rm | 1 files · contended | 4 | 10.25 | 11.93 | 11.93 | 16.36 | 0.64× | 0.47× | -9.48 | -12.91 | 178 / 9,157 / 0 | — | 10.248 ms per file | commit |
| fs.rm | 1 files · uncontended | 11 | 13.20 | 16.98 | 16.98 | 39.88 | 1.44× | 0.95× | 15.04 | 22.11 | 217 / 11,338 / 0 | — | 13.196 ms per file | files.change |
| fs.stat | ≤1 KiB · contended | 3 | 3.88 | 3.88 | 3.88 | 4.98 | 1.21× | 1.21× | 0.61 | 1.11 | 88 / 4,718 / 0 | — | 0.0071 ms per byte | — |
| fs.stat | ≤1 KiB · uncontended | 8 | 3.78 | 6.97 | 6.97 | 7.21 | 1.23× | 1.48× | 7.96 | 11.67 | 57 / 4,434 / 0 | — | 0.0058 ms per byte | — |
| fs.stat | ≤512 KiB · uncontended | 4 | 2.44 | 3.29 | 3.29 | 4.97 | 0.80× | 1.04× | — | — | 48 / 2,932 / 0 | — | 0 ms per byte | — |
| fs.stat | ≤64 KiB · contended | 5 | 3.23 | 3.81 | 3.81 | 4.33 | 1.29× | 1.52× | 0.56 | 0.69 | 75 / 4,429 / 0 | — | 0.0001 ms per byte | — |
| fs.stat | ≤64 KiB · uncontended | 17 | 2.87 | 4.16 | 4.16 | 5.73 | 1.06× | 0.93× | 3.25 | 4.59 | 45 / 3,650 / 0 | — | 0.0002 ms per byte | — |
| fs.stat | ≤8 KiB · contended | 2 | 3.19 | 3.19 | 3.19 | 3.31 | 1.24× | 1.09× | -3.58 | -4.71 | 50 / 3,616 / 0 | — | 0.0007 ms per byte | — |
| fs.stat | ≤8 KiB · uncontended | 12 | 2.86 | 3.50 | 3.50 | 4.15 | 1.12× | 0.97× | 4.72 | 7.00 | 53 / 4,204 / 0 | — | 0.0006 ms per byte | — |
| fs.write | >512 KiB · contended | 2 | 50.83 | 50.83 | 50.83 | 81.69 | 2.94× | 2.94× | — | — | 1,166 / 55,889 / 0 | — | 0 ms per byte | commit |
| fs.write | >512 KiB · uncontended | 7 | 14.42 | 17.08 | 17.08 | 24.46 | 1.15× | 1.28× | -1.61 | -2.60 | 170 / 6,377 / 0 | — | 0 ms per byte | commit |
| fs.write | ≤1 KiB · contended | 47 | 19.42 | 115.34 | 187.10 | 194.36 | 1.09× | 0.99× | 2.44 | 3.96 | 440 / 36,848 / 0 | — | 0.0462 ms per byte | files.change |
| fs.write | ≤1 KiB · uncontended | 84 | 9.64 | 18.09 | 29.03 | 30.26 | 1.08× | 0.83× | 6.40 | 9.42 | 164 / 7,449 / 0 | — | 0.0171 ms per byte | commit |
| fs.write | ≤512 KiB · contended | 21 | 26.50 | 133.47 | 133.47 | 138.82 | 1.35× | 1.50× | 18.02 | 26.30 | 401 / 40,089 / 0 | — | 0.0002 ms per byte | files.change |
| fs.write | ≤512 KiB · uncontended | 31 | 13.01 | 21.16 | 26.54 | 28.92 | 1.14× | 0.85× | 7.93 | 11.84 | 171 / 8,107 / 0 | — | 0.0001 ms per byte | commit |
| fs.write | ≤64 KiB · contended | 94 | 18.04 | 67.64 | 130.60 | 160.84 | 1.20× | 1.41× | 10.56 | 15.77 | 380 / 21,680 / 0 | — | 0.0011 ms per byte | commit |
| fs.write | ≤64 KiB · uncontended | 207 | 9.01 | 20.72 | 26.45 | 71.38 | 1.03× | 1.10× | -1.00 | -1.39 | 163 / 7,035 / 0 | — | 0.0007 ms per byte | commit |
| fs.write | ≤8 KiB · contended | 102 | 18.41 | 57.81 | 88.95 | 144.40 | 1.34× | 1.52× | 12.44 | 18.47 | 400 / 24,692 / 0 | — | 0.0045 ms per byte | commit |
| fs.write | ≤8 KiB · uncontended | 325 | 9.38 | 17.11 | 26.39 | 40.72 | 1.11× | 0.97× | 6.25 | 9.23 | 158 / 7,067 / 0 | — | 0.0029 ms per byte | commit |
| operator.store.stats | — · uncontended | 1 | 0.63 | 0.63 | 0.63 | 0.63 | 0.87× | 0.87× | -7.71 | -11.13 | 3 / 61 / 0 | — | — | — |
| sandbox.commit | 0 files · Committed · contended | 34 | 30.45 | 49.39 | 56.05 | 58.40 | 0.96× | 0.99× | -5.80 | -8.43 | 410 / 28,191 / 0 | — | — | commit |
| sandbox.commit | 0 files · Committed · uncontended | 112 | 28.29 | 49.84 | 67.45 | 285.13 | 1.04× | 1.27× | -1.81 | -2.71 | 347 / 23,971 / 0 | — | — | commit |
| sandbox.commit | 0 files · UpToDate · contended | 11 | 4.24 | 10.16 | 10.16 | 13.52 | 1.12× | 1.80× | 11.45 | 16.64 | 6 / 71 / 0 | — | — | observe.after |
| sandbox.commit | 0 files · UpToDate · uncontended | 49 | 3.99 | 6.95 | 8.98 | 16.25 | 1.06× | 1.18× | 1.95 | 2.77 | 6 / 71 / 0 | — | — | observe.after |
| sandbox.commit | 1 files · Committed · contended | 14 | 10.49 | 42.09 | 42.09 | 46.20 | 1.02× | 2.32× | -22.65 | -32.94 | 138 / 6,130 / 0 | — | 10.493 ms per file | commit |
| sandbox.commit | 1 files · Committed · uncontended | 14 | 8.86 | 13.29 | 13.29 | 14.17 | 0.87× | 1.01× | 0.46 | 0.71 | 110 / 3,876 / 0 | — | 8.858 ms per file | commit |
| sandbox.commit | 1 files · Conflict · contended | 1 | 344.94 | 344.94 | 344.94 | 344.94 | 1.25× | 1.25× | 5.68 | 8.70 | 15,283 / 591,681 / 8,191 | — | 344.942 ms per file | commit |
| sandbox.commit | 2–4 files · Committed · contended | 5 | 46.35 | 76.80 | 76.80 | 107.37 | 3.00× | 2.61× | 33.25 | 47.73 | 351 / 76,088 / 8,191 | — | 15.4503 ms per file | commit |
| sandbox.commit | 2–4 files · Committed · uncontended | 12 | 10.91 | 15.99 | 15.99 | 32.45 | 1.09× | 1.31× | -2.65 | -3.92 | 115 / 4,937 / 0 | — | 4.7945 ms per file | commit |
| sandbox.commit | 5–16 files · Committed · contended | 1 | 13.85 | 13.85 | 13.85 | 13.85 | 0.34× | 0.34× | -14.96 | -22.08 | 140 / 7,096 / 0 | — | 2.7692 ms per file | commit |
| sandbox.commit | 5–16 files · Committed · uncontended | 2 | 14.46 | 14.46 | 14.46 | 17.92 | 0.87× | 0.84× | — | — | 188 / 8,590 / 0 | — | 2.8916 ms per file | commit |
| sandbox.commit | — · Committed · contended | 2 | 217.90 | 217.90 | 217.90 | 279.31 | 1.65× | 1.65× | — | — | 1,189 / 51,669 / 0 | — | — | commit |
| sandbox.commit | — · Committed · uncontended | 13 | 104.31 | 1290.47 | 1290.47 | 15519.29 | 0.98× | 0.90× | 4.08 | 6.17 | 1,100 / 111,593 / 0 | — | — | commit |
| sandbox.exec | 0 files · contended | 266 | 49.98 | 1047.59 | 4940.42 | 5222.85 | 0.07× | 1.00× | -14.24 | -17.59 | 0 / 0 / 0 | 4767.30 | — | — |
| sandbox.exec | 0 files · uncontended | 189 | 36.03 | 770.91 | 1152.87 | 10765.41 | 0.96× | 1.00× | -2.94 | -4.34 | — | 4829.30 | — | — |
| sandbox.exec | 1 files · contended | 48 | 41.74 | 57.03 | 60.54 | 76.52 | 1.15× | 0.99× | 1.32 | 1.78 | — | 4.70 | 41.738 ms per file | — |
| sandbox.exec | 1 files · uncontended | 53 | 38.52 | 61.81 | 70.58 | 75.59 | 1.06× | 0.98× | -1.11 | -1.66 | — | 5 | 38.519 ms per file | — |
| sandbox.exec | 17–64 files · contended | 4 | 57.01 | 57.27 | 57.27 | 68.73 | 0.84× | 0.83× | — | — | — | 103 | 2.8506 ms per file | — |
| sandbox.exec | 17–64 files · uncontended | 6 | 70.67 | 80.46 | 80.46 | 81.62 | 0.89× | 1.02× | -5.04 | -7.57 | — | 95 | 3.5844 ms per file | — |
| sandbox.exec | 2–4 files · contended | 39 | 39.64 | 65.54 | 69.13 | 78.10 | 0.93× | 0.98× | 2.01 | 3.26 | — | 11.70 | 16.8165 ms per file | — |
| sandbox.exec | 2–4 files · uncontended | 41 | 43.93 | 68.94 | 73.75 | 81.58 | 0.96× | 1.04× | 5.60 | 8.02 | — | 11.30 | 18.961 ms per file | — |
| sandbox.exec | 5–16 files · contended | 12 | 57.33 | 70.47 | 70.47 | 71.55 | 1.14× | 1.00× | 11.97 | 17.68 | 0 / 0 / 0 | 27 | 8.0326 ms per file | — |
| sandbox.exec | 5–16 files · uncontended | 16 | 54.07 | 85.82 | 85.82 | 100.89 | 0.85× | 1.01× | -4.85 | -7.20 | — | 29 | 9.1857 ms per file | — |
| sandbox.exec | — · contended | 20 | 8390.44 | 33427.56 | 33427.56 | 35880.03 | 0.84× | 1.06× | 26.34 | 38.46 | — | 45036.40 | — | — |
| sandbox.exec | — · uncontended | 30 | 251.76 | 18197.92 | 31977.08 | 44345.21 | 0.72× | 0.99× | -34.41 | -49.84 | — | 45036.40 | — | — |
| sandbox.mount | — · contended | 90 | 12.35 | 29.93 | 36.53 | 38.08 | 1.03× | 1.37× | 0.05 | 0.10 | 64 / 1,710 / 82 | — | — | sandbox.mount.attach |
| sandbox.mount | — · uncontended | 176 | 10.31 | 18.22 | 21.44 | 25.03 | 0.94× | 1.05× | -0.45 | -0.67 | 45 / 1,362 / 82 | — | — | observe.after |
| sandbox.status | — · uncontended | 5 | 6.19 | 7.91 | 7.91 | 51.72 | 1.35× | 1.23× | 20.91 | 30.18 | 0 / 0 / 0 | — | — | observe.after |
| sandbox.unmount | — · contended | 68 | 16.11 | 30.85 | 41.25 | 44.27 | 1.17× | 1.33× | 11.28 | 16.43 | 0 / 0 / 0 | — | — | observe.after |
| sandbox.unmount | — · uncontended | 198 | 14.22 | 26.11 | 157.94 | 229.98 | 0.94× | 0.92× | 1.80 | 2.60 | 0 / 0 / 0 | — | — | observe.after |

| Method | Category | Calls | Bytes in | Bytes out | Files / entries | Outcomes |
| --- | --- | --- | --- | --- | --- | --- |
| branch.diff_branches | branch | 14 | 0.0 KiB | 748.8 KiB | 3,314 | ok 14 |
| branch.diff_commits | branch | 407 | 0.0 KiB | 22.4 MiB | 75,881 | ok 407 |
| branch.fork | branch | 24 | 0.0 KiB | 0.0 KiB | 0 | Forked 24 |
| branch.list_commits | project | 10 | 0.0 KiB | 95.7 KiB | 163 | ok 10 |
| branch.merge | branch | 9 | 0.0 KiB | 0.0 KiB | 0 | Merged 9 |
| branch.publish | branch | 1 | 0.0 KiB | 0.0 KiB | 0 | Added 1 |
| fs.apply | fs | 18 | 1.4 MiB | 0.0 KiB | 29 | Committed 18 |
| fs.diff_files | fs | 58 | 0.0 KiB | 522.7 KiB | 45 | Text 45, NoSuchPath 13 |
| fs.glob | fs | 63 | 0.0 KiB | 61.4 KiB | 821 | ok 63 |
| fs.grep | fs | 60 | 0.0 KiB | 266.5 KiB | 884 | ok 60 |
| fs.list | fs | 66 | 0.0 KiB | 356.4 KiB | 2,356 | ok 66 |
| fs.read | fs | 56 | 0.0 KiB | 204.2 KiB | 56 | ok 56 |
| fs.rm | fs | 15 | 0.0 KiB | 0.0 KiB | 15 | Committed 15 |
| fs.stat | fs | 59 | 0.0 KiB | 13.6 KiB | 59 | ok 59 |
| fs.write | fs | 920 | 18.2 MiB | 0.0 KiB | 920 | Committed 920 |
| operator.store.stats | operator | 1 | 0.0 KiB | 0.0 KiB | 0 | ok 1 |
| sandbox.commit | sandbox | 275 | 0.0 KiB | 0.0 KiB | 0 | Committed 214, UpToDate 60, Conflict 1 |
| sandbox.exec | sandbox | 734 | 2.5 MiB | 6.8 MiB | 0 | exit:0 730, exit:2 4 |
| sandbox.mount | sandbox | 276 | 0.0 KiB | 0.0 KiB | 0 | Mounted 276 |
| sandbox.status | sandbox | 5 | 0.0 KiB | 0.0 KiB | 0 | ok 5 |
| sandbox.unmount | sandbox | 276 | 0.0 KiB | 0.0 KiB | 0 | Unmounted 276 |

### C. Scale probes

Binary: daemon `c41a86d23822`.

Load average (1-min, runner (Docker VM kernel)): start 1.57 · end 1.91.

| Probe | ms (median) | Samples | Load 1-min | Counters (first sample) |
| --- | --- | --- | --- | --- |
| stat | 1.426 | 14.164 · 1.483 · 1.426 · 1.157 · 1.242 | 2.41–2.41 | statements 34, vm_steps 1140, fullscan_steps 0, sorts 0, returned_rows 92 |
| read | 1.23 | 1.219 · 1.253 · 1.215 · 1.373 · 1.23 | 2.41–2.41 | statements 19, vm_steps 816, fullscan_steps 0, sorts 0, returned_rows 77 |
| list_small | 1.112 | 1.265 · 1.112 · 1.32 · 1.035 · 1.072 | 2.41–2.41 | statements 19, vm_steps 825, fullscan_steps 0, sorts 0, returned_rows 77 |
| list_largest | 11.663 | 13.594 · 11.663 · 12.579 · 11.55 · 11.579 | 2.41–2.41 | statements 199, vm_steps 28416, fullscan_steps 0, sorts 0, returned_rows 2623 |
| grep_scoped | 1.576 | 1.679 · 1.339 · 1.584 · 1.576 · 1.333 | 2.41–2.41 | statements 24, vm_steps 971, fullscan_steps 0, sorts 0, returned_rows 86 |
| glob_scoped | 1.854 | 1.262 · 1.351 · 2.638 · 1.996 · 1.854 | 2.41–2.41 | statements 18, vm_steps 804, fullscan_steps 0, sorts 0, returned_rows 76 |
| grep_tree | 6334.923 | 6781.973 · 6735.476 · 6334.923 · 5922.264 · 5967.762 | 1.98–2.26 | statements 67462, vm_steps 4889821, fullscan_steps 0, sorts 0, returned_rows 481930 |
| glob_tree | 10.606 | 12.319 · 10.606 · 9.765 · 9.106 · 10.758 | 1.98–1.98 | statements 156, vm_steps 22980, fullscan_steps 0, sorts 0, returned_rows 2254 |
| diff_files | 6.013 | 6.013 · 8.584 · 8.521 · 5.434 · 5.288 | 1.98–1.98 | statements 96, vm_steps 4780, fullscan_steps 0, sorts 0, returned_rows 462 |
| list_commits | 0.823 | 1.862 · 0.823 · 0.825 · 0.749 · 0.703 | 1.98–1.98 | statements 70, vm_steps 1298, fullscan_steps 0, sorts 0, returned_rows 52 |
| diff_commits | 2.834 | 4.743 · 3.06 · 2.8 · 2.636 · 2.834 | 1.98–1.98 | statements 69, vm_steps 2260, fullscan_steps 0, sorts 0, returned_rows 239 |
| fork | 0.908 | 0.908 · 0.906 · 1.583 · 1.145 · 0.849 | 1.98–1.98 | statements 16, vm_steps 274, fullscan_steps 0, sorts 0, returned_rows 7 |
| merge | 32.667 | 37.582 · 33.886 · 31.928 · 32.667 · 31.292 | 1.98–1.98 | statements 530, vm_steps 23513, fullscan_steps 0, sorts 0, returned_rows 1704 |
| oneshot_mount_unmount | 17.59 | 21.631 · 15.55 · 17.861 · 17.59 · 17.069 | 1.98–1.98 | statements 68, vm_steps 2360, fullscan_steps 82, sorts 2, returned_rows 228 |
| oneshot_commit | 75.736 | 88.953 · 82.355 · 71.543 · 75.736 · 70.871 | 1.98–1.98 | statements 197, vm_steps 12673, fullscan_steps 82, sorts 2, returned_rows 930 |
| oneshot_exec | — |  ·  ·  ·  ·  | 1.98–1.98 | statements 0, vm_steps 0, fullscan_steps 0, sorts 0, returned_rows 0 |

### D. Storage internals

From the sealed file at snapshot r060: 446,970 pages of 4,096 B, 0 free · Commits 72,425 · Branches 1,563 · Layers 73 · compression 3.82× (canonical ÷ stored).

| Role | Objects | Canonical bytes |
| --- | --- | --- |
| 1 | 231,223 | 1.45 GiB |
| 2 | 79,883 | 1.23 GiB |
| 3 | 18,775 | 8.2 MiB |
| 4 | 53 | 10.5 KiB |
| 5 | 18,655 | 1.9 MiB |
| 6 | 204,308 | 980.8 MiB |
| 7 | 584,156 | 142.6 MiB |
| 8 | 1,803 | 531.0 KiB |
| 9 | 156,944 | 353.7 MiB |
| 10 | 77,843 | 9.6 MiB |
| 11 | 12,822 | 1.7 MiB |
| 13 | 2,538 | 208.5 KiB |

| Pack domain | Packs | Bytes |
| --- | --- | --- |
| 0 | 74,653 | 161.2 MiB |
| 1 | 78,190 | 948.8 MiB |

| Table or index | Pages | Bytes | Unused |
| --- | --- | --- | --- |
| pack | 297,164 | 1.13 GiB | 41.7 MiB |
| inode_value | 90,313 | 352.8 MiB | 6.7 MiB |
| binding_hint | 27,729 | 108.3 MiB | 10.1 MiB |
| object_location | 18,874 | 73.7 MiB | 7.8 MiB |
| commit | 6,074 | 23.7 MiB | 3.8 MiB |
| file_digest | 1,736 | 6.8 MiB | 786.3 KiB |
| commit_lineage | 1,568 | 6.1 MiB | 752.2 KiB |
| commit_runs | 1,515 | 5.9 MiB | 763.9 KiB |
| commit_identity | 1,117 | 4.4 MiB | 494.2 KiB |
| content_signature | 157 | 628.0 KiB | 9.7 KiB |
| branch | 68 | 272.0 KiB | 43.4 KiB |
| branch_names | 25 | 100.0 KiB | 16.6 KiB |
| branch_identity | 19 | 76.0 KiB | 14.7 KiB |
| run_merges | 9 | 36.0 KiB | 9.0 KiB |
| history_meta | 8 | 32.0 KiB | 2.1 KiB |
| sqlite_schema | 6 | 24.0 KiB | 7.7 KiB |
| layer | 5 | 20.0 KiB | 7.1 KiB |
| absorbed_heights | 4 | 16.0 KiB | 7.5 KiB |
| absorbed | 4 | 16.0 KiB | 7.5 KiB |
| layers_source | 3 | 12.0 KiB | 5.6 KiB |

### E. Stage times

**Time 374.8 s** (tooling): play 134.7 · consolidate 144.3 · verify 31.7 · probes 32.9 · tests 0.0 · seal + snapshot 13.8 · report 17.4

374.80 s tooling: prepare 1.68 · play 132.99 · consolidate 144.27 · verify 18.86 (diff_commits + full compareTree) · version walk 12.83 · probes 32.90 · metrics 0.84 · seal 1.48 · sealed figures 6.47 · snapshot copy 5.87 · report 0.57

### F. Attempts

| # | Binary | Started | Result | Reason |
| --- | --- | --- | --- | --- |
| 1 | c41a86d23822da1da70e03eb843938d51ddba522de5a8aa598911d3d3b24f851 | 2026-10-20T13:31:10.424Z | optimize | Speed: fs.grep 5–16 files · uncontended: 2.16× baseline (sdk.lines); Scaling: not judged: stat (chain-bounded): 3 of 9 points: a bound needs a full metadata delta-cap period (8) plus one; Counters: oneshot_mount_unmount.vm_steps: depth exponent 0.49; Contended work: not judged: no contended class has 3 ranges of 5+ calls with per-call SQL over a tree that grew 1.5× (10 classes too narrow); SQL per call (sql.call); Range growth: 33.9 MiB; median not judged: 2 of 3 earlier ranges; Snapshot time: 5812 ms for 1499.0 MiB new; size exponent 1.226; Wall projection: 1 |

### G. Evidence

- `~/lfs-history/metrics/range-060.a1.json`
- trace `~/lfs-history/runs/p3-main-x-c/trace/range-060.a1.jsonl` · runner log `~/lfs-history/runs/p3-main-x-c/play.log` · snapshot manifest `/Users/yifanxu/lfs-history/snapshots/range-060.json`

### H. Git internals

Seed pack: — objects, — (counted apart from lane objects).

| Lane | Objects | Index bytes |
| --- | --- | --- |
| r060-2-packages-client | 564 | 659.5 KiB |
| r060-3-agents-notes | 520 | 662.3 KiB |
| r060-1-examples-acp-agent | 475 | 658.0 KiB |
| r060-4-apps-web | 474 | 658.3 KiB |

| git command | ms | lstat |
| --- | --- | --- |
| `git status --porcelain` | 537.0 | 5,309 |
| `git diff --stat` | 43.0 | 5,303 |
| `git add -f` | 42.0 | — |
| `git rm --cached` | 9.0 | — |
| `git commit` | 47.0 | 5,305 |

### I. Proof details

| Lane | Point | Proof | Result | Detail | Native cached |
| --- | --- | --- | --- | --- | --- |
| r060-1-examples-acp-agent | end | P1 | pass | — | — |
| r060-1-examples-acp-agent | end | P2 | pass | exit 0 | — |
| r060-1-examples-acp-agent | end | P3 | pass | 300 bookkeeping path(s) | — |
| r060-1-examples-acp-agent | end | P4 | pass | 163 emitted files, exit 2 | — |
| r060-1-examples-acp-agent | end | P5 | pass | 25 files | — |
| r060-1-examples-acp-agent | end | P6 | n/a | not a repair | — |
| r060-3-agents-notes | end | P1 | pass | — | — |
| r060-3-agents-notes | end | P2 | pass | exit 0 | — |
| r060-3-agents-notes | end | P3 | pass | 300 bookkeeping path(s) | — |
| r060-3-agents-notes | end | P4 | pass | 107 emitted files, exit 2 | — |
| r060-3-agents-notes | end | P5 | pass | 46 files | — |
| r060-3-agents-notes | end | P6 | n/a | not a repair | — |
| r060-2-packages-client | end | P1 | pass | — | — |
| r060-2-packages-client | end | P2 | pass | exit 0 | — |
| r060-2-packages-client | end | P3 | pass | 300 bookkeeping path(s) | — |
| r060-2-packages-client | end | P4 | pass | 307 emitted files, exit 2 | — |
| r060-2-packages-client | end | P5 | pass | 70 files | — |
| r060-2-packages-client | end | P6 | n/a | not a repair | — |
| r060-4-apps-web | end | P1 | pass | — | — |
| r060-4-apps-web | end | P2 | pass | exit 0 | — |
| r060-4-apps-web | end | P3 | n/a | an install, not a refresh | — |
| r060-4-apps-web | end | P4 | pass | 532 emitted files, exit 2 | — |
| r060-4-apps-web | end | P5 | pass | 75 files | — |
| r060-4-apps-web | end | P6 | n/a | not a repair | — |
| lead | repair | P1 | n/a | folded into P6 | — |
| lead | repair | P2 | pass | exit 0 | — |
| lead | repair | P3 | n/a | a repair, not a no-op | — |
| lead | repair | P4 | n/a | folded into P6 | — |
| lead | repair | P5 | pass | 30 files | — |
| lead | repair | P6 | pass | P1 pass, P4 pass (2413 emitted files, exit 0) | — |

### J. Conflicts by path class

No conflicts by path recorded.
