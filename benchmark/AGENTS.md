# AGENTS.md — benchmarks

> **Status:** Current general guide, 2026-10-20. Root [AGENTS.md](../AGENTS.md)
> §1–3 and the [measurement workflow](../docs/general/agent-measurement-policy.md)
> govern; this file names the environment and the SDK route for suites in
> `benchmark/`.

Read before any measurement:

- root AGENTS.md §1–3;
- [benchmark rules](../docs/general/benchmark_rules.md);
- the [report template](../docs/general/benchmark_agent_report.md);
- the suite's own README.

Read the [`layerfs-js-sdk` skill](../.agents/skills/layerfs-js-sdk/SKILL.md)
before writing any LayerFS client code.

## What lives here

| Path | State | Notes |
| --- | --- | --- |
| [fs-bench/](fs-bench/README.md) | **Current** | Cloudflare Computer's frozen twelve-scenario `fs-bench.sh`, run against pinned Computer and against LayerFS core as one pair. `run.sh` collects one arm; `compare.py` validates the pair. |
| [fs-bench-pro/](fs-bench-pro/AGENTS.md) | **Frozen and broken** (owner, 2026-10-18) | Do not edit, build, run or repair it. Its #352 F-020 breaks stay. |
| `deepseek-sdk-experiment/` | **Broken at HEAD** | It calls Rust SDK operations that #352 F-020 removed. Acknowledged; not repaired. |
| [data/](data/) | Release data | One folder per suite and version (`data/<suite>/v<version>/`), copied unchanged from receipts or release notes and never recomputed. The website mirrors it. |

## Environment

- **Host.** Docker Desktop on this arm64 Mac (a linux/arm64 VM, kernel
  6.12.x-linuxkit).
  - Docker is limited to 8 GB and 8 CPUs.
  - Build with `-j 6`, one heavy batch at a time.
  - Record the Docker version, OS and kernel, CPUs and memory with each pair.
  - A native x86-64 Linux host is the later route to a qualifying pair; this
    host's results say so.
- **Linux builds.** Build the daemon and the SDK addon from the same checkout in
  the pinned toolchain image
  `sha256:378b799ef43343fc64008b6a5ef456dd6bf0cb8f6ea4cec72e7b42dfc17d2cd6`
  (Rust 1.85.1, arm64):
  - the repository bound read-only at `/work`;
  - `CARGO_TARGET_DIR=/work/core/target/cluster2-linux`;
  - the host `~/.cargo/registry` bound read-only;
  - `cargo build --offline --locked --release -j 6 -p layerfs-node --lib -p layerfs-daemon --bins`.

  Copy `liblayerfs_node.so` to `layerfs.node`, stage both binaries outside the
  target, and record their SHA-256. A cloned target can carry stale artifacts:
  touch the sources or check them before trusting a partial rebuild.
- **Images, always by digest.**
  - fs-bench measurement and Sandbox image: `sha256:66aeb6bbf7fc…`, built from
    [fs-bench/computer/Dockerfile](fs-bench/computer/Dockerfile) plus
    `gawk.Dockerfile` (on branch `fs-bench-sdk-main`, like the SDK scripts
    below). Both arms use this image. With gawk, a statistic of
    2.147 s or more is no longer capped by mawk's `%d`.
  - SDK client runtime: `layerfs-352-runtime:node24` =
    `sha256:d3773b4eac6a7a644887b17e36956cd1553786d47103f0170a3bb2b0ff6988de`
    (Node 24).
- **Store.** Disposable/WAL/OFF only (root AGENTS.md). Each LayerFS arm gets:
  - a fresh named volume for the Store, mounted at `/layerfs-store`;
  - a second fresh named volume for the SDK home.

  Remove both after the receipts are copied. Export
  `LAYERFS_CONSTRUCTION_WORKERS=1`.
- **Load and neighbours.** Record the 1-minute load at each arm. Don't wait
  for it to drop and don't rerun because of it. List other owners' running
  containers as declared interference, and never touch them.
- **Bounds.**
  - No command runs longer than 2 minutes: collectors run under a 115 s alarm,
    and long holders run in the background.
  - A complete collector command is ≤ 15 s by default; record a miss, don't
    hide it.
  - Check free space with `python3 tools/cleanup.py check` before builds and
    image work.

## LayerFS through the SDK and the Sandbox

A LayerFS arm measures LayerFS as an agent uses it. Every step is a call to the
public JavaScript SDK (`@layerfs/sdk`, source `sdk/js/src` at the measured
commit, with the Linux addon from the same build). Every command inside the
Sandbox goes through `sandbox.exec`.

**Where the client runs.** SDK Store calls open the Store in-process and work
on Linux only (#352 F-020). On this Mac, run every client in the runtime image
with:

- the Docker socket;
- the Store volume at `/layerfs-store`;
- `LAYERFS_HOME` on the shared SDK-home volume;
- `LAYERFS_DOCKER`, `LAYERFS_IMAGE`, `LAYERFS_VOLUME`, `LAYERFS_DAEMON`,
  `LAYERFS_NATIVE`, `LAYERFS_CONTAINER_PREFIX`;
- `LAYERFS_STORE_PATH=/layerfs-store/global/store.sqlite`;
- `LAYERFS_DAEMON_HOST=host.docker.internal`;
- `LAYERFS_CONSTRUCTION_WORKERS=1`.

This is the same setup as `sdk/js/test/verify/container.mjs`. A host folder
can't be `LAYERFS_HOME`: the SDK requires a private home owned by the client
user, and creates one on first use.

**Call order.**

```text
new LayerFS(project)
project.init(sourceDir)                    once per fresh volume
sandbox.create(name, project, image)       installs the Store into the volume: before any Store call
branch.fork(ownBranch, "main")             work on your own Branch; never mount main
sandbox.mount(id, ownBranch)               returns the Workspace path, e.g. /workspaces/1
sandbox.exec(id, path, command)            every command in the Sandbox, timed work included
sandbox.commit(id, path, message)          only when the case measures Commit
sandbox.unmount(id, path, discard)
sandbox.close(id)
layerfs.close()
```

**How `sandbox.exec` behaves.**

- It runs `bash -c <command>` as the Sandbox identity (uid 501, gid 20) in the
  Workspace directory, with only `HOME=/tmp` set. Put any environment the
  command needs inside the command.
- It keeps 1 MiB of each stream. Check `truncated` before trusting output.
- A non-zero `exitCode` is a result, not a refusal.
- A refusal throws `LayerFSError`: read it and stop. No retry.
- Files the Sandbox writes are owned by 501:20. Run tools such as git as that
  user, never as root ("dubious ownership").

**Several processes, one Sandbox.** A later process reaches the same Sandbox
through the shared `LAYERFS_HOME`, one process at a time. The SDK names the
container `<LAYERFS_CONTAINER_PREFIX><id>`; find it by that name, not from the
home's records.

**Do not:**

- use `layerfs_api::internal` or a Rust holder;
- pass daemon settings the SDK doesn't use;
- start a service Sandbox;
- `docker exec` into the Sandbox for any measured or setup command (Docker
  only reads metadata: `docker inspect`, `docker logs`);
- use `fs.*` calls in place of work the case does on the mounted filesystem;
- count client startup, setup, mount, Commit or unmount inside a timer the
  case doesn't declare.

**fs-bench scripts.**

- [fs-bench/holder/](fs-bench/holder/) is a set of four scripts:
  - `run-holder.sh` writes `deploy.env` and creates the SDK-home volume;
  - `client.sh` runs any client in the runtime image;
  - `holder.mjs` does setup and teardown, and holds the mount until stdin
    closes;
  - `exec.mjs` makes one `sandbox.exec` call.
- `run.sh layerfs-core sdk SDK_HOME SANDBOX MOUNT PAIR` makes three
  `sandbox.exec` calls: identity and mount check, stage+hash+run, then
  collect+cleanup.
- **As of 2026-10-20, these files and `run.sh` sdk mode are on worktree branch
  `fs-bench-sdk-main`, uncommitted.** This checkout's `fs-bench/holder/`
  still holds the retired Rust holder; don't use it.

## Collecting and reporting

- One sample per arm, in a fixed order. A change to the collector, image or
  binaries means a new pair ID, not a retry.
- Keep every pair's record, including INCOMPLETE and failed ones.
- `compare.py` refuses saturated statistics and any row that isn't `OK`. A
  written `VALID` from an older verifier is not upgraded or rewritten.
- Raw receipts go to `benchmark-results/<suite>/<pair>/`, which Git ignores.
  The campaign record goes in the suite's `records/`. A release result goes in
  `data/<suite>/v<version>/` with its CSVs, the unchanged receipts and the
  record.
- Every commit states its production LOC comparison (root AGENTS.md §4). Data
  and harness changes report delta 0.
