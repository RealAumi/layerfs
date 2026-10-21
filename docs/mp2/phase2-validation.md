# Remote Store prototype validation

> Status: Dated planning checkpoint; not release evidence or a product contract.

2026-10-20, `mp2/remote-store`, upstream `3a80ec6d9`. Linux arm64 on
remote-host/OrbStack, Docker 29.4.0, Rust 1.85.1; all Store creation explicitly
Disposable. No Linux compilation ran on the local Mac. No upstream push.

## Commands and outcomes

All Cargo commands below ran in the owned Linux build containers, cwd `/work`,
with `CARGO_HOME=/work/.cargo-home`, `CARGO_TARGET_DIR=/work/target-remote`,
`LAYERFS_CONSTRUCTION_WORKERS=1` for execution. Dependencies are locked;
rsproxy supplied the existing lockfile after crates.io connectivity failed.
The selected packages exclude frozen fs-bench-pro. Every test invocation had
an explicit 120-second wall limit; compilation preceded execution.

For compactness, **T** below expands exactly to:
`timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2`.
These are all Cargo test commands run, including failed attempts:

| Command after T | Invocations/results |
| --- | --- |
| `-p layerfs-daemon --test remote_refresh_gate --no-run` | Twice; both PASS. |
| `-p layerfs-daemon --test remote_refresh_gate -- --nocapture` | Three times: fixture FAIL (`main` ReadOnly); corrected PASS 1; after publisher extraction PASS 1. |
| `-p layerfs-daemon --test remote_refresh_gate --test lane_merge --no-run` | Once, PASS. |
| `-p layerfs-daemon --test lane_merge -- --nocapture` | Once, PASS 4. |
| `-p layerfs-remote-store --test remote_driver --no-run` | Once, PASS. The driver is explicitly ignored until run inside A. |
| `-p layerfs-remote-store --test transport --test remote_driver --no-run` | Twice, PASS (initial transport and final build). |
| `-p layerfs-remote-store --test transport --no-run` | Once, PASS after bounding test-peer accept. |
| `-p layerfs-remote-store --test transport -- --nocapture` | Three times, PASS 2 each: initial, bounded test accept, final style corrections. |

The two transport tests exercise actual Noise fragmentation/offset rejection and
wrong canonical identity rejection without caching or automatic replay. Test
peer accept/read/write waits are bounded to three seconds.

External E2E fixture calls use exactly
`timeout 120 /opt/lfs/remote_driver --ignored --exact drive --nocapture`, with
`LFS_MODE=init/write/read/oracle/history/head` and the recorded `LFS_PATH`,
`LFS_TEXT`, `LFS_EXPECT`. These invoke `layerfs_api::call`'s public SDK method
table in A, opening the Store directly; the JavaScript wrapper itself was not
executed. Controller calls use
`timeout 110 /opt/lfs/layerfs-remote /state/daemon.setup <operation> <arguments>`.
Local `.log` copies trim trailing whitespace only; original logs on remote-host
remain unchanged. The exact argv, environment arguments, exit status, stdout and elapsed wall time
of **every completed container command** are retained in the five JSONL receipts
below; their console logs also retain the command interrupted by timeout.

| Run | Invocation on remote-host | Result and retained evidence |
| --- | --- | --- |
| 01 | `python3 run-remote-e2e.py` | Mount/ls diagnostic completed; oracle copy hit its 30-second limit. The fault proxy lacked TCP_NODELAY, adding ~40 ms/request. [Commands](receipts/run01/e2e-receipts.jsonl), [failure](receipts/run01/e2e-console.log). |
| 02 | Same, after proxy fix | 3003-file oracle, refresh, root and failing-command Commit PASS. Normal unmount FAIL at Join after 5 seconds. [Commands](receipts/run02/e2e-receipts.jsonl), [failure](receipts/run02/e2e-console.log). |
| 03 | Same, main-process daemon launch | Refresh/root/command checks PASS; same unmount FAIL after 5 seconds, with only 39 completed requests. Main-process launch did not fix it. [Commands](receipts/run03/e2e-receipts.jsonl). |
| 04 | Same, resume independent mount/races | Fresh mount, disjoint-line race, overlapping-line conflict and resolution PASS. Descriptor probe then failed with a harness Python quoting error. [Commands](receipts/run04/e2e-receipts.jsonl), [failure](receipts/run04/e2e-console.log). |
| 05 | Same, corrected probe; faults only | Isolation, read EIO, upload Unknown, unchanged head and no replay/reconnect PASS. [Commands](receipts/run05/e2e-receipts.jsonl), [read cut](receipts/run05/mp2-lfs-b1-cut-events.jsonl), [upload cut](receipts/run05/mp2-lfs-b2-cut-events.jsonl). |

Successful earlier phases were reused when resuming independent checks. No
failed Commit or unmount was replayed. The second post-cut Commit is an
admission-refusal check: its counter stays 17, with original custody retained.
There is no claimed all-green lifecycle run. The checked-in harness consolidates
these phases into explicit `diagnostic`, `refresh`, `races`, `faults` selectors;
that selector-only consolidation was syntax checked, not rerun as another sample.

Other checks:

- `python3 -B core/tools/check_fuser_integrity.py`: PASS, retained in build logs.
- `python3 -B core/tools/check_product_boundary.py`: FAIL, exactly the same 57
  violations as `3a80ec6d9` after normalizing line numbers. [Baseline](receipts/baseline-boundary.log),
  [final](receipts/final-boundary.log). No new violations; no guard weakening.
- `python3 -B -m unittest discover -s core/tools -p 'test_check_product_boundary.py'`:
  PASS 25, under `subprocess.run(..., timeout=120)`.
- `python3 -B -m unittest discover -s core/tools -p 'test_*.py'`:
  PASS 50 under the same explicit timeout; [output](receipts/tools-tests.log).
- `cargo clippy --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store -p layerfs-daemon -p layerfs-store-service -p layerfs-bridge --all-targets -- -D warnings`:
  first unavailable component; then FAIL 3 new style warnings; after corrections
  PASS. Components installed only in the owned container. [Output](receipts/build/clippy-03.log).
- `cargo fmt --manifest-path core/Cargo.toml -p layerfs-bridge -p layerfs-store-service -p layerfs-remote-store -p layerfs-daemon -- --check`:
  FAIL; changed-file formatting repaired, remaining differences are unchanged
  `f046_fork_reference.rs`, `tests/support/mounted.rs`, `bootstrap.rs`.
  [Output](receipts/package-fmt.log). Changed files separately PASS
  `rustfmt --edition 2021 --config skip_children=true --check <35 changed Rust files>`.
- `git diff --check`: PASS. Python harness syntax checked using `compile`, with
  no bytecode outside the repository. No tests deleted.

Build attempts, including failures, are retained in [build receipts](receipts/build/):
missing Git metadata, login-shell Cargo PATH, network acquisition (interrupted),
then compiler errors from seam/transport assembly, corrected in subsequent
attempts. The final build command was:

```sh
cargo build --manifest-path core/Cargo.toml --locked -j 2 --profile test -p layerfs-daemon --bin layerfs-remote-daemon -p layerfs-remote-store --bins --test transport --test remote_driver
```

It passed, followed by the final no-run and two-test transport PASS above.
E2E binary hashes/image identity are in [tested identities](receipts/tested-identities.txt).
E2E preceded formatting and equivalent Clippy initializer/hex-format corrections;
final compilation/transport checks cover those changes, with earlier unaffected
E2E evidence retained. Earlier native refresh/merge proofs cover the shared
publisher; this is not a claim that all repository tests passed.

## Running the prototype

Use the built `layerfs-store --config <private-file>` on A and
`layerfs-remote-daemon --config <private-file>` on B. Both configs are private,
current-user-owned files, maximum 8192 bytes, one `key=value` per line. A needs
`listen`, `store`, `binding` (existing Store binding bytes in hex), `cursor`,
`overlay`, `private_key`, `token`. B needs `server` (numeric TCP address),
`server_key` (pinned server public key), `token`, `private_key` (daemon key),
`listen`, `control`, `uid`, `gid`, `cache`, `overlay`, `mounts`.
Keys/tokens are 32-byte hex values. Shared `token` is the client's Noise private
key; the server derives the admitted public key. Per-Workspace authorization is
still TODO. Both daemon control and Store transport use Noise KK.

B's cache/overlay/config parents are daemon-owned mode 0700; command UID/GID
must be nonzero, with UID distinct from the daemon. `/dev/fuse` must be a
character device owned by the daemon (startup narrows it to 0600); the mount
home is absolute, daemon-owned mode 0755. Linux mount capability and `allow_other`
are required. Set `LAYERFS_CONSTRUCTION_WORKERS=1`. B has no Store setting or
path. This prototype uses one read/reservation connection and one upload/Commit
connection, with five-second connect and ten-second request I/O deadlines;
failed channels were quarantined, never reconnected automatically
([Phase 9](remote-store.md#phase-9-reopening-lost-connections) reopens them).

Explicit control operations:

```sh
layerfs-remote /state/daemon.setup mount <branch-id-hex>
layerfs-remote /state/daemon.setup commit <workspace-id-hex> <namespace>
layerfs-remote /state/daemon.setup stats
layerfs-remote /state/daemon.setup unmount <workspace-id-hex> <namespace>
```

The controller prints the mount path/token. Commands are launched by an external
executor. The `unmount` command is implemented through the existing path, but
normal teardown failed in this container environment as recorded above.

For reproduction, rsync source into `~/lfs-remote/mp2-remote-store/source/` on
remote-host, build there with the ECR image and existing `.cargo` ARM64 settings,
write the selected compiled helper basename into `driver-path`, then run the
checked-in [harness](run-remote-e2e.py) from that remote directory with a phase
argument. It creates only named `mp2-lfs-*` containers/networks/volumes, copies
binaries rather than source into B, and removes its resources in `finally`.
Move existing receipts and oracle directories to a fresh retained run directory
before another explicitly selected run. Do not rerun diagnostics for a better
sample. Setup configs contain secrets; do not publish `seed/`.

All owned test/build containers and volumes were removed; each E2E receipt
records its own network cleanup, with remaining setup cleanup in
[cleanup](receipts/cleanup.log). Other containers and images were untouched.
