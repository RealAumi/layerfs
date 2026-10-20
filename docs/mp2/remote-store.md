# Cross-machine Store: option A

> **Status: Proposal; target mp2 prototype; not a released contract.**
> Source: `3a80ec6d9a67b77d6b62fe5b45c676dac2073bee`, 2026-10-20.
> Phase 1: source inspection only; no builds, runtime tests or measurements.

One authoritative SQLite Store stays on the server; Content construction,
Workspace, Overlay and FUSE run in each VM. Platform `fs.*` runs **on the server**
through the existing JS SDK. The external executor owns commands/cancellation.
This task proposes an opt-in exception to today's direct-Store-only topology;
preserve that default without restoring F12 or `layerfs-server`. Task-supplied
single-host timings are unverified here and do not forecast remote performance.

## 1. Source audit: the three interfaces are necessary, not sufficient

Paths below are relative to `core/crates/`; **S** = `layerfs-store-service/src/`,
**D** = `layerfs-daemon/src/`, **W** = `layerfs-workspace/src/`,
**C** = `layerfs-content/src/`, **F** = `layerfs-fuse/src/`.

The exact traits are `AuthenticatedObjects::read_canonical_batch(&[ObjectId])`
([C/object/access.rs](../../core/crates/layerfs-content/src/object/access.rs)),
`FileLengths::{file_length,file_lengths}` (`W/ports/lengths.rs`) and
`InodeSerials::reserve(count)` (`W/workspace/serials.rs`). Concrete `StorePorts`,
`StoreOperation` and `BoundWorkspace` still need decoupling. `CanonicalClient`
already accepts object/length trait objects; its `resident` client must remain
memory-only inside overlay jobs.

| Mounted operation | Store-touching route and facts | Coverage / missing seam |
| --- | --- | --- |
| Bind / mount | `D/control/operations.rs` → `Store::bind` (`S/store/bind.rs`): opens a per-Workspace read session, obtains `HistoryCatalog::branch_snapshot`; `checked_base` → `BaseView::open`, inode lookup, directory-root decode, portable attributes. Opens local overlay from template. | Objects cover root validation. **Missing:** coherent `BranchSnapshot`, Store identity, construction policy/profile/scope, reader lifecycle. Remote bind replaces local SQL reader opening. |
| Attach / Ready | `D/control/attach.rs` → `Workspace::prepare_serials` → `reserve_inodes(ReserveRequest)` before kernel attachment. | `InodeSerials` covers this **write**, 1,024 serials per Workspace refill; unused serials stay consumed. |
| Lookup / getattr / open | `F/operations/lookup.rs`, `D/service/filesystem_port.rs` (`FilesystemPort`, `RequestServices`) → `W/operations/kernel_read.rs` → `BaseView::{child,inode,stat}` (`W/base/view.rs`): directory/inode pages, attributes, symlink target; regular-file length. Directory link counts enumerate child kinds (`W/base/links.rs`). | Objects + lengths. No head or hint-table lookup. Missing resident facts are fetched outside the overlay lock. |
| Readdir | `F/operations/directory.rs` → `KernelDirectoryWindow::finish` (`W/operations/kernel_directory.rs`): merge local names with `BaseView::list_after_bytes`; individual `BaseView::inode` kind lookups reuse cached pages. Cookies remain local. | Objects; ordinary readdir needs no file lengths/payloads. Batched inode reads occur in link-count/sibling-length prefetch, not this kind loop. |
| Read / readlink | `F/operations/read.rs` → `KernelWindow::finish` (`W/operations/kernel_data.rs`): local payload/zero/reference pieces plus `BaseView` / `FileView::{open,read_range}` for inherited bytes, mapping pages and chunks. | Objects; lookup/stat may already have demanded lengths. Fully local windows require no Store call. |
| Write / namespace mutation | `F/operations/mutation.rs`, `D/service/filesystem_port.rs`: resolve missing base facts, then one local publishing job. `recognize` can fetch committed mapping pages; create calls `StorePorts::take_serial`, including low-water refill. | Objects + lengths + serials. Payload edits are local SQLite writes, not remote Saves. Neither an arbitrary write nor create is guaranteed network-free. |
| Commit | `Request::Commit` → `Service::execute_control` → `BoundWorkspace::commit_captured` → `commit_admitted` (`S/store/captured.rs`, `commit.rs`). Capture, normalize, construct; Save, head/merge/history; install. | Three interfaces cover base reads/lengths/allocation only. Additional dependencies below. |
| Status / close | `D/control/status.rs` reads maintained binding/overlay, **not current head**. Dirty unmount reporting (`D/control/dirty.rs`) can read base objects via `TreeTable::open` / `compare::locate`. Close releases overlay and Store reader/producer (`S/store/operation.rs`). | Objects cover dirty-path reporting; explicit server snapshot supplies current-head observation. No history deletion. |

Optional operator calls are separate: `D/operator/workspace.rs` reads base
objects/lengths for live changes; `D/control/inspect.rs` combines history and
Workspace observations. Refuse unavailable Store diagnostics explicitly in
remote mode; do not add remote `HistoryCatalog` calls for them.

Commit also touches `FileDigests::{file_roots,record_file_digests}` through
`StoreDigests` (`S/store/digests.rs`, 64-row windows); `Storage::policy`,
`begin_save`, same-Save reads, `Save::accept/finish`; logical-size history and
length facts; `CatalogHints` / `record_new_bindings` (`binding_hint`);
merge scratch, serial allocation, publication lane and `commit_branch`.
Storage's pack/ordinal reservations, locators, signatures, pooled metadata and
pack writes stay server-local.
Prototype remote construction omits optional `CapturedNamespace::with_digests`:
correctness survives, but fresh-file reuse acceleration is unqualified. Binding
hints stay enabled server-side; provider failures must not become empty hints.

**Identity correction:** `ObjectId::for_bytes` is
`BLAKE3("layerfs/object/v2\0" || canonical_bytes)`, not raw BLAKE3 of bytes
(`C/object/id.rs`). Lengths are trusted server metadata, not payload-hash proofs.

## 2. Commit and protocol boundary

Extract `commit_admitted`'s Store half as a shared candidate publisher; keep
capture, installation and failure custody in `BoundWorkspace`. Adapt its concrete
`Save` wrapper to `AuthenticatedObjects` + `FinalizedConsumer`, already accepted
by `CapturedNamespace::construct` (`W/construction/driver.rs`). An indexed local
spool supplies reads of newly constructed children. Do not remote
`PackPersistence` or `HistoryCatalog`: their locks/physical internals stay local.

Proposed semantic RPCs (names are new, not existing APIs):

| Call | Request → result / completion |
| --- | --- |
| `Bind` | Store/branch and fresh Workspace identity → one coherent `BranchSnapshot`, canonical policy/version, root-validation objects, initial serial block. Server reserves the block once; combine reads/reservation in one response without claiming a single read-only transaction. |
| `GetObjects`, `GetLengths`, `ReserveInodes` | Ordered bounded IDs → exact ordered results; scope/count → consumed range. Positive immutable cache entries only. |
| `Lacking` | Bounded ordered candidate IDs → missing bitmap. Use server-local locator lookup; no pack/row details on the wire. |
| `Upload` | Missing `(id, role, canonical bytes)` in child-before-parent order → acknowledged saved window after `Save::finish`. Each window has its own stack-local Save; prior windows satisfy later dependencies. No remote borrowed Save session. |
| `CommitCandidate` | Operation ID, original binding, captured candidate root, pending-conflict context and message → committed/up-to-date result or conflict, exact installed root/binding and merge report. No implicit forced overwrite. |

Page the disk-backed emission index through `Lacking` then `Upload`, preserving
dependency order. Existing Save CAS arbitration handles racing duplicates. Use windows
(initially 512 objects / 4 MiB, separately admitted singleton up to the existing
16 MiB object ceiling); backpressure limits buffers, never total Commit size.
Use `FinalizedObject::admit`, derived references, `validate_context`, saved
closure and root/profile/scope/root-serial checks. These do **not** prove
whole-tree topology, alias counts or serial ownership. Prototype peers must be
trusted instances of the same constructor; hostile-client validation remains open.

The existing driver reads the head and performs the main three-way merge
**before** the publication lane. It finishes Save, calculates logical size and
records bindings outside the lane. Inside the lane it rereads the head; a second
move invokes `merge_in_lane`, bounded to 1,024 changed serials, otherwise
`CommitError::LaneMerge` (no retry). It then calls `HistoryCatalog::commit_branch`
with expected head/base/root. Preserve `.lww`, statistics and single-writer
admission, with **no network I/O while holding the lane**. A conflict publishes no head: return
the saved marker root and head binding for local installation. The daemon must
retain `PendingMerge`, refuse unresolved markers, preserve post-capture writes,
and use `prepare_base_install` / `install_prepared` plus `stale_after_install`
kernel invalidation. Fetching merged objects can fail after known publication;
that is a local-install failure, not a failed server Commit.

Reuse `layerfs-bridge::duplex::{initiate,accept,Connection}` over TCP:
Noise KK, Curve25519/AESGCM/SHA256 on x86_64; 65,519 plaintext bytes per record
(`layerfs-bridge/src/duplex/profile.rs`). Existing `Call` / `Answer` carry Hello,
Mount, Attach, Commit, Status, Locate and Unmount; `InitialRecord` distinguishes
control from Store-file installation. They contain **no object-batch protocol**;
the daemon rejects SDK Store calls despite retained `Sdk`/history vocabulary.
Use separate daemon→server connections with a new versioned Store message family,
fragment offsets/lengths and explicit end/result records over the same Noise
transport. A bounded read pool independent of upload/publication preserves
read capacity. Keep controller→daemon control unchanged; no HTTP stack needed.

Auth: use a random 32-byte shared token as the clients' Noise static credential
(`duplex::public_key` supplies the server's allowed peer), with a pinned server
public key. Protected files hold credentials. Every holder has whole-Store
authority. **TODO:** per-Workspace authorization, revocation and rotation.

## 3. VM launch, cache and failures

Today Docker uploads the executable and binary `DaemonSetup`, mounts the volume
at `/layerfs-store`, then starts
`layerfs-daemon --config /layerfs-local/config/daemon.setup`
(`layerfs-sandbox/src/backend/docker/archive.rs` and `container.rs`). Config names
`/layerfs-store/global/store.sqlite`, overlay template, `/workspaces`, listen
address, Noise keys, command UID/GID and resource limits. Secrets are not env/argv.
`D/application/cli.rs` already launches a plain Linux process; Docker supplies
placement and security, not the FUSE implementation.

Add explicit remote configuration/startup, keeping local mode unchanged: server
address/Store ID, token/server pin, local control keys/listen address, cache and
overlay paths, mount home, limits. No Store path or installation manifest in the
VM's remote mode. Server opens an existing Store at an explicit local path using
Disposable/WAL/OFF, binding and cursor authority; retain
`S/kernel_guard.rs` checks (Linux, ext4/xfs/btrfs). That guard verifies filesystem
type, not cross-machine kernel identity. SDK and server Store openers share one
kernel. No NFS/shared SQLite fallback.

Launcher requirements: matching x86_64 Linux binary; root/CAP_SYS_ADMIN daemon;
daemon-owned 0700 directories and 0600 config; `/dev/fuse` character device owned
by daemon and narrowed to 0600; traversable protected mount home. Existing
config rejects command UID/GID 0 and daemon/command UID equality: cloud-sandbox's root
availability suffices for launch, **root agent commands need a different design**.
External executor drops to e.g. UID/GID 1000, drops capabilities, sets
no-new-privileges and prevents copied mount/user namespaces as Docker's seccomp
policy does. It shares the mount namespace and reaps descendants. Preserve
`F/mount/profile.rs` negotiation (ASYNC_READ/BIG_WRITES, 128 KiB windows, no
writeback), mountinfo checks and Ready handshake. `/sys/fs/fuse/connections`
controls optional forced teardown. Use TCP, no Docker socket. Set
`LAYERFS_CONSTRUCTION_WORKERS=1`; other startup settings live in config.
Kernel 6.1 compatibility requires a real mount test.

Cache proposal: `/var/lib/layerfs/remote/<store-id>/objects.sqlite`, nonauthoritative
canonical BLOBs keyed by ID, role and positive length facts; indexed per-attempt
emission order beside them. Use existing SQLite dependency, bounded queries,
MEMORY/OFF, no fsync; never store packs or mutable heads as cache truth. Verify
objects before insertion and on disk read. Retain verified objects for VM-disk
lifetime, including daemon restarts: **“forever” means unbounded disk growth until
capacity, not bounded storage**. Report ENOSPC explicitly; no silent eviction.
Keep a configurable 64 MiB RAM cache plus bounded admitted request buffers;
this is not a whole-process/page-cache residency claim. Existing
`CanonicalClient` limits a demand to 4,096 IDs / 32 MiB, one object to 16 MiB.

Cold RTT model, not a measurement: 5,000 files alone does not determine tree
shape, metadata diversity, `ls` options or cache misses. For a flat directory,
16-byte names, inline attributes, contiguous serials, no evictions and a
two-level inode tree, unbundled bind/attach needs **6 application round trips**:
snapshot, filesystem root, inode branch, inode leaf, directory root, reservation.
Root getattr's child-directory count visits 256 names/window (20 windows);
8 KiB directory pages imply roughly 16–40 leaf fetches and at most 20 batched
inode-leaf waves. Thus mount + ordinary `ls -R` is roughly **42–66 round trips**
under these assumptions; subsequent readdir hits those pages. Add TCP + KK
handshake (approximately two RTTs per cold connection). Attribute-heavy stat
walks can add thousands of metadata misses; sibling-length prefetch already
batches first+128 following entries (`W/base/view.rs`). Deep trees add dependent
descents. This is not a universal bound.

Bundled `Bind` reduces mount to one application RTT. Optional demand-triggered
metadata prefetch can return directory descendants and their inode pages in
bounded 256 KiB batches: the flat example's roughly 0.5–1 MiB metadata could
need about 3–6 application exchanges including bind, if the dependency walk is
server-side. No file payload prefetch or whole-tree work at mount. Account for
all transferred bytes and prefetch work; verify these estimates with counters.

| Failure / race | Required outcome |
| --- | --- |
| Server unreachable during read | Cached/local windows still work; a miss returns request-scoped EIO, never ENOENT/zeros. Preserve original error and fencing; no automatic resend. A failed serial reservation follows existing stricter mutation custody. |
| Upload / Commit disconnect | Completed saved windows may remain unreferenced. Before Commit was sent, head publication was not attempted. After send, a lost result is Unknown: retain capture/spool and refuse another Commit; never infer outcome from current head alone. Prototype has no automatic reconciliation or replay. |
| Daemon restart | Verified cache can survive. Overlay MEMORY/OFF files may remain or be corrupt; frontier, bindings, open handles, serial remainders and conflict custody are in memory. `S/overlay/workspaces.rs` creates a new template/roster; it does not reopen mounts. Start a new incarnation in a fresh overlay directory, preserve old evidence; uncommitted edits are not recoverable by contract. |
| Two sandboxes, same branch | Different scoped serial ranges; independent overlays; server publisher merges against moved head and CASes in the shared lane. Conflicts stay local, not published. Mounted bases do not automatically follow later server `fs.*` writes. |

Server WAL/OFF survives ordinary process termination under its existing contract,
not VM/kernel crashes. Durable execution remains `NOT_RUN — disabled by owner`.

## 4. Phase 2 scope and upstream churn

Add `WorkspaceBackend` / operation ports in S with local and remote adapters;
share candidate publication. New `layerfs-remote-store` owns client/server/cache/
wire; daemon depends on it, it depends on store-service/bridge, never on daemon.
Its controller connects to the plain daemon for Mount→Attach→Commit→Unmount.
Content, FUSE algorithms, Docker and JS SDK routing remain unchanged.

Anticipated edit surface below; refinements require source review in phase 2.
Existing numbers are **production LOC**, using `tools/production_loc.py --files`
at the pinned commit; directory subtotals cover only shown files. Parenthesized
numbers count commits touching that exact path, without rename following, via
`git log --since=2026-10-06T18:48:11+08:00 --format=%H 3a80ec6d9 -- <path>`.
This is the two weeks ending at HEAD's timestamp; **hot = at least 8 changes**.
New paths have zero history; estimates appear separately, never as file counts.

```text
core/crates/layerfs-store-service/src/store/ [1699] (partial)
  mod.rs                                      33 (5)
  bind.rs                                    144 (2)
  captured.rs                                238 (2)
  commit.rs                                  444 (5)
  commit_merge.rs                            282 (6)
  commit_types.rs                            215 (4)
  operation.rs                                75 (2)
  ports.rs                                   241 (4)
  settle.rs                                   27 (1)
  backend.rs                                   — new
  publish.rs                                   — new
```

```text
core/crates/layerfs-daemon/src/              [2747] (partial)
  application/                              [885]
    mod.rs                                    14 (5)
    cli.rs                                    44 (1)
    config.rs                                115 (9; hot)
    diagnostics.rs                           369 (17; hot)
    filesystem.rs                            110 (4)
    owner.rs                                 233 (12; hot)
    remote.rs                                  — new
  control/                                 [1192]
    attach.rs                                230 (8; hot)
    dirty.rs                                 141 (1)
    failure.rs                               235 (16; hot)
    inspect.rs                                65 (4)
    observation.rs                            84 (7)
    operations.rs                            300 (27; hot)
    registry.rs                              137 (8; hot)
  operator/                                 [313]
    workspace.rs                             313 (4)
  service/                                  [357]
    filesystem_port.rs                       357 (30; hot)
```

```text
core/crates/layerfs-bridge/src/               [146] (partial)
  daemon_setup.rs                             146 (6; preserve local codec)
```

```text
core/crates/layerfs-remote-store/                [0] (new; no existing source)
  Cargo.toml                                    — new
  src/                                         [0]
    lib.rs                                      — new
    cache.rs                                    — new
    client.rs                                   — new
    config.rs                                   — new
    server.rs                                   — new
    wire.rs                                     — new
    bin/                                       [0]
      layerfs-store.rs                          — new
      layerfs-remote.rs                         — new
```

Also anticipated: `core/Cargo.toml` (14 changes, hot), `core/Cargo.lock` (20, hot),
`core/crates/layerfs-daemon/Cargo.toml` (11, hot). New private remote setup
vocabulary must leave old `DaemonSetup` encoding/initializers usable. Update
opt-in topology contracts in `AGENTS.md` (16, hot), `core/AGENTS.md` (58, hot),
`core/docs/issues/303/06-cluster-one-integration.md` (12, hot) and
`core/docs/issues/352/DIRECT_STORE.md` (3); this note is new. External tests go
under the affected crates' `tests/`, new paths with zero history.

Planning estimate: 1,800–2,600 new production lines for remote transport/cache/
server/controller, 700–1,100 for shared backend/publisher adaptation, 400–700 for
daemon startup/integration: **2,900–4,400 added/rewritten lines**, not net growth.
Allow another 800–1,200 test lines. Hot adapters warrant small sequential commits
and rebase review; low counts in store-service partly reflect its recent move.

Prototype gates, in order:

1. Extract seams with local behavior preserved; test saved-candidate publication,
   identity/cardinality/fragment validation, closure and exact failure outcomes.
2. Two Linux hosts (or two network-isolated containers): server alone mounts the
   Store; VM/container B has only local overlay/cache and `/dev/fuse`. Run server
   `fs.*`, remote mount, tree/read oracle, edits, Commit, server SDK readback and a
   fresh mount. Use external commands, including a failing command whose edits
   are still explicitly committed. Prove no Store file is opened on B.
3. Two daemon instances race same-branch disjoint and overlapping edits; verify
   merged content, conflict markers, later-write preservation, hard links,
   symlinks, sparse data, retained descriptors and repeated Commit/unmount.
   Cut TCP during read/upload/publication/reply; corrupt cache/object input;
   kill daemon; verify EIO/Unknown/no replay and cache reuse without overlay
   recovery claims. Check nonroot permissions and actual Ready on cloud-sandbox kernel 6.1.

Build selected packages locked; compile tests with `--no-run`, then impose an
explicit ≤120 s timeout per test command. Exclude frozen fs-bench-pro. Timing
needs a separate policy/cache declaration. Leave out Durable, offline Commits,
restart reconciliation, GC, replication, remote JS SDK packaging, cloud-sandbox
provisioning, FUSE optimization and hostile-client/per-Workspace security.
Phase 1 stops here.

## Phase 2 results (in progress)

Prerequisite at phase-1 source `cfbd865f5`: the real mounted test
`core/crates/layerfs-daemon/tests/remote_refresh_gate.rs` passed on remote-host,
Docker 29.4.0 / Linux arm64, Rust 1.85.1. The build retained the repository ARM64
flags and explicitly selected Disposable; no Linux compilation ran locally.

- A clean mount with cached data accepted server `fs.write` followed by Commit,
  and immediately read the new bytes. Disjoint local edits survived the same flow.
- **Correction to phase 1:** nonzero `command_uid` is a configuration/attribute
  identity, not a caller-UID allowlist. `request/callbacks.rs` does not inspect
  request UID; `attributes.rs::Identity::attributes` projects configured UID/GID
  for every inode. Root touch/write/cat succeeded and the new file appeared as
  `65534:65534`. Kernel `default_permissions` still applies; this is not root
  isolation. The configuration rule remains unchanged.
- The first fixture mistakenly wrote `main`: SDK refused `ReadOnly` before the
  refresh check. The corrected test forks writable `work`; no product fix was needed.

Test commands so far (inside the owned Linux test container, cwd `/work`,
`CARGO_HOME=/work/.cargo-home`, `CARGO_TARGET_DIR=/work/target-remote`,
`LAYERFS_CONSTRUCTION_WORKERS=1`):

```sh
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test remote_refresh_gate --no-run
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test remote_refresh_gate -- --nocapture
```

Both commands ran twice: first no-run PASS / execution FAIL (`main` ReadOnly,
0.01 s); after fixture correction no-run PASS / execution PASS (1 test, 0.03 s).
Compilation ran first with `cargo build --manifest-path core/Cargo.toml --locked
-j 2 --profile test -p layerfs-daemon --test remote_refresh_gate` (PASS).
Fuser provenance check passed. Initial build setup failures were missing Git
metadata in the rsync copy and login-shell PATH hiding Cargo; fixed in the owned
remote directory/container. One dependency acquisition/build was interrupted
after crates.io timeout diagnostics; rsproxy then supplied locked dependencies
with retries disabled. Raw logs are retained under `~/lfs-remote/mp2-remote-store/`.
Remote transport, two-container proofs and RTT diagnostics are not yet run.

Shared publisher/backend checkpoint: `Store::publish_candidate` now owns the
existing two-stage merge/publication algorithm; local capture/install stays in
`BoundWorkspace`. Daemon changes route the backend and classify remote errors.
After extraction, the mounted refresh/root test passed again (1 test, 0.03 s),
and `lane_merge` passed all 4 cases (0.22 s). Its incidental timing output is not
promoted to performance evidence. Commands, once each at this checkpoint:

```sh
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test remote_refresh_gate --test lane_merge --no-run
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test remote_refresh_gate -- --nocapture
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test lane_merge -- --nocapture
```
