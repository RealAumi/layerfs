# smallfile — run 20261019T224809Z

> **Verdict:** COMPLETE, one sample per operation and arm. 18 / 18
> smallfile runs passed (9 / 9 `layerfs`, 9 / 9 `sandbox-disk`): exit 0,
> status `Success`, 100 % of 100,000 files processed in every operation.
> No LayerFS-only failure. LayerFS was slower than the container's overlayfs
> in every operation: smallfile's files/s ratio (layerfs ÷ sandbox-disk)
> ranged from 0.033 (append) to 0.227 (mkdir). One `sandbox.commit` of the
> 100,000 created files took 10,721.1 ms. Diagnostic host (arm64 Docker
> Desktop, 1-minute load 6.6–12.0).

## Identity

| Item | Value |
| --- | --- |
| LayerFS | core at `e5c7aaae05` (the fs-bench v1.0.0 build): daemon `431dc4f5…`, addon `242b4384…` |
| SDK | `sdk/js/src` in checkout `fs-bench-sdk-main` at `454d912f09`; `benchmark/smallfile` uncommitted (`harness_dirty_files=1`) |
| Sandbox image | `bench-smallfile:20261019` = `sha256:4d95be33a981…`, FROM `fs-bench-computer:gawk-20261020` (`sha256:66aeb6bb…`) |
| smallfile | distributed-system-analysis/smallfile `aa2519de5bf0b3b383db2c31eacbf8ac4328e19c` (version 1.0.2), Python 3.11.2, python3-yaml 6.0-3+b2 (Debian bookworm) |
| Runtime image | `layerfs-352-runtime:node24` = `sha256:d3773b4eac6a…` |
| Store | Disposable; policy 16/8/8; `LAYERFS_CONSTRUCTION_WORKERS=1`; SDK tracing off |
| Sandbox | Linux 6.12.76-linuxkit aarch64, 8 CPUs, uid 501 gid 20; `layerfs` arm on `/workspaces/1/sf` (fuse, `default_permissions,allow_other,max_read=131072`), `sandbox-disk` arm on `/tmp/sf` (overlayfs) |
| Host | Docker 29.5.2, Docker Desktop, 8 CPUs, 8.32 GB |
| Lock | taken 22:54:17Z, released 22:57:49Z |

## Parameters

Every operation, both arms:

```text
python3 /opt/smallfile/smallfile_cli.py --top <top> --operation <op> --threads 4 \
  --files 25000 --file-size 4 --stonewall N --finish Y --output-json /tmp/sf-out/<arm>/<op>/result.json
```

4 threads × 25,000 files of 4 KiB = 100,000 files (390.6 MiB) per arm;
smallfile defaults otherwise (100 files per directory, 10 directories per
directory, record size = file size, no fsync, verify-read on, compressible
data). 25,000 was chosen from the smoke runs below: LayerFS rename, the
slowest operation, ran at about 5,500 files/s, so 100,000 files keep every
exec near 20 s, well under 100 s.

## Commands

One client per step under the 115 s alarm; all 21 exited 0
(`commands.log`). `bench_setup` created the volumes at 22:48:09Z; the
measurement lock was held by pjdfstest, then fsstress, so `start` waited
four times (`perl -e 'sleep 90'` or `sleep 60`, then asked again) and took the lock at
22:54:17Z. Setup 22:54:17 (Init 16.7 ms, create 268.3 ms, mount 4.3 ms);
operations 22:54:23–22:57:48 at 1-minute load 6.61–10.33; Commit 22:54:48
(load 11.98); teardown 22:57:48–22:57:49 (unmount 112.8 ms, close 286.4 ms).
The longest exec was `rename` on `layerfs`, 21.4 s.

## Result

files/s, elapsed and MiB/s are smallfile's own (`--output-json`). Wall is
`date +%s%N` around the whole `smallfile_cli.py` process inside the
Sandbox; it includes about 3.6 s of smallfile start-up in each run, so
compare arms on files/s. Ratio is layerfs ÷ sandbox-disk files/s; "slower"
is its inverse.

| Op | layerfs files/s | sandbox-disk files/s | Ratio | LayerFS slower by | layerfs elapsed s | disk elapsed s | layerfs wall ms | disk wall ms | Load (lf / disk) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| create | 6,394 | 171,026 | 0.037 | 26.7× | 15.654 | 0.588 | 19,269.1 | 4,183.5 | 8.56 / 10.33 |
| read | 40,835 | 356,019 | 0.115 | 8.7× | 2.453 | 0.295 | 6,025.9 | 3,864.0 | 9.82 / 9.20 |
| append | 10,387 | 317,168 | 0.033 | 30.5× | 9.637 | 0.326 | 13,205.2 | 3,904.5 | 8.39 / 8.07 |
| stat | 51,150 | 946,583 | 0.054 | 18.5× | 1.982 | 0.106 | 5,554.2 | 3,671.3 | 7.67 / 7.53 |
| chmod | 40,326 | 625,310 | 0.064 | 15.5× | 2.487 | 0.163 | 6,048.4 | 3,762.0 | 7.06 / 7.37 |
| rename | 5,620 | 111,491 | 0.050 | 19.8× | 17.800 | 0.901 | 21,369.6 | 4,499.7 | 7.10 / 6.81 |
| delete-renamed | 7,762 | 230,063 | 0.034 | 29.6× | 12.891 | 0.437 | 16,472.3 | 4,032.0 | 6.61 / 7.52 |
| mkdir | 11,584 | 51,075 | 0.227 | 4.4× | 8.651 | 1.973 | 12,224.7 | 5,576.1 | 7.15 / 8.58 |
| rmdir | 12,938 | 69,543 | 0.186 | 5.4× | 7.732 | 1.517 | 11,323.5 | 5,144.2 | 7.87 / 7.42 |

MiB/s (data operations only): create 24.98 / 668.07, read 159.51 /
1,390.70, append 40.57 / 1,238.94 (layerfs / sandbox-disk).

Several `sandbox-disk` operations finished in 0.1–0.6 s of smallfile
elapsed time, so their files/s carry more timing noise than the LayerFS
numbers. The layerfs `read` ran after the Commit, so it read files from
the committed base rather than the Workspace overlay. One sample each;
cache state: warm/unknown, not cold.

### Commit

After the layerfs `create`, one `sandbox.commit` in its own client (not
inside any timed operation): **Committed in 10,721.1 ms** for the 100,000
created files (about 107 µs per file), commit `120e8a9104…`, base
`32e28c9861…`, logical 409,600,076 B, newCanonical 12,300,831 B, newStored
973,607 B, newMetadata 965,045 B. smallfile's default file content is
highly repetitive, so the stored bytes say nothing about real data.

## Other runs

- `smoke-20261019T224521Z`: the whole plan at 1,000 files per thread
  (4,000 files); 18 / 18 PASS; Commit of 4,000 files 404.5 ms. Used to
  check the harness and choose the file count. Not a measurement.
- `smoke-20261019T224745Z-scale`: only `create` on `layerfs` at 10,000 per
  thread (40,000 files, 6,811 files/s) and the Commit (4,003.8 ms), to check
  that Commit time stays inside the client alarm at 100,000 files. Not a
  measurement.

No measured run failed or was restarted.

## Receipts

`benchmark-results/smallfile/20261019T224809Z/` (Git-ignored):
`identity.txt`, `deploy.env`, `params.env`, `commands.log`,
`ledger.jsonl`, `results.jsonl`, `sandbox-identity.txt`, `ops/*.txt`,
`results.csv`, `commit.csv`, `summary.json`, each step's `.out` / `.err`.
Volumes removed 22:57:49Z; no `bench-smallfile-*` container or volume
remains.
