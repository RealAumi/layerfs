# smallfile

> **Status:** Current general guide.

Small-file operation throughput: distributed-system-analysis/smallfile
drives many 4 KiB files through one operation at a time (create, read,
append, stat, chmod, rename, delete-renamed, mkdir, rmdir) with several
threads and reports files/s, MiB/s and the elapsed time it measured. One of
the [#365](https://github.com/Ephemeral-AI-Lab/layerfs/issues/365) suites;
it uses the shared harness in [benchmark/common](../common/README.md).

## Route and arms

Everything LayerFS does goes through the public JavaScript SDK. In the
`layerfs` and `sandbox-disk` arms smallfile runs only through
`sandbox.exec`, as uid 501 in the suite's Sandbox image. The
`passthrough-fuse` arm is the one exception: it is not LayerFS, uses no SDK
call, and runs in a sibling container through `docker exec`
([common/passthrough.sh](../common/README.md#fuse-baseline-arm-passthroughsh)).

```text
setup     project.init(seed folder) → sandbox.create → branch.fork("bench", "main") → sandbox.mount
          exec: smallfile identity, kernel, both arms' filesystems; mkdir both top folders
          then bench_pt_start: sibling container, passthrough_ll mounted at /tmp/pt; mkdir /tmp/pt/sf
next      per operation and arm: smallfile_cli.py (measured) → read-back (untimed); sandbox.exec
          for layerfs and sandbox-disk, bench_pt_exec for passthrough-fuse
          after the layerfs create: sandbox.commit of the Workspace, in its own client (timed)
teardown  bench_pt_stop → sandbox.unmount (terminal) → sandbox.close; volumes removed
```

| Arm | smallfile `--top` | Filesystem |
| --- | --- | --- |
| `layerfs` | `<mounted Workspace>/sf` | LayerFS FUSE mount |
| `sandbox-disk` | `/tmp/sf` | the Sandbox container's overlayfs (reference) |
| `passthrough-fuse` | `/tmp/pt/sf` in the sibling container | libfuse `passthrough_ll` over `/tmp/pt-src` (the sibling's overlayfs), the like-for-like FUSE reference |

Plan order: `create` layerfs, `commit`, `create` sandbox-disk, `create`
passthrough-fuse, then for `read`, `append`, `stat`, `chmod`, `rename`,
`delete-renamed`, `mkdir` and `rmdir`: layerfs, then sandbox-disk, then
passthrough-fuse, so the three arms of one operation run close together.
The `sandbox.commit` is LayerFS only. Because it follows the layerfs
`create`, the layerfs `read` runs after the Commit and reads the created
files from the committed base, not the Workspace overlay; v1.0.0 had the
same order and it is kept. Each operation is its own
`smallfile_cli.py --operation <op>` over the same top folder, so each one
works on the files the previous one left. smallfile's output, its
`--output-json` result and its per-thread logs (`TMPDIR`) go to
`/tmp/sf-out/<arm>/<op>/` in every arm (in the sibling's own `/tmp` for
passthrough-fuse), outside the measured folder.

The passthrough-fuse sibling is the suite's Sandbox image plus
`passthrough_ll` (`bench-smallfile:<date>-pt`, `run.sh pt-image`), with
`/dev/fuse` and `CAP_SYS_ADMIN`, on the same Docker VM and kernel. Root
runs `passthrough_ll -o source=/tmp/pt-src -o allow_other /tmp/pt` with its
defaults (up to 10 worker threads, cache timeout 1.0 s, writeback off);
smallfile runs as uid 501, gid 20, `HOME=/tmp`, under a 115 s limit, timed
the same way as the other arms. `exec_ms` is the `docker exec` time seen by
the host there, not a `sandbox.exec` time.

## Parameters

Every operation in every arm:

```text
python3 /opt/smallfile/smallfile_cli.py --top <top> --operation <op> --threads 4 \
  --files <FILES> --file-size 4 --stonewall N --finish Y --output-json <out>/result.json
```

`--stonewall N --finish Y` make every thread process all of its files, so
`pctFilesDone` is 100 and the next operation finds the complete set. The
rest are smallfile's defaults: 100 files per directory, 10 directories per
directory, record size = file size, no fsync, `--verify-read Y`, fixed
size, compressible data. `FILES` is fixed per run in `RUN/params.env` and
`identity.txt`; v1.0.0 uses 25,000 per thread (100,000 files, 390.6 MiB),
chosen from the smoke runs so the slowest LayerFS exec stays well under
100 s.

## Files

| Path | Role |
| --- | --- |
| `run.sh` | One step per command: `image`, `pt-image`, `setup`, `start`, `next`, `teardown`, `report`; the passthrough-fuse operation (`pt_op`) |
| `sandbox/Dockerfile` | `FROM fs-bench-computer:gawk-20261020`; python3-yaml from bookworm; smallfile at `aa2519de5bf0b3b383db2c31eacbf8ac4328e19c` in `/opt/smallfile`; `/opt/smallfile-identity.txt` |
| `client/common.mjs` | Each arm's top folder, the output folder, the smallfile command |
| `client/setup.mjs` | Init, create, fork, mount (`common/session.mjs`); identity probe; both top folders |
| `client/op.mjs` | One operation in the layerfs or sandbox-disk arm: the measured smallfile exec and the read-back exec |
| `client/commit.mjs` | The one `sandbox.commit` after the layerfs create |
| `client/teardown.mjs` | Unmount and close |
| `report.py` | `results.csv`, `commit.csv` and `summary.json` from the receipts |
| `records/` | One record per measured run |

## Running

```bash
B=benchmark/smallfile
$B/run.sh image                               # once per image change
$B/run.sh pt-image                            # after image: the passthrough-fuse sibling image
RUN=$PWD/benchmark-results/smallfile/$(date -u +%Y%m%dT%H%M%SZ)
$B/run.sh setup $RUN 25000 measured           # exit 75: lock held; wait, then $B/run.sh start $RUN measured
$B/run.sh next $RUN                           # one plan step per command; repeat until DONE
$B/run.sh teardown $RUN                       # sibling, unmount, close, volumes, lock
$B/run.sh report $RUN
```

A smoke run uses `benchmark-results/smallfile/smoke-<id>`, a small `FILES`
(1000) and `smoke` (no lock). The v1.0.0 two-arm plan is
`setup $RUN 25000 measured "layerfs sandbox-disk"`; a run whose
`params.env` has no `arms` (v1.0.0) also plans those two. Run `teardown`
on every path, after a failure too: it removes the sibling first.

## Receipts

`RUN/results.jsonl` (one row per operation and arm: smallfile's exit, the
in-Sandbox wall time around smallfile alone, the Sandbox's `/proc/loadavg`,
the exec's client-side time), `RUN/ops/<op>-<arm>.txt` (smallfile's output,
its JSON result, and after a failure its per-thread log tails),
`ledger.jsonl` (setup, probe, Commit, teardown), `params.env`,
`sandbox-identity.txt`, `pt-identity.txt` and `pt-mount.txt` (the sibling's
smallfile identity, kernel, uid and mount), `identity.txt` (with the
`pt_*` passthrough image and `passthrough_ll` identity), `deploy.env`,
`commands.log` (the host's 1-minute load per step) and each step's
`.out` / `.err`.

## Reading the result

- **result:** `PASS` is smallfile exit 0, status `Success` and 100 % of
  files processed; `FAIL` is anything else from smallfile; `HARNESS` means
  the exec itself failed.
- **files_per_s, mb_per_s, elapsed_s, pct_files_done** are smallfile's own
  (`filesPerSec`, `MiBps`, `elapsed`, `pctFilesDone`). `elapsed` runs from
  smallfile's starting gate to the last thread's finish; `mb_per_s` is MiB/s
  and exists only for the data operations (create, read, append).
- **wall_ms** is `date +%s%N` around the whole `smallfile_cli.py` process
  inside the Sandbox, so exec overhead is excluded but smallfile's own
  start-up (about 3.6 s of Python start, directory setup and gate polling in
  the smoke runs) is included. Compare arms on files/s.
- **load** is the host's 1-minute load when the operation's client started.
  One sample per operation and arm on a shared host; treat speed as
  indicative. Cache state: warm/unknown, not cold.
- The Commit after the layerfs create also changes what the layerfs `read`
  reads: the created files are in the committed base afterwards, not the
  Workspace's overlay.
- Three-arm ratios: LayerFS ÷ passthrough-fuse is the like-for-like FUSE
  comparison; LayerFS ÷ sandbox-disk is kept for reference;
  passthrough-fuse ÷ sandbox-disk is the cost of FUSE alone.

## Known limits

- smallfile's multi-host mode, response-time statistics (numpy/scipy),
  xattr, symlink, overwrite, truncate, readdir and ls-l operations are not
  run.
- The arms run one after the other, not concurrently. `layerfs` and
  `sandbox-disk` share one Sandbox; `passthrough-fuse` runs in a different
  container that shares the Docker VM, kernel and image layers.
- `sandbox-disk` is overlayfs in the container, not a raw block device.
- `passthrough_ll` is not tuned to LayerFS: it runs as root with no
  per-request credential switch (files it creates are owned by root) and
  without `default_permissions`; its threads (up to 10) and cache timeout
  (1.0 s) are its defaults. It keeps nothing beyond the directory, where
  LayerFS also records each change for Commit. Both have writeback off.
- `passthrough_ll` (libfuse 3.14.0's example) finds inodes by a linear walk
  of one list under one mutex (`lo_find`), so its per-request cost grows
  with the inodes the kernel holds; at 100,000 files its create ran at
  about a third of its 4,000-file rate in the smoke runs.
