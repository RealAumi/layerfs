# fio release data

> **Status:** Current general guide.

One folder per release with fio results: fio 3.33 (Debian bookworm) runs
nine data I/O jobs, each its own invocation, through `sandbox.exec` in a
LayerFS Workspace (`layerfs`) and in the same Sandbox's own overlayfs
`/tmp` (`sandbox-disk`) as the reference. A later three-arm run adds a
FUSE baseline (`passthrough-fuse`); see [Three-arm run](#three-arm-run-v100-build-fuse-baseline-added).
The harness is [benchmark/fio](../../fio/README.md).

## v1.0.0

[v1.0.0](v1.0.0/): 20 s per job (`--time_based`, `--ramp_time=0`), `psync`
at iodepth 1, files laid out before the timed jobs: seq 1 GiB, rand
512 MiB, sync 64 MiB. Ratio is LayerFS bandwidth ÷ sandbox-disk bandwidth:
1.0 is the same speed, below 1.0 is slower on LayerFS, above 1.0 faster.

| Job | layerfs MB/s | sandbox-disk MB/s | layerfs IOPS | sandbox-disk IOPS | Ratio | In plain words |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| seq-write (1 MiB, end fsync) | 140.29 | 2,332.05 | 134 | 2,224 | 0.060 | LayerFS writes at about 1/17 the speed |
| seq-read (1 MiB) | 239.59 | 4,374.07 | 228 | 4,171 | 0.055 | LayerFS reads at about 1/18 the speed |
| rand-write (4 KiB) | 4.30 | 1,570.37 | 1,051 | 383,392 | 0.003 | LayerFS does about 1/365 as many writes |
| rand-read (4 KiB) | 2.54 | 11.19 | 619 | 2,733 | 0.227 | LayerFS does about 1/4.4 as many reads |
| rand-read-4j (4 KiB, 4 jobs) | 1.43 | 38.98 | 349 | 9,517 | 0.037 | LayerFS does about 1/27 as many reads |
| randrw-70-30 read | 2.98 | 4.74 | 727 | 1,156 | 0.629 | LayerFS does about 1/1.6 as many reads |
| randrw-70-30 write | 1.31 | 2.06 | 319 | 503 | 0.636 | LayerFS does about 1/1.6 as many writes |
| sync-write (4 KiB, fsync each) | 21.70 | 0.78 | 5,298 | 190 | 27.821 | LayerFS is 27.8× faster, because its fsync does not flush (see below) |
| rand-write-direct (4 KiB, O_DIRECT) | 1.85 | 20.03 | 451 | 4,890 | 0.092 | LayerFS does about 1/11 as many writes |
| rand-read-direct (4 KiB, O_DIRECT) | 40.06 | 40.04 | 9,781 | 9,774 | 1.000 | the same speed |

Completion latency p50 / p99 (µs), layerfs vs sandbox-disk: seq-write
4,489 / 39,584 vs 230 / 5,866; seq-read 2,769 / 34,341 vs 206 / 1,028;
rand-write 346 / 7,111 vs 1.5 / 6.8; rand-read 643 / 9,634 vs 161 / 3,228;
rand-read-4j 4,424 / 106,431 vs 134 / 3,752; sync-write 101 / 1,384 vs
14 / 149 (plus fsync p50 1.0 µs vs 3,719 µs); rand-write-direct 1,286 /
12,386 vs 157 / 1,417; rand-read-direct 72 / 913 vs 40 / 395.

**v1.0.0 in one line:** all 18 runs passed (fio exit 0, `error` 0,
`O_DIRECT` included) with no LayerFS-only failure. LayerFS was slower than
the container's overlayfs in every buffered data job, from 1.6× (mixed
70/30 random) to about 365× (4 KiB buffered random writes, 1,051 vs
383,392 IOPS); about 17–18× on 1 MiB sequential write and read. It matched
overlayfs on O_DIRECT random reads and was 27.8× faster on 4 KiB writes
with an fsync after each, only because a Disposable Workspace's fsync does
no disk flush. One `sandbox.commit` of the three data files (1.68 GB
logical, 1.50 GB newly stored) took 26,423.3 ms.

## Comparison scope: the reference is not like-for-like

`sandbox-disk` is the container's own overlayfs `/tmp`: the kernel's
in-memory page cache with no FUSE hop, no history and nothing kept after
the container goes. It is a ceiling for this host, not a peer. A LayerFS
Workspace differs by design:

- every operation is a FUSE request to the daemon (any FUSE filesystem pays
  this round trip);
- kernel writeback caching is off under the FUSE contract, so each buffered
  write reaches the daemon, where the reference only copies into page cache;
- each change is recorded in the Workspace overlay so a Commit can capture
  it, and the files remain mountable as history afterwards.

The ratios below are therefore the cost of those properties against the
kernel's fastest local path, not a ranking against another filesystem of
the same kind. No FUSE baseline (for example a passthrough FUSE
filesystem) was measured in v1.0.0.

## Three-arm run (v1.0.0 build, FUSE baseline added)

[v1.0.0/three-arm](v1.0.0/three-arm/): run `20261020T000148Z`, the same
build, image, nine jobs and parameters as v1.0.0, plus a third arm,
`passthrough-fuse`: libfuse's `passthrough_ll` (fuse-3.14.0, its
defaults) over a plain directory in a sibling container on the same
Docker VM. fio runs there as uid 501 through `docker exec`. It is the
like-for-like FUSE reference; it is not LayerFS and uses no SDK. Per job
the arms run `layerfs`, `sandbox-disk`, `passthrough-fuse`, one sample
each. Ratios are bandwidth ratios; above 1 means the first arm is
faster. The like-for-like figure is **LayerFS ÷ passthrough-fuse**;
LayerFS ÷ overlayfs is kept for reference, and passthrough-fuse ÷
overlayfs is the cost of FUSE alone.

| Job | MB/s lf / pt / disk | IOPS lf / pt / disk | p50 µs lf / pt / disk | p99 µs lf / pt / disk | **LayerFS ÷ passthrough-fuse** | LayerFS ÷ overlayfs | passthrough-fuse ÷ overlayfs |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| seq-write (1 MiB, end fsync) | 514.04 / 1,669.23 / 3,258.41 | 490 / 1,592 / 3,108 | 1,433.6 / 464.9 / 232.4 | 13,172.7 / 3,424.3 / 1,003.5 | **0.308** | 0.158 | 0.512 |
| seq-read (1 MiB) | 5,030.87 / 6,228.39 / 6,111.06 | 4,798 / 5,940 / 5,828 | 166.9 / 148.5 / 152.6 | 659.5 / 577.5 / 444.4 | **0.808** | 0.823 | 1.019 |
| rand-write (4 KiB) | 33.12 / 81.99 / 2,594.71 | 8,087 / 20,017 / 633,475 | 79.4 / 38.1 / 1.2 | 774.1 / 234.5 / 3.2 | **0.404** | 0.013 | 0.032 |
| rand-read (4 KiB) | 3,000.10 / 2,127.73 / 2,546.86 | 732,447 / 519,465 / 621,793 | 1.0 / 1.1 / 1.2 | 4.5 / 31.9 / 5.2 | **1.410** | 1.178 | 0.835 |
| rand-read-4j (4 KiB, 4 jobs) | 12,572.62 / 10,793.41 / 10,681.50 | 3,069,486 / 2,635,110 / 2,607,788 | 1.0 / 1.1 / 1.3 | 1.5 / 1.8 / 1.8 | **1.165** | 1.177 | 1.010 |
| randrw-70-30 read | 101.52 / 45.54 / 1,621.51 | 24,786 / 11,117 / 395,877 | 1.8 / 50.9 / 1.4 | 10.7 / 264.2 / 4.9 | **2.229** | 0.063 | 0.028 |
| randrw-70-30 write | 43.58 / 19.53 / 694.93 | 10,641 / 4,769 / 169,660 | 74.2 / 43.8 / 1.5 | 321.5 / 181.2 / 5.5 | **2.231** | 0.063 | 0.028 |
| sync-write (4 KiB, fsync each) ¹ | 57.97 / 8.39 / 11.47 | 14,152 / 2,049 / 2,800 | 61.7 / 32.1 / 3.2 | 185.3 / 140.3 / 12.5 | **6.909** | 5.054 | 0.731 |
| rand-write-direct (4 KiB, O_DIRECT) ² | 49.58 / FAIL / 70.30 | 12,104 / — / 17,162 | 66.0 / — / 46.3 | 370.7 / — / 156.7 | **—** | 0.705 | — |
| rand-read-direct (4 KiB, O_DIRECT) | 54.42 / 36.58 / 70.69 | 13,287 / 8,931 / 17,259 | 68.1 / 77.3 / 48.9 | 122.4 / 321.5 / 162.8 | **1.488** | 0.770 | 0.517 |

¹ Not durability-equivalent. `passthrough_ll`'s fsync really flushes to
its overlayfs backing file (fsync p50 197.6 µs), as `sandbox-disk` does
(122.4 µs). A Disposable LayerFS Workspace's fsync does not flush
(0.9 µs). The end fsync of `seq-write` differs the same way.

² `passthrough_ll` refused the O_DIRECT 4 KiB writes:
`fio: io_u error on file /tmp/pt/fio/rand: Invalid argument: write offset=32378880, buflen=4096`
(fio `error` 22, also in the smoke run). This is a baseline failure, not
a LayerFS one; LayerFS passed. There is no like-for-like figure for this
job.

**In plain words, against the FUSE baseline:**

- **LayerFS trails** on 1 MiB sequential write (about 1/3.2 the speed),
  1 MiB sequential read (0.81×) and 4 KiB buffered random writes (0.40×:
  8,087 vs 20,017 IOPS, p50 79 vs 38 µs). With kernel writeback off in
  both, each buffered write is a request to the FUSE server, and LayerFS
  takes longer per request (it also records each change for Commit).
- **LayerFS is ahead** on the mixed 70/30 random job (2.23×; its reads
  were page-cache hits at p50 1.8 µs, `passthrough_ll`'s went to the
  server at p50 50.9 µs) and on O_DIRECT random reads (1.49×).
- **Effectively a tie on the FUSE side** for the cached random reads
  (`rand-read` 1.41×, `rand-read-4j` 1.17×). All three arms served them
  from the page cache at p50 1.0–1.3 µs, so these rows measure the
  kernel, not the FUSE server.
- **Not comparable:** `sync-write` (fsync semantics, ¹) and
  `rand-write-direct` (baseline failure, ²).
- **FUSE alone** (passthrough-fuse ÷ overlayfs) costs about half the
  bandwidth on `seq-write` and O_DIRECT reads and about 1/31 to 1/36 on
  buffered 4 KiB random writes and the mixed job. Part of LayerFS's gap to
  overlayfs is therefore the cost of any FUSE filesystem.

One `sandbox.commit` (LayerFS only) of the three data files after the
jobs took 24,831.5 ms. It committed 1.68 GB logical, of which 1.15 GB was
newly stored. 26 / 27 fio runs passed; the only failure is ², and there
is no LayerFS-only failure.

**File removal.** Three arms' files plus both FUSE arms' backing copies
come to about 8 GiB, beyond the VM's available memory. The smoke run
showed that a FUSE arm caches a file on the mount and again in its
backing. So once all three arms had run the last job that uses `seq`
(`seq-read`) or `sync` (`sync-write`), that file was removed (untimed)
from `sandbox-disk` and `passthrough-fuse`. No later job reads a removed
file. The `layerfs` copies stayed for the Commit. During the jobs the VM
then had `MemAvailable` 6.1–7.0 GiB.

**Not comparable with the two-arm v1.0.0 table above.** That run had
less free memory (5.2 GB at setup against 7.1 GB), higher load
(7.8–35.6 against 6.5–19.9) and no file removal. Both LayerFS and
overlayfs figures moved a lot between the two runs; for example,
LayerFS's `rand-write` went from 1,051 to 8,087 IOPS and overlayfs's
`rand-read` p50 from 160.8 to 1.2 µs. Compare arms within one run, not
across runs. The record is
[benchmark/fio/records/20261020T000148Z.md](../../fio/records/20261020T000148Z.md).

**Fairness notes (facts).** `passthrough_ll` runs as root with no
per-request credential switch, so files it creates are root's, and it
does not use `default_permissions` (LayerFS does). Its threading (up to
10 workers) and cache timeout (1.0 s) are its defaults, not LayerFS's.
It keeps nothing beyond the directory; LayerFS also records each change
for Commit. Both have kernel writeback off. The sibling container and
the Sandbox share the Docker VM, kernel and image layers, but they are
different containers.

`v1.0.0/three-arm/` holds `results.csv` (as above, `arm` now also
`passthrough-fuse`), `ratios.csv` (per job and direction: each arm's
MB/s, IOPS, p50, p99 and result, plus the three ratios), `commit.csv`,
`environment.csv` (including the `pt_*` identity lines) and `receipts/`
copied unchanged, with `drop.jsonl`, `pt-identity.txt`, `pt-mount.txt`
and the run's `record.md`.

## How to read it

- `bw_mb_s` is decimal MB/s (fio's `bw_bytes` / 10^6). IOPS, runtime and
  bytes are fio's per direction; clat percentiles are fio's completion
  latency in µs. `randrw-70-30` has a read row and a write row.
- `sync-write` IOPS counts write+fsync pairs; `sync_p50_us` and
  `sync_p99_us` are fio's fsync latency. The Store profile is Disposable,
  whose Workspace backing is never fsynced, so the `layerfs` fsync returns
  in about 1 µs while `sandbox-disk` flushes the VM disk (about 3.7 ms).
  This row and the end fsync of `seq-write` are not durability-equivalent.
- `cache_state`: the Sandbox cannot drop caches. Buffered jobs read and
  write files their arm wrote minutes earlier: **warm own-write**, never
  cold. Residency was not checked, and it was not complete: both arms'
  files (3.2 GiB) plus LayerFS's overlay backing exceeded what stayed
  resident in the Sandbox's 5.2 GB available memory on a host running other
  containers, and the buffered 4 KiB read latencies (p50 134–643 µs) show
  most of those reads missed the page cache in both arms (going to
  the VM disk, or on `layerfs` to the daemon). O_DIRECT
  rows bypass the page cache; below it is warm/unknown.
- `load` is the host's 1-minute load when the job's client started
  (7.8–35.6 during the jobs). One sample per job and arm on a heavily
  loaded Docker Desktop host. Indicative only.

Each folder holds:

| File | What it is |
| --- | --- |
| `results.csv` | One row per job, arm and direction: `job, arm, rw, bs, numjobs, direct, sync, runtime_s, size, bw_mb_s, iops, clat_p50_us, clat_p99_us, clat_p999_us, cache_state, load`, then `ddir, bytes, clat_mean_us, sync_p50_us, sync_p99_us, ioengine, result, fio_error, exit, wall_ms` (in-Sandbox wall around fio), `exec_ms` (the exec's client-side time) and `sandbox_loadavg` (the Sandbox's `/proc/loadavg` at start) |
| `commit.csv` | The one `sandbox.commit` after the layerfs jobs: time, load, kind, ids, logical and new bytes |
| `environment.csv` | Source, binaries, images, fio version and args, files, layout, Store, host, load |
| `receipts/` | The run's receipts, unchanged: `identity.txt`, `deploy.env`, `params.env`, `commands.log`, `ledger.jsonl`, `results.jsonl`, `layout.jsonl`, `sandbox-identity.txt`, `summary.json`, `ops/*.txt` (fio's log and JSON per job and arm, each arm's layout output), and the run's `record.md` |

The CSVs are derived from the receipts by `benchmark/fio/report.py`;
everything else is copied unchanged from `benchmark-results/fio/`.

## Limits

- `psync` at iodepth 1 only: no libaio/io_uring queue depth, no mmap
  engine, no `fallocate` (LayerFS refuses it), no verify pass.
- Nothing here is a cold-read figure, and full residency was not reached,
  so the buffered read rows mix page-cache hits and lower-level reads in
  proportions the run did not measure.
- fio's buffers are pseudo-random, so the Commit's stored bytes are close
  to logical: a fair storage case for incompressible data.
- `sandbox-disk` is the container's overlayfs on the Docker Desktop VM
  disk, not a raw block device; both arms share one Sandbox and run one
  after the other.
- v1.0.0 was measured at `main` `e5c7aaae05` (the fs-bench v1.0.0 build)
  on Docker Desktop on an arm64 Mac, Disposable Store with policy 16/8/8.
