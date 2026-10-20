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
