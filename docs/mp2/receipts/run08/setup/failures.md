# Retained check and harness failures

- Initial warm stat selection used `stat --printf=`. All 20 samples completed
  but did not perform per-file stat work (19 had zero FUSE requests; one60): INELIGIBLE, retained in hot/. Corrected to
  `--cached=never --printf=%s\n`; only stat was rerun in hot-stat/.
- fix-checks.log: duplicate --all-targets in the second Clippy invocation;
  command rejected before compilation. Earlier Fuse/daemon tests and fuser
  Clippy passed and were not repeated. Corrected selector in fix-checks02.log.
- fix-checks02.log: scoped Clippy passes; workspace formatting fails on
  unchanged files. Scoped changed Rust files pass in fix-checks03.log.
- fix-checks.log: boundary guard FAIL with 57 unchanged findings. No suppressions.
- A local result summarization snippet mistakenly expected a `seconds` field;
  actual sample schema is integer `ns`. It raised KeyError before producing a
  summary. Corrected parsing reads `ns / 1e9`; no samples were rerun or altered.
- cp/tar/rsync ownership failures and the missed ctime oracle are retained in
  their respective results and syscall traces, not replaced by clean runs.

- Correction cohort baseline stat sample1 has11,227 FUSE requests; all other stat
  samples have4,869. Retained in the10-run result, no resample. Exact extra opcodes
  were not captured; this limits equal-request-rate qualification.

- summary-v1-failure.log: analysis parser rejected nine split strace syscall
  lines. Corrected parsing correlates unfinished/resumed lines by TID; only
  existing receipts were recomputed, no native cycle rerun.

- Raw receipt whitespace check exits2 on preserved apt CR progress lines and
  rustfmt diff context blanks. `raw-receipt-whitespace.log` retains the full
  diagnostic. Product/docs/harness whitespace is checked separately, excluding
  immutable raw receipts; their bytes are not reformatted.
