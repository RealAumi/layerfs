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

## Phase 2 results

**Prototype implemented; read/Commit acceptance passed, normal unmount failed.**
All Linux compilation/execution ran on remote-host in arm64 OrbStack containers
(Docker 29.4.0, Rust 1.85.1), with Disposable Stores and repository ARM64 flags.
No push, upstream issue/PR, Docker-backend change or upstream contract edit.

`layerfs-remote-store` now supplies the versioned Noise Store protocol, server,
two-connection client and verified canonical SQLite cache. `WorkspaceBackend`
and the shared `Store::publish_candidate` keep network I/O outside the publish
lane. `layerfs-remote-daemon` mounts without Docker or a Store path; the separate
`layerfs-remote` controller performs explicit mount/Commit/unmount. Commands stay
external. Positive cached objects remain indefinitely; construction emission
order is SQLite-backed. Upload uses lacking-ID windows, child-before-parent
admission and local Save completion, then the existing server merge/CAS logic.
No new dependency package/version was introduced.

**Server edits and root callers.** Confirmed both by source and actual FUSE:
clean overlay + moved head proceeds through merge/install, rather than the
native UpToDate fast path. Server `fs.write` → remote Commit → ordinary `cat`
returns new content even after caching the old bytes; disjoint local edits
survive. Root touch/write/cat also works with `allow_other` and configured UID/GID
1000. New files appear as `1000:1000`. FUSE callbacks do not enforce request UID;
`Identity::attributes` projects configured ownership and kernel
`default_permissions` remains active. The nonzero setup rule is unchanged.
**This corrects phase 1's overly broad root-command warning:** it is not a
caller-UID allowlist or root isolation boundary. The earlier native proof used
65534 and observed `65534:65534`.

| Acceptance | Result |
| --- | --- |
| Remote mount, 3003-file tree/read oracle, local edits | PASS; independent server SDK-method-table reads matched sandbox file hashes. |
| Commit → server `fs.read` → fresh mount | PASS; B had binaries/cache/overlay only. |
| Failing external command's edits committed | PASS; command exited 7, explicit Commit preserved its file. |
| Server edit refresh, clean and disjoint dirty overlay | PASS; kernel cache invalidation observed by `cat`. |
| Root touch/write/cat, configured ownership | PASS; `1000:1000`, no setup-rule change. |
| Two B daemons, same branch, different lines | PASS; both line changes in server readback. |
| Same-line race | PASS; one conflict, history grew by exactly one winning Commit; loser published nothing. Markers and explicit resolution also checked. |
| Read TCP cut | PASS; cold content read returned EIO. |
| Upload TCP cut | PASS; Unknown, unchanged head, no reconnect; later Commit refused at admission with unchanged request count. |
| No Store access on B | PASS; Docker mounts, absent Store path and `/proc/*/fd` showed only local cache/overlay/template SQLite files. |
| Normal unmount | **FAIL** twice: detached=true, Join retained, two receive loops did not exit within existing 5 s. Main-process launch did not resolve it. No FUSE fix, deadline extension or failed-operation replay. |

RTT diagnostic ([raw result](receipts/run02/diagnostic.json)): empty B object
cache before mount, **mount 6 Store requests / 43.465 ms** including controller
process/Docker-exec wall overhead; subsequent **`ls -R` 24 requests / 17.387 ms**
for 3003 files (30 requests cumulative). The ls wall interval surrounds ls itself.
Counters exclude Noise handshakes/control RPCs; daemon startup is outside mount.
ls reuses mandatory bind pages; server/OS cache state is not cold-qualified.
These are one-run diagnostics, not performance qualification. No new prefetch
was added. The earlier proxy without TCP_NODELAY produced an ineligible slow
run and an oracle timeout; its evidence is retained, not overwritten.

The [validation ledger](phase2-validation.md) lists **every test command and
result**, including no-run invocations, all five E2E attempts, exact container
argv/outputs, initial failures and final checks. Final transport tests PASS 2;
native refresh PASS 1 and lane-merge PASS 4; core-tool tests PASS 50; scoped
all-target Clippy PASS. Changed-file formatting passes. Package-wide formatting
still finds three unchanged upstream files; the boundary guard has exactly the
same 57 violations as `3a80ec6d9`. All owned containers, networks and volumes
were cleaned up; other containers/images were untouched.

Local implementation commits:

| Commit | Change | Production LOC before → after |
| --- | --- | --- |
| `6771ecad8` | Mounted server-refresh and root-caller prerequisite proof | 104,430 → 104,430 (0) |
| `10d2c76b0` | Shared candidate publisher and Workspace backend ports | 104,430 → 104,890 (+460) |
| `6aa63705c` | Noise server/client/cache, remote daemon/controller and external proofs | 104,890 → 106,260 (+1,370) |

Results/receipt publication is a separate documentation-only commit, identified
by `git log -1 --format='%h %s' -- docs/mp2/phase2-validation.md` (unchanged
production 106,260 → 106,260, delta 0). Phase-1 design is `cfbd865f5`.
Overall phase-2 changed production: **2,560 lines (+2,195/−365; net +1,830)**;
external tests: **552 added code lines** (391 Rust + 161 Python harness/proxy),
no deleted tests. Nonblank/non-comment Rust is counted with pinned
`tools/production_loc.py` blob `e6d94d1a731b402ccc9159f49cef1eba5a74cfe0`,
including inline-test exclusion; diff counted over those code lines, so moved
publisher code contributes to churn. Python counts exclude comments/docstrings.
Final production scopes: core 98,090; SDK 2,861; dsh 5,309, excluding the same
739 scripted mock lines in every snapshot. Reference absent (retired R9c;
last counted 65,417 at tree `498dd1917812`).

**Limits and deviations.** The seam works as designed; the added semantic bind
snapshot remains necessary beyond the three read interfaces. Normal unmount
is an unresolved lifecycle gap, not a passing result. Server SDK calls were
exercised through the public native method table, not the JS wrapper. Execution
was Linux arm64 containers, not cloud-sandbox/x86_64/kernel-6.1 qualification. Remote force,
non-default Store policies and remote operator Store diagnostics are unsupported.
No metadata prefetch, read pool, eviction/GC, restart recovery/reconciliation,
Unknown replay, hostile-client hardening beyond bounded admission, per-Workspace
authorization, remote JS SDK, FUSE optimization, provisioning or command
supervisor was built. Durable was NOT_RUN—disabled by owner. Whole-workspace
and frozen fs-bench-pro tests were skipped as instructed; extra symlink/sparse/
descriptor/restart scenarios from the broader phase-1 plan remain unqualified.

## Phase 3 results

**Commit diagnostics completed; the historical unmount root cause remains
unresolved.** Product changes are limited to acknowledged upload counters
(`c834e1c`). No teardown/FUSE code, five-second deadline or replay behavior changed.
Detailed commands, raw results and limitations are in
[the Phase 3 receipt index](receipts/run03/phase3/README.md).

### Unmount investigation and ten-cycle proof

The pending pair is `fuser-0` / `fuser-1`, not the two Store TCP connections.
`control/detach.rs::Service::unmount_kernel` calls `KernelSession::detach/drain`;
`layerfs-fuse/src/session/drain.rs::quiesce` waits for
`SessionPhase::Joined`. The receivers run the vendored Fuser event loop, whose
`channel.rs::receive` reads `/dev/fuse`; the mount owner joins them. The remote
client owns synchronous channels and creates no receive threads. Its shared
Store sockets intentionally live across Workspace unmounts.

Two fresh reproductions, including the original refresh/root/failing-command
sequence, succeeded on committed Phase-2 source. Ten unchanged-source cycles
also passed. With only counters added, a second **10/10 consecutive
mount → edit → Commit → unmount proof passed** on separate A/B networks with
one shared link: [cycle receipts](receipts/run03/phase3/cycles/results.jsonl).
Every unmount returned `Unmounted`, median **0.768 ms**, range **0.712–0.872 ms**.
After every cycle the daemon returned to exactly one accept thread and the same
FD/socket identities; no per-mount threads, FUSE FD or overlay FD remained.
Explicit daemon stop then removed its PID and daemon-owned sockets. All owned
containers, networks, volumes and the temporary tools image were cleaned up.

**No root-cause fix is claimed.** Phase 2 recorded loop counts but no stuck-thread
stack or surviving mount-reference evidence. Its intermediate failing executable
was not retained; the rebuilt committed-source executable passes. Thus why that
historical detach failed to end the receivers is still unknown. Closing shared
Store sockets would not be a justified repair. The receipt index records the
binary identity gap; Phase-3 executables are now retained by hash remotely.

### Build-output cost

Used **real Dubbo** `cb05763298f081ed17171d704408b6478cf8fd83`, because its
sources and offline Maven repository already existed on remote-host. Offline
`package` with tests/checkstyle/RAT/Spotless skipped produced **5,354 files,
260,024,428 bytes across 115 target directories**. An initial uncached formatter
failure is retained. One leaf-module greeting change and incremental `package`
rewrote 1,430 output files / 23,377,148 bytes; three output files changed content
(class, JAR, compiler list), plus the source edit. Identical real output snapshots
were copied through FUSE into each fresh sample; builds ran once as preparation,
not inside the Commit timer or anew in each mount. No synthetic payload was used.

Each cell has **three samples**; values are median **[min–max] seconds**. Timers
cover control authentication through Commit reply; outer Docker-exec wall is
also recorded. Native means the existing local Store/FUSE daemon on the same VM.

| Store / configured RTT | First full output | Incremental output |
| --- | ---: | ---: |
| Remote, no added delay | **4.983** [4.945–5.208] | **0.260** [0.260–0.261] |
| Remote, 2 ms | **5.188** [5.170–5.204] | **0.272** [0.265–0.273] |
| Remote, 20 ms | **7.931** [7.166–7.990] | **0.376** [0.371–0.386] |
| Native local Store | **2.909** [2.891–2.918] | **0.285** [0.282–0.290] |

| Remote operation, identical counts in all nine samples | Uploaded canonical bytes | Objects | Store requests |
| --- | ---: | ---: | ---: |
| First full output | 114,849,854 | 11,781 | 73 |
| Incremental output | 43,368 | 10 | 3 |

Native has zero transport bytes/objects/requests; this does not mean zero Store
I/O. Upload counters count acknowledged canonical payload, excluding framing.
Save statistics report 81,108,655 new stored bytes first / 17,733 incremental
remotely, versus 81,096,106 / 2,018 locally; these are not allocated SQLite/WAL
file growth. [Recomputable summary](receipts/run03/phase3/summary.json).

Network verification mattered: naive netem on an idle OrbStack VM overshot its
setting. Earlier cohorts/calibrations remain retained and are not pooled. The
final matched cohort uses B-egress netem, the existing TCP proxy pinned to CPU 0,
and one low-priority continuously yielding loop on that CPU; daemon scheduling
is unchanged. The same CPU load/idle proxy exist in the native arm. Individual
ping medians were **0.013 / 2.04 / 20.0 ms**; the 2 ms samples include first-probe
outliers up to 4.085 ms, while 20 ms spans 20.004–20.052 ms. This controlled-load
setup is a diagnostic, not an idle-host or cloud-sandbox performance claim.

At 2 ms, **cold mount + `git --no-optional-locks status` on Dubbo** took
**20.579 s [20.505–20.605]**, with **8,885 requests [8,885–8,886]**. Mount alone
used seven requests; status used 8,878–8,879. Those wall intervals include
Docker-exec overhead. B's object cache and kernel mount were fresh; server/OS
caches could be warm. Commits followed metadata preparation and ordinary FUSE
writes, so metadata/overlay/own-write payload were warm. No cache drops or cold
Commit claim. Frozen fs-bench-pro and Durable were not run.

For the pending design decision: committing this full build output costs about
**5.19 s at 2 ms** and **7.93 s at 20 ms**, plus roughly 115 MB uploaded; that is
material overhead after every short task. The measured leaf-edit incremental
case costs **0.272 s / 0.376 s**, which is reasonable after each task. These
numbers support retaining incremental output when useful, but do not justify
assuming a fresh/full artifact Commit is cheap. They do not by themselves settle
a blanket “keep all ignored paths local” policy: core-module rebuilds,
node_modules, future read/rebuild savings and total task wall were not measured.
The earlier ~8 s native spike is not a matched comparison. No ignored-path
feature, prefetch, recovery, eviction or other excluded feature was built.

Validation: locked arm64 build/no-run PASS; transport tests 2 PASS; scoped
all-target Clippy PASS; core-tool tests 50 PASS; changed-file formatting PASS.
The boundary guard still has the same 57 upstream violations. Phase-3 production
churn is **33 lines (+29/−4, net +25)**; total production is **106,285**.
Fixture/harness/aggregation additions are about **227 non-comment code lines**,
within the requested harness budget. Counter/method and mock exclusions are
unchanged from Phase 2. No tests deleted; no push or upstream doc edits.

## Phase 4 results

**Content dominates the cold status; no batching optimization was shipped.**
The owner's conditional stop applies. The 2 ms target remains **FAIL** at
20.47 s. Added only opt-in `LAYERFS_REMOTE_TRACE_READS` in
`layerfs-remote-store/src/server.rs` (opcode + canonical IDs, no payloads), plus
an ignored external `tests/request_paths.rs` diagnostic that maps immutable IDs
to paths through existing Content readers. No protocol, cache, FUSE, Git policy,
retry or publication behavior changed. Local implementation commit:
`06a781cfceb61af32a967cae0d7af0c0142f7b82` — opt-in canonical-read diagnostics.

### Cold request attribution

A fresh, traced 0 ms mount used **7 requests**; subsequent status used **8,877**
(the earlier 8,878 is reproduced in the untraced 2 ms cohort). Tracing was off for
all timed samples. Canonical roles come from A's object-location catalog;
namespace owners come from a separate, untimed traversal of an independent copy
of the same sealed Store. Git's actual reads/mappings come from `strace`.

| Status demand | Requests | Objects / roots requested |
| --- | ---: | ---: |
| Whole-file content | 4,701 | 4,701 |
| Chunked content, including its extent/file-state pages | 157 | 769: 748 chunks, 16 extent pages, 5 file states |
| Directory/inode metadata | 2,772 | 2,629 directory pages + 150 inode-table pages |
| File lengths for lookup/getattr | 1,247 | 4,709 file roots |
| **Total** | **8,877** | **54.7% of requests fetch content** |

Length batching already exists in Workspace
`base/view.rs::provide_sibling_lengths`; the remote client preserves those
batches. It is not one length request per file. The metadata objects are needed
by lookup/readdir/getattr and shared across those operations; object traces do
not uniquely assign a shared page to one kernel opcode.

Examples of exclusive top-level ownership (shared objects are counted
separately, not charged repeatedly):

| Paths | Content requests | Metadata requests | Length requests |
| --- | ---: | ---: | ---: |
| `dubbo-common/**` | 962 | 237 | 201 |
| `dubbo-plugin/**` | 581 | 477 | 165 |
| `dubbo-rpc/**` | 610 | 198 | 107 |
| `dubbo-config/**` | 537 | 213 | 134 |
| `dubbo-remoting/**` | 462 | 206 | 91 |

[Every request and its owner paths](receipts/run04/phase4/requests-by-path.jsonl.gz),
[per-path request/read counts](receipts/run04/phase4/path-totals.jsonl.gz), and
[aggregate breakdown](receipts/run04/phase4/summary.json) retain the full detail.
A shared request can touch several paths, so per-path counts are not additive.
Inode-table pages are explicitly generation-shared. Git read bytes from **4,799
paths**, and also mapped `.git/index`, Git pack/index files and larger working
files; the syscall receipt names them all.

The imported index contains native-host stat identities. For `README.md`, its
cached uid/gid/inode are **502/20/70491307**, while FUSE reports
**1000/1000/20**, with matching size and timestamps. This explains the working
file rehash, rather than a pure metadata walk. `--no-optional-locks` also prevents
the usual optional index refresh from being saved. Even perfect elimination of
all metadata/length requests leaves **4,858 × 2 ms = 9.716 s** of serialized
content RTT alone. Metadata batching cannot meet 3 s for this cold workload.

The next experiment should address the transplanted Git stat cache: validate a
Git stat-check policy or an index-refresh lifecycle that remains correct across
mounts and server edits, with changed-file/racy-timestamp oracles. Keeping a
Workspace and its refreshed index alive can amortize the first rehash; it does
not establish a cold-mount guarantee. Do not silently weaken stat checks or
rewrite index stat fields to claim success. Once unnecessary rehashing is
removed, metadata batching would be the next transport improvement. Content
prefetch was explicitly excluded and was not built.

Three independent samples per condition; seconds are median **[min–max]**,
including Docker-exec wall for mount and status. “After” is deliberately N/A:
the content-dominant stop selected no new read treatment.

| RTT | Before: cold mount + status | Store requests, median [range] | After |
| --- | ---: | ---: | --- |
| No added delay | 2.493 [2.405–2.501] | 8,884 [8,884–8,887] | N/A |
| 2 ms | 20.471 [20.363–20.585] | 8,885 [8,885–8,885] | N/A; target unmet |
| 20 ms | **INCOMPLETE: all three status runs capped at 115 s** | 5,666 [5,665–5,666], partial | N/A |

No completed median is claimed for 20 ms. A 240 s diagnostic exception was
requested because the request-latency floor is about 178 s; none was received,
so the runs retained a cutoff below the repository's 120 s test ceiling.
These are bounded diagnostic observations, not frozen-family qualifications.

### node_modules Commit cost

A single network-disabled `npm ci --offline --ignore-scripts` attempt using an
existing lockfile and copied npm cache failed with `ENOTCACHED` for
`yocto-queue-0.1.0.tgz`. No package download was attempted. The fallback uses
**real file bytes and paths**, sampled deterministically from the existing
`~/work/mp2/node_modules` on remote-host: the lowest SHA-256 relative-path values
select 30,000 regular files out of 151,271 eligible files, excluding the added
dependency. Symlinks are omitted; this is a synthetic sparse installation shape,
not an executable install. The original Bun version-store directory structure
is retained, so this is not a claim about a flat npm layout.

Full tree: **211,730,666 bytes**, median file 820 B, p90 7,124 B, p99 73,770 B,
maximum 8,532,944 B; directory depth 5–15 including the `node_modules` component. Incremental:
add the complete existing **Zod 4.6.5** package under a new dependency path,
**840 files / 6,140,311 bytes**. This measures one dependency addition, not all
possible upgrades, removals or lifecycle-script output. Manifests and the
[shape summary](receipts/run04/phase4/node-shape.json) pin every selected byte.

| RTT | Commit | Seconds, median [min–max] | Uploaded bytes | Objects | Requests | New stored bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2 ms | Full | **14.252 [14.241–14.336]** | 198,832,210 | 42,903 | 186 | 48,791,195 |
| 2 ms | Add dependency | **0.312 [0.305–0.341]** | 5,985,194 | 702 | 5 | 1,010,991 |
| 20 ms | Full | **18.255 [18.212–18.465]** | 198,832,210 | 42,903 | 186 | 48,791,195 |
| 20 ms | Add dependency | **0.543 [0.541–0.544]** | 5,985,194 | 702 | 5 | 1,010,991 |

All non-time metrics were identical across all six samples. Upload bytes count
acknowledged canonical payload, not TCP framing. New stored bytes independently
match A's increase in `sum(pack.length)` and the Commit Save statistics.
SQLite occupied-page growth was **57,430,016 B full / 1,196,032 B incremental**;
it includes indexes/catalog overhead and is not the same metric as stored pack
bytes or SQLite/WAL file lengths. Six server-side SDK readbacks of the added
package manifest passed after publication.

### Conditions, conclusions and checks

Each sample cloned the same closed Disposable Store into A. B had a fresh
SQLite object cache, overlay and FUSE mount, with **no Store volume/path**.
A and B had separate private networks plus one shared link. The Phase-3 proxy,
B-egress netem and low-priority CPU-0 yielding process were reused; no parallel
build/measurement ran during timing. Ping packet medians were **0.023 / 2.03 /
20.0 ms**; first-probe outliers reached 4.10 ms and 40.1 ms. Exact probes are in
command receipts. Host/server OS caches were not dropped; only B's application
cache and new mount are cold. Commit follows ordinary FUSE copies, so overlay
payload is warm; preparation/copy/install time is excluded. There was no prior
`git status` warming for the node_modules samples. Construction used one worker;
Commit retained its 25 s command bound. These are diagnostics, not a benchmark
or cloud-sandbox qualification.

**Per-task decision:** the measured common incremental cases cost roughly
**0.27–0.31 s at 2 ms** and **0.38–0.54 s at 20 ms** for Maven leaf output or one
JS dependency addition. Those are plausible costs after each task. Fresh output
is materially different: Maven target costs **5.19 / 7.93 s**, and this 30k-file
node_modules shape costs **14.25 / 18.25 s**, at 2 / 20 ms respectively, plus
115 / 199 MB uploaded. Paying that after every short task is unattractive;
keeping ignored paths local would avoid that publication cost but also lose
shared/restorable output. These results support avoiding repeated fresh-output
publication, not a blanket rule excluding all ignored paths. Larger installs,
core-module rebuilds and future rebuild/read savings remain unmeasured; no such
feature was implemented.

Validation: locked arm64 build/no-run PASS; transport **2 PASS**; offline owner
mapping **1 PASS**; scoped all-target Clippy PASS; changed Rust formatting PASS;
core-tool tests **50 PASS**. The boundary guard reports the **same 57 upstream
violations**, compared after normalizing line numbers. Initial diagnostic-helper
compile errors and a missing overlay-directory failure are retained, followed by
corrected preparation and passing checks. No tests deleted. No FUSE changes,
content prefetch, recovery/replay, cache policy, Durable run or upstream-doc edits.
Source/binary identities, the measured trace patch and its subsequent
format-only difference are recorded; the daemon binaries are unchanged Phase 3.
See the [receipt index](receipts/run04/phase4/README.md) for exact commands,
limits, failures, cleanup and retained executable custody.

Production LOC: **106,285 → 106,288 (+3)**; implementation churn **+3/−0**,
plus **95 external diagnostic test lines**. The measurement/analysis scripts
reuse the Phase-3 topology: **165 added non-comment lines**, within the
approximately 200-line harness budget. The docs/receipt commit leaves production LOC unchanged. The cold-start
target and complete 20 ms cold timings remain unresolved; no speedup is claimed.

## Phase 5 results

**Neither variant qualifies as a correct cold-start solution.** The refreshed
index variant stopped at the requested all-fields-stable gate; minimal stat
checking removes the working-file rehash but misses the restored-mtime edit.
No production, protocol, FUSE, Git policy or index-rewriting change was made.
The numerical metadata-batching condition is reached under minimal checking,
but that variant fails a required correctness oracle: it was rejected rather
than tuned, and no batching was built on it.

### 1. Refreshed index: stat-stability gate

Mounted the same immutable Dubbo root simultaneously in two independent sandbox
containers, each with its own daemon, overlay and cache. Both used the same A
server, separate sandbox-private networks and the shared link. Compared `lstat`
for **all 4,846 tracked paths** before any refresh or file mutation.

| Field | Paths differing | `README.md`, B1 → B2 |
| --- | ---: | --- |
| `st_ino` | 0 | 20 → 20 |
| `st_dev` | **4,846** | **83 → 85** |
| uid / gid | 0 / 0 | 1000/1000 → 1000/1000 |
| `st_mtime_ns` | 0 | 1792484244627118447 → same |
| `st_ctime_ns` | 0 | 1792484244627118447 → same |
| Size, additional check | 0 | 8,526 → 8,526 |

`st_dev` is a mount-specific kernel device identity. Per the explicit instruction
“if something is unstable … stop that variant,” **no in-mount index refresh,
Commit of a refreshed base, or timed remount was attempted**. This is a failure
of the selected stability gate, **not proof that this Git build uses `st_dev`
to reject an index entry**; that policy question was not silently substituted
for the requested gate. Source supports the other observations:
`core/crates/layerfs-fuse/src/attributes.rs::Identity::inode` projects stable serials, and
`Identity::attributes` projects the configured uid/gid and portable mtime.

| Refreshed-index variant | 0 ms | 2 ms | 20 ms | Correctness oracles a / b / c |
| --- | --- | --- | --- | --- |
| Cold mount + status; requests; working files read | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN / NOT_RUN / NOT_RUN — stopped before refreshing |

Full per-path stat pairs and the teardown result are retained in
[stability receipts](receipts/run05/stability/results.jsonl.gz).

### 2. Imported index with `core.checkStat=minimal`

Only the Git command received `-c core.checkStat=minimal`; the imported index
and repository configuration were unchanged. All status commands also used
`--no-optional-locks`. Each sample started with a fresh B cache/overlay/mount and
an independent copy of the same sealed Disposable Store in A. The timed status
used narrow `strace` (`read,pread64,mmap`) to count actual file-content accesses;
this instrumentation is included in every sample. No pre-status tree walk or
refresh warmed the measured mount. Server opcode tracing was enabled only for
a separate attribution run, not for the timing cohort.

The attribution run used **4,055 status requests**: **2,772 metadata**, **1,247
file-length**, and **36 content**. Metadata and lengths are **99.1%** of requests.
Git read only **one working-tree file, `.gitignore` (687 bytes)**, plus its own
`.git` metadata and pack/index mappings. It did not rehash ordinary tracked
source files. The inode/uid/gid mismatch found in Phase 4 is thereby bypassed,
but that speed path is not correctness-qualified.

Three independent samples per RTT; seconds are median **[min–max]**, summing
mount and status command walls, including Docker-exec and narrow strace costs.
Request counts include mount. File counts exclude `.git/**` but include
`.gitignore`; no ordinary working source file was read.

| RTT | Cold mount + status | Store requests | Working files read | Oracles a / b / c |
| --- | ---: | ---: | ---: | --- |
| No added delay | 1.217 [1.217–1.258] s | 4,065 [4,064–4,066] | 1 [1–1] | FAIL / PASS / PASS |
| 2 ms | 9.641 [9.634–9.706] s | 4,063 [4,062–4,063] | 1 [1–1] | Same variant oracle results; target unmet |
| 20 ms | 83.370 [83.323–83.435] s | 4,063 [4,063–4,065] | 1 [1–1] | Same variant oracle results |

Oracles were separate, untimed, fresh-fixture checks at no added delay; their
results apply to the variant, not three repeated oracle campaigns per RTT.

| Oracle | Minimal-policy outcome | Independent evidence |
| --- | --- | --- |
| a. Change content, keep size, explicitly restore mtime | **FAIL: status returned clean** | README remained 8,526 bytes; mtime and ctime both remained 1792484244627118447 ns; SHA-256 and Git's forced blob hash changed |
| b. Server `fs.write`, then remount sandbox | **PASS: ` M README.md`** | Server write succeeded; remounted `cat` read the new text; forced hash differed from index |
| c. Ordinary in-mount edit | **PASS: ` M README.md`** | Same-size content edit advanced mtime/ctime; forced hash differed from index |

No adjustment was made after oracle (a) failed. In
`core/crates/layerfs-fuse/src/attributes.rs::Identity::attributes`, **ctime is projected from
mtime**. The oracle confirms that restoring mtime also restores the ctime seen
by Git. Thus the remaining stat fields cannot establish unchanged contents for
this case. This is a filesystem metadata limitation, not something metadata
batching can repair. The refreshed-index variant's oracle outcomes remain
unknown because its earlier stop gate fired; they are not inferred as passes.
[Oracle receipts](receipts/run05/oracles/results.jsonl),
[recomputed summary](receipts/run05/summary.json).

### Warm-base recommendation and remaining limits

**Keep Git's default stat policy and do not ship `core.checkStat=minimal` as a
warm-base optimization.** Do not rewrite index stat fields outside Git. This
phase does not qualify a refreshed index for cold remounts, so do not advertise
`git update-index --refresh` + Commit as eliminating cold rehash safely. A future
warm-base validation should first explicitly decide whether varying `st_dev` is
acceptable for the selected Git build and establish mutation-sensitive ctime
semantics; then prepare the index with Git inside the mount, Commit it, and pass
all three oracles after a fresh remount. Until then, retain the conservative
rehash cost. Reusing an active mount may amortize work, but it is not a cold-start
correctness result.

A second unresolved issue reappeared during the dual-sandbox stat check: B2's
normal unmount detached but returned **Retained / Join** after the existing 5 s,
with two receive loops entered and zero exited. The exact reply and executable
hashes are retained; no root cause is claimed. The harness removed its owned
containers after the refusal, without replaying unmount. B1's explicit unmount
was consequently not reached in that check. Subsequent single-B diagnostic,
oracle and timing unmounts succeeded. No teardown or FUSE fix was attempted in
this phase.

The retained Phase-4 executables were reused by hash; no Rust source changed or
Linux Rust build was needed. The owned tools image reused its cached arm64
ECR-base build layers. Only diagnostic scripts, receipts and this note changed.
All commands used explicit bounds (status 115 s, mount/unmount 25 s, seed test
120 s); no timeout was extended or failed operation replayed. Server/OS caches
were not dropped, so “cold” describes B's new application cache and kernel mount,
not a cold-storage claim. Netem/proxy calibration and one construction worker
were unchanged. These are diagnostics, not frozen-family benchmark admission.
Exact commands, identities, per-run accesses, measured RTT and cleanup are in
[the receipt index](receipts/run05/README.md). All owned containers, networks,
volumes and the temporary tools image were cleaned up. No push or upstream
contract-document edits; production LOC remains **106,288 (delta 0)**.

## Phase 6 results

**The revised gate qualifies a Git-refreshed base. Metadata batching reduces
cold mount + default-policy status at 2 ms RTT from 9.730 s to 1.037 s and from
about 4,063 Store calls to 53.** The ctime hole also exists in ordinary steady
state. It is unchanged. Retained-Join reproduces and remains unresolved at the
FUSE/kernel lifecycle boundary; it is not a Store-connection failure.

### Steady-state oracle and the container's Git

On the imported Dubbo root, ordinary `git status --short` **without**
`--no-optional-locks` refreshed and wrote the index. Then README.md was changed
without changing its size (8,526 bytes), and its mtime was explicitly restored.
Git 2.39.5, with default `core.checkStat`, reported **clean**: oracle a′ misses
this change. Both SHA-256 and Git's forced blob hash prove different content.

| README stat field | Before edit | After edit + mtime restore |
| --- | ---: | ---: |
| mtime ns | 1792484244627118447 | 1792484244627118447 |
| ctime ns | 1792484244627118447 | 1792484244627118447 |
| inode / uid / gid / size | 20 / 1000 / 1000 / 8526 | unchanged |

The source is `core/crates/layerfs-fuse/src/attributes.rs::Identity::attributes`:
it derives `time` from portable mtime and assigns it to both `mtime` and `ctime`.
Restoring mtime therefore restores the only change timestamp Git sees. This is
a LayerFS-wide steady-state metadata gap, not a cold-start regression.

The refreshed seed was prepared solely through Git: mount → `git update-index
--refresh` → Workspace Commit → consistent SQLite backup of the published
Disposable Store. An independent B2 mounted that root while B1 was still
mounted. README's saved index device was **83**, while B2 reported **86**;
inode 20, uid/gid 1000, size and nanosecond mtime/ctime matched. Default-policy
status returned clean and read only `.gitignore`, not README or other source
files. Thus this container's actual Git does **not** reject these entries for
the changed device identity. This is an observed behavior result, not a claim
about every Git build's `USE_STDEV` setting.

### Refreshed root before batching

Same Dubbo cb05763298f081ed17171d704408b6478cf8fd83, default Git policy; three
fresh B caches/overlays/mounts and independent A Store copies per RTT. Values
are medians **[min–max]**. Wall is mount plus status Docker-exec time, excluding
the intervening counter query. Narrow syscall tracing and server request
tracing are enabled in **both** timing arms. Daemons/Noise connections are
ready before mount timing. Server/host OS caches are uncontrolled; “cold” means
B's application cache and kernel mount. These are diagnostics, not a benchmark
qualification. Netem ping medians are 0.023 / 2.02 / 20.0 ms before, and
0.020 / 2.04 / 20.0 ms after; first-probe outliers remain in receipts.

| Added RTT | Mount + status seconds | Store requests | Request classes: metadata / lengths / content / other | Working files read | Oracles a / b / c |
| --- | ---: | ---: | --- | ---: | --- |
| 0 ms | 1.244 [1.192–1.295] | 4062 [4062–4063] | 2777 [2777–2778] / 1247 / 36 / 2 | 1 | matches a′ / PASS / PASS |
| 2 ms | 9.730 [9.614–9.748] | 4063 [4062–4063] | 2778 [2777–2778] / 1247 / 36 / 2 | 1 | same variant oracles |
| 20 ms | 83.414 [83.410–83.426] | 4062 [4062–4062] | 2777 / 1247 / 36 / 2 | 1 | same variant oracles |

“Other” is Snapshot + serial reservation. Working files exclude `.git/**`;
the single file is `.gitignore` in all 18 before/after samples. Ordinary source
files are not rehashed. Metadata plus lengths dominate (~99% of calls), so the
conditional batching gate is met. Oracles are separate fresh-fixture checks at
zero added delay, not repeated per timed sample: (a) misses the same-size,
restored-mtime edit exactly like a′; (b) detects server `fs.write` after remount,
with `cat` proving visibility; (c) detects an ordinary in-mount edit. Each edit
also has a forced-hash difference from the index. Qualification is relative to
steady state, **not native-filesystem ctime correctness**.

### Protocol change and refreshed root after batching

`layerfs-remote-store::metadata` adds a bounded metadata-wave operation to the
existing Noise Store family (opcode 8). After Snapshot pins an immutable root,
the client traverses canonical filesystem-root, inode and directory pages in
windows of **256 objects**, including corresponding regular-file lengths in
the replies. Existing Content decoders and Store ports supply the data; the
client verifies canonical object IDs. Attribute trees and symlink targets keep
their demand path; **no file payload is prefetched**. New opcode support is
required on both peers; older servers fail explicitly, without fallback/replay.

The traversal frontier is an indexed temporary SQLite table with disk-backed
temp storage, not a resident whole-tree list. Cache locks are released before
network I/O. A completed-root marker is recorded only after the frontier drains;
partial failure never marks it complete. No publication lane is held. The
existing cache remains nonauthoritative and has no eviction. Explicit opcode
mutation classification keeps a failed metadata read from being labeled Unknown.
No daemon, FUSE, local Store or Docker backend code changed.

| Added RTT | Mount + status seconds | Store requests | Request classes: metadata waves / separate lengths / content / other | Working files read | Oracles a / b / c |
| --- | ---: | ---: | --- | ---: | --- |
| 0 ms | 0.937 [0.877–0.939] | 53 [53–53] | 15 / 0 / 36 / 2 | 1 | matches a′ / PASS / PASS |
| 2 ms | **1.037 [1.036–1.042]** | 53 [53–53] | 15 / 0 / 36 / 2 | 1 | same variant oracles |
| 20 ms | 2.086 [1.985–2.087] | 53 [53–53] | 15 / 0 / 36 / 2 | 1 | same variant oracles |

This deliberately moves work into mount: mount-only medians at 0/2/20 ms grow
from 0.041/0.056/0.200 s to 0.190/0.235/0.627 s. Whole-generation metadata
acquisition is proportional to namespace size even if a caller accesses one
file; this tradeoff is justified for the selected whole-tree status workload,
not yet qualified for enormous or sparsely accessed namespaces. Live testing
verified **2,790 cached metadata objects, 4,725 file lengths, no cached payload**,
and a second Snapshot of the same root used just one request. Framing/corrupt-ID
tests, Clippy and formatting pass. The product-boundary guard still reports
57 violations on unchanged upstream files; it is not green. Its 50 tool tests
pass. Exact commands and limits are in the [receipt index](receipts/run06/phase6/README.md).

### Retained-Join: reproduced, not repaired

Two dual-B checks reproduce the refusal. In the dedicated check, B2 detached
but returned **Retained / Join** after the unchanged 5 s; B1 then unmounted
successfully. B2's two `fuser` threads remained blocked in `fuse_dev_do_read`
(`read` syscall on `/dev/fuse`, fd 17). Per-thread and host mountinfo scans found
no remaining B2 mount; a host FD/cwd/root scan found no visible mount pin.
Connection 84 matched B2's device 0:84; fusectl reported zero waiting requests.
A single, explicitly targeted **cleanup-only** abort of connection 84 released
both receivers and the mount/fence owners within two seconds, leaving only the
daemon main thread. This did not retry unmount or relabel its refusal as success.

The wait chain is `layerfs-daemon/src/control/detach.rs::Service::unmount_kernel`
→ `layerfs-fuse/src/session/drain.rs::KernelSession::detach` /
`KernelSession::quiesce`. `mount/syscalls.rs::detach` calls `umount2`; the
subsequent `queue.stop_receive()` fences admission but cannot wake an already
blocked read. In `core/vendor/fuser-0.18.0/src/channel.rs::Channel::receive`
and `session.rs::SessionEventLoop::event_loop_started`, receive-loop exit still
depends on the kernel returning Destroy/ENODEV/error. **The established defect
is the teardown dependency on detach waking those receivers; it did not.**
Why this OrbStack kernel retained the detached connection is still unproven;
the scans rule out visible pins, not all kernel references. A robust fix needs
an explicit cancellable receive/connection-termination protocol with exact
active-request drain and custody proof. That is a FUSE lifecycle change, not a
small Store protocol hook, and is outside this phase's permitted FUSE changes.
No deadline extension, dropped Join, failed-operation replay or teardown patch.

### Warm-base recommendation

Prepare a warm base with **default Git settings**: perform source setup, mount
it, run Git's own `git update-index --refresh`, Commit the Workspace including
`.git/index`, and validate one fresh mount with the intended Git build. Keep
that refreshed root as the base. There is no need for `core.checkStat=minimal`
or external index rewriting. With metadata batching this workload meets the
2 ms target while preserving ordinary and server-edit detection. This replaces
Phase 5's overly strict device-stability gate; it does not fix the inherited
ctime hole or imply that every Git build ignores `st_dev`.

### Draft upstream issue text — not filed

**Title: FUSE ctime mirrors mtime and permits missed same-size changes after
Git refresh.** On a normal LayerFS mount, run ordinary `git status` to refresh
the index, change a tracked file without changing its size, restore its old
mtime with `utime`, and run default-policy status again. Content hashes differ
but status reports clean because `Identity::attributes` returns the restored
mtime as ctime (both 1792484244627118447 ns in this receipt). This affects warm
mounts as well as refreshed cold bases. LayerFS should provide mutation-sensitive
ctime semantics across writes, metadata changes, Commit/install and remount,
with explicit persistence/identity rules; changing Git policy is not a fix.
A future upstream fix needs this reproduction plus timestamp/identity and
server-install regression proofs. No ctime change is included here.

Implementation commit: `6cc16e913` — bounded immutable metadata batches.
Production LOC is **106,288 → 106,523 (+235)**; raw product diff +246/−6,
external tests +118 lines. Only the remote-store crate changes. All owned
containers, networks, volumes and the temporary tools image were removed;
executable hashes and raw receipts remain under the authorized directories.
No push, upstream issue/PR, upstream contract edit or Durable execution.

## Phase 7 results

Status: Local OrbStack lifecycle diagnostic; not universal kernel or performance
qualification. Everything ran on this Mac, with `cx7-` Docker resource names.
The ignore worktree's harness and ignore01/ignore02 receipts were read only.
No ignore, ctime, metadata-batching or Store-protocol code changed.

### Before/after rate and evidence

The identical harness initializes each cycle from an independent copy of the
same 3,003-file Disposable Store seed, starts fresh A/B containers and a fresh
B cache/overlay, mounts, writes two small files, runs `git init`, `git add -A`,
`git commit`, performs LayerFS Commit, then makes **one** normal unmount attempt.
A/B have private networks plus one shared link; B has no Store path or volume.
Each arm selects 40 Git cycles plus one plain-write control (same small writes,
no Git). Git identity/config and the 3,003-file seed match the prior ignore-off
reproduction's essential shape. No timeout or workload was tuned between arms.
Both arms trace `umount2` with the same seccomp-filtered strace. These are failure
rates under this diagnostic workload, not independent statistical qualification.

| Shape | Before, `6394865a4` | After, `524862598` |
| --- | --- | --- |
| Git init/add/commit → LayerFS Commit → unmount | **28/40 Retained(Join), 70%**; 12 clean | **0/40 Retained(Join), 0%**; 40 clean |
| Plain writes → Commit → unmount | **0/1 Retained**, clean | **0/1 Retained**, clean |
| Deliberately held file across unmount | Not selected | **Refused(Busy), `EBUSY`**, mount and open file preserved; not a post-detach Retained |

Every before failure is retained under
[run07/cycles-before](receipts/run07/cycles-before/), including both fuser kernel
stacks, exact connection's fusectl `waiting`, task-visible host namespace
mountinfo, all sandbox processes' fd links/fdinfo/cwds/roots, and syscall trace.
All 28 show **`umount2("/workspaces/1", 0) = 0`**, two readers blocked in
`fuse_dev_do_read`, **waiting=0**, no remaining `fuse layerfs` mount in the
captured namespaces, and no sandbox fd/cwd/root in the former mount. No Git
process, automatic GC or fsmonitor survived in those snapshots. Successes also
retain the original unmount reply, flags and post-unmount thread inventory.
The one plain-write control is insufficient to prove that Git is necessary;
it only establishes that this simpler selected control succeeds.

A preflight configuration error (DNS name where the client requires a numeric
socket address) occurred **before mount**. Its command/error/proc receipts are
preserved separately; it is not a discarded unmount sample. The corrected
harness is identical in the two 40-cycle cohorts. The candidate's first build
failed because `PollFlags` has no `Default`; the compiler output and exact
candidate patch are preserved. Explicit empty flags fixed that compilation
error. No runtime failure was replayed or replaced by a clean sample.

### Cause: proven wait dependency, kernel trigger still unproven

Normal detach is **not lazy**: `layerfs-fuse/src/mount/syscalls.rs::detach`
passes empty flags to `umount2`, confirmed by every actual trace. A held mount
reference therefore has the kernel's reversible `EBUSY` path; there is no
`MNT_DETACH` hiding a Git descendant or open file in these failures.

`layerfs-fuse/src/session/drain.rs::KernelSession::detach` marks known detach
and calls `MountRequests::stop_receive`. That is a userspace admission fence;
it does not wake a read already sleeping in the kernel. In the old
`core/vendor/fuser-0.18.0/src/channel.rs::Channel::receive`, the receiver is in
blocking `read(/dev/fuse)`. `session.rs::SessionEventLoop::event_loop_started`
can leave only after receiving Destroy or a terminal read result. Meanwhile
`KernelSession::quiesce` waits for `SessionRunner::run` to consume every join.
The same session/notifier still owns the device while those joins wait.
Thus known namespace detach does not supply the receive-stop event that the
userspace lifecycle requires. The stacks plus zero active/retained request
counts prove the failure is idle receive exit, not an unfinished callback.

The reference Linux read implementation waits while connected with no request;
nonblocking mode returns EAGAIN instead. See
[Linux v6.1 `fuse_dev_do_read`](https://github.com/torvalds/linux/blob/v6.1/fs/fuse/dev.c)
and [last-superblock connection destruction](https://github.com/torvalds/linux/blob/v6.1/fs/fuse/inode.c).
This explains the observed wait dependency, but **is not an exact source match**
for this Mac's **7.2.9-orbstack-00391-g2b298d05fbd4** kernel. Why that kernel
does not finish connection shutdown/wake these readers after successful detach
is still unproven.
The proc scans exclude observed userspace holders, not every possible internal
superblock reference or a namespace with no observable task. No kernel leak,
lost wakeup or Git process is asserted as the unobserved trigger.

### Fix and custody argument

Implemented option **(b), cancellable receive**, within the authorized scoped
fuser lifecycle patch; option (a) had no evidenced process holder to fix.
`session/receive_stop.rs::ReceiveStop` owns a nonblocking close-on-exec pipe.
Receivers poll the device and the pipe. `SessionMonitor::stop_receivers` closes
the sole writer, producing a persistent HUP visible to **every** receiver;
no receiver consumes the notification. The device is also nonblocking: if two
receivers observe readiness and one consumes the request, the other returns
to poll on EAGAIN instead of becoming stuck in read again. No new unsafe code,
dependency or version change. The old blocking Session route and non-Linux
behavior are preserved; the explicit Linux SessionRunner uses cancellation.

For normal unmount, `KernelSession::quiesce` signals only **after known detach
and active-request quiescence**. A request already read still dispatches and
retains its original disposition. All original receiver joins, owner/watcher
joins, the final active/retained request check, namespace revocation and backing
cleanup remain mandatory. Signal delivery is never substituted for a Join.
The existing forced path also reaches this shared barrier only after its own
known abort; this phase neither invokes nor adds that abort. No normal-path
fusectl write, no deadline extension, no dropped handle and no replay.

The change costs one pipe per session and two poll entries per receiver,
independent of namespace size; it adds poll work to receives, whose throughput
cost was not measured here. Startup pipe/fcntl failure remains an original
startup error with the existing partial-startup join/custody machinery.
Original timestamp/lifecycle/buffer provenance is unchanged. The additional
[patch record](fuser-receive-stop/provenance.json) is separately pinned and
verified by the extended integrity guard, with tamper/missing-file tests.

### Verification and limits

Locked Linux arm64 binaries and `--no-run` builds pass. Eight Fuse tests
(including active-request wake/drain), two daemon backing/custody tests, Fuse
and fuser Clippy, formatting, vendor integrity, and 51 guard tool tests pass.
The product boundary guard still **fails with the identical 57 upstream
findings**; it is not green. The exact commands, bounds, source/executable seals,
all failed attempts and cleanup are in the [receipt index](receipts/run07/README.md).
The scoped source commit is `524862598`; the after cohort uses one immutable
binary set from its exact tree throughout. Its launcher recorded the parent
HEAD just before the local commit completed; the precomputed staged tree equals
the committed tree, and no product bytes changed during sampling.

The held-file oracle returned `Refused(Busy)` at `unmount:kernel` with “kernel
reported the mount busy; no terminal effect”; traced `umount2(..., 0)` returned
`EBUSY`. The daemon reported 526,667 ns for that operation. The holder still had
`/workspaces/1/local` open, the mount remained in mountinfo, and both receivers
were still polling (kernel `__arm64_sys_ppoll`, two entries). This is a prompt,
safe refusal with custody preserved, **but differs from the requested literal
Retained variant**: the existing contract uses reversible Busy before detach,
and Retained after an unestablished terminal effect. No response was relabeled
or policy changed to manufacture that expected variant. The retained held-case
receipt proves the cancellation hook was not used to force a busy mount through.
All 40 candidate successes have no remaining fuser/mount-owner/fence thread.

The rate comparison establishes this harness's observed improvement, not a
zero probability of future refusal. Unproven: the kernel's underlying delayed
connection destruction, inactive namespaces invisible to proc enumeration,
other kernels/platforms, cloned-device configurations, injected startup failures,
forced teardown integration, and receive-throughput impact. Exact retained
custody remains the outcome for any future unestablished drain. No new
recovery, replay, ignore, ctime, GC or Durable behavior was built.

Production LOC: **106,523 → 106,524 (+1)** in the repository's first-party
counter scope; separately audited vendor runtime files **770 → 880 (+110)**,
so **+111 net runtime lines** for the phase's change budget. The vendor subtotal
covers only the three changed files, not the whole dependency. The docs/harness
commit has production delta 0. All owned containers, networks, seed/data volumes and the `cx7-tools` image
were removed. The sole retained Docker resource is **`cx7-target`**, the Cargo
cache/target volume permitted by the task. Binary copies and their hashes remain
under `target/cx7/bin-before` and `target/cx7/bin-after`; receipts remain in
`docs/mp2/receipts/run07/`. No other container, image or volume was changed.

## Phase 8 results

Status: local OrbStack diagnostics on Linux arm64 7.2.9, Git 2.39.5. Original
arms are the retained binaries for `6394865a4` and `524862598`; only the daemon
varies, with the same 524 Store server/CLI, fixture and harness. Source and binary
seals, full commands, every failure and cache policy are in the
[run08 receipt index](receipts/run08/README.md). No SSH or real environments.
Other jobs' CPU/OS-cache effects are uncontrolled. Stores are Disposable;
construction workers=1. No ignored-path, warm-up, ownership or ctime change.

### 1. Warm receive-path cost

Dubbo is pinned at `cb05763298f081ed17171d704408b6478cf8fd83`, 4,846 tracked
files. Each already-mounted sample has explicit untimed preparation; Store
objects and metadata are warm. Read samples evict only the FUSE file data pages
so they still exercise receives. **Every valid timed sample has zero Store
requests**. Ten samples per arm/case, alternating AB/BA, no outliers discarded.
Times below are seconds, **median [min–max]**. “Fixed” is `c73497e2c`, measured in
a second prospectively selected matched cohort; its own baseline is shown,
not substituted into the original comparison.

| Workload | Parent, original cohort | 524 patch | Delta | Parent, correction cohort | Fixed | Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hot status ×20 | 4.4230 [4.2696–4.6476] | 4.1634 [4.0271–4.2376] | -5.87% | 4.4292 [4.3111–4.6398] | 4.1459 [3.9935–4.2526] | -6.40% |
| find/count | 0.1636 [0.1483–0.2193] | 0.1694 [0.1608–0.1883] | +3.56% | 0.1742 [0.1585–0.2377] | 0.1554 [0.1437–0.1876] | -10.74% |
| stat every file | 0.0453 [0.0426–0.0525] | 0.0576 [0.0530–0.0653] | +27.15% | 0.0453 [0.0432–0.1472] | 0.0412 [0.0382–0.0427] | -8.90% |
| Read 5,000 ×1 KiB | 0.2515 [0.2244–0.3909] | 0.2561 [0.2435–0.2914] | +1.84% | 0.2311 [0.2180–0.2753] | 0.2230 [0.2167–0.2907] | -3.49% |
| Read 256 MiB | 0.5359 [0.5214–0.6676] | 0.5269 [0.5090–0.6280] | -1.68% | 0.5377 [0.5185–0.6913] | 0.5262 [0.5091–0.6583] | -2.15% |

Status means 20 sequential `git --no-optional-locks status --short` calls;
find/stat cover 4,869 regular files, including Git internals. FUSE completed
requests per sample are approximately 263,148 for status, exactly 14,900 for
find, normally 4,869 for stat, 20,000 for small reads and 2,690–2,691 for sequential
read. Correction-cohort baseline stat sample 1 made 11,227 requests and took 147.23 ms;
it remains in the 10-run median/spread. Extra opcode identities were not captured.
The 60 s entry TTL (`request/reply.rs::TTL`) can add revalidation despite warm Store
objects; that explanation is inferred. Strict equal-request-rate
qualification for this cohort is **INCOMPLETE**. Every original corrected stat sample made exactly 4,869 requests.
Optional commons-lang Maven compile is **NOT_RUN**: no local source checkout
and only a partial Maven cache, so it was not cheap to set up offline.

The initial stat command used an empty printf format and did not perform per-file stat
work: 19 samples issued zero FUSE requests and one issued 60. All 20 results remain in `hot/`, marked INELIGIBLE. Only stat was
corrected (`--cached=never --printf=%s\n`) and rerun in `hot-stat/`; its **27.15%**
regression is the failing-first result. The other four original workloads have
no >5% median regression. The full corrected cohort has none either.

Mechanism: Phase 7's `session/receive_stop.rs::ReceiveStop::receive` rebuilt a
two-descriptor ppoll wait on every receive, with nonexclusive device wakeups.
A separate count-only trace for 4,869 stat requests shows **4,869 reads** at the
parent, versus **5,586 ppolls +5,586 reads, 717 EAGAIN** at 524. The small repair
registers one epoll instance per receiver once in `ReceiveStop::prepare`, with
exclusive device readiness and **nonexclusive stop-pipe readiness**. Corrected
trace: **5,045 epoll waits +5,045 reads, 176 EAGAIN**. This reduces raced reads
and per-wait registration work; it does not eliminate races or the wait syscall.
Tracing is separate from timing; its idle-inclusive durations are not compared.
The observed faster medians are local diagnostics, not a universal speed claim.

`ReceiveWait::receive` still uses a nonblocking device, prioritizes persistent
pipe HUP, and dispatches any frame already read. Closing the sole pipe writer
wakes every receiver, including one not yet waiting. Known detach and active
request quiescence remain prerequisites to signaling; every original Join,
final request proof and namespace/backing release remains mandatory. No abort,
timeout extension, dropped Join or replay. The existing nix dependency only
enables its event feature. [Additional provenance](fuser-receive-exclusive/README.md)
pins the exact delta without modifying Phase 7's record.

Custody revalidation uses the unchanged Phase 7 cycle harness except its receipt
root: **0/40 Retained(Join), 40 clean Git cycles**, plus **0/1 Retained** for plain
writes. Phase 7's accepted result was also 0/40 after its original fix; the older
28/40 failure receipts remain unchanged. Every normal syscall is `umount2(...,0)`
returning 0, including nine split strace entries correlated by TID. Post-unmount
inventories show no fuser/mount/fence threads; the daemon service main thread is
expected to remain. A deliberately held file returns **Busy/EBUSY in 0.482 ms**;
the file fd and mount remain, with both receivers in epoll wait. It is neither
forced success nor a Join bypass. Native failures would retain the same full
proc/namespace evidence; the held-case evidence is retained. These are diagnostic
rates, not universal kernel qualification.

### 2. Metadata warm-up versus namespace size

Both published roots have an index refreshed by Git inside a mount and then
LayerFS-committed. The larger adds an ignored synthetic node_modules with
**30,000 files, 211,730,666 bytes and 9,470 directories**, retaining Phase 4's
real-derived names, sizes, depths and duplicate groups. Payloads are synthetic;
this is a namespace diagnostic, not a real package installation. One selected
sample per cell, **original 524 binary**; fresh B object cache/overlay, unchanged
host/server OS cache. Times include Docker exec/CLI overhead. A cache-count
query between mount/status inspects metadata already populated by mount.

| Added delay | Root | Mount s | Mount Store requests | Cached metadata objects | Cached file lengths | First status s | Status Store requests |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 ms | Dubbo | 0.187 | 17 | 2,783 | 4,721 | 0.469 | 28 |
| 0 ms | +node_modules | 1.104 | 57 | 13,092 | 32,060 | 0.507 | 29 |
| 2 ms | Dubbo | 0.254 | 17 | 2,783 | 4,721 | 0.592 | 28 |
| 2 ms | +node_modules | 1.228 | 57 | 13,092 | 32,060 | 0.615 | 29 |
| 20 ms | Dubbo | 0.838 | 17 | 2,783 | 4,721 | 1.185 | 28 |
| 20 ms | +node_modules | 2.534 | 57 | 13,092 | 32,060 | 1.332 | 29 |

The configured 0/2/20 ms netem delays are not exact end-to-end RTTs. Five ping
probes per cell measured plain/large averages **0.302/0.100**, **5.168/4.673**,
**30.615/29.178 ms**, with substantial scheduler jitter; raw min/max remain in
receipts. No replacements or retuning. Both first statuses were clean in all
conditions. Cached canonical metadata bodies are 950,981 versus 5,604,292 bytes.

Adding the ignored tree costs **10,309 metadata objects and 40 mount requests**;
extra mount wall time is **0.92/0.97/1.70 s** across these scenarios, while status
adds only **0.04/0.02/0.15 s**. Skipping initial warm-up of `node_modules/`, including
its `.bun` package directories, would therefore matter more at mount than at
status. This is an opportunity, not a measured implementation saving:
`metadata.rs::expand` currently traverses a global inode table, requests lengths
for all regular inodes and queues every directory. Merely skipping directory
pages would still pay that global scan; a selective policy would need to defer
unvisited inode/length work while preserving later demand reads. `.git/` and
tracked source remain useful for status. **No warm-up change was made.**

### 3. Ownership-preserving copies

Every destination inode reports configured owner/group **1000:1000**, including
root-created files. Source fixtures contain two files and a nested directory,
owned wholly by 0:0 or 1000:1000. All 12 runs retain syscall traces, stderr and
content/mode/ownership readbacks. The table gives tool exit and preservation
outcome; EPERM is errno 1.

| Source owner | Caller | `cp -a` | `tar -xpf` | `rsync -a` |
| --- | --- | --- | --- | --- |
| 0:0 | root | Exit **1**, `fchown(fd,0,0)` and fallback `fchown(fd,-1,0)` → EPERM; preservation warning | Exit **2**, `fchown(fd,0,0)` → EPERM; cannot change ownership | Exit **23**, `fchownat(AT_FDCWD,".",0,0,AT_SYMLINK_NOFOLLOW)` (also files) → EPERM; partial-transfer warning |
| 0:0 | uid1000 | Exit **0**, the same chowns fail EPERM but are tolerated; owner is not preserved | Exit **0**, no failed ownership syscall; owner restoration skipped | Exit **0**, no failed ownership syscall; owner restoration skipped |
| 1000:1000 | root | Exit **0**, bytes/owner preserved | Exit **0**, bytes/owner preserved | Exit **0**, bytes/owner preserved |
| 1000:1000 | uid1000 | Exit **0**, bytes/owner preserved | Exit **0**, bytes/owner preserved | Exit **0**, bytes/owner preserved |

The proposed minimum “same configured owner as a no-op” **already exists** in
`layerfs-fuse/src/operations/unsupported.rs::ownership`, called by
`operations/write.rs::set_attributes`. A direct `chown(1000,1000)` passes;
`chown(0,0)` returns EPERM. Other ownership is not stored. Kernel permission
checks may reject an unprivileged caller before this adapter; the traces prove
the syscall result, not where every individual rejection occurred.

Smallest honest semantics are to retain that rule and select copy options that
do not request unsupported ownership: `cp -a --no-preserve=ownership`,
`tar --no-same-owner -xpf`, or `rsync -a --no-owner --no-group` (proposals, not
additional tested cases). Silently accepting root ownership as an alias would
make successful chown disagree with subsequent stat. True arbitrary ownership
would require persistent inode ownership and permission semantics, beyond this
prototype. A successful unprivileged copy alone is not a preservation oracle.
No ownership implementation was changed.

### 4. ctime gap, status only

One oracle a′ on **524862598**, imported index and default Git stat policy:
ordinary status first refreshed/wrote the index, then README.md was changed
without changing its size and its mtime was explicitly restored.

| Observation | Before edit | After edit + mtime restore |
| --- | --- | --- |
| Size | 8,526 bytes | 8,526 bytes |
| Reported mtime ns | 1792516007467733512 | 1792516007467733512 |
| Reported ctime ns | 1792516007467733512 | 1792516007467733512 |
| Git content object | `c2fa196a54c94f244d60854a1b3817b44a98e5fe` (index) | `868cff4e1fd79b42d5338a4740621d4d3e0d57e2` (forced hash) |
| Git status | Clean after refresh | **Clean despite changed content: detection FAIL, unchanged gap** |

`layerfs-fuse/src/attributes.rs::Identity::attributes` assigns `ctime` from the
same `ViewStat` modified time used for mtime. Thus restoring mtime also restores
reported ctime. Full SHA-256 byte hashes and Git hashes are in `ctime/`; the
Phase 6 draft issue remains the proposal. No ctime fix or issue was made.

### Verification, size and remaining limits

Locked build/`--no-run`, 8 Fuse tests, 2 daemon custody tests, scoped Clippy and
formatting, vendor integrity and 52 guard tests pass. All actual tests have
explicit <=120 s child bounds. A duplicate Clippy flag was rejected and corrected;
its receipt is retained. Workspace formatting and the boundary guard still fail
on unchanged paths (57 boundary findings), independently checked against Phase 7.
The [receipt index](receipts/run08/README.md) lists exact commands, skipped Maven,
invalid stat cohort, expected ownership failures and ctime failure. No test was
deleted, no receipt replaced, and no failed operation replayed.

Commit **`c73497e2c`** corrects receive wait registration. First-party Production
LOC **106,524 →106,524 (delta 0)**; separately counted vendor runtime **880→890
(+10)** in three files (raw runtime diff +43/−30). Existing nix event feature only.
The documentation/test commit has production delta 0. Exact counter/scope and
snapshot proofs are in `setup/fix-production-loc.json`; reference remains absent
(retired R9c, last 65,417). No content prefetch, ignore, ownership, ctime, recovery,
eviction or Durable behavior was built. Exact OrbStack kernel shutdown trigger,
other kernels, precise 2/20 ms end-to-end timing and Maven cost remain unqualified.
Cleanup leaves only the permitted **cx7-target** Cargo volume; no other job's
containers, images, networks or volumes were touched.

## Phase 9: reopening lost connections

A trial on cloud sandboxes, with the Store on one machine and the daemon on
another, ran the Store protocol over a WebSocket byte pipe (the sandboxes have no
raw TCP between them). Mount, fork, edit loops and a replacement machine worked.
Two lifecycle events broke the channels for good, because a failed channel was
quarantined and never reopened:

- **Pause and resume.** The old connection still looked open but carried
  nothing; the next request timed out and the Commit failed.
- **Idle.** The exposure closed both connections after 300 s without traffic;
  afterwards an uncached read returned EIO and the Commit failed.

Now a lost connection is dropped and the next request on that channel opens a
new one (`layerfs-remote-store/src/client.rs`).

- **Requests other than Commit are sent once more** on the new connection.
  - Reads and presence checks change nothing.
  - Uploads are content-addressed, and the Save reuses an object it already
    stores.
  - A serial range whose answer was lost stays consumed, as unused ranges
    already do.
- **A Commit is never resent.** A lost Commit answer stays unknown and keeps
  the existing custody.
- **An idle channel is probed before a Commit.** When the write channel has had
  no answer for over a second, an empty presence check runs first. A connection
  cut while idle is therefore found and replaced by a resendable request, not by
  the Commit.
- **The server closes a connection that sends nothing for 15 minutes.** A client
  that vanished without closing, such as a paused or deleted machine, frees its
  slot; a live client reopens on its next request.

No heartbeat was added: reopening on demand covers both events. After a pause,
the first request still waits for the ten-second deadline before it reopens.

Three unit tests drive a fake Store over real Noise channels:
- a lost read is resent on a new connection;
- a lost Commit opens no new connection and returns unknown;
- an idle Commit replaces a cut connection through the probe.

`cargo test --locked -p layerfs-remote-store` passes on Linux with Rust 1.85.1,
including the two existing transport tests. On macOS those two existing tests fail
before and after this change. An accepted socket there inherits the listener's
non-blocking flag, so the tests are Linux-only as written.

The pause and idle cases have not been rerun on the sandboxes with this change.
