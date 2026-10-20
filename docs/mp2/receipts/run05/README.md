# Phase 5: Git stat-cache diagnostics

Status: Dated diagnostic checkpoint; not release or performance qualification.

The pre-existing Phase-2 `e2e-*` and `mp2-lfs-*` root receipts remain byte-for-byte
unchanged. Phase-5 data is in the named subdirectories and new summary files;
the new checksum manifest excludes those historical files.

Source checkout: `e4eae2953`, branch `mp2/remote-store`; no product changes.
Host: `ssh remote-host`, work below `~/lfs-remote/mp2-remote-store/phase5`.
Runtime: arm64 OrbStack, Linux 7.0.14-orbstack, Git 2.39.5. Disposable Store,
MEMORY/OFF overlays, `LAYERFS_CONSTRUCTION_WORKERS=1`. No Durable execution.
The ECR Rust-base tools image reused its cached iproute2/iputils/strace layer.
No Rust compilation was needed: the accepted Phase-4 executables were reused
and checked against retained hash-addressed copies. Their original builds and
no-run checks remain in run03/run04; no Mac/Linux build substitute was used.

## Selected sequence and outcomes

1. `stability`: two simultaneous, independent sandbox containers mount one
   immutable root from A. Every one of the 4,846 tracked paths has stable inode,
   uid/gid, size and nanosecond timestamps, but different `st_dev` (83 vs 85).
   The all-fields-stable gate **FAILS**. Stop variant 1 before refresh/Commit,
   measurements or oracles. Device instability alone is not evidence that Git
   checks device identity; the explicitly selected stop condition governs.
2. `diagnose`: minimal policy, imported index, fresh cache/mount. Status issues
   4,055 requests (2,772 metadata, 1,247 lengths, 36 content); narrow syscall
   tracing shows `.gitignore` is the only working-tree file read.
3. `oracles`: fresh independent Store copies, no added RTT. Same-size edit with
   restored mtime **FAILS** (status clean); server edit/remount **PASSES**; ordinary
   edit **PASSES**. Each forced Git hash differs from the index hash. The failed
   variant was not tuned. FUSE projects ctime from mtime; both return to the old
   value when mtime is restored. No correctness-qualified variant remains, so
   metadata batching was not implemented, despite its numerical opportunity.
4. `measure-0`, `measure-2`, `measure-20`: three independent samples each, in that
   order, for the rejected minimal-policy variant. All status commands complete
   within the fixed 115 s bound. No failing cell was replaced or warmed retry
   substituted. Results remain **correctness FAIL**, not a faster safe solution.

## Receipt map and metric definitions

- `seed/`: exact initialization command, compiled fixture test outcome, binary
  hashes/image ID. Seed is the same Dubbo source used in Phase 4, copied from
  the existing `lfs-src` volume read-only. Original source was not modified.
- `stability/results.jsonl.gz`: every per-path stat pair and field-change counts.
  `stability/commands.jsonl.gz` retains all control replies, including B2's
  **Retained / Join** after five seconds: two loops entered, none exited.
  The harness then removed its owned B2 and B1 containers. It did not retry
  unmount; B1's explicit unmount was not reached. This failure does not erase
  the already captured stat result. No thread stack or additional cause is
  inferred; the exact failing executable now has retained custody.
- `diagnose/`: separate server opcode trace, object roles, status accesses and
  counters. These tracing-on timings are not pooled into the timing cohort.
- `oracles/results.jsonl`: status verdict, explicit before/after stat fields,
  SHA-256/forced Git content hashes and index hashes. The server edit uses
  the public SDK `fs.write` through the retained external driver, followed by
  unmount/remount and ordinary `cat`. No captured/stat field is rewritten.
- `measure-*/results.jsonl`: per-run mount/status command wall ns and cumulative
  Store request deltas. `status-*.trace` records `read`, `pread64` and file-backed
  `mmap`, including filenames via `strace -yy`. A working file is a distinct
  non-`.git/**` path with positive read bytes or a successful file-backed mapping.
  `.gitignore` counts; directory stat/lookup requests do not. All nine cases
  read exactly one working file and zero ordinary source files.
- `summary.json`: recomputed counts, medians and min/max spreads, exact file
  lists, stat stability, oracles and ping distributions. Reproduce with
  `python3 -B docs/mp2/phase5-summary.py`. The script reads gzip receipts too;
  no product execution or performance resampling occurs.
- `receipts/binary-custody.json`: binary hashes and verified existing immutable
  copies under phase4/artifacts. `harness-custody.json` seals the executed scripts.
  `cleanup.log.gz` pins Git/kernel/closed-seed SQLite hash and proves final empty
  inventories for the owned containers, networks and volumes.

The timing cohort uses server request tracing **off**, and the same narrow
strace instrumentation **on** in every timed status. Reported wall is the sum
of Docker-exec mount and status intervals; the intervening counter-query wall
is not included. File-content tracing adds overhead and is declared. Each A
starts from an independent byte copy of the closed seed; each B starts with a
new SQLite object cache, overlay and kernel mount, and receives **no Store path
or volume**. No pre-status tree walk, content read or index refresh is performed
in the timed samples. Server/host OS caches are uncontrolled; no cold-storage
or frozen-family eligibility is claimed.

B-egress `tc netem` adds the full configured RTT. The Phase-3 calibrated CPU-0
proxy and low-priority yielding loop are unchanged. Packet medians are
0.021 / 2.02 / 20.0 ms; first-probe ARP outliers reach 4.08 / 40.1 ms.
Raw ping probes remain in each commands log. No builds or other measurement
cohorts overlapped these runs. The same two-container private/shared-network
arrangement was used; the stability gate alone adds a second independent B.

## Commands, bounds and validation

All command argv, output, exit and wall ns are retained in `commands.jsonl`.
The launcher is a sequence of separately bounded operations, not a single
unbounded test. Run on remote-host from the permitted checkout:

```sh
bash source/docs/mp2/phase5-prepare.sh
python3 source/docs/mp2/phase5-diagnostics.py seed
python3 source/docs/mp2/phase5-diagnostics.py stability
python3 source/docs/mp2/phase5-diagnostics.py diagnose
python3 source/docs/mp2/phase5-diagnostics.py oracles
python3 source/docs/mp2/phase5-diagnostics.py measure-0
python3 source/docs/mp2/phase5-diagnostics.py measure-2
python3 source/docs/mp2/phase5-diagnostics.py measure-20
python3 source/docs/mp2/phase5-cleanup.py
```

`seed` runs the already compiled `timeout 120 /bin-lfs/driver --ignored --exact
drive --nocapture`, `LFS_MODE=init`, `LFS_SOURCE=/original/dubbo`: **1 PASS**.
Every control operation is `timeout 25 /bin-lfs/layerfs-remote
/state/control.setup ...`. Normal unmount has its unchanged internal 5 s Join
deadline; B2's stability-check unmount **FAILS**, subsequent single-B unmounts
**PASS**. No failure was replayed or deadline extended.

Measured Git command (inside B):

```sh
timeout 115 strace -f -yy -o /state/status.trace \
  -e trace=read,pread64,mmap \
  git -c safe.directory='*' -c core.checkStat=minimal \
  -C /workspaces/1 --no-optional-locks status --short
```

All nine commands **PASS execution**; the variant remains **FAIL correctness**.
The clean pre-oracle status and forced `hash-object`/`rev-parse :README.md`
checks use the same command-local policy, without changing `.git/config` or
refreshing the index. These Git calls also have explicit 115 s subprocess
bounds. Server write: `timeout 10 /bin-lfs/driver --ignored --exact drive
--nocapture`, `LFS_MODE=write`, path `/README.md`: **1 PASS**. Ordinary edits,
restored mtime and raw stat comparisons run via recorded Python commands with
explicit outer subprocess bounds. Full stat traversal additionally has
`timeout 25`. All three hash-difference checks **PASS**; they do not turn the
missed status change into a pass.

Local, non-product validation: Python AST parse, summary arithmetic and trace
count checks, changed documentation links, receipt checksums and `git diff
--check`. No Rust source/manifest changed; Rust build/Clippy/transport/FUSE
campaigns were not rerun. Previously accepted Rust verification is reused,
not relabeled as a new test pass. Frozen fs-bench-pro remains unrun.

Cleanup removed only `mp2-p5-*` resources created by this campaign, including
seed/input/data volumes, all private/shared networks and the temporary tools
image. Existing `mp2-postgres-1`, images and source/cache volumes were not
modified. Existing hash-addressed binaries and campaign sources remain under
`~/lfs-remote/` for review. Raw receipts may be gzip-compressed byte-for-byte;
`SHA256.json` verifies the retained files.

Production LOC: **106,288 → 106,288 (delta 0)**: core 98,118, SDK 2,861,
dsh 5,309. Counter `tools/production_loc.py`, blob
`e6d94d1a731b402ccc9159f49cef1eba5a74cfe0`, with its comment/inline-test
exclusions and the retained 739 scripted-mock-line exclusion. All changed
paths are under docs/mp2; product blobs match the first parent. Reference
absent (retired R9c; last counted 65,417 at tree 498dd1917812).
