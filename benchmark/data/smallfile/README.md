# smallfile release data

> **Status:** Current general guide.

One folder per release with smallfile results: distributed-system-analysis
smallfile runs one operation at a time over many 4 KiB files with 4
threads, through `sandbox.exec` in a LayerFS Workspace (`layerfs`) and in
the same Sandbox's own overlayfs `/tmp` (`sandbox-disk`) as the reference.
The harness is [benchmark/smallfile](../../smallfile/README.md).

## v1.0.0

[v1.0.0](v1.0.0/): 4 threads × 25,000 files × 4 KiB = 100,000 files per
arm. files/s is smallfile's own figure. Ratio is LayerFS files/s ÷
sandbox-disk files/s: 1.0 would be the same speed, below 1.0 is slower on
LayerFS.

| Operation | layerfs files/s | sandbox-disk files/s | Ratio | LayerFS takes |
| --- | ---: | ---: | ---: | --- |
| create | 6,394 | 171,026 | 0.037 | 26.7× as long |
| read | 40,835 | 356,019 | 0.115 | 8.7× as long |
| append | 10,387 | 317,168 | 0.033 | 30.5× as long |
| stat | 51,150 | 946,583 | 0.054 | 18.5× as long |
| chmod | 40,326 | 625,310 | 0.064 | 15.5× as long |
| rename | 5,620 | 111,491 | 0.050 | 19.8× as long |
| delete-renamed | 7,762 | 230,063 | 0.034 | 29.6× as long |
| mkdir | 11,584 | 51,075 | 0.227 | 4.4× as long |
| rmdir | 12,938 | 69,543 | 0.186 | 5.4× as long |

**v1.0.0 in one line:** all 18 runs passed (smallfile exit 0, status
`Success`, 100 % of files processed) with no LayerFS-only failure, and
LayerFS was slower than the container's overlayfs in every operation, by
4.4× (mkdir) to 30.5× (append). The data-writing and namespace-changing
operations (create, append, rename, delete-renamed) are the slowest on
LayerFS at about 5,600–10,400 files/s; stat, chmod and
read run at about 40,000–51,000 files/s. One `sandbox.commit` of the
100,000 created files took 10,721.1 ms (about 107 µs per file).

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

[v1.0.0/three-arm](v1.0.0/three-arm/): a later run (`20261020T000127Z`)
of the same v1.0.0 build, image and parameters, with a third arm,
`passthrough-fuse`: libfuse's `passthrough_ll` (`fuse-3.14.0`) over a plain
directory in a sibling container, the like-for-like FUSE reference. It is
not LayerFS and uses no SDK call; smallfile runs there through
`docker exec` as uid 501, gid 20. Per operation the arms ran layerfs, then
sandbox-disk, then passthrough-fuse. The one `sandbox.commit` (LayerFS
only, 10,430.5 ms) followed the layerfs create, so the layerfs read ran
after it. The two-arm v1.0.0 section above is a different run and is
unchanged.

files/s is smallfile's own figure. Each ratio divides the first arm's
files/s by the second's: above 1.0 the first arm is faster.

| Operation | layerfs files/s | passthrough-fuse files/s | sandbox-disk files/s | **LayerFS ÷ passthrough-fuse** | LayerFS ÷ kernel overlayfs | passthrough-fuse ÷ kernel overlayfs |
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

- **LayerFS ÷ passthrough-fuse** (like for like): all 27 runs passed, and
  LayerFS beat the FUSE baseline in every operation. It led narrowly in
  delete-renamed (1.27×), append (1.72×), rename (1.75×) and create
  (2.03×), and widely in read (3.0×), rmdir (3.3×), chmod (3.4×), mkdir
  (4.2×) and stat (10.7×). It matched or trailed the baseline in no
  operation.
- **LayerFS ÷ kernel overlayfs** (reference, as in v1.0.0): slower in every
  operation, 0.018 (chmod) to 0.460 (read).
- **passthrough-fuse ÷ kernel overlayfs** (the cost of FUSE alone):
  0.005 (stat, chmod) to 0.152 (read); on this host a plain FUSE
  passthrough loses more to overlayfs than LayerFS does in every
  operation.
- The read, chmod and rmdir figures differ from the two-arm v1.0.0 run:
  sandbox-disk read 28,651 against 356,019 files/s, layerfs read 13,176
  against 40,835, layerfs chmod 17,275 against 40,326, sandbox-disk rmdir
  173,828 against 69,543. Not diagnosed; page cache state was unknown
  (the passthrough create added another 390.6 MiB of files on the same
  8 GB Docker VM before the reads, and other suites ran on the host).
  One sample per operation and arm, 1-minute load 6.66–11.51.

Fairness notes (facts, not adjustments):

- `passthrough_ll` runs as root and does no per-request credential switch.
  Files it creates are owned by root, and it doesn't use
  `default_permissions`. Its threading (up to 10 workers) and cache
  timeout (1.0 s) are its defaults, not LayerFS's.
- `passthrough_ll` keeps nothing beyond the directory. LayerFS also
  records each change for Commit. Both have kernel writeback caching off.
- `passthrough_ll` finds inodes by walking one linked list of every inode
  it holds, under one mutex, on each lookup (`lo_find`). Its cost per
  request grows with the inodes the kernel references: in the smoke runs
  its create fell from 8,769 files/s at 4,000 files to 2,825 at 100,000,
  while LayerFS's went from 6,747 to 5,777. Part of LayerFS's margin at
  100,000 files is that list, not FUSE itself; a FUSE server with an
  indexed inode table (for example libfuse's `passthrough_hp`) was not
  measured.
- The sibling container and the Sandbox share the Docker VM, kernel and
  image layers, but they are different containers. `exec_ms` for
  passthrough-fuse is the host-side `docker exec` time, not a
  `sandbox.exec` time; `wall_ms` is timed inside the container in all
  three arms.

`three-arm/` holds `results.csv` and `commit.csv` (as below, with `arm`
now including `passthrough-fuse`), `environment.csv` (with the `pt_*`
passthrough identity lines) and `receipts/` copied unchanged from
`benchmark-results/smallfile/20261020T000127Z/` (plus `pt-identity.txt`,
`pt-mount.txt`, `pt-image.txt` and the run's `record.md`).

## How to read it

- files/s, MiB/s, elapsed and `pct_files_done` are smallfile's own
  `--output-json` figures. Its elapsed time runs from its starting gate to
  the last thread's finish.
- `wall_ms` is `date +%s%N` around the whole `smallfile_cli.py` process
  inside the Sandbox. It excludes the `sandbox.exec` overhead but includes
  about 3.6 s of smallfile start-up per run, so the wall-time ratio
  understates the difference; use files/s to compare arms.
- `PASS` means smallfile exit 0, status `Success` and 100 % of files
  processed (`--stonewall N --finish Y` make every thread finish its files).
- Several `sandbox-disk` operations took only 0.1–0.6 s of smallfile time,
  so their files/s carry more timing noise than the LayerFS figures.
- The layerfs `read` ran after the Commit, so it read files from the
  committed base rather than the Workspace overlay.
- One sample per operation and arm on a loaded Docker Desktop host
  (1-minute load 6.6–10.3 during the operations). Indicative only. Cache
  state: warm/unknown, not cold.

Each folder holds:

| File | What it is |
| --- | --- |
| `results.csv` | One row per operation and arm: `op, arm, threads, files_per_thread, file_size_kb, files_per_s, mb_per_s, elapsed_s, pct_files_done, wall_ms, load`, then `result, status, files, exit, exec_ms` (the exec's client-side time) and `sandbox_loadavg` (the Sandbox's `/proc/loadavg` at start). `load` is the host's 1-minute load when the client started; `mb_per_s` is MiB/s and exists only for create, read and append |
| `commit.csv` | The one `sandbox.commit` after the layerfs create: files, time, load, kind, ids, logical and new bytes |
| `environment.csv` | Source, binaries, images, upstream commit, smallfile args, Store, host, load |
| `receipts/` | The run's receipts, unchanged: `identity.txt`, `deploy.env`, `params.env`, `commands.log`, `ledger.jsonl`, `results.jsonl`, `sandbox-identity.txt`, `summary.json`, `ops/*.txt` (smallfile's output and JSON result per operation and arm), and the run's `record.md` |

The CSVs are derived from the receipts by `benchmark/smallfile/report.py`;
everything else is copied unchanged from `benchmark-results/smallfile/`.

## Limits

- Only create, read, append, stat, chmod, rename, delete-renamed, mkdir and
  rmdir were run; smallfile's xattr, symlink, overwrite, truncate, readdir
  and ls-l operations and its multi-host mode were not.
- smallfile's default file content is highly repetitive, so the Commit's
  stored bytes (973,607 B for 409,600,076 logical) are not a storage result.
- `sandbox-disk` is the container's overlayfs on the Docker Desktop VM
  disk, not a raw block device; both arms share one Sandbox and run one
  after the other.
- v1.0.0 was measured at `main` `e5c7aaae05` (the fs-bench v1.0.0 build)
  on Docker Desktop on an arm64 Mac, Disposable Store with policy 16/8/8.
