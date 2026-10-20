# Local ignore review receipts

> **Status:** Dated review checkpoint; not release or performance qualification.

Worktree `~/Developer/layerfs-ignore`, branch `mp2/ignore`.
Input: feature `f83e912a3`, rerun documentation `77424eee8`.
All execution was on this Mac. No Docker, SSH, staging, cloud-sandbox, push, issue or PR.
No Docker resources were created; failed unit fixtures owned by this review
were removed. Global Store/Durable execution: NOT_RUN. Fault tests use the
ordinary per-Workspace MEMORY/OFF overlay; transport uses its existing cache.

## Results

See [current findings](../../ignore.md#review-findings) for severity,
file::function, scenario and named regression. The first local review commit,
`1c783ba09`, contains failing regressions and raw failure output before fixes.
The follow-up fixes only classifier rule discovery, absent tracked-path
reconciliation and directory detachment, plus the transport test socket helper.
No tests were deleted. The in-memory replay harness moved from product `src/`
to the external test target, using existing public APIs; fault tests inspect
installed local-base and history identities and subsequent driver behavior.

- `scoped-tests-final.txt`: scoped all-target tests pass; four explicit design
  regressions and three existing external/offline tests are ignored by default.
- `unresolved-final.txt`: running the four design regressions explicitly still
  fails. `server-flip-next.txt` additionally verifies the next no-op Commit is
  still wrong after the server unignores a local-only path.
- `named-seeds.txt`: named seeds 1, 2, 31 and 130. The random envelope runs
  seeds 0–199, 30 steps each, using real Content merge with disjoint server-head
  writes/removes/moves. The final full ignore target takes about one second;
  this is a test runtime observation, not a performance comparison.
- `faults-2.txt`: real remote Commit driver, definite pre-publication refusal,
  post-publication base-read failure and rebase-output failure. Definite provider
  refusal preserves the next explicit Commit; known publication failures retain
  custody and refuse it `InFlight`. Successful recovery is not implemented.
- The final transport tests exercise second-window rejection and lost reply
  after 512 acknowledged objects. Neither sends the unreachable private marker;
  both retain cache contents and quarantine the channel without another RPC.
  The blocking-listener test and original two macOS transport tests pass.
- `format.txt`: changed-file rustfmt check passes; `git diff --check` passes.
- `clippy.txt`: strict warning-denying Clippy fails on two existing
  `result_large_err` sites (`backend.rs:101`, `store_service.rs:148`).
  `clippy-diagnostic.txt` passes with only that lint allowed on the command line;
  no source allowance or unrelated cleanup was committed.
- `boundary-baseline.txt`: 74 violations at input. `boundary-final.txt`: 64
  remaining violations, all baseline; moving the replay tests removes ten.
  `boundary-self-tests.txt`: 50 tool tests pass. The guard is not green.

## Commands and build identity

Rust 1.98.1 is installed; 1.85.1 is not. Changes use 1.85-compatible syntax,
without claiming a 1.85 build. Cargo ran from the repository root with its
ARM64 flags from `.cargo/config.toml`, locked dependencies and local
`core/target`. The two packages select the remote crate's existing bundled
SQLite, required because this Mac's system SQLite is rejected by the overlay's
existing version qualification (`faults-1.txt`). No dependency or profile change.
The frozen fs-bench-pro package was not built, tested or changed.

```sh
cargo +1.98.1 test --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store --all-targets --no-run
timeout 60s cargo +1.98.1 test --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store --all-targets
# Expected FAIL: preserved design gaps, not part of the passing envelope.
timeout 30s cargo +1.98.1 test --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store --test ignore -- --ignored
cargo +1.98.1 clippy --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store --all-targets --no-deps -- -D warnings
# Diagnostic isolation only; strict Clippy remains failed.
cargo +1.98.1 clippy --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store --all-targets --no-deps \
  -- -D warnings -A clippy::result_large_err
python3 -B core/tools/check_product_boundary.py
timeout 120s python3 -B -m unittest discover -s core/tools -p 'test_*.py'
```

Changed-file formatting uses `rustfmt +1.98.1 --check --edition 2021 --config
skip_children=true` on `classify.rs`, `replay.rs`, `ignore/mod.rs`, external
`tests/ignore.rs`, `tests/ignore/faults.rs` and `tests/transport.rs`.

## Retained diagnostics

All earlier failed/intermediate receipts remain unchanged. `review-before.txt`,
`model-before.txt` and `transport-before.txt` were committed before fixes.
`hardlinks-before.txt` and `server-rule-before.txt` retain the additional open
findings. `review-after-1.txt` exposed an oracle mistake: nested negation travels
with a moved rule file. `model-merged.txt` exposed a second oracle mistake:
concurrent rename/edit is inode-based; the passing random envelope uses disjoint
server paths. `model-merged-2.txt` and `seed31-diagnostic.txt` show a third oracle
mistake: previously kept bytes can move as frozen ignored leftovers. The leak
oracle tracks unique byte provenance; exact kept path/byte equality remains a
separate assertion. These oracle diagnostics are not product bugs or passes.

## Production LOC

Counter: `tools/production_loc.py` at `77424eee8`; identical counter and source
classification on Git archive exports of the first parent and final staged tree,
using `--json`. Test-only modules, tests, tools, docs and manifests are excluded.
Scopes are `core/crates/*/src` plus shipped SQL, JavaScript SDK and dsh packages.

| Commit | Combined before → after | Signed delta | Core | SDK | dsh |
| --- | --- | --- | --- | --- | --- |
| `1c783ba09` failing evidence | 108644 → 108644 | +0 | 99735 → 99735 | 2861 → 2861 | 6048 → 6048 |
| Follow-up hardening commit containing this receipt | 108644 → 108657 | +13 | 99735 → 99748 | 2861 → 2861 | 6048 → 6048 |

Reference absent (retired R9c; last counted 65,417 at tree `498dd1917812`).
The test move is a relocation, not a production source reduction. No test was
removed; no product or third-party code was moved out of the counting scope.

Reproduce for either commit and its first parent: export `core/crates`, `sdk/js`
and `dsh/packages` with `git archive <revision>` into a temporary directory;
write `git show 77424eee8:tools/production_loc.py` outside those product paths;
run `python3 <counter> --root <export> --json`. The final staged tree is obtained
with `git write-tree` and compared against `HEAD^{tree}` after committing.
