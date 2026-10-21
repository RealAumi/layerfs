# fio — run 20261020T000148Z (three arms)

> **Verdict:** COMPLETE, one sample per job and arm. 26 / 27 fio runs
> passed: 9 / 9 `layerfs`, 9 / 9 `sandbox-disk`, 8 / 9 `passthrough-fuse`.
> The one failure is in the FUSE baseline, not LayerFS: `passthrough_ll`
> rejected the 4 KiB `O_DIRECT` writes of `rand-write-direct` with
> `Invalid argument` (fio `error` 22). No LayerFS-only failure.
> Against the like-for-like FUSE baseline, LayerFS trailed on 1 MiB
> sequential write (0.31×), 1 MiB sequential read (0.81×) and 4 KiB
> buffered random write (0.40×). It was ahead on the mixed 70/30 random
> job (2.23×) and on `O_DIRECT` random reads (1.49×). It was also ahead on
> the cached 4 KiB random reads (1.41×, 1.17×), but there all three arms
> served reads from the page cache at p50 1.0–1.1 µs. `sync-write` was
> 6.9× faster on LayerFS only because its Disposable fsync does not
> flush. One `sandbox.commit` of the three data files took 24,831.5 ms.
> Diagnostic host (arm64 Docker Desktop, 1-minute load 6.50–19.89).

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK | `sdk/js/src` in checkout `fs-bench-sdk-main` at `d00c00e44e`; `benchmark/fio` uncommitted (`harness_dirty_files=7` at setup; only `README.md` changed after setup) |
| Sandbox image | `bench-fio:20261019` = `sha256:08338542b178…` (the v1.0.0 image; digest re-checked before the run), FROM `fs-bench-computer:gawk-20261020` (`sha256:66aeb6bb…`) |
| FUSE baseline image | `bench-fio:20261019-pt` = `sha256:bf55646461…`, FROM the Sandbox image above, plus libfuse `passthrough_ll` at `3f65bb699cd2…` (fuse-3.14.0; `passthrough_ll.c` `b8081e5f…`, binary `f928a291…`), libfuse3 `3.14.0-4`, gcc 12.2.0 |
| fio | `fio-3.33`, Debian bookworm package `3.33-3`, the same bytes in both containers |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Sandbox | Linux 6.12.76-linuxkit aarch64, 8 CPUs, MemTotal 8,126,948 kB, MemAvailable 7,134,856 kB at setup; uid 501 gid 20; `layerfs` arm on `/workspaces/1/fio` (fuse, `default_permissions,allow_other,max_read=131072`), `sandbox-disk` arm on `/tmp/fio` (overlayfs) |
| Sibling | `bench-fio-20261020T000148Z-pt` (`/dev/fuse`, `CAP_SYS_ADMIN`, apparmor unconfined); `passthrough_ll -o source=/tmp/pt-src -o allow_other /tmp/pt` as root (`fuse.passthrough_ll rw,nosuid,nodev,relatime,user_id=0,group_id=0,allow_other`); fio as 501:20, `HOME=/tmp`, through `bench_pt_exec` from `client/pt.mjs` (host node v24.21.0) |
| Host | Docker 29.5.2, Docker Desktop, 8 CPUs, 8.32 GB |
| Lock | taken 00:18:06Z, released 00:28:48Z (after teardown and `bench_pt_stop`) |

## Parameters

The v1.0.0 jobs unchanged: nine fio jobs (ten result rows, since
`randrw-70-30` has a read and a write row), `psync`, iodepth 1,
`--fallocate=none`, `--invalidate=0`, 20 s each with ramp 0, seed 365,
seq 1 GiB, rand 512 MiB, sync 64 MiB. Every arm runs the same command
string from `client/common.mjs`; only `--filename` differs
(`/workspaces/1/fio/<file>`, `/tmp/fio/<file>`, `/tmp/pt/fio/<file>`):

```text
fio --name=<job> --filename=<dir>/<file> --size=<size> --rw=<rw> --bs=<bs> --numjobs=<n> --direct=<0|1> <extra> \
  --ioengine=psync --iodepth=1 --fallocate=none --invalidate=0 --time_based --runtime=20 --ramp_time=0 \
  --randrepeat=1 --randseed=365 --percentile_list=50:99:99.9 --group_reporting --output-format=json \
  --output=/tmp/fio-out/<arm>/<job>.json
```

`run.sh setup RUN 20 1g 512m 64m measured three drop`. Layout (untimed,
one exec per arm): `fio --name=layout-<f> --filename=<dir>/<f>
--size=<size> --rw=read --bs=1M --create_only=1 --fallocate=none` for seq,
rand, sync. It took 4,350.6 ms on `layerfs`, 2,884.4 ms on `sandbox-disk`
and 3,146.3 ms on `passthrough-fuse` (in-container wall; information only).
Compared with v1.0.0, the layout and each read-back also print the VM's
`MemAvailable`, `Cached` and `Dirty` (untimed). The measured exec is
unchanged.

### File deletion (FILES drop): what was chosen and why

The v1.0.0 run was under memory pressure: two arms' files plus LayerFS's
backing did not stay resident in the Sandbox's ~5.2 GB available. A third
arm's files sit in another container but in the same VM page cache. The
smoke run (below) measured how much each arm caches: removing the 64 MiB
`seq` file freed 63.9 MiB of `Cached` on `sandbox-disk` and 97.4 MiB on
`passthrough-fuse`. The FUSE arm caches the file on the mount and again in
its backing file. LayerFS likewise caches on the mount and in its overlay
backing. At full size that is about 1.6 GiB (overlayfs) plus up to 3.2 GiB
for each FUSE arm: about 8 GiB in all, more than the 5–7 GB the VM had
available.

Chosen: **drop**. Once all three arms had run the last job that uses a
file, that file was removed (untimed, its own step) from `sandbox-disk`
and `passthrough-fuse`: `seq` after `seq-read`, `sync` after `sync-write`.
`rand` is used to the last job and is never removed. No later job reads a
removed file, so no measured job reads different data. The `layerfs`
copies were not removed, because the Commit captures all three files as
the layerfs jobs left them (as in v1.0.0). So during the later jobs
LayerFS still holds its `seq` and `sync` copies (1.06 GiB of file data,
cached on the mount and in its backing) where the other arms do not. If
anything, that works against LayerFS.

Measured effect: the `seq` removal freed 1,004.9 MiB (`sandbox-disk`) and
1,033.2 MiB (`passthrough-fuse`) of `Cached`, `sync` 63.7 and 97.0 MiB.
After each job the VM showed `MemAvailable` 6,115–6,978 MiB and `Cached`
2,892–5,464 MiB.

## Commands

One client per step under the 115 s alarm; all 38 steps exited 0
(`commands.log`: setup, pt-probe, 3 layouts, 27 jobs, 4 drops, commit,
teardown). SDK clients ran in the runtime image; the
`passthrough-fuse` steps ran `client/pt.mjs` on the host under the same
`perl alarm 115`, logged the same way. `bench_setup` created the volumes
at 00:01:48Z. The lock was held by mdtest and then smallfile, so `start`
waited ten times (`perl -e 'sleep 90'`, then asked again) and took the
lock at 00:18:06Z. Setup 00:18:06 (Init 24.3 ms, create 393.4 ms, mount
7.0 ms). `bench_pt_start` and the probe ran at 00:18:07. Layout ran
00:18:12–00:18:25, jobs 00:18:26–00:28:16 at host 1-minute load
6.50–19.89, and the Commit at 00:28:16 (load 7.33). Teardown ran at
00:28:47–00:28:48: `bench_pt_stop` (00:28:47), unmount 219.0 ms,
close 323.1 ms, volumes removed, lock released. Every passing fio exec
took 20.28–20.67 s in-container wall. No Docker removal stall and no
alarm this time. No other suite's client step overlapped the run
(checked against every `benchmark-results/*/*/commands.log`).

## Result

Bandwidth is decimal MB/s (fio `bw_bytes` / 10^6); IOPS are fio's own;
p50 / p99 are fio's completion latency in µs. Arms are listed as
lf = `layerfs`, pt = `passthrough-fuse`, disk = `sandbox-disk` (kernel
overlayfs). Ratios are bandwidth ratios: above 1 means the first arm is
faster.

| Job | MB/s lf / pt / disk | IOPS lf / pt / disk | p50 µs lf / pt / disk | p99 µs lf / pt / disk | LayerFS ÷ passthrough-fuse | LayerFS ÷ overlayfs | passthrough-fuse ÷ overlayfs |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| seq-write | 514.04 / 1,669.23 / 3,258.41 | 490 / 1,592 / 3,108 | 1,433.6 / 464.9 / 232.4 | 13,172.7 / 3,424.3 / 1,003.5 | 0.308 | 0.158 | 0.512 |
| seq-read | 5,030.87 / 6,228.39 / 6,111.06 | 4,798 / 5,940 / 5,828 | 166.9 / 148.5 / 152.6 | 659.5 / 577.5 / 444.4 | 0.808 | 0.823 | 1.019 |
| rand-write | 33.12 / 81.99 / 2,594.71 | 8,087 / 20,017 / 633,475 | 79.4 / 38.1 / 1.2 | 774.1 / 234.5 / 3.2 | 0.404 | 0.013 | 0.032 |
| rand-read | 3,000.10 / 2,127.73 / 2,546.86 | 732,447 / 519,465 / 621,793 | 1.0 / 1.1 / 1.2 | 4.5 / 31.9 / 5.2 | 1.410 | 1.178 | 0.835 |
| rand-read-4j | 12,572.62 / 10,793.41 / 10,681.50 | 3,069,486 / 2,635,110 / 2,607,788 | 1.0 / 1.1 / 1.3 | 1.5 / 1.8 / 1.8 | 1.165 | 1.177 | 1.010 |
| randrw-70-30 read | 101.52 / 45.54 / 1,621.51 | 24,786 / 11,117 / 395,877 | 1.8 / 50.9 / 1.4 | 10.7 / 264.2 / 4.9 | 2.229 | 0.063 | 0.028 |
| randrw-70-30 write | 43.58 / 19.53 / 694.93 | 10,641 / 4,769 / 169,660 | 74.2 / 43.8 / 1.5 | 321.5 / 181.2 / 5.5 | 2.231 | 0.063 | 0.028 |
| sync-write ¹ | 57.97 / 8.39 / 11.47 | 14,152 / 2,049 / 2,800 | 61.7 / 32.1 / 3.2 | 185.3 / 140.3 / 12.5 | 6.909 | 5.054 | 0.731 |
| rand-write-direct ² | 49.58 / FAIL / 70.30 | 12,104 / — / 17,162 | 66.0 / — / 46.3 | 370.7 / — / 156.7 | — | 0.705 | — |
| rand-read-direct | 54.42 / 36.58 / 70.69 | 13,287 / 8,931 / 17,259 | 68.1 / 77.3 / 48.9 | 122.4 / 321.5 / 162.8 | 1.488 | 0.770 | 0.517 |

¹ `sync-write` is not durability-equivalent. `passthrough_ll` passes each
fsync to its overlayfs backing file, which flushes (fsync p50 197.6 µs,
p99 2,310.1 µs), as `sandbox-disk` does (p50 122.4 µs, p99 2,342.9 µs).
A Disposable LayerFS Workspace does not fsync its backing, so its fsync
returns without a flush (p50 0.9 µs, p99 2.1 µs). The same applies to
the end fsync of `seq-write`.

² `passthrough-fuse` FAIL: fio exit 1, JSON `error` 22, log
`fio: io_u error on file /tmp/pt/fio/rand: Invalid argument: write offset=32378880, buflen=4096`
after 292.4 ms. The same error appeared in the smoke run. `rand-read-direct` on
the same file passed afterwards. The likely cause is that `passthrough_ll`
opens its backing file with the caller's `O_DIRECT` and then writes from
a buffer that is not aligned for `O_DIRECT`. That is not verified here.
This failure is in the baseline, not in LayerFS. LayerFS passed this job.

Where LayerFS stands against the FUSE baseline, as measured:

- **Trails:** `seq-write` (0.31×; p50 1,434 vs 465 µs), `seq-read`
  (0.81×) and `rand-write` (0.40×; 8,087 vs 20,017 IOPS, p50 79.4 vs
  38.1 µs). Both FUSE arms have kernel writeback off, so every buffered
  write is a request to the server; the gap is the time each server
  takes per request.
- **Ahead:** `randrw-70-30` (2.23× both directions). Here LayerFS's reads
  were served at p50 1.8 µs, a page-cache hit, while `passthrough_ll`'s
  reads took p50 50.9 µs, going to the server. Also ahead on
  `rand-read-direct` (1.49×; p99 122.4 vs 321.5 µs).
- **Page-cache reads (not a server comparison):** `rand-read` (1.41×) and
  `rand-read-4j` (1.17×). All three arms were at p50 1.0–1.3 µs, so these
  rows measure the kernel's cached read path; `passthrough_ll` shows a
  higher p99 on `rand-read` (31.9 vs 4.5 µs).
- **Not comparable:** `sync-write` (fsync semantics, ¹) and
  `rand-write-direct` (baseline FAIL, ²).
- FUSE alone (`passthrough-fuse ÷ overlayfs`) costs 0.51× on `seq-write`,
  0.03× on buffered 4 KiB random writes and the mixed job, 0.52× on
  `O_DIRECT` reads, about nothing on `seq-read` and `rand-read-4j`
  (1.02×, 1.01×) and 0.84× on `rand-read`.

Cache state: warm own-write for every buffered job (each arm wrote its
file minutes earlier), never cold, residency not checked. The buffered
random reads were page-cache hits in all three arms (p50 ≤ 1.3 µs).
`--direct=1` rows bypass the page cache; below it is warm/unknown. One
sample each on a loaded host; indicative only.

**Not comparable with the v1.0.0 two-arm run.** This run had more free
memory: `MemAvailable` 7.1 GB at setup against 5.2 GB, and at least
6.1 GiB after every job. It also had lower load (6.5–19.9 against
7.8–35.6) and the file removal above. LayerFS's own figures moved a lot:
`rand-write` 8,087 against 1,051 IOPS, `rand-read` p50 1.0 against
643.1 µs, `seq-write` 514 against 140 MB/s. The `sandbox-disk` figures
moved as well (`rand-read` p50 1.2 against 160.8 µs). One sample each, so
the cause is not separated. It is consistent with the v1.0.0 record's
memory-pressure reading, not with a per-write cost that grows with file
size. The v1.0.0 section and data stay unchanged.

### Commit

After every job, one `sandbox.commit` of the `layerfs` Workspace in its
own client (LayerFS only, not inside any timed job): **Committed in
24,831.5 ms**. Commit `129d5b7c7c…`, base `32e7c6f664…`, logical
1,677,721,655 B (the same three files as v1.0.0), newCanonical
1,682,915,885 B, newStored 1,147,780,906 B, newMetadata 2,938,758 B.

## Fairness notes (facts)

- `passthrough_ll` runs as root and does no per-request credential
  switch; files it creates are owned by root, and it does not use
  `default_permissions`. LayerFS mounts with `default_permissions`. Its
  threading (up to 10 workers) and cache timeout (1.0 s) are its
  defaults, not LayerFS's.
- `passthrough_ll` keeps nothing beyond the directory. LayerFS also
  records each change in the Workspace overlay for Commit. Both have
  kernel writeback off.
- The sibling container and the Sandbox share the Docker VM, kernel and
  image layers (the sibling image is the Sandbox image plus
  `passthrough_ll`), but they are different containers. The
  `passthrough-fuse` backing is the sibling's own overlayfs `/tmp/pt-src`.
- The `passthrough-fuse` `exec_ms` is the host's `docker exec` time; the
  other arms' is the `sandbox.exec` client time. The in-container
  `date +%s%N` wall and fio's own figures are the comparable ones.

## Other runs

- `smoke-20261019T235826Z`: the whole three-arm plan with `drop` at 3 s
  per job, seq 64m, rand 32m, sync 8m, no lock. 26 / 27 PASS; the one FAIL
  was `rand-write-direct` on `passthrough-fuse` with the same
  `Invalid argument` (offset 2023424). Commit 1,535.4 ms. It proved the
  arm end to end, the sibling lifecycle (`bench_pt_stop` at teardown,
  volumes removed) and the drop steps, and gave the cache figures used
  above. Not a measurement. A `report.py` fix followed: a failed row with
  no data direction now fills its job's row in `ratios.csv`. Its clients
  (23:58:26–00:00:50Z) **overlapped mdtest's measured run
  `20261019T235618Z`** (steps `case-files-4p-shared-passthrough-fuse-1`
  23:58:27–23:59:48 and `case-files-4p-unique-*` 00:00:00–00:02:03) and
  smallfile's smoke `smoke-20261019T235827Z-scale`. Smoke runs take no
  lock under the brief; whether this touched an mdtest operation is for
  mdtest's record to say.

No measured run failed or was restarted.

## Receipts

`benchmark-results/fio/20261020T000148Z/` (Git-ignored): `identity.txt`,
`deploy.env`, `params.env`, `commands.log`, `ledger.jsonl`,
`results.jsonl`, `layout.jsonl`, `drop.jsonl`, `sandbox-identity.txt`,
`pt-identity.txt`, `pt-mount.txt`, `ops/*.txt` (fio's log and JSON per
job and arm, with the VM's memory figures; each arm's layout; each drop),
`results.csv`, `commit.csv`, `ratios.csv`, `summary.json`, each step's
`.out` / `.err`. Sibling removed 00:28:47Z, volumes removed 00:28:48Z;
no `bench-fio-*` container or volume remains.
