# Released reference catalogue

> **Status:** Archived; retained for historical evidence only.

`reference.csv` copies all 461 rows of the three sources named in section 8
of the [implementation spec](../../../../core/docs/benchmark/fs-bench-pro/implementation-spec.md):
36 v0.1.6 performance rows, 198 v0.1.5 performance rows and 227 v0.1.5
verification rows. Each row retains its source file, physical CSV row (header
is row 1), SHA-256 and complete original row as JSON. Empty observations stay
empty. Historical status, omissions, profile and seals remain in that JSON;
no historical disposition is recalculated.

The directory name identifies the frozen workload definition; `release`
identifies the product that produced each number. The label is **reference
from release X, different topology and clock**. There is no ratio or comparison
verdict in this catalogue.

The v0.1.6 record uses complete command wall in seconds with host Store/SDK and
Linux FUSE. Its seed-1 samples reused closed prepared masters with independent
byte copies. Original declarations and exceptions are retained in each source
row. See the [released closeout](../../../../release-notes/0.1.6/benchmark-closeout.md).

The v0.1.5 record uses product-call sums or operation-specific timers; the
verification wall is a different clock boundary. Its warm prepared clone
profile, exceptional verified-cold namespace member, reused producing treatments
and historical WARN/FAIL/waiver dispositions stay as released. The CSV's
`reference_profile` describes its older v0.1.3 comparison and is not a new
v0.1.5 cache claim. See the [released closeout](../../../../release-notes/0.1.5/benchmark-closeout.md).

Second-valued observations keep their original decimal text and use labelled
decimal unit conversion into integer nanoseconds (sub-nanosecond digits are
truncated). This adds no precision. v0.1.5 `candidate_ns` is copied as published;
`candidate_receipt_ns`, when present, is preserved separately in the original
row and never silently substituted. Unrecorded seals remain empty.

Reproduce the catalogue using `engine.receipts.released_references`; the owning
test compares every field against the three frozen source CSVs. No reference
product is built or executed by harvesting or testing this catalogue.
