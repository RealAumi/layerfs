# Git-ignored paths stay local

> **Status: Proposal; target mp2 fork; not a released contract.**
> Source: `cfbd865f5cdfea5c52b36bcc89ac4273ce9cf5ee`, 2026-10-20.
> Read-only source audit; no builds, runtime checks or new measurements.

**The intended behavior fits, but a capture filter alone does not.** Install
retires an entire captured generation, including anything construction skipped.
The smallest design satisfying repeated Commit, concurrent writes and bounded
retention adds indexed local ownership inside the existing Overlay database.
FUSE routing and the canonical Store format stay unchanged. This is a substantial
Overlay change, not a small matcher patch.

This explicitly opts out of the upstream complete-state policy. Project Init's
`layerfs-project/src/import/scan.rs` enumerates every child through `fs::read_dir`:
ignored output already imported into the base remains versioned. The supplied
8 s dubbo Commit and 1–11% build overhead motivate the work; neither was verified
here. “Never committed” below means excluded **new bindings**, not already
versioned content or bytes shared with a versioned hard link.

## 1. Capture and the projected namespace

Paths abbreviated below are under `core/crates/`: **W** = `layerfs-workspace/`,
**O** = `layerfs-overlay/`, **S** = `layerfs-store-service/`, **D** =
`layerfs-daemon/`, **B** = `layerfs-bridge/`. These are file references, not a
proposed directory layout.

`O/src/lifetime/generation.rs::Overlay::capture` freezes `active`, advances it,
and resets raw dirty counters. `CapturedReader` pins the root and installed
floor. `reader_inodes` / `reader_directory_entries` in
`O/src/lifetime/captured_reader.rs` enumerate indexed generation pages.
`S/src/store/captured.rs::BoundWorkspace::construct_captured` passes them to
`W/src/construction/driver.rs::CapturedNamespace`.

Introduce a proposed `CaptureProjection` **before** `namespace/normalize.rs`
calls `names` and `values`. Its indexed membership must govern both those passes
and `namespace/cursor.rs::Cursor`'s sequential **and point** name reads. Otherwise
headers/counts disagree, an excluded directory remains in its parent's entries,
or `Builder::value` constructs orphaned file objects before pruning. Filter before
digest recording, file construction and any `FinalizedConsumer::accept`.
Recompute projected links, directory membership/counts and dense fresh ranks;
retain different live metadata locally. Preserve explicit metadata edits on base
directories, but exclude membership/link-count effects caused solely by local
children, so ignored-only work does not manufacture a changed root.

| Case | Proposed rule |
| --- | --- |
| Base path, including replacement or deletion | Always versioned. Test the captured **base path**, not `DirectoryEntry::inherited` (which can mean a lower overlay binding). |
| New ignored directory | Omit its parent binding and all excluded descendants. A matching directory already in the base stays; test each new child separately, retaining base descendants and their deletions. |
| Hard links | Filter names, not serials. Any surviving versioned alias requires the shared inode/content; writes through an ignored alias therefore can be committed. Canonical link counts count included aliases; live counts include local aliases. No inode cloning or changed POSIX semantics. |
| Rename into ignored destination | If destination is absent from base, retain it locally; publish deletion of any base source. Replacing a base destination remains versioned. A moved base directory may require local references to its old immutable subtree. |
| Rename out / rule removal | Newly included binding promotes its retained content, including unchanged descendants. Do not rely only on that generation's dirty-inode pages. |

## 2. Installation, dirt and collision ownership

`W/src/workspace/install.rs::prepare_base_install` checks/rebinds the root;
`S/src/overlay/lifetime_operations.rs::install_prepared` waits for base readers;
`Workspace::install_prepared_base` pairs the binding swap with `Overlay::install`.
The latter sets `installed = capture.generation` and enqueues `RETIRE`.
`O/src/database/statements.rs` and `payload/layers.rs::layers` read above that
floor; `maintenance/garbage.rs::retire_generation` deletes old names/data/inodes.
Post-capture active rows survive, but can still depend on skipped older payload.
Keeping a reader merely delays deletion; it does not restore live visibility.
`namespace/inode.rs::keep_live_row` only carries metadata whose bytes will be in
the new base; it is insufficient here.

**Proposed local-retention ownership:** an indexed, versioned selection of name,
inode and payload-layer references in the same Overlay file. Prepare it against
the sealed capture, then activate it atomically with install, before retirement.
Live precedence is later active changes → captured changes → retained local
state → installed base. Preserve newer whiteouts, truncation and payload masks;
never overwrite post-capture rows with retained snapshots. Readers pin the exact
local selection too. Extend existing bounded composition/reclamation to release
superseded local versions; do not pin a complete generation per Commit or copy
payload wholesale. Unknown publication keeps original custody; definite failure
discards only prepared selection metadata through the existing failure path.

This also needs explicit “has committed backing” identity. `born > installed`
in `CapturedReader::created_above`, `SourceView::inherits`, mutation evaluation
and `CapturedFileEdits` stops identifying new files once a local-only inode
survives install. Do not fix this by changing its stable serial or pretending it
exists in the new base. Retained immutable references preserve bytes when a
versioned source was moved into a local path.

`S/src/store/commit.rs::commit_admitted` currently gates its fast UpToDate path on
raw `WorkspaceState::dirty_inodes` / `dirty_directory_entries`, then checks the
head. Add projection classification before Save: empty versioned change set plus
unchanged head and no `PendingMerge` returns UpToDate after local retention is
settled. Only local mutations are reclassified; unchanged local state is not
reconstructed each Commit. Cache classification by exact revision/base/rule
identity; rule or ancestor-rename changes invalidate affected local subtrees.
Raw counters may remain nonzero and must not be advertised as committable dirt.

`D/src/control/status.rs` currently reports those raw counters; retain their
meaning. `D/src/operator/workspace.rs::{scan,changes,overlay}` compares the live
tree to the base and currently reports ignored paths as ordinary Added/Modified.
Add `localOnly` and `shadowsBase` classifications plus separate committable/local
counts there, and label local loss in `control/dirty.rs` unmount reporting. Keep
raw resource accounting. `sdk/js/operator/index.js` forwards these values, so
this needs no JS implementation change. Current diagnostics walk both trees;
pagination alone does not make that scan cheap.

For a moved head, existing `commit.rs` installs the merged/conflict root and
retains `PendingMerge`; retain local state over that exact returned root too.
**Collision rule:** a previously local binding shadows a newly installed base
binding, including file/directory type collisions, and reports `shadowsBase`.
This is an explicit exception to “base wins”: the server binding remains in the
projection, the shadow never silently becomes versioned on the next Commit.
Keep it local until the user removes/renames it; removing it reveals the base
instead of publishing a deletion. Block promotion over a collision even if rules
change. Reconcile changed ancestor identities by path, not stale parent serial;
report the highest shadowed ancestor. Preserve the existing
`D/src/control/invalidate.rs` → `stale_after_install` coherence path. These cases
need mounted proof, especially retained descriptors and merged ancestors.

The smaller alternative is selective carry-forward using
`O/src/lifetime/composition.rs`'s failed-capture folding machinery before install.
It still needs name/payload preservation, freshness fixes and projection dirt;
it visits retained rows repeatedly and may merge payload cells. It cannot offer
“unchanged local state is not recaptured” and could merely replace the 8 s cost
with local copying. It is not the recommended implementation.

## 3. Rules, activation and remote boundary

Read rule bytes through a new captured-view adapter over `CapturedReader`,
`OverlayCapturedNamespace`, `read_captured` and `BaseView`/`FileView`, never by
opening the live FUSE mount. Load `.git/info/exclude` and ancestor `.gitignore`
files from the **same sealed view** as the changes; later rule writes apply next
time. Resolve paths with paged captured-name/base lookup. `BaseView::child` and
`inode` give indexed base membership without payload reads, once the path is
known. Dirty pages contain parent/serials, not full paths: initial base ancestor
discovery can require a tree walk (`D/src/control/dirty.rs` uses `compare::locate`).
Use backed path/parent records; do not claim constant-cost classification.

Choose `ignore::gitignore::{GitignoreBuilder,Gitignore}` with `add_line` from
captured bytes, rather than filesystem-walking APIs. Neither `ignore`,
`gix-ignore` nor `globset` is in `core/Cargo.lock`. `gix-ignore` is a viable
lower-level Git matcher; it brings no existing dependency advantage here.
Pin a compatible release during implementation; toolchain compatibility is
unverified. [Builder API](https://docs.rs/ignore/0.4.33/ignore/gitignore/struct.GitignoreBuilder.html),
[gix-ignore API](https://docs.rs/gix-ignore/latest/gix_ignore/).

The adapter owns precedence: exclude lowest, then root-to-leaf ignore files,
last applicable pattern wins. Apply directory rules, anchoring, escapes and
negation; an excluded parent prevents re-including its child. Do not follow
symlinked rule files or load global excludes. These are
[Git's rules](https://git-scm.com/docs/gitignore). Scope the prototype to a
repository rooted at the Workspace; a `.git` indirection outside it is explicitly
unsupported, never read from the daemon host. Rule read/parse failures refuse
capture rather than silently uploading excluded data. Rules can themselves be
local; projection still evaluates their captured bytes.

Cost per classification: changed bindings/inodes plus required ancestor lookups
and rule bytes; a rule change or directory move can revisit an entire affected
local subtree. Reuse unchanged compiled rules by captured identity with bounded
caches/backed traversal. Large rule sets still cost parsing/matcher memory;
bounded batches or explicit resource refusal need qualification. No build-output
payload read is required merely to classify it. No timing claim is made.

Smallest explicit per-Workspace surface: a new fork-only mount-control variant
with local-path policy, leaving `Request::Mount` unchanged/default-off. The remote
prototype controller uses it; daemon latches policy before attachment in shared
`Workspace` state, including scoped operation clones. No marker, global switch,
Sandbox change or JS SDK change is required for this controller path. Ordinary
JS mounts retain default behavior; a JS opt-in can be added later.

In [remote-store.md](remote-store.md), construction feeds the local emission
index before `Lacking` → `Upload` → `CommitCandidate`. Filtering before emission
means excluded bindings and exclusively local content produce no candidate
objects, uploads or published references; no ignore rules/retention state go to
the server. Shared hard-link bytes and previously committed objects are the
exceptions already stated. Rule/base reads may still use `GetObjects`; an empty
projection still needs a head check. This confirms the **proposed seam**, not
implemented remote behavior: the other worktree was not inspected or modified.

## 4. Implementation scope and acceptance

Edit/churn inventory, grouped by responsibility; every parenthesized number is
the exact-path commit count from
`git log --since=2026-10-06 --format=%H cfbd865f5 -- <path>` (no rename following).
`!` marks **hot: ≥8 commits**. Estimates are changed/new production lines per
group, not measured LOC or promises; new test/module paths have zero history.

| Responsibility; estimated lines | Existing files and commits |
| --- | --- |
| Projection/rules; 500–800 | W/src/construction/driver.rs (7); W/src/construction/namespace/normalize.rs (6); W/src/construction/namespace/cursor.rs (6); W/src/ports/captured_namespace.rs (5); W/src/lib.rs (23!) |
| Binding/freshness; 150–250 | W/src/workspace/state.rs (3); W/src/workspace/install.rs (3); W/src/workspace/view.rs (6); W/src/mutation/eval.rs (3); W/src/construction/captured/owner.rs (8!) |
| Retention/read/cleanup; 700–1,100 | O/sql/schema.sql (29!); O/src/database/startup.rs (37!); O/src/database/statements.rs (38!); O/src/namespace/inode.rs (16!); O/src/namespace/directory_entry.rs (4); O/src/lifetime/generation.rs (12!); O/src/lifetime/captured_reader.rs (9!); O/src/lifetime/composition.rs (9!); O/src/payload/layers.rs (4); O/src/maintenance/garbage.rs (8!); O/src/maintenance/pieces.rs (3); O/src/contract/types.rs (15!); O/src/lib.rs (22!) |
| Commit integration; 150–250 | S/src/store/captured.rs (2); S/src/store/commit.rs (5); S/src/store/commit_types.rs (4); S/src/overlay/lifetime_operations.rs (1); S/src/overlay/captured_namespace_port.rs (4) |
| Opt-in/diagnostics; 150–250 | B/src/control_types.rs (15!); B/src/control_request.rs (10!); D/src/control/operations.rs (27!); D/src/control/dirty.rs (1); D/src/operator/workspace.rs (4) |
| Dependency/docs; no production estimate | W/Cargo.toml (0); core/Cargo.lock (20!); core/docs/architecture/64-overlay-terminology.md (10!); core/docs/architecture/78-captured-namespace-construction.md (9!); core/docs/architecture/79-product-commit.md (7) |

Put new rule/projection helpers under W and local-retention helpers under O,
within the group estimates; names are not scaffolding requirements. Total rough
production edit budget: **1,650–2,650 lines**; add approximately 500–800 external
test lines. Start with Overlay ownership/install proofs, then projection and
matcher, then control/remote integration. Rebase the hot Overlay hooks carefully
and coordinate `S/src/store/commit.rs` with the remote-store owner.

Tests in the relevant crates' `tests/`: nested/negated rules and base-wins,
whiteouts, mixed hard links, both rename directions, rule changes/promotions,
parent-only side effects, no consumer/digest emissions for local-only content;
install with concurrent overwrite/truncate/unlink, captured-reader release,
bounded reclamation, fresh-inode checks, merged ancestor/type collisions,
definite failure and unknown custody. Include default-off regression coverage.

End-to-end, once the remote prototype exists: mount opt-in from a base containing
the ignore rules but **no `target/`**; run a build plus one source edit; Commit;
read the server tree independently and inspect upload/constructor receipts for
absence of target-only objects; verify sandbox target bytes/identity; run an
incremental build that changes only `target/`; second Commit must be UpToDate
with no new upload/Commit. Verify local classification, then unmount/remount and
confirm local output is gone. Run separately with a moved head/collision.

Leave out Init filtering, index/global-exclude parsing, local directories/FUSE
routing, eviction/restart persistence, server-side filtering, standalone UI and
fs-bench-pro. Future proofs select Disposable, one construction worker and
bounded explicit timeouts; Durable remains disabled. All runtime and performance
acceptance above is **NOT_RUN** in this design phase.

## Option B: local subtrees in the daemon

Assessment at `07675573bd1dbc85bba1d32469d69ac9b10760a2`, 2026-10-20;
source inspection only. **B removes Overlay payload retention, but is neither a
drop-in port wrapper nor equivalent to capture-time ignore rules.** It introduces
a second filesystem backend and a union namespace. Below, **F** means
`core/crates/layerfs-fuse/`; other abbreviations retain their definitions above.

### Dispatch boundary

`F/src/request/callbacks.rs::KernelFilesystem` implements `fuser::Filesystem`.
`request/state.rs::submit`, `request/reply.rs::ReadReply`,
`request/mutate.rs::MutationReply` and `request/directory.rs` drive the semantic
operations. `D/src/service/filesystem_port.rs::Mounted` supplies a per-request
`FilesystemPort(StoreOperation, Fence)` through `MountServices::request`.

The existing `RequestServices` trait (`F/src/ports.rs`) returns concrete
`KernelReadOutcome`, `KernelWindow`, `KernelDirectoryWindow`,
`KernelMutationOutcome` and `KernelCookieOffer`. Mutations also carry Overlay
`OpenFile` and `Publication` custody. `operations/mutation.rs::Custody::decide`
reserves a Workspace serial **before** `mutate_visit`. A wrapper here would
either fabricate Overlay ownership or change these types throughout the stack.

Use a proposed optional **`LocalServices` port above that boundary**, supplied by
`Mounted`, with backend-neutral requests, fd/handle ownership, attributes, errno
and actual byte-count results. Fuse owns callbacks/replies; daemon owns routing,
rules, local catalog and native I/O. Route before serial reservation, recognition,
Workspace visits and `.request()`'s `StoreOperation` creation. Preserve the
existing default path and `MountRequests` admission/drain; do not add another
receiver or hold a Workspace SQL lock during native I/O. Routing policy can be
centralized; the callback/identity/reply hooks cannot all sit in one current port.

| Operation | Hook and required behavior |
| --- | --- |
| lookup/getattr/readlink | `request/state.rs::submit`, `request/reply.rs::ReadReply`; consult local roots before versioned lookup, including a versioned parent. Return local attributes/lookup ownership and opaque symlink bytes. |
| open/read/release | Same read path plus `callbacks.rs::release`; local fd handles bypass `KernelWindow` and `close_file`'s Overlay token. Native short reads are valid. |
| setattr/write | `request/mutate.rs` before `KernelMutation::perform`; local fchmod/truncate/timestamps/pwrite, explicit errno and partial-effect handling. Do not use `coherence/pages.rs::written` to claim the requested count after a short host write. |
| create/mkdir/mknod/symlink/link/unlink/rmdir/rename | `callbacks.rs` and `request/mutate.rs::named`; classify both source and destination, local-root membership and versioned-parent constraints before the publishing path. Return EXDEV through the new reply port; current `Refusal` has no EXDEV. Preserve regular-file-only mknod support. |
| opendir/readdir/releasedir | `request/directory.rs`; new daemon union stream/handle. Existing `operations/directory.rs::DirectoryStream` publishes Overlay-owned cookies and cannot simply receive appended native entries. |
| readdirplus | Currently refused in `callbacks.rs`, not negotiated by `mount/profile.rs`. Leave disabled; enabling it adds attributes and lookup ownership for every accepted entry. |
| flush/fsync/fsyncdir | Currently inline ENOSYS. Smallest B retains uniform no-durability semantics under the no-sync-on-disposable-backing policy. Native fsync is a policy departure: route these callbacks and use explicit success on the versioned side, since ENOSYS is connection-wide/sticky and can suppress later local calls. It still would not persist the routing table or promise restart recovery. |
| xattrs | Currently uniformly ENOSYS. Smallest B keeps them unsupported on both sides. Native xattrs require extra safe syscall support, policy and callback routing; versioned replies must then be EOPNOTSUPP rather than connection-wide ENOSYS. Do not claim full native syscall transparency. |
| statfs | `callbacks.rs` → `request/inline.rs::statfs` currently returns fixed declared capacity. Route local nodes to backing-filesystem capacity and declared quota; root/versioned statistics must label their different meaning. |
| forget/batch-forget | `request/inline.rs::forget_unit`; split local and Workspace ownership before `RequestServices::forget`. The library delivers batch units as individual callbacks. |

### Identity, directories and installation

Today `F/src/attributes.rs::Identity` maps the root serial to kernel inode 1 and
other serials to `serial + 1`. Content serials stop at `i64::MAX`, so the highest
versioned kernel number is **2^63**, not 2^63−1. Reserve local kernel numbers
**2^63+1 through u64::MAX**, decode them as `Local` rather than a Workspace
serial, and never allocate them from the Store. Existing entry/create replies
use `Generation(KernelMount::owner_id())`; a monotonic, never-reused local number
within that mount can use the same generation. Refuse exhaustion, never wrap.

Map backing `(device, inode)` to a stable local identity; aliases within one local
subtree share it. Pin host identity with fd ownership while lookup/open/request
references exist, so host inode reuse cannot redirect an old kernel reference.
Keep local lookup counts and handles separately; LOOKUP/CREATE/LINK acquire,
FORGET decrements, RELEASE closes, and unlinked-but-open files remain usable.
Plain READDIR acquires no lookup reference. A lost reply does not undo a native
mutation or guessed lookup count. Ordinary host errors such as ENOENT/ENOSPC must
be completed errno replies, not `ServiceError`s that terminally retain the mount.
Use bounded/indexed backing for the subtree/identity/cookie catalog if it grows
beyond open/kernel-referenced state; an unbounded resident path map is not free.
Any backing catalog is disposable and never reopened as recovery state.

For versioned parents, maintain local child names, virtual parent timestamps and
directory link-count adjustments outside Overlay. Check merged emptiness for
rmdir and rename-over-directory: Overlay alone would incorrectly permit removal
of a parent whose only children are local. Serialize first-local creation and
table publication with competing namespace operations. Read current rules/base
through Workspace ports and retain a base source across the decisive operation
to fence install; ancestor/rule mutations also need routing coordination. Base
and rule misses can still contact the remote Store. No syscall retry on unknown
effects, and no whole-Commit lock.
Prepare a new backing node privately before publishing its table binding; host
creation plus catalog insertion are not one transaction. Retain exact partial
failure custody and cleanup debt instead of exposing a half-created route.

A union directory needs its **own cookie namespace**: positions 1/2 for `.`/`..`,
then published positions identifying backend and continuation, not raw native
`d_off` mixed with Overlay offsets. Use a bounded two-phase stream (versioned
entries with shadowed names removed, then local names); sorting across both
backends is unnecessary. Record only the prefix accepted by the reply buffer,
retain cookies until release/defined rewind, and handle local-table mutations
without interpreting an old cookie as another name. Local-only directories use
fd-based native enumeration behind the same cookie adapter. Wrapped versioned
directory handles retain their existing lower owner. Test seek/rewind and tiny
reply buffers through concurrent namespace changes and Commit.

`S/src/store/commit_merge.rs::BoundWorkspace::stale_after_install` compares
**canonical roots**, not the union view; `D/src/control/invalidate.rs` forwards
its events through `F/src/session/invalidate.rs::Invalidator`. Keep this for
versioned nodes, add local-name/parent invalidation and collision reconciliation;
never invalidate a local file's data merely because its hidden base counterpart
changed. Local bindings keep their kernel identities, including open handles.
Parent deletion/replacement is harder than a same-name file collision: preserving
`module/target` may require a local ancestor container at `module`, reparenting
the virtual subtree and invalidating old parent/name caches. Retain detached old
owners until release. A stale path→directory map alone cannot do this.

Consequently the native **publication algorithm and UpToDate predicate need no
local-dirt logic**, but installation needs a short, provider-independent routing
coordination hook in the Store-service driver around the known install, plus
daemon reconciliation before exposing the new union view. Reconcile the exact
installed root, including conflicts and post-capture creates. This is not solved
by running a callback only after the Commit reply. Preserve known-publication
failure custody if reconciliation fails; do not replay Commit.

### Behavioral rules and remaining differences

| Case | Required rule / qualification |
| --- | --- |
| `getcwd` | Local-root `..` is the **virtual versioned parent**, never the private backing directory. Parent readdir must return the same local inode; track virtual ancestry through renames/reconciliation. Deleted cwd may return ENOENT normally. Test inside descendants and across parent replacement. |
| `rm -rf` / root unlink | Recursively serve local children; only successful rmdir of an empty root, or unlink of a file root, removes its table binding. Serialize with recreation, preserve held fds/lookups. A failed native removal keeps the binding. Under collision, removal reveals the base; a continuing recursive command can then act on that revealed versioned data. Report this behavior, not isolation from `rm`. |
| `mvn clean` then rebuild | Removing `target` removes the route; the next mkdir re-evaluates current rules and creates a **fresh local identity** if eligible. Existing handles still name the old object. |
| Cross-boundary rename/link | EXDEV before any effect, including distinct local subtrees treated as separate domains. `mv` may copy/delete non-atomically; `ln` and some build tools simply fail. For the smaller prototype, also refuse rename of a versioned ancestor containing local roots with EXDEV; otherwise it needs a coupled Overlay/table rename. Never silently leave stale prefixes. |
| Symlink from versioned space | Keep the symlink versioned; kernel path resolution reaches local lookup. For local links, return text via readlink and let the kernel resolve it. Native leaf opens must not follow links into the daemon host; use retained directory fds and no-follow component operations, never concatenate untrusted absolute paths. |
| mmap / handles across Commit | Keep backing fds and local inode IDs; use the existing cached-I/O profile with writeback off. MAP_SHARED writes arrive as FUSE writes; Commit is not an msync barrier. No direct backing access by sandbox commands. Qualify truncate, unlink, dirty mappings, ENOSPC and teardown; ordinary local payload install is unnecessary. |
| Permissions / `command_uid` | Mount already uses `allow_other,default_permissions`; `Identity` projects command UID/GID. Keep that model, supported modes and umask semantics; private backing parents remain daemon-only. Set intended backing mode/owner explicitly because daemon umask is 077. Do not switch process-wide credentials or expose root-only xattr/device/chown powers through forwarding. |
| Quota / ENOSPC | Existing Overlay accounting covers none of this disk. Expose backing free space and an explicit local budget (or explicitly no per-Workspace quota); include unlinked-open allocation. Prechecking free bytes cannot guarantee a write. Native writes may partially succeed before ENOSPC: preserve/report the actual effect, do not claim Overlay atomicity or replay a tail. Cached FUSE partial-write/error behavior needs mounted proof. |
| Unmount / discard | Opt-in accepts loss of local-only data on ordinary successful unmount; it must not permanently require `discard`. Preserve the versioned-dirt refusal. After detach/drain, revoke local owners, close fds and delete native trees/catalog with bounded traversal; report retained cleanup failure. Force follows the same ownership fence. A crash can leave private residue; never restore or claim it was deleted. |
| Rule changes | B classifies at **creation**, whereas A classifies at **capture**. Re-reading rules for later creates cannot demote earlier uncommitted Overlay paths or promote existing native subtrees. Exact A semantics require migration, races/handle preservation and Commit integration, defeating the proposed no-change boundary. Smallest B must instead freeze a subtree's local classification until deletion/explicit copy-out; this is a policy change, not equivalent Git behavior. |

Likewise, a `.gitignore` added after unignored files were created cannot make B
skip them at the next Commit without migration. Negation cannot split an already
routed subtree after rule changes. Already committed base names still win at
creation; existing uncommitted versioned names must remain in that backend until
explicitly removed. Shadow collisions remain local even when rules change.

For the **creation-time, sticky-subtree variant**, no changes to Overlay schema,
capture, generation floor, `born`, payload composition or `CapturedNamespace`
are necessary. No exclusively local objects enter `Lacking`/`Upload`/
`CommitCandidate`; server-side ignore support is unnecessary. It still needs the
daemon routing/installation work above, rule evaluator, opt-in control, lifecycle
and diagnostics. The existing `operator.workspace.changes` walks Workspace's
view and would show **none** of these paths: merge local catalog/native traversal
into its reporting with `localOnly`/`shadowsBase`, separately paginated/countable.
`workspace.status`'s raw dirty counters can remain versioned-only; document that
zero does not mean no disposable local data. Add local usage/counts to operator
status and report loss separately from committable dirt. JS forwarding can stay
unchanged; reuse the fork-only mount variant proposed in §3.

### Scope, churn and recommendation

Same exact-path method, now pinned to this assessment's parent:
`git log --since=2026-10-06 --format=%H 0767557 -- <path>`; `!` = ≥8 commits.
This is an edit inventory, not a source layout. Estimates cover the sticky
variant, existing supported node types, no native fsync/readdirplus/xattrs, and no
transparent migrations. They are planning ranges, not measured source deltas.

| Work; estimated production lines | Existing edit points and commits |
| --- | --- |
| Local port/identity/replies; 400–700 | F/src/ports.rs (18!); F/src/attributes.rs (4); F/src/request/callbacks.rs (11!); F/src/request/state.rs (8!); F/src/request/reply.rs (9!); F/src/request/mutate.rs (5); F/src/request/directory.rs (10!); F/src/request/inline.rs (5); F/src/session/invalidate.rs (1); F/src/lib.rs (7) |
| Native backend, rules, union catalog/cookies; 1,200–1,900 | D/src/lib.rs (22!); D/src/service/filesystem_port.rs (30!); D/src/application/config.rs (9!); D/src/application/filesystem.rs (4); D/Cargo.toml (11!) |
| Lifecycle/install/diagnostics/opt-in; 700–1,200 | D/src/control/registry.rs (8!); D/src/control/operations.rs (27!); D/src/control/attach.rs (8!); D/src/control/invalidate.rs (1); D/src/control/unmount.rs (14!); D/src/control/force.rs (6); D/src/control/dirty.rs (1); D/src/operator/workspace.rs (4); S/src/store/commit.rs (5); S/src/store/commit_types.rs (4); B/src/control_types.rs (15!); B/src/control_request.rs (10!) |
| Lock/docs; excluded from production estimate | core/Cargo.lock (20!); core/docs/architecture/75-native-request-service.md (21!); core/docs/architecture/77-native-mutation-coherence.md (19!) |

New helpers (zero history) would be `F/src/local.rs` for the generic port and
`D/src/local_subtrees/mod.rs`, `router.rs`, `catalog.rs`, `io.rs`, `directory.rs`,
`rules.rs`, `lifecycle.rs` beneath that directory, split within the 999-line rule.
The estimates include these files. Use existing std/nix safe fd APIs; both crates
forbid unsafe code. The matcher remains a new dependency; safe syscall coverage
and locked toolchain compatibility need implementation-stage checking. A backed
catalog can use the repository's SQLite dependency, without changing Overlay or
adding a second authoritative Store. Add external tests under F and D `tests/`;
new test filenames have no history. No frozen harness changes.

| Dimension | A: Overlay retention | B: native sticky subtrees |
| --- | --- | --- |
| Production / test estimate | 1,650–2,650 / 500–800 | **2,300–3,800 / 900–1,400** |
| Main change | Projection plus local ownership in Overlay | Native backend plus union namespace and kernel ownership |
| Dynamic rules | Reclassify at capture; promote retained content | New creates only; existing routing sticks; exact parity unestimated |
| Rename/hard links | Shared inode semantics; projected aliases | EXDEV at boundaries; fallback is tool-dependent |
| Commit/upload | Filter + projection dirt + install retention | No local objects/dirt; still install coordination/reconciliation |
| Cost moved | Excluded payload not constructed; overlay writes remain | Native syscall/copy/page-cache costs; union routing and host disk usage |
| Rebase risk | High: schema/query/lifetime hot spots | Also high: ports, callbacks, daemon mount/unmount; smaller Overlay overlap, new conflict with remote Commit seam |

Proofs must include the earlier build/Commit/server-absence/second-UpToDate case;
tiny readdir buffers and seek/rewind; lookup/forget balance; mixed backend
rename/link refusal; local-parent emptiness and `getcwd`; clean/recreate with old
fds; symlink escape prevention; modes; short writes/ENOSPC; mmap/truncate across
Commit; merged parent removal/type collision; concurrent create/install and rule
edits; ordinary/forced unmount and cleanup failure. Count native bytes/catalog
growth as well as time; the existing 1–11% Overlay build overhead does not predict
native-forwarding performance. All remain **NOT_RUN**; no builds were performed.

**Recommendation: neither yet under the unchanged requirements.** A is already
rejected on cost; B avoids its hottest Overlay changes but replaces them with a
second filesystem backend, union-cookie/identity ownership and install races,
with no demonstrated smaller implementation or faster build path. More
decisively, creation-time routing cannot preserve the accepted capture-time rule
semantics without migration. If that policy is deliberately narrowed to sticky,
newly created ignored subtrees and EXDEV boundaries, B becomes a viable separate
prototype; the source audit does not justify calling it the cheap equivalent.
