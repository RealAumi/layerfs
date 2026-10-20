# Phase 6: default Git index refresh and bounded metadata batching

Dated diagnostics on remote-host, under `~/lfs-remote/mp2-remote-store/phase6`.
Source before: `ddf93133e`; product after: `6cc16e9`. Linux arm64 OrbStack
7.0.14, Git 2.39.5. All Stores Disposable, overlays MEMORY/OFF, construction
workers explicitly one. No Durable run, frozen fs-bench-pro run or local Linux
Rust build. Only the `phase6/` subtree here is new; historical run06 data is
untouched. This is not a benchmark admission or native-ctime correctness claim.

## Identities and method

`receipts/binary-custody.json` seals both executable arms. Copies are retained
by SHA-256 under the remote campaign's `artifacts/`. The baseline reuses the
accepted Phase-5 binaries; `before-bin` preserves them before installing the
new server, remote daemon and client. `receipts/source-custody.json` pins the
executed harness and remote-store source. `seed/results.jsonl` pins original
binary/image identities. `receipts/cleanup.log` pins kernel/Git, tools image
and both closed Store seeds. `production-loc.json` counts exact parent and
staged snapshots; the recorded staged tree equals implementation commit's tree.

Dubbo source cb05763298f081ed17171d704408b6478cf8fd83 came from the existing
read-only `lfs-src` volume; no download or source modification there. `seed`
imports the original host index. `warm` runs Git's own update-index in a mount,
Commits and copies the resulting consistent SQLite snapshot into an owned
warm-seed volume. No index stat bytes are written outside Git.

Every timing sample gets an independent A Store copy and a fresh B
cache/overlay/mount. A and B each have a private network plus their shared link;
B has no Store volume/path. Daemons and Noise channels are ready before timing.
The proxy and netem setup is inherited unchanged from Phase 3. B-egress adds the
full requested RTT; CPU-0 proxy/calibration loop and raw ping values are retained.
No build or other measurement cohort overlapped these samples. Server/host OS
cache residency is uncontrolled. “Cold” means the B application cache and kernel
mount, not cold disks. No status/prewalk warms the measured B mount.

Both timing arms enable server request tracing and narrow status syscall
tracing (`read,pread64,mmap`, `strace -yy`). Wall seconds sum the Docker-exec
mount and status intervals, excluding the intervening counter query. Counters
include mount and status. Object roles from A distinguish content from metadata;
length requests and metadata waves have their own classes. The two remaining
calls are Snapshot and inode serial reservation. Working files are unique
non-`.git/**` paths read with positive bytes or successfully file-mapped;
`.gitignore` counts. Every measured status reads that one working file only.

The user's explicit three repetitions supersede the general single-sample rule
for this diagnostic. Fixed status limit 115 s accommodates the ~83 s untreated
20 ms arm; it was not raised after a failure. Each selected command is separately
bounded; the Python campaign launcher does not wrap one unbounded test. No
failed operation or Unknown outcome was replayed. No tuning followed a failed
oracle: restored-mtime misses are retained as misses and matched against a′.

## Sequence, exact selectors and outcomes

Remote launcher sequence (working directory `~/lfs-remote/mp2-remote-store`):

```sh
bash source/docs/mp2/phase6-prepare.sh
python3 source/docs/mp2/phase6-diagnostics.py seed
python3 source/docs/mp2/phase6-diagnostics.py steady
python3 source/docs/mp2/phase6-diagnostics.py warm
python3 source/docs/mp2/phase6-diagnostics.py oracles-before
python3 source/docs/mp2/phase6-diagnostics.py measure-before-0
python3 source/docs/mp2/phase6-diagnostics.py measure-before-2
python3 source/docs/mp2/phase6-diagnostics.py measure-before-20
python3 source/docs/mp2/phase6-diagnostics.py join
# Build and install the new server/remote-daemon/client and metadata-test ELF.
python3 source/docs/mp2/phase6-diagnostics.py check
python3 source/docs/mp2/phase6-diagnostics.py oracles-after
python3 source/docs/mp2/phase6-diagnostics.py measure-after-0
python3 source/docs/mp2/phase6-diagnostics.py measure-after-2
python3 source/docs/mp2/phase6-diagnostics.py measure-after-20
python3 source/docs/mp2/phase6-cleanup.py
```

The `join` launcher intentionally retained its exact processes for follow-up
observation; its manual observation/cleanup receipts are separate. Subdirectory
`commands.jsonl` retains exact argv, output, exit and wall ns for every harness
operation. `results.jsonl` retains selected metrics and control replies.

- Seed: `timeout 120 /bin-lfs/driver --ignored --exact drive --nocapture`,
  `LFS_MODE=init`, `LFS_SOURCE=/original/dubbo`: **1 PASS**.
- Steady: `timeout 115 git -c safe.directory=* -C /workspaces/1 status --short`
  refreshes normally; a′ then returns clean despite changed forced hash:
  **missed change**, the baseline filesystem gap.
- Warm: same bounded Git with `update-index --refresh`, followed by
  `timeout 25 /bin-lfs/layerfs-remote /state/control.setup commit ...`: **PASS**.
  Saved device 83 versus live device 86 in independent B2; clean status reads
  only `.gitignore`, establishing this Git build tolerates the device change.
- Timed status: `timeout 115 strace -f -yy -o /state/status.trace -e
  trace=read,pread64,mmap git -c safe.directory=* -C /workspaces/1
  --no-optional-locks status --short`: **18/18 exit 0** (3 per RTT per arm).
- Each variant's oracles: (a) same-size write + `os.utime` restoring mtime,
  **missed, matches a′**; (b) server edit/remount **PASS**; (c) ordinary edit
  **PASS**. Git status/forced `hash-object`/`rev-parse :README.md` each use
  timeout 115. Server `fs.write`: `timeout 10 /bin-lfs/driver --ignored --exact
  drive --nocapture`, `LFS_MODE=write`, `/README.md`: **1 PASS per arm**.
  No-optional-locks prevents oracle status from changing the seed index.
- All mount/unmount control commands have timeout 25 (outer harness 27), with
  unchanged internal Join limit 5 s. **Warm dual-B: both unmounts retain Join;
  dedicated join check: B2 retains Join, B1 succeeds.** Single-B cohort,
  oracle and live-cache-test teardown succeeds. Failures are not erased.
- Live metadata: `timeout 120 /bin-lfs/metadata-test --ignored --exact
  remote_generation_is_verified_metadata_only_and_reused --nocapture`:
  **1 PASS**, 2790 metadata objects, 4725 lengths, 16 first-Snapshot requests
  (Snapshot + 15 waves); repeated root costs one Snapshot, no refill/payload.

Build inside the owned ECR-based tools container, source `/work`,
`CARGO_HOME=/work/.cargo-home`, `CARGO_TARGET_DIR=/work/target-remote`;
repository ARM64 flags retained, dependency mirror rsproxy.cn:

```sh
cargo build --manifest-path core/Cargo.toml --locked -j 2 --profile test \
  -p layerfs-daemon -p layerfs-remote-store --bins
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 \
  -p layerfs-remote-store --test metadata --test transport --no-run
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 \
  -p layerfs-remote-store --test metadata --test transport
cargo clippy --manifest-path core/Cargo.toml --locked -j 2 \
  -p layerfs-remote-store --all-targets -- -D warnings
timeout 120 python3 -B core/tools/check_product_boundary.py
timeout 120 python3 -B -m unittest discover -s core/tools -p 'test_*.py'
```

Build/no-run **PASS**. Tests **3 PASS**, one fixture-dependent test ignored in
this invocation and separately passed live above. Clippy **PASS** (component
installed in disposable tools container). Product guard **FAIL: 57 existing
violations**, all flagged sources/manifests byte-identical to parent, as checked
in `boundary-comparison.json`; no new remote-store guard finding. Guard tool
unit tests **50 PASS**. No tests deleted. No broad daemon/FUSE suite rerun;
those source paths are unchanged and the targeted end-to-end oracles cover
this selected integration. No new interruption/recovery campaign; existing
fragment/corrupt-identity transport tests pass, no replay/recovery was added.

Formatting: `timeout 30 rustfmt --edition 2021 --check` on changed remote-store
source and `tests/metadata.rs`: first command **NOT_RUN** because the pristine
Rust image lacks rustfmt (`format.log`). After adding that component through
rsproxy.cn in a new disposable container, the same check **PASS** (`format02.log`).
No source/dependency patch or timeout change. This final ephemeral container
was `--rm`; it leaves no campaign resource after the cleanup ledger.

## Receipts and limitations

- `steady/`: a′ raw timestamps and changed hashes.
- `warm/`: Git-owned refresh/Commit, device/index comparison and dual-B refusal.
- `measure-{before,after}-{0,2,20}/`: each of three independently initialized
  samples, all status accesses, Store request traces, role map and ping probes.
- `oracles-{before,after}/`: untimed fresh-fixture checks at no added delay;
  outcomes apply to the variant, not repeated per RTT.
- `join/`: exact retained reply, per-thread stacks and mountinfo, host mount scan.
  `receipts/host-fds.json` supplements visible pin inspection.
  `receipts/targeted-abort.json` records exact owned connection 84 and tasks
  before/after one cleanup-only fusectl abort; `join-cleanup.log` removes those
  owned resources. This confirms a missing receiver wakeup, not why the kernel
  held the connection. No FUSE fix was attempted under the protocol-only scope.
- `summary.json`: generated by `python3 -B docs/mp2/phase6-summary.py`, preserving
  medians/min/max, request classes, per-sample working paths, oracles and pings.
- `receipts/cleanup.log`: final removal of owned seed/warm/input volumes and
  tools image; empty owned container/network/volume inventories. Pre-existing
  source/cache volumes, images and other containers untouched. Hash-addressed
  executables remain below the permitted remote directory.
- `SHA256.json`: checksums for all retained phase6 files except itself. Large
  raw receipts are gzip-compressed without changing their uncompressed bytes.

Production LOC: **106288 → 106523 (+235)**; core 98118 → 98353, SDK 2861,
dsh 5309. Counter blob `e6d94d1a731b402ccc9159f49cef1eba5a74cfe0`, same
nonblank/noncomment/inline-test rules in both exact trees, subtract 739
scripted-mock lines. Raw product diff +246/−6; external tests +118. Reference
absent (retired R9c; last counted 65417 at tree 498dd1917812). The subsequent
docs/harness/receipt commit leaves production at 106523, delta 0.
