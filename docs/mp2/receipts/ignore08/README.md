# Keyed local restore

> **Status: Local prototype implementation and qualification record.**

The owner raised the production budget to about 400 lines and removed key
leases. One live sandbox per key is the caller's responsibility. No admission,
refusal or release mechanism was added. The restore contract and CLI are in
[ignore.md](../../ignore.md).

The implementation stores the original BranchSnapshot, L, its published partner,
pending seeds and a manifest in one SQLite transaction after installation. The
manifest reuses the existing local closure walk and detects absent local leaves
and roots without LACKING calls; remote subtrees remain fetchable. It was smaller
than adding tri-state traversal/network failure handling. Last-writer replacement
keeps the complete record together. No hint, overlay, uncommitted edit, or
post-publication failure recovery is added.

## Failing-first evidence

Commit 4aa44bc holds the two failing remount/fresh-owner tests before the fix.
`unit/baseline-fail.log` retains the first fixture deadlock (temporary State lock
held across bind; explicitly terminated). `baseline-fail2.log` retains remount's
root mismatch and restart's fixture directory collision. The corrected fixture
uses fresh overlay directories; `baseline-fail3.log` has both intended root
mismatches. No production change addressed either fixture problem. The original
Docker failures remain in ignore07, unchanged.

## Mac checks

All Cargo invocations use locked dependencies and toolchain 1.98.1, preserving
1.85 compatibility. Tests were built before execution and had 60/120-second
wall limits. No test ran Durable. Exact outputs are under `unit/`.

- `all-build.log`: all targets of store-service, remote-store, daemon, bridge,
  and API compile; the frozen fs-bench-pro package was excluded.
- `final-tests.log`: 63 tests pass (41 ignore, including model 200 × 30;
  4 cache restore; 5 transport; 4 control codec; 9 mount control).
- `layout-tests.log`: 7 observed-record tests pass; the actual Request/Call/
  StoreManifest/InitialRecord sizes remain 112/120/208/208 bytes.
- Strict all-target Clippy stops at the existing pinned-1.85 unfulfilled lint
  expectation in `initial_record.rs` under 1.98.1. The diagnostic pass also
  encounters the existing constant assertion in `tests/duplex.rs`. No source
  allowance or unrelated lint edit was added. `clippy-scoped.log` passes for
  production and the affected selected tests with command-line allowances for
  `unfulfilled_lint_expectations` and existing `result_large_err` only.
- Boundary guard: 64 existing violations; its 52 self-tests pass. Fuser
  provenance passes. All ten earlier e2e scenario function ASTs are unchanged.

## Docker

The first and only full e2e on **d2fafd9eb** passed **11/11 scenarios and
185/185 checks**. `results.json`, `e2e-invocation.log`, `e2e-receipts.jsonl` and
the daemon/proxy logs retain the full run. No scenario was rerun. The ten existing
scenarios passed, followed by 35 checks in the new restart/fallback scenario.

| Case | ignore07 baseline | ignore08 |
| --- | --- | --- |
| Remount | tracked exact; ignored files missing | all four files exact |
| SIGKILL/restart, same cache, fresh process paths | tracked exact; ignored files missing | all four files exact |
| Missing local leaf | not exercised | fallback to head, reason exposed, next Commit has no private files |
| Missing local L | not exercised | same safe fallback |

The new paths are `src/restart.txt`, `.gitignore`,
`node_modules/restart/index.js`, and `target/restart.bin`; exact bytes and
presence are recorded in `facts.restart_inventory`. The missing-object checks
delete SQLite rows explicitly and exercise actual daemon creation and Commit,
not just cache-unit validation. The kept tracked edit remains present throughout.

Builds used local OrbStack, Rust 1.85.1, `CARGO_BUILD_JOBS=2`, and a fresh
`cxi-target` volume. `build/` and `tested-identities.txt` pin source/build output
and binary hashes. No product dependency was changed. The run used one
construction worker. Earlier overlay/mount startup refusals remain unchanged
in ignore07; fresh per-incarnation paths are harness setup only.

The invocation had a 120-second wall limit and completed its checks and cleanup.
The subsequent exit-file shell wrapper failed because zsh's `status` variable is
read-only; its exact error is retained in `e2e-wrapper.txt`. No rerun or replacement
receipt followed. The harness's completed JSON checks, not the outer shell exit,
establish the result. This is correctness evidence, not a performance comparison.

All `cxi-` containers and networks were removed, as were their data volumes.
Only **cxi-target** remains for Cargo reuse; see `cleanup.json`. No `ign-*`,
`cx7-*`, user container, or real environment was modified.

## Production LOC

Implementation: **108,828 → 109,088 (delta +260)**, within the raised budget.
Normalized production diff: 284 lines added, 24 removed (308 changed).
Core 99,919 → 100,179; SDK 2,861 and dsh 6,048 unchanged. Reference absent
(retired R9c; last counted 65,417 at tree 498dd1917812). Counter:
`tools/production_loc.py` pinned at 4c394e3fb, `--root <export> --json`, on
first-parent and final staged `git archive` exports of `core/crates`, `sdk/js`
and `dsh/packages`; tests, docs, harnesses and inline test items excluded.

Raw test output retains Cargo's trailing blank lines; `git diff --check` flags
four new receipt endings. Maintained Rust/Python/Markdown changes are clean.


Local commits: `4aa44bc` failing tests (+0); `d2fafd9eb` implementation (+260).
The final receipt/documentation commit is 109,088 → 109,088 (+0), counted with
the same method against its first parent. Product snapshots are unchanged by it.
Remaining limits: caller-managed key sharing, uncommitted edits discarded,
no eviction/GC, no post-publication recovery and no power-loss qualification.
Strict all-target lint/boundary blockers above remain; scoped validation passed.
