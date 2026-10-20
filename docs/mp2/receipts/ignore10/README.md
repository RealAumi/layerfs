# Restore validation follow-up

Local macOS only; no Docker run or resources created. Baseline `9f8acbbbb`;
failing-first commit `fea73ceff`. Rust 1.98.1, locked dependencies; changes use
1.85-compatible syntax. No retries/reconnects added to product code.

## Findings and proof

- A well-framed LACKING error previously allowed binding the server head. Now
  binding is refused before Workspace creation, with the original error and
  `unknown: false`. An explicit caller retry restores the original local root,
  BranchSnapshot and seeds; SQLite record bytes remain identical.
- A SQLite validation query failure (injected by dropping the covering index)
  follows the same refusal/recovery contract. Actual corrupt metadata and
  missing root/leaf tests still produce definite fallback verdicts.
- A record with a trailing 32-byte manifest entry previously restored. It now
  returns `invalid-record`, the existing head-fallback result. No compatibility
  reader remains.

`failing-before.log` retains the first invocation: nine passes, three failures.
The two bind tests hit duplicate-incarnation errors during their explicit retry
because the defective first bind had unexpectedly opened a Workspace. The
harness was corrected to use a fresh Workspace ID for retry.
`failing-before-adjusted.log` then records all three intended assertion failures
against unchanged production code (nine passes). No failure receipt was removed.

## Verification

Build commands used `cargo +1.98.1 test --manifest-path core/Cargo.toml --locked`,
with `--no-run` before execution. Baseline selected `-p layerfs-remote-store
--test restore_cache`; final selected `-p layerfs-remote-store
-p layerfs-store-service --test ignore --test restore_cache --test transport`.
Every test command used `timeout 120s`, then `-- --nocapture`.

Final `tests-after.log`: **59 passed** (12 cache, five transport, 42 ignore),
including the 200 deterministic seeds × 30 operations. Formatting of the three
changed Rust files passes. Boundary self-tests: 52 passed. Boundary guard: 64
pre-existing violations, byte-for-byte identical to ignore09's guard receipt.
Strict Clippy (`--all-targets --no-deps -- -D warnings`) stops at the same three
pre-existing `result_large_err` warnings in Store service. Diagnostic Clippy
with only that lint allowed passes; both outputs are retained. No frozen
fs-bench-pro or Durable execution. Raw logs retain their original trailing blank
lines; `git diff --check` reports that receipt-only whitespace. Source/docs
whitespace checks pass.

Production LOC uses `tools/production_loc.py` pinned at `4c394e3fb`, run against
`git archive` snapshots of `core/crates`, `sdk/js`, and `dsh/packages`, excluding
tests/inline test code. Test commit: **109151 → 109151 (+0)**. Fix commit:
**109151 → 109145 (-6)** (core 100242 → 100236, SDK 2861, dsh 6048).
The production diff adds 29 code lines and removes 35; comments excluded.
Reference absent (retired R9c; last counted 65,417 at tree `498dd1917812`).
