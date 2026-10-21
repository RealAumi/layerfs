# pjdfstest release data

> **Status:** Current general guide.

One folder per release with pjdfstest results: POSIX conformance of a
mounted LayerFS Workspace, every pjdfstest file run once in the Workspace
(`layerfs`) and once on the Sandbox container's own overlayfs
(`sandbox-disk`) as the reference, through the public JS SDK. The harness
is [benchmark/pjdfstest](../../pjdfstest/README.md).

pjdfstest `85a8aea9e685` carries only the classic C suite, which expects
root; `sandbox.exec` runs as uid 501, so the root-only part fails on both
arms. Only an assertion that fails on `layerfs` and passes on
`sandbox-disk` counts against LayerFS.

| Release | Arm | Files pass / fail / skip | Assertions planned | Passed | Failed | Skipped | TODO | LayerFS-only |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [v1.0.0](v1.0.0/) | `layerfs` | 83 / 84 / 71 | 8,798 | 2,444 | 6,262 | 71 | 21 | **707** (275 primary, 432 cascade) |
| | `sandbox-disk` | 93 / 74 / 71 | 8,798 | 3,003 | 5,696 | 71 | 28 | — |

The v1.0.0 LayerFS-only failures reduce to four classes, each reproduced
with a few `pjdfstest` calls (the [run record](v1.0.0/20261019T224251Z/record.md)
has the commands and outputs):

| Class | Primary rows | `layerfs` | `sandbox-disk` |
| --- | ---: | --- | --- |
| FIFO and UNIX socket nodes cannot be created (`mkfifo`, `mknod … f`, `bind`) | 214 | EPERM | 0 |
| Set-id and sticky mode bits refused for the owner (`create 04777`, `chmod 06555`, `chmod 01700`) | 37 | EPERM | 0 |
| atime is not kept apart from mtime (`utimensat` then `lstat atime`) | 16 | atime = mtime | as set |
| ctime not updated by `chmod`, `link`, `unlink` of another link, `rename` onto a multiply linked target | 6 | unchanged | +1 s |

Most of the 432 cascades are class 1: later calls on the FIFO or socket that
was never created (ENOENT, or EEXIST/ENOTEMPTY checks that pass through).
141 assertions fail only on `sandbox-disk` for the same reason (sticky
directory checks that find nothing on `layerfs`). No file hung, crashed or
lost data; utimensat/09.t bailed out on `layerfs` because its probe reads
atime as the mtime.

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

Each folder holds:

| File | What it is |
| --- | --- |
| `results-by-file.csv` | One row per test file and arm: planned, passed, failed (not ok without TODO, plus missing), skipped (quick_exit files), todo, missing, exit, wall ms, status |
| `results-by-dir.csv` | The same totals per test directory and arm |
| `layerfs-only-failures.csv` | One row per assertion failing only on `layerfs`: file, assertion number, pjdfstest call, arguments (random names as NAME), expected, got, cascade hint, the `sandbox-disk` result |
| `different-failures.csv` | Assertions failing on both arms with a different result |
| `summary.json` | Totals per arm, LayerFS-only counts by call and by primary class |
| `environment.csv` | Source, binaries, images, upstream commit, build and tool arguments, user, mounts, Store, host, load |
| `<run id>/` | The run's receipts, unchanged: `identity.txt`, `deploy.env`, `commands.log`, `ledger.jsonl`, `plan.json`, `groups.jsonl`, `tap/` (every group's TAP), the client outputs, `results-by-assertion.csv` (every assertion, both arms), and the run's `record.md` |
| `smoke-<id>-repro/` | The diagnostic repro run: `repro.jsonl` with both arms' outputs |

The CSVs and `summary.json` are derived from the receipts by
`benchmark/pjdfstest/report.py`; everything under the run folders is copied
unchanged from `benchmark-results/pjdfstest/`. The `cascade` column is a
reading aid from the TAP text, not a proof of cause; the record names the
two rows it misreads.

v1.0.0 was measured at `main` `e5c7aaae05` (the fs-bench v1.0.0 build) on
Docker Desktop on an arm64 Mac at 1-minute load 6.3–15.8, one sample per
arm, Disposable Store with policy 16/8/8. Cache state: warm/unknown, not
cold; the suite makes no speed claim.
