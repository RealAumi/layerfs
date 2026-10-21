# mdtest release data

> **Status:** Current general guide.

One folder per release with mdtest results: IOR's `mdtest` measures
metadata operation rates (create, stat, open/close or rename, remove) from
1 and 4 MPI processes, in a shared folder and in a folder per process, run
through `sandbox.exec` in a LayerFS Workspace (`layerfs`) and in the same
Sandbox's own overlayfs `/tmp` (`sandbox-disk`) as the reference. The
harness is [benchmark/mdtest](../../mdtest/README.md).

A later run of the same build adds a third arm, a passthrough FUSE
baseline: see [Three-arm run](#three-arm-run).

## v1.0.0

All 20 mdtest executions exited 0 in both arms; there is no LayerFS-only
failure. Rates are ops/s (mdtest's own `SUMMARY rate`, one iteration).
The ratio is LayerFS ÷ sandbox-disk: 0.10 means LayerFS ran at a tenth of
the container disk's rate; above 1 means LayerFS was faster.

| Case | Phase | layerfs ops/s | sandbox-disk ops/s | Ratio |
| --- | --- | ---: | ---: | ---: |
| files, 1 proc, shared (`-F`, 20,000) | creation / stat / read / removal | 6,395 / 831,980 / 18,731 / 10,134 | 67,215 / 683,128 / 499,887 / 151,006 | 0.095 / 1.22 / 0.037 / 0.067 |
| files, 1 proc, unique (`-F -u`) | creation / stat / read / removal | 6,988 / 778,330 / 10,306 / 5,620 | 59,504 / 636,861 / 425,694 / 116,710 | 0.117 / 1.22 / 0.024 / 0.048 |
| files, 4 procs, shared (`-F`, 4 × 20,000) | creation / stat / read / removal | 3,808 / 826,788 / 46,690 / 4,785 | 74,672 / 1,295,713 / 953,140 / 139,182 | 0.051 / 0.64 / 0.049 / 0.034 |
| files, 4 procs, unique (`-F -u`) | creation / stat / read / removal | 10,157 / 1,574,305 / 54,464 / 11,518 | 205,704 / 1,402,402 / 852,715 / 269,036 | 0.049 / 1.12 / 0.064 / 0.043 |
| dirs, 1 proc, shared (`-D`) | creation / stat / rename / removal | 5,302 / 833,824 / 5,509 / 6,896 | 26,140 / 710,153 / 94,639 / 106,846 | 0.203 / 1.17 / 0.058 / 0.065 |
| dirs, 1 proc, unique (`-D -u`) | creation / stat / rename / removal | 5,179 / 801,725 / 5,072 / 5,862 | 30,776 / 622,203 / 94,098 / 98,992 | 0.168 / 1.29 / 0.054 / 0.059 |
| dirs, 4 procs, shared (`-D`) | creation / stat / rename / removal | 5,795 / 2,782,130 / 5,661 / 5,322 | 19,108 / 1,150,685 / 72,920 / 71,602 | 0.303 / 2.42 / 0.078 / 0.074 |
| dirs, 4 procs, unique (`-D -u`) | creation / stat / rename / removal | 11,720 / 2,667,814 / 12,248 / 11,213 | 46,640 / 1,480,523 / 278,030 / 224,120 | 0.251 / 1.80 / 0.044 / 0.050 |
| tree, 4 procs (`-z 2 -b 4`, 4 × 10,500): dirs | creation / stat / rename / removal | 7,877 / 2,397,104 / 8,070 / 7,627 | 26,152 / 561,123 / 119,022 / 64,634 | 0.301 / 4.27 / 0.068 / 0.118 |
| tree, 4 procs: files | creation / stat / read / removal | 5,777 / 2,357,423 / 59,436 / 8,437 | 60,661 / 626,398 / 434,415 / 117,150 | 0.095 / 3.76 / 0.137 / 0.072 |

The ratios per phase, in plain words:

- **File creation:** LayerFS creates empty files at about a tenth of the
  container disk's rate with one process (0.095–0.12) and about a twentieth
  with four (0.05). Absolute: 3,800–10,200 files/s.
- **File stat:** about the same or faster on LayerFS (0.64–1.22; 3.8 in
  the tree case), because mdtest stats files it has just created and the
  kernel's FUSE attribute cache answers. Warm caches, not a cold-stat rate.
- **File read** (open and close of an empty file): the widest gap, 2–6 %
  of the disk's rate (0.024–0.064; 0.14 in the tree case).
- **File removal:** 3–7 % of the disk's rate (0.034–0.072).
- **Directory creation:** the closest write phase, a fifth to a third of
  the disk's rate (0.17–0.30).
- **Directory stat:** faster on LayerFS (1.2–4.3), the same warm-cache
  reason as file stat.
- **Directory rename:** 4–8 % of the disk's rate (0.044–0.078).
- **Directory removal:** 5–12 % (0.050–0.118).
- **Tree creation and removal** (1–21 test folders per case) take a few
  ms on LayerFS and under mdtest's 1 ms resolution on the disk, so their
  ratios (0.07–0.83 creation, 0.04–0.15 removal) are noise-level; they
  are in `results.csv`.

Four processes in **one shared folder** are slower than one process on
LayerFS for files: creation 6,395 → 3,808 files/s and removal 10,134 →
4,785. With a folder per process (`-u`) four processes do scale (10,157
and 11,518). The container disk does not drop in the shared folder.

**Commit:** after a layerfs-only `mdtest -F -C -n 20000` (20,000 empty
files), one `sandbox.commit` took **3,643.5 ms** (about 182 µs per file):
logical 60 B (only the seed README has bytes), newCanonical 2,238,515 B,
newStored 168,272 B, newMetadata 168,272 B. `mdtest -r` then removed the
files at 5,540 files/s.

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

## Three-arm run

Run `20261020T002921Z` (same LayerFS v1.0.0 build, same Sandbox image and
`cases.tsv`) adds the FUSE baseline the v1.0.0 run lacked:
`passthrough-fuse`, libfuse's `passthrough_ll` (`fuse-3.14.0`, Debian
bookworm's libfuse3) over a plain folder in a sibling container on the
same Docker VM and kernel, built from this suite's image so mdtest and
Open MPI are the same bytes. The same mpirun command runs there as uid
501 through `docker exec`, right after the `layerfs` and `sandbox-disk`
arms of the same case. It is not LayerFS and does not use the SDK. Data:
[v1.0.0/three-arm](v1.0.0/three-arm/); record:
[20261020T002921Z](../../mdtest/records/20261020T002921Z.md).

25 of 27 case executions exited 0. The two failures are
`passthrough-fuse` only: `dirs-4p-shared` and `dirs-4p-unique` reached
the 115 s ceiling (`rc=124` at 111.0 s) on passthrough_ll, where LayerFS
took 37.6 s and 19.9 s. There is no LayerFS-only failure. The Commit pass
is LayerFS only: 20,000 empty files committed in **2,591.4 ms**.

Rates are ops/s (mdtest's `SUMMARY rate`, one iteration). **L/P =
LayerFS ÷ passthrough-fuse**, the like-for-like ratio; L/D = LayerFS ÷
kernel overlayfs (`sandbox-disk`), kept for reference; P/D =
passthrough-fuse ÷ kernel overlayfs, the cost of FUSE alone. Above 1, the
first arm was faster.

| Case | Phase | layerfs | passthrough-fuse | sandbox-disk | L/P | L/D | P/D |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| files, 1 proc, shared (`-F`, 20,000) | creation | 5,697 | 4,455 | 93,522 | 1.28 | 0.061 | 0.048 |
|  | stat | 696,185 | 11,020 | 717,674 | 63.2 | 0.97 | 0.015 |
|  | read | 16,781 | 5,096 | 532,881 | 3.29 | 0.032 | 0.0096 |
|  | removal | 6,811 | 6,922 | 174,684 | 0.98 | 0.039 | 0.040 |
| files, 1 proc, unique (`-F -u`) | creation | 4,143 | 3,707 | 69,917 | 1.12 | 0.059 | 0.053 |
|  | stat | 526,744 | 10,657 | 786,599 | 49.4 | 0.67 | 0.013 |
|  | read | 15,622 | 5,317 | 534,204 | 2.94 | 0.029 | 0.010 |
|  | removal | 5,689 | 6,586 | 175,339 | 0.86 | 0.032 | 0.038 |
| files, 4 procs, shared (`-F`, 4 × 20,000) | creation | 4,340 | 3,598 | 83,795 | 1.21 | 0.052 | 0.043 |
|  | stat | 3,365,877 | 5,104 | 1,436,528 | 659 | 2.34 | 0.0036 |
|  | read | 55,366 | 5,781 | 996,772 | 9.58 | 0.056 | 0.0058 |
|  | removal | 5,846 | 3,949 | 179,697 | 1.48 | 0.033 | 0.022 |
| files, 4 procs, unique (`-F -u`) | creation | 11,597 | 3,206 | 216,954 | 3.62 | 0.053 | 0.015 |
|  | stat | 3,007,855 | 3,839 | 1,403,928 | 784 | 2.14 | 0.0027 |
|  | read | 55,296 | 3,708 | 989,156 | 14.9 | 0.056 | 0.0037 |
|  | removal | 12,455 | 3,271 | 423,684 | 3.81 | 0.029 | 0.0077 |
| dirs, 1 proc, shared (`-D`) | creation | 6,136 | 6,613 | 35,719 | 0.93 | 0.17 | 0.19 |
|  | stat | 880,056 | 11,698 | 787,094 | 75.2 | 1.12 | 0.015 |
|  | rename | 6,311 | 4,940 | 100,254 | 1.28 | 0.063 | 0.049 |
|  | removal | 6,149 | 6,455 | 116,217 | 0.95 | 0.053 | 0.056 |
| dirs, 1 proc, unique (`-D -u`) | creation | 5,865 | 5,513 | 33,025 | 1.06 | 0.18 | 0.17 |
|  | stat | 754,514 | 10,258 | 643,377 | 73.6 | 1.17 | 0.016 |
|  | rename | 5,750 | 5,032 | 92,039 | 1.14 | 0.062 | 0.055 |
|  | removal | 6,589 | 6,329 | 94,443 | 1.04 | 0.070 | 0.067 |
| dirs, 4 procs, shared (`-D`) | creation | 6,440 | FAIL (115 s) | 21,416 | — | 0.30 | — |
|  | stat | 2,845,573 | FAIL (115 s) | 1,463,297 | — | 1.94 | — |
|  | rename | 6,600 | FAIL (115 s) | 83,155 | — | 0.079 | — |
|  | removal | 6,702 | FAIL (115 s) | 71,513 | — | 0.094 | — |
| dirs, 4 procs, unique (`-D -u`) | creation | 12,667 | FAIL (115 s) | 62,349 | — | 0.20 | — |
|  | stat | 2,864,717 | FAIL (115 s) | 1,884,742 | — | 1.52 | — |
|  | rename | 13,756 | FAIL (115 s) | 327,600 | — | 0.042 | — |
|  | removal | 12,105 | FAIL (115 s) | 287,635 | — | 0.042 | — |
| tree, 4 procs (`-z 2 -b 4`, 4 × 10,500): dirs | creation | 7,323 | 2,240 | 33,750 | 3.27 | 0.22 | 0.066 |
|  | stat | 2,382,160 | 5,650 | 1,752,774 | 422 | 1.36 | 0.0032 |
|  | rename | 7,721 | 4,517 | 153,384 | 1.71 | 0.050 | 0.029 |
|  | removal | 8,007 | 5,272 | 140,144 | 1.52 | 0.057 | 0.038 |
| tree, 4 procs: files | creation | 7,072 | 1,674 | 153,723 | 4.22 | 0.046 | 0.011 |
|  | stat | 2,404,531 | 3,661 | 1,152,040 | 657 | 2.09 | 0.0032 |
|  | read | 58,623 | 3,581 | 849,668 | 16.4 | 0.069 | 0.0042 |
|  | removal | 7,902 | 3,322 | 249,482 | 2.38 | 0.032 | 0.013 |

Tree creation and removal phases are left out of the ratios, as in
v1.0.0 (1–21 folders, mostly 0–9 ms at mdtest's 1 ms resolution); they are
in `results.csv`.

Where LayerFS stands against the FUSE baseline, in plain words:

- **Matches it with one process.** Single-process create, rename and
  removal of files and directories are within 0.86–1.28× of
  passthrough_ll. LayerFS is ahead on file creation (1.12–1.28) and
  directory rename (1.14–1.28), level on directory creation and removal
  (0.93–1.06), and behind on file removal (0.86–0.98).
- **Beats it with four processes.** passthrough_ll slows down when four
  processes share it (file creation 4,455 ops/s with one process,
  3,206–3,598 with four, 1,674 in the tree case); LayerFS holds or
  scales, so it is 1.21–4.22× ahead on every four-process create, rename
  and removal phase that both finished. The two four-process directory
  cases did not finish on passthrough_ll inside 115 s.
- **Stat and open/close: far ahead, by cache policy.** passthrough_ll
  replies with its default 1.0 s entry and attribute timeout, so by the
  time mdtest stats what it created each stat is a FUSE request
  (3.7–11.7k ops/s). LayerFS replies with a 60 s timeout, so the kernel
  answers from its cache (0.5–3.4 M ops/s). The 49–784× stat ratios and
  2.9–16× open/close ratios measure that policy difference, not daemon
  speed; a passthrough_ll with a longer timeout was not measured.
- **The FUSE hop is most of the gap to the kernel.** passthrough_ll runs
  create, rename and removal at 0.8–19 % of overlayfs (P/D 0.0077–0.19);
  LayerFS is at 2.9–30 % (L/D 0.029–0.30). With one process, most of
  LayerFS's distance from `sandbox-disk` on those phases is what any FUSE
  filesystem pays here.

Fairness notes (facts, not adjustments):

- `passthrough_ll` runs as root with no per-request credential switch
  (files it creates are owned by root) and without `default_permissions`.
  Its threading (up to 10 workers) and 1.0 s cache timeout are its
  defaults, not LayerFS's.
- `passthrough_ll` keeps nothing beyond the folder. LayerFS also records
  each change for Commit. Writeback is off in both.
- The sibling container and the Sandbox share the Docker VM, kernel and
  image layers, but they are different containers.
- The passthrough command ran under `timeout -k 3 110` inside the sibling,
  because the shared helper's perl alarm does not stop the docker CLI. A
  first measured attempt without it (`20261019T235618Z`) was stopped when
  `dirs-4p-shared` on passthrough_ll ran 115.16 s; its receipts are kept,
  its numbers are diagnostic only.
- One sample per case and arm, host 1-minute load 7.9–15.7. Cache state:
  warm/unknown, not cold.

`v1.0.0/three-arm/` holds `results.csv` (the v1.0.0 columns, `arm` now
including `passthrough-fuse`), `ratios.csv` (`case, phase, layerfs,
passthrough_fuse, sandbox_disk, layerfs_over_pt, layerfs_over_disk,
pt_over_disk`), `commit.csv`, `environment.csv` (with the passthrough
identity lines) and `receipts/` copied unchanged (also `arms.txt`,
`pt-identity.txt`, `pt-mount.txt` and the record).

## How to read it

- One sample per case and arm (`-i 1`), on a loaded Docker Desktop host
  (1-minute load 10.6–14.1). Speed is indicative. Cache state:
  warm/unknown, not cold.
- `wall_ms` is mdtest's own phase time (`SUMMARY time`, which mdtest
  labels ms/op but prints in seconds with 3 decimals) times 1000, so it
  has 1 ms resolution; short phases read 0–5 ms.
- `load` is the host's 1-minute load at the start of that case's client.

Each folder holds:

| File | What it is |
| --- | --- |
| `results.csv` | One row per case, arm and phase: `case, arm, procs, items_per_proc, unique_dir, phase, ops_per_s, wall_ms, load` (the commit pass's `-C` and `-r` cases appear as `commit-create` and `commit-remove`, layerfs only) |
| `commit.csv` | The one `sandbox.commit` after the create-only pass: files left, time, kind, ids, logical and new bytes, load |
| `environment.csv` | Source, binaries, images, upstream commit, mdtest and MPI build and args, Store, host, load |
| `receipts/` | The run's receipts, unchanged: `identity.txt`, `deploy.env`, `cases.tsv`, `commands.log`, `ledger.jsonl`, `results.jsonl`, `sandbox-identity.txt`, `summary.json` (with the ratios), `cases/*.txt` (mdtest's output per case and arm), and the run's `record.md` |

The CSVs are derived from the receipts by `benchmark/mdtest/report.py`;
everything else is copied unchanged from `benchmark-results/mdtest/`.

## Limits

- One node; MPI ranks share the Sandbox's 8 CPUs. Files are empty
  (`-w 0 -e 0`); no `-N` stride, random stat or shared-file mode.
- `sandbox-disk` is the container's overlayfs, not a raw block device.
- v1.0.0 was measured at `main` `e5c7aaae05` (the fs-bench v1.0.0 build)
  on Docker Desktop on an arm64 Mac, Disposable Store with policy 16/8/8.
