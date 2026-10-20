# Phase 8 receipts — receive cost, namespace scaling, ownership and ctime

Status: local OrbStack diagnostics, not a general benchmark or release claim.
Everything executed on this Mac. No SSH, real environment, push, upstream issue,
ignore work or other job resource modification. All created Docker names begin
`cx7-`. Other workloads, including the separate cxi job, were uncontrolled.

## Identities and cache policy

The original executable sets are the retained Phase 7 builds, byte-for-byte:
parent `6394865a4` and stop patch `524862598`. `setup/binary-custody.json` pins all
three sets, including the correction `c73497e2c`. Performance uses the original
524 server and CLI for every arm; **only the daemon executable changes**. Rust
1.85.1 test profile, repository ARM64 AEAD flags, local Linux arm64 Docker. The
candidate builds use `--locked -j 2`, own volume `cx7-target`,
`CARGO_HOME=/target/cargo-home`, `CARGO_TARGET_DIR=/target/cargo`, cwd `/work`.
No build overlapped a performance sample. `setup/image.log` pins the ECR Rust
image with strace/rsync/tc/ping tools. Phase 7's image is rebuilt for custody.

No local Dubbo checkout was found; one shallow pinned source fetch inside our
input volume obtained `cb05763298f081ed17171d704408b6478cf8fd83` (4,846 tracked
files). `setup/source.log` records it. No local commons-lang checkout was found;
only a partial Maven cache was present. Optional Maven is **NOT_RUN**, avoiding
new source/dependency downloads. `phase8-fixture.py` copies Dubbo into plain,
large, and hot fixtures. Large adds the retained Phase 4 full manifest's 30,000
node_modules files, sizes, directory paths and duplicate groups; contents are
deterministic synthetic SHAKE payloads, not an executable installed package set.
It has 211,730,666 file bytes and 9,470 directories. The hot fixture additionally
has 5,000 × 1 KiB files and a 256 MiB incompressible deterministic sequential file.
`setup/fixture.log` records totals. Both plain/large exclude node_modules in
`.git/info/exclude`; this is Git configuration, not a LayerFS exclusion.

Public SDK driver creates explicitly Disposable raw Stores. Each warm base is
mounted using 524, refreshed through Git's own `update-index --refresh`, committed,
and saved via a consistent SQLite backup. All three refresh/Commit/unmounts pass.
Each campaign A gets an independent seed copy; B gets **no Store path/volume**,
only its cache and overlay. A/B have private networks plus one shared link.
Construction workers=1; overlays retain MEMORY/OFF. No Durable execution.

Hot cohorts use an already-mounted Workspace with local object and metadata
caches warm. Every measured command has an untimed identical preparation. For
small/sequential reads only FUSE data pages are advised DONTNEED after preparation,
so measured reads still traverse FUSE while the backing immutable object cache
is warm. Counters confirm zero Store trips and real FUSE requests in every valid
sample. The stat path list is prepared outside timing; `stat` itself runs on
all 4,869 regular files (including Git internals). Status is 20 sequential
`git --no-optional-locks status --short` calls per sample, asserting clean output.
Both daemons stay mounted; sample order alternates AB/BA. Ten per arm per case,
explicitly requested by the owner. No samples removed as outliers. Medians and
min–max spread are descriptive; no statistical significance claim.

Cold scaling is one selected sample per root/delay, original 524 only. Fresh B
application cache, refreshed index; host/server OS caches uncontrolled. There is
one cache-count SELECT between mount and first status, disclosed separately from
timing. It reads metadata already populated by mount, not file payload. Reported
wall times include Docker exec/CLI startup; inner mount `wall_ns` is retained.
`tc netem` adds 0/2/20 ms on B's egress. Five ping receipts retain actual RTT:
plain/large averages 0.302/0.100, 5.168/4.673, 30.615/29.178 ms respectively.
These are added-delay scenarios, **not exact 2/20 ms end-to-end RTT claims**.
No RTT/workload adjustment or replacement sample was made.

## Campaign commands and outcomes

Host Python orchestrates local Docker; every child test/workload has an explicit
wall bound <=120 s. Each of the user-selected ten samples is separately bounded;
the multi-sample coordinator is not an unbounded test. `commands.jsonl` keeps the
full executed argv/output/exit/ns, and `results.jsonl` keeps each selected sample.
The caller-side timeout is slightly longer only to capture a bounded child exit.

```sh
python3 docs/mp2/phase8-run.py seed
python3 docs/mp2/phase8-run.py hot
python3 docs/mp2/phase8-run.py hot-stat
python3 docs/mp2/phase8-diagnose.py
python3 docs/mp2/phase8-run.py cold
python3 docs/mp2/phase8-run.py ownership
python3 docs/mp2/phase8-run.py ctime
# Build/check/seal c73497e2c, then new prospectively matched control cohort:
python3 docs/mp2/phase8-run.py hot-fixed
python3 docs/mp2/phase8-diagnose.py fixed
python3 docs/mp2/phase8-cycles.py seed fixed
python3 docs/mp2/phase8-cycles.py cycles fixed
python3 docs/mp2/phase8-cycles.py held fixed
python3 docs/mp2/phase8-summary.py
```

- `hot/`: all 100 commands exit zero; 20 stat samples **INELIGIBLE** because an
  empty printf format produced no per-file stat work (19 samples had zero FUSE
  requests; one had 60). Original scripts preserved as
  `setup/hot-v1-*.py`. Corrected format `%s\n`, then only stat selected again.
- `hot-stat/`: all 20 corrected samples pass their work oracle, exposing the
  **27.15%** median receive-path regression. No Store trips, 4,869 FUSE calls each.
- `receive-diagnosis/`: count-only strace, not performance samples. Parent makes
  4,869 reads. 524 makes 5,586 ppolls plus 5,586 reads with 717 EAGAIN reads.
- `hot-fixed/`: all 100 corrected cohort samples pass; no median regression
  above 5% versus its paired baseline. Original failing cohort is never replaced.
  Baseline stat sample 1 has 11,227 FUSE requests versus 4,869 for every other stat
  sample, and is retained at 147.23 ms. The 10-run result includes this mismatch;
  equal-request-rate qualification is **INCOMPLETE** for that cohort. Per-opcode counts were
  not collected. The 60 s entry TTL can cause extra revalidation even after
  preparation; that attribution is an inference, not proven for this sample.
- `receive-diagnosis-fixed/`: 5,045 epoll waits and reads, 176 EAGAIN reads for
  4,869 FUSE requests. Exclusive wake reduces, does not eliminate, raced reads;
  persistent registration also avoids rebuilding a two-fd poll wait each time.
  Tracer elapsed time includes idle/control gaps; do not compare its wall time.
- `cold/`: all six mount/clean-status selections and unmounts pass. Exact counts
  and times are in `summary.json` and the main note. No warm-up change.
- `ownership/`: all 12 selections retained. Root restoring source owner 0 gets
  cp=1, tar=2, rsync=23; all other selected cases exit 0. Every file's resulting
  owner/group is 1000, with readback hashes/modes. Strace includes exact fchown or
  fchownat failures, errno and command stderr. Nonroot cp can tolerate failed
  chowns and exit 0. Direct same-owner chown passes; chown 0 gets EPERM.
- `ctime/`: ordinary status writes the index, then same-size content edit and
  restored mtime goes unreported. Full pre/post ns, bytes, hashes, indexed and
  forced Git object IDs prove the existing gap. **FAIL detection, unchanged**.
- `cycles-fixed/`: **40/40 clean Git cycles**, **1/1 clean plain control**; no
  Retained(Join), normal umount flags 0, original joins consumed. Post-unmount
  inventories have no fuser/mount/fence tasks; service main remains.
- `held-fixed/`: expected **Busy/EBUSY**, inner wall 481,999 ns; mount and open
  descriptor remain, both receivers wait in epoll. Full held-case captures kept.
- Native custody uses exactly the Phase 7 cycle source except its receipt-root
  literal, with the same seed/shape/timeouts and umount-only strace. Every native
  failure would retain full probe/namespace evidence before cleanup. A held file
  is deliberately a failure selection, never retried or reported as success.

Limits: child seed driver 120 s; workload preparation/measurement 115 s; Git 110 s;
control mount/Commit/unmount 25 s; Status observer 8 s (socket I/O deadlines 3 s);
ownership trace 20 s; count-only tracer detach 5 s. Native cycles use the unchanged
Phase 7 bounds (Git 60 s, writes/probes 15 s, control 25 s). All selected normal
unmounts outside the deliberate held-file case succeed; no operation replay.

## Builds and required checks

Observer, before timing (both initial and after formatting):

```sh
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 \
  -p layerfs-remote-store --test receive_observe --no-run
```

Both **PASS** (`observer-build*.log`). Runtime observer invokes
`timeout 8 /observe/receive_observe --ignored --exact observe --nocapture` with
workspace/namespace env vars; all invocations pass and end their control session.
The fixture driver invokes `timeout 120 /bin-lfs/remote_driver --ignored --exact
drive --nocapture`, `LFS_MODE=init`, for three workload seeds and one custody seed.

Correction (`setup/fix-build.log`):

```sh
python3 -B core/tools/check_fuser_integrity.py
cargo build --manifest-path core/Cargo.toml --locked -j 2 --profile test \
  -p layerfs-daemon --bin layerfs-remote-daemon
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-fuse --tests --no-run
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test workspace_databases --no-run
```

All **PASS**. Subsequent checks (`fix-checks*.log`):

```sh
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-fuse --tests
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test workspace_databases
cargo clippy --manifest-path core/Cargo.toml --locked -j 2 -p fuser --lib -- -D warnings
# First attempted next command had --all-targets twice: rejected by CLI.
cargo clippy --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-fuse -p layerfs-remote-store --all-targets -- -D warnings
cargo fmt --manifest-path core/Cargo.toml --all -- --check
rustfmt --edition 2024 --check core/vendor/fuser-0.18.0/src/session/receive_stop.rs core/vendor/fuser-0.18.0/src/session/lifecycle.rs core/vendor/fuser-0.18.0/src/session.rs
rustfmt --edition 2021 --check core/crates/layerfs-remote-store/tests/receive_observe.rs
python3 -B core/tools/check_fuser_integrity.py
timeout 120 python3 -B -m unittest discover -s core/tools -p 'test_*.py'
python3 -B core/tools/check_product_boundary.py
```

**8 Fuse + 2 daemon tests PASS**, Clippy PASS (after correcting the duplicate CLI
flag), scoped formatting/integrity PASS, **52 tool tests PASS**. Workspace-wide
formatting **FAIL** on unchanged paths (`formatting-existing.json`). Boundary
**FAIL**, the same 57 reported findings as Phase 7 (`boundary-comparison.json`).
The summary parser initially rejected split strace lines; `summary-v1-failure.log`
and the original parser are retained. Matching unfinished/resumed syscall TIDs
fixes receipt interpretation without rerunning any native sample.
No failed test was retried unchanged; successful earlier commands were not rerun
because a later command failed. `setup/failures.md` indexes all check/harness
failures. No tests deleted or weakened. Frozen fs-bench-pro, Durable, other
platforms, recovery, content prefetch, ignore/ownership/ctime/warm-up changes
were **NOT_RUN / NOT_BUILT**, outside scope.

## Source size, preservation and cleanup

Correction first-party Production LOC **106524 →106524 (delta 0)**; core 98354,
SDK 2861, dsh 5309. Exact parent/staged counted-scope subtrees match. Counter
`tools/production_loc.py` blob `e6d94d1a731b402ccc9159f49cef1eba5a74cfe0`, excluding
comments/blank/inline-test lines, scripted mocks 739, tests/docs/tools/vendor.
Separate vendor runtime subtotal in the three changed Rust files **880→890 (+10)**;
raw runtime diff +43/−30, plus one Cargo feature line. No new dependency/version.
Reference absent (retired R9c; last 65417 at tree 498dd1917812). Documentation/test
commit leaves production and vendor runtime counts unchanged.

All failure/success receipts are immutable observations. Gzip, where used,
preserves original bytes. `SHA256.json` pins every receipt except itself; source,
image, fixture and executable hashes are retained. Cleanup removes all owned
cx7 containers/networks/volumes/images except the permitted **cx7-target** Cargo
volume. Cleanup is environment disposal, never a claimed successful product
retry or custody release. No other job resource is touched.
