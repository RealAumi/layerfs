# fsx

> **Status:** Current general guide.

Single-file data integrity: xfstests' `ltp/fsx` drives one file through a
seeded random mix of reads, writes, mapped reads and writes, truncates,
fallocate modes and copy/clone ranges, and checks every read and the file
size against its in-memory model. One of the
[#365](https://github.com/Ephemeral-AI-Lab/layerfs/issues/365) suites; it
uses the shared harness in [benchmark/common](../common/README.md).

## Route and arms

Everything goes through the public JavaScript SDK. fsx itself runs only
through `sandbox.exec`, as uid 501 in the suite's Sandbox image.

```text
setup     project.init(seed folder) → sandbox.create → branch.fork("bench", "main") → sandbox.mount
          exec: fsx identity, kernel, both arms' filesystems; mkdir both fsx folders
next      per case and arm: exec fsx (measured) → exec read-back (untimed)
commit    sandbox.commit of the Workspace, after every case (timed)
teardown  sandbox.unmount (terminal) → sandbox.close; volumes removed
```

| Arm | Folder | Filesystem |
| --- | --- | --- |
| `layerfs` | `<mounted Workspace>/fsx/<variant>-s<seed>/` | LayerFS FUSE mount |
| `sandbox-disk` | `/tmp/fsx/<variant>-s<seed>/` | the Sandbox container's overlayfs (reference) |

Both arms run the same fsx command with the same seed in the same Sandbox,
one after the other. fsx probes each optional op at start and prints
`does not support ..., disabling!` for the ones the filesystem refuses
(fallocate modes: `ENOSYS` or `EOPNOTSUPP`); that op is then skipped in the
run. A disabled op is recorded in `unsupported_ops`, not as a failure.

## Variants

`cases.tsv` is the measured plan; each row runs in both arms. Every case
also gets `-N <ops> -S <seed> -P <folder> <folder>/f`.

| Variant | fsx arguments | What it covers |
| --- | --- | --- |
| `default` | (none: `-l 262144 -o 65536`, unaligned, mmap on) | the upstream defaults; fallocate, punch, zero, collapse, insert, copy/clone/dedupe/exchange range auto-detected |
| `no-mmap` | `-R -W` | read/write system calls only |
| `aligned` | `-r 4096 -w 4096 -t 4096` | page-aligned reads, writes and truncates |
| `medium` | `-l 4194304` | 4 MiB file: crosses the 1 MiB point of #361 with 64 KiB ops |
| `large` | `-l 67108864 -o 1048576` | 64 MiB file, ops up to 1 MiB, mmap on |
| `large-no-mmap` | `-l 67108864 -o 1048576 -R -W` | the same without mapped I/O |
| `direct` | `-Z -R -W -r 4096 -w 4096` | `O_DIRECT`, page-aligned (fsx asks for `-R -W -r -w` with `-Z`) |

Seeds 1 and 2 for every variant. Op counts keep each fsx exec near 30 s on
this host, well under the 115 s client limit; a longer run is split into
more seeds, not more ops.

## Files

| Path | Role |
| --- | --- |
| `run.sh` | One step per command: `image`, `setup`, `start`, `next`, `commit`, `probe`, `teardown`, `report` |
| `cases.tsv` | Measured plan (variant, seed, ops, fsx args) |
| `cases-smoke.tsv`, `cases-probe.tsv` | Smoke plan (small op counts); empty plan for the fallocate probe |
| `sandbox/Dockerfile` | `FROM fs-bench-computer:gawk-20261020`; xfstests-dev at `22348afe338c0f6d540c0d7ef0db749eaa51b218`, `make configure`, `./configure`, `make -C lib`, `make -C ltp fsx`; `/usr/local/bin/fsx` and `/opt/fsx-identity.txt` |
| `client/setup.mjs` | Init, create, fork, mount (`common/session.mjs`); identity probe; both arms' folders |
| `client/case.mjs` | One case in one arm: the measured fsx exec and the read-back exec |
| `client/commit.mjs` | The one `sandbox.commit` after all cases |
| `client/probe.mjs` | Diagnostic: each fallocate mode's error text with `fallocate(1)`, both arms |
| `client/teardown.mjs` | Unmount and close |
| `report.py` | `results.csv`, `commit.csv` and `summary.json` from the receipts |
| `records/` | One record per measured run |

## Running

```bash
B=benchmark/fsx
$B/run.sh image                               # once per image change
RUN=$PWD/benchmark-results/fsx/$(date -u +%Y%m%dT%H%M%SZ)
$B/run.sh setup $RUN $B/cases.tsv measured    # exit 75: lock held; wait, then $B/run.sh start $RUN measured
$B/run.sh next $RUN                           # one case and arm per command; repeat until DONE
$B/run.sh commit $RUN
$B/run.sh teardown $RUN                       # unmount, close, volumes, lock
$B/run.sh report $RUN
```

A smoke run uses `benchmark-results/fsx/smoke-<id>`, `cases-smoke.tsv`
and `smoke` (no lock). The fallocate probe runs in a smoke run:
`setup ... cases-probe.tsv smoke`, `probe`, `teardown`.

## Receipts

`RUN/results.jsonl` (one row per case and arm: fsx's exit, the in-Sandbox
wall time around fsx alone, the exec's client-side time),
`RUN/cases/<variant>-s<seed>-<arm>.txt` (fsx's output, the `.fsxlog` tail,
`ls -l`, and after a failure the first differing bytes against `.fsxgood`
and its tail), `ledger.jsonl` (setup, probe, Commit, teardown),
`sandbox-identity.txt`, `identity.txt`, `deploy.env`, `cases.tsv`,
`commands.log`, and each step's `.out` / `.err`.

## Reading the result

- **result:** `PASS` is fsx's own `All N operations completed A-OK!` with
  exit 0; `FAIL` is any other fsx exit (its code says which check: 110 bad
  data, 120 size, 151 write, 161 fallocate or range op, 190–205 mmap); `HARNESS` means the
  exec itself failed. `first_failure` is fsx's first error line and the
  last op of its log dump.
- **ops_per_s** is ops over the in-Sandbox wall time of the fsx process
  alone. One sample per case and arm; the host is loaded (other suites,
  Docker Desktop), so treat speed as indicative. Cache state: warm/unknown,
  not cold.
- **LayerFS-only** differences are ops or results the `sandbox-disk` arm
  does not share (`summary.json` `layerfs_only`).

## Known limits

- fsx's AIO (`-A`) and io_uring (`-U`) modes, `-X` (verify after every op)
  and the dm-log-writes integrity mode are not run.
- The two arms share one Sandbox and run sequentially, not concurrently.
- `sandbox-disk` is overlayfs in the container, not a raw block device; it
  refuses clone/dedupe/exchange range and the newer fallocate modes too.
