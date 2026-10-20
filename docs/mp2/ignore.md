# Git-ignored names stay local

> **Status: mp2 prototype on branch `mp2/ignore`; not a released contract.**
> Opt-in per remote daemon: `ignore=git` in its setup. A warm-base builder
> runs without it.

With `ignore=git`, a remote Commit projects kept changes onto a separate
published tree and uploads only that tree's reachable local objects. Build
outputs and dependencies remain visible locally. **This prototype is not a
confidentiality boundary:** unsupported indexes and incomplete hardlink hints
can publish ignored bytes; server namespace/rule changes have unresolved
reconciliation cases below.

Paths below are relative to `core/crates/layerfs-store-service/src/store/`.

## Two roots per Workspace

Every Commit builds the Workspace's **whole tree** as before. Two roots then
follow from it:

| Root | Holds | Where its objects live |
| --- | --- | --- |
| Local base `L` | Everything the sandbox sees | Local object cache only |
| Published `Q` | `L`'s kept names, plus ignored names it already had | Server |

The intended invariant is that the kept names of `L` and `Q` are equal, with
the same inode serials. The unresolved cases below violate it. Ignored names in `Q` are leftovers from a warm base: published
as they were, never updated.

One Commit, given the previous local tree `L₀` and the tree just built `L₁`
(`remote_commit.rs`):

1. **Project.** `P = replay(L₀ → L₁ onto Q, Ignore)` carries the changes Git
   does not ignore (`ignore/project.rs`). A Commit with nothing left out and
   no local base publishes `L₁` itself.
2. **Upload.** Only objects `P` reaches that the cache holds as local are
   uploaded: a children-first walk from `P`'s root over rows marked
   `remote=0`, sent in LACKING/UPLOAD windows of at most 512 objects or
   4 MiB (`layerfs-remote-store/src/{cache,client}.rs`). Objects `L` alone
   reaches are never sent.
3. **Publish** `P`. The server may merge it with a moved head into `M`.
4. **Rebase.** The new local base is `replay(P → M onto L₁, All)`: the head's
   changes land on the local tree, and local-only names survive. With an
   unmoved head this is `L₁` itself (`ignore::rebase`).

The local base is installed like a published root, so the overlay retires as
usual and FUSE is unchanged. `BoundWorkspace::{local_root,published_root}`
(`commit_merge.rs`) keep the two roots apart; `IgnoreState` holds the pair.

## Replay

`ignore/replay.rs` replays the changes of `from → to` onto a third root,
name by name. The work follows the change, not the tree:

- Changed inodes come from the inode-table difference, and changed names from
  the changed directories among them.
- A change applies only where `onto` still agrees with `from`; otherwise
  `onto`'s change wins.
- A kept name that binds an inode `onto` lacks brings it from `to`, with the
  kept part of its subtree. Brought inodes keep their serials, so later
  Commits still find them.
- A kept name that binds an inode `onto` holds elsewhere **adopts** it. A
  directory has one name, so an adopted directory loses its old name in
  `onto`; so does a moved file whose old name was left out.
- **Reconcile.** While projecting, `L` may hold below a shared inode what `Q`
  never got, so adopted inodes are reconciled. Their kept names and values
  are made `L`'s.

## What Git ignores

`ignore/classify.rs` decides name by name, from `L₁` itself, as Git does:

- `.git/info/exclude`, then every `.gitignore` from the root down. The
  matcher is `ignore/rules.rs`: last match wins, deepest file first, Git's
  wildmatch with `**` and classes.
- Below an excluded directory everything is excluded. A path the index tracks
  (`ignore/index.rs`, versions 2–4) is never ignored, wherever it sits.
- `.git` itself is never ignored.
- A name that cannot be placed in the tree is kept, so an unknown never
  withholds a change.
- An index that cannot be read publishes the whole built tree. That covers a
  split index and an index over 256 MiB.

There are no parent pointers, so names come from the Workspace's `PathHints`:
bindings the kernel looked up, checked against the tree. A `locate` walk is
the fallback.

### Flips

A change of rules or index can make kept what `Q` never got. The classifier
hands these back to the replay to reconcile:

- **Newly tracked paths**, from comparing this index with the previous one
  (`git add -f`, or a checkout that tracks a file that was ignored). Each path
  is imposed: its first differing name is placed, its inode reconciled, or
  its stale published binding removed when the path is absent locally.
- **Changed rule files**, a `.gitignore` or `.git/info/exclude` bound,
  unbound or rewritten. The directory is reconciled, the root for `exclude`.
  This walks the kept part of that subtree; it is the one cost that follows
  the tree, and only on a rule edit.
- **Moves** out of ignored places are adoptions, above. Detach checks the
  published directory binding even when earlier ignored moves left it different
  from the old local name.
- A changed rule file with no checked hint uses the same location fallback as
  value classification, including an ignored rule file absent from `Q`.

A path that becomes ignored needs nothing: `Q` keeps what it had.

## Cost

- With checked hints, ordinary projection follows the change, plus one index
  parse when `.git/index` changed. The parse is cached by content. Missing hints
  and directory adoptions with unknown published names can require tree walks.
- A rebase is proportional to what the head added.
- A rule edit walks the kept subtree below it. Adopting a moved directory
  reconciles that directory.

## Limits

- The local base lives in memory with the bound Workspace. A remount or a
  daemon restart starts from the published head, and local-only files are
  gone. Restart recovery is not built.
- Hints are in memory too (at most eight bindings per inode). Without them,
  placing a name falls back to a walk, bounded at 1,048,576 directories;
  unknown placement keeps a change. Rule files over 1 MiB are read as empty.
- Local-only objects stay in the cache until it is dropped; there is no
  eviction.
- Ignored leftovers in `Q` are stale by design. Moving a directory out of an
  ignored place removes it from there in `Q`.
- Matching is case-sensitive; `core.ignorecase` is not read. Global excludes
  (`core.excludesFile`) are not read either, as they live outside the tree.

## Review findings

All tests below are in `layerfs-store-service/tests/ignore.rs` unless specified. P1 means content
leak, loss, missing kept content or failed Commit; P2 means stale empty namespace
or test portability. Open cases retain failing assertions behind explicit
`#[ignore = "design gap: ..."]`; they are not passes.

| Severity / status | File::function and concrete scenario | Regression |
| --- | --- | --- |
| P1 fixed | `replay.rs::detach`: move `node_modules/x` to an already published `out/x`, then to `vendor/x`; the stale first name gave the directory two parents | `review_move_twice_from_shared_ignored_parents` |
| P1 fixed | `classify.rs::changed`: rewrite an ignored `logs/.gitignore` without hints to `!keep.log`; kept bytes were missing from publication | `review_ignored_rule_rewrite_without_hints_reconciles` |
| P2 fixed | `replay.rs::impose`: delete an ignored directory locally, then index-track an absent child; its stale published directory remained kept | `review_seed_1_tracking_a_locally_deleted_directory` |
| P1 open | `project.rs::IgnoreState::project`: an unsupported index plus `target/secret` publishes the whole local tree | `review_unreadable_index_does_not_publish_ignored_bytes` |
| P1 open | `classify.rs::Ignore::value`: rewrite a warm file with two ignored hardlinks and no complete hints; the unknown alias makes the new bytes publish | `review_ignored_hardlinks_without_complete_hints_do_not_leak` |
| P1 open | `project.rs::rebase` / `replay.rs::replay`: server deletes `logs`, which locally also contains ignored `private.log`; installation loses that file | `review_server_delete_preserves_local_ignored_descendants` |
| P1 open | `project.rs::rebase`: server removes `target/` from the rules during publication; local-only content becomes kept without appearing in `Q` | `review_server_rule_flip_keeps_views_equal` |
| P2 fixed | `layerfs-remote-store/tests/transport.rs::bounded`: macOS inherits non-blocking mode from the test listener; accepted test sockets now explicitly block. Production `server.rs::serve` uses a blocking listener | Original two transport tests plus `production_style_blocking_listener_returns_blocking_sockets` |

The open cases require an explicit unknown-classification policy, complete alias
classification, and delete/rule/index conflict semantics across the two roots.
No recovery, remount persistence, FUSE teardown or metadata batching changes are
included in this review.

## Tests and failure boundaries

- The in-memory model runs seeds **0–199**, **30 steps each**, with an independent
  path/byte oracle. It covers file writes/removals, directory creation/removal,
  file/directory moves, root and nested `!` rules, index add/remove, and separate
  server-head writes/removes/moves merged by the production Content merge.
  It checks kept paths/bytes, complete local contents, unique directory parents,
  readable references, and unique ignored-only byte tokens after every Commit.
  Previously published bytes may move with stale ignored leftovers. Concurrent
  edits to the same name and the four open design cases are separate regressions,
  not included in the passing random envelope.
- The original round-trip, matcher and index tests remain. Seeds 1, 2, 31 and 130 have
  named tests; seed 31 also checks the oracle's handling of moved warm leftovers.
- `layerfs-store-service/tests/ignore/faults.rs` drives the real `BoundWorkspace::commit_remote` through
  `RemoteStore` / `RemoteBuild` faults. A definite pre-publication refusal leaves
  `IgnoreState` unchanged and permits a new explicit Commit, preserving local
  bytes and the projection. Known publication followed by a base-read failure
  or rebase-output failure retains the capture and old pair; the next Commit is
  refused `InFlight`, without another publish. Recovery to a successful next
  Commit is **not implemented**; no stale-pair publish is allowed.
- Real authenticated localhost transport tests reject the second upload window
  or drop its reply after one 512-object window was acknowledged. Unreachable
  private bytes never enter LACKING/UPLOAD, acknowledged objects remain marked
  remote, all other local objects remain cached, and a later publish performs no
  RPC on the quarantined channel. This also applies to definite transport-level
  rejection; it differs from the reusable provider used by the driver unit test.
- Local receipts, commands, check results and retained failures:
  [ignore03](receipts/ignore03/README.md). Rust 1.98.1 on this Mac; changes use
  Rust 1.85-compatible syntax. The remote crate's existing bundled SQLite feature
  is selected together with Store-service tests; this Mac's system SQLite fails
  the existing overlay version qualification. No Store profile was changed.
- No Docker run in this review. Prior two-sandbox evidence remains in
  [ignore01](receipts/ignore01/) and [ignore02](receipts/ignore02/); those runs do
  not cover the adversarial cases above. No `cxi-` Docker resources were created.
