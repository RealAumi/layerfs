# fs-bench-pro release data

> **Status:** Current general guide.

One folder per release that published fs-bench-pro results, each holding that
release's `benchmark-performance.csv` and `benchmark-verification.csv`. They are
byte-for-byte copies of the files in `release-notes/<version>/`, which stay the
release record; nothing here is recomputed. The website's benchmark pages read
these files.

| Release | Cases | What one number is | Release record |
| --- | ---: | --- | --- |
| [v0.1.4](v0.1.4/) | 198 | each case's own timer, against an absolute target | [closeout](../../../release-notes/0.1.4/benchmark-closeout.md) |
| [v0.1.5](v0.1.5/) | 198 | each case's own timer, against the v0.1.3 reference | [closeout](../../../release-notes/0.1.5/benchmark-closeout.md) |
| [v0.1.6](v0.1.6/) | 36 | the complete command wall, against the 15 s family target | [closeout](../../../release-notes/0.1.6/benchmark-closeout.md) |

All three were measured by the v0.1.6-era harness against the reference
implementation that R9c retired; reproduce a row from tag
`reference-v0.1.6-final`. The core port of the suite,
[benchmark/fs-bench-pro](../../fs-bench-pro/AGENTS.md), is
frozen and broken (#352 F-020); it does not run at HEAD. v0.1.7 published no benchmarks; 1.0.0 results wait on issue #332.

To add a release, create `v<version>/` with that release's two CSVs, copied
unchanged from its release notes.
