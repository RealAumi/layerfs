# fio — run 20261019T230733Z

> **Verdict:** COMPLETE, one sample per job and arm. 18 / 18 fio runs
> passed (9 / 9 `layerfs`, 9 / 9 `sandbox-disk`): fio exit 0 and `error` 0
> in every JSON result, `O_DIRECT` included. No LayerFS-only failure.
> LayerFS was slower than the container's overlayfs in every buffered
> data job, from 1.6× (`randrw-70-30`) to 365× (`rand-write`, 4 KiB
> buffered random writes: 1,051 vs 383,392 IOPS). It matched it on
> `rand-read-direct` (9,781 vs 9,774 IOPS) and was 27.8× faster on
> `sync-write`, because a Disposable Workspace does not flush on `fsync`
> (fsync p50 1.0 µs vs 3,719 µs). One `sandbox.commit` of the three data
> files (1.68 GB logical) took 26,423.3 ms. Diagnostic host (arm64 Docker
> Desktop, 1-minute load 7.8–35.6).

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK | `sdk/js/src` in checkout `fs-bench-sdk-main` at `d6e01c7d6d`; `benchmark/fio` uncommitted (`harness_dirty_files=1`) |
| Sandbox image | `bench-fio:20261019` = `sha256:08338542b178…`, FROM `fs-bench-computer:gawk-20261020` (`sha256:66aeb6bb…`) |
| fio | `fio-3.33`, Debian bookworm package `3.33-3` (libaio1 `0.3.113-4` installed, not used) |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Sandbox | Linux 6.12.76-linuxkit aarch64, 8 CPUs, MemTotal 8,126,948 kB, MemAvailable 5,244,576 kB at setup; uid 501 gid 20; `layerfs` arm on `/workspaces/1/fio` (fuse, `default_permissions,allow_other,max_read=131072`), `sandbox-disk` arm on `/tmp/fio` (overlayfs) |
| Host | Docker 29.5.2, Docker Desktop, 8 CPUs, 8.32 GB |
| Lock | taken 23:12:46Z, released 23:26:46Z |

## Parameters

Every timed job, both arms (`--filename` is `/workspaces/1/fio/<file>` or
`/tmp/fio/<file>`):

```text
fio --name=<job> --filename=<dir>/<file> --size=<size> --rw=<rw> --bs=<bs> --numjobs=<n> --direct=<0|1> <extra> \
  --ioengine=psync --iodepth=1 --fallocate=none --invalidate=0 --time_based --runtime=20 --ramp_time=0 \
  --randrepeat=1 --randseed=365 --percentile_list=50:99:99.9 --group_reporting --output-format=json \
  --output=/tmp/fio-out/<arm>/<job>.json
```

| Job | File (size) | rw | bs | numjobs | direct | extra |
| --- | --- | --- | --- | ---: | ---: | --- |
| seq-write | seq (1g) | write | 1M | 1 | 0 | `--end_fsync=1` |
| seq-read | seq (1g) | read | 1M | 1 | 0 | |
| rand-write | rand (512m) | randwrite | 4k | 1 | 0 | |
| rand-read | rand (512m) | randread | 4k | 1 | 0 | |
| rand-read-4j | rand (512m) | randread | 4k | 4 | 0 | |
| randrw-70-30 | rand (512m) | randrw | 4k | 1 | 0 | `--rwmixread=70` |
| sync-write | sync (64m) | write | 4k | 1 | 0 | `--fsync=1` |
| rand-write-direct | rand (512m) | randwrite | 4k | 1 | 1 | |
| rand-read-direct | rand (512m) | randread | 4k | 1 | 1 | |

Layout (untimed, one exec per arm before any job):
`fio --name=layout-<f> --filename=<dir>/<f> --size=<size> --rw=read --bs=1M --create_only=1 --fallocate=none`
for seq, rand and sync; fio reported "Laying out IO file" for each and
`ls`/`du` showed 1,073,741,824 / 536,870,912 / 67,108,864 bytes fully
allocated in both arms. Layout took 6,721.5 ms on `layerfs` and 3,937.0 ms
on `sandbox-disk` (in-Sandbox wall; information only). Runtime 20 s and
the sizes were chosen from the smoke run below so each exec stays near
21 s and the Commit well inside the 115 s client limit.

## Commands

One client per step under the 115 s alarm; all 23 exited 0
(`commands.log`). `bench_setup` created the volumes at 23:07:33Z; the lock
was held by mdtest, so `start` waited three times (`perl -e 'sleep 90'`,
then asked again) and took the lock at 23:12:46Z. Setup 23:12:46 (Init
51.8 ms, create 1,820.7 ms, mount 6.8 ms); layout 23:12:55–23:13:11; jobs
23:13:11–23:26:06 at host 1-minute load 7.84–35.64; Commit 23:26:12
(load 9.67); teardown 23:26:45–23:26:46 (unmount 104.8 ms, close
320.6 ms). Every fio exec took 20.3–21.7 s in-Sandbox wall.

Two incidents, neither touching a measured fio exec:

- **Docker removal stall.** The `rand-write-direct` `sandbox-disk` client
  finished its work at 23:19:53 (fio exec 20,650 ms, read-back and
  `results.jsonl` row written, container exit 0), but Docker Desktop kept
  the `--rm` container in "removing" until about 23:24:50, so the client
  step shows 23:19:31–23:24:51 in `commands.log`. Containers of other
  sessions on the host were stuck in the same state at the time. The 115 s
  `perl alarm` in `bench_client` did not stop it: the alarm survives the
  `exec` into the `docker` CLI, which, as a Go program, ignores SIGALRM.
  My Bash command that ran four plan steps in a row passed 120 s because
  of this and was moved to the background by the tool; it finished on its
  own (exit 0) after the next step.
- **Probe container.** While diagnosing the stall I ran one
  `docker run --rm --entrypoint true bench-fio:20261019` (about 1 s) at
  about 23:24:51, as the `rand-read-direct` `layerfs` client was starting.
  It overlapped at most the first second of that client's set-up, not
  known to overlap its fio exec.

## Result

Bandwidth is decimal MB/s (fio `bw_bytes` / 10^6); IOPS, runtime and bytes
are fio's own; clat is fio's completion latency in µs. Ratio is layerfs ÷
sandbox-disk bandwidth (above 1 is faster on LayerFS). Load is the host's
1-minute load when each client started. Every fio runtime was
20.001–21.106 s.

| Job | layerfs MB/s | disk MB/s | layerfs IOPS | disk IOPS | Ratio | LayerFS | clat p50 lf / disk | clat p99 lf / disk | clat p99.9 lf / disk | MiB moved lf / disk | Load lf / disk |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |
| seq-write | 140.29 | 2,332.05 | 134 | 2,224 | 0.060 | 16.6× slower | 4,489 / 230 | 39,584 / 5,866 | 692,060 / 15,663 | 2,676 / 46,940 | 20.89 / 19.82 |
| seq-read | 239.59 | 4,374.07 | 228 | 4,171 | 0.055 | 18.3× slower | 2,769 / 206 | 34,341 / 1,028 | 173,015 / 4,145 | 4,570 / 83,433 | 18.27 / 16.78 |
| rand-write | 4.30 | 1,570.37 | 1,051 | 383,392 | 0.003 | 365× slower | 346.1 / 1.5 | 7,111 / 6.8 | 36,438 / 80.4 | 82 / 29,954 | 14.58 / 18.90 |
| rand-read | 2.54 | 11.19 | 619 | 2,733 | 0.227 | 4.4× slower | 643.1 / 160.8 | 9,634 / 3,228 | 39,060 / 14,090 | 48 / 214 | 18.92 / 17.54 |
| rand-read-4j | 1.43 | 38.98 | 349 | 9,517 | 0.037 | 27.3× slower | 4,424 / 134.1 | 106,431 / 3,752 | 851,444 / 20,316 | 27 / 744 | 16.07 / 35.64 |
| randrw-70-30 read | 2.98 | 4.74 | 727 | 1,156 | 0.629 | 1.6× slower | 132.1 / 378.9 | 10,027 / 6,521 | 29,229 / 23,200 | 57 / 90 | 29.38 / 24.92 |
| randrw-70-30 write | 1.31 | 2.06 | 319 | 503 | 0.636 | 1.6× slower | 150.5 / 7.3 | 9,896 / 199.7 | 40,108 / 839.7 | 25 / 39 | 29.38 / 24.92 |
| sync-write | 21.70 | 0.78 | 5,298 | 190 | 27.821 | 27.8× faster | 100.9 / 14.0 | 1,384 / 148.5 | 4,178 / 2,179 | 414 / 15 | 21.36 / 19.15 |
| rand-write-direct | 1.85 | 20.03 | 451 | 4,890 | 0.092 | 10.8× slower | 1,286 / 156.7 | 12,386 / 1,417 | 42,205 / 4,014 | 35 / 387 | 16.54 / 17.93 |
| rand-read-direct | 40.06 | 40.04 | 9,781 | 9,774 | 1.000 | same | 72.2 / 39.7 | 913.4 / 395.3 | 2,540 / 1,909 | 764 / 764 | 7.84 / 10.93 |

`sync-write` fsync latency (fio `sync`): p50 1.0 µs, p99 14.9 µs on
`layerfs`; p50 3,719.2 µs, p99 30,801.9 µs on `sandbox-disk`. The
`layerfs` fsync does no disk flush (Disposable Workspace backing), so that
row is not a durability-equivalent comparison.

Cache state: warm own-write (every file was written by its arm minutes
earlier), never cold, residency not checked. The buffered 4 KiB reads on
`sandbox-disk` (`rand-read` p50 160.8 µs, `rand-read-4j` p50 134.1 µs) and
on `layerfs` (p50 643.1 µs) are far above a page-cache hit, so a large part
of those reads missed the page cache (going to the VM disk, or on
`layerfs` to the daemon): the two arms' 3.2 GiB of files
plus LayerFS's own overlay backing did not all stay resident in the
Sandbox's 5.2 GB available memory on a host running other containers.
`--direct=1` rows bypass the page cache; below it is warm/unknown. One
sample each on a heavily loaded host; indicative only.

### Commit

After every job, one `sandbox.commit` in its own client (not inside any
timed job): **Committed in 26,423.3 ms** for the three data files as the
layerfs jobs left them; commit `12fab4e72a…`, base `32820d7762…`, logical
1,677,721,655 B, newCanonical 1,682,987,992 B, newStored 1,501,587,082 B,
newMetadata 2,979,507 B. fio's buffers are pseudo-random (no
`buffer_compress_percentage`), so the stored bytes are close to logical.

## Other runs

- `smoke-20261019T230418Z`: FAILED at setup, harness bug: `run.sh` used a
  variable named `runtime`, which overwrote `lib.sh`'s runtime image name,
  so `client.sh` tried to run image `3`. Fixed (renamed to `secs`);
  receipts kept; volumes removed. Not a measurement.
- `smoke-20261019T230434Z`: the whole plan at 3 s per job with seq 64m,
  rand 32m, sync 8m; 18 / 18 PASS; Commit 1,854.1 ms for 109 MB logical.
  Used to check the harness, O_DIRECT in both arms and the sizes. Not a
  measurement. Its Commit client (23:06:51–23:06:53) overlapped mdtest's
  lock take (23:06:52) by about one second; whether that touched an mdtest
  operation is for mdtest's record to say.
  Diagnostic observation only: at 32 MiB the `layerfs` buffered 4 KiB
  `rand-read` was served at p50 0.9 µs and `rand-write` ran at 9,382 IOPS
  (p50 78.3 µs), against 619 and 1,051 IOPS here with a 512 MiB file under
  higher load. One sample each, different sizes and load; the cause
  (memory pressure, load, or a per-write cost that grows with file size)
  is not established by this run.

No measured run failed or was restarted.

## Receipts

`benchmark-results/fio/20261019T230733Z/` (Git-ignored): `identity.txt`,
`deploy.env`, `params.env`, `commands.log`, `ledger.jsonl`,
`results.jsonl`, `layout.jsonl`, `sandbox-identity.txt`, `ops/*.txt`
(fio's log and JSON per job and arm, and each arm's layout output),
`results.csv`, `commit.csv`, `summary.json`, each step's `.out` / `.err`.
Volumes removed 23:26:46Z; no `bench-fio-*` container or volume remains.
