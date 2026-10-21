# fsx release data

> **Status:** Current general guide.

One folder per release with fsx results: xfstests' `ltp/fsx` checks one
file against its in-memory model through a seeded random mix of reads,
writes, mapped I/O, truncates and range ops, run through `sandbox.exec`
in a LayerFS Workspace (`layerfs`) and in the same Sandbox's own overlayfs
`/tmp` (`sandbox-disk`) as the reference. The harness is
[benchmark/fsx](../../fsx/README.md).

| Release | Variant | fsx args | Ops per arm | layerfs | sandbox-disk | layerfs ops/s | sandbox-disk ops/s |
| --- | --- | --- | ---: | --- | --- | ---: | ---: |
| [v1.0.0](v1.0.0/) | default | (none: 256 KiB, unaligned, mmap) | 600,000 | 2 / 2 PASS | 2 / 2 PASS | 8,591 | 8,515 |
| | no-mmap | `-R -W` | 600,000 | 2 / 2 PASS | 2 / 2 PASS | 9,690 | 21,750 |
| | aligned | `-r 4096 -w 4096 -t 4096` | 600,000 | 2 / 2 PASS | 2 / 2 PASS | 11,713 | 10,650 |
| | medium | `-l 4194304` | 400,000 | 2 / 2 PASS | 2 / 2 PASS | 7,375 | 8,090 |
| | large | `-l 67108864 -o 1048576` | 24,000 | 2 / 2 PASS | 2 / 2 PASS | 1,152 | 2,036 |
| | large-no-mmap | `-l 67108864 -o 1048576 -R -W` | 32,000 | 2 / 2 PASS | 2 / 2 PASS | 1,301 | 2,438 |
| | direct | `-Z -R -W -r 4096 -w 4096` | 800,000 | 2 / 2 PASS | 2 / 2 PASS | 12,887 | 9,178 |

ops/s is Σ ops ÷ Σ fsx wall time over seeds 1 and 2.

**v1.0.0 in one line:** 28 / 28 fsx runs passed (3,056,000 ops per arm),
with no data or size miscompare; files grew past 1 MiB (to 4 and 64 MiB)
and mapped writes and `O_DIRECT` passed, unlike the v0.1.6 reports in #361.
The LayerFS-only difference is that every fallocate mode (0, `KEEP_SIZE`,
`PUNCH_HOLE|KEEP_SIZE`, `ZERO_RANGE`, `COLLAPSE_RANGE`, `INSERT_RANGE`)
fails `EOPNOTSUPP` on the mount, so fsx disables them there and those ops
were not exercised on LayerFS. One `sandbox.commit` of the Workspace
afterwards: Committed in 457.2 ms (166,731,557 logical bytes).

## By design: LayerFS's stored format

Every LayerFS-only difference here is a deliberate limit of what a Workspace
stores and serves, decided in source, not a defect found by this run:

| Limit | What LayerFS does | Where it is decided |
| --- | --- | --- |
| Node types | Regular files, directories and symlinks only; FIFO, socket and device nodes are refused (EPERM) | `core/crates/layerfs-fuse/src/operations/unsupported.rs` (`node`) |
| Mode bits | `0o777` on files, `0o1777` on directories; set-id bits and sticky on files are refused (EPERM); the mount is `nosuid` | `core/crates/layerfs-content/src/filesystem/attributes/portable.rs`, `core/crates/layerfs-fuse/src/mount/syscalls.rs` |
| Times | One stored time (mtime); atime, ctime and crtime are reported as it; the mount is `noatime` | `core/crates/layerfs-fuse/src/attributes.rs`, `core/crates/layerfs-fuse/src/operations/write.rs` |
| Absent FUSE operations | Extended attributes, fallocate, ioctl, copy_file_range, locks and lseek are not implemented (ENOSYS; the kernel falls back or returns EOPNOTSUPP) | `core/crates/layerfs-fuse/src/operations/unsupported.rs` (`absent`) |
| Rename flags | `RENAME_NOREPLACE` only; exchange and whiteout are refused (EINVAL) | `core/crates/layerfs-fuse/src/operations/unsupported.rs` (`rename_replaces`) |
| Hard links | Not to a directory or a symlink (EPERM) | `core/crates/layerfs-workspace/src/operations/types.rs` (`NotPermitted`) |
| Ownership | One runtime identity per Workspace; chown to another is refused | `core/crates/layerfs-fuse/src/operations/unsupported.rs` (`ownership`) |

These keep a Commit to portable, reproducible metadata (type, permission
bits, mtime, content). Counts below are reported as recorded; read a
LayerFS-only failure as "outside the format", not as a broken operation.

## How to read it

- `PASS` is fsx's own `All N operations completed A-OK!` with exit 0. A
  `FAIL` keeps fsx's exit code and its first error line plus the last op
  of its log dump in `first_failure`.
- `unsupported_ops` lists the ops fsx disabled at start because the
  filesystem refused them. That is not a failure, but an op missing only
  on `layerfs` is a LayerFS-only difference.
- Speed is one sample per case and arm on a loaded Docker Desktop host
  (1-minute load 7–15); the seed-to-seed spread on one arm is as large as
  some arm differences. Indicative only. Cache state: warm/unknown, not
  cold.

Each folder holds:

| File | What it is |
| --- | --- |
| `results.csv` | One row per variant, arm and seed: `variant, arm, seed, args, ops, exit, result, wall_ms, ops_per_s, unsupported_ops, first_failure`, then `ops_requested, exec_ms` (the exec's client-side time) |
| `commit.csv` | The one `sandbox.commit` after all cases: time, kind, ids, logical and new bytes |
| `environment.csv` | Source, binaries, images, upstream commit, fsx build and args, Store, host, load |
| `receipts/` | The run's receipts, unchanged: `identity.txt`, `deploy.env`, `cases.tsv`, `commands.log`, `ledger.jsonl`, `results.jsonl`, `sandbox-identity.txt`, `summary.json`, `cases/*.txt` (fsx's output per case and arm), and the run's `record.md` |
| `probe/` | The diagnostic fallocate probe (`probe.jsonl`: each mode's `fallocate(1)` error text in both arms) and its run files |

The CSVs are derived from the receipts by `benchmark/fsx/report.py`;
everything else is copied unchanged from `benchmark-results/fsx/`.

## Limits

- fsx's AIO (`-A`), io_uring (`-U`), `-X` and dm-log-writes modes were not run.
- `sandbox-disk` is the container's overlayfs, which also refuses
  clone/dedupe/exchange range and the `UNSHARE_RANGE` / `WRITE_ZEROES`
  fallocate modes; those are not LayerFS-only.
- v1.0.0 was measured at `main` `e5c7aaae05` (the fs-bench v1.0.0 build)
  on Docker Desktop on an arm64 Mac, Disposable Store with policy 16/8/8.
