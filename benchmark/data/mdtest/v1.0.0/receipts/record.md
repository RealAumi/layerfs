# mdtest — run 20261019T230650Z

> **Verdict:** COMPLETE, one sample per case and arm. All 20 mdtest
> executions exited 0 (9 cases × 2 arms, plus the layerfs-only `-C` and
> `-r` passes); no LayerFS-only failure. Speed: LayerFS ran creation,
> rename, removal and open/close at 2–30 % of `sandbox-disk`'s rate, and
> stat at 0.6–4.3 times it (kernel attribute cache, warm). The
> 20,000 files left by the create-only pass committed in 3,643.5 ms.
> Diagnostic host (arm64 Docker Desktop, 1-minute load 10.6–14.1 during
> the cases).

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK | `sdk/js/src` in checkout `fs-bench-sdk-main` at `d6e01c7d6d`; `benchmark/mdtest` uncommitted (`harness_dirty_files=1`) |
| Sandbox image | `bench-mdtest:20261019` = `sha256:d87e290efaea…`, FROM `fs-bench-computer:gawk-20261020` (`sha256:66aeb6bb…`) |
| mdtest | hpc/ior `f1172addabada77d13cf37773d1ffdb202b4fc4a` (`./bootstrap`, `./configure`, `make -j2`), mdtest 4.1.0+dev, binary `sha256:84641249…` |
| MPI | Open MPI 4.1.4 (Debian bookworm `openmpi-bin` / `libopenmpi-dev` 4.1.4-3+b1); `mpirun --oversubscribe --bind-to none -np <procs>` as uid 501, no other MCA flags needed |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Sandbox | Linux 6.12.76-linuxkit aarch64, 8 CPUs, uid 501 gid 20; `layerfs` arm on `/workspaces/1/md` (fuse, `default_permissions,allow_other,max_read=131072`), `sandbox-disk` arm on `/tmp/md` (overlayfs) |
| Host | Docker 29.5.2, Docker Desktop, 8 CPUs, 8.32 GB |
| Lock | taken 23:06:52Z (right after `bench_setup`, before the setup client mounted), released 23:12:09Z |

## Commands

One client per step under the 115 s alarm; all 24 exited 0
(`commands.log`). Setup 23:06:52–23:06:53 (Init 41.1 ms, create 569.8 ms,
mount 5.1 ms); cases 23:06:58–23:11:43 at 1-minute load 10.58–13.85;
commit pass 23:11:43–23:12:01 (load 10.75–14.14); teardown
23:12:07–23:12:09 (unmount 46.0 ms, close 653.8 ms). The longest exec was
`dirs-4p-shared` on `layerfs`, 44.2 s.

Every case is `mpirun --oversubscribe --bind-to none -np <procs> mdtest
-P -i 1 -n <items> <args> -d <arm base>/<case>`. `-w`/`-e` stay 0, so
files are empty and the read phase is open/close (mdtest warns so).

## Result

Rate is the Mean column of mdtest's `SUMMARY rate` (ops/s; one
iteration). Ratio is layerfs ÷ sandbox-disk.

| Case | Procs × items | Phase | layerfs ops/s | sandbox-disk ops/s | Ratio |
| --- | --- | --- | ---: | ---: | ---: |
| files-1p-shared (`-F`) | 1 × 20,000 | creation | 6,395 | 67,215 | 0.095 |
| | | stat | 831,980 | 683,128 | 1.218 |
| | | read | 18,731 | 499,887 | 0.037 |
| | | removal | 10,134 | 151,006 | 0.067 |
| files-1p-unique (`-F -u`) | 1 × 20,000 | creation | 6,988 | 59,504 | 0.117 |
| | | stat | 778,330 | 636,861 | 1.222 |
| | | read | 10,306 | 425,694 | 0.024 |
| | | removal | 5,620 | 116,710 | 0.048 |
| files-4p-shared (`-F`) | 4 × 20,000 | creation | 3,808 | 74,672 | 0.051 |
| | | stat | 826,788 | 1,295,713 | 0.638 |
| | | read | 46,690 | 953,140 | 0.049 |
| | | removal | 4,785 | 139,182 | 0.034 |
| files-4p-unique (`-F -u`) | 4 × 20,000 | creation | 10,157 | 205,704 | 0.049 |
| | | stat | 1,574,305 | 1,402,402 | 1.123 |
| | | read | 54,464 | 852,715 | 0.064 |
| | | removal | 11,518 | 269,036 | 0.043 |
| dirs-1p-shared (`-D`) | 1 × 20,000 | creation | 5,302 | 26,140 | 0.203 |
| | | stat | 833,824 | 710,153 | 1.174 |
| | | rename | 5,509 | 94,639 | 0.058 |
| | | removal | 6,896 | 106,846 | 0.065 |
| dirs-1p-unique (`-D -u`) | 1 × 20,000 | creation | 5,179 | 30,776 | 0.168 |
| | | stat | 801,725 | 622,203 | 1.289 |
| | | rename | 5,072 | 94,098 | 0.054 |
| | | removal | 5,862 | 98,992 | 0.059 |
| dirs-4p-shared (`-D`) | 4 × 20,000 | creation | 5,795 | 19,108 | 0.303 |
| | | stat | 2,782,130 | 1,150,685 | 2.418 |
| | | rename | 5,661 | 72,920 | 0.078 |
| | | removal | 5,322 | 71,602 | 0.074 |
| dirs-4p-unique (`-D -u`) | 4 × 20,000 | creation | 11,720 | 46,640 | 0.251 |
| | | stat | 2,667,814 | 1,480,523 | 1.802 |
| | | rename | 12,248 | 278,030 | 0.044 |
| | | removal | 11,213 | 224,120 | 0.050 |
| tree-4p-shared (`-z 2 -b 4`, files and dirs) | 4 × 10,500 | dir creation | 7,877 | 26,152 | 0.301 |
| | | dir stat | 2,397,104 | 561,123 | 4.272 |
| | | dir rename | 8,070 | 119,022 | 0.068 |
| | | dir removal | 7,627 | 64,634 | 0.118 |
| | | file creation | 5,777 | 60,661 | 0.095 |
| | | file stat | 2,357,423 | 626,398 | 3.763 |
| | | file read | 59,436 | 434,415 | 0.137 |
| | | file removal | 8,437 | 117,150 | 0.072 |

Tree creation and removal (the 1–21 test-tree folders per case) are in
`results.csv`; they are a few ms on `layerfs` and below mdtest's 1 ms
time resolution on `sandbox-disk`, so their rates are noise-level:
layerfs ÷ sandbox-disk 0.07–0.83 for creation, 0.04–0.15 for removal.

What stands out:

- **Writes through the mount** (create, rename, remove, open/close) run at
  2–30 % of the container disk's rate. Directory creation is the closest
  (17–30 %); file open/close of an empty file the furthest (2–14 %).
- **Shared directory with 4 writers is slower than 1 writer on LayerFS.**
  File creation in one directory: 6,395 ops/s with 1 process, 3,808 with
  4; removal 10,134 vs 4,785. With a directory per process (`-u`) 4
  processes do scale (10,157 and 11,518). `sandbox-disk` does not drop
  (67,215 vs 74,672 creation). Directories in one shared folder stay flat
  at 5.3–5.8k ops/s.
- **Stat is as fast or faster on LayerFS** (0.64–4.3×): mdtest stats what
  it just created, so the kernel's FUSE attribute cache answers. Cache
  state warm/unknown, not cold.

### Commit pass (layerfs only)

`mdtest -F -C -n 20000` (1 process) into `/workspaces/1/md/commit`:
6,998 files/s. Then one `sandbox.commit` in its own client:
**Committed in 3,643.5 ms** (load 10.93), commit `124d8cd09d…`, base
`32a3f7088e…`, logical 60 B (only the seed README has bytes; mdtest's
files are empty), newCanonical 2,238,515 B, newStored 168,272 B,
newMetadata 168,272 B. That is about 182 µs per captured empty file.
Then `mdtest -F -r -n 20000` removed them: 5,540 files/s.

## Other runs

- `smoke-20261019T230258Z`: `cases-smoke.tsv` (200 items per process),
  every case and both arms, the commit pass (200 files, Commit 50.9 ms),
  then two sizing probes appended to that run's `cases.tsv`
  (`-F` and `-D`, 4 × 20,000 shared: 34.4 s and 36.3 s on `layerfs`),
  used to choose `-n 20000`. Not a measurement.
- An earlier `run.sh setup` attempt stopped before creating anything:
  `image.txt` held an `mpi=` line with spaces and parentheses that
  `bench_setup` could not source. The image identity line was made
  shell-safe and the image rebuilt (`sha256:d87e290e…`) before the smoke run.

No measured run failed or was restarted. Cache state: warm/unknown, not cold.

## Receipts

`benchmark-results/mdtest/20261019T230650Z/` (Git-ignored): `identity.txt`,
`deploy.env`, `cases.tsv`, `commands.log`, `ledger.jsonl`,
`results.jsonl`, `sandbox-identity.txt`, `cases/*.txt` (mdtest's whole
output per case and arm), each step's `.out` / `.err`, and the derived
`results.csv`, `commit.csv`, `summary.json`.
