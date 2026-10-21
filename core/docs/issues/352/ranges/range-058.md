# Range 058 · **stop** · attempt 3

**Matches git ✓** · daemon `c41a86d23822` · image `d3773b4e` · plan v2 · forked from snapshot r057 (run p3-main-x)
dsh `1e10966ef`..`7c2e5a740` · **60 commits** (10 mainline, 50 side) · 2026-07-31 → 2026-07-31
Areas changed: `packages/client` 45% · `/` 15% · `packages/host` 8% · other 32%
**Phase P3** · **Git ✓** · **Node ✗** (P1–P6: 16 pass, 1 stop, 0 NOT_RUN over 4 points) · **Content 0.15×** · **Churn 0.00**
**Time split:** play 138.7 s · git 134.7 s · Node 294.5 s · verify 19.4 s

| Latest version | Store on disk | Space amplification | Added this range | Commits | Time |
| --- | --- | --- | --- | --- | --- |
| **871.1 MiB** (+2.9 MiB) | **1.65 GiB** (+29.6 MiB) | **1.94×** (prev 1.92×) | **33.2 MiB** | **1,593** (total 69,520) | **388.2 s** tooling (total 223.4 min) |

**Checks:** 11 pass · 7 watch: Speed sandbox.exec — · uncontended: 1.89× baseline (no phase); not judged: branch.publish — · uncontended: 1/1/1 calls (2.19×), fs.write >512 KiB · uncontended: 3/12/5 calls (1.59×), sandbox.commit 2–4 files · Committed · uncontended: 7/5/3 calls (1.54×), fs.apply >512 KiB · uncontended: 1/1/1 calls (1.49×), sandbox.exec 17–64 files · uncontended: 1/4/7 calls (1.4×) (baseline class under 5 calls per range); Scaling insufficient same-binary points: 1 of 3 (daemon c41a86d23822); also not judged: oneshot_exec: 1 of 3 points of probe version 1; Counters insufficient same-binary points: 1 of 3 (daemon c41a86d23822); Contended work not judged: no contended class has 3 ranges of 5+ calls with per-call SQL; SQL per call (sql.call); Directory share 0.527; Range growth 33.2 MiB; median not judged: 0 of 3 earlier ranges; Snapshot time 5339 ms for 1461.3 MiB new; size exponent not judged (1 snapshots) · 1 optimize/stop: Node proofs
**D-6 triggers** (none): max candidate paths in a merge not traced (needs a candidate-path count on branch.merge (e.g. daemon timing `merge.paths` carrying `candidates`)) (trips > 50,000) · max lane hold of the merge at publish not traced (needs a span for the publication-lane hold inside branch.publish (e.g. daemon timing `publish.lane`, ms)) (trips > 500 ms) · Capacity/ObjectLimitExceeded/Busy from 8 merges: 0 (trips at 1)
**Moved most:** ▲ probe fork +232% · ▲ probe stat +83% · ▲ probe read +75%
**Budget:** 59 of 202 ranges · projected total 16.7 h (budget 16.8 h) · disk 55% of budget at range 202

## 1. Correctness

| Check | Result |
| --- | --- |
| Tree vs git | **5,255 tracked files match** (blob id and mode) |
| History | 3 lanes merged, 1 publish |
| Steps | 2,608 / 2,608 outcomes as planned |
| Conflicts | **3 / 3 planned hit · 0 unplanned** |
| Unit tests | **30 / 30 equal to native** |
| Installed tree | against the native replay of the on-top chain (lead, lane points, repair): **equal to native** (the repair's P1) · the lead's chain alone (context; without the lane points' installs and builds): 3307 package groups equal · not byte-compared: 3 pnpm state file(s) · by target: 433 bin shims, 4780 links · output root ×0, verification age ×1 |
| Last-writer-wins (`/.lww`) | unchanged (61 lines from 4 .gitignore files) · **97 picks** in 3 merges (80 under node_modules) · re-installed after the merge |
| Ignored files | — (installs not played in P3) |
| Milestone | — |
| Git | **HEAD = checkpoint `7c2e5a740`** · 122 commits written for 122 dsh commits · status clean · fresh mount read back 0 · lane guard 0 · git clean 4 untracked, unignored (3,347 B) |
| Install inputs (NODE_RULE §3; reported, not gated) | not recorded |
| Conflicts by path class | Tracked 0 · Install outputs 80 · Build outputs 17 · `.git` 0 |

### Node and git proofs

Each proof runs the same command natively on the identical tree id (NODE_RULE §6); a proof not run is `NOT_RUN`, never pass.

| Lane | Point | Tree | Install inputs | P1 | P2 | P3 | P4 | P5 | P6 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r058-3-apps-web | end | `52dbf48eb1e0` | `78c571a9048a` | pass (436 normalized) | pass | pass | pass | pass | n/a |
| r058-1-root | end | `c63a48493fa0` | `69a0fe43d6cb` | pass (450 normalized) | pass | n/a | pass | stop | n/a |
| r058-2-packages-client | end | `3552177cec0d` | `78c571a9048a` | pass (436 normalized) | pass | pass | pass | pass | n/a |
| lead | repair | `429249d66c9e` | `null` | n/a | pass | n/a | n/a | pass | pass (138,855 rewritten) |

P5 skip list (failing natively, set at calibration): `packages/host/apiproxy/tests/api-proxy-models.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-blank.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-fork.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-cold.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-rename.spec.ts` (fails natively) · `packages/settings/settings/tests/redact.spec.ts` (fails natively) · `packages/host/apiproxy/tests/rpc-schemas.spec.ts` (fails natively) · `packages/llm/llm/tests/invariant.spec.ts` (fails natively) · `packages/llm/llm-retry/tests/loader-composition.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-view.spec.ts` (fails natively) · `packages/llm/llm/tests/topology.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/loader-composition.spec.ts` (fails natively) · `packages/llm/llm-retry/tests/transport-recovery.spec.ts` (fails natively) · `packages/host/apiproxy/tests/fetch-carrier.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/dynamic-config.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-config.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-workspace.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/adapter.spec.ts` (fails natively) · `packages/settings/settings-local/tests/local.spec.ts` (fails natively) · `packages/settings/settings-local/tests/concurrency.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-projections.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-commands.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-approval.spec.ts` (fails natively) · `packages/llm/llm-retry/tests/retry.spec.ts` (fails natively) · `packages/client/connection/tests/node-half.spec.ts` (fails natively) · `packages/client/ui-conversation/tests/apply-inject.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/ask-question-row.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/assembly-surfaces.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-apply.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-branch-tails.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-code-subcalls.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-stats-bash-sample.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-tool-row.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-toolview-slot.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-view.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/coverage-tails.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/gate-branch-tails.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-bar.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-matrix.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-scenarios.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/queue-dock.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/selection-survival.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/service-orchestration.spec.ts` (fails natively) · `packages/client/ui-conversation/tests/skeleton.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/terminal-card.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/todo-panel.spec.tsx` (fails natively) · `packages/client/ui-model/tests/browser-plugin.spec.ts` (fails natively) · `packages/client/ui-model/tests/model-select.spec.tsx` (fails natively) · `packages/client/ui-models/tests/apply.spec.ts` (fails natively) · `packages/client/ui-models/tests/components.spec.tsx` (fails natively) · `packages/client/ui-models/tests/invariant.spec.ts` (fails natively) · `packages/client/ui-models/tests/onboarding-dialog.spec.tsx` (fails natively) · `packages/client/ui-models/tests/readiness.spec.ts` (fails natively) · `packages/client/ui-models/tests/store.spec.ts` (fails natively) · `packages/client/ui-primitives/tests/ansi.spec.ts` (fails natively) · `packages/client/ui-primitives/tests/atoms.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/hover-card.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/icons.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/json-tree.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/markdown-plain-text.spec.ts` (fails natively) · `packages/client/ui-primitives/tests/markdown.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/state-dot.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/terminal-block.spec.tsx` (fails natively) · `packages/client/ui-primitives/tests/tooltip.spec.tsx` (fails natively) · `packages/client/ui-question/tests/browser-plugin.spec.ts` (fails natively) · `packages/client/ui-question/tests/plan-review-panel.spec.tsx` (fails natively) · `packages/client/ui-question/tests/question-composer.spec.tsx` (fails natively) · `packages/client/ui-settings/tests/apply.spec.ts` (fails natively) · `packages/client/ui-settings/tests/settings-root.spec.tsx` (fails natively) · `packages/client/ui-sidebar/tests/apply.spec.tsx` (fails natively) · `packages/client/ui-sidebar/tests/sidebar-root.spec.tsx` (fails natively) · `packages/client/ui-sidebar/tests/sidebar-snapshot.spec.tsx` (fails natively) · `packages/client/ui-slash/tests/apply.spec.ts` (fails natively) · `packages/client/ui-slash/tests/menu-view.spec.tsx` (fails natively) · `packages/client/ui-slash/tests/service.spec.ts` (fails natively) · `packages/client/ui-trajectory/tests/layout.spec.tsx` (fails natively) · `packages/client/ui-trajectory/tests/table.spec.tsx` (fails natively) · `packages/client/ui-trajectory/tests/views.spec.tsx` (fails natively) · `packages/client/web/tests/app-shell.spec.tsx` (fails natively) · `packages/client/web/tests/app.spec.tsx` (fails natively) · `packages/examples/agent-spine-demo/tests/agent-core.spec.ts` (fails natively) · `packages/examples/agent-spine-demo/tests/gen-config-catalog.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-approval.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-blank.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-cold.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-commands.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-config.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-fork.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-models.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-projections.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-rename.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-view.spec.ts` (fails natively) · `packages/host/apiproxy/tests/api-proxy-workspace.spec.ts` (fails natively) · `packages/host/apiproxy/tests/client-handler.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/adapter.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/dynamic-config.spec.ts` (fails natively) · `packages/llm/llm-deepseek/tests/loader-composition.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/adapter.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/dynamic-config.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/loader-composition.spec.ts` (fails natively) · `packages/llm/llm-pi-ai/tests/sdk-options.spec.ts` (fails natively) · `packages/llm/llm-retry/tests/transport-recovery.spec.ts` (fails natively) · `packages/skill/skill-local/tests/skill-local.spec.ts` (fails natively) · `packages/skill/tool-skill/tests/tool-skill.spec.ts` (fails natively) · `packages/ui/permission/tests/permission.spec.ts` (fails natively) · `packages/ui/permission/tests/projection.spec.ts` (fails natively) · `packages/ui/tui/tests/chat-helpers.spec.ts` (fails natively) · `packages/ui/tui/tests/plugin-shape.spec.ts` (fails natively) · `packages/ui/tui/tests/tui.spec.ts` (fails natively) · `packages/client/ui-trajectory/tests/client-bundle.spec.ts` (fails natively) · `apps/cli/tests/source-launch.compat.spec.ts` (fails natively) · `packages/client/ui-command/tests/popup-view.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/apply-inject.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/assembly-surfaces.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-apply.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-branch-tails.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-code-subcalls.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-toolview-slot.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-view.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/service-orchestration.spec.ts` (fails natively) · `packages/client/ui-goal/tests/browser-plugin.spec.tsx` (fails natively) · `packages/client/ui-goal/tests/goalbar.spec.tsx` (fails natively) · `packages/client/ui-trajectory/tests/views.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/workspace-picker.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/browser-styles.spec.ts` (fails natively) · `packages/client/ui-conversation/tests/selection-survival.spec.tsx` (fails natively) · `packages/client/runtime/tests/wire-events.spec.ts` (fails natively) · `packages/client/ui-command/tests/browser-plugin.spec.ts` (fails natively) · `packages/client/runtime/tests/projection-store.spec.ts` (fails natively) · `packages/client/ui-slash/tests/apply.spec.ts` (fails natively) · `packages/client/runtime/tests/client-apply.spec.ts` (fails natively) · `packages/client/runtime/tests/queue-store.spec.ts` (fails natively) · `packages/client/ui-sidebar/tests/sidebar-snapshot.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/rename-assembly.spec.tsx` (fails natively) · `packages/client/connection/tests/fixture-commands.spec.ts` (fails natively) · `packages/client/runtime/tests/workspaces-service.spec.ts` (fails natively) · `packages/client/ui-slash/tests/service.spec.ts` (fails natively) · `packages/client/test-runtime/tests/runtime.spec.tsx` (fails natively) · `packages/client/ui-command/tests/service.spec.ts` (fails natively) · `packages/client/ui-conversation/tests/web-card.spec.tsx` (fails natively) · `packages/client/ui-workspace/tests/workspace-browser.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/ask-question-row.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/todo-panel.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/skeleton.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/input-bar.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/terminal-card.spec.tsx` (fails natively) · `packages/client/ui-conversation/tests/chat-tool-row.spec.tsx` (fails natively) · `packages/session-query/session-query-sqlite/tests/sqlite.spec.ts` (fails natively).

## 2. Activity

**3,346 calls** · **139 steps** by **8 agents + lead** on **3 Branches + main** · **189 Workspaces** (99% one-shot, 0 open at end)
**File changes:** +158 added · 1,298 modified · −109 deleted · 17.5 MiB written · fs 1,444 : Sandbox 121 (**12 : 1**, reported only in P3)
**Execs:** 527 (JS 47 · shell 480) · 4 non-zero exits · install 0 · test runs 5 · version figures 1 (tooling)

**Calls by category**

| Category | Calls | Writes | Reads | Outcomes |
| --- | --- | --- | --- | --- |
| fs | 1,793 | 1,457 | 336 | Committed 1,457 · Text 42 · NoSuchPath 8 · Equal 3 |
| sandbox | 1,095 | 713 | 4 | commit 186 (Committed 151, UpToDate 34, Conflict 1) · exec 527 (exit:0 523, exit:2 3, exit:1 1) · mount 189 (Mounted 189) · status 4 · unmount 189 (Unmounted 189) |
| branch | 448 | 32 | 416 | diff_branches 13 · diff_commits 403 · fork 23 (Forked 23) · merge 8 (Merged 8) · publish 1 (Added 1) |
| project | 9 | 0 | 9 | list_commits 9 |
| operator | 1 | 0 | 1 | store.stats 1 |
| **Total** | **3,346** | **2,202** | **766** |  |

**Branches**

| Branch | Agents | Steps | Commits | Merged into main | Published |
| --- | --- | --- | --- | --- | --- |
| r058-1-root | a01 | 17 | 428 | ✓ | — |
| r058-2-packages-client | a02 a03 a04 | 45 | 389 | ✓ | — |
| r058-3-apps-web | a05 a06 a07 a08 | 71 | 435 | ✓ | — |
| main | lead | 6 | 341 | — | ✓ |

**Conflicts**

| Kind | Hit / planned | Where | Resolved in |
| --- | --- | --- | --- |
| Commit Conflict | 1 / 1 | r058-3, a08 after a06 | 0.1 s |
| Stale clean merge | 1 / 1 | r058-3, a05 a06 | merged cleanly |
| Decoy edit | 1 / 1 | r058-3, a07 a05 | replaced before the checkpoint |
| Merge / publish race | 0 / 0 | — | — |
| **Unplanned** | **0** | — | — |

**Agents**

| Agent | Branch | Steps | fs | sandbox | branch | project | Commits | Conflicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a01 | r058-1 | 17 | 10 | 7 | 0 | 0 | 428 | — |
| a02 | r058-2 | 13 | 6 | 7 | 0 | 0 | 243 | — |
| a03 | r058-2 | 11 | 3 | 8 | 0 | 0 | 16 | — |
| a04 | r058-2 | 21 | 8 | 13 | 0 | 0 | 130 | — |
| a05 | r058-3 | 14 | 4 | 10 | 0 | 0 | 90 | stale-clean-merge, decoy |
| a06 | r058-3 | 24 | 10 | 14 | 0 | 0 | 142 | commit-conflict, stale-clean-merge |
| a07 | r058-3 | 15 | 8 | 7 | 0 | 0 | 145 | decoy |
| a08 | r058-3 | 18 | 8 | 10 | 0 | 0 | 58 | commit-conflict |
| lead | main | 6 | 1 | 0 | 5 | 0 | 341 | — |
| **Total** |  | **139** | **58** | **76** | **5** | **0** | **1,593** | **3** |

Scale-probe Commits (setup and samples): **22**, not range work and not counted above.


**Execs by tool:** git 102 · pnpm 1 · tsc 3 · vitest 5 · other 416

| Lane | git status | git diff | git add | git rm --cached | Lane commits | Loose objects |
| --- | --- | --- | --- | --- | --- | --- |
| r058-3-apps-web | 48 | 48 | 48 | 1 | 48 | 934 |
| r058-2-packages-client | 36 | 36 | 36 | 2 | 36 | 791 |
| r058-1-root | 11 | 11 | 11 | 5 | 11 | 211 |
| **lead** | — | — | — | — | 122 commit-tree | index rebuild ✓ · repack ✓ |

| Lane | Installs | Refreshes | tsc -b | vitest points | Test files | Equal to native |
| --- | --- | --- | --- | --- | --- | --- |
| r058-3-apps-web | 0 | 1 | 1 | 1 | 47 | 47 / 47 |
| r058-1-root | 1 | 0 | 1 | 1 | 73 | — / 73 |
| r058-2-packages-client | 0 | 1 | 1 | 1 | 97 | 97 / 97 |
| **lead repair** | 1 | — | 1 | — | — | 138,855 files rewritten |

## 3. Storage

**3a. Overview**

|  | Previous (r057) | Now | Change |
| --- | --- | --- | --- |
| Latest version (tracked / `node_modules` / build / `.git`) | 868.1 MiB (29.4 MiB / 692.1 MiB / 27.4 MiB / 119.3 MiB) | 871.1 MiB (29.8 MiB / 692.1 MiB / 27.8 MiB / 121.4 MiB) | +2.9 MiB |
| Version figures from | — | full: first (no manifest for range 57) | — |
| Files / directories / symlinks | 64,938 / 10,095 / 4,772 | 65,037 / 10,097 / 4,788 | +99 / +2 / +16 |
| Largest file / largest directory | 23.5 MiB / 2,252 entries | 23.5 MiB (`node_modules/.pnpm/@rolldown+binding-linux-arm64-gnu@1.1.1/node_modules/@rolldown/binding-linux-arm64-gnu/rolldown-binding.linux-arm64-gnu.node`) / 2,252 entries (`node_modules/.pnpm/@mistralai+mistralai@2.2.6_@opentelemetry+api@1.9.0/node_modules/@mistralai/mistralai/esm/models/components`) | — |
| **Store on disk** (allocated, sealed) | 1.62 GiB | 1.65 GiB | +29.6 MiB |
| **Space amplification** (total · tracked) | 1.92× · tracked 4.91× | 1.94× · tracked 4.93× | 0.03 |
| Head cost / history cost | — | — (needs a reachability walk of the sealed file; not built) / — | — |
| **Stored per byte changed** (content / metadata / shared) | — | **8.34** (0.89 / 0.25 / 1.02) | 1.14× the median range |
| **Stored per Commit** | 24.5 KiB | 18.9 KiB | — |
| Metadata share | 0.45 | 0.45 | this range 0.53 |
| History: Commits / Layers / Branches | 67,927 | 69,520 / 40 / 956 | +1,593 |
| Projection at range 202 (estimate: study model, per-Commit cost × planned Commits + install and build forecast) | — | 8.26 GiB (Commits 5.71 GiB · installs 827.2 MiB · build 91.8 MiB) | — |
| Disk guard floor at range 202 (headroom: 256 MiB per range minimum) / disk budget | — | 37.62 GiB / 55% | — |
| Snapshot | — | r058, 1.43 GiB new blocks | — |

**3b. Where the bytes are**

| Part | Bytes | × latest version | Change this range |
| --- | --- | --- | --- |
| Content | 926.5 MiB | 1.06 | +12.1 MiB |
| Metadata | 155.4 MiB | 0.18 | +3.6 MiB |
| Index rows | 528.7 MiB | 0.61 | +12.4 MiB |
| Waste | 79.7 MiB | 0.09 | +1.4 MiB |
| Other | 2.1 MiB | 0.00 | +36.0 KiB |
| **Total = Store on disk** | **1.65 GiB** | **= 1.94** space amplification | +29.6 MiB |

Exact: from the sealed file.

**3c. By source**

| Source | Latest version | Stored (content + metadata) | Amplification | Head cost | Added this range | Changed this range | Stored per byte changed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Tracked | 29.8 MiB | 146.9 MiB (76.1 MiB + 70.9 MiB) | 4.93× | — | 2.6 MiB | 4.0 MiB | 0.65 |
| `node_modules` | 692.1 MiB | 241.0 MiB (201.5 MiB + 39.4 MiB) | 0.35× | — | 1002.6 KiB | 0.4 KiB | 2828.16 |
| Build output | 27.8 MiB | 35.9 MiB (33.0 MiB + 2.9 MiB) | 1.29× | — | 1.3 MiB | 9.6 MiB | 0.13 |
| `.git` | 121.4 MiB | 600.7 MiB (572.5 MiB + 28.2 MiB) | 4.95× | — | 10.7 MiB | 0.0 KiB | — |
| Shared (index rows + waste + other) | — | 610.4 MiB | — (not divided) | — | 13.9 MiB | — | — |
| Unattributed (Saves without traced sizes) | — | 57.4 MiB | — | — | — | — | — |
| **Total** | — | **1.65 GiB** | **= 1.94×** space amplification | — | — | — | — |

Sources by the Commit that wrote them (an install Commit is `node_modules`, a build Commit build output). Any comparison with git uses the Tracked row only.

**3d. What's inside**

| Object | Total | Added | Avg size | Reused (dedupe hits) | As delta |
| --- | --- | --- | --- | --- | --- |
| Whole files | 224,962 | +4,176 | 6.5 KiB | 0 (derived) | 55% |
| Chunks (large files) | 77,739 | +1,003 | 16.1 KiB | — | 57% |
| Large-file extents | 18,507 | — | 0.4 KiB | — | — |
| Directories | 560,032 | 5,045 (with inodes, pooled) | 0.3 KiB | — | 59% |
| Inodes and attributes | 455,944 | ↑ pooled | 2.9 KiB | — | — |
| Symlinks | 2,537 | +4,904 | 0.1 KiB | — | — |

Delta: 3.7% at depth cap · 15% of refused bases stopped by budget · `node_modules` reinstall: absolute: 916952 new stored bytes for 363 raw changed bytes of 16 changed packages (2526.039×; raw under 1 MiB)

**3e. Git and Node (P3)**

| Measure | Value |
| --- | --- |
| Tracked only (amplification of the tracked source; comparable with ranges 0–14) | 4.93× (146.9 MiB for 29.8 MiB) |
| Store growth per git commit (index / loose objects / pack) | 3.0 KiB / 4.7 KiB / 10.1 KiB over 217 git commits |
| **Content ratio** (stored content ÷ distinct new content; ≤1.x, watch > 2×, act > 5×) | 0.15× |
| **Churn ratio** (stored ÷ bytes Node churn rewrote) | 0.00 (2.3 MiB stored for 2.09 GiB rewritten) |
| Native-disk equivalence (stored ÷ lanes × one native checkout) | 0.65 (3 lanes × 871.1 MiB) |
| Metadata per file / per Commit (budget from the dev range) | 0.1 KiB / 2.2 KiB (budget not set) |

## 4. Speed

Daemon `c41a86d23822` · p50 / p95 · ratio to baseline (dominant size class) in brackets

| write | read | list | Commit (one-shot) | mount | merge | exec (FUSE ÷ native) |
| --- | --- | --- | --- | --- | --- | --- |
| 9.0 ms / 22.9 ms (0.93×) | 3.1 ms / 4.9 ms (0.90×) | 3.8 ms / 7.0 ms (1.04×) | 23.0 ms / 91.2 ms (1.10×) | 10.8 ms / 20.8 ms (0.95×) | 470 ms / 470 ms (1.03×) | — (native comparison in P3; exec 42.2 ms / 1482 ms) |
| SQL p50: 163 stmts | 60 stmts | 64 stmts | 252 stmts | 51 stmts | 6,983 stmts | — |

**Commit cost:** 7.77 ms per changed file · **One-shot Workspace** (mount + exec + commit + unmount): 838 ms p50 over 189
**Slowest:** sandbox.exec 45556 ms · sandbox.exec 35191 ms · sandbox.exec 34711 ms · checkpoint diff_commits 0.12 ms and 1.72 statements per entry (74,378 entries per page)
**Scaling:** not judged: fewer than 3 same-binary ranges (16 probes)

**Git and Node** (LayerFS ÷ native on the identical tree; ×base compares only with the P3 re-baseline)

| Operation | LayerFS p50 / p95 | Native p50 / p95 | ÷ native (p50) | #362 case ÷ native |
| --- | --- | --- | --- | --- |
| git status (cold) | 543 ms / 543 ms | — / — | — | git / status-cold: — |
| git status (steady) | 557 ms / 806 ms | — / — | — | git / status-steady: — |
| git add | 43.0 ms / 135 ms | — / — | — | git / add: — |
| git commit (lane) | 47.0 ms / 115 ms | — / — | — | git / commit: — |
| lead writes main | 7171 ms / 7171 ms | — / — | — | — |
| repack | 3778 ms / 3778 ms | — / — | — | — |
| pnpm install (incremental) | 4121 ms / 4121 ms | 2109 ms / 2109 ms | 1.95× | pnpm-reinstall / cold: — |
| pnpm refresh | 1799 ms / 1799 ms | 940 ms / 940 ms | 1.91× | pnpm-reinstall / steady: — |
| tsc -b | 14005 ms / 14005 ms | 6564 ms / 8022 ms | 2.13× | tsc-b / cold: — |
| vitest | 14684 ms / 14684 ms | 4840 ms / 4840 ms | 3.03× | vitest / cold: — |

**Health:** 0 Workspaces open · 0 overlay files left · daemons 2 MB (+0 MB) over 5 of 5 Sandboxes · 15 open files · WAL before seal 0.0 KiB
**Resilience:** Busy 0 · EAGAIN 0 · refused unmount 0 · writer wait — · lane hold — per Commit (p50 / p95) · daemon RSS max 2 MB, median 2 MB over 1 daemons · overlay max — · unmount 13.2 ms / 21.6 ms

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

**WAL across each class this range:** fs.write ≤1 KiB 4194304 → 4194304 B · fs.write ≤8 KiB 4173592 → 4194304 B · fs.write ≤64 KiB 4173592 → 4194304 B · fs.read ≤8 KiB 4194304 → 4194304 B · sandbox.mount 4194304 → 2678032 B · sandbox.commit 1 file (Committed) 4194304 → 4194304 B · branch.merge 0 → 4194304 B
**Host load (1-min, recorded, not waited on):** macOS 5.73 at the first command → 7.17 after the last (max 10.95 over 8 commands) · Docker VM 0.17 → 1.49

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

**Watch row** (control (b)/(a) p50 over 1.25×, or (b)'s reads per call over 2× (a)'s): pass (sample control-058.a3)

## 5. Findings and action

### Finding 058.a1 · stop

**1. Trigger** (attempt 1, daemon `32eda22d657d`)

| Check | Value | Threshold |
| --- | --- | --- |
| Correctness | tree 0 missing, 1 extra, 0 content, 0 mode; steps 2605/2606; conflicts 3/3; tests 30/30 equal to native | all |

Diagnosis pending: `finding-058.a1.json`.

### Finding 058.a2 · stop

**1. Trigger** (attempt 2, daemon `32eda22d657d`)

| Check | Value | Threshold |
| --- | --- | --- |
| Correctness | tree 0 missing, 1 extra, 0 content, 0 mode; steps 2605/2606; conflicts 3/3; tests 30/30 equal to native | all |

Diagnosis pending: `finding-058.a2.json`.

### Finding 058.a3 · stop

**1. Trigger** (attempt 3, daemon `c41a86d23822`)

| Check | Value | Threshold |
| --- | --- | --- |
| Node proofs | 16 pass · 1 stop · 0 NOT_RUN over 4 points: r058-1-root end P5 | P1–P6 pass at every point |

Diagnosis pending: `finding-058.a3.json`.

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

- **a1 (`p3-main-x`, daemon `32eda22d`): STOP at the checkpoint, on the path check only.** Native first passed: 3 points calibrated and the repair ok.
  - `diff_commits` from r57's head to r58's head lists `packages/cordis/tool-cordis/src/api-catalog.ts` as changed. Git's `c57..c58` (`085383b145..7c2e5a740d`) does not touch it.
  - The ids check passed. The full tree compare passed: 5,255 files, content and mode equal. So the final bytes are git's (blob `4d986582`, the same at c57 and c58).
  - The trace shows the cause. Lane `r058-3-apps-web` wrote the file at `r058.s0115` (227,085 B), and the reconcile wrote the checkpoint's bytes back (234,915 B). The net change is zero.
  - `diff_commits` did not report the path as metadata-only (kind Modified with content false), which the harness accepts. It reported a change, though the file's bytes at both heads are identical.
  - Steps: lead 3 s; cuts 30, 45 and 52: 33, 18 and 9 s; lanes 69 s; repair 130 s (install 36.9, build 30.5, tests 2.2); verify 20 s; finish stopped at 6 s.
- **a2 (`p3-main-x-b`, a fork of `p3-main-x`'s r57 snapshot, chain set to the r57 adopted native state `state-9e2a63b0…`, LESSONS R8): STOP, the same.**
  - The same path, the same counts (git 361, LayerFS 537 paths), ids and full tree pass. Deterministic: the same write sequence gives the same diff.
  - Steps: lanes 70 s, repair 131 s, verify 20 s.
- **Reading:** a LayerFS `diff_commits` false positive after a write and a write-back to the same bytes. A file rewritten to other bytes and then back to its original bytes is listed as changed. The stored representation probably differs (a delta or predecessor chain, F-063), while the bytes are equal.
- **Gap:** the trace records no `diff_commits` response items, so the item's kind and content flag were not seen.
- No snapshot, savestate or adopt for a1 or a2.
- **a3 (`p3-main-x-c`, daemon `c41a86d2` and addon `a1078e69`, built at main `d06a2b81fa` with fix 073; a fork of `p3-main-x`'s r57 snapshot, chain set to the r57 adopted state `state-9e2a63b0…`, R8): STOP on Node proof P5, closed under a liaison ruling (owner delegation).**
  - **The checkpoint passes with no exemption:** tree, paths, ids and full all true, with `extra` empty. On a1 and a2, `api-catalog.ts` was the one extra.
  - **The `diff_commits` item, read on a read-only copy of a3's Store** (volume `…-diag58c`, since removed; SDK `d06a2b81` with addon `a1078e69`): r57 head `12dbfee1…` → r58 head `12517c6a…` still lists `/packages/cordis/tool-cordis/src/api-catalog.ts`, as `{kind: Modified, content: false, identity: false, metadata: true}`.
    - The roots still differ: r57 `ee055170…` against r58 `40ba3671…`, at the same inode 699528 and 234,915 B.
    - F-073 made the content flag compare bytes, so the path counts as metadata-only, the same as the control path `apps/cli/src/tui.ts`. In all, 74,378 diff items.
  - **F-063:** active; chunk PREFIX 482 against FULL 154, over 95 lane git Commits. f063.mjs ran on build `d06a2b81fa` and exited 0.
  - **The stop:** at `r058-1-root.end`, `packages/skill/skill-local/tests/skill-local-watcher.spec.ts` passes natively and fails on LayerFS, with `expected 1 to be greater than or equal to 2` at line 225.
    - The test mocks the watcher and checks the rewatch and invalidation that follow a runtime watcher error. It waits only two `settle()` calls, each a single `setTimeout(0)`, so it races real async I/O. Its temporary directories are in the container's tmpdir, off the mount.
    - The same point and test passed on LayerFS in a1 and a2: 73 files, exit 0, vitest 8.8 and 9.1 s.
    - P1–P4 pass at that point, and the tree and ids are equal.
  - **Liaison ruling (a): the stop is a timing-sensitive test, not a content difference.** The verdict stays "stop (P5, timing-sensitive test; liaison ruling)", with P5 recorded as it is. There is no a4 and no rerun of the test.
    - The test goes on the timing-sensitive list (SCRIPTS §16). It stays judged in later ranges, and if it fails again it goes to the liaison with the same evidence.
  - **Lane exec on a3 against a1 (old binaries, same points and trees):**

    | Point | vitest ms a1 / a3 | tsc ms a1 / a3 |
    | --- | --- | --- |
    | `r058-3-apps-web.end` | 7,651 / 11,736 (+53%) | 10,466 / 14,005 (+34%) |
    | `r058-1-root.end` | 8,817 / 14,684 (+67%) | 10,092 / 14,061 (+39%) |
    | `r058-2-packages-client.end` | 15,618 / 24,605 (+58%) | 9,385 / 11,670 (+24%) |

    - Host 1-minute load during a3's lanes was 7.6–8.2, rising to 11.0 at the repair start. The Docker VM load was 0.2–2.0, as on a1 and a2.
    - On the identical r55–r57 trees, the new binaries' lane exec was faster than the old on r55–r56 and 10–25% slower on r57 (re-baseline run against `p3-main-x`). So a 55% slowdown from the binary is not established.
    - r59–r60 report these per point (liaison condition). A sustained slowdown above 25% at similar load is a finding.
  - **Steps:** lead 3 s; cuts 30, 45 and 52: 34, 19 and 10 s; lanes 89 s; repair 156 s (install 45.6, build 35.2, tests 2.8); verify 24 s; finish 66 s. Control passes.
  - **Recovery note:** post.sh first started with its default attempt 1 on `p3-main-x-c`. f063.mjs printed "no trace", and the proofs were stopped before they wrote anything; a stray `…-node-oracle` container was removed. The a1 and a2 metrics were checked unchanged (mtimes 19:03 and 19:11). post.sh then ran on attempt 3 with build `d06a2b81fa`.
  - **Storage:** Store +29.6 MiB; added this range 33.2 MiB; snapshot 1,461.3 MiB new in 5.3 s.
  - **Isolation:** the diagnostic volume `layerfs-issue352-lead51-diag58`, a read-only copy of `p3-main-x`, is removed along with `~/lfs-history/diag58`, and so is the a3 copy. `p3-main-x-b` stays as evidence.


## Appendix

### A. Checks

| Check | Value | Threshold | Result |
| --- | --- | --- | --- |
| Correctness | tree ok; steps 2608/2608; conflicts 3/3; tests 30/30 equal to native | all | pass |
| Health | 0 open, 0 overlays | 0, 0, flat | pass |
| Speed | sandbox.exec — · uncontended: 1.89× baseline (no phase); not judged: branch.publish — · uncontended: 1/1/1 calls (2.19×), fs.write >512 KiB · uncontended: 3/12/5 calls (1.59×), sandbox.commit 2–4 files · Committed · uncontended: 7/5/3 calls (1.54×), fs.apply >512 KiB · uncontended: 1/1/1 calls (1.49×), sandbox.exec 17–64 files · uncontended: 1/4/7 calls (1.4×) (baseline class under 5 calls per range) | ≤ 1.2× | watch |
| Scaling | insufficient same-binary points: 1 of 3 (daemon c41a86d23822); also not judged: oneshot_exec: 1 of 3 points of probe version 1 | < 0.15 | watch |
| Counters | insufficient same-binary points: 1 of 3 (daemon c41a86d23822) | < 0.05 | watch |
| Contended work | not judged: no contended class has 3 ranges of 5+ calls with per-call SQL; SQL per call (sql.call) | < 0.05 (SQL work against tree size) | watch |
| Directory share | 0.527 | < 0.5 | watch |
| Reinstall growth | absolute: 916952 new stored bytes for 363 raw changed bytes of 16 changed packages (2526.039×; raw under 1 MiB) | ≤ 2× changed packages; ≤ 1 MiB with none or under 1 MiB raw | pass |
| Delta at cap | 0.0373 (budget 0.1516) | < 0.1 | pass |
| Range growth | 33.2 MiB; median not judged: 0 of 3 earlier ranges | ≤ 3× median, ≤ 2 GiB | watch |
| Snapshot time | 5339 ms for 1461.3 MiB new; size exponent not judged (1 snapshots) | < 0.15 | watch |
| Disk projection | 0.55 | < 0.8 | pass |
| Wall projection | 0.99 | ≤ 1 (p3 budget) | pass |
| Git | HEAD = checkpoint; 122 commits; clean; 0 read back; 0 guard violations | HEAD = checkpoint, commits = dsh, clean, 0 read back, 0 guard | pass |
| Node proofs | 16 pass · 1 stop · 0 NOT_RUN over 4 points: r058-1-root end P5 | P1–P6 pass at every point | stop |
| `.git` conflicts | 0 (tracked 0 · install 80 · build 17; tracked judged by Correctness) | 0 | pass |
| Resilience | Busy 0 · EAGAIN 0 · refused unmount 0 | 0 Busy, EAGAIN, refused unmount | pass |
| Content ratio | 0.15× | ≤ 2× (act > 5×) | pass |
| Install inputs (reported, not gated) | not recorded | none until NODE_RULE §3 is decided | pass |

Played vs planned:

| Count | Played | Planned |
| --- | --- | --- |
| Steps (bash calls) | 139 | 140 |
| Lanes / agents | 3 / 8 | 3 / 8 |
| LayerFS Commits | 1593 | 1486 |
| Workspaces (one-shot share) | 189 (0.99) | 75 (0.973) |
| Reads | 287 | 287 |
| Reconcile writes | 334 | 334 |
| Left out (not played in this phase) | install 1, tests 1 | — |

### B. Latency by method and size class

Binary: daemon `c41a86d23822` (attempt 3). Each call's own input is its size class; ×base compares the same operation and class only.

| Operation | Size class | n | p50 | p95 | p99 | max | ×base p50 | ×base p95 | Depth slope | Tree slope | SQL p50: statements / VM steps / full-scan steps | FUSE opcodes p50 per exec | Per unit (p50) | Slowest phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| branch.diff_branches | >64 entries · uncontended | 13 | 18.91 | 557.94 | 557.94 | 891.09 | 0.34× | 1.18× | — | — | 219 / 24,871 / 0 | — | 0.0795 ms per entrie | — |
| branch.diff_commits | 2–4 entries · uncontended | 1 | 3.50 | 3.50 | 3.50 | 3.50 | no baseline | no baseline | — | — | 78 / 4,291 / 0 | — | 1.1673 ms per entrie | — |
| branch.diff_commits | 5–16 entries · uncontended | 1 | 5.28 | 5.28 | 5.28 | 5.28 | no baseline | no baseline | — | — | 71 / 7,000 / 0 | — | 0.8807 ms per entrie | — |
| branch.diff_commits | >64 entries · uncontended | 396 | 21.87 | 51.79 | 84.36 | 551.55 | 0.97× | 0.99× | — | — | 302 / 35,454 / 0 | — | 0.1211 ms per entrie | sdk.compare |
| branch.fork | — · uncontended | 7 | 0.81 | 1.47 | 1.47 | 2.79 | 1.06× | 1.08× | — | — | 16 / 274 / 0 | — | — | — |
| branch.list_commits | 17–64 entries · uncontended | 2 | 0.88 | 0.88 | 0.88 | 1.27 | 0.67× | 0.67× | — | — | 70 / 1,298 / 0 | — | 0.0442 ms per entrie | — |
| branch.merge | 17–64 entries · Merged · uncontended | 1 | 2.25 | 2.25 | 2.25 | 2.25 | 1.40× | 1.40× | — | — | 35 / 517 / 0 | — | 0.0352 ms per entrie | — |
| branch.merge | >64 entries · Merged (new Commit) · uncontended | 2 | 469.95 | 469.95 | 469.95 | 702.36 | 1.03× | 1.03× | — | — | 6,983 / 752,096 / 0 | — | 2.0256 ms per entrie | branch.merge |
| branch.publish | — · uncontended | 1 | 21.12 | 21.12 | 21.12 | 21.12 | 2.19× | 2.19× | — | — | 40 / 902 / 0 | — | — | — |
| fs.apply | >512 KiB · uncontended | 1 | 50.07 | 50.07 | 50.07 | 50.07 | 1.49× | 1.49× | — | — | 209 / 18,524 / 0 | — | 0 ms per byte | commit |
| fs.apply | ≤1 KiB · contended | 3 | 11.71 | 11.71 | 11.71 | 28.21 | 0.70× | 0.59× | — | — | 199 / 14,944 / 0 | — | 0.0748 ms per byte | files.change |
| fs.apply | ≤1 KiB · uncontended | 2 | 10.35 | 10.35 | 10.35 | 21.57 | 1.01× | 1.01× | — | — | 148 / 7,605 / 0 | — | 0.0161 ms per byte | commit |
| fs.apply | ≤8 KiB · contended | 2 | 11.14 | 11.14 | 11.14 | 15.95 | 0.64× | 0.39× | — | — | 309 / 19,432 / 0 | — | 0.0105 ms per byte | commit |
| fs.apply | ≤8 KiB · uncontended | 5 | 9.16 | 10.36 | 10.36 | 12.55 | 1.01× | 0.95× | — | — | 168 / 7,301 / 0 | — | 0.0031 ms per byte | commit |
| fs.diff_files | ≤1 KiB · uncontended | 17 | 8.39 | 13.04 | 13.04 | 19.12 | 1.01× | 1.08× | — | — | 209 / 10,494 / 0 | — | 0.027 ms per byte | sdk.read |
| fs.diff_files | ≤64 KiB · contended | 8 | 10.77 | 14.73 | 14.73 | 16.93 | 0.79× | 0.86× | — | — | 310 / 14,436 / 0 | — | 0.0006 ms per byte | sdk.read |
| fs.diff_files | ≤64 KiB · uncontended | 12 | 9.31 | 11.25 | 11.25 | 12.06 | 0.96× | 0.77× | — | — | 188 / 10,733 / 0 | — | 0.0006 ms per byte | sdk.read |
| fs.diff_files | ≤8 KiB · uncontended | 11 | 9.48 | 10.81 | 10.81 | 13.23 | 1.10× | 0.89× | — | — | 199 / 10,998 / 0 | — | 0.0036 ms per byte | sdk.read |
| fs.glob | 1 files · uncontended | 2 | 1.64 | 1.64 | 1.64 | 2.06 | 0.56× | 0.56× | — | — | 34 / 2,211 / 0 | — | 1.641 ms per file | — |
| fs.glob | 17–64 files · contended | 3 | 8.04 | 8.04 | 8.04 | 8.18 | 1.00× | 0.97× | — | — | 118 / 16,071 / 0 | — | 0.1547 ms per file | — |
| fs.glob | 17–64 files · uncontended | 6 | 8.61 | 9.03 | 9.03 | 11.31 | 1.45× | 1.52× | — | — | 137 / 15,961 / 0 | — | 0.1613 ms per file | — |
| fs.glob | 2–4 files · uncontended | 2 | 3.30 | 3.30 | 3.30 | 4.00 | 1.12× | 0.81× | — | — | 53 / 4,717 / 0 | — | 1.0008 ms per file | — |
| fs.glob | 5–16 files · contended | 3 | 4.09 | 4.09 | 4.09 | 4.95 | 1.30× | 1.30× | — | — | 80 / 7,488 / 0 | — | 0.4823 ms per file | — |
| fs.glob | 5–16 files · uncontended | 12 | 3.71 | 6.10 | 6.10 | 6.17 | 0.90× | 1.07× | — | — | 73 / 6,472 / 0 | — | 0.3862 ms per file | — |
| fs.glob | >64 files · contended | 3 | 4.77 | 4.77 | 4.77 | 6.25 | 0.65× | 0.65× | — | — | 131 / 8,771 / 0 | — | 0.0179 ms per file | — |
| fs.glob | >64 files · uncontended | 15 | 4.34 | 9.21 | 9.21 | 10.71 | 0.56× | 0.40× | — | — | 59 / 5,357 / 0 | — | 0.0162 ms per file | — |
| fs.grep | 17–64 files · contended | 4 | 11.56 | 15.15 | 15.15 | 15.35 | 1.13× | 1.48× | — | — | 322 / 15,842 / 0 | — | 0.2952 ms per file | sdk.lines |
| fs.grep | 17–64 files · uncontended | 6 | 12.54 | 17.24 | 17.24 | 18.30 | 1.32× | 1.01× | — | — | 267 / 14,098 / 0 | — | 0.2842 ms per file | sdk.lines |
| fs.grep | 2–4 files · contended | 2 | 4.60 | 4.60 | 4.60 | 5.89 | 1.04× | 1.04× | — | — | 105 / 6,728 / 0 | — | 2.298 ms per file | sdk.lines |
| fs.grep | 2–4 files · uncontended | 1 | 4.52 | 4.52 | 4.52 | 4.52 | 1.05× | 1.01× | — | — | 80 / 5,609 / 0 | — | 2.26 ms per file | sdk.lines |
| fs.grep | 5–16 files · contended | 1 | 4.58 | 4.58 | 4.58 | 4.58 | 0.90× | 0.90× | — | — | 102 / 6,754 / 0 | — | 0.7635 ms per file | sdk.lines |
| fs.grep | 5–16 files · uncontended | 11 | 7.53 | 10.81 | 10.81 | 11.77 | 1.40× | 1.02× | — | — | 142 / 9,695 / 0 | — | 0.7422 ms per file | sdk.lines |
| fs.grep | >64 files · contended | 6 | 24.12 | 25.30 | 25.30 | 49.98 | 0.93× | 0.67× | — | — | 451 / 26,576 / 0 | — | 0.0046 ms per file | sdk.lines |
| fs.grep | >64 files · uncontended | 16 | 23.17 | 43.47 | 43.47 | 57.60 | 1.04× | 0.93× | — | — | 582 / 25,747 / 0 | — | 0.1019 ms per file | sdk.lines |
| fs.list | 1 entries · contended | 1 | 3.48 | 3.48 | 3.48 | 3.48 | no baseline | no baseline | — | — | 100 / 6,512 / 0 | — | 3.48 ms per entrie | — |
| fs.list | 1 entries · uncontended | 1 | 2.45 | 2.45 | 2.45 | 2.45 | 0.67× | 0.67× | — | — | 42 / 3,327 / 0 | — | 2.45 ms per entrie | — |
| fs.list | 17–64 entries · contended | 6 | 3.76 | 4.99 | 4.99 | 8.26 | 0.72× | 0.70× | — | — | 69 / 6,620 / 0 | — | 0.1709 ms per entrie | — |
| fs.list | 17–64 entries · uncontended | 18 | 4.35 | 7.37 | 7.37 | 7.78 | 1.04× | 0.80× | — | — | 60 / 5,378 / 0 | — | 0.0871 ms per entrie | — |
| fs.list | 2–4 entries · contended | 2 | 4.10 | 4.10 | 4.10 | 5.81 | 1.45× | 1.45× | — | — | 84 / 6,186 / 0 | — | 2.052 ms per entrie | — |
| fs.list | 2–4 entries · uncontended | 3 | 3.24 | 3.24 | 3.24 | 3.54 | 1.08× | 1.07× | — | — | 47 / 5,105 / 0 | — | 0.884 ms per entrie | — |
| fs.list | 5–16 entries · contended | 1 | 3.25 | 3.25 | 3.25 | 3.25 | 0.64× | 0.29× | — | — | 58 / 6,335 / 0 | — | 0.361 ms per entrie | — |
| fs.list | 5–16 entries · uncontended | 16 | 3.55 | 4.86 | 4.86 | 4.98 | 0.95× | 0.71× | — | — | 55 / 5,351 / 0 | — | 0.362 ms per entrie | — |
| fs.read | ≤1 KiB · contended | 1 | 3.78 | 3.78 | 3.78 | 3.78 | 0.96× | 0.96× | — | — | 64 / 4,936 / 0 | — | 0.0051 ms per byte | sdk.lines |
| fs.read | ≤1 KiB · uncontended | 14 | 3.23 | 4.35 | 4.35 | 4.62 | 0.99× | 1.04× | — | — | 61 / 4,402 / 0 | — | 0.004 ms per byte | sdk.lines |
| fs.read | ≤64 KiB · uncontended | 2 | 2.99 | 2.99 | 2.99 | 3.08 | 1.12× | 1.12× | — | — | 62 / 3,457 / 0 | — | 0.0003 ms per byte | sdk.lines |
| fs.read | ≤8 KiB · contended | 8 | 3.32 | 4.63 | 4.63 | 4.85 | 0.92× | 0.58× | — | — | 83 / 5,494 / 0 | — | 0.0011 ms per byte | sdk.lines |
| fs.read | ≤8 KiB · uncontended | 24 | 2.80 | 6.02 | 7.36 | 12.69 | 0.90× | 0.69× | — | — | 56 / 3,324 / 0 | — | 0.001 ms per byte | sdk.lines |
| fs.rm | 1 files · contended | 21 | 11.80 | 17.67 | 17.67 | 22.43 | 0.74× | 0.70× | — | — | 330 / 20,459 / 0 | — | 11.8 ms per file | commit |
| fs.rm | 1 files · uncontended | 87 | 8.62 | 14.92 | 35.00 | 35.42 | 0.94× | 0.84× | — | — | 161 / 8,812 / 0 | — | 8.615 ms per file | commit |
| fs.stat | ≤1 KiB · contended | 1 | 3.71 | 3.71 | 3.71 | 3.71 | 1.16× | 1.16× | — | — | 105 / 5,436 / 0 | — | 0.0073 ms per byte | — |
| fs.stat | ≤1 KiB · uncontended | 13 | 3.03 | 4.05 | 4.05 | 4.89 | 0.99× | 0.86× | — | — | 49 / 3,968 / 0 | — | 0.0071 ms per byte | — |
| fs.stat | ≤512 KiB · contended | 1 | 2.63 | 2.63 | 2.63 | 2.63 | 0.65× | 0.65× | — | — | 39 / 2,978 / 0 | — | 0 ms per byte | — |
| fs.stat | ≤512 KiB · uncontended | 1 | 2.79 | 2.79 | 2.79 | 2.79 | 0.91× | 0.88× | — | — | 48 / 2,896 / 0 | — | 0 ms per byte | — |
| fs.stat | ≤64 KiB · contended | 3 | 3.23 | 3.23 | 3.23 | 4.21 | 1.29× | 1.29× | — | — | 69 / 5,133 / 0 | — | 0.0003 ms per byte | — |
| fs.stat | ≤64 KiB · uncontended | 9 | 2.68 | 4.00 | 4.00 | 5.16 | 0.99× | 0.89× | — | — | 50 / 3,759 / 0 | — | 0.0002 ms per byte | — |
| fs.stat | ≤8 KiB · contended | 5 | 3.30 | 3.78 | 3.78 | 5.25 | 1.28× | 1.29× | — | — | 75 / 7,429 / 0 | — | 0.0008 ms per byte | — |
| fs.stat | ≤8 KiB · uncontended | 15 | 2.49 | 3.35 | 3.35 | 3.64 | 0.97× | 0.93× | — | — | 52 / 3,321 / 0 | — | 0.0007 ms per byte | — |
| fs.write | >512 KiB · contended | 1 | 56.49 | 56.49 | 56.49 | 56.49 | 3.27× | 3.27× | — | — | 1,102 / 63,682 / 0 | — | 0.0001 ms per byte | commit |
| fs.write | >512 KiB · uncontended | 5 | 15.53 | 21.23 | 21.23 | 25.04 | 1.24× | 1.59× | — | — | 173 / 6,844 / 0 | — | 0 ms per byte | commit |
| fs.write | ≤1 KiB · contended | 42 | 17.31 | 103.88 | 124.17 | 161.87 | 0.98× | 0.89× | — | — | 351 / 20,951 / 0 | — | 0.0281 ms per byte | commit |
| fs.write | ≤1 KiB · uncontended | 159 | 8.04 | 12.70 | 22.75 | 28.61 | 0.90× | 0.58× | — | — | 157 / 7,195 / 0 | — | 0.0158 ms per byte | commit |
| fs.write | ≤512 KiB · contended | 8 | 16.31 | 24.03 | 24.03 | 25.15 | 0.83× | 0.27× | — | — | 271 / 19,548 / 0 | — | 0.0002 ms per byte | files.change |
| fs.write | ≤512 KiB · uncontended | 26 | 10.17 | 16.48 | 17.38 | 53.46 | 0.89× | 0.66× | — | — | 145 / 6,750 / 0 | — | 0.0001 ms per byte | files.change |
| fs.write | ≤64 KiB · contended | 78 | 12.98 | 30.34 | 54.52 | 102.25 | 0.86× | 0.63× | — | — | 331 / 18,598 / 0 | — | 0.0009 ms per byte | files.change |
| fs.write | ≤64 KiB · uncontended | 261 | 9.18 | 14.91 | 25.39 | 35.75 | 1.05× | 0.80× | — | — | 161 / 7,267 / 0 | — | 0.0006 ms per byte | commit |
| fs.write | ≤8 KiB · contended | 174 | 12.67 | 54.05 | 92.77 | 105.21 | 0.92× | 1.42× | — | — | 306 / 17,036 / 0 | — | 0.0051 ms per byte | commit |
| fs.write | ≤8 KiB · uncontended | 570 | 7.82 | 14.11 | 19.33 | 46.18 | 0.93× | 0.80× | — | — | 149 / 6,899 / 0 | — | 0.0035 ms per byte | commit |
| operator.store.stats | — · uncontended | 1 | 0.77 | 0.77 | 0.77 | 0.77 | 1.05× | 1.05× | — | — | 3 / 61 / 0 | — | — | — |
| sandbox.commit | 0 files · Committed · contended | 26 | 35.46 | 49.24 | 51.99 | 54.48 | 1.12× | 0.99× | — | — | 509 / 43,333 / 0 | — | — | commit |
| sandbox.commit | 0 files · Committed · uncontended | 70 | 29.98 | 59.78 | 91.19 | 272.50 | 1.10× | 1.53× | — | — | 368 / 27,174 / 0 | — | — | commit |
| sandbox.commit | 0 files · UpToDate · contended | 8 | 3.14 | 3.86 | 3.86 | 4.15 | 0.83× | 0.69× | — | — | 6 / 71 / 0 | — | — | observe.after |
| sandbox.commit | 0 files · UpToDate · uncontended | 26 | 3.82 | 5.33 | 6.56 | 8.39 | 1.02× | 0.91× | — | — | 6 / 71 / 0 | — | — | observe.after |
| sandbox.commit | 1 files · Committed · contended | 4 | 19.04 | 22.14 | 22.14 | 43.02 | 1.86× | 1.22× | — | — | 248 / 11,802 / 0 | — | 19.037 ms per file | commit |
| sandbox.commit | 1 files · Committed · uncontended | 12 | 8.70 | 11.76 | 11.76 | 12.01 | 0.86× | 0.90× | — | — | 107 / 3,999 / 0 | — | 8.704 ms per file | commit |
| sandbox.commit | 1 files · Conflict · contended | 1 | 281.54 | 281.54 | 281.54 | 281.54 | 1.02× | 1.02× | — | — | 14,082 / 506,266 / 0 | — | 281.537 ms per file | commit |
| sandbox.commit | 17–64 files · Committed · uncontended | 1 | 48.89 | 48.89 | 48.89 | 48.89 | no baseline | no baseline | — | — | 1,198 / 51,777 / 0 | — | 2.8759 ms per file | commit |
| sandbox.commit | 2–4 files · Committed · contended | 9 | 20.89 | 40.71 | 40.71 | 45.53 | 1.35× | 1.38× | — | — | 225 / 25,399 / 0 | — | 6.9623 ms per file | commit |
| sandbox.commit | 2–4 files · Committed · uncontended | 7 | 11.79 | 18.81 | 18.81 | 23.27 | 1.18× | 1.54× | — | — | 155 / 7,198 / 0 | — | 4.992 ms per file | commit |
| sandbox.commit | 5–16 files · Committed · contended | 4 | 21.35 | 21.81 | 21.81 | 29.26 | 0.53× | 0.54× | — | — | 351 / 19,568 / 0 | — | 2.2803 ms per file | commit |
| sandbox.commit | 5–16 files · Committed · uncontended | 1 | 20.82 | 20.82 | 20.82 | 20.82 | 1.25× | 1.21× | — | — | 388 / 24,785 / 0 | — | 1.8928 ms per file | commit |
| sandbox.commit | — · Committed · contended | 3 | 385.96 | 385.96 | 385.96 | 401.14 | 2.92× | 2.92× | — | — | 3,007 / 139,655 / 0 | — | — | commit |
| sandbox.commit | — · Committed · uncontended | 9 | 90.93 | 1419.24 | 1419.24 | 16477.55 | 0.85× | 0.99× | — | — | 366 / 23,632 / 0 | — | — | commit |
| sandbox.exec | 0 files · contended | 154 | 49.22 | 1256.40 | 4516.61 | 4679.14 | 0.07× | 1.20× | — | — | — | 4948.70 | — | — |
| sandbox.exec | 0 files · uncontended | 142 | 39.22 | 804.10 | 1131.00 | 12023.71 | 1.05× | 1.04× | — | — | — | 4868.70 | — | — |
| sandbox.exec | 1 files · contended | 19 | 41.02 | 70.37 | 70.37 | 73.77 | 1.13× | 1.22× | — | — | — | 4.30 | 41.024 ms per file | — |
| sandbox.exec | 1 files · uncontended | 40 | 39.90 | 67.03 | 68.32 | 70.51 | 1.10× | 1.06× | — | — | — | 4.30 | 39.896 ms per file | — |
| sandbox.exec | 17–64 files · contended | 11 | 42.47 | 62.28 | 62.28 | 72.67 | 0.63× | 0.90× | — | — | — | 20.10 | 2.4981 ms per file | — |
| sandbox.exec | 17–64 files · uncontended | 9 | 83.19 | 111.00 | 111.00 | 128.31 | 1.05× | 1.40× | — | — | — | 20.10 | 4.1594 ms per file | — |
| sandbox.exec | 2–4 files · contended | 26 | 36.02 | 56.10 | 60.38 | 60.79 | 0.85× | 0.84× | — | — | — | 8.70 | 15.394 ms per file | — |
| sandbox.exec | 2–4 files · uncontended | 32 | 38.46 | 52.82 | 57.87 | 58.42 | 0.84× | 0.79× | — | — | — | 10 | 15.3395 ms per file | — |
| sandbox.exec | 5–16 files · contended | 27 | 40.46 | 75.80 | 76.27 | 78.93 | 0.80× | 1.08× | — | — | — | 21.40 | 4.496 ms per file | — |
| sandbox.exec | 5–16 files · uncontended | 17 | 62.53 | 76.19 | 76.19 | 172.10 | 0.98× | 0.90× | — | — | — | 30 | 5.5869 ms per file | — |
| sandbox.exec | — · contended | 14 | 4114.88 | 34456.90 | 34456.90 | 34695.62 | 0.41× | 1.09× | — | — | — | 59212.10 | — | — |
| sandbox.exec | — · uncontended | 26 | 606.68 | 34710.57 | 35190.81 | 45556.09 | 1.74× | 1.89× | — | — | — | 46844.10 | — | — |
| sandbox.mount | — · contended | 62 | 12.29 | 20.85 | 25.96 | 38.51 | 1.02× | 0.95× | — | — | 63 / 1,686 / 82 | — | — | sandbox.mount.bind |
| sandbox.mount | — · uncontended | 117 | 10.46 | 17.76 | 24.77 | 36.90 | 0.95× | 1.02× | — | — | 45 / 1,362 / 82 | — | — | observe.after |
| sandbox.status | — · contended | 1 | 5.49 | 5.49 | 5.49 | 5.49 | 0.84× | 0.84× | — | — | 0 / 0 / 0 | — | — | observe.after |
| sandbox.status | — · uncontended | 3 | 3.67 | 3.67 | 3.67 | 48.86 | 0.80× | 0.57× | — | — | 0 / 0 / 0 | — | — | observe.after |
| sandbox.unmount | — · contended | 49 | 11.93 | 18.48 | 19.73 | 20.47 | 0.87× | 0.80× | — | — | 0 / 0 / 0 | — | — | observe.after |
| sandbox.unmount | — · uncontended | 130 | 13.62 | 32.59 | 233.05 | 323.08 | 0.90× | 1.15× | — | — | 0 / 0 / 0 | — | — | observe.after |

| Method | Category | Calls | Bytes in | Bytes out | Files / entries | Outcomes |
| --- | --- | --- | --- | --- | --- | --- |
| branch.diff_branches | branch | 13 | 0.0 KiB | 697.0 KiB | 3,069 | ok 13 |
| branch.diff_commits | branch | 403 | 0.0 KiB | 22.2 MiB | 74,901 | ok 403 |
| branch.fork | branch | 23 | 0.0 KiB | 0.0 KiB | 0 | Forked 23 |
| branch.list_commits | project | 9 | 0.0 KiB | 85.3 KiB | 143 | ok 9 |
| branch.merge | branch | 8 | 0.0 KiB | 0.0 KiB | 0 | Merged 8 |
| branch.publish | branch | 1 | 0.0 KiB | 0.0 KiB | 0 | Added 1 |
| fs.apply | fs | 25 | 2.1 MiB | 0.0 KiB | 36 | Committed 25 |
| fs.diff_files | fs | 53 | 0.0 KiB | 458.5 KiB | 45 | Text 42, NoSuchPath 8, Equal 3 |
| fs.glob | fs | 56 | 0.0 KiB | 60.3 KiB | 751 | ok 56 |
| fs.grep | fs | 57 | 0.0 KiB | 282.7 KiB | 1,009 | ok 57 |
| fs.list | fs | 60 | 0.0 KiB | 352.6 KiB | 2,333 | ok 60 |
| fs.read | fs | 54 | 0.0 KiB | 143.5 KiB | 54 | ok 54 |
| fs.rm | fs | 108 | 0.0 KiB | 0.0 KiB | 108 | Committed 108 |
| fs.stat | fs | 56 | 0.0 KiB | 12.7 KiB | 56 | ok 56 |
| fs.write | fs | 1,324 | 16.2 MiB | 0.0 KiB | 1,324 | Committed 1324 |
| operator.store.stats | operator | 1 | 0.0 KiB | 0.0 KiB | 0 | ok 1 |
| sandbox.commit | sandbox | 186 | 0.0 KiB | 0.0 KiB | 0 | Committed 151, UpToDate 34, Conflict 1 |
| sandbox.exec | sandbox | 527 | 2.2 MiB | 5.3 MiB | 0 | exit:0 523, exit:2 3, exit:1 1 |
| sandbox.mount | sandbox | 189 | 0.0 KiB | 0.0 KiB | 0 | Mounted 189 |
| sandbox.status | sandbox | 4 | 0.0 KiB | 0.0 KiB | 0 | ok 4 |
| sandbox.unmount | sandbox | 189 | 0.0 KiB | 0.0 KiB | 0 | Unmounted 189 |

### C. Scale probes

Binary: daemon `c41a86d23822`.

Load average (1-min, runner (Docker VM kernel)): start 0.17 · end 1.49.

| Probe | ms (median) | Samples | Load 1-min | Counters (first sample) |
| --- | --- | --- | --- | --- |
| stat | 2.123 | 18.071 · 2.262 · 2.123 · 1.404 · 1.19 | 2.04–2.04 | statements 34, vm_steps 1118, fullscan_steps 0, sorts 0, returned_rows 91 |
| read | 2.056 | 1.967 · 3.032 · 2.256 · 1.886 · 2.056 | 2.04–2.04 | statements 19, vm_steps 794, fullscan_steps 0, sorts 0, returned_rows 76 |
| list_small | 1.666 | 1.902 · 1.638 · 1.856 · 1.373 · 1.666 | 2.04–2.04 | statements 19, vm_steps 803, fullscan_steps 0, sorts 0, returned_rows 76 |
| list_largest | 13.83 | 17.525 · 13.365 · 12.962 · 13.83 · 15.334 | 2.04–2.04 | statements 212, vm_steps 28653, fullscan_steps 0, sorts 0, returned_rows 2643 |
| grep_scoped | 1.735 | 2.618 · 1.612 · 1.543 · 1.982 · 1.735 | 2.04–2.04 | statements 24, vm_steps 949, fullscan_steps 0, sorts 0, returned_rows 85 |
| glob_scoped | 1.608 | 1.608 · 1.39 · 1.922 · 1.657 · 1.185 | 2.04–2.04 | statements 18, vm_steps 782, fullscan_steps 0, sorts 0, returned_rows 75 |
| grep_tree | 6554.446 | 6554.446 · 6594.181 · 6280.256 · 6355.91 · 6605.581 | 1.72–1.88 | statements 66678, vm_steps 4844078, fullscan_steps 0, sorts 0, returned_rows 477709 |
| glob_tree | 12.71 | 14.554 · 12.183 · 12.987 · 11.82 · 12.71 | 1.72–1.72 | statements 169, vm_steps 23333, fullscan_steps 0, sorts 0, returned_rows 2300 |
| diff_files | 5.776 | 5.651 · 5.86 · 5.776 · 5.706 · 5.837 | 1.72–1.72 | statements 96, vm_steps 4648, fullscan_steps 0, sorts 0, returned_rows 456 |
| list_commits | 0.881 | 2.155 · 0.881 · 0.884 · 0.781 · 0.783 | 1.72–1.72 | statements 70, vm_steps 1298, fullscan_steps 0, sorts 0, returned_rows 52 |
| diff_commits | 3.793 | 4.743 · 3.793 · 4.054 · 3.45 · 3.184 | 1.72–1.72 | statements 68, vm_steps 2421, fullscan_steps 0, sorts 0, returned_rows 271 |
| fork | 1.796 | 2.846 · 1.273 · 2.906 · 1.024 · 1.796 | 1.72–1.72 | statements 16, vm_steps 274, fullscan_steps 0, sorts 0, returned_rows 7 |
| merge | 35.414 | 40.817 · 34.397 · 35.415 · 35.256 · 35.414 | 1.72–1.72 | statements 523, vm_steps 23791, fullscan_steps 0, sorts 0, returned_rows 1808 |
| oneshot_mount_unmount | 20.407 | 25.519 · 20.407 · 22.878 · 17.76 · 15.247 | 1.72–1.72 | statements 68, vm_steps 2338, fullscan_steps 82, sorts 2, returned_rows 227 |
| oneshot_commit | 70.906 | 78.061 · 70.906 · 77.648 · 69.832 · 70.718 | 1.72–1.72 | statements 197, vm_steps 12834, fullscan_steps 82, sorts 2, returned_rows 974 |
| oneshot_exec | — |  ·  ·  ·  ·  | 1.72–1.72 | statements 0, vm_steps 0, fullscan_steps 0, sorts 0, returned_rows 0 |

### D. Storage internals

From the sealed file at snapshot r058: 433,225 pages of 4,096 B, 0 free · Commits 70,508 · Branches 1,499 · Layers 70 · compression 3.79× (canonical ÷ stored).

| Role | Objects | Canonical bytes |
| --- | --- | --- |
| 1 | 224,962 | 1.40 GiB |
| 2 | 77,739 | 1.19 GiB |
| 3 | 18,455 | 7.8 MiB |
| 4 | 52 | 10.3 KiB |
| 5 | 18,336 | 1.9 MiB |
| 6 | 197,051 | 947.4 MiB |
| 7 | 558,316 | 136.5 MiB |
| 8 | 1,716 | 501.5 KiB |
| 9 | 152,076 | 339.9 MiB |
| 10 | 75,659 | 9.3 MiB |
| 11 | 12,822 | 1.7 MiB |
| 13 | 2,537 | 208.4 KiB |

| Pack domain | Packs | Bytes |
| --- | --- | --- |
| 0 | 72,613 | 155.4 MiB |
| 1 | 76,195 | 926.5 MiB |

| Table or index | Pages | Bytes | Unused |
| --- | --- | --- | --- |
| pack | 289,646 | 1.10 GiB | 40.7 MiB |
| inode_value | 86,427 | 337.6 MiB | 6.5 MiB |
| binding_hint | 26,428 | 103.2 MiB | 9.7 MiB |
| object_location | 18,194 | 71.1 MiB | 7.5 MiB |
| commit | 5,891 | 23.0 MiB | 3.6 MiB |
| file_digest | 1,707 | 6.7 MiB | 773.7 KiB |
| commit_lineage | 1,515 | 5.9 MiB | 686.4 KiB |
| commit_runs | 1,475 | 5.8 MiB | 743.8 KiB |
| commit_identity | 1,085 | 4.2 MiB | 471.4 KiB |
| content_signature | 157 | 628.0 KiB | 9.7 KiB |
| branch | 66 | 264.0 KiB | 44.7 KiB |
| branch_names | 25 | 100.0 KiB | 20.0 KiB |
| branch_identity | 17 | 68.0 KiB | 9.3 KiB |
| run_merges | 9 | 36.0 KiB | 10.1 KiB |
| history_meta | 8 | 32.0 KiB | 2.1 KiB |
| sqlite_schema | 6 | 24.0 KiB | 7.7 KiB |
| layer | 5 | 20.0 KiB | 7.6 KiB |
| absorbed_heights | 4 | 16.0 KiB | 7.8 KiB |
| absorbed | 4 | 16.0 KiB | 7.8 KiB |
| layers_source | 3 | 12.0 KiB | 5.9 KiB |

### E. Stage times

**Time 388.2 s** (tooling): play 140.4 · consolidate 151.6 · verify 32.7 · probes 33.6 · tests 0.0 · seal + snapshot 13.7 · report 16.2

388.15 s tooling: prepare 1.71 · play 138.68 · consolidate 151.57 · verify 19.38 (diff_commits + full compareTree) · version walk 13.32 · probes 33.61 · metrics 1.02 · seal 1.50 · sealed figures 6.76 · snapshot copy 5.41 · report 0.58

### F. Attempts

| # | Binary | Started | Result | Reason |
| --- | --- | --- | --- | --- |
| 1 | 32eda22d657d10ba2b419652882f2be41fd2b99cbf38e3eeb32d39a19dc16d88 | 2026-10-20T10:58:28.717Z | stop | Correctness: tree 0 missing, 1 extra, 0 content, 0 mode; steps 2605/2606; conflicts 3/3; tests 30/30 equal to native; Speed: sandbox.exec — · uncontended: 1.53× baseline (no phase); not judged: fs.apply ≤1 KiB · uncontended: 4/19/11 calls (1.98×), fs.apply >512 KiB · uncontended: 1/1/1 calls (1.76×), sandbox.commit 5–16 files · Committed · uncontended: 7/4/6 calls (1.4×) (baseline class under 5 calls per range); Scaling: branch.diff_commits checkpoint statements in total (entries exponent 0.019): tree files exponent 0.535; Counters: not judged: no counters; Contended work: not judged: no contended class has 3 ranges of 5+ calls with per-call SQL over a tree that grew 1.5× (21 classes too narrow); SQL per call (sql.call); Directory share: 0.525; Node proofs: 0 pass · 0 stop · 21 NOT_RUN over 4 points |
| 2 | 32eda22d657d10ba2b419652882f2be41fd2b99cbf38e3eeb32d39a19dc16d88 | 2026-10-20T11:06:39.190Z | stop | Correctness: tree 0 missing, 1 extra, 0 content, 0 mode; steps 2605/2606; conflicts 3/3; tests 30/30 equal to native; Speed: sandbox.exec — · uncontended: 1.56× baseline (no phase); not judged: fs.apply >512 KiB · uncontended: 1/1/1 calls (2.1×), sandbox.commit 5–16 files · Committed · uncontended: 7/4/6 calls (1.39×), sandbox.exec 17–64 files · uncontended: 2/5/6 calls (1.25×) (baseline class under 5 calls per range); Scaling: branch.diff_commits checkpoint statements in total (entries exponent 0.019): tree files exponent 0.528; Counters: not judged: no counters; Contended work: not judged: no contended class has 3 ranges of 5+ calls with per-call SQL over a tree that grew 1.5× (20 classes too narrow); SQL per call (sql.call); Directory share: 0.528; Node proofs: 0 pass · 0 stop · 21 NOT_RUN over 4 points |
| 3 | c41a86d23822da1da70e03eb843938d51ddba522de5a8aa598911d3d3b24f851 | 2026-10-20T12:40:43.874Z | stop | Speed: sandbox.exec — · uncontended: 1.89× baseline (no phase); not judged: branch.publish — · uncontended: 1/1/1 calls (2.19×), fs.write >512 KiB · uncontended: 3/12/5 calls (1.59×), sandbox.commit 2–4 files · Committed · uncontended: 7/5/3 calls (1.54×), fs.apply >512 KiB · uncontended: 1/1/1 calls (1.49×), sandbox.exec 17–64 files · uncontended: 1/4/7 calls (1.4×) (baseline class under 5 calls per range); Scaling: insufficient same-binary points: 1 of 3 (daemon c41a86d23822); also not judged: oneshot_exec: 1 of 3 points of probe version 1; Counters: insufficient same-binary points: 1 of 3 (daemon c41a86d23822); Contended work: not judged: no contended class has 3 ranges of 5+ calls with per-call SQL; SQL per call (sql.call); Directory share: 0.527; Range growth: 33.2 MiB; median not judged: 0 of 3 earlier ranges; Snapshot time: 5339 ms for 1461.3 MiB new; size exponent not judged (1 snapshots); Node proofs: 16 pass · 1 stop · 0 NOT_RUN over 4 points: r058-1-root end P5 |

### G. Evidence

- `~/lfs-history/metrics/range-058.a1.json`
- `~/lfs-history/metrics/range-058.a2.json`
- `~/lfs-history/metrics/range-058.a3.json`
- trace `~/lfs-history/runs/p3-main-x-c/trace/range-058.a3.jsonl` · runner log `~/lfs-history/runs/p3-main-x-c/play.log` · snapshot manifest `/Users/yifanxu/lfs-history/snapshots/range-058.json`

### H. Git internals

Seed pack: — objects, — (counted apart from lane objects).

| Lane | Objects | Index bytes |
| --- | --- | --- |
| r058-3-apps-web | 934 | 651.0 KiB |
| r058-2-packages-client | 791 | 647.7 KiB |
| r058-1-root | 211 | 644.3 KiB |

| git command | ms | lstat |
| --- | --- | --- |
| `git status --porcelain` | 557.0 | 5,233 |
| `git diff --stat` | 46.0 | 5,219 |
| `git add -f` | 43.0 | — |
| `git rm --cached` | 9.0 | — |
| `git commit` | 47.0 | 5,224 |

### I. Proof details

| Lane | Point | Proof | Result | Detail | Native cached |
| --- | --- | --- | --- | --- | --- |
| r058-3-apps-web | end | P1 | pass | — | — |
| r058-3-apps-web | end | P2 | pass | exit 0 | — |
| r058-3-apps-web | end | P3 | pass | 300 bookkeeping path(s) | — |
| r058-3-apps-web | end | P4 | pass | 231 emitted files, exit 2 | — |
| r058-3-apps-web | end | P5 | pass | 47 files | — |
| r058-3-apps-web | end | P6 | n/a | not a repair | — |
| r058-1-root | end | P1 | pass | — | — |
| r058-1-root | end | P2 | pass | exit 0 | — |
| r058-1-root | end | P3 | n/a | an install, not a refresh | — |
| r058-1-root | end | P4 | pass | 678 emitted files, exit 2 | — |
| r058-1-root | end | P5 | stop | 1 pass natively, fail on LayerFS: packages/skill/skill-local/tests/skill-local-watcher.spec.ts | — |
| r058-1-root | end | P6 | n/a | not a repair | — |
| r058-2-packages-client | end | P1 | pass | — | — |
| r058-2-packages-client | end | P2 | pass | exit 0 | — |
| r058-2-packages-client | end | P3 | pass | 0 bookkeeping path(s) | — |
| r058-2-packages-client | end | P4 | pass | 546 emitted files, exit 2 | — |
| r058-2-packages-client | end | P5 | pass | 97 files | — |
| r058-2-packages-client | end | P6 | n/a | not a repair | — |
| lead | repair | P1 | n/a | folded into P6 | — |
| lead | repair | P2 | pass | exit 0 | — |
| lead | repair | P3 | n/a | a repair, not a no-op | — |
| lead | repair | P4 | n/a | folded into P6 | — |
| lead | repair | P5 | pass | 30 files | — |
| lead | repair | P6 | pass | P1 pass, P4 pass (2381 emitted files, exit 0) | — |

### J. Conflicts by path class

No conflicts by path recorded.
