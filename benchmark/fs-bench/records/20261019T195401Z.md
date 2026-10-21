# fs-bench pair `20261019T195401Z`: LayerFS core fully through `sandbox.exec`, gawk image

> **Status:** Dated campaign record.
> - **Pair: VALID.** `compare.py`, including its saturation check, accepted
>   all twelve rows for both arms. The largest statistic was 1,677,186,334 ns.
> - **Numbers: one sample each.** They are not medians or a repeatability
>   claim.
> - **Warm-state rows:** `pure read`, `pure copy` and `overwrite` are
>   own-write warm.
> - **Supersedes `20261019T193128Z` as the LayerFS arm of record.** Here every
>   LayerFS command goes through the public JS SDK's `sandbox.exec`.
> - **Not release evidence.**

This repeats [`20261019T194736Z`](20261019T194736Z.md), with one fix. That
pair was INCOMPLETE because two Computer rows saturated at mawk's 32-bit
`%d`. Both arms now run on one image that adds GNU awk as `awk`
([`computer/gawk.Dockerfile`](../computer/gawk.Dockerfile)), one layer over
the previous image `sha256:9c145fbc…`. The runner uses awk only after each
row's clock stops, to compute and print the statistics, so the fix changes no
timed work. The image changed, so this is a new pair, not a retry.

The routes are the same as in `194736Z`:

- **Computer:** `docker exec` as root.
- **LayerFS:** set up through the SDK by
  [`holder/run-holder.sh`](../holder/run-holder.sh) (`project.init`,
  `sandbox.create`, `branch.fork`, `sandbox.mount`). `run.sh` sdk mode then
  makes three `sandbox.exec` calls through [`holder/exec.mjs`](../holder/exec.mjs):
  identity and mount check, stage+hash+run, then collect+cleanup.

Raw receipts are in `benchmark-results/fs-bench/20261019T195401Z/` of the
`fs-bench-sdk-main` worktree, which Git ignores.

## Identity and custody

| Field | Receipt value |
| --- | --- |
| Family, cases, order | Cloudflare Computer `fs-bench.sh` (SHA-256 `0e2004339a92…`), twelve offline scenarios in fixed order; `REPS=1 WARMUP=0 RANDOMIZE_TARGETS=0`; no `BASE`. `computer-upstream`, then `layerfs-core`. |
| Source: Computer | `de87919a4fd3…`, tree `4fb409d7e135…`. Provenance **verified** (labels carried into the gawk image). |
| Source: LayerFS core | `main` at `e5c7aaae05229a9edd7a18eed6a94154b9f771b1`; `core` tree `963afa1e1f7d`, `sdk` tree `7bb343576d89`, both clean against HEAD. Provenance **unverified** (shared image carries the Computer labels). |
| Image | `sha256:66aeb6bbf7fc825686a0e6d8c8486d90c99d03ce81f854008f179a23bdf4097e` (arm64), built with `computer/gawk.Dockerfile` (SHA-256 `ded33a18…`) from base `sha256:9c145fbc292a…`. Checked before the pair: `awk` → `/usr/bin/gawk` 5.2.1, `printf "%d"` of 3,000,000,000 is exact, Git 2.39.5, Bash 5.2.15. Shared by both arms and used as the Sandbox image. |
| Command routes (manifest `command_route`) | **Computer:** `docker exec`, `exec_user` `0:0`. **LayerFS:** `sandbox.exec (@layerfs/sdk), Sandbox bench`, `exec_user` `501:20`, as reported by the first call. All three calls exited 0 with `truncated: false`. |
| LayerFS binaries | Daemon `431dc4f5…` and Linux addon `242b4384…`, built at `e5c7aaae05`; client runtime `layerfs-352-runtime:node24` (`d3773b4eac6a`). SDK daemon settings: `cache_bytes` 64 MiB, `namespaces` 16, `pager_kib` 1024. |
| Collector | Uncommitted `benchmark/fs-bench` on worktree branch `fs-bench-sdk-main`; `run.sh` `235474e5…`, `compare.py` `ae29a111…` (with the saturation check), `exec.mjs` `f112d151…`, `holder.mjs` `56431691…`, `client.sh` `8d524382…`, `run-holder.sh` `d865e359…`. |
| Workspace root | One-file project on fresh volume `fs-bench-core-20261019T195401Z`; SDK home on `…-sdk-home`; Branch `bench` forked from `main`; mount `/workspaces/1`. Released `Unmounted`/`CLOSED`; both volumes removed. |
| Host, load and interference | Same host as the earlier pairs. 1-minute load **7.48** at the Computer arm and **8.16** at the LayerFS arm. No other container was running during either arm. |
| Mounts | **Computer:** `/workspace`, `fuse` `/dev/fuse`, `relatime`, `max_read=524288`, privileged. **LayerFS:** `/workspaces/1`, `fuse` `layerfs`, `noatime`, `default_permissions,allow_other,max_read=131072`, unprivileged Sandbox with `CAP_SYS_ADMIN`, writeback off. |
| Commands | `run.sh computer-upstream docker fs-bench-computer-20261019T195401Z /workspace 20261019T195401Z`; `holder/run-holder.sh <home> sha256:66aeb6bb… fs-bench-core-20261019T195401Z <daemon> <addon> fsbench fsbench-pair-`; `run.sh layerfs-core sdk <home> bench /workspaces/1 20261019T195401Z`; each collector under a 115 s limit; then `compare.py 20261019T195401Z`. |

## Check before the pair

On the gawk image, before any timed run:

- **Computer:** started healthy, `/workspace` mounted as FUSE, and a write
  and read worked.
- **SDK holder:** set up and mounted on a fresh volume. One `sandbox.exec`
  call reported:
  - `501:20`;
  - `/usr/bin/gawk`, printing 3000000000;
  - the LayerFS FUSE mount.

  The holder then released (`Unmounted`, `CLOSED`), and its volumes were
  removed.

## Results (raw ns, one sample per arm)

| Scenario | Cache state | computer-upstream ns | layerfs-core ns | Computer ÷ LayerFS |
| --- | --- | ---: | ---: | ---: |
| create 1000 files | self-contained | 1,396,236,542 | 413,045,167 | 3.38 |
| stat 1000 files | self-contained | 1,677,186,334 | 1,071,464,250 | 1.57 |
| rm 1000 files | self-contained | 1,236,643,709 | 475,568,667 | 2.60 |
| mkdir tree (10x10x10) | self-contained | 1,406,576,209 | 835,242,751 | 1.68 |
| find tree | self-contained | 1,502,291,959 | 960,366,251 | 1.56 |
| write 64 MiB | self-contained | 127,213,167 | 160,365,625 | 0.79 |
| copy 64 MiB | self-contained | 351,905,750 | 598,285,167 | 0.59 |
| read 64 MiB | self-contained | 178,903,167 | 178,277,083 | 1.00 |
| pure read 64 MiB | own-write warm | 78,430,458 | 7,430,083 | 10.56 |
| pure copy 64 MiB | own-write warm | 224,265,625 | 209,113,958 | 1.07 |
| overwrite 64 MiB | own-write warm | 168,876,042 | 110,921,791 | 1.52 |
| git init + commit 100 files | self-contained | 535,192,042 | 181,144,250 | 2.95 |
| Convenience sum | — | 8,883,721,004 | 5,201,225,043 | 1.71 |

LayerFS core had the lower time in **10 of 12** rows. Computer had the lower
time in two:

- `write 64 MiB`, by 33.2 ms;
- `copy 64 MiB`, by 246.4 ms.

`read 64 MiB` is counted as a LayerFS win by 0.6 ms, which is within any
plausible noise for one sample. The ratio is
`computer_median_ns ÷ layerfs_median_ns` from `comparison.json`. The sum is
not an agent-turn duration.

| Arm | Runner user | Collector exit | Complete collector command ns / bound | Rows OK |
| --- | --- | ---: | ---: | ---: |
| computer-upstream | `0:0` | 0 | 12,956,630,016 / 15 s | 12 / 12 |
| layerfs-core | `501:20` | 0 | 11,650,160,896 / 15 s | 12 / 12 |

The LayerFS command includes three SDK client starts in the runtime image.
Each row is timed inside the script, so the route is outside every row's
timer.

## Limits on reading these numbers

- **Single samples.** The load was 7–8, lower than for any earlier pair, but
  the host was not quiet. Earlier pairs on this host moved by up to about 2×
  per row between runs. Read each row as one observation.
- **`copy 64 MiB` is LayerFS's weakest row here.** It took 599 ms, against
  278 ms in `191404Z` and 359 ms in `193128Z`, on the same daemon build at
  higher load. One sample can't separate a route or image effect from
  variance. A repeat on a quiet host would be needed before treating it as
  a regression.
- **Different FUSE and container profiles, by design.** Computer has a
  larger `max_read`, auto_cache, `relatime` and a privileged container.
  LayerFS has a smaller `max_read`, no writeback, `noatime` and the SDK's
  narrower container.
- **Scope.** The rows exercise zero-filled inputs, resident FUSE operations
  and native arm64 in Docker Desktop on macOS. Setup, Commit and unmount are
  outside the timer. A native x86-64 Linux host remains the route to a
  qualifying pair.

## Disposition

| Item | Value |
| --- | --- |
| Non-passing items | None. `20261019T194736Z` stays INCOMPLETE. |
| Reproduction | The commands above, with [`computer/Dockerfile`](../computer/Dockerfile) plus [`computer/gawk.Dockerfile`](../computer/gawk.Dockerfile) and the [SDK holder](../holder/). |
| Next | Commit the package, plan and records. For a qualifying pair, run on a quiet or native x86-64 host. |
| Production LOC | No commit made. |

## Key evidence SHA-256

```text
7cd08a51da156786ed26547de81fe5faa19ac9e04fa23bbd6d01d7e849f2cf68  comparison.json
27fa3c54b655b6e16431416ac1af2ebd4057ea17d0ed26f0519e3ac89b9ff634  comparison.md
139ac273e64670f95bf915cee0a6850e51ba486023bf62c5bec2933a7cbd8c7e  computer-upstream/result.json
d982d7391a7797b0e25cdc05b2eeabb409329c0076d0815ab4d77871d1e5c693  layerfs-core/result.json
59a783fa1616cbfd3056343861f018d52780be7af24cec98074b66fe7925d378  computer-upstream/manifest.tsv
04a0313deec45fc5f2500807a9d468fb157b42ad68651d2f79298a85c819ceec  layerfs-core/manifest.tsv
d6c1dcd060a927cfd634495a9e37eb9599fb0ee87d1feb23d177a34aa2cd7553  layerfs-core/sdk-check.json
1e01609119b4819705e35922c11be49bec3819221c892bc914ea42656d14f618  layerfs-core/sdk-run.json
c6c48ba2a22727d9e2a68138a83684d6107a4e70a18d17881ad1ae5ae17cd01e  layerfs-core/sdk-collect.json
0df829af49cd1eb7870a541206d29d232336bf3c301b7a72759dde22e30b2fa0  layerfs-core-holder.log
39086786995be87651b11700cb8a1bd8d7bdbfad6165c6b61e7d40775045231c  layerfs-core-daemon.log
d9ff7527b89fdff820d380bbe91f56958be518a32800df07604dc1b9191b3c31  layerfs-core-deploy.env
bac04b91b6c8f02417f2a853aae9bfac6778c2342b8d67cab42a0168ad4b74dd  computer-upstream-daemon.log
```
