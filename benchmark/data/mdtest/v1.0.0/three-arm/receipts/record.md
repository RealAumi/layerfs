# mdtest — run 20261020T002921Z (three arms)

> **Verdict:** COMPLETE WITH TWO FAILURES, one sample per case and arm.
> 25 of 27 case executions exited 0, plus the layerfs-only `-C` and `-r`
> passes. The two failures are both in the `passthrough-fuse` arm:
> `dirs-4p-shared` and `dirs-4p-unique` reached the 115 s ceiling
> (`rc=124` at 111.0 s, stopped by `timeout`). There is no LayerFS-only
> failure. Against the like-for-like FUSE baseline (libfuse
> `passthrough_ll`), LayerFS is at 0.86–1.28× on single-process create,
> rename and removal, 1.2–4.2× on four-process ones, and 49–784× on stat
> and 2.9–16× on open/close, where passthrough_ll's 1.0 s cache timeout
> against LayerFS's 60 s decides the result. Diagnostic host (arm64 Docker
> Desktop, 1-minute load 7.9–15.7 during the cases).

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK | `sdk/js/src` in checkout `fs-bench-sdk-main` at `c7433bbb1e`; `benchmark/mdtest` uncommitted (`harness_dirty_files=3`: `run.sh`, `report.py`, `README.md`) |
| Sandbox image | `bench-mdtest:20261019` = `sha256:d87e290efaea…` (digest checked unchanged before the run), FROM `fs-bench-computer:gawk-20261020` (`sha256:66aeb6bb…`) |
| Passthrough image | `bench-mdtest:20261019-pt` = `sha256:4119b41bf2aa…`, FROM the Sandbox image above; libfuse `3f65bb699cd2f0afe2b9519c39d29922229f2168` (`fuse-3.14.0`), `passthrough_ll.c` `sha256:b8081e5f…`, binary `sha256:f928a291…`, Debian libfuse3 3.14.0-4, gcc 12.2.0 |
| mdtest | hpc/ior `f1172addabada77d13cf37773d1ffdb202b4fc4a`, mdtest 4.1.0+dev, binary `sha256:84641249…` (same bytes in both images) |
| MPI | Open MPI 4.1.4; `mpirun --oversubscribe --bind-to none -np <procs>` as uid 501 in both containers, no extra MCA flag or environment variable needed under `docker exec` either |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Sandbox | Linux 6.12.76-linuxkit aarch64, 8 CPUs, uid 501 gid 20; `layerfs` on `/workspaces/1/md` (fuse, `default_permissions,allow_other,max_read=131072`), `sandbox-disk` on `/tmp/md` (overlayfs) |
| Passthrough sibling | `bench-mdtest-20261020T002921Z-pt`, same kernel, 8 CPUs, `docker exec -u 501:20 -e HOME=/tmp`; `passthrough_ll -o source=/tmp/pt-src -o allow_other /tmp/pt` (`fuse.passthrough_ll rw,nosuid,nodev,relatime,user_id=0,group_id=0,allow_other`); arm folder `/tmp/pt/md` |
| Host | Docker 29.5.2, Docker Desktop, 8 CPUs, 8.32 GB |
| Lock | taken 00:29:22Z (right after `bench_setup`, before the setup client and the sibling), released 00:43:44Z after teardown and `bench_pt_stop` (00:43:43Z) |

## Commands

`run.sh setup RUN benchmark/mdtest/cases.tsv measured three`, then
`run.sh next` per case and arm, `run.sh commit`, `run.sh teardown`,
`run.sh report`. Every client and docker exec exited 0
(`commands.log`). Setup 00:29:22–00:29:24 (Init 21.5 ms, create
478.3 ms, mount 4.5 ms); cases 00:29:28–00:43:18; commit pass
00:43:23–00:43:36; teardown 00:43:43 (unmount 30.1 ms, close 216.6 ms).

Per case the order was `layerfs`, `sandbox-disk`, `passthrough-fuse`.
Every case is `mpirun --oversubscribe --bind-to none -np <procs> mdtest
-P -i 1 -n <items> <args> -d <arm base>/<case>`, the v1.0.0 `cases.tsv`
unchanged. In the passthrough arm mpirun runs under `timeout -k 3 110`
inside the sibling (see "Other runs" for why).

Host 1-minute load at each case's start: `layerfs` 8.27–15.72,
`sandbox-disk` 8.10–13.62, `passthrough-fuse` 7.91–13.62; commit pass
6.58–6.86. The Docker VM's own load (`vm_load`) was 2.2–5.9.

## Result

ops/s is the Mean column of mdtest's `SUMMARY rate` (one iteration).
L/P = layerfs ÷ passthrough-fuse (like-for-like FUSE), L/D = layerfs ÷
sandbox-disk, P/D = passthrough-fuse ÷ sandbox-disk (the cost of FUSE
alone). Above 1, the first arm was faster.

| Case | Phase | layerfs | passthrough-fuse | sandbox-disk | L/P | L/D | P/D |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| files-1p-shared | creation | 5,697 | 4,455 | 93,522 | 1.28 | 0.061 | 0.048 |
| | stat | 696,185 | 11,020 | 717,674 | 63.2 | 0.97 | 0.015 |
| | read | 16,781 | 5,096 | 532,881 | 3.29 | 0.032 | 0.0096 |
| | removal | 6,811 | 6,922 | 174,684 | 0.98 | 0.039 | 0.040 |
| files-1p-unique | creation | 4,143 | 3,707 | 69,917 | 1.12 | 0.059 | 0.053 |
| | stat | 526,744 | 10,657 | 786,599 | 49.4 | 0.67 | 0.013 |
| | read | 15,622 | 5,317 | 534,204 | 2.94 | 0.029 | 0.010 |
| | removal | 5,689 | 6,586 | 175,339 | 0.86 | 0.032 | 0.038 |
| files-4p-shared | creation | 4,340 | 3,598 | 83,795 | 1.21 | 0.052 | 0.043 |
| | stat | 3,365,877 | 5,104 | 1,436,528 | 659 | 2.34 | 0.0036 |
| | read | 55,366 | 5,781 | 996,772 | 9.58 | 0.056 | 0.0058 |
| | removal | 5,846 | 3,949 | 179,697 | 1.48 | 0.033 | 0.022 |
| files-4p-unique | creation | 11,597 | 3,206 | 216,954 | 3.62 | 0.053 | 0.015 |
| | stat | 3,007,855 | 3,839 | 1,403,928 | 784 | 2.14 | 0.0027 |
| | read | 55,296 | 3,708 | 989,156 | 14.9 | 0.056 | 0.0037 |
| | removal | 12,455 | 3,271 | 423,684 | 3.81 | 0.029 | 0.0077 |
| dirs-1p-shared | creation | 6,136 | 6,613 | 35,719 | 0.93 | 0.17 | 0.19 |
| | stat | 880,056 | 11,698 | 787,094 | 75.2 | 1.12 | 0.015 |
| | rename | 6,311 | 4,940 | 100,254 | 1.28 | 0.063 | 0.049 |
| | removal | 6,149 | 6,455 | 116,217 | 0.95 | 0.053 | 0.056 |
| dirs-1p-unique | creation | 5,865 | 5,513 | 33,025 | 1.06 | 0.18 | 0.17 |
| | stat | 754,514 | 10,258 | 643,377 | 73.6 | 1.17 | 0.016 |
| | rename | 5,750 | 5,032 | 92,039 | 1.14 | 0.062 | 0.055 |
| | removal | 6,589 | 6,329 | 94,443 | 1.04 | 0.070 | 0.067 |
| dirs-4p-shared | creation / stat / rename / removal | 6,440 / 2,845,573 / 6,600 / 6,702 | FAIL (115 s ceiling) | 21,416 / 1,463,297 / 83,155 / 71,513 | — | 0.30 / 1.94 / 0.079 / 0.094 | — |
| dirs-4p-unique | creation / stat / rename / removal | 12,667 / 2,864,717 / 13,756 / 12,105 | FAIL (115 s ceiling) | 62,349 / 1,884,742 / 327,600 / 287,635 | — | 0.20 / 1.52 / 0.042 / 0.042 | — |
| tree-4p-shared: dirs | creation | 7,323 | 2,240 | 33,750 | 3.27 | 0.22 | 0.066 |
| | stat | 2,382,160 | 5,650 | 1,752,774 | 422 | 1.36 | 0.0032 |
| | rename | 7,721 | 4,517 | 153,384 | 1.71 | 0.050 | 0.029 |
| | removal | 8,007 | 5,272 | 140,144 | 1.52 | 0.057 | 0.038 |
| tree-4p-shared: files | creation | 7,072 | 1,674 | 153,723 | 4.22 | 0.046 | 0.011 |
| | stat | 2,404,531 | 3,661 | 1,152,040 | 657 | 2.09 | 0.0032 |
| | read | 58,623 | 3,581 | 849,668 | 16.4 | 0.069 | 0.0042 |
| | removal | 7,902 | 3,322 | 249,482 | 2.38 | 0.032 | 0.013 |

Tree creation and removal (1–21 folders per case, mostly 0–9 ms of
mdtest's 1 ms resolution) are in `results.csv` and left out of the ratios,
as in v1.0.0.

Whole mdtest wall time inside the container (`tool_ns`), layerfs /
passthrough-fuse / sandbox-disk: files-1p-shared 8.9 / 14.2 / 1.5 s,
files-4p-shared 34.7 / 73.2 / 2.6 s, files-4p-unique 15.9 / 93.0 / 1.8 s,
dirs-4p-shared 37.6 / ≥111.0 (stopped) / 7.0 s, tree-4p-shared 29.6 /
105.5 / 3.5 s.

What stands out, against the FUSE baseline:

- **Matches with one process.** Single-process file and directory
  create, rename and removal are within 0.86–1.28× of passthrough_ll:
  LayerFS is slightly ahead on create and rename, slightly behind on file
  removal (0.86–0.98) and directory creation in a shared folder (0.93).
- **Beats it with four processes.** passthrough_ll slows down when four
  processes share it (file creation 4,455 → 3,206–3,598 ops/s, tree file
  creation 1,674), while LayerFS holds or scales, so LayerFS is 1.2–4.2×
  ahead on four-process create, rename and removal. The two
  four-process directory cases did not finish on passthrough_ll within
  115 s, while LayerFS finished them in 37.6 s and 19.9 s.
- **Stat and open/close are decided by cache policy.** passthrough_ll's
  default entry and attribute timeout is 1.0 s, so by the time mdtest
  stats its 20,000 files, each stat is a FUSE request (3.7–11.7k ops/s).
  LayerFS replies with a 60 s timeout (`TTL` in
  `core/crates/layerfs-fuse/src/request/reply.rs` at `e5c7aaae05`), so
  the kernel answers from its cache (0.5–3.4 M ops/s). The 49–784× stat
  ratios and the 2.9–16× open/close ratios measure that difference, not
  daemon speed.
- **FUSE alone costs most of the gap to the kernel.** passthrough_ll runs
  creation, rename and removal at 0.8–19 % of overlayfs (P/D
  0.0077–0.19), the same range as LayerFS (L/D 0.029–0.30). With one process, most of
  LayerFS's distance from `sandbox-disk` on those phases is the FUSE
  round trip itself.

### Commit pass (layerfs only)

`mdtest -F -C -n 20000` (1 process) into `/workspaces/1/md/commit`:
5,040 files/s. Then one `sandbox.commit` in its own client:
**Committed in 2,591.4 ms** (load 6.72), commit `1289070bfc…`, base
`32b5a80382…`, logical 60 B, newCanonical 2,238,515 B, newStored
168,282 B, newMetadata 168,282 B, about 130 µs per captured empty file.
Then `mdtest -F -r -n 20000` removed them at 6,071 files/s.

## Failures

Both are `passthrough-fuse` only, so neither counts against LayerFS:

- `dirs-4p-shared`: `mpirun --oversubscribe --bind-to none -np 4 mdtest -P
  -i 1 -n 20000 -D -d /tmp/pt/md/dirs-4p-shared` under `timeout -k 3 110`
  → `rc=124 ns=111007488954`; the output stops after
  `4 tasks, 80000 directories` with `mpirun: Forwarding signal 18 to job`.
- `dirs-4p-unique`: the same with `-D -u -d /tmp/pt/md/dirs-4p-unique` →
  `rc=124 ns=111008170787`, same last lines.

Not rerun (one sample). The identical `dirs-4p-shared` command finished
in the stopped run below in 115.06 s, so it needs about 115 s on this
host; `dirs-4p-unique` was not reached there.

## Other runs

- `20261019T235618Z` (measured, **stopped**, receipts kept): the same plan
  and harness without the in-sibling `timeout`. It ran 21 of 27 case
  executions, all exit 0, then stopped after
  `case-dirs-4p-shared-passthrough-fuse-1`, which completed in 115.16 s
  host-side (`tool_ns` 115.06 s), past the 115 s ceiling: the perl alarm
  in `bench_pt_exec` never fired, because the docker CLI is a Go program
  and Go ignores SIGALRM (checked: `perl -e 'alarm 2; exec @ARGV' docker
  run --rm … sleep 5` returned 0 after 5 s). That is a harness defect,
  so the run was torn down (lock released 00:07:23Z), `pt_case` was given
  `timeout -k 3 110` inside the sibling (TERM lets mpirun stop its ranks;
  a TERM→KILL test with 1 s grace left a rank behind, 3 s did not), and
  this run started under a new id. Its numbers are diagnostic, not the
  result; they agree with this run in kind (for example dirs-4p-shared on
  passthrough_ll: creation 2,334, stat 4,069, rename 2,476, removal 2,889
  ops/s).
- `smoke-20261019T235531Z`: three arms, 200 items per process,
  files-1p-shared, dirs-4p-unique, tree-4p-shared and the commit pass
  (Commit 43.2 ms). Not a measurement.
- `smoke-20261020T000848Z`: three arms, files-1p-shared only, after the
  `timeout` change. Not a measurement.
- The measured run waited for the lock (held by smallfile, then fio)
  from 00:09 to 00:29 with `perl -e 'sleep 90'` between asks.

Cache state: warm/unknown, not cold.

## Fairness notes

- `passthrough_ll` runs as root and does no per-request credential switch:
  files it creates are owned by root, and it does not use
  `default_permissions`. Its threading (up to 10 workers) and cache
  timeout (1.0 s) are its defaults, not LayerFS's.
- `passthrough_ll` keeps nothing beyond the directory. LayerFS also
  records each change for Commit. Both have writeback off.
- The sibling container and the Sandbox share the Docker VM, kernel and
  image layers, but they are different containers.

## Receipts

`benchmark-results/mdtest/20261020T002921Z/` (Git-ignored):
`identity.txt` (with the `pt_*` lines), `deploy.env`, `cases.tsv`,
`arms.txt`, `commands.log`, `ledger.jsonl`, `results.jsonl`,
`sandbox-identity.txt`, `pt-identity.txt`, `pt-mount.txt`, `cases/*.txt`
(mdtest's whole output per case and arm), each step's `.out` / `.err`,
and the derived `results.csv`, `commit.csv`, `ratios.csv`,
`summary.json`.
