# pjdfstest — run 20261019T224251Z

> **Verdict:** COMPLETE, one sample. All 238 test files ran once in each arm
> (8,798 planned assertions per arm), no file was cut by a timeout, the
> Workspace committed afterwards. **707 assertions in 45 files fail only on
> `layerfs`**; read as root causes they are four classes (below). Run as
> uid 501, not root, so the root-only part of the suite fails on both arms
> and is not counted. Diagnostic host (arm64 Docker Desktop, 1-minute load
> 6.3–15.8); not a qualifying result.

## Identity

| Item | Value |
| --- | --- |
| LayerFS | `main` `e5c7aaae05` build: daemon `431dc4f5…`, addon `242b4384…` (`core/target/fs-bench-bin`) |
| Harness | `benchmark/pjdfstest` (untracked at checkout `3a629cfbf0`), `benchmark/common` at `3a629cfbf0` |
| Sandbox image | `sha256:e52048e29f1c0645d3e6ea46b676a9aa9c9ba1c8fbf826d7245afd3739520f05` (`bench-pjdfstest:20261019`), FROM `fs-bench-computer:gawk-20261020` = `sha256:66aeb6bbf7fc…` |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| pjdfstest | `85a8aea9e685999ef0540392fd80535f873d7ff7`, classic C binary built with autoreconf/configure/make (bookworm autoconf, automake), binary sha256 `3e214f563b45…` |
| Store | Disposable, policy 16/8/8, `LAYERFS_CONSTRUCTION_WORKERS=1`, trace off |
| Sandbox user | uid 501, gid 20 (groups 20), umask 022, `/bin/sh` = dash |
| Arms | `layerfs`: `/workspaces/1/pjd/<dir>`, `fuse rw,nosuid,nodev,noatime,user_id=0,group_id=0,default_permissions,allow_other,max_read=131072`; `sandbox-disk`: `/tmp/pjd/<dir>`, overlay |
| Parameters | `sh tests/DIR/FILE.t` per file, file timeout 100 s, start budget 40 s, a file that calls `sleep` starts only first in a group, group cut 105 s |
| Host | Docker 29.5.2, Docker Desktop linuxkit 6.12.76, 8 CPUs, 8.32 GB; free disk 424 GB at start |
| Cache state | warm/unknown, not cold (no timing claim is made) |

## Runs

| Run | Outcome |
| --- | --- |
| `smoke-20261019T222200Z` | Smoke (chmod, mkfifo), no lock. Its cleanup was given a relative RUN, so the SDK home volume went before teardown; the Sandbox container was removed with `docker rm -f` and the Store volume after it. `run.sh` now requires an absolute RUN and refuses cleanup before a teardown row. |
| `smoke-20261019T222520Z` | Smoke (mkfifo) through finish and cleanup. |
| `20261019T223809Z` | **Aborted, harness bug.** `chown/00.t` sleeps about 76 s in its ctime checks; the 60 s file timeout cut it at assertion 1,153 of 1,280 in both arms (exit 124). Torn down, cleaned up and unlocked after 7 groups; receipts kept. |
| `20261019T224251Z` | **This run**, after the fix (file timeout 100 s; a sleeping file starts only first). |
| `smoke-20261019T225601Z-repro` | Diagnostic after the run, no lock: `client/repro.mjs`, the minimal repro of each class below, once per arm. |

## Commands

| Step | Start–end (UTC) | Exit | 1-min load |
| --- | --- | --- | --- |
| setup (Init 19.3 ms, create 473.8 ms, mount 5.4 ms) | 22:42:53–22:42:55 | 0 | 15.77 |
| lock | 22:42:55 | 0 | — |
| group-1 … group-51 (50 groups + DONE) | 22:43:01–22:51:23 | all 0 | 6.29–15.31 |
| finish (residue, Commit 10.6 ms, unmount 2.1 ms, close 195.1 ms) | 22:51:23–22:51:24 | 0 | 7.25 |
| cleanup, unlock | 22:51:24 | 0 | — |

25 groups per arm; the longest exec was `chown/00.t` alone (78.7 s
`layerfs`, 78.1 s `sandbox-disk`). Summed per-file wall: 163.8 s `layerfs`,
163.5 s `sandbox-disk`. No output was truncated; no group was cut.

After the run, `pjd/` in the Workspace held 21 entries (3 left by tests:
one each under `mkdir`, `rename`, `utimensat`). The Commit captured them:
`newCanonical` 2,769 B, `newStored` 725 B.

## Result per arm

| | `layerfs` | `sandbox-disk` |
| --- | ---: | ---: |
| Files pass / fail / skip | 83 / 84 / 71 | 93 / 74 / 71 |
| Planned assertions | 8,798 | 8,798 |
| Passed | 2,444 | 3,003 |
| Failed (incl. missing) | 6,262 (6 missing) | 5,696 (0) |
| Skipped (quick_exit files) | 71 | 71 |
| TODO (`todo Linux`) | 21 | 28 |

Per directory, assertions passed (`layerfs` / `sandbox-disk`) of planned:
chmod 135 / 199 of 327; chown 280 / 425 of 1,497; ftruncate 71 / 71 of 89;
link 162 / 225 of 359; mkdir 69 / 77 of 118; mkfifo 42 / 84 of 120; mknod
56 / 106 of 186; open 113 / 133 of 337; rename 1,106 / 1,207 of 4,857; rmdir
77 / 83 of 145; symlink 72 / 76 of 95; truncate 68 / 68 of 84; unlink
124 / 154 of 440; utimensat 69 / 95 of 122; chflags, granular and
posix_fallocate are all skipped on Linux (`results-by-dir.csv`).

Most failures on both arms are the root-only cases: `chown` to 65534/0,
device `mknod`, and every `pjdfstest -u/-g` call (setuid/setgroups fail with
EPERM, so those assertions print no result).

## LayerFS-only failures

707 assertions fail on `layerfs` and pass on `sandbox-disk`
(`layerfs-only-failures.csv`). report.py marks 432 as cascades of an
earlier layerfs-only create failure in the same file (mostly ENOENT on the
FIFO or socket that was never made; `link`, `mkdir`, `open O_EXCL` and
`symlink` returning 0 instead of EEXIST because the existing FIFO or socket
is missing; `rename` and `rmdir` of a directory succeeding where ENOTEMPTY
was expected because the FIFO or socket inside it is missing). The 275 primary rows are four classes; each was reproduced with
`run.sh repro` in `smoke-20261019T225601Z-repro`:

| Class | Primary rows | Example (file #assertion) | Repro (in the Workspace, `P=/opt/pjdfstest/pjdfstest`) | `layerfs` | `sandbox-disk` |
| --- | ---: | --- | --- | --- | --- |
| FIFO and UNIX socket nodes cannot be created | 214 (mkfifo 107, bind 93, mknod 14) | mkfifo/00.t #2 `mkfifo NAME 0755`: expected 0, got EPERM | `$P mkfifo f 0644`; `$P bind s`; `$P mknod m f 0644 0 0` | `mkfifo returned -1 EPERM`, `bind returned -1 EPERM`, `mknod returned -1 EPERM` | `0` each |
| Set-id and sticky mode bits refused for the owner | 37 (create 3, chmod 32, stat 2) | chmod/12.t #2 `create NAME 04777`: got EPERM; chown/00.t #374 `chmod NAME 06555`: got EPERM; chmod/11.t #3 `chmod NAME 01621`: got EPERM | `$P create su 04777`; `$P create a 0644; $P chmod a 06555`; `$P mkdir d 0755; $P chmod d 06555`; `$P create b 0644; $P chmod b 01700` | `create returned -1 EPERM`, `chmod returned -1 EPERM` (file and directory) | `0` each |
| atime is not kept apart from mtime | 16 (lstat 10; utimensat/09.t 6 missing) | utimensat/00.t #4 `lstat NAME atime`: expected 1900000000, got 1950000000; utimensat/09.t bails out (its probe reads atime 4294967296 = the mtime) | `$P create t 0644; $P open . O_RDONLY : utimensat 0 t 1900000000 0 1950000000 0 0; $P lstat t atime,mtime` | `1950000000,1950000000` | `1900000000,1950000000` |
| ctime is not updated by chmod, link, unlink of another link, or rename onto a multiply linked target | 6 (chmod/00.t #64 file, #68 directory; link/00.t #134; unlink/00.t #29, #110; rename/23.t #7) | test_check `$ctime1 -lt $ctime2` after `sleep 1` | `$P create c 0644; a=$($P stat c ctime); sleep 1; $P chmod c 0600; $P stat c ctime` (and the same around `link l l2`, `unlink l2`, `rename s1 d1` with `d1` linked to `dl`) | before = after (e.g. `1792450564,1792450564`) | after = before + 1 |

Two more rows report.py calls primary, chown/00.t #1199 and #1262, are the
ctime checks of the FIFO and socket iterations (their creates failed more
than six assertions earlier), so cascades of class 1. mkfifo/09.t #8 and
#17 (`mkfifo NAME` expected EEXIST, got EPERM) also belong to class 1: the
existing object was itself a FIFO or socket that was never created; a FIFO
on an existing regular file does return EEXIST (repro).

`different-failures.csv` lists 493 assertions that fail on both arms with a
different result; they are the same cascades (ENOENT on `layerfs` where
`sandbox-disk` reaches the root-only EPERM) and the modes left by class 2.
141 assertions fail only on `sandbox-disk` (rename/09.t 70, rename/10.t 60,
unlink/11.t 10, mkdir/10.t 1): sticky-directory checks where `layerfs`
passes only because the FIFO or socket never existed (ENOENT where the test
expected the root-only move to have happened).

## Reading the classes

- Class 1 reaches every FIFO/socket assertion in chmod, chown, link, mkdir,
  mkfifo, mknod, open, rename, rmdir, symlink and unlink; it is the bulk of
  the 707 (45 files in all have a layerfs-only failure).
- Class 2 shows up wherever a test sets S_ISUID/S_ISGID/S_ISVTX as the
  owner; overlay accepts them (gid 20 is the caller's group).
- Class 3 and 4 are timestamp semantics. `noatime` on the mount does not
  explain class 3: `utimensat` sets atime explicitly.
- Nothing here is a crash, hang, lost write or wrong data; every file ran to
  its plan except utimensat/09.t's bail-out.
