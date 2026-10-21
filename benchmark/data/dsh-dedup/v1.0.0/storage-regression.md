# dsh-dedup v1.0.0 — storage regression

> **Status:** Open, recorded 2026-10-20. The owner accepted the v1.0.0 results
> as they are; this record keeps the regression visible. Nothing here changes a
> receipt or an old verdict.

The v1.0.0 Stores are larger than the last in-process history results
(2026-10-07, source `6af972dc0`, Disposable), and the gap grows with the
number of Commits. At stride 1 the Store is above the old approved ceiling.

| Stride | Commits | 2026-10-07 in-process | v1.0.0 (SDK) | Δ bytes | Δ % | Old approved ceiling | Within it |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10 | 16 | 50,692,096 | 53,125,120 | +2,433,024 | +4.80 | 54,278,964 | yes |
| 3 | 52 | 64,245,760 | 69,455,872 | +5,210,112 | +8.11 | 70,427,034 | yes |
| 1 | 156 | 85,172,224 | 100,085,760 | +14,913,536 | +17.51 | 92,342,273 | **no** (+7,743,487) |

All three also miss the original targets (49,344,512 / 64,024,576 /
83,947,520 B), as the 2026-10-07 results did. Against Git (pack + index of
the same trees) the Store is 1.27× / 1.44× / 1.82×.

## Where the bytes are

`store.json` (the closed Store's own totals) splits each v1.0.0 Store:

| Stride | Allocated | Payload (`stored`) | Metadata (Commits + Init) | Other |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 53,125,120 | 41,472,751 | 1,325,047 | 10,327,322 |
| 3 | 69,455,872 | 51,897,185 | 2,457,063 | 15,101,624 |
| 1 | 100,085,760 | 67,488,833 | 5,507,608 | 27,089,319 |

"Other" is allocated minus payload minus metadata: history rows, signatures,
the object index, B-tree interior pages and page slack. It grows by about
0.12–0.13 MB per added Commit and is 27% of the stride-1 Store. Payload grows
far more slowly (+26 MB from 16 to 156 Commits).

One older receipt hints that the payload is not where the regression is. The
#286 stride-10 r007 run (2026-09-30, older source, two database files) reports
45,326,352 B of pack bodies and 1,091,760 B of framing in a
51,720,192 B Store, leaving about 5.3 MB other. v1.0.0's stride-10 payload is
smaller (41.5 MB) and its other bytes about twice as large (10.3 MB). This is a
different source, layout and measurement; it is a pointer, not a result.

## Differences from the old run (none isolated)

| | 2026-10-07 in-process | v1.0.0 SDK route |
| --- | --- | --- |
| Driver | Rust example calling content/storage/persistence directly | public JS SDK, Sandbox, FUSE mount, daemon Commit |
| Pack layout | GroupRowsIndexed | Monolithic (SDK Init's only layout) |
| Depth (whole file / chunk / metadata) | 8 / 4 / 8 | 16 / 8 / 8 |
| Delta predecessors | every changed file, at its path | same-inode in-place edits only (Commit's own) |
| Similarity lookup | off | on |
| History | example-only catalog | Branch Commits, one global Store |

Deeper chains should lower payload, not raise it; the likely contributors are
the pack layout and per-Commit history/index rows. Neither is confirmed.

## Next step

Break the stride-1 Store down by table and index (for example SQLite's
`dbstat` on a closed copy of a fresh stride-1 Store), without changing product
code, and attribute "other" before any fix is chosen. Any fix is a product
change with its own measurement under a new run ID; v1.0.0's data stays as
recorded.
