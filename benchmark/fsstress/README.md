# fsstress

> **Status:** Current general guide.

Random filesystem operations from xfstests' `fsstress` against a LayerFS
Workspace and against the Sandbox container's own disk, plus a Commit
capture proof: the tree fsstress leaves behind is committed, forked, mounted
again and compared entry by entry. Part of
[#365](https://github.com/Ephemeral-AI-Lab/layerfs/issues/365); the shared
harness is [benchmark/common](../common/README.md).

## Tool

`fsstress` from xfstests-dev
(`https://git.kernel.org/pub/scm/fs/xfs/xfstests-dev.git`) at
`22348afe338c0f6d540c0d7ef0db749eaa51b218`, program `ltp/fsstress.c`, built in
the Sandbox image with upstream's own autotools build (`make configure`,
`./configure`, `make -C lib`, `make -C ltp fsstress`). Configure finds
libaio, liburing, fallocate and copy_file_range; libbtrfsutil is absent, so
the btrfs snapshot/subvolume ops are off, as fsstress does on any
non-btrfs directory. Every other op keeps its default frequency.

## Route and arms

Everything goes through the public JavaScript SDK; every command in the
Sandbox is one `sandbox.exec` (uid 501, gid 20, no root).

```text
setup     project.init(<one-file seed>) → sandbox.create → branch.fork("bench", "main") → sandbox.mount
case      exec run-case.sh: fsstress -d DIR -p P -n N -s SEED -v -V -o /tmp/fsslog/<case>-<arm>.log
          exec × k: read each gzipped per-process log back in base64 pieces (untimed)
capture   exec manifest.py build (live Workspace) → sandbox.commit (timed) → branch.fork("capture", <Commit id>)
          sandbox.mount("capture") → exec manifest.py build → exec manifest.py compare → sandbox.unmount
teardown  sandbox.unmount → sandbox.close
```

| Arm | DIR |
| --- | --- |
| `layerfs` | `<Workspace>/fss-<case>` (FUSE mount from `sandbox.mount`) |
| `sandbox-disk` | `/tmp/fss-<case>` in the Sandbox container (overlayfs), the reference |

| Case | Command | Arms |
| --- | --- | --- |
| c1, deterministic | `fsstress -p 1 -n 10000 -s 365001 -v -V` | both |
| c2, concurrent | `fsstress -p 4 -n 10000 -s 365002 -v -V` | both |
| c3, capture | after c2 has exited: manifest, Commit, fork, second mount, manifest, compare | layerfs |

- **Logs.** `-v` logs every operation with its result; `-V` leaves inode
  numbers out so the two c1 logs compare line by line; `-o` writes one log per
  process. `wall_ms` is `date` before and after fsstress inside the exec; the
  exec's client-side time is kept as `exec_ms`.
- **Outcomes.** `report.py` takes each operation's (process, opno) first result
  line: 0, an errno, `-1` (fsstress prints a raw return code for some
  ioctls), `SIGBUS`, or `skip` (no object to act on). `errors_total` counts
  everything except 0 and skip. A few operations print no line at all; the
  summary records how many outcomes were parsed out of `procs × ops`.
- **Manifest.** `manifest.py` walks the whole Workspace root without
  following symlinks: path, type, permission bits, size and SHA-256 of
  regular files, symlink target, nlink, and the hard-link group (smallest path
  sharing the inode). The capture compares the live manifest with the one
  taken in the second Workspace.
- **Policy.** Store policy 16/8/8, Disposable profile,
  `LAYERFS_CONSTRUCTION_WORKERS=1`, SDK tracing off (common/session.mjs).

## Files

| Path | Role |
| --- | --- |
| `run.sh` | One step per command: `image`, `setup`, `lock`, `case`, `capture`, `repro`, `teardown`, `cleanup`, `unlock` |
| `client/` | `setup.mjs`, `case.mjs`, `capture.mjs` (`commit` and `verify` phases), `teardown.mjs`; `common.mjs` holds the JSON exec and the read-back; `repro.mjs` sends `repro.sh` (minimal repros of the LayerFS-only failures, both arms) as a diagnostic |
| `sandbox/` | `Dockerfile`, `run-case.sh`, `manifest.py` (copied to `/opt/fsstress-bench`) |
| `report.py` | `runs.csv`, `op-errors.csv`, `capture.csv` and `summary.json` from a run's receipts |
| `image.txt` | The built image digest |
| `records/` | One record per run |

## Running

```bash
benchmark/fsstress/run.sh image
RUN=$PWD/benchmark-results/fsstress/$(date -u +%Y%m%dT%H%M%SZ)
benchmark/fsstress/run.sh lock $RUN          # exit 75: another suite measures; wait and ask again
benchmark/fsstress/run.sh setup $RUN
benchmark/fsstress/run.sh case $RUN c1 sandbox-disk 365001 1 10000
benchmark/fsstress/run.sh case $RUN c1 layerfs 365001 1 10000
benchmark/fsstress/run.sh case $RUN c2 sandbox-disk 365002 4 10000
benchmark/fsstress/run.sh case $RUN c2 layerfs 365002 4 10000
benchmark/fsstress/run.sh capture $RUN
benchmark/fsstress/run.sh teardown $RUN
benchmark/fsstress/run.sh cleanup $RUN
benchmark/fsstress/run.sh unlock $RUN
python3 benchmark/fsstress/report.py $RUN benchmark/data/fsstress/v1.0.0
```

`run.sh repro RUN` (between setup and teardown, no lock: a diagnostic, not a
measurement) writes `repro.jsonl`, one row per probe with each arm's exit and
output.

One sample per case and arm. A change to the harness, image or binaries
means a new run, not a retry.

## Limits

- **No root.** `sandbox.exec` runs as uid 501, so `chown` to other ids,
  `mknod` of character devices and `rename(WHITEOUT)` fail with EPERM in both
  arms; XFS-only ioctls (bulkstat, project ids, DIOINFO) fail with ENOTTY in
  both. Only `layerfs`-only differences count against LayerFS.
- **Divergence.** With one process and a fixed seed, fsstress is
  deterministic for a given filesystem, but an op that fails in one arm and
  succeeds in the other changes the files later ops pick, so c1 compares op
  counts per outcome and reports the first diverging operation, not a full
  op-by-op equality.
- **Cache.** Warm/unknown, not cold. The capture's live manifest reads every
  file just before the Commit.
- **Host.** Docker Desktop on an arm64 Mac, shared with other agents' builds;
  the 1-minute load is in `commands.log`. Diagnostic, not a qualifying result.
