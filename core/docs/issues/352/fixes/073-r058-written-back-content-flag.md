# F-073 · r058: a file written away and back counted as a content change in diffs and merges

> **Status:** Current fix record (#352 range 058, a1 and a2 stop), three
> commits: the difference, merge, then the publication lane's bound. Product change in `layerfs-content`
> (`compare/bytes.rs`, `merge/decide.rs`, `merge/units.rs`) and
> `layerfs-store-service` (`read/compare.rs`). Store format, overlay schema
> and construction are unchanged. Not an F-063 interaction.

| | |
| --- | --- |
| Trigger | [range 058](../ranges/range-058.md): the checkpoint's path check listed `packages/cordis/tool-cordis/src/api-catalog.ts` (git 361, LayerFS 537 paths). Its bytes were git's at both heads (blob `4d986582`, 234,915 B); ids and the full tree compare passed |
| Issue | #352 |
| Kind | code path: `diff_commits` and `diff_branches` items, `fs.diff_files` `contentEqual`, merge's three-way decision and merge-unit classification decided "content changed" from unequal content roots |
| Binaries | the run's SDK addon `4c52d23c` (with F-063); pre-F-063 addon `bf1cd303` (origin/main `6e8986ff46`); fixed addon `7a35c33c` (Linux, pinned image `378b799ef433`); runtime image `d3773b4e` |
| Commits | this commit; regression tests `core/crates/layerfs-api/tests/sdk_written_back.rs` |
| Recovery | none: no attempt reran. Probes ran on clones of `p3-main-x-b`'s Store, copied through a read-only mount (sha256 `e8c61042…`) |

## What happened

The file's first-parent history on the run's Store, read with
`operator.files.history`:

| Commit | Step | Size | Content root |
| --- | --- | --- | --- |
| `12cf9467…` | `r057.reconcile` (the r57 head's version) | 234,915 | `e6fffe32…` |
| `12c07208…` | `merge r058-3-apps-web` (lane `s0115`) | 227,085 | `6f66f1e2…` |
| `12a55361…` | `r058.reconcile` (the r58 head's version) | 234,915 | `2d001b97…` |

`diff_commits` from `12dbfee1…` (r57 head) to `12286c64…` (r58 head), as the
verify step paged it, gave this item:

```json
{"path":"/packages/cordis/tool-cordis/src/api-catalog.ts","kind":"Modified","type":"file",
 "before":{"type":"file","inode":699528},"after":{"type":"file","inode":699528},
 "content":true,"identity":false,"metadata":true}
```

It is the same inode, so no rename was involved. The checkpoint check accepts
a Modified file not in git's list only with `content: false`
(`steps.mjs` `comparePaths`), so the path counted as extra.

## Root cause

**A content root depends on how a file was built, not only on its bytes. The
difference took unequal roots to mean unequal bytes.**

- Both 234,915-byte versions were written by `fs.write` on the Store route,
  so F-063 never ran.
- Each write went through the F-005 localized-edit construction. The trace
  shows `edit.compare`, `edit.split`, `content.chunk` and `edit.finish`.
- A localized edit keeps the extents of the file it edits:
  - r57's version was built over a 221,356-byte predecessor;
  - r58's version was built over the lane's 227,085-byte one.
- The same bytes therefore got two mappings and two roots. CAS handbook §2
  allows this explicitly.
- `read/compare.rs` set `content` from
  `l.content_root != r.content_root`.

Fix 044's digest reuse does not apply here either way. It follows only fresh
inodes written by exact appends. An in-place `fs.write` over an existing file
is neither.

## Replay of the sequence

A clone of the r58 Store, one sample per arm. Each arm forks the r57 head,
writes the lane's bytes (blob `31b1793f`), then writes the checkpoint's bytes
back (blob `4d986582`), and diffs from the r57 head.

| Arm | Lane root | Write-back root | Item |
| --- | --- | --- | --- |
| pre-F-063 addon `bf1cd303` | `6f66f1e2…` | `2d001b97…` | `content: true`, `identity: false`, `metadata: true` |
| run addon `4c52d23c` (F-063 active) | `6f66f1e2…` | `2d001b97…` | the same |

Both arms reproduce the run's roots exactly, so the result is deterministic
and does not depend on F-063.

## Fix

The difference proves inequality instead of assuming it.
`layerfs_content::compare::same_file_bytes(reader, left, right, scope)`:

- Equal roots: equal, with no read.
- Different lengths: unequal, after one root read each.
- Otherwise it walks both files' extents together:
  - an extent both files take from the same chunk, at the same offset and
    chunk offset, is skipped;
  - everything else is read from both sides in windows of at most 256 KiB
    and compared. This covers misaligned extents, holes and whole-file roots.
  - It stops at the first window that differs, and holds at most two
    windows in memory.

`read/compare.rs` uses it, through `same_content`, only for two regular files
whose roots differ:

- the item's `content` flag;
- whether a same-inode pair with unchanged metadata is listed at all;
- `fs.diff_files`' `contentEqual` for files that are not text. Text files
  were already compared by their text.

### Merge (second commit)

Merge had the same false difference, in two places. Both now use
`compare::same_content` (kind and root, or for two regular files, the bytes).

- **`merge/decide.rs`, `Decider::same`.** This is the three-way rule:
  ours equal to theirs, or ours equal to the base, keeps ours; theirs equal
  to the base takes ours. Before, sides with equal bytes under different
  roots went on to the text merge. Text merged back to the same bytes, but
  the file was rewritten. A file that is not text, or text over 1 MiB,
  became a `Binary` conflict, and the merge was refused. The by-serial merge
  (#355 M1) reaches its "both changed" serials through this same rule.
- **`merge/units.rs`, `changed`** (F-057 merge units). A side counted a path
  as changed in its unit if its root differed from the base's. A side that
  only wrote a file away and back could therefore make a unit "changed by
  both". If that side's write was later, the other side's real changes in
  the unit were reverted. A metadata change (the write-back's time) still
  counts as a change, as before.

### The publication lane (third commit)

The liaison asked where each compare runs:

1. **Commit merge onto an advanced head: inside the lane.**
   `commit.rs` calls `merge_in_lane` → `merge_roots` with
   `bound: Some(LANE_MERGE_PATHS)`, under `publish_lane`. That reaches
   `Decider::same`, so an unbounded compare would make the hold grow with a
   file's size.
   - Now a bounded merge (`MergeInput::bound` set, which only the lane does)
     compares bytes only for files of at most `MAXIMUM_TEXT_BYTES` (1 MiB).
     That is the bound the lane's text merge already reads per side.
   - Above it, different roots count as different, as before F-073. A
     large binary file both sides rewrote to the same bytes in that short
     window conflicts as it did before. No pre-lane result exists to reuse
     there, because the in-lane step decides only what landed after the
     pre-lane merge.
   - The pre-lane merge (`merge_candidate`) and `branch.merge` stay
     unbounded. Neither holds the lane: `branch.merge`'s hold is its one
     publish write.
2. **Merge-unit classification: never in the lane.** It runs only in
   `branch.merge`, before its publish (`history/units.rs`).
3. **Diffs: reads, no lane.**

Measured: `lane_merge.rs` `the_lane_does_not_compare_a_large_file_byte_by_byte`,
one sample each, host 1-min load 4.6.
- The case: 64 MiB files of the same length. The Workspace's and the
  landed Commit's differ only in the last byte. The base differs from both
  at the first byte.

| Lane rule | Lane hold | Writer statements | Reply |
| --- | --- | --- | --- |
| bounded (this commit) | 0.84 ms | 26 | Conflict (binary) |
| unbounded (`366f23222b`) | 1.75 ms | 41 | Conflict (binary) |

- **Why the unbounded arm was also cheap.** Content-defined chunks
  re-synchronize, so the two files share every chunk but the last, and the
  compare skips shared extents.
- **The true worst case** is equal bytes under misaligned extents, where
  every window is read. Two full reads of a 64 MiB chunked file take 142 ms
  in memory on this host (release, one sample), more from the Store. The
  bound caps it at 2 × 1 MiB per path.

### Options weighed

| Option | Cost | Verdict |
| --- | --- | --- |
| (a) Store a whole-file digest for every file version and compare digests when roots differ | Every in-place edit must hash the whole file. A localized edit reads only its windows today (#316 requirement: edit cost independent of file size). Chunk ids cannot be combined into a whole-file BLAKE3, so this is O(file size) per edit, or a format change to a chunk-level digest tree. It needs a new per-version table, and older versions have no digest, so (b) is still needed for them | rejected: it moves the cost onto every write, the common case, for a rare comparison |
| (b) Compare bytes when roots differ | Only when two regular files have different roots and the same length. Shared extents are skipped, and it stops at the first differing window | **chosen** |
| (c) Make the edit path produce the plain-build root for the same bytes | It changes what a root identifies. Every edit would have to rebuild the CDC layout over the whole file: O(size), and the predecessor's extent reuse (F-005) would be lost | rejected: changes identity and edit cost |

Measured for (b): r58's own checkpoint diff, below, took 11.3 → 9.5 s,
one sample each. For the cost (a) would move onto writes: the r58
reconcile's 234,915 B in-place `fs.write` spent 3.5 ms in `files.change`.
A whole-file hash adds O(size) to every such write and grows with the
file. (b) pays only when roots differ and lengths are equal.

## Proof

**`sdk_written_back.rs`** (three tests). In each, Init saves a 400 KiB file,
and an edit gives the start version an edit-built root, as r57's reconcile
did. Then:

1. **Store route** (`fs.apply`): an edit elsewhere, then the start bytes
   written back.
   - The edit is listed with `content: true`.
   - Start to write-back: no content change. `fs.diff_files` answers
     `Equal`, `contentEqual: true`.
   - A same-length change of the last byte is still `content: true` and
     `contentEqual: false`.
2. **Rename-over** (a Workspace `<name>.save` then rename, the liaison's
   case): the edited bytes, then the start bytes saved over the path.
   - The write-back is listed for its new inode (`identity: true`) with
     `content: false`.
   - `contentEqual` is true.

3. **Merge**: two Branches from the start version both end at the same
   bytes, built over different predecessors (one edit; or another edit, then
   that one). The bytes are not text.
   - `fs.diff_files` reports them equal.
   - `branch.merge` succeeds (`Merged`), and the merged file holds those
     bytes.

Without the `read/compare.rs` change, tests 1 and 2 fail with the run's item
shape: `content: true`, plus `identity: true` for the rename. Without the
merge change, test 3 fails:
`Conflict: ours + theirs conflict in 1 file(s); nothing was created`. With
the changes, all three pass.

**The run's own checkpoint.** `diff_commits` `12dbfee1…` → `12286c64…`, all
pages, on the r58 clone, one sample per addon, host 1-min load 5.4:

| Addon | Items | Files | Modified files with `content: false` | `api-catalog.ts` | Wall time |
| --- | --- | --- | --- | --- | --- |
| run `4c52d23c` | 74,378 | 65,018 | 64,148 | `content: true` | 11.3 s |
| fixed `7a35c33c` | 74,378 | 65,018 | 64,149 | `content: false` | 9.5 s |

Only that path changed. The byte check costs no visible time on the real
checkpoint; the 1.8 s difference is within one-sample noise. The fixed addon
was built before `pair_differs` was rewritten for Clippy. The rewrite has the
same logic.

## Checks

- Clippy `-D warnings`, `--all-targets`, on content, store-service and api:
  host `+1.85.1` passes; Linux (image `378b799ef433`) passes.
- Tests, each run ≤120 s:
  - content: 485 passed, 2 ignored;
  - store-service: 3 passed;
  - layerfs-api: all 42 integration binaries pass (they share the changed
    test support), including `sdk_written_back` (3);
  - layerfs-daemon `lane_merge`: 5 passed, including the new 64 MiB case.
- Boundary guard: the same 57 violations as origin/main. Tool self-tests:
  50 ok.
- rustfmt: the changed files are clean.

## Left open

- **In-lane merge, files over 1 MiB.** These still compare by root, as
  above. The next Commit's pre-lane merge compares their bytes.
- **`root_changes`** (`commit_merge.rs`, the paths a conflicted Commit
  merge wrote) still compares roots. It is informational, in a reply that
  already reports conflicts.
- **The daemon's `operator.workspace.changes`** still compares roots. It
  is a diagnostic.
- **`sandbox.status`** reports dirty overlay counts and compares no roots.
- **`operator.files.history`, `files.stats` and `fs.blame`** count a
  rewrite to the same bytes under a new root as a revision. That is a
  history listing, not a correctness check, and is left as is.
- **Mapping structure.** I did not decode the two roots' extent layouts
  from the Store. The trace's construction counters show what differs:
  - the r58 write-back saved 40,421 new canonical bytes;
  - r57's root `e6fffe32…` is not reused by it.
