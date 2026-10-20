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

Build and first/only full e2e pending at this commit. This section will record
that run's actual result without reruns or replacing failed receipts. Builds use
OrbStack, Rust 1.85.1, `CARGO_BUILD_JOBS=2`, and `cxi-build-net`/`cxi-target`.
The run uses only `cxi-` resources and one construction worker. Restart selects
fresh overlay/mount paths while retaining its cache. The ten existing scenarios
run once, followed by keyed remount/restart and explicit missing-leaf/root
creation fallback checks. No real environment is involved.

## Production LOC

Implementation: **108,828 → 109,088 (delta +260)**, within the raised budget.
Core 99,919 → 100,179; SDK 2,861 and dsh 6,048 unchanged. Reference absent
(retired R9c; last counted 65,417 at tree 498dd1917812). Counter:
`tools/production_loc.py` pinned at 4c394e3fb, `--root <export> --json`, on
first-parent and final staged `git archive` exports of `core/crates`, `sdk/js`
and `dsh/packages`; tests, docs, harnesses and inline test items excluded.

Raw test output retains Cargo's trailing blank lines; `git diff --check` flags
four new receipt endings. Maintained Rust/Python/Markdown changes are clean.
