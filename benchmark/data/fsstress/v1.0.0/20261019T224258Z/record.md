# fsstress — run 20261019T224258Z

> **Verdict:** COMPLETE, one sample per case and arm. Every fsstress run
> exited 0 in both arms. The capture proof PASSED: the tree in the second
> Workspace, mounted from a Branch forked at the Commit, matched the live
> Workspace in all 3,755 entries (manifest SHA-256 identical). fsstress found
> five LayerFS-only operation gaps: extended attributes, fallocate,
> `RENAME_EXCHANGE`, hard links to symlinks, and the inode-flag and FIEMAP
> ioctls. Diagnostic host (arm64 Docker Desktop, load 5.9–15.3); not a
> qualifying result.

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core `main` `e5c7aaae05`: daemon `431dc4f5…`, addon `242b4384…` (`core/target/fs-bench-bin`) |
| Checkout | `fs-bench-sdk-main` at `3a629cfbf0` (`identity.txt`); `benchmark/fsstress` untracked (`harness_dirty_files=1`) |
| Sandbox image | `sha256:f5aefd23f5fc7308fd47e9600289a45e5f561f3639fb37e6441d6cbe5aaaad75` (`bench-fsstress:20261019`), FROM `fs-bench-computer:gawk-20261020` `sha256:66aeb6bbf7fc…` |
| Runtime image | `layerfs-352-runtime:node24` `sha256:d3773b4eac6a…` |
| fsstress | xfstests-dev `22348afe338c0f6d540c0d7ef0db749eaa51b218` `ltp/fsstress.c`, binary sha256 `249121ae404bb184…`; gcc 12.2.0, autoconf 2.71, automake 1.16.5, libtool 2.4.7, libaio 0.3.113, liburing 2.3, xfslibs-dev 6.1.0 (Debian bookworm) |
| Store | Disposable, policy 16/8/8, `LAYERFS_CONSTRUCTION_WORKERS=1`, trace off |
| Sandbox | uid 501, gid 20, kernel 6.12.76-linuxkit; Workspace `/workspaces/1` is `fuse rw,nosuid,nodev,noatime,default_permissions,allow_other,max_read=131072`; `/` (and `/tmp`) overlay |
| Host | Docker Desktop 29.5.2, 8 CPUs, 8.32 GB |
| Cache | warm/unknown, not cold |

## Commands

| Step | Start (UTC) | End | Exit | 1-min load |
| --- | --- | --- | --- | --- |
| setup | 22:42:59 | 22:43:00 | 0 | 15.31 |
| lock taken | 22:51:52 | | | |
| case-c1-sandbox-disk | 22:51:58 | 22:52:02 | 0 | 5.94 |
| case-c1-layerfs | 22:52:02 | 22:52:06 | 0 | 5.94 |
| case-c2-sandbox-disk | 22:52:12 | 22:52:17 | 0 | 6.24 |
| case-c2-layerfs | 22:52:17 | 22:52:27 | 0 | 6.22 |
| capture-commit | 22:52:32 | 22:52:48 | 0 | 6.43 |
| capture-verify | 22:52:48 | 22:53:01 | 0 | 6.68 |
| teardown, cleanup, unlock | 22:53:07 | 22:53:08 | 0 | 6.92 |

Setup ran before the lock: `bench_lock` found pjdfstest's run
`20261019T224251Z` holding it (taken 4 s before), so the Workspace sat
mounted and idle until 22:51:52 while pjdfstest measured. No fsstress
operation ran before the lock was taken. Volumes and containers were removed
at teardown.

Arguments (seeds fixed): c1 `fsstress -d DIR -p 1 -n 10000 -s 365001 -v -V -o
/tmp/fsslog/c1-ARM.log`; c2 the same with `-p 4 -n 10000 -s 365002`. DIR is
`/workspaces/1/fss-cN` (layerfs) or `/tmp/fss-cN` (sandbox-disk).

## Result

| Case | Arm | Procs × ops | Exit | Wall ms | Ops/s | Errors | Outcomes parsed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c1 | sandbox-disk | 1 × 10,000 | 0 | 2,453.9 | 4,075.1 | 2,150 | 10,000 |
| c1 | layerfs | 1 × 10,000 | 0 | 3,824.9 | 2,614.5 | 3,621 | 10,000 |
| c2 | sandbox-disk | 4 × 10,000 | 0 | 3,962.4 | 10,094.9 | 8,443 | 39,992 |
| c2 | layerfs | 4 × 10,000 | 0 | 6,932.0 | 5,770.3 | 14,638 | 39,992 |

Wall is fsstress alone inside the exec; the exec's client-side time was
2,654.8 / 3,933.4 / 4,419.2 / 7,192.7 ms. Ops/s is procs × ops ÷ wall. The
two arms do not do the same work: an op that fails returns early, and
the files later ops act on diverge (below), so the wall ratio (1.56× for c1,
1.75× for c2) is indicative only. Errors include the root-only and XFS-only
failures common to both arms. Eight c2 operations per arm print no result
line, the same count in both arms.

**c1 determinism.** The two c1 logs (blocks masked) first differ at line 8,
op 6: `getattr f0 0 -1` (layerfs) against `getattr f0 524288 0`. Op 6 does
not change the tree; the first tree-changing divergence is op 32, a
`rename(EXCHANGE)` that succeeds only on the reference, after which the arms
pick different files: 391 of 10,000 operations have the same op and outcome,
80 the same op with another outcome, 9,529 a different op. c1 is compared
through per-op outcome counts (`op-errors.csv`).

### Capture proof (layerfs, after c2 exited)

| Measure | Value |
| --- | ---: |
| Entries (whole Workspace: seed, `fss-c1`, `fss-c2`) | 3,755 (947 dirs, 1,963 files, 845 symlinks; 477 hard-linked paths) |
| Regular-file bytes | 5,214,397,108 |
| Commit (`sandbox.commit`) | **4,851.7 ms** |
| logical / newCanonical / newStored / newMetadata | 5,214,397,108 / 375,189,900 / 1,283,524 / 832,088 B |
| Commit id | `12fea63ce0d30898e29ca48fc74ae746cf5b89e6907357a5e6fb2eab3cdd480f88` |
| Fork `capture` head | the Commit id |
| Second mount / unmount | 34.7 / 182.0 ms (`/workspaces/2`) |
| Manifest live / captured (exec) | 10,167.5 / 11,627.6 ms |
| Manifest equal | **yes**, 0 differences; both SHA-256 `40b8b0f4ee02…` |

The files are mostly sparse: fsstress writes at random offsets up to 1 MiB
past the end. The live manifest read every file through the mount just
before the Commit, so the Commit ran with that data in the page cache.

### LayerFS-only failures

Counts are c1 / c2 operations; the reference column is what sandbox-disk
returned for the same op. Each was reproduced with a standard tool in a
separate diagnostic run (`smoke-20261019T225428Z-repro`, `run.sh repro`,
the same image and binaries), in `<Workspace>/repro` and `/tmp/repro`.

| Op (fsstress) | layerfs | sandbox-disk | c1 / c2 | Repro on layerfs | Error |
| --- | --- | --- | ---: | --- | --- |
| `setfattr`, `getfattr`, `listfattr`, `removefattr` (user.* xattrs) | EOPNOTSUPP | 0, ENODATA, EEXIST | 516 / 2,013 | `python3 -c 'import os; os.setxattr("f", "user.k", b"v")'` (and getxattr, listxattr, removexattr) | `OSError: [Errno 95] Operation not supported` |
| `fallocate()` (mode 0) | EOPNOTSUPP | 0 | 67 / 204 | `fallocate -o 0 -l 1048576 f` | `fallocate: fallocate failed: Operation not supported` |
| `fallocate(KEEP_SIZE)`, `(KEEP_SIZE\|PUNCH_HOLE)`, `(KEEP_SIZE\|ZERO_RANGE)` | EOPNOTSUPP | 0 | 167 / 627 | `fallocate -n -o 1048576 -l 65536 f`; `fallocate -p -o 0 -l 4096 f` | `fallocate: fallocate failed: keep size mode is unsupported` |
| `fallocate(ZERO_RANGE)`, `(COLLAPSE_RANGE)`, `(INSERT_RANGE)` | EOPNOTSUPP | 0 or EINVAL | 150 / 598 | `fallocate -z -o 0 -l 4096 f`; `-c`; `-i` | `fallocate: fallocate failed: Operation not supported` |
| `xfsctl(XFS_IOC_RESVSP64)`, `(XFS_IOC_UNRESVSP64)` (preallocation through the generic ioctl) | EOPNOTSUPP | 0 | 209 / 840 | `ioctl(fd, XFS_IOC_RESVSP64, …)` in Python | `OSError: [Errno 95] Operation not supported` |
| `rename(EXCHANGE)` | EINVAL (188 / 764; 6 / 10 returned 0) | 0 | 188 / 764 | `renameat2(AT_FDCWD, "a", AT_FDCWD, "b", RENAME_EXCHANGE)` via ctypes | `[Errno 22] Invalid argument` |
| `link` of a symlink | EPERM | 0 | 31 / 128 | `ln -s f s; ln s s2` | `ln: failed to create hard link 's2' => 's': Operation not permitted` |
| `getattr` (`FS_IOC_GETFLAGS`) | -1 on every call | 0 where the open succeeds (57 / 224) | 92 / 413 | `fcntl.ioctl(open("f","rb"), FS_IOC_GETFLAGS, …)` | `OSError: [Errno 25] Inappropriate ioctl for device` |
| `ioctl(FIEMAP)` | -1 on every call | 0 (51 / 221) | 83 / 413 | `fcntl.ioctl(fd, FS_IOC_FIEMAP, …)` | `OSError: [Errno 95] Operation not supported` |
| `setxattr` (`FS_IOC_FSGETXATTR` / project id) | -1 on every call | 0 on 5 / 26 calls | 101 / 415 | `fcntl.ioctl(fd, FS_IOC_FSGETXATTR, …)` | `OSError: [Errno 25] Inappropriate ioctl for device` |

The last three ops print fsstress's raw return code (-1), not an errno; the
errno comes from the repro. The 6 / 10 `rename(EXCHANGE)` calls that
returned 0 on layerfs exchanged an entry with itself or with a hard link to
the same inode (for example `3/143: f1 to f4` after `3/25: link f1 f4`),
which the kernel completes without calling the filesystem.

Not counted against LayerFS:

- `deduperange`: EOPNOTSUPP on layerfs (400 / 1,598), ioctl success on the
  reference, but the reference deduplicated nothing: its per-range results
  were 17,591 × EINVAL and 2,688 × "0 bytes deduplicated" in c1 (repro: range
  status -22). Neither arm deduplicates.
- Common to both arms: `chown` and `mknod` EPERM (uid 501), `bulkstat1` and
  `exchangerange` ENOTTY, `clonerange` and the unsupported fallocate
  combinations (`PUNCH_HOLE` without `KEEP_SIZE`, `UNSHARE_RANGE`,
  `WRITE_ZEROES`, `KEEP_SIZE|COLLAPSE_RANGE`, `KEEP_SIZE|INSERT_RANGE`)
  EOPNOTSUPP, `rmdir` ENOTEMPTY, `rename()`/`rename(NOREPLACE)` EINVAL.

## Harness notes

- `run.sh` gained the `repro` step after this run; the steps used here are
  unchanged. `report.py` ran after the run.
- The two manifests were gzipped (`gzip -9 -n`) after read-back; their
  uncompressed SHA-256 is in `capture.jsonl`.
- Smoke runs `smoke-20261019T222356Z` (500/20,000 ops, capture in one
  client) and `smoke-20261019T222627Z` (split capture) chose N and checked the
  route; they are not results.

## Files

`benchmark-results/fsstress/20261019T224258Z/`: `identity.txt`,
`deploy.env`, `commands.log`, `ledger.jsonl`, `cases.jsonl`,
`readback.jsonl`, `capture.jsonl`, `logs/` (the eight fsstress logs plus the
empty parent logs, gzipped), `manifest-live.jsonl.gz`,
`manifest-capture.jsonl.gz`, `summary.json` and the client `.out`/`.err`
files. CSVs: [benchmark/data/fsstress/v1.0.0](../../data/fsstress/v1.0.0/).
