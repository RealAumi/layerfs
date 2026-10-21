# pjdfstest

> **Status:** Current general guide.

POSIX conformance of a mounted LayerFS Workspace, measured with
[pjdfstest](https://github.com/pjd/pjdfstest) at commit
`85a8aea9e685999ef0540392fd80535f873d7ff7` (2026-08-07). Root AGENTS.md
§1–3, [benchmark/AGENTS.md](../AGENTS.md) and the
[shared harness](../common/README.md) govern.

## Variant and configuration

That commit carries only the **classic suite**: the C program `pjdfstest`
(built with its own autotools) and 238 shell test files `tests/<syscall>/NN.t`
that print TAP. There is no Rust rewrite at this commit, so there is no
unprivileged mode or feature config to select.

The classic suite expects root. `sandbox.exec` is never root (uid 501,
gid 20, umask 022, `/bin/sh` is dash), so every test file runs as uid 501.
Cases that need root fail on **both** arms: `chown` to other uids, `mknod`
of devices, `-u`/`-g` identity switches in `pjdfstest` itself (setuid and
setgroups fail with EPERM, so those assertions print no result), and
whatever follows from them. Those are not counted against LayerFS. Only an
assertion that fails on `layerfs` and passes on `sandbox-disk` is a
LayerFS-only failure.

Files that call `quick_exit` print a fake `1..1 / ok 1` when the platform or
filesystem is unsupported (chflags, the FreeBSD/ZFS NFSv4 ACL `granular`
tests, posix_fallocate on Linux, and others); `run-group.sh` marks them and
`report.py` counts them as skipped. `todo Linux …` assertions keep TAP's
TODO meaning (a known platform failure, not counted as failed).

misc.sh finds the filesystem type with `df -PT .`: `FUSE` on `layerfs`,
`OVERLAY` on `sandbox-disk`. No test file branches on either value at this
commit (they branch on FreeBSD/UFS/ZFS/Btrfs and two FUSE network
filesystems), so both arms run the same assertions.

## Arms

Both arms run in the same Sandbox, through `sandbox.exec`, with the same
command:

| Arm | Working directory | Filesystem |
| --- | --- | --- |
| `layerfs` | `<Workspace>/pjd/<dir>` (`/workspaces/1/pjd/<dir>`) | LayerFS FUSE mount |
| `sandbox-disk` | `/tmp/pjd/<dir>` | the container's overlayfs |

## Route

```text
setup   new LayerFS("pjdfstest", { storePolicy: 16/8/8 })   (common/session.mjs)
        project.init(RUN/seed)        one README file
        sandbox.create("bench", "pjdfstest", image) → branch.fork("bench", "main") → sandbox.mount
        exec probe: id, umask, both arms' fs type, mount options, pjdfstest commit and binary hash
        exec ls /opt/pjdfstest/tests/*/*.t → plan.json
group   exec run-group.sh ROOT DIR 100 40 FILE.t...   (repeat until DONE)
finish  exec residue listing → sandbox.commit (timed) → sandbox.unmount → sandbox.close
```

- **Groups.** One `sandbox.exec` per group. A group takes the first
  directory (in `ls` order) with files not yet started in an arm, `layerfs`
  first, then `sandbox-disk`. `run-group.sh` runs each file as
  `sh tests/DIR/FILE.t` (what `prove` does for a `#!/bin/sh` test) under a
  100 s timeout, starts no file after 40 s, starts a file that calls `sleep`
  (the ctime checks; `chown/00.t` sleeps about 76 s) only as the group's
  first, and is cut at 105 s, so each client stays under its 115 s limit.
  Files it did not start are deferred to the next group; no file runs twice
  in an arm.
- **Receipts.** Each group's TAP goes unchanged to `tap/<arm>-<dir>-<ms>.tap`
  with `### begin`/`### end` markers (exit, wall ms, quick_exit, residue
  count); `groups.jsonl` records the exec's exit, wall time, truncation and
  the files started and deferred.
- **Commit.** No Commit is measured. `finish` makes one `sandbox.commit` after
  all groups to show the Workspace still commits; its time is in
  `ledger.jsonl`.

## Files

| Path | Role |
| --- | --- |
| `run.sh` | `image`, `setup`, `lock`, `group`, `finish`, `repro`, `teardown`, `cleanup`, `unlock` (sources `../common/lib.sh`) |
| `client/setup.mjs` | Init, create, fork, mount (common `setup`), probe, `plan.json` |
| `client/group.mjs` | The next pending group, one exec |
| `client/finish.mjs` | Residue, the one Commit, unmount and close |
| `client/repro.mjs` | Diagnostic: minimal repros of the LayerFS-only classes, one exec per arm, into `repro.jsonl` |
| `sandbox/Dockerfile` | `FROM fs-bench-computer:gawk-20261020`, autoconf/automake from bookworm, pjdfstest fetched at the pinned commit and built |
| `sandbox/run-group.sh` | Runs one directory's files in an arm; in the image at `/opt/pjd-bench/` |
| `report.py` | `results-by-file.csv`, `results-by-dir.csv`, `results-by-assertion.csv`, `layerfs-only-failures.csv`, `different-failures.csv`, `summary.json` |
| `records/` | One record per run |

## Running

```bash
cd benchmark/pjdfstest
./run.sh image                                  # bench-pjdfstest:<yyyymmdd>, image.txt
RUN=$PWD/../../benchmark-results/pjdfstest/$(date -u +%Y%m%dT%H%M%SZ)
./run.sh lock $RUN                              # measured runs; exit 75: another suite measures; wait 90 s, ask again
./run.sh setup $RUN                             # add DIR... for a smoke run of some directories (no lock)
./run.sh group $RUN                             # repeat until it prints DONE
./run.sh finish $RUN
./run.sh cleanup $RUN
./run.sh unlock $RUN
python3 report.py $RUN
```

For the minimal repros, use a separate smoke run (no lock):
`./run.sh setup $SMOKE granular`, `./run.sh repro $SMOKE`,
`./run.sh teardown $SMOKE`, `./run.sh cleanup $SMOKE`.

RUN must be absolute. `cleanup` refuses until `finish` (or `teardown`) has
recorded a teardown, so the SDK home outlives the Sandbox.

## Reading the result

- `results-by-file.csv`: per file and arm, `planned` (the TAP plan),
  `passed`, `failed` (not ok without TODO, plus planned assertions that never
  printed), `skipped` (quick_exit files), `todo`, `missing`, exit and wall ms.
- `layerfs-only-failures.csv`: one row per assertion that fails on `layerfs`
  and passes on `sandbox-disk`, with the pjdfstest call, the expected and
  actual result. Its `cascade` column is a reading aid (rules in
  `report.py`'s header): `cascade` marks a failure that follows a create that
  failed only on `layerfs` in the same file (ENOENT on that object, or an
  EEXIST check passing through); `primary` rows are the ones to read first.
- `different-failures.csv`: assertions that fail on both arms with a
  different result (mostly the same cascades).

## Known limits

- Not root: the root-only part of the suite is unmeasured on both arms. A
  root run (or the Rust rewrite's unprivileged mode, at a later commit) would
  cover more.
- Assertions are matched by number within a file. Both arms run the same
  branches here (see the fs type note), so numbers line up.
- `sandbox-disk` is the container's overlayfs on the Docker Desktop VM's
  ext4, not a bare local filesystem; it is the reference, not a POSIX oracle.
- Wall times are recorded per file for diagnosis; this suite makes no speed
  claim. Cache state: warm/unknown, not cold.
