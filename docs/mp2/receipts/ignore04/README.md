# Ignore round 2 local receipts

> **Status:** Dated review checkpoint; not release or performance qualification.

Input `941fa6252`, worktree `~/Developer/layerfs-ignore`, branch
`mp2/ignore`. All execution was on this Mac; no Docker, remote environment,
SSH, push, issue or PR. No `cxi-` Docker resources were created. No Durable Store
execution; tests use memory canonical objects, the existing disposable overlay
and cache, and authenticated localhost transport. The frozen benchmark was not
built, run or changed.

## Implemented

- Unreadable indexes use patterns with an empty tracked set, retain the stat,
  and reconcile recognized tracked paths when a readable index returns.
- Rebase prunes shared bindings on server directory removal/replacement, retaining
  local-only descendants and their ancestors. Moves retain the entire subtree.
- Server rule/index flips and retained directory identities become pending seeds.
  The next projection consumes a copy even with no local edits. Only a known
  successful publication acknowledges them. Failed projection and unacknowledged
  publication leave them available. Missing published ancestors are imposed.
- Classification uses at most one bounded placement walk per local tree, records
  all aliases and completes hardlinks beyond hint capacity. Kernel create, mkdir,
  symlink, link and rename record hints after successful mutation. READDIRPLUS
  remains unsupported, confirmed in `callbacks.rs::readdirplus`.

Current contract and limits: [ignore.md](../../ignore.md). No recovery protocol,
remount persistence, split-index reader, ctime, unmount/teardown or metadata
batching change was made.

## Failing first

| Local commit | Evidence before the corresponding fix |
| --- | --- |
| `fa7740919` | Four enabled regressions; withholding/recovery, nested pruning, rebinding, server flips, 1,000-file placement and kernel hints (`ignore-before.txt`, `hints-before.txt`) |
| `b45fe97` | Deleted nested rule must reconcile a retained directory absent from Q (`tests-after-3.txt`) |
| `afa66af` | A kept write below a retained directory must reach the next publication (`retained-write-before.txt`) |

All original assertions remain except the server-flip timing assertion explicitly
changed by the owner: equality is required after the next projection. Local bytes
are checked throughout. No tests were deleted. All four `#[ignore]` attributes
were removed.

## Results

- `tests-final.txt`: **57 scoped tests pass, none ignored**: 35 ignore/model/fault
  tests, 7 kernel-visit tests, 5 directory-link tests, 5 transport tests, and 5
  existing matcher/index unit tests. The 35-test ignore target was checked again
  after making model payload tokens distinct (`tests-provenance-final.txt`).
- Model: **200 deterministic seeds × 30 steps**. Every seed includes five server
  directory deletions, five server rule flips and five following no-op Commits,
  alongside random local and server operations. Local-only directory ancestors
  may outlive the server deletion, and server flips reconcile on the next
  projection; other kept-view checks are unchanged. Named original seeds 1, 2,
  31 and 130 keep their original generator envelope.
- Counting reader: **16 probe-directory reads for 1,000 rewrites**, versus
  **16,000** before the fix. Probe directories are not otherwise accessed by
  classification. This is a work-count regression, not a latency benchmark.
- Pending seeds survive rejected output and repeated unacknowledged projections.
  Existing remote Commit fault and actual upload rejection/lost-ack tests pass.
  Post-publication failures still retain custody and block the next Commit;
  recovery is not implemented or qualified.
- Changed-file rustfmt and whitespace checks pass. Strict Clippy fails at an
  existing `result_large_err` site in unchanged `workspace/install.rs:57`.
  Diagnostic Clippy allowing only that lint passes (`clippy-diagnostic-final.txt`);
  no source-level allowance or unrelated production cleanup was added.
- Boundary guard: the same **64 existing violations** as the input; no new
  violation. Its **50 self-tests pass**. The guard is not green.

Intermediate receipts remain intact. The first compile had a test-only Vec
conversion error (`build-before.txt`). `tests-after-1.txt` records 32 probe reads:
initial placement eagerly looked up absent rule files as well as listing each
probe; lazy rule-stack resolution removes those extra reads. `hints-after.txt`
records a test fixture collision with its pre-existing `alias`; the regression
now uses `cxi-alias`. `clippy-diagnostic.txt` found a new test-only iterator lint,
corrected using `next_back` without changing production code.

## Commands

Rust **1.98.1** on macOS, with unchanged repository ARM64 flags in
`.cargo/config.toml`, locked dependencies and worktree-local `core/target`.
Rust 1.85.1 is not installed; changes use compatible syntax, but no 1.85 build is
claimed. Selecting the remote crate enables its existing bundled SQLite feature
for the real overlay tests; no dependency or Store profile was changed.

```sh
cargo +1.98.1 test --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store -p layerfs-workspace \
  --test ignore --test kernel_visit --test directory_links --test transport --lib --no-run
timeout 60s cargo +1.98.1 test --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store -p layerfs-workspace \
  --test ignore --test kernel_visit --test directory_links --test transport --lib -- --nocapture
cargo +1.98.1 clippy --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store -p layerfs-workspace \
  --all-targets --no-deps -- -D warnings
# Diagnostic isolation only; strict Clippy remains failed.
cargo +1.98.1 clippy --manifest-path core/Cargo.toml --locked \
  -p layerfs-store-service -p layerfs-remote-store -p layerfs-workspace \
  --all-targets --no-deps -- -D warnings -A clippy::result_large_err
python3 -B core/tools/check_product_boundary.py
timeout 120s python3 -B -m unittest discover -s core/tools -p 'test_*.py'
```

Formatting uses `rustfmt +1.98.1 --check --edition 2021 --config
skip_children=true` on changed Rust files only. Tests were built before execution;
every execution had an explicit timeout of 30, 60 or 120 seconds.

## Production LOC

Counter `tools/production_loc.py` at `941fa6252`, identical `--json` method on
first-parent and staged Git archive exports. Scope: first-party core production
source/runtime SQL, SDK and dsh; tests, docs, tools and generated artifacts excluded.

| Commit | Combined before → after | Signed delta |
| --- | --- | --- |
| `fa7740919` | 108657 → 108657 | +0 |
| `b45fe97` | 108657 → 108657 | +0 |
| `afa66af` | 108657 → 108657 | +0 |
| Implementation commit containing this receipt | 108657 → 108827 | +170 |

Implementation scope subtotals: core **99748 → 99918**, SDK **2861 → 2861**,
dsh **6048 → 6048**. Reference absent (retired R9c; last counted 65,417 at tree
`498dd1917812`). Normalized production code changes are **259 added, 89 removed**
(**348 total**, net +170), within the approximately 400-line budget. Gross counts
compare nonblank/noncomment lines after the same counter's Rust/test stripping,
using `difflib.SequenceMatcher(autojunk=False)`; no Git raw-line totals are used.

Reproduce the totals by exporting `core/crates`, `sdk/js` and `dsh/packages`
with `git archive <revision>`, writing the pinned counter outside those product
paths, and running `python3 <counter> --root <export> --json`. Before committing,
count `HEAD` and `git write-tree`; confirm the resulting `HEAD^{tree}` matches
the staged snapshot. No production file was moved or excluded to reduce counts.
