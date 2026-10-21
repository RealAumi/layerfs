# fsx — run 20261019T222512Z

> **Verdict:** COMPLETE, one sample per case and arm. 28 / 28 fsx runs
> passed: 14 / 14 `layerfs`, 14 / 14 `sandbox-disk`, 3,056,000 ops per arm,
> no data or size miscompare. The one LayerFS-only difference is fallocate:
> modes 0, `KEEP_SIZE`, `PUNCH_HOLE|KEEP_SIZE`, `ZERO_RANGE`,
> `COLLAPSE_RANGE` and `INSERT_RANGE` fail `EOPNOTSUPP` on the mount, so fsx
> disables them there. The Workspace committed afterwards (457.2 ms).
> Diagnostic host (arm64 Docker Desktop, load 7.5–14.9 during the cases).

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK | `sdk/js/src` in checkout `fs-bench-sdk-main` at `3a629cfbf0`; `benchmark/fsx` uncommitted (`harness_dirty_files=1`) |
| Sandbox image | `bench-fsx:20261019` = `sha256:bd687dfd1d5e…`, FROM `fs-bench-computer:gawk-20261020` (`sha256:66aeb6bb…`) |
| fsx | xfstests-dev `22348afe338c0f6d540c0d7ef0db749eaa51b218`, `ltp/fsx` built with `./configure` (AIO, io_uring, fallocate, copy_file_range on); binary `sha256:400b8e1c…`; gcc 12.2.0, liburing 2.3-3, libaio 0.3.113-4, xfslibs-dev 6.1.0-1 |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Sandbox | Linux 6.12.76-linuxkit aarch64, uid 501 gid 20; `layerfs` arm on `/workspaces/1/fsx` (fuse, `default_permissions,allow_other,max_read=131072`), `sandbox-disk` arm on `/tmp/fsx` (overlayfs) |
| Host | Docker 29.5.2, Docker Desktop, 8 CPUs, 8.32 GB |
| Lock | taken 22:25:14Z, released 22:38:02Z |

## Commands

One client per step under the 115 s alarm; all 32 exited 0
(`commands.log`). Setup 22:25:14–22:25:15 (Init 21.5 ms, create 346.7 ms,
mount 5.7 ms); cases 22:25:20–22:37:50 at 1-minute load 7.45–14.87; Commit
22:37:55 (load 22.34); teardown 22:38:01–22:38:02 (unmount 42.8 ms, close
236.7 ms). The longest exec was `direct` seed 2 on `sandbox-disk`, 53.9 s.

## Result

fsx arguments are the variant's plus `-N <ops> -S <seed> -P <folder> <folder>/f`.
Wall time is the fsx process alone, timed inside the Sandbox.

| Variant | Seed | Ops | layerfs | ms | ops/s | sandbox-disk | ms | ops/s |
| --- | ---: | ---: | --- | ---: | ---: | --- | ---: | ---: |
| default | 1 | 300,000 | PASS | 37,601.8 | 7,978 | PASS | 33,985.6 | 8,827 |
| default | 2 | 300,000 | PASS | 32,240.4 | 9,305 | PASS | 36,482.4 | 8,223 |
| no-mmap (`-R -W`) | 1 | 300,000 | PASS | 31,107.2 | 9,644 | PASS | 13,176.3 | 22,768 |
| no-mmap | 2 | 300,000 | PASS | 30,811.8 | 9,737 | PASS | 14,410.2 | 20,819 |
| aligned (`-r/-w/-t 4096`) | 1 | 300,000 | PASS | 26,316.1 | 11,400 | PASS | 28,468.3 | 10,538 |
| aligned | 2 | 300,000 | PASS | 24,907.8 | 12,044 | PASS | 27,868.8 | 10,765 |
| medium (`-l 4194304`) | 1 | 200,000 | PASS | 25,810.2 | 7,749 | PASS | 21,187.8 | 9,439 |
| medium | 2 | 200,000 | PASS | 28,423.5 | 7,036 | PASS | 28,253.9 | 7,079 |
| large (`-l 67108864 -o 1048576`) | 1 | 12,000 | PASS | 9,789.6 | 1,226 | PASS | 5,974.9 | 2,008 |
| large | 2 | 12,000 | PASS | 11,044.2 | 1,087 | PASS | 5,814.5 | 2,064 |
| large-no-mmap (`… -R -W`) | 1 | 16,000 | PASS | 12,934.1 | 1,237 | PASS | 6,046.0 | 2,646 |
| large-no-mmap | 2 | 16,000 | PASS | 11,661.9 | 1,372 | PASS | 7,076.9 | 2,261 |
| direct (`-Z -R -W -r/-w 4096`) | 1 | 400,000 | PASS | 29,643.0 | 13,494 | PASS | 33,380.0 | 11,983 |
| direct | 2 | 400,000 | PASS | 32,434.2 | 12,333 | PASS | 53,782.2 | 7,437 |

Per variant (Σ ops ÷ Σ wall, both seeds), layerfs ÷ sandbox-disk ops/s:
default 8,591 / 8,515 (1.01), no-mmap 9,690 / 21,750 (0.45), aligned
11,713 / 10,650 (1.10), medium 7,375 / 8,090 (0.91), large 1,152 / 2,036
(0.57), large-no-mmap 1,301 / 2,438 (0.53), direct 12,887 / 9,178 (1.40).
One sample each under load 7–15; the seed-to-seed spread on the same arm
(direct on `sandbox-disk`: 11,983 vs 7,437) is as large as some arm
differences.

### What fsx disabled

| Arm | Disabled at start (fsx's probe) |
| --- | --- |
| layerfs | fallocate 0, `KEEP_SIZE`, `UNSHARE_RANGE`, `PUNCH_HOLE\|KEEP_SIZE`, `ZERO_RANGE`, `WRITE_ZEROES`, `COLLAPSE_RANGE`, `INSERT_RANGE`; clone, dedupe and exchange range; dontcache I/O; atomic writes |
| sandbox-disk | fallocate `UNSHARE_RANGE`, `WRITE_ZEROES`; clone, dedupe and exchange range; dontcache I/O; atomic writes |

Atomic writes are off in both arms (without `-Z`: "need O_DIRECT"; with
`-Z`: "IO Stack does not support atomic writes"). `copy_file_range` was
enabled and exercised in both arms (`copying to largest ever` lines).

LayerFS-only: fallocate modes 0, `KEEP_SIZE`, `PUNCH_HOLE|KEEP_SIZE`,
`ZERO_RANGE`, `COLLAPSE_RANGE`, `INSERT_RANGE`, in every variant. The error
text comes from a separate diagnostic smoke run
(`smoke-20261019T223849Z-probe`, `client/probe.mjs`, util-linux
`fallocate(1)` on a 64 KiB file in each arm):

| Mode | layerfs | sandbox-disk |
| --- | --- | --- |
| 0 (`fallocate -l 131072 f`) | `fallocate failed: Operation not supported` | exit 0 |
| `KEEP_SIZE` (`-n -o 65536 -l 65536`) | `fallocate failed: keep size mode is unsupported` (util-linux's text for `EOPNOTSUPP` with keep size) | exit 0 |
| `PUNCH_HOLE` (`-p -o 4096 -l 4096`) | same as `KEEP_SIZE` | exit 0 |
| `ZERO_RANGE` (`-z -o 4096 -l 4096`) | `fallocate failed: Operation not supported` | exit 0 |
| `COLLAPSE_RANGE` (`-c -o 0 -l 4096`) | `fallocate failed: Operation not supported` | exit 0 |
| `INSERT_RANGE` (`-i -o 0 -l 4096`) | `fallocate failed: Operation not supported` | exit 0 |

### Issue #361 items at v1.0.0

| v0.1.6 report | v1.0.0 here |
| --- | --- |
| writes past ~1 MiB fail | PASS: `medium` grows the file to 4 MiB (largest truncate 0x3ffe46) and `large` to 64 MiB (largest copy end 0x3ff8700) with ops up to 1 MiB, in both seeds and with and without mmap |
| mmap writes fail | PASS: mapped writes on in `default`, `aligned`, `medium` and `large` |
| fallocate fails | still refused: every fallocate mode returns `EOPNOTSUPP`; fsx disables them, so no fallocate, punch, zero, collapse or insert op ran on LayerFS |
| `O_DIRECT` | PASS: `open(O_DIRECT)` succeeds on the mount and 800,000 `-Z` ops passed |

### Commit

After all cases, one `sandbox.commit` of the Workspace (both arms' files
were left in place; only the `layerfs` arm's are in the Workspace):
**Committed in 457.2 ms**, commit `12ce6e8742…`, base `32ea5132bc…`,
logical 166,731,557 B, newCanonical 27,079,792 B, newStored 15,292,443 B,
newMetadata 50,689 B.

## Other runs

- `smoke-20261019T222254Z`: `cases-smoke.tsv` (2,000 ops, 500 for the
  large variants, seed 1), 14 / 14 PASS, Commit 187.1 ms; used to choose op
  counts. Not a measurement.
- `smoke-20261019T223849Z-probe`: the fallocate diagnostic above, after the
  measured run.

No measured run failed or was restarted. Cache state: warm/unknown, not cold.

## Receipts

`benchmark-results/fsx/20261019T222512Z/` (Git-ignored): `identity.txt`,
`deploy.env`, `cases.tsv`, `commands.log`, `ledger.jsonl`,
`results.jsonl`, `sandbox-identity.txt`, `cases/*.txt`, `results.csv`,
`commit.csv`, `summary.json`, each step's `.out` / `.err`. Volumes removed
22:38:02Z; no `bench-fsx-*` container or volume remains.
