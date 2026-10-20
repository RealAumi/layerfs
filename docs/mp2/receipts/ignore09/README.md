# Ignore09: bounded Commit persistence and process-crash cache safety

> **Status: local prototype diagnostics and correctness evidence; no release claim.**

The manifest regression is confirmed and fixed. A keyed Commit serializes only
its original BranchSnapshot, L, published partner and pending seeds. It neither
walks objects nor rewrites an object manifest. Restore performs the full local
closure walk once, using an `object_presence` covering index. Payload leaves,
symlinks and directory leaves require no body read; metadata carrying references
is read and authenticated. Absent references go through one batched LACKING phase,
windowed at the existing 4096-ID wire limit. Server-missing objects cause fallback.
Old manifest-bearing records remain readable; their suffix is no longer trusted
as the object inventory. Payload authentication remains on demand.

A local checkpoint-write failure leaves publication/install successful, retains
the older atomic record and reports `restore: save-failed`. The Workspace can
Commit again. Tests also restore that older checkpoint and merge newer tracked
content correctly while retaining only the older ignored content.

The cache profile is inherited from the **mp2/remote-store base**, in
`core/crates/layerfs-remote-store/src/cache.rs`; the change affects remote clients
with and without ignore. MEMORY journaling was unsuitable once the cache held the
only copy of local objects. It now uses **WAL / synchronous=OFF**. WAL provides
process-crash consistency; OFF does not promise survival or consistency after
power loss or an OS crash. Preserve the cache database and WAL together. No
Store/overlay profile, teardown, recovery protocol, GC or batching change was made.
Sources: [SQLite synchronous](https://www.sqlite.org/pragma.html#pragma_synchronous),
[MEMORY journal corruption](https://www.sqlite.org/howtocorrupt.html).

## Frozen method and identities

[plan.md](plan.md) registers order, sample counts, timing and the noise screen.
The owner's ten-sample requirement overrides the repository's usual single-sample
policy. [harness-scope.json](harness-scope.json) proves the four measurement helper
ASTs stayed identical across all cohorts; the later kill-loop function does not
change them. The driver uses independent Branches, so these are one-file Commits,
not moved-head merges. Earlier ignore e2e scenarios are unchanged.

| Field | Value |
| --- | --- |
| Fixture | Phase 8 SHAKE recipe over retained Phase 4 full manifest |
| Size | 30,000 ignored files, 211,730,666 bytes, 9,470 directories |
| Manifest SHA-256 | df3379f51945f00bcccf5d83c6329f4b4e732cd431771ac87db0030923876b41 |
| Topology | This Mac, OrbStack Linux/arm64, 0 ms **added** delay; actual network RTT not zero |
| Cache | Phase 8 hot, already mounted, initial Commit populated local caches; OS residency uncontrolled |
| Input setup | One deterministic host fixture, independent copies to each arm's mount |
| Source | baseline d2fafd9eb binaries; small-record a2dfc4fe0; WAL a2dfc4fe0 + retained one-line source.patch |
| Build | Rust 1.85.1 test profile, repository ARM flags, locked dependencies, jobs=2 |
| Workers / Store | construction workers=1; Disposable only |
| Timing | CLI `wall_ns`, including control authentication/startup; outer subprocess ns separately retained |
| Preparation | Fixed-size one-kept-file replacement before each sample, outside Commit timer |
| Schedule | Ten alternating keyed/unkeyed pairs per cohort; every sample retained |
| Bounds | Samples 25/28 s; inherited setup/restore/recovery controls 300/320 s (gap below); coordinator holds multiple samples |
| Interference | No own build overlaps samples; other owners' workloads uncontrolled |
| Eligibility | Local diagnostic comparisons, not cold-cache or release admission |

Binary hashes are in baseline/binaries.json and the two build directories'
tested-identities.txt; source patch and logs pin the WAL candidate. The test-only
SDK driver was rebuilt to fork an independent Branch before any timing; baseline
Store/daemon/CLI binaries exactly match ignore08. No ign/cx7 resources were used.
Fixture generation, source hashes, complete commands, output, storage and every
sample's inner/outer ns are retained. `summary.json` is recomputable from the raw
samples; it does not replace them. No measurement was rerun.

## Measurements, as found

All values below are milliseconds. Each Commit cell is **median [min, max]**, n=10.
Restore is one selected mount of the same fixture, outer CLI/attachment time.

| Implementation / cache | Keyed Commit | Unkeyed Commit | Median paired keyed − unkeyed | Restore |
| --- | ---: | ---: | ---: | ---: |
| Manifest / MEMORY | 327.344 [321.707, 345.260] | 6.948 [6.337, 7.587] | +320.603 | 287.336 |
| Small record / MEMORY | 6.972 [6.264, 7.832] | 7.151 [6.300, 8.012] | −0.225 | 190.581 |
| Small record / WAL | 7.345 [6.639, 8.112] | 7.119 [6.696, 8.235] | +0.562 | 152.799 |

Keyed Commit cost is within the registered max(3 ms, 15%) local noise screen.
The WAL keyed median increase over small-record MEMORY is **0.372499 ms (5.34%)**,
below the 3 ms screen. That comparison uses separate cohorts, not alternating
MEMORY/WAL pairs; no statistical significance claim is made. The WAL switch is
kept on this small-cost result and its crash-safety benefit.

The keyed record shrank from **1,249,827 to 387 bytes**. The unkeyed arm writes no
restore record. `verified` rows retain DB/WAL sizes and local object totals.
Saving is structurally O(binding + pending seeds), independent of ignored data;
restore is O(reachable local metadata + object IDs), plus absent-ID windows.

Do not hide setup cost: the full-fixture setup Commit was 5.127 s keyed / 4.717 s
unkeyed with manifests, 5.045 / 4.985 s for small-record MEMORY, and **5.709 /
5.455 s for WAL**. These are single untimed-preparation observations, not ten-run
bulk-write medians. The keyed WAL setup observation is 0.664 s (13.2%) above
MEMORY. Complete multi-sample commands were 53.912 / 54.849 / 57.297 s respectively;
those include setup, verification and cleanup and are not Commit latency.

All 60 sampled Commits returned known success. After each cohort, the verifier
counted all 30,000 local ignored files, matched kept bytes against published
bytes, and confirmed an ignored sentinel was absent from the published root.

## Twenty kill cycles — no replacements

`kill-loop/cycles.jsonl` retains every original attempt. The loop uses the same
ignored fixture plus two ignored 8 MiB generation-marked payloads and one kept
counter. Every cycle edits them, starts one Commit, waits a registered 0–960 ms
after observing its CLI start, SIGKILLs the daemon container, then restarts with
the same WAL cache and fresh overlay/mount paths. No old overlay is recovered.
Each restarted daemon actually opens the cache before the read-only integrity
observer runs. Each child had a bounded deadline; the control-bound configuration gap below
is retained. No cycle is rerun.

**20/20 restart checks PASS**: SQLite opens, `quick_check=ok`, and a coherent
checkpoint restores. Both ignored files have the same permitted generation and
exact deterministic payload bytes. Every explicit next Commit succeeds, its
kept counter equals the server's, and neither ignored payload nor the fixture
sentinel appears in the published root. No fallback was needed in these cycles;
missing-leaf/root fallback is covered by unit tests and the retained ignore08 e2e.

**Coverage limit:** 12 original Commits exit 137, while eight complete before the
kill (one finishes between the client poll and SIGKILL). All late kills stay in
the record; they are not relabeled as mid-transaction faults. Thirteen clients
were still live at the pre-kill poll, which is not proof of a particular SQLite
phase. This is 20 process restart checks, not 20 proven interrupted transactions.
Cycle 16 restores generation 10 after the interrupted Commit published a newer
head; its next Commit is `MergeCommitted`, demonstrating the old binding's use.
The phase inside each interrupted SQLite transaction is not instrumented.

## Tests, failures and cleanup

- b927c453c commits failing tests before fixes: graph reads during save, eager
  payload reads during restore, missing save-failed status, blocked Workspace
  after save error, and non-WAL journaling. All original logs remain in `unit/`.
- `small-build.log` retains an implementation compile error (pending TimingScope
  needed); `small-build2.log` is the corrected build. Nothing overwrote the error.
- Final Mac tests: **56 pass** (9 real cache/transport-peer restore tests,
  5 transport tests, 42 ignore/store tests including model **200 × 30**).
  Tests cover batch absence, missing leaf/root, old checkpoints after save error,
  pending seeds, two-key writers, and on-demand leaf authentication. The journal
  test was deliberately skipped in the MEMORY comparison, then passes with WAL.
- Mac toolchain 1.98.1; Linux builds prove 1.85.1 compatibility. No new dependency.
  Unit test builds precede execution; each unit test invocation has an explicit
  <=120 s bound.
- Strict Clippy retains the existing three `result_large_err` failures. Scoped
  all-target Clippy passes with only that command-line allowance. No lint churn.
- Boundary guard still reports 64 existing violations; all 52 guard tests pass.
  Fuser provenance and touched-Rust formatting pass. Raw Cargo trailing blank
  lines are retained rather than rewritten for whitespace checks.
- A post-campaign audit found inherited 300/320-second control limits for setup,
  restore and recovery operations, despite the registered <=120-second limit.
  Timed samples were correctly bounded at 25/28 seconds; actual controls and all
  three complete cohorts finished below 120 seconds. The failed pure harness
  check and corrected 115/120-second check are retained in `unit/`; no product
  ran during them. This configuration violation remains a qualification limit,
  not a reason to repeat or relabel the original runs. The final helper is fixed.
- All cxi containers, networks and data volumes are removed. Only **cxi-target**
  remains; `cleanup.json` records the final inventory. Other owners were untouched.

## Production LOC

Counter `tools/production_loc.py` at 4c394e3fb, identical `--root <export> --json`
on first-parent and staged Git archive exports of core/crates, sdk/js and
dsh/packages; tests/docs/tooling/inline tests excluded.

| Commit | Before → after | Delta |
| --- | ---: | ---: |
| b927c453c failing tests/measurement | 109,088 → 109,088 | +0 |
| a2dfc4fe0 small record/save failure | 109,088 → 109,151 | +63 |
| WAL and final receipts (this commit) | 109,151 → 109,151 | +0 |

Total production diff: **105 added, 42 removed = 147 changed, +63 net**. Core is
100,242; SDK 2,861 and dsh 6,048 are unchanged. Reference absent (retired R9c;
last counted 65,417 at tree 498dd1917812). WAL changes an existing line, not LOC.
Remaining limits: power/OS loss, uncommitted edits, payload bit-rot qualification,
GC/eviction and post-publication recovery protocols are not built. Eight late
kills and the uninstrumented transaction phases limit fault coverage as above.
