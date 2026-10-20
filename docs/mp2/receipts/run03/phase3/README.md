# Phase 3 raw evidence and limits

> Status: Dated planning checkpoint; not release evidence or a product contract.

Product source: `c834e1c`, based on `cd2abaeab` (accepted Phase 2). ARM64 Linux
7.0.14-orbstack-00380-ga7e0a2dc9535, Docker 29.4.0, Rust 1.85.1 test profile
(opt-level=1, debug assertions retained), explicit Disposable, one construction
worker. No Linux build ran locally. Store/cache/overlays used Linux named volumes;
only binaries, source/input setup and receipts crossed the Mac bind mounts.

## Teardown: passes, not an established fix

The two pending receivers in Phase 2 are the `fuser-0` / `fuser-1` threads.
`core/crates/layerfs-daemon/src/control/detach.rs::unmount_kernel` calls
`KernelSession::detach` then `drain`. In
`core/crates/layerfs-fuse/src/session/drain.rs::quiesce`, the Join wait observes
`SessionPhase::Joined`. The receiver code in
`core/vendor/fuser-0.18.0/src/session/lifecycle.rs` runs the event loop; the
underlying read in `src/channel.rs::receive` is a `read(2)` on `/dev/fuse`.
The event loop exits on EOF/ENODEV. The mount owner joins those receivers and
notifies the monitor; the fence watcher also returns before custody releases.

The remote Store client has two synchronous TCP channels and **no receive
threads** of its own. Their lifetime is the daemon/backend, shared across mounted
Workspaces; normal unmount does not close them. Thus the recorded pair of pending
receivers is not the pair of Noise connections. The Phase-2 snapshot establishes
that the FUSE loops had not exited, but it contains no stuck-thread syscall stack
or mount-reference evidence explaining why. Do not infer that cause from counts.

Two fresh reproductions, including the full Phase-2 server-refresh/root/failing-
command sequence, unmounted successfully on the committed Phase-2 source. An
unchanged-source ten-cycle proof also passed (`cycles-before`). With only upload
counters added, `cycles/results.jsonl` proves another ten consecutive
mount/edit/Commit/unmount cycles. Every reply is Unmounted; controller unmount
wall is 0.712–0.872 ms, median 0.768 ms. After each cycle, the daemon has exactly
one idle accept thread, the same FD list and the same three unique sockets
(two persistent Store connections, one control listener), with no FUSE FD or
per-mount threads. Then the daemon is stopped, its PID disappears, and `ss`
records no daemon-owned listener/established connection. Cleanup removes B.

**Unresolved:** no root cause or teardown repair was established. The historical
failing daemon hash `97d27662e002498307ab8dd3110dbaac6f4f27d7571c27bc298c9f5815250c40`
is recorded in Phase 2, but its executable was not retained; the current
committed-source executable used for reproduction had hash
`83f900dd0c466f95d2dd3145506ce5fb2b73b73003e03096194ed84532d97cad`.
Current-source passes cannot retrospectively explain an intermediate binary's
failure. There is no justified remote teardown patch to claim. No FUSE code,
5-second deadline, abort behavior or operation replay was changed. A recurrence
needs original binary custody, receiver stacks and mount-reference evidence.
Phase-3 executables are now retained by hash under the remote `phase3/artifacts/`
([manifest](binary-custody.json)) to avoid repeating this evidence gap.

## Workload and measured boundary

Existing read-only volumes `lfs-src` and `lfs-m2-dubbo` supplied Dubbo
`cb05763298f081ed17171d704408b6478cf8fd83` and its offline repository. Copies
under `~/lfs-remote/mp2-remote-store/phase3-work/` were used; originals untouched.
Commons-lang was available but unnecessary. No synthetic shape was needed.

Maven preparation command (inside cached ECR Maven 3.9.9 / Temurin 17):

```sh
timeout 120 mvn -o -Dmaven.repo.local=/work/m2/repository -s /work/m2/settings.xml -DskipTests -Dmaven.test.skip=true -Dcheckstyle.skip -Drat.skip=true -Dspotless.skip=true package
```

Full package PASS (~68 s); incremental package PASS (31.762 s). The first
attempt omitted `-Dspotless.skip=true` and failed on an uncached formatter
artifact; no Maven dependencies were downloaded. Logs are under `workload/`.
The full snapshot has 5,354 output files / 260,024,428 bytes / 115 target dirs.
One greeting literal in HelloServiceImpl changed; package rewrote 1,430 output
files / 23,377,148 bytes, with only three content changes: the class, JAR and
createdFiles.lst. The incremental input also includes that one source edit.
Manifests retain paths, sizes, timestamps and hashes.

Builds ran once as preparation. Identical real full/incremental output snapshots
were copied as ordinary FUSE writes into each independent sample. Maven itself
was not run inside each measured mount. The timing measures Commit after those
writes, not build execution or fixture transfer. `cp -a --no-preserve=ownership`
keeps modes/timestamps; every mounted inode has configured ownership 1000:1000.
A fresh writable Store clone and a new daemon/cache/overlay are used per sample.

Commit timer is the controller's `wall_ns`: before Noise control authentication
to returned Commit reply. Process launch, TCP connect, preparation and EndSession
are excluded; Docker-exec wall is separately in commands/results. Counter deltas
bracket Commit including its install. Uploaded bytes/objects are **acknowledged
canonical Upload payload**, excluding wire headers/encryption. Store requests
are Store-protocol calls, not SQL statements; native has no such transport (0).
Native uses the ordinary local daemon and its own Store on the same VM, not a
native-filesystem-without-LayerFS comparison. Save statistics are retained in
replies; they are not allocated SQLite/WAL file growth.

Caches: fresh B object cache and fresh kernel mount for the cold-status phase;
server/OS caches may be warm. Commit follows metadata preparation and FUSE writes,
so metadata, overlay and own-write payload are warm. No global cache drop, RSS
bound or benchmark eligibility claim is made. Whole-workspace/frozen harness,
Durable, cloud-sandbox/x86_64 and the excluded Phase-3 features were not run/built.

## Network calibration and all attempts

See immutable `plan.md`, `plan-v2.md`, `plan-v3.md`; owner explicitly requested
three samples per cell. Large raw receipts are losslessly gzip-compressed; `compressed.json` records
their uncompressed SHA-256 and size (`gzip -dc <file.gz>` reads them).
Every completed command has exact argv, exit status,
stdout and wall in its directory's `commands.jsonl`. Errors remain visible.

| Invocation: `python3 phase3-diagnostics.py <argument>` | Result |
| --- | --- |
| `seed` | PASS real-source Store/input setup. |
| `cycles` | PASS 10 cycles, stable daemon resources, explicit stop. |
| `measure` | Preparation FAIL: ownership-preserving copy refused; no Commit attempted. |
| `measure-02` | Three unshaped pairs PASS; nominal 2 ms verified at 5–13 ms and cold status hit 25 s. Not pooled into final cohort. |
| `calibrate` | One-sided netem alone has idle-VM timer overshoot. |
| `calibrate-hot` | CPU-0 busy loop yields accurate ping timing; not yet application validation. |
| `measure-v2` | CPU-affined daemon + busy loop caused unshaped cold status timeout, before any Commit. |
| `calibrate-separated` | Different-CPU sender still has RTT overshoot. |
| `calibrate-idle` | Accurate ping, but cold status timeout with the CPU-affined daemon. |
| `calibrate-proxy` | Normal daemon affinity + pinned proxy, but non-yielding loop still interfered; cold status timeout. |
| `calibrate-yield` | PASS: pinned proxy + nice=19 continuously yielding CPU-0 loop; accurate RTT and 2.483 s unshaped cold status. |
| `measure-v3` | PASS all 12 samples / 24 Commits and unmounts. This alone supplies the final medians. |

Final cohort uses the existing TCP proxy, TCP_NODELAY, proxy affinity CPU 0 and
one nice=19 `os.sched_yield()` loop on that CPU, with normal daemon affinity.
`tc qdisc ... dev eth0 root netem delay 2ms/20ms` is on B's egress to A; the full
one-sided delay is added RTT. The same loop/idle proxy are present for native.
This controlled CPU load is disclosed, not an idle-host performance claim.
The 20 ms arm warms metadata at no added delay, then applies/verifies 20 ms
before output copy/Commit. The 2 ms arm supplies the requested cold-status case.

Per-sample ping results verify the link. Across final samples, individual-probe
median RTT is 0.013 / 2.04 / 20.0 ms. The 2 ms condition spans 2.008–4.085 ms
(including initial probe outliers; median of the three five-probe means 2.442 ms).
The 20 ms condition spans 20.004–20.052 ms. Do not silently claim exact RTT for
every packet. No timed-out operation was replayed or had its deadline extended.
Measured operations retain their 25 s product / 27 s outer ceiling.

## Build/tests/checks and reproduction

All Rust commands run on remote-host in an owned Linux arm64 container, cwd `/work`,
with the existing repository `.cargo` settings, CARGO_HOME=/work/.cargo-home,
CARGO_TARGET_DIR=/work/target-remote. Builds locked; tests compiled first.

```sh
cargo build --manifest-path core/Cargo.toml --locked -j 2 --profile test -p layerfs-daemon -p layerfs-remote-store --bins --test remote_driver
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store --test remote_driver --no-run
cargo clippy --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store -p layerfs-daemon --all-targets -- -D warnings
cargo build --manifest-path core/Cargo.toml --locked -j 2 --profile test -p layerfs-remote-store --test transport
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store --test transport --no-run
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store --test transport -- --nocapture
```

All PASS (transport 2 tests). An initial build invocation repeated `--bins` and
was rejected by Cargo before building; preserved in setup/phase3-build.log.
The fixture execution is `timeout 120 /bin-lfs/driver --ignored --exact drive
--nocapture` with LFS_MODE=init and LFS_SOURCE=/original/dubbo: PASS.
`python3 -B -m unittest discover -s core/tools -p 'test_*.py'` under an explicit
120 s subprocess timeout: PASS 50. `check_product_boundary.py`: same 57 baseline
violations, no additions. Changed-file rustfmt check and Python syntax checks
PASS. `python3 docs/mp2/phase3-summary.py` recomputes the medians/ranges directly
from receipts and asserts the ten-cycle resource invariant. No tests deleted.

Use [phase3-diagnostics.py](../../../phase3-diagnostics.py) for the owned
container lifecycle and [phase3-summary.py](../../../phase3-summary.py) for
aggregation. Raw binary/image/harness identities are in setup/phase3-v3-identities.txt
and seed/results.jsonl. The final script additionally archives binaries by hash;
that receipt-only addition was syntax checked, with binaries archived separately
without repeating measurements. Inputs and copied Maven repo remain under the
allowed remote directory. All owned containers/networks/volumes and the owned
tools image were removed; see cleanup.log and per-run cleanup commands. Existing
containers/images/volumes were left unchanged.
