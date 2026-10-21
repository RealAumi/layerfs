# smallfile — run 20261020T000127Z (three arms)

> **Verdict:** COMPLETE, one sample per operation and arm. 27 / 27
> smallfile runs passed (9 / 9 each for `layerfs`, `sandbox-disk` and
> `passthrough-fuse`): exit 0, status `Success`, 100 % of 100,000 files
> processed in every operation. No LayerFS-only failure. Against the
> like-for-like FUSE baseline (libfuse `passthrough_ll`), LayerFS was faster
> in all nine operations: LayerFS ÷ passthrough-fuse files/s ranged from
> 1.270 (delete-renamed) to 10.709 (stat). Against the container's
> overlayfs it was slower in all nine (0.018 chmod to 0.460 read). One
> `sandbox.commit` of the 100,000 created files took 10,430.5 ms.
> Diagnostic host (arm64 Docker Desktop, 1-minute load 6.66–11.51 during
> the operations).

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK / harness | checkout `fs-bench-sdk-main` at `d00c00e44e`; `benchmark/smallfile` `run.sh` and `report.py` uncommitted at run time (`harness_dirty_files=2`) |
| Sandbox image | `bench-smallfile:20261019` = `sha256:4d95be33a981…` (the v1.0.0 image; tag still has the recorded digest), FROM `fs-bench-computer:gawk-20261020` (`sha256:66aeb6bb…`) |
| Passthrough image | `bench-smallfile:20261019-pt` = `sha256:5d0c68ce2ce3…`, base `sha256:4d95be33a981…` (the Sandbox image above) plus `passthrough_ll` |
| passthrough_ll | libfuse `3f65bb699cd2f0afe2b9519c39d29922229f2168` (`fuse-3.14.0`) `example/passthrough_ll.c` (sha256 `b8081e5f…`), `passthrough_helpers.h` (`b801a232…`), built with gcc 12.2.0 against Debian libfuse3 3.14.0-4; binary sha256 `f928a291…` |
| smallfile | distributed-system-analysis/smallfile `aa2519de5bf0b3b383db2c31eacbf8ac4328e19c` (version 1.0.2), Python 3.11.2, python3-yaml 6.0-3+b2 (Debian bookworm); the same bytes in both images |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Sandbox | Linux 6.12.76-linuxkit aarch64, 8 CPUs, uid 501 gid 20; `layerfs` on `/workspaces/1/sf` (fuse, `default_permissions,allow_other,max_read=131072`), `sandbox-disk` on `/tmp/sf` (overlayfs) |
| Sibling | container `bench-smallfile-20261020T000127Z-pt`, same kernel and CPUs, uid 501 gid 20 for smallfile; `passthrough_ll /tmp/pt fuse.passthrough_ll rw,nosuid,nodev,relatime,user_id=0,group_id=0,allow_other`, source `/tmp/pt-src` (the sibling's overlayfs) |
| Host | Docker 29.5.2, Docker Desktop, 8 CPUs, 8.32 GB |
| Lock | taken 00:08:20Z, released 00:17:41Z (after `bench_pt_stop` at 00:17:40Z and teardown) |

## Parameters

Every operation, every arm (v1.0.0's parameters and order):

```text
python3 /opt/smallfile/smallfile_cli.py --top <top> --operation <op> --threads 4 \
  --files 25000 --file-size 4 --stonewall N --finish Y --output-json /tmp/sf-out/<arm>/<op>/result.json
```

`<top>` is `/workspaces/1/sf` (layerfs), `/tmp/sf` (sandbox-disk) or
`/tmp/pt/sf` (passthrough-fuse). 4 threads × 25,000 files of 4 KiB =
100,000 files (390.6 MiB) per arm; smallfile defaults otherwise.

## Commands

`run.sh setup` at 00:01:27Z created the volumes; the measurement lock was
held by mdtest (`20261019T235618Z`), so `start` exited 75 and waited
four times with `perl -e 'sleep 90'` before it took the lock at 00:08:20Z.
Setup client 00:08:20 (Init 23.5 ms, create 299.0 ms, mount 4.6 ms), then
`bench_pt_start` at 00:08:21Z. Plan order per operation: layerfs,
sandbox-disk, passthrough-fuse; the one `sandbox.commit` followed the
layerfs `create` (00:08:46–00:08:57, load 7.37), so the layerfs `read` ran
after the Commit, as in v1.0.0. Operations 00:08:27–00:17:33 at 1-minute
load 6.66–11.51; all 30 steps exited 0 (`commands.log`). The longest
command was `rename` on passthrough-fuse, 41.8 s (115 s alarm). Teardown:
`bench_pt_stop` 00:17:40Z, unmount 106.8 ms, close 327.5 ms, volumes
removed 00:17:41Z.

## Result

files/s, elapsed and MiB/s are smallfile's own (`--output-json`). Wall is
`date +%s%N` around the whole `smallfile_cli.py` process inside the
container (Sandbox or sibling); it includes about 3.6 s of smallfile
start-up, so compare arms on files/s. A files/s ratio above 1 means the
first arm is faster.

| Op | layerfs files/s | passthrough-fuse files/s | sandbox-disk files/s | **LayerFS ÷ passthrough-fuse** | LayerFS ÷ sandbox-disk | passthrough-fuse ÷ sandbox-disk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| create | 6,693 | 3,293 | 204,225 | **2.032** | 0.033 | 0.016 |
| read | 13,176 | 4,365 | 28,651 | **3.018** | 0.460 | 0.152 |
| append | 8,213 | 4,790 | 199,550 | **1.715** | 0.041 | 0.024 |
| stat | 52,136 | 4,868 | 1,050,826 | **10.709** | 0.050 | 0.005 |
| chmod | 17,275 | 5,114 | 973,438 | **3.378** | 0.018 | 0.005 |
| rename | 4,615 | 2,635 | 78,914 | **1.751** | 0.058 | 0.033 |
| delete-renamed | 5,589 | 4,401 | 174,917 | **1.270** | 0.032 | 0.025 |
| mkdir | 12,349 | 2,934 | 69,575 | **4.210** | 0.177 | 0.042 |
| rmdir | 10,971 | 3,354 | 173,828 | **3.272** | 0.063 | 0.019 |

| Op | layerfs elapsed s | pt elapsed s | disk elapsed s | layerfs wall ms | pt wall ms | disk wall ms | Load (lf / disk / pt) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| create | 14.960 | 30.442 | 0.491 | 18,561.6 | 34,003.6 | 4,084.9 | 6.87 / 7.56 / 7.46 |
| read | 7.634 | 22.989 | 3.500 | 11,244.0 | 26,574.1 | 7,096.1 | 7.38 / 7.73 / 8.22 |
| append | 12.201 | 20.923 | 0.504 | 15,766.2 | 24,495.1 | 4,215.2 | 7.59 / 7.10 / 7.50 |
| stat | 1.929 | 20.580 | 0.096 | 5,500.9 | 24,144.1 | 3,665.6 | 6.91 / 6.76 / 6.66 |
| chmod | 5.801 | 19.585 | 0.106 | 9,365.0 | 23,158.8 | 3,703.7 | 7.83 / 8.07 / 7.59 |
| rename | 21.689 | 38.089 | 1.284 | 25,267.6 | 41,661.8 | 4,842.6 | 7.09 / 9.79 / 10.38 |
| delete-renamed | 17.900 | 22.738 | 0.583 | 21,469.6 | 26,308.6 | 4,281.0 | 8.17 / 9.01 / 11.51 |
| mkdir | 8.110 | 34.263 | 1.450 | 11,689.8 | 37,831.8 | 5,095.5 | 10.61 / 10.06 / 9.11 |
| rmdir | 9.123 | 29.826 | 0.599 | 12,690.1 | 33,409.1 | 4,212.7 | 10.14 / 9.50 / 9.38 |

MiB/s (data operations only, layerfs / passthrough-fuse / sandbox-disk):
create 26.14 / 12.86 / 797.75, read 51.47 / 17.05 / 111.92, append
32.08 / 18.71 / 779.49.

- **Where LayerFS stands against the FUSE baseline:** it beats
  `passthrough_ll` in every operation. The margin is small for the
  operations that remove or move names (delete-renamed 1.27×, append
  1.72×, rename 1.75×) and for create (2.03×), and large for the metadata
  reads and directory operations (stat 10.7×, mkdir 4.2×, chmod 3.4×,
  rmdir 3.3×, read 3.0×). It matches or trails it in none.
- **FUSE alone** (passthrough-fuse ÷ sandbox-disk) costs 0.005–0.152 of
  the overlayfs rate here, a larger loss than LayerFS's in every operation.
- `read` differs from v1.0.0 in both Sandbox arms: sandbox-disk 28,651
  files/s (v1.0.0: 356,019) and layerfs 13,176 (v1.0.0: 40,835), so
  LayerFS ÷ sandbox-disk is 0.460 here against 0.115 then. chmod (0.018
  against 0.064; layerfs 17,275 against 40,326 files/s) and rmdir (0.063
  against 0.186; sandbox-disk 173,828 against 69,543) also moved by about
  3×; the other six ratios are within 25 % of v1.0.0. Not diagnosed. The sibling's create added another 390.6 MiB of files on
  the same 8 GB Docker VM between the sandbox-disk create and the reads,
  and other suites ran on the host, so page cache state before `read` is
  unknown. One sample; not rerun.
- Several sandbox-disk operations finished in 0.1–0.6 s of smallfile
  elapsed time, so their files/s carry more timing noise.

### Commit

After the layerfs `create`, one `sandbox.commit` in its own client (LayerFS
only, outside every timed operation): **Committed in 10,430.5 ms** for
the 100,000 created files (about 104 µs per file), commit `12a20c1832…`,
base `328b7345a7…`, logical 409,600,076 B, newCanonical 12,300,831 B,
newStored 976,730 B, newMetadata 968,168 B. smallfile's default file content
is highly repetitive, so the stored bytes say nothing about real data.

## Fairness notes (facts)

- `passthrough_ll` runs as root and does no per-request credential switch.
  Files it creates are owned by root, and it doesn't use
  `default_permissions` (LayerFS's mount has it). Its threading (up to 10
  workers) and cache timeout (1.0 s) are its defaults, not LayerFS's.
- `passthrough_ll` keeps nothing beyond the directory. LayerFS also
  records each change in the Workspace overlay for Commit. Both have
  kernel writeback caching off.
- `passthrough_ll` (libfuse 3.14.0's example) finds an inode by walking
  one linked list of every inode it holds, under one mutex (`lo_find`,
  `passthrough_ll.c` lines 291–307), on each lookup. Its per-request cost
  therefore grows with the number of inodes the kernel references. In the
  smoke runs its create rate fell from 8,769 files/s at 4,000 files to
  2,825 at 100,000; LayerFS's barely moved (6,747 to 5,777). Part of
  LayerFS's margin at 100,000 files comes from that list, not from FUSE
  itself.
- The sibling container and the Sandbox share the Docker VM, kernel and
  image layers, but they are different containers: the sibling has
  `/dev/fuse` and `CAP_SYS_ADMIN`, its backing directory is its own
  overlayfs `/tmp/pt-src`, and smallfile runs there through `docker exec`
  (`exec_ms` is the host-side `docker exec` time), not `sandbox.exec`.
- Arms ran one after the other, not concurrently. Cache state:
  warm/unknown, not cold.

## Other runs

- `smoke-20261019T235532Z-pt`: the whole three-arm plan at 1,000 files per
  thread (4,000 files); 27 / 27 PASS; Commit of 4,000 files 458.9 ms.
  Checked the arm and the sibling lifecycle end to end. Not a measurement.
- `smoke-20261019T235827Z-scale`: at 25,000 per thread, only `create` in
  the three arms and the Commit (10,734.6 ms), to check that
  passthrough-fuse stays inside the 115 s alarm at 100,000 files (create
  39.6 s wall, 2,825 files/s). Then one diagnostic passthrough-fuse
  `rename` outside the plan, by hand through `bench_pt_exec`
  (`diag-rename-passthrough-fuse.txt`: 57.0 s wall, 1,880 files/s), since
  rename was passthrough-fuse's slowest smoke operation. Not a
  measurement.

No measured run failed or was restarted. The v1.0.0 run
`20261019T224809Z` was not reused or altered; `report.py` still
reproduces its `results.csv`, `commit.csv` and `summary.json` byte for
byte.

## Receipts

`benchmark-results/smallfile/20261020T000127Z/` (Git-ignored):
`identity.txt` (with the `pt_*` lines), `deploy.env`, `params.env`,
`commands.log`, `ledger.jsonl`, `results.jsonl`, `sandbox-identity.txt`,
`pt-identity.txt`, `pt-mount.txt`, `ops/*.txt`, `results.csv`,
`commit.csv`, `summary.json`, each step's `.out` / `.err`. Passthrough
image identity: `benchmark-results/smallfile/pt-image.txt`. No
`bench-smallfile-*` container or volume remains.
