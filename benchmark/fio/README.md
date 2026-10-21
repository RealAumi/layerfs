# fio

> **Status:** Current general guide.

Data I/O throughput, IOPS and latency: fio (Debian bookworm `apt`, 3.33)
runs nine jobs, each its own fio invocation with `--output-format=json`,
and reports bandwidth, IOPS, completion-latency percentiles, runtime and
bytes moved. One of the
[#365](https://github.com/Ephemeral-AI-Lab/layerfs/issues/365) suites; it
uses the shared harness in [benchmark/common](../common/README.md).

## Route and arms

Everything LayerFS does goes through the public JavaScript SDK. fio runs
through `sandbox.exec`, as uid 501 in the suite's Sandbox image, in the
`layerfs` and `sandbox-disk` arms. The optional third arm,
`passthrough-fuse`, is the like-for-like FUSE reference: libfuse's
`passthrough_ll` in a sibling container
([common/passthrough.sh](../common/passthrough.sh)), driven by
`docker exec` as 501:20. It is not LayerFS and makes no SDK call.

```text
setup     project.init(seed folder) → sandbox.create → branch.fork("bench", "main") → sandbox.mount
          exec: fio identity, kernel, memory, both arms' filesystems; mkdir both fio folders
next      layout per arm: exec fio --create_only=1 for seq, rand, sync (untimed)
          per job and arm: exec fio (measured) → exec read-back of fio's JSON and log (untimed)
          after every job: sandbox.commit of the layerfs Workspace, in its own client (timed)
teardown  sandbox.unmount (terminal) → sandbox.close; volumes removed

three arms (ARMS three) add, outside the SDK:
start     bench_pt_start (sibling from bench-fio:<date>-pt, passthrough_ll on /tmp/pt); pt.mjs probe
next      layout and each job in /tmp/pt/fio through bench_pt_exec, right after sandbox-disk
          FILES drop: seq and sync removed from sandbox-disk and passthrough-fuse after their last job
teardown  bench_pt_stop first (fusermount3 -u, container removed)
```

| Arm | fio folder | Filesystem |
| --- | --- | --- |
| `layerfs` | `<mounted Workspace>/fio` | LayerFS FUSE mount |
| `sandbox-disk` | `/tmp/fio` | the Sandbox container's overlayfs (reference) |
| `passthrough-fuse` | `/tmp/pt/fio` in the sibling container | libfuse `passthrough_ll` (fuse-3.14.0) over the sibling's overlayfs `/tmp/pt-src` |

Plan order: layout of each arm, then each job in the table below on
`layerfs`, then on `sandbox-disk`, then (three arms) on `passthrough-fuse`,
then the Commit. fio's JSON and log go to `/tmp/fio-out/<arm>/` in every
arm, outside the measured folder. The `passthrough-fuse` commands are the
same strings (`client/common.mjs`) with the folder changed.

**FILES drop** (three arms only). Three arms' files do not stay resident
together: the smoke run showed both FUSE arms cache file data twice (on
the mount and in the backing), so 1.6 GiB per arm becomes about 8 GiB in
all, beyond the VM's 5–7 GB available. With `drop`, once all three arms
have run the last job that uses `seq` (seq-read) or `sync` (sync-write),
that file is removed (untimed, memory figures before and after) from
`sandbox-disk` and `passthrough-fuse`. No later job reads it. The
`layerfs` copy stays, because the Commit captures all three files as the
layerfs jobs left them.

## Jobs

| Job | File | fio options |
| --- | --- | --- |
| `seq-write` | seq | `--rw=write --bs=1M --end_fsync=1` |
| `seq-read` | seq | `--rw=read --bs=1M` |
| `rand-write` | rand | `--rw=randwrite --bs=4k` |
| `rand-read` | rand | `--rw=randread --bs=4k` |
| `rand-read-4j` | rand | `--rw=randread --bs=4k --numjobs=4` (four processes on the same file) |
| `randrw-70-30` | rand | `--rw=randrw --rwmixread=70 --bs=4k` |
| `sync-write` | sync | `--rw=write --bs=4k --fsync=1` (fsync after every write) |
| `rand-write-direct` | rand | `--rw=randwrite --bs=4k --direct=1` |
| `rand-read-direct` | rand | `--rw=randread --bs=4k --direct=1` |

Every job also gets, in both arms:

```text
--name=<job> --filename=<dir>/<file> --size=<file size> --numjobs=<n> --direct=<0|1>
--ioengine=psync --iodepth=1 --fallocate=none --invalidate=0 --time_based --runtime=<RUNTIME>
--ramp_time=0 --randrepeat=1 --randseed=365 --percentile_list=50:99:99.9 --group_reporting
--output-format=json --output=/tmp/fio-out/<arm>/<job>.json
```

- `psync` throughout (libaio is installed but not used).
- `--fallocate=none`: LayerFS refuses `fallocate` (known gap).
- `--invalidate=0`: fio does not `posix_fadvise(DONTNEED)` the file before
  the job, so both arms start from the same declared state (warm own-write)
  instead of a partial, filesystem-dependent page-cache drop.
- `--time_based` with a fixed `--size`: a job loops over its file until
  `RUNTIME` seconds pass. v1.0.0 uses 20 s, seq 1 GiB, rand 512 MiB,
  sync 64 MiB (`RUN/params.env`).

**Layout.** Before any timed job, one untimed exec per arm runs fio's own
layout phase for the three files
(`fio --name=layout-<f> --filename=<dir>/<f> --size=<size> --rw=read --bs=1M --create_only=1 --fallocate=none`),
which writes every byte of each file. So every timed job, writes
included, works on an existing, fully written file.

## Files

| Path | Role |
| --- | --- |
| `run.sh` | One step per command: `image`, `setup`, `start`, `next`, `teardown`, `report` |
| `sandbox/Dockerfile` | `FROM fs-bench-computer:gawk-20261020`; fio from bookworm; `/opt/fio-identity.txt` |
| `client/common.mjs` | Each arm's folder, the output folder, the data files, the job table, fio's argv and every arm's exact shell commands |
| `client/setup.mjs` | Init, create, fork, mount (`common/session.mjs`); identity probe; both fio folders |
| `client/layout.mjs` | The untimed layout of one arm's three files |
| `client/job.mjs` | One job in `layerfs` or `sandbox-disk`: the measured fio exec and the read-back exec |
| `client/drop.mjs` | FILES drop: removes one `sandbox-disk` data file |
| `client/pt.mjs` | The `passthrough-fuse` arm on the host (plain node, no SDK): probe, layout, job, drop through `bench_pt_exec` |
| `client/commit.mjs` | The one `sandbox.commit` after the layerfs jobs |
| `client/teardown.mjs` | Unmount and close |
| `report.py` | `results.csv`, `commit.csv` and `summary.json` from the receipts; with three arms also `ratios.csv` |
| `records/` | One record per measured run |

## Running

```bash
B=benchmark/fio
$B/run.sh image                                     # once per image change
$B/run.sh pt-image                                  # three arms: once per image change
RUN=$PWD/benchmark-results/fio/$(date -u +%Y%m%dT%H%M%SZ)
$B/run.sh setup $RUN 20 1g 512m 64m measured three drop   # the three-arm run; v1.0.0 was the two-arm default
# exit 75: lock held; wait, then $B/run.sh start $RUN measured
$B/run.sh next $RUN                                 # one plan step per command; repeat until DONE
$B/run.sh teardown $RUN                             # unmount, close, volumes, lock
$B/run.sh report $RUN
```

A smoke run uses `benchmark-results/fio/smoke-<id>`, small sizes and a
short runtime (`3 64m 32m 8m smoke three drop`, no lock). `setup` with
no ARMS reproduces the v1.0.0 two-arm plan.

## Receipts

`RUN/results.jsonl` (one row per job and arm: fio's exit, the in-Sandbox
wall time around fio alone, the Sandbox's `/proc/loadavg`, the exec's
client-side time, fio's argv), `RUN/ops/<job>-<arm>.txt` (fio's log and
JSON), `RUN/layout.jsonl` and `RUN/ops/layout-<arm>.txt` (the layout),
`ledger.jsonl` (setup, probe, Commit, teardown), `params.env`,
`sandbox-identity.txt`, `identity.txt`, `deploy.env`, `commands.log` (the
host's 1-minute load per client) and each step's `.out` / `.err`. Three
arms add `pt-mount.txt`, `pt-identity.txt` (the sibling's probe), the
`pt_*` lines of `identity.txt`, and with FILES drop `drop.jsonl` and
`ops/drop-<file>-<arm>.txt`. Each read-back starts with the VM's
`MemAvailable`, `Cached` and `Dirty` after the job.

## Reading the result

- **result:** `PASS` is fio exit 0 with `error` 0 in its JSON; `FAIL` is
  anything else from fio; `HARNESS` means the exec itself failed.
- **bw_mb_s** is decimal MB/s (fio's `bw_bytes` / 10^6); **iops**,
  **runtime_s** and **bytes** are fio's per direction; **clat** percentiles
  are fio's completion latency in µs. `randrw-70-30` has a read row and a
  write row. For `sync-write`, IOPS counts write+fsync pairs and
  `sync_p50_us` / `sync_p99_us` are fio's fsync latency.
- **cache_state:** the Sandbox cannot drop caches. Every buffered job runs
  on a file this arm wrote moments earlier (layout or an earlier job):
  **warm own-write**, never cold. Residency is not checked: the two arms'
  files (1.6 GiB each) plus LayerFS's overlay backing for its copy share
  the Docker VM's page cache (about 8 GB, with other containers running),
  so part of a file may be read from below the page cache; the latencies
  show it. `--direct=1` jobs bypass the page cache for the file; what lies
  below (the LayerFS daemon's state, the VM's disk cache) is warm/unknown.
- **fsync:** the Store profile is Disposable, and a Disposable Workspace
  does not `fsync` its backing, so on `layerfs` an `fsync` returns without
  a disk flush, while `sandbox-disk` flushes, and `passthrough_ll` passes
  each `fsync` to its overlayfs backing file, which flushes too.
  `sync-write` and the end fsync of `seq-write` are therefore not
  durability-equivalent between `layerfs` and the other two arms.
- **passthrough-fuse:** `passthrough_ll` runs as root with no per-request
  credential switch (files it creates are root's) and without
  `default_permissions`; its threading (up to 10 workers) and 1.0 s cache
  timeout are its defaults, not LayerFS's. It keeps nothing beyond the
  directory, where LayerFS also records each change for Commit. Both have
  kernel writeback off. The sibling shares the Docker VM, kernel and image
  layers with the Sandbox but is a different container; its `exec_ms` is
  the host's `docker exec` time, not comparable to a `sandbox.exec`.
- **load** is the host's 1-minute load when the job's client started. One
  sample per job and arm on a shared host; treat speed as indicative.
- The Commit runs after every job, so it changes no measured read.

## Known limits

- Only `psync` with iodepth 1; no libaio/io_uring queue depths, no
  `fallocate`, no mmap engine, no verify pass.
- Read jobs are warm own-write; nothing here is a cold-read figure.
- The two SDK arms share one Sandbox; the FUSE baseline runs in a sibling
  container. All arms run one after the other, not concurrently.
- `passthrough_ll` (libfuse 3.14 example, defaults) refuses the 4 KiB
  `O_DIRECT` writes of `rand-write-direct` with `Invalid argument`
  (EINVAL; seen in the smoke run), so that job has no passthrough-fuse
  figure.
- `sandbox-disk` is overlayfs in the container, not a raw block device.
