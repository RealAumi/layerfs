# First `fs-bench` pair: Computer upstream vs LayerFS core

> **Status:** Dated plan, 2026-10-20; not evidence or a performance claim.
> The first pair, [`20261019T190859Z`](records/20261019T190859Z.md), is
> INCOMPLETE. The git row failed on `layerfs-core` because the collector runs
> as root, while LayerFS projects every inode as the command identity
> (501:20). The second pair,
> [`20261019T191404Z`](records/20261019T191404Z.md), runs each arm as its
> mount user and is VALID. The third pair,
> [`20261019T193128Z`](records/20261019T193128Z.md), sets up the LayerFS
> arm through the public JS SDK on `main` and is VALID. The fourth,
> [`20261019T194736Z`](records/20261019T194736Z.md), runs every LayerFS
> command through `sandbox.exec` (`run.sh` sdk mode) and is INCOMPLETE: two
> Computer rows saturated at awk's 32-bit `%d` limit under heavy load. The
> fifth, [`20261019T195401Z`](records/20261019T195401Z.md), repeats it on
> an image with gawk and is VALID; it is the LayerFS arm of record.

The goal is one paired run of the frozen twelve-scenario Cloudflare Computer
`fs-bench.sh` workload, run against two arms:

- `computer-upstream`: a `computerd` FUSE mount;
- `layerfs-core`: a Workspace mounted by the current core daemon.

Both arms go through the [collector](run.sh), and then
[`compare.py`](compare.py) validates the pair and writes the report.

## Arms

| Arm | Source | Mount |
| --- | --- | --- |
| `computer-upstream` | Computer commit `de87919a4fd37242e960e13b7b3ba802d1eef0a0` (tree `4fb409d7e135…`), present in the local clone `~/Ephemeral-AI-Lab/study/cloudflare-computer`; `computerd` source CLI under native arm64 Node, built by [computer/Dockerfile](computer/Dockerfile) | `MOUNT_POINT=/workspace` inside a privileged arm64 container |
| `layerfs-core` | This repository at the run's commit; a Linux daemon built locked with Cargo 1.85.1 | `/workspaces/<namespace>` inside the Sandbox container the SDK creates, as in [`sandbox_kernel_mount`](../../core/crates/layerfs-api/examples/sandbox_kernel_mount.rs) |

Both arms use docker mode:
`run.sh <arm> docker <container> <mount> <pair>`.
In docker mode, the collector:

- checks that the path is the exact FUSE mountpoint in the container's
  `/proc/self/mountinfo`;
- copies the frozen script in and runs it;
- keeps container and image inspection files.

Provenance is `unverified` unless the image carries matching
commit and tree labels. The Computer Dockerfile sets them. The LayerFS
Sandbox image doesn't, so that arm stays `unverified`.

## Environment: native linux/arm64 in Docker, as on 2026-08-27

Both arms ran on this Mac on 2026-08-27, natively on linux/arm64 with no
emulation, and in one shared image. That run used the retired v0.1.x
`layerfs-mount` binary for the LayerFS arm. Its receipts are under
`~/.codex/visualizations/2026/08/27/01a04288-ebdc-7073-8bd5-a0cf92610334/cloudflare-computer-local-64c462b/same-image-8c5100/`:

- `cloudflare-fs-bench.*`
- `layerfs-fs-bench.*`
- daemon logs and `findmnt` output for each arm.

Those receipts used `REPS=3 WARMUP=1 RANDOMIZE_TARGETS=1` with a `/tmp`
baseline. They don't meet the rules here, so treat them as history, not as
an arm of this pair.

- **Host:** this Mac's Docker Desktop VM, linux/aarch64, 8 CPUs, 8 GB (the
  repository limit). Record `docker version`, `docker info` and `uname -a`
  with the pair.
- **Computer image:** [computer/Dockerfile](computer/Dockerfile),
  recovered from the build on 2026-08-25:
  - `node:22-bookworm-slim` on arm64, with `computerd` run from its source
    CLI under native Node;
  - `fuse-native` rebuilt against the system `libfuse.so.2`. This is the
    arm64 repair upstream documents in its own `AGENTS.md`;
  - `FUSE_MOUNT=fuse`, so `computerd` can't fall back to its in-process
    shim;
  - the image labels carry the pinned commit and tree, so the collector
    can mark that arm's provenance `verified`.

  The original images (`layerfs-lane-a-cloudflare-computerd-native:attempt-1`,
  then `…-fs-bench:attempt-2` = `sha256:8c5100fabfd8…`) are deleted.
  Rebuild from a clean `git archive` of `de87919a4`; the Dockerfile header
  has the command. The `npm ci` step needs network.
- **Container flags** (the 2026-08-27 run):
  `--platform linux/arm64 --privileged --device /dev/fuse --cap-add SYS_ADMIN --cap-add MKNOD --security-opt apparmor=unconfined --security-opt seccomp=unconfined`.
  Start `computerd` in the background with `MOUNT_POINT=/workspace` (the
  old run used `/tmp/workspace`). Poll `curl http://127.0.0.1:45678/health`,
  then record `findmnt -J -T <mount>`.
- **LayerFS arm in the same image.** The Sandbox takes an image by digest.
  Use the Computer measurement image for the LayerFS Sandbox too, so both
  arms get the same:
  - kernel and userland: Bash 5, GNU coreutils, `shuf`, `awk`;
  - Git version.

  Check first that the image satisfies the Sandbox's requirements. If it
  doesn't, use one image for both arms with `computerd` added. Don't use two
  different images.
- **Qualifying pairs:** a native x86-64 Linux host stays an option for later
  qualifying pairs. It isn't needed for the first one.

## Measurement settings

- `REPS=1 WARMUP=0 RANDOMIZE_TARGETS=0`, the collector defaults: one
  sample per arm, no warmup, no best-of. One pair, no reruns.
- Cache state is declared per row, for both arms:
  - **Self-contained:** `create 1000 files`, `stat 1000 files`,
    `rm 1000 files`, `mkdir tree`, `find tree`, `write 64 MiB`,
    `copy 64 MiB`, `read 64 MiB`, `git init + commit 100 files`. These rows
    write their own input inside the timer, so the write is paid in the same
    sample.
  - **Timed after an untimed prep step that writes the 64 MiB input:**
    `pure read 64 MiB`, `pure copy 64 MiB`, `overwrite 64 MiB`.

  The second group is own-write warm from an earlier phase. Report those
  three rows as warm-state comparisons, never as cold claims.
- The 64 MiB inputs are zero-filled. They exercise sparse-zero and page-cache
  behaviour, not high-entropy throughput.
- **LayerFS:**
  - Disposable/WAL/synchronous=OFF Store, `LAYERFS_CONSTRUCTION_WORKERS=1`.
  - Kernel writeback stays off, under the current FUSE contract.
  - Init, Sandbox create, mount, Commit and unmount are setup, outside the
    timer. That matches the workload's own exclusions.
- **Computer:** built-in default FUSE profile (auto_cache, 1 s metadata
  timeouts), no `COMPUTERD_FUSE_*` overrides. The two arms' kernel profiles
  differ by design; the report must say so.
- **Budgets:**
  - Each arm's complete collector command targets ≤15 s, with a declared
    exception up to 25 s.
  - No command may run longer than 2 minutes.
  - Record the 1-minute load average with each arm; don't wait for load
    to drop.
- Check free disk before building, with `python3 tools/cleanup.py check`.

## Steps

1. **Computer arm image and container.**
   - Export `de87919a4` with `git archive` to a fresh context directory.
     Don't build from the working clone, which is at `64c462b`.
   - Build [computer/Dockerfile](computer/Dockerfile) for linux/arm64.
     Record the image digest and the `fuse.node` SHA-256 that the build
     prints.
   - Start the container with the flags above. Start `computerd`, wait for
     `/health`, and keep the container running for the collector.
2. **LayerFS arm holder.** Done: [holder/holder.mjs](holder/holder.mjs),
   a harness script outside production LOC that sets up the arm through the
   public JavaScript SDK, following the `layerfs-js-sdk` skill:
   - `project.init` of a one-file folder, `sandbox.create` on the step-1
     image, `branch.fork("bench", "main")`, then `sandbox.mount` of `bench`;
   - print `CONTAINER <id>` and `MOUNT /workspaces/<namespace>`, plus a probe
     of the runner's tools as uid 501, then `HOLDING`;
   - at stdin EOF, `sandbox.unmount` (discard) and `sandbox.close`; a
     refusal stops it with its error, with no retry.

   SDK Store calls run in-process on Linux only, so
   [run-holder.sh](holder/run-holder.sh) runs the holder in
   `layerfs-352-runtime:node24` with the bindings of the SDK's verify
   harness:
   `run-holder.sh <image-digest> <fresh-volume> <linux-daemon> <linux-addon> fsbench <container-prefix>`,
   with stdin held open, for example from a FIFO. Build the Linux daemon and
   addon from the same checkout in the pinned toolchain image
   `sha256:378b799ef433…`:
   - `cargo build --offline --locked --release -j 6 -p layerfs-node --lib -p layerfs-daemon --bins`;
   - `CARGO_TARGET_DIR=/work/core/target/cluster2-linux`; copy
     `liblayerfs_node.so` to `layerfs.node`;
   - the repository bound read-only at `/work`, and the host Cargo registry
     bound read-only.

   The earlier pairs used a Rust holder outside the SDK, with
   `cache_bytes` 64 KiB and `namespaces` 8 instead of the SDK's 64 MiB and
   16.
3. **Self-check.** Run `benchmark/fs-bench/run.sh --self-check`. It passed
   on this Mac on 2026-10-20 without the native smoke test, because macOS
   Bash is 3.2.
4. **Collect.** Use one `pair=$(date -u +%Y%m%dT%H%M%SZ)` for both arms,
   then run, each as its own command:
   - `benchmark/fs-bench/run.sh computer-upstream docker <computer-container> /workspace "$pair"`
   - `benchmark/fs-bench/run.sh layerfs-core docker <sandbox-container> /workspaces/<namespace> "$pair"`
5. **Compare.** `python3 benchmark/fs-bench/compare.py "$pair"` writes
   `comparison.json` and `comparison.md` under
   `benchmark-results/fs-bench/<pair>/`, and refuses to overwrite them.
6. **Tear down.** Close the holder (unmount, then Sandbox close) and stop
   the Computer container. Remove the named volume only after the receipts
   are copied. Keep a failed arm's container and volume for diagnosis.

## Reporting

- Write the campaign record from
  [benchmark_agent_report.md](../../docs/general/benchmark_agent_report.md). Include:
  - exact commands, pins, image digests and binary hashes;
  - the per-row cache-state labels;
  - the platform option used;
  - every outcome, including failed or unrun arms.
- Keep raw receipts in `benchmark-results/fs-bench/<pair>/`.
- When a release publishes a qualifying pair, copy its two arm results and
  the comparison into `benchmark/data/fs-bench/v<version>/`, following
  [fs-bench-pro's data folder](../data/fs-bench-pro/README.md).
- The website can then add an `fs-bench` suite card.

## Readiness checks, 2026-10-20 (no pair collected)

| Check | Result |
| --- | --- |
| Computer image | Built from a `git archive` of `de87919a4`: `layerfs-fs-bench-computer:de87919a4` = `sha256:9c145fbc292a260800639355dbadd81c793290af65afab1b2bb867e4a50c4766`, arm64, 596 MB, labels match the pin. `libfuse.so` replaced, x86-64 → aarch64 (`55df6b91…` → `03eaf187…`); `fuse.node` aarch64 `1136562d…`. |
| Computer smoke test | Health answered within about 0.5 s. `findmnt` shows `/workspace` with fstype `fuse` and options `user_id=0,group_id=0,max_read=524288`. `/__computerd/info` reports backend `fuse`. A write and read worked. The container was removed. |
| Linux daemon | Built in the pinned image in 35 s. aarch64 PIE, `layerfs-daemon` sha256 `9e269490679794cfb6c17dec616913d510083387cc49591adb953272d7e574a7`. |
| Holder on the Computer image | The Sandbox started on `sha256:9c145fbc…` and mounted `/workspaces/1`. As uid 501, the probe found Bash 5.2, `date +%s%N`, `shuf`, `awk`, `git` 2.39.5, `seq`, `dd`, `cp`, `cat` and `find`, and a write worked. The holder then unmounted, closed and deleted its container, and the borrowed volume was removed. |
| Collector view of the LayerFS mount | `mountinfo` shows `/workspaces/1` with fstype `fuse` and `default_permissions,allow_other,max_read=131072`. Through `docker exec`, `root` could mkdir, write, read and remove. So could uid 501. The Sandbox container is unprivileged, with only `CAP_SYS_ADMIN` added. |

Both arms can therefore use one image. One difference: the Computer
container runs privileged, while the Sandbox container keeps the SDK's own
narrower settings. Report this with the pair.

## Known risks

- **User:** `run.sh` runs the script through `docker exec` as root, in both
  arms. Root's access to the LayerFS mount is confirmed. Running as 501 would
  match agent use, but `run.sh` has no user option yet.
- **FUSE profiles differ:** Computer runs auto_cache with 1 s metadata
  timeouts; LayerFS keeps kernel writeback off. Report both profiles with
  the pair.
