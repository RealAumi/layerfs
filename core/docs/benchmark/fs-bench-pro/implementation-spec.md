# fs-bench-pro implementation spec: one harness, 25 workload families

> **Status:** Proposal; target LayerFS 0.1.7; not a released contract.

Written 2026-10-10 against `main` at `84323b47a`. It describes what will be
built and in what order. It claims no implementation, measurement or
comparison. The [measurement workflow](../../../../docs/general/agent-measurement-policy.md),
[benchmark rules](../../../../docs/general/benchmark_rules.md) and
[report template](../../../../docs/general/benchmark_agent_report.md) stay binding; where
this page and they disagree, they win.

## 1. Goal

Run the workload families of the v0.1.6 benchmark against the product in
`core/`, from one harness, reproducibly from the repository, with the released
numbers beside each result as a labelled reference.

Three things are in scope:

1. Reorganize `core/benchmark/` so that workload families, cluster-one tests
   and cluster-two tests live apart.
2. Port all 25 v0.1.6 families as product-neutral case definitions.
3. Collect every released reference number into one place.

Out of scope: optimizing the product, new workload families beyond the 25,
any acceptance threshold, and re-running v0.1.6 itself (section 8 says when
that would be worth doing).

### First iteration: make it run, fix what breaks

Owner direction, 2026-10-10: the first pass through the 25 families is to
implement them, run them and fix bugs, not to optimize.

- **A case passes the first iteration when it runs to the end, its verifier
  passes and the mount ends cleanly.** Its time and storage are recorded and
  shown beside the reference, and are not judged.
- **A slow case is not a failure.** A case that exceeds its declared time
  limit is recorded with its measured wall and left alone. No limit, workload
  or cache state is changed to make it fit, and no product change is made for
  speed.
- **A wrong result, a crash, a hang or a leaked mount is a bug** and is in
  scope. Each one is diagnosed from its receipt and the source, fixed once in
  the product with a test that fails without the fix, and the affected case is
  run once at the new source. The failed receipt stays.
- **A missing capability is not a bug.** A case the product cannot express yet
  (section 10) is `not-applicable` with its reason until the capability exists.
- Speed work starts only after all seven batches have run, from the recorded
  results, as a separate task.

## 2. Where things stand

| Fact | State at `84323b47a` |
| --- | --- |
| v0.1.6 harness, `benchmark/fs-bench-pro` | 25 families. Each is `mod.rs` plus `setup.sh`, `perf.sh`, `verify.sh`, run by a Rust driver linked to the v0.1.6 SDK. It cannot build on `main` since the reference was retired; it is the definition of the tests, nothing more |
| Families with a version in core | 1 of 25: `init_namespace`. Its driver exists; it was not run for this spec |
| Core harness files | 13 family files under `core/benchmark/fs-bench-pro/families`. Seven serve cluster one. Six workspace families need drivers that were removed with the host-mediated runtime and record `NOT_RUN` |
| The one working Workspace path | `core/benchmark/fs-bench-pro/r7` with the Rust harness `core/benchmark/r7-runtime`. It produced the [timing baseline](../../issues/307/TIMING-BASELINE-20261010.md) |
| What that path depends on outside the repository | Untracked driver scripts under `core/target/`, about 360 prepared inputs under `/tmp`, two Docker master volumes. None can be rebuilt from a command today |
| Core benchmark directories | Eight siblings: `fs-bench-pro`, `fs-bench-pro-storage-content`, `r7-runtime`, `r7-tools`, `r8-tools`, `r7-passthrough`, `r7-cache`, `cluster2-platform` |
| SDK surface | `ProjectApi` init and install; `WorkspaceApi` bind, mount, commit, status, unmount, force unmount, cleanup; `SandboxApi` create, exec, status. `ProjectApi::fork` and `ProjectApi::history` are already public thin methods over the existing control requests (source correction, 2026-10-10) |

The table above is a historical source snapshot, not the current SDK contract.
The 2026-10-12 owner follow-up is implemented at the [SDK surface](../../../../docs/general/sdk.md):
Project init/fork/branches/commits, Sandbox create/close and Workspace mount/exec/
commit/status/unmount. One file per operation and base/ replace the earlier layout.
Control/recovery/observation borrows are hidden. Project commits sends the original
History request; branches alone adds an authorized request and dispatch.

The runtime uses public Workspace exec for mounted commands and the same internal
launcher for native/concurrent proof borrows. No launcher, command registration,
ordinary timeout or implicit Commit/unmount is added. Setup closes its exact
container through SDK stop/delete and independently observes deletion. Samples
retain backend Stop until strict closed Store/overlay export and telemetry are
harvested, then remove their own resources. This preserves the original readback
and count scopes; it is not a second public SDK operation or an optimization.
The historical P-1 routing below is superseded for current callers by public
ProjectApi::fork and ProjectApi::commits borrowing ManagedSandbox; raw component
channels remain internal. The original pinned source and results remain archival.

## 3. Rules the design follows

1. **A family is data and scripts. The machinery exists once.** Adding a
   family adds a directory, not Python.
2. **A case is defined once, product-neutrally:** the fixture, the operations
   and the expected final state. A driver executes the definition against a
   product.
3. **`families/` holds only the 25 v0.1.6 families**, under their original
   names. Tests written during cluster one or cluster two live in their own
   directories and are never compared with v0.1.6.
4. **Everything needed to run is rebuilt from the repository** by a command.
   Nothing depends on `/tmp` or an untracked script.
5. **A released number is a reference, not an arm.** It was measured on
   another product version, topology, clock and cache contract.
6. **Raw receipts stay out of Git.** A run writes to the gitignored
   `benchmark-results/`; only a compact result file is committed.
7. **Closed campaigns are frozen.** Their registrations, tools and receipts
   move unchanged and are not edited to fit the new layout.

## 4. Target layout

Scope: planned layout of `core/benchmark/` relative to `84323b47a`. These are
harness files, outside the scope of `tools/production_loc.py`, so no
production LOC is shown. `—` marks a path that does not exist yet.

```
core/benchmark/
  fs-bench-pro/                          (the workload benchmark)
    AGENTS.md                            (existing; updated in stage 0)
    README.md                       —    new
    bench.py                        —    new   (single entry point)
    families/                       —    new   (25 directories, section 5)
    engine/                         —    new
      cache.py                      —    new   (cache classes and their checks)
      fixtures.py                   —    new   (build and clone master volumes)
      identity.py                   —    new   (source, build, image and workload seals)
      oracle.py                     —    new   (independent verification)
      project.py                    —    new   (Init and history cases, no mount)
      receipts.py                   —    new
      reliability.py                —    new   (complete-case source applicability and refusal)
      workspace.py                  —    new   (mount, run, commit, unmount)
      recipes/                      —    new   (fixture generators)
    runtime/                             (moved from r7-runtime)
    writers/                             (existing: programs that issue exact system calls)
    baselines/                      —    new
      v0.1.6/                       —    new   (section 8)
      core/                         —    new   (two CSV files per recorded run, section 6.1)
    tests/                          —    new
      engine/                       —    new
      families/                     —    new
  cluster-one/                      —    new
    init/                                (moved: phase7_sqlite, phase7_storage, serverless_init)
    history/                             (moved: phase7_history, history_retention)
    storage-content/                     (moved from fs-bench-pro-storage-content)
    registry/                            (moved: disposable-wal-matrix, pre-s8 registrations)
    tests/                               (moved with their subjects)
  cluster-two/                      —    new
    cells/                               (moved from fs-bench-pro/r7: the C, E, K and W matrix)
    proofs/                              (moved from r8-tools)
    passthrough/                         (moved from r7-passthrough)
    cache/                               (moved from r7-cache)
    platform/                            (moved from cluster2-platform)
    registry/                            (moved: r7-optimization, r8-integrated-qualification v1 to v4, cluster-two-evidence)
    baselines/                      —    new   (the twelve cells of 2026-10-10)
    retired/                             (moved: the six dead workspace family files)
    tests/                               (moved with their subjects)
```

Supporting files keep their existing names inside these subjects. The old
`runner.py`, `campaign_disposable_init.py`, `shared/` and `diagnostics/` move
into `cluster-one/init/`; `init_namespace.py` joins the other Init modules.
The two history modules move into `cluster-one/history/`. The old
`cluster_two_evidence.py` moves into `cluster-two/registry/`. `r7-tools` files
join `cluster-two/cells/`, alongside the existing matrix modules. The retired
`shell_package.py` joins the six retired Workspace modules. The shell-package
registration joins `cluster-two/registry/`. Tests move under each cluster's
`tests/` with their existing subject directory names; storage-content's Rust
and Python tests remain inside its moved harness.

A move may adjust import/search paths, repository-relative executable and
fixture paths, relative Cargo dependencies, repository-root discovery and
checker manifest paths. These are relocation changes only; no workload,
algorithm, threshold, expected result, registration content or historical
receipt changes. Closed tools and tests that depend on removed product source
remain historical; their source availability is reported separately from
relocation verification at HEAD. Stage 0.2 runs all product-free tests that
remain applicable, preserves any pre-existing failure, and adds no replacement
product route to make a historical test run.

Root `benchmark/fs-bench-pro` is not touched. It stays the frozen v0.1.6
definition until every family is ported or declared not applicable.

## 5. A family

```
families/
  <family>/                         —    new
    family.json                     —    new   (the cases)
    workload.sh                     —    new   (what runs inside the mount)
    fixture.json                    —    cond. (only when no shared recipe fits)
```

`family.json` is the single source of truth for a family. One entry per case:

```json
{
  "family": "file_size_transition",
  "engine": "workspace",
  "cases": [
    {
      "id": "boundary-exact",
      "v016_case": "v016-boundary-exact-v1",
      "status": "pending",
      "fixture": {"recipe": "boundary-files", "seed": 1},
      "steps": [
        {"run": "workload.sh write exact", "commit": true},
        {"run": "workload.sh rewrite exact", "commit": true}
      ],
      "cache_class": "B",
      "oracle": {"scope": "full-tree", "roots": "every commit"},
      "budget": {"command_ms": 15000, "verifier_ms": 9500},
      "reference": {"release": "0.1.6", "row": "v016-boundary-exact-v1"},
      "differences": []
    }
  ]
}
```

Field rules:

- `status` is `pending`, `ported` or `not-applicable`. `not-applicable`
  needs a written reason and keeps the case visible.
- `steps` is an ordered list. A step runs a command in the mount, and may
  commit, unmount and remount, or fork. A single-command family has one step.
- `differences` lists every way the ported case departs from its v0.1.6
  definition. An empty list is a claim that there is none, and the parity
  check (section 7) is what backs it.
- `budget` copies the v0.1.6 case's own limits where they exist. No limit is
  widened to make a case fit.
- `workload.sh` uses ordinary shell and filesystem calls only. It never calls
  an SDK, never names the product, and never branches on which product it
  runs under. Exact write patterns come from the programs in `writers/`.

## 6. The engine

`bench.py` is the only entry point:

| Command | Does |
| --- | --- |
| `list` | Every family and case with its status and reference |
| `prepare <fixture>` | Builds a master volume from a recipe, seals it, records its identity |
| `build` | Locked release builds of the runtime and the daemon; records the build seal |
| `run <family> [--case <id>]` | One sample of each selected case; writes a receipt |
| `run cluster-two/cells [--case <id>]` | Stage 0.4 only: the twelve existing C cells, outside the 25-family catalogue; same phase/count contracts |
| `verify <run>` | Independent verification of a recorded run |
| `report <run>` | The report-template table and a compact result file |
| `parity <family>` | The check of section 7 |

What each module owns:

| Module | Contract |
| --- | --- |
| `fixtures` | A master is built once by host Init of a recipe's output, sealed and installed into a named volume. Every sample gets an independent byte copy. A master is never mounted for a sample |
| `workspace` | One attempted operation per phase, no retry. Phases and their clocks are those of the cluster-two matrix: setup, mount, command, commit, unmount, cleanup, verifier. Only mount, command, commit and unmount are product time |
| `project` | Init and history cases through the public `ProjectApi`, with no mount |
| `oracle` | Runs outside every timer. Compares the mounted or re-mounted result with an expected state built without the product |
| `cache` | Classes A (fresh mount, cold), B (fresh mount, warm daemon) and C (same mount, warm), each with its enforced precondition. A sample whose precondition is not met is `INELIGIBLE` |
| `identity` | Source commit and tree, product tree, build seal, binary hashes, image digest, harness tree, workload and fixture hashes. A run refuses a dirty tree |
| `receipts` | Append-only output under `benchmark-results/fs-bench-pro/<run>/`; a second sample of the same identity is refused |
| `reliability` | Exact source applicability of complete frozen failure cases; retain original obligations and refuse unavailable cases before setup or runtime work. Source-only parity never qualifies a native or mounted proof |

Fixed for every run: global Store Disposable/WAL/OFF selected explicitly,
overlay MEMORY/OFF/EXCLUSIVE, `LAYERFS_CONSTRUCTION_WORKERS=1` (Init keeps its
supported parallel profile), the pinned image by digest, one sample per case.
Durable is `NOT_RUN — disabled by owner until explicit reauthorization`.

The B/C warm-daemon or same-mount predicate is only the declared product
regime. It does not establish the cache state of still-paid OS backing,
kernel metadata or SQLite/reader work. Numeric eligibility additionally needs
independent identity-bound observations before each paid phase, with the
phase boundary and cold backing/metadata/reader state verified. A zero object
demand counter or an observation after unmount cannot supply that proof.
Unknown phase input state is `INELIGIBLE`; no cache treatment is changed to
obtain eligibility. Earlier receipts retain their original scoped labels,
with missing full qualification recorded separately in the rollout ledger.

Every result reports time and storage together, and the exact request,
owner-job and statement counts the daemon already exposes. Counts are exact
observations of that execution; a time is one sample. Kernel READ batching and
conditional probes during last-owner reclamation can change the totals of a
correct ordinary-shell workload. Counts must not be edited, normalized or
sampled repeatedly to manufacture equality.

### 6.1 Result format

`bench.py report` writes two CSV files per recorded run into
`baselines/core/<date>-<commit>/<family>/` for new parallel-family runs.
The original family name separates recorded runs that share one clean source
commit; otherwise two independent reports would collide on the same filenames.
Already recorded run directories retain their original paths and contents.
They are generated from the receipts and never filled by hand. The columns extend the v0.1.6 release tables
(`docs/release-notes/0.1.6/derive_tables.py`) with the phase split, the counts and
the reference columns of the v0.1.5 table. Times are raw nanoseconds.

The stage 0.4 `cluster-two/cells` selection uses the same two CSV schemas
under `cluster-two/baselines/<date>-<commit>/`, so cluster-two proofs remain
separate from the 25 workload families. This is an explicit route to the
existing cells, not a 26th family.

`performance.csv`, one row per case, every case of the family present:

```
family, case, v016_case, status, cache_class,
complete_wall_ns, mount_ns, command_ns, commit_ns, unmount_ns,
declared_limit_ns, limit_status,
requests, owner_jobs, statements,
store_logical_bytes, store_allocated_bytes, overlay_logical_bytes, overlay_allocated_bytes,
cleanup,
reference_release, reference_timer, reference_ns, reference_profile,
source_commit, product_tree, daemon_sha256, image, evidence, tag
```

`verification.csv`, one row per case:

```
family, case, v016_case, proof_status, proof_wall_ns, declared_limit_ns,
oracle_scope, omissions, cleanup,
source_commit, product_tree, image, evidence, tag
```

| Column | Values and meaning |
| --- | --- |
| `status` | `PASS` (ran to the end, verifier passed, mount ended cleanly), `FAIL`, `INELIGIBLE` (cache precondition not met), `NOT_RUN`, `NOT_APPLICABLE`. Verification-only performance rows use `N/A`; their actual proof or applicability disposition remains in `verification.csv`. A non-passing row keeps its reason in `tag` |
| `limit_status` | `WITHIN` or `EXCEEDED` against `declared_limit_ns`. In the first iteration this is recorded and not judged; an `EXCEEDED` row can still be `PASS` |
| `reference_*` | Copied from `baselines/v0.1.6/reference.csv`: the release, the timer it used, its value and its profile. Empty when no released number exists |
| `evidence` | Path of the receipt directory under `benchmark-results/` |
| a value a receipt does not supply | `UNAVAILABLE`, never 0 |

Verification-only selections have no performance sample: performance phase,
time, count, storage, cache, limit and status cells are `N/A`. This does not
hide a failed outcome or case inapplicability: `verification.csv` retains the
actual proof status, original proof limit and reason; absent proof timing is
`UNAVAILABLE`. An unattempted source-inapplicable selection is
`NOT_APPLICABLE`, with zero actual workload and verification attempts. Native
adapter diagnostics remain separately scoped raw evidence. They are not a
whole-case proof or a numerical performance result. Existing CSV receipts and
verdicts are unchanged by this schema clarification.

There is no ratio column. The reference was measured on another version,
topology and timer, and a printed ratio would read as a verdict the data
cannot support.

## 7. Parity with v0.1.6

"The same test" means the same fixture, the same operations and the same
expected final state. It does not mean the same harness, clock or topology.

`bench.py parity <family>` checks, per case:

1. the case names a `v016_case` that exists in the root harness;
2. the fixture recipe produces the tree the v0.1.6 setup produced, by file
   count, total bytes and a content digest, where the v0.1.6 fixture is
   deterministic;
3. the ordered operations match the v0.1.6 workload's, as a reviewed
   transcription recorded beside the case;
4. the oracle covers at least what the v0.1.6 verifier covered.

Item 3 is a review by a person or an agent, recorded with the commit of the
Rust source it was read from. It cannot be mechanical, because the v0.1.6
workloads are Rust code calling an SDK that no longer builds. Anything that
cannot match goes in `differences` with its reason. Expected examples: v0.1.6
kept the Store on the host and core keeps it in the VM; a v0.1.6 case that
called an SDK edit method must become ordinary file writes.

For a `not-applicable` case, parity verifies its exact original ID, reviewed
fixture/ordered operation/oracle declarations, complete original guards and
limits, the current clean product/source identities and the specific missing
capability with its reason and needs. It records source applicability
separately from native fixture or runtime parity. A source-applicability check
may pass while `runtime_parity` remains `NOT_RUN`; it never establishes that
the complete case verifier ran or passed. Every unavailable case remains in
both result CSVs, with zero actual attempts. All original obligations remain
required before any future ported classification; a sampled/shared/logical
counter, post-Start resource limit, partial primitive proof or reused proof
with narrower scope cannot replace them. This is the explicit applicability
route for batch 7's 26 physical-accounting and two from-creation resource-profile
gaps; it introduces no product capability or relaxed case oracle.

## 8. Reference numbers

The released records already hold more than the v0.1.6 closeout alone:

| Source | Families with a timing | Rows |
| --- | --- | --- |
| `docs/release-notes/0.1.6/benchmark-performance.csv` | 5: `branch_development`, `dedup_branch_history`, `file_size_transition`, `mixed_load_bearing`, `multi_workspace_development`. `historical_access` has six rows, all verification only | 36, of which 28 timed |
| `docs/release-notes/0.1.5/benchmark-performance.csv` | 16: `dedup_branch_history`, `dedup_cdc_locality`, `dedup_cross_file`, `dedup_workspace_reuse`, `directory_construction_traversal`, `edit_canonical_chunk_count`, `edit_length_changing`, `edit_length_preserving`, `git_tool_workflow`, `init_namespace`, `mixed_load_bearing`, `namespace_mutation`, `payload_create_read`, `store_footprint`, `tiny_file_churn`, `workspace_change_locality` | 198 |
| `docs/release-notes/0.1.5/benchmark-verification.csv` | `workspace_reliability` adds 28 verification-only rows; the other 199 rows retain the released proofs for the remaining selections | 227 total |
| No released number found | `edit_length_changing_capped`, `local_snapshot`, `repository_history`, `small_file_delta_smoke` | — |

So 19 families have a released timing: 3 only in the 0.1.6 record, 14 only in
the 0.1.5 record, 2 in both. Two more, `historical_access` and
`workspace_reliability`, have verification rows and no timing. The 0.1.5 rows
describe the v0.1.5 product, one release before the retired reference; they
are the latest released number for those families, not a v0.1.6 measurement.

The two records do not time the same thing. The 0.1.6 rows are the complete
command wall, 1.8 to 18.3 s, against a 15 s family target that three rows
exceed inside a declared allowance. The 0.1.5 rows are sums of product calls
(`pure_call_sum_ns`, `edit_commit_ns`, `layerstack_init_ns`), 7.6 ms to
16.1 s, and most carry a `WARN` disposition in that record. `reference.csv`
keeps each row's timer name and disposition so the two are never mixed.

`baselines/v0.1.6/` will hold:

| File | Content |
| --- | --- |
| `reference.csv` | One row per released case: family, case, release, timer name, value in nanoseconds, source file and row, source and product seals where recorded |
| `README.md` | Each source, its topology, clock and cache contract, and what may not be concluded from it |
| `missing.md` | Families and cases with no released number, and where else was searched |

Rows are copied, never recomputed. All 227 verification rows are retained,
including proofs for selections already in the performance source. A source
that records seconds retains that original value; decimal unit conversion
to nanoseconds is labelled and adds no precision. A side-by-side table always carries the
label "reference from release X, different topology and clock" and never
prints a ratio as a verdict.

A matched comparison needs v0.1.6 re-run from its tag on the same machine
through the same case definitions. That is a separate, optional step. It is
worth doing only for cases where a decision depends on the ratio.

## 9. Rollout

Every stage ends with scoped checks at its final source and a commit per
step. Nothing below starts a sample before its registration is committed.

### Stage 0: sort things out

| Step | Work | Done when |
| --- | --- | --- |
| 0.1 | Harvest the released numbers into `baselines/v0.1.6/` | Every row of the three source files is present with its provenance; `missing.md` lists the rest |
| 0.2 | Move-only reorganization into `fs-bench-pro`, `cluster-one`, `cluster-two` | Only the relocation path changes defined in section 4; applicable existing harness tests pass from their new locations, with historical source-gated checks retained explicitly |
| 0.3 | Catalogue: every case of the 25 families as a `pending` entry in its `family.json` | `bench.py list` shows every v0.1.6 case; the total matches the root harness's own registry |
| 0.4 | Engine built from the working cluster-two path, with `prepare` replacing the `/tmp` state, and `report` writing the tables of section 6.1 | All twelve cells run once through `bench.py` at clean source identities with independent functional verification and terminal cleanup; retain the unchanged exact comparison to the 2026-10-10 request, owner-job and statement counts. If equality fails with no identified product correctness bug, close exact reproduction as failed, record the original triples, source-backed diagnosis and remaining uncertainty, and continue the workload rollout |

The original stage 0.4 target remains exact equality, and an unequal comparison
remains `FAIL`. This closure rule does not change its checker or establish
reproduction success. In the initial attempt C10 differed by one READ/job and
two statements, and C12 by one conditional orphan-inode query, with the same
daemon binary/product tree and passing independent functional proofs. The
[rollout ledger](ROLLOUT-LEDGER.md) retains evidence and uncertainty. No
workload, kernel profile, product path, verifier, limit or counter is changed
to force the historical observation. Successful unaffected cells are retained
without re-sampling under the repository's evidence-reuse rule.

### Stages 1 to 7: the families

| Batch | Families | Engine capability added | Reference |
| --- | --- | --- | --- |
| 1, pilot | `init_namespace`, `payload_create_read`, `tiny_file_churn`, `namespace_mutation` | One mount, one workload, one Commit; the `family.json` format end to end | 0.1.5 for all four |
| 2, edits | `edit_length_preserving`, `edit_length_changing`, `edit_length_changing_capped`, `edit_canonical_chunk_count`, `small_file_delta_smoke` | Exact positional writes through `writers/` | 0.1.5 for three; none for two |
| 3, trees and tools | `directory_construction_traversal`, `git_tool_workflow`, `local_snapshot`, `workspace_change_locality` | Large namespaces and tiered sizes | 0.1.5 for three; none for `local_snapshot` |
| 4, history on one branch | `file_size_transition`, `dedup_branch_history`, `mixed_load_bearing` | A schedule of many Commits on one Workspace | 0.1.6 for all three |
| 5, branches and Workspaces | `branch_development`, `multi_workspace_development`, `historical_access` | Forks, several Workspaces at once, mounting an older commit | 0.1.6 for two; `historical_access` verification only |
| 6, dedup and storage | `dedup_cdc_locality`, `dedup_cross_file`, `dedup_workspace_reuse`, `store_footprint`, `repository_history` | Store size as a first-class result | 0.1.5 for four; none for `repository_history` |
| 7, reliability | `workspace_reliability` | Failure cases; reuse the cluster-two proofs where the scope is the same | verification only |

A batch is done when, for each of its families:

1. every case is `ported` or `not-applicable` with a reason;
2. `bench.py parity` passes, with every difference written down;
3. one sample of each ported case ran, its verifier passed and the mount
   ended cleanly; a bug found on the way is fixed under the first-iteration
   rules of section 1, and a case that still fails stays in the result as
   failed;
4. the two CSV files of section 6.1 are committed under `baselines/core/`,
   with every case of the batch present, and the batch report shows each case
   beside its reference row.

An original case whose one attempted preparation reaches its unchanged
external test ceiling cannot supply a sealed input for a sample. Retain the
preparation as `FAIL`, its actual case as `NOT_RUN` with that reason, and its
parity row as `FAIL`; do not retry, extend the stop, remove checkpoints or
claim that preparation passed. Other cases may proceed only after their own
unchanged parity checks pass. The aggregate family parity and batch closure
remain explicitly failed for the unprepared case, with both CSVs retaining
every original selection. That truthful failed closure permits the next
batch; it is not a passing done-when result. This exception applies to the
retained batch-4 `v016-mixed-exhaustive-500mb-30000-k100-v1` preparation,
which reached 120 seconds after fifteen of twenty selected native states,
and batch-5 `v016-branch-mixed-500mb-30000-k100-v1`, whose external
120-second preparation supervisor expired before known return. Its inner
process later reported a complete sealed input, but late output does not
promote the failed authorized invocation. Both failed preparations and every
late artifact stay unchanged; no individual native state error or product
correctness bug was identified, and neither case is sampled from that input.
The same failed-preparation closure also applies to batch-6 `repository_history`
`deepseek-full`: its one unchanged 120-second native-input preparation expired
after the 157 selected checkpoint directories and partial `fixture.json` were
written, before the sealed `prepared.json` and resource claim existed. Those
partial native outputs do not establish passing preparation or authorize an
actual history sample. Retain preparation `FAIL`, actual case `NOT_RUN` and
aggregate parity `FAIL`; independently prepared and parity-passing cases may
continue once. No preparation retry, deadline extension or late-output
promotion is permitted.

## 10. Prerequisites and open decisions

| ID | Question | Blocks | Recommendation |
| --- | --- | --- | --- |
| P-1 | Source correction: `ProjectApi::fork` and `ProjectApi::history` already exist in `core/crates/layerfs-api/sdk/src/project/history.rs`, exported by `project/mod.rs` at the handed-over product tree | Batch 5 | Reuse and verify these existing thin SDK methods when batch 5 is reached; do not duplicate them or drive the control protocol from the harness. No product addition is needed for P-1 |
| P-2 | Source correction: direct bind takes a Branch; both the original v0.1.6 access driver and current `ForkSource::Commit` select an ancestor by Fork-then-mount | `historical_access` | Verify the existing public Fork/History route in batch 5 before sampling. The original access lane already creates a separate access Branch, so do not label that Branch as an added topology difference. Preserve source-Branch ancestry membership, selected roots and producer heads; if the existing route cannot express a case, retain it as `not-applicable` rather than adding a feature |
| P-3 | Workloads that used v0.1.6 SDK edit calls have no shell equivalent yet | Batch 2 | Express them as ordinary writes through `writers/` and record the difference |
| P-4 | Old registrations pin harness files by path and hash; after the move they can only be re-checked at their own commit | Stage 0.2 | Accept; they are closed |
| P-5 | The largest v0.1.6 fixtures are 500 MB and 30,000 files with 100 Commits; some cases exceeded 15 s on v0.1.6 itself | Batches 4 and 5 | Keep the v0.1.6 case's own declared limit; a case that cannot fit is recorded with its measured wall, not shrunk |
| P-6 | One Workspace per tool call is the product's main mode and none of the 25 families measures it | — | Owner decision whether to add families beyond the 25; not part of this spec |
| P-7 | Open issues #230, #232, #233 and #235 describe an earlier version of this work | — | Close them against this spec once stage 0 lands |

## 11. What this spec does not establish

- That any family can be ported without differences; section 7 exists
  because some cannot.
- That core is faster or slower than v0.1.6. No number here is a comparison.
- That the 25 families cover the product's main use; see P-6.
- Any acceptance threshold, cold-cache claim or release gate.
