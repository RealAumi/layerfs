# fs-bench-pro workload benchmark

> **Status:** First iteration closed with failures and not-applicable cases; no release admission is established.

The [implementation spec](../../core/docs/benchmark/fs-bench-pro/implementation-spec.md)
and [rollout ledger](../../core/docs/benchmark/fs-bench-pro/ROLLOUT-LEDGER.md) define
the first iteration: port the 25 frozen v0.1.6 workload families, run each
case once, verify results and cleanup, and fix correctness bugs. No speed,
comparison or release gate is selected.

Stage 0.1 has harvested all 461 released source rows into
[the reference catalogue](baselines/v0.1.6/README.md). Stage 0.2 has moved the
working SDK runtime here and separated cluster-one and cluster-two harnesses.
The first-iteration catalogue contained all 25 original families and 273 cases. All seven batches
are truthfully closed: 192 functional/verifier/clean-close passes, 50 failed
outcomes, three actual cases unrun after failed preparation, and 28 complete
reliability cases not applicable. Source-only reliability parity preserves the
missing physical accounting and creation-profile requirements; it is not a
native or mounted proof. The [iteration completion](../../core/docs/benchmark/fs-bench-pro/ITERATION-1-COMPLETION.md)
records every case, failed or unavailable scope, limit miss, fix, decision,
source pair and production LOC. Raw receipts and claims remain append-only;
closed results are not authorization to repeat an unchanged sample.

Current issue319 owner direction retires `workspace_reliability` and its28
cases, including the engine/runtime routes and dedicated tests. The active
registry has24 families and245 unique cases. All3 `repository_history` cases
remain selectable and are NOT_RUN — set aside by owner, leaving242 cases for
the terminal campaign. Historical reliability receipts and baseline CSVs stay
unchanged. This retirement tests the current contract scope, not performance;
no failing/slow ordinary case is removed. See the
[retirement record](../../core/docs/issues/319/checks/phase11-retirement.json).

Use `bench.py build --out <fresh-results-path>`, then
`bench.py prepare empty|big64m --build <seal> --out <fresh-results-path>`.
A stage 0.4 run uses `bench.py run cluster-two/cells --case Cxx --build <seal>
--prepared <master-receipt> --out <source-fixed-run>`. Run each case under its
own checkout lock and explicit wall stop. Both masters can also be placed in
`<prepared-parent>/empty` and `<prepared-parent>/big64m` for automatic selection.
`bench.py verify <run>` reads retained independent evidence; `bench.py report
<run>` creates the two CSVs once, including all twelve registered cells.

Each `bench.py run` case has a read-only kernel observer beside it
([engine/io_observer.py](engine/io_observer.py)). It runs
[`cgroup_observer.py`](../../core/docs/issues/320/tools/cgroup_observer.py) in its
own container of the pinned image, outside every timer, and keeps its rows in
`<sample>/io-observer/`. Before the receipt is written, the receipt's
interference line declares the observer and `io_observer` records, for each
Commit, the counts of
[`commit_kernel_window.py`](../../core/docs/issues/320/tools/commit_kernel_window.py):
container I/O pressure, container dirty-page peak, VM dirty plus write-back
peak with its two limits, and container and VM pages scanned. Its `label` is
`IO_STALLED` when the container waited on I/O for more than 20% of the
observed Commit interval, else `NOT_STALLED`; `NO_COMMIT` and `UNAVAILABLE`
say why there is none. The threshold comes from four dense-rewrite samples:
unstalled 0.1% and 8.5%, stalled 38.0% and 43.7% ("Issue 321 follow-up —
Store-write stall cause" in [PROGRESS](../../core/docs/issues/320/PROGRESS.md)). The
label is diagnostic: no status, verdict or limit depends on it; `report` only
appends it to the row's tag.

Read [AGENTS.md](AGENTS.md) before changing or running the harness. It identifies
current paths, profiles, lock and test requirements. The frozen root harness
remains read-only. Durable remains disabled. All first-iteration numbers will
be raw one-sample observations with their cache eligibility, not comparisons.

The Init family uses `prepare <namespace-case>` to create and completely verify
native inputs without running Init early. `parity init_namespace --prepared
<parent> --out <fresh-results-path>` compares each of the four prepared cases
with the frozen registry, fixture digest and agent review. `run init_namespace`
selects one public Init/seal per case, a fresh Store and a separate-process
sampled reopen proof. Use `--case` to bound each invocation independently.
This host route has no daemon/FUSE counts; those observations are UNAVAILABLE.
The source is setup-warm and host cold metadata is unverified, so its raw
observations remain INELIGIBLE even if functional verification passes.

Payload preparation uses `prepare <payload-case>` to generate and fully verify
original native fixture/expected states, then provision a sealed master through
public Init/install. `parity payload_create_read --prepared <parent> --out
<fresh-results-path>` checks all eight cases. Each `run payload_create_read
--case <id>` clones its master, runs the original ordinary syscall program,
commits through the SDK, terminally unmounts, verifies a fresh published-root
mount and performs a separate offline current-format persisted proof. The
runtime's `verify-workspace` mode is an independent harness oracle over a closed
sample Store; the live daemon data path stays in-process in the shared volume.

M1 recipe-history preparation retains the pristine native source and the full
checkpoint manifests, selective scopes, summaries, generator identities and SDK
assets. Each generated checkpoint payload tree is removed after those records
are authored and checked, before sealing preparation. Its recorded `native_root`
is the former materialization path. These None-mode expected trees are separate
from actual mounted/Storage proofs: every selected measured root and its frozen
byte/metadata scope remains independently verified. Other contextual/historical
preparations retain their required native trees.

Ordinary resource guards remain root observers in the exact owned daemon
container, separate from the product's admitted nonroot Exec. The controller
uses the same Engine Exec create/start/inspect operations through a private
synchronous Python calls in the existing controller, without a host helper child. The fixed observer script,
protected Store path, actual cgroup fields, every pre-/post-Commit check and
frozen apparent/allocated/OOM/swap limits remain unchanged. Append-only attempt/completion and stdout/stderr artifacts describe the actual
remote observer argv; host PID/group and unknown remote exit remain explicit
null. One absolute allowance starts before evidence setup and covers all three
exchanges and output close. Post-write checks refuse late completion; only an
owned provisional success link is revoked, retaining its exact attempt bytes.
An acknowledged remote Exec ID is retained on failure; closing a local socket
or killing the host child does not establish remote cancellation. No request
is retried and a running/unavailable/nonzero terminal observation fails.
The helper uses one deadline across its three exchanges; the original outer
child wall stop also covers Python startup. Eight KiB stream windows retain
HTTP upgrade read-ahead and exact partial output. Observer wall remains excluded
from product time and charged to the absolute watchdog, including failures.

Topology transcripts retain every acknowledged Commit in role-local order.
Only the frozen selected payload checkpoints carry a manifest and, for M1,
the created-mode binding. Omitted checkpoints carry `-` in both scope columns;
their Commit tuples still participate in complete public Branch/History and
physical-object census checks. The independent runtime oracle enforces this
binding before selected-root Storage readback.

The native M1 verifier visits each namespace path once, using that visit's
`symlink_metadata` directly for the existing type, length, mode, timestamp,
inode-class and declared-range checks. It traverses directories without
following symlinks and verifies the complete sorted path set. It keeps the
existing path list and class maps, plus two fixed scratch buffers; it does
not retain a second whole-tree metadata snapshot.

Closed Store normalization computes the initial raw file digests during the
existing bounded scratch copy. Scratch remains an independent byte copy of
every allowed regular main/WAL/SHM file; the verifier hashes those copies
independently before SQLite opens them. It also retains the complete raw-after
hash, bounded read-only WAL backup into a separate WAL/OFF target, unchanged
absolute deadline and strict typed Storage/census readback. This removes one
raw stream read without reducing the source/copy/output identity checks.

The independent typed tree proof lazily allocates its existing two 1 MiB
payload windows once per verified root and reuses them for that root's files.
Every read still clears the observed window and compares the exact requested
byte count, including a final partial window. A membership-only proof allocates
neither payload buffer. All metadata, alias, mapping and complete inode-census
checks remain in the same verifier; no scope or cache bound changes.

Typed namespace traversal retains authenticated directory serials and acquires
each listing's inode values as one bounded batch, using the existing 128-entry
and 16,384-byte limits. It queues directories and holds only one listing page;
file values leave that page after their complete verification. Every listed
name still undergoes the existing point lookup against its authenticated parent
and must return the same serial. This retains child-level and sibling-bound
refusals that listing alone does not supply. Symlink decoding and the final
complete inode census remain unchanged. Each delivered path still passes the
existing LogicalPath validation, including its whole-path limits.

Historical access setup first creates a new complete closed original producer.
For a paired selection of that same producer, use `bench.py prepare <access-case>
--build <seal> --reuse-producer <first-access-prepared-folder> --out <fresh-path>`.
The adapter admits original source/helper/graph/custody seals, preserves the
original producer identity and installs a new independent complete Store byte
copy. This reuses setup only; each original access gets its own fresh mount,
reader and verifier, with zero performance samples and one proof attempt.
