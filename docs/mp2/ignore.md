# Git-ignored names stay local

> **Status: mp2 prototype on branch `mp2/ignore`; not a released contract.**
> Opt-in per remote daemon: `ignore=git`. Warm-base builders run without it.

A remote Commit builds the complete local filesystem, projects its kept changes
onto a separate published tree, and uploads only that tree's reachable local
objects. Ignored outputs remain visible locally. This is not a confidentiality
boundary: oversized rule files and incomplete placement at the walk limit retain
the explicit limitations below.

Source paths below are relative to `core/crates/layerfs-store-service/src/store/`.

## Two roots and one Commit

| Root | Contents | Object location |
| --- | --- | --- |
| Local base `L` | Everything the Workspace sees | Local cache, including local-only objects |
| Published `Q` | Kept names and frozen ignored leftovers from earlier publication | Server |

`remote_commit.rs` performs:

1. **Project:** replay `L₀ → L₁` onto `Q` with the local rules/index. Pending
   reconciliation seeds are included even when `L₀ == L₁`.
2. **Upload:** walk only the candidate's reachable cache objects marked local,
   children first. LACKING/UPLOAD windows contain at most 512 objects or 4 MiB
   past the first object (`layerfs-remote-store/src/{cache,client}.rs`).
3. **Publish:** the server can merge the candidate `P` with a moved head into
   `M`. Only a known successful publication acknowledges existing pending seeds;
   project failure, rejected/uncertain publication and an unpublished merge do
   not clear them.
4. **Rebase:** replay `P → M` onto `L₁`, preserving local-only names. Record
   server rule/index changes and retained directories for the next projection.
5. **Install:** install the rebased local root and retain its published partner
   in `IgnoreState`. The overlay retires normally, preserving later mutations.

The kept views normally agree after Commit. Server rule/index flips can leave
newly kept local bytes ahead of `Q` until the **next projection**, including a
no-op Commit. A server deletion can also leave local-only structural directories
until that projection. No automatic second publication is attempted.

## Replay and pruning

`ignore/replay.rs` discovers changed inodes and directory bindings from canonical
tree differences. A change applies where the target still agrees with the source;
otherwise the target's change wins. A kept binding brings missing inodes with
filtered subtrees, or adopts and reconciles existing inodes. An adopted directory
loses its actual old published name, including after earlier ignored moves.

Rebase enables a small `Keep::preserve_local` switch in that same replay. When a
server removal or replacement hits a directory, it prunes bindings shared with
`P` in postorder and retains bindings present only in `L` (including locally
rebound names). Empty shared directories disappear; ancestors needed by retained
names survive. If a replacement collides with such a retained directory, the
local directory wins. A serial moved elsewhere in `M` is detached and adopted
without pruning: its local-only descendants travel with it.

Retained directories become pending seeds too. This lets later kept writes below
a directory absent from `Q` reach publication. Seeds name directory identities;
at projection they resolve against the current local tree and impose missing
ancestors before reconciliation.

## Classification and placement

`ignore/classify.rs` reads `.git/info/exclude`, then applicable `.gitignore`
files from the root down. Matching is case-sensitive, last matching pattern wins,
and a nested `!` cannot reinclude a child of an excluded directory. `.git` is
always kept. A readable index's tracked paths override ignore patterns.

An unsupported, split, unparseable or over-256-MiB index is treated as an **empty
tracked set**: patterns still apply and `Projection.unreadable_index` is true.
Accepted cost: edits to tracked files matching ignore patterns remain local until
the index is readable again. Recovery compares against an empty previous tracked
set and reconciles the newly recognized tracked paths. Split-index reading is
not implemented. Actual provider/read errors still fail the operation.

`layerfs-workspace::PathHints` records LOOKUP and successful kernel create, mkdir,
symlink, link and rename bindings. Refused/failed mutations record no binding.
READDIRPLUS is not served: its callback returns `ENOSYS` and no capability is
negotiated, so there are no READDIRPLUS entries to annotate.

Hints are checked against the tree. Missing or incomplete bindings trigger at
most **one placement walk of the projection's local tree**, recording every
visited inode's aliases, including hardlinks. Subsequent placement uses that
learned map. Rule stacks are resolved only for directories classification needs;
walking unrelated directories does not read their rules speculatively.

## Rule and index flips

Local rule edits and newly tracked paths reconcile their affected kept subtrees.
A newly tracked path absent locally removes its stale published binding.

During rebase, rule-file binds, unbinds and rewrites seed their directories;
a change to `.git/info/exclude` seeds the root, including removal of `.git/info`.
The index comparison `P → M` seeds newly tracked paths. `IgnoreState` carries
these seeds to the next projection, where rules and paths are evaluated against
the then-current local tree. Failed projection leaves the seeds intact.

## Cost and limits

- With complete hints, ordinary classification follows the changes. One missing
  placement can list the whole local tree once, bounded at 1,048,576 directories.
  The learned binding map grows with that visited tree. Hardlinks beyond the
  eight-bindings-per-inode hint cache are completed by this walk.
- At the walk limit, names still unplaced retain fail-open behavior and increment
  `unplaced`. Rule files over 1 MiB are treated as empty. These are not secrecy
  guarantees. Global excludes and `core.ignorecase` are not read.
- Rule flips/reconciliation walk the affected kept subtree; server pruning walks
  the removed subtree. Locating an adopted directory's old published name can
  separately walk `Q`. Index parsing is cached by content for two indexes.
- Ignored leftovers already in `Q` stay stale. Previously published bytes can
  move with those leftovers. A kept hardlink legitimately publishes shared bytes.
- Local roots, hints and pending seeds are memory-only. Restart/remount begins
  from the published head and loses local-only content. Recovery is not built.
- Local-only cache objects have no eviction. No ctime, teardown/unmount, metadata
  batching or post-publication recovery changes are included.
- Known publication followed by rebase/install failure retains custody and
  refuses another Commit `InFlight`. Transport upload failure quarantines the
  write channel. Neither boundary has a recovery protocol.

## Tests

`layerfs-store-service/tests/ignore.rs` and `ignore/round4.rs` cover the four
formerly ignored regressions, unreadable-index withholding/recovery and split
indexes, incomplete/stale hardlink hints, nested deletion/replacement, moves,
next-Commit writes below retained directories, nested rule removal, server
rule/exclude/index flips, and pending seeds surviving projection failure or
unacknowledged publication. All four design regressions are enabled.

The independent model runs **200 deterministic seeds × 30 steps**, with real
Content merge. It includes local writes/removes/moves, rules and index edits,
server file changes, repeated directory deletion with a private leaf two levels
down, and server rule flips followed by no-op Commits. It checks complete local
contents, kept paths/bytes, directory topology and unique ignored-only byte
provenance. Only the explicitly deferred server-flip comparison and retained
structural ancestors use the new contract's temporary exceptions. Original
named seeds 1, 2, 31 and 130 retain their original operation envelope.

A counting reader checks 1,000 rewrites without hints: the 16 unrelated probe
directories are read at most once each (previously 16,000 reads). Kernel-visit
tests exercise all five successful mutation types without LOOKUP. The real
remote Commit fault tests and authenticated localhost upload/transport tests
remain; post-publication recovery remains unqualified.

Local review evidence and commands: [ignore04](receipts/ignore04/README.md).
Earlier failures remain in [ignore03](receipts/ignore03/README.md); historical
Docker runs remain in [ignore01](receipts/ignore01/) and [ignore02](receipts/ignore02/).
No Docker or remote environment was used for this round.
