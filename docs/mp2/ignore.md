# Git-ignored names stay local

> **Status: mp2 prototype on branch `mp2/ignore`; not a released contract.**
> Opt-in per remote daemon: `ignore=git` in its setup. A warm-base builder
> runs without it.

A remote sandbox's build outputs and dependencies are the bulk of its writes,
and Git already says which they are. With `ignore=git`, what Git ignores never
leaves the sandbox: no upload, no published root, no merge on the server. The
sandbox still sees all of it, and `mvn clean`, `rm -rf node_modules` or
`git clean -fdX` stay local too.

Paths below are relative to `core/crates/layerfs-store-service/src/store/`.

## Two roots per Workspace

Every Commit builds the Workspace's **whole tree** as before. Two roots then
follow from it:

| Root | Holds | Where its objects live |
| --- | --- | --- |
| Local base `L` | Everything the sandbox sees | Local object cache only |
| Published `Q` | `L`'s kept names, plus ignored names it already had | Server |

The invariant is that the kept names of `L` and `Q` are equal, with the same
inode serials. Ignored names in `Q` are leftovers from a warm base: published
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
  is imposed: its first differing name is placed, or its inode reconciled.
- **Changed rule files**, a `.gitignore` or `.git/info/exclude` bound,
  unbound or rewritten. The directory is reconciled, the root for `exclude`.
  This walks the kept part of that subtree; it is the one cost that follows
  the tree, and only on a rule edit.
- **Moves** out of ignored places are adoptions, above.

A path that becomes ignored needs nothing: `Q` keeps what it had.

## Cost

- Per Commit: proportional to the change, as before, plus one index parse
  when `.git/index` changed. The parse is cached by content.
- A rebase is proportional to what the head added.
- A rule edit walks the kept subtree below it. Adopting a moved directory
  reconciles that directory.

## Limits

- The local base lives in memory with the bound Workspace. A remount or a
  daemon restart starts from the published head, and local-only files are
  gone. Restart recovery is not built.
- Hints are in memory too. Without them, placing a name falls back to a walk.
- Local-only objects stay in the cache until it is dropped; there is no
  eviction.
- Ignored leftovers in `Q` are stale by design. Moving a directory out of an
  ignored place removes it from there in `Q`.
- Matching is case-sensitive; `core.ignorecase` is not read. Global excludes
  (`core.excludesFile`) are not read either, as they live outside the tree.

## Tests

- `ignore/tests.rs` drives the round trip on in-memory trees. It covers:
  - ignored changes;
  - cleans and rebuilds;
  - tracked files in ignored directories;
  - moves out of ignored places, in the same Commit and across Commits;
  - `git add -f`;
  - rule edits, including a nested `!` rule;
  - a moved head;
  - the plain case that publishes the built tree.
- `ignore/{rules,index}.rs` hold unit tests for matching and index parsing.
- The two-sandbox Docker run is `docs/mp2/run-ignore-e2e.py`, with receipts
  in `docs/mp2/receipts/ignore01/`. B1 runs `ignore=git`; B2 runs without
  it, as the warm-base builder and the other machine. All six scenarios
  passed:
  - a warm base;
  - ignored changes (32 MiB `big.bin`, 3,000 `node_modules` files, logs);
  - a clean;
  - a rebuild;
  - flips (`git add -f`, an un-ignoring `.gitignore`);
  - a moved head.
- In that run, the Commit with ignored outputs uploaded 9,353 B in 411 ms. The
  same shape with ignore off uploaded 34.2 MB in 790 ms. `git status` agreed
  on both sandboxes.
