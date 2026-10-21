# Core workload benchmark routing and evidence

> **Status:** Current general guide.
> Updated 2026-10-10 for the fs-bench-pro first iteration.
>
> **Frozen and left broken (owner, 2026-10-18).** Do not edit, build, run or
> repair this harness. Since #352 F-020 its `runtime` no longer compiles
> (`ProjectApi` fork and commits, `ForkRequest`, `SandboxCreate` without
> `connect_host`); that break is accepted and its call sites are listed in the
> F-020 fix record (`core/docs/issues/352/fixes/007-a1-f020-direct-store-access.md`). Everything below is
> historical until the owner explicitly reopens it.

Read [root instructions](../../AGENTS.md), [core instructions](../../core/AGENTS.md),
[implementation spec](../../core/docs/benchmark/fs-bench-pro/implementation-spec.md),
[measurement workflow](../../docs/general/agent-measurement-policy.md),
[benchmark rules](../../docs/general/benchmark_rules.md) and
[report template](../../benchmark_agent_report.md) before changing a harness
or collecting a sample. The original owner handoff selected the 25 frozen root families,
in the spec's stage and batch order. Issue319's later owner direction selects repair/optimization and retires
`workspace_reliability`. The #319 SDK follow-up then removes 85 selected cases
and keeps all five capped edits because their oracle is stricter than the twins.
The active selection is 157 cases in [tiers.json](tiers.json): everyday 108 and
heavy 49. Three repository_history definitions remain outside both tiers and
NOT_RUN by owner direction, so the default catalogue has 160 definitions in 24
family directories. Historical 242-case receipts and frozen root definitions
remain unchanged; current tier selection supersedes their active membership.
The [rollout ledger](../../core/docs/benchmark/fs-bench-pro/ROLLOUT-LEDGER.md) records
implementation, checks, decisions, failures and outstanding work.

## Active route and profiles

The workload benchmark's single entry point is `bench.py`, implemented in the
rollout. `families/` retains the 24 original-name family directories; the two
tiers select 23 active families and exclude repository_history. Each case starts pending and needs a committed definition, parity review,
fixture and independent oracle before one sample. The engine owns machinery
once. The moved `runtime/` is the ordinary SDK/Sandbox control driver from the
working cluster-two path. It is harness code, outside production LOC.

Every new global Store is explicitly Disposable/WAL/synchronous=OFF. Durable
is `NOT_RUN — disabled by owner until explicit reauthorization`. The separate
daemon overlay is MEMORY/OFF/EXCLUSIVE. Export
`LAYERFS_CONSTRUCTION_WORKERS=1`; Init keeps its supported parallel profile.

Host Project Init seals and installs one Store file into a named Docker volume.
After installation the host is control-only: each Linux daemon directly opens
that shared Store and performs Storage/History operations in-process. No host
Server, retired SDK data route or direct protocol driver substitutes for the
public SDK. Use the pinned image digest in the spec and handoff, and verify host
source hashes inside a Linux build container before its build begins.

## Separated cluster harnesses

Cluster-one Init modules, the old runner, shared helpers and diagnostics now
live in [cluster-one/init](../cluster-one/init/); history modules in
[cluster-one/history](../cluster-one/history/); the independent component
harness in [cluster-one/storage-content](../cluster-one/storage-content/).
Closed Disposable/pre-S8 registrations are in
[cluster-one/registry](../cluster-one/registry/).

Cluster-two cells and their preparation tools now live in
[cluster-two/cells](../cluster-two/cells/), functional proofs in
[cluster-two/proofs](../cluster-two/proofs/), and closed registrations in
[cluster-two/registry](../cluster-two/registry/). Cache, platform and
passthrough subjects retain their names under cluster-two. The six old
Workspace modules and shell-package runner are in
[cluster-two/retired](../cluster-two/retired/); their mechanisms are removed and
new execution remains refused. Their presence does not establish a capability.
Owning tests moved with subjects. Historical source-gated failures and OWNER-3
passthrough provenance refusals remain visible in the ledger.

Root `benchmark/fs-bench-pro` stays the frozen workload definition and is never
edited or deleted in this iteration. Its SDK driver cannot build at HEAD after
reference retirement. Read retired product source at `reference-v0.1.6-final`
or `v0.1.6`; do not restore root crates. Closed registrations, receipts and
completion records retain their original content and hashes. Relocated tools
can be checked against their original paths at their recorded commit; a path
move does not rewrite their evidence.

## Runs and receipts

Use one sample per case and source identity, with no retry, unchanged repeat,
best-of result or hidden setup warmth. Commit registration before sampling.
Declare and enforce each cache class; unknown preconditions are INELIGIBLE.
Independent verification is outside product timers. Retain every failed,
ineligible, not-applicable and unrun case.
Every `bench.py run` case also starts the read-only kernel observer of
[engine/io_observer.py](engine/io_observer.py) and declares it in the
interference line. Its `IO_STALLED` label marks a Commit that the shared
Docker VM held on I/O; it is diagnostic and changes no verdict.

A first-iteration functional PASS needs completed work, passing verification
and clean terminal unmount. Record time, storage and exact request/owner-job/
statement counts together. A completed slow case reports EXCEEDED and is not
optimized. A watchdog expiry, wrong result, crash, hang or leaked mount is a
failure. Diagnose from retained evidence and source; a product fix needs its
external failing regression and the required host/Linux covering checks.

Raw receipts belong under gitignored
`benchmark-results/fs-bench-pro/<run>/`. Generated performance and verification
CSVs are committed under `baselines/core/`; released observations and provenance
are under `baselines/v0.1.6/`. A reference carries its actual release, topology,
clock and disposition; no ratio or comparison verdict is printed.

Build, test and measurement commands serialize under
`perl core/target/r4-locked.pl <seconds> <command>`. Every test has an explicit
wall stop at most 120 s; build Rust tests with `--no-run` first. No background
or repeat loop extends a test. Host Cargo is `+1.85.1 --locked`, with the
repository ARM64 flags. Use worktree-local Cargo targets. No CI or aggregate
pre-push gate exists. After harness changes run owning scoped tests, preserving
failures. Product changes additionally need the covering checks in core's guide.

## Kept workload tiers

The tracked tier entry point is `tier.py`: `all` is for the owner in their
terminal; agents use `next`, exactly one case per command. Missing preparation
returns the exact `bench.py prepare` command and starts no sample. Prepare that
distinct fixture under the existing bound, then invoke `next`. See
[kept fixture preparation](../../core/docs/benchmark/fs-bench-pro/PREPARED-FIXTURES.md)
for producer keys, integrity, persistent ownership, source identity and cleanup.
No script mode authorizes an unchanged retry, widened oracle, product tuning or
Durable. Case counters and all original verdicts remain visible in the journal.
