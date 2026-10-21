# Shared SDK-route harness

> **Status:** Current general guide.

The suites of [#365](https://github.com/Ephemeral-AI-Lab/layerfs/issues/365)
(pjdfstest, fsx, fsstress, smallfile, mdtest, fio) share these files. Each
suite drives LayerFS only through the public JS SDK: `project.init`,
`sandbox.create`, the run's own Branch from `branch.fork`, `sandbox.mount`,
`sandbox.exec`, `sandbox.commit`, `sandbox.unmount` and `sandbox.close`.
Every tool invocation is a `sandbox.exec` in the suite's Sandbox image.

| File | What it does |
| --- | --- |
| `client.sh RUN SUITE SCRIPT [ARG...]` | Runs `benchmark/SUITE/client/SCRIPT` in the SDK runtime image with the run's deployment (`RUN/deploy.env`) |
| `session.mjs` | SDK client (Store policy 16/8/8), ledger helpers, `timed`, `exec` (never throws on a non-zero exit), `setup` (Init, create, fork, mount; path kept in `session.json` for later clients), `commit`, `teardown` |
| `lib.sh` | Shell steps for a suite's `run.sh`: `bench_client` (115 s limit, `commands.log` with 1-minute load), `bench_timeout`, `bench_field`, `bench_next`, `bench_image`, `bench_setup`, `bench_lock` / `bench_unlock`, `bench_cleanup`; its globals start with `bench_` |
| `watchdog.pl SECS COMMAND [ARG...]` | The wall-clock limit behind `bench_timeout` (see [Time limits](#time-limits)) |

A suite's `run.sh` sets `suite=<folder name>` and sources `lib.sh`. Its
clients import `../../common/session.mjs`. The mounted Workspace survives
between client processes; each client reads its path from `session.json`.

Two arms run in the same Sandbox through `sandbox.exec`: `layerfs`, in the
mounted Workspace, and `sandbox-disk`, in the container's own `/tmp`
(overlayfs), as the reference. `sandbox.exec` runs `bash -c` as uid 501 with
`HOME=/tmp`, no stdin, and keeps at most 1 MiB per stream.

Measured runs hold the host measurement lock
(`benchmark-results/.measure.lock`) from setup to teardown, so only one suite
measures at a time. `bench_lock` exits 75 while another run holds it.
Builds and smoke runs take no lock.

Images: each suite builds its own Sandbox image `FROM fs-bench-computer:gawk-20261020`
(checked against `sha256:66aeb6bb…`, Debian bookworm with gcc, make, git,
perl, prove and python3), with tools from pinned upstream commits, and
records the resulting digest.

## Time limits

Every client, build and docker call runs under `bench_timeout SECS`
(`watchdog.pl`): TERM to the command and every process below it at SECS,
KILL 3 s later, exit 124. The earlier `perl -e 'alarm 115; exec ...'` never
fired on docker: the docker CLI is a Go program and ignores SIGALRM
(`alarm 2` around `docker run ... sleep 5` returned 0 after 5 s). Two gaps
remain on the host side, so they are closed separately:

- After a client times out, `bench_client` removes its container
  (`<prefix><script>`); the CLI's death alone does not stop it.
- Killing a `docker exec` CLI leaves its process running in the container,
  so `passthrough.sh` also runs each exec under GNU `timeout` in the sibling
  (`bench_pt_exec`: TERM at 113 s, KILL 1 s later).

A measured run takes the lock before its setup client; `bench_lock` accepts
a RUN folder that does not exist yet, and `bench_setup` records the lock.

## FUSE baseline arm (`passthrough.sh`)

smallfile, mdtest and fio also run a third arm, `passthrough-fuse`: libfuse's
`passthrough_ll` (libfuse `fuse-3.14.0`, matching Debian bookworm's libfuse3)
over a plain directory, the like-for-like FUSE reference. A Sandbox cannot
host a second FUSE mount (no-new-privileges, no user namespaces, commands
without capabilities), so the arm runs in a sibling container from the
suite's own image plus `passthrough_ll` (`passthrough/Dockerfile`), on the
same Docker VM and kernel, with `/dev/fuse` and `CAP_SYS_ADMIN`. Root mounts
it with its defaults (multi-threaded, cache timeout 1.0 s, writeback off,
as LayerFS); the measured command runs as uid 501, gid 20, `HOME=/tmp`
through `docker exec`. It is not LayerFS and does not use the SDK.
