# Phase 4 diagnostic receipts

All Linux work ran on `ssh remote-host`, below
`~/lfs-remote/mp2-remote-store`, in owned arm64 OrbStack containers. The earlier
Phase-2 `run04` receipts are untouched; this nested directory is Phase 4.
Production base: `68f5dd3d6`; final diagnostic implementation: `06a781cfceb`.
`source-custody.json`, `server-measured.rs`, `seed/identity.jsonl` and
`binary-custody.json` pin sources, trace-format difference, executables and image.
Measured server source is the base plus the retained trace addition; final Rust
formatting only joined its condition onto one line. The daemon/client executables
are unchanged Phase 3. This is declared reuse, not a new daemon performance arm.

## Cases and interpretation

- `diagnose/`: fresh cache, traced unshaped mount/status, Git syscall trace,
  canonical IDs/roles and cache payload fingerprints. Timing is diagnostic only.
- `receipts/request-paths02.log.gz`: passing offline Content traversal on an
  independent byte copy of the sealed seed. `request-paths.log.gz` retains the
  missing overlay-directory failure. Object owners are not unique syscall causes.
- `requests-by-path.jsonl.gz`: every status request, opcode, IDs and owners;
  shared inode pages have an explicit shared label. `path-totals.jsonl.gz`
  joins owner-touch counts with actual Git read bytes/mappings. Shared requests
  must not be summed across paths. `summary.json` contains exclusive top-level
  counts as well as all timing/metric spreads; recompute with
  `python3 docs/mp2/phase4-analysis.py` (no product execution).
- `index/`: imported Git index stat fields versus mounted `README.md` fields.
- `cold-0/`, `cold-2/`, `cold-20/`: three fresh independent samples each. No
  changed read treatment/after arm: content dominated, activating the requested
  conditional stop. 20 ms samples are censored at 115 seconds, exit 124, not
  completed medians. The partial request counts show continued progress, not
  evidence of a transport hang. No 240-second timeout exception was received.
- `node-2/`, `node-20/`: three independent seed copies each, full then incremental
  Commit on the same mount. The SDK readback verifies the added manifest on A.
  Store requests/bytes/objects cover Commit only; FUSE copy, inode reservations
  during preparation and npm installation are outside that timer.
- `full-manifest.json.gz`, `delta-manifest.json.gz`, `node-shape.json`: every
  selected file's source path, size, SHA-256; deterministic sample without
  symlinks, original bytes, normalized 0644 mode. Depth counts all parent
  directory components, including node_modules. The original install
  was only read. Sparse Bun-layout sample is not a runnable npm installation.
- `rtt.json`: ping distributions. B-egress netem adds the full configured RTT;
  the Phase-3 CPU-0 proxy/yielding-loop calibration is reused. First probes can
  pay ARP; raw ping output is retained. No build overlapped measured operations.

B receives only its own cache/overlay volume, read-only input and binaries.
`commands.jsonl` retains exact Docker setup/exec/cleanup commands, wall ns,
stdout/stderr and exit status. No token/config contents are published. Each
sample starts with a new B cache and mount; server/OS page cache is uncontrolled.
Commit payload is warm from own writes. Disposable only, one construction worker.
All samples are diagnostics, not frozen performance-family qualification.

## Commands and outcomes

Remote prefix for Cargo commands: `cd ~/lfs-remote/mp2-remote-store`; run through
`/usr/local/bin/docker run --rm --name mp2-p4-check -v "$PWD/source:/work" -w /work
-e CARGO_HOME=/work/.cargo-home -e CARGO_TARGET_DIR=/work/target-remote mp2-p4-tools`.
The build profile and root ARM64 flags are unchanged. Setup is reproducible via
`bash source/docs/mp2/phase4-prepare.sh`; all output is `receipts/prepare.log.gz`.

| Command (inside its container unless noted) | Result |
| --- | --- |
| `cargo build --manifest-path core/Cargo.toml --locked -j 2 --profile test -p layerfs-remote-store --bin layerfs-store` | PASS |
| `timeout 120 npm ci --offline --ignore-scripts --cache /work/npm-cache-root --no-audit --no-fund`, Node 22 image, `--network none` | FAIL: ENOTCACHED; no download/retry; fallback selected |
| `cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store --test request_paths --test transport --no-run` | Initial helper compile FAIL (wrong imports/Arc/root wrapper); build only, no tests ran |
| Same no-run command prefixed `timeout 120` after correction | PASS; `receipts/checks02.log.gz` |
| `timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store --test transport` | 2 PASS |
| `timeout 120 /bins/request_paths-<hash> --ignored --exact request_paths --nocapture` | First FAIL: missing fixture directory; after `mkdir /state/paths-overlay`, 1 PASS, 2.34 s |
| `rustup component add clippy` then `cargo clippy --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-remote-store --all-targets -- -D warnings` | PASS; ephemeral installation, rsproxy.cn distribution mirror |
| `timeout 120 python3 -B core/tools/check_product_boundary.py` | FAIL: same 57 upstream violations; normalized comparison retained |
| `timeout 120 python3 -B -m unittest discover -s core/tools -p 'test_*.py'` | 50 PASS |
| Local `rustfmt --edition 2021 --check core/crates/layerfs-remote-store/src/server.rs core/crates/layerfs-remote-store/tests/request_paths.rs` | PASS; no local Rust build |
| Remote `python3 source/docs/mp2/phase4-diagnostics.py seed` | PASS: reused already compiled driver, `timeout 120 /bin-lfs/driver --ignored --exact drive --nocapture`, explicit Disposable fixture |
| Same launcher `diagnose` | PASS: `timeout 120 strace ... git --no-optional-locks status --short`; no changed treatment |
| Same launcher `index` | PASS: `timeout 10 git ... ls-files --debug README.md`; stat comparison |
| Same launcher `cold-0`, then `cold-2`, then `cold-20` | First six statuses PASS; last three INCOMPLETE at `timeout 115`, exit 124 |
| Same launcher `node-2`, then `node-20` | 12 Commits PASS under `timeout 25`; 6 server SDK readbacks PASS under `timeout 10` |
| Every ordinary copy into FUSE | `timeout 115 cp -a --no-preserve=ownership ...`, PASS; excluded from Commit time |
| Every mount/unmount/stats | `timeout 25 /bin-lfs/layerfs-remote /state/control.setup ...`, PASS; exact replies retained |
| Local `git diff --check`; Python AST parsing of changed scripts; summary arithmetic/count checks | PASS |

The topology launcher is a sequence of separately bounded operations, not one
background test escaping a test timeout. The traced object mapper streams file
bytes to a sink. Its 120 s bound is separate from timed cold/Commit operations.
The sole long diagnostic selection (20 ms status) was cut rather than silently
extending the deadline. No failed Commit was replayed.

No new content/cache protocol was selected, so there is no batching unit suite
or fabricated after result. No FUSE edits, Durable runs, frozen fs-bench-pro,
remote JS SDK, recovery, ignored-path feature, provisioning or lifecycle campaign.
Prior accepted lifecycle/merge/error evidence is reused, not rerun or relabeled.

## Custody and cleanup

The owned `mp2-p4-*` containers, networks, data/input/seed volumes and temporary
tools image are removed; `cleanup.log` records the exact removals and final empty
inventories. Existing containers/images/source/Maven/cache volumes were not
modified. B never received the Store. Source, input snapshots and hash-addressed
executables remain under the permitted remote campaign directory for inspection.
`production-comparison.json` proves the exact parent/staged product delta; the
first implementation commit tree matches it. Reference absent (retired R9c;
last counted 65,417 at tree 498dd1917812).
