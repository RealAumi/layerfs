# dsh-dedup probe — 20261019T204353Z

> **Verdict:** diagnostic, one sample, SDK tracing on. It settled the route
> before the suite was built; its numbers are not results.

States 1–5 of the 157-checkpoint corpus (ordinals 100–500), through the JS
SDK only: `project.init` of state 1 with policy 16/8/8, then per state one
`sandbox.exec` applying it in place, one `sandbox.exec` verifying it against
the oracle and one `sandbox.commit`. Same binaries as the suite
(`e5c7aaae05`); probe image `sha256:188754f1673c…` (states 1–5 only); load
about 12. The probe's own scripts (`probe/probe.mjs`, `probe/run-probe.sh`)
were folded into `client/` and `run.sh`; its receipts are in
`benchmark-results/dsh-dedup/probe-20261019T204353Z/`.

The tiny corpus (`tiny/`, about 29 bytes per state) was not used: every file
is under the 128 KiB small-file cutoff, so it cannot show chunk deltas.

## Findings

1. **In-place overwrite gives chunk deltas.** `pnpm-lock.yaml` (169–183 KB,
   above the cutoff) changes in place in states 3–5. The trace's delta
   counters show delta chunks in those Commits: `chunk_depths` [0, 1],
   [0, 3] and [0, 0, 1] (state 2's 9 chunks are full: new large files).
2. **Whole-file deltas** were chosen for 128–220 objects per Commit, with 33–66
   full copies where no candidate existed.
3. **`branch.fork` accepts a Commit id.** Forking state 3's Commit, mounting
   it and verifying it against state 3's oracle passed. The suite's history
   proof uses this.
4. Every live state matched its oracle.

| State | Commit ms | newCanonical | newStored | Chunk delta objects | Whole-file delta / full |
| --- | ---: | ---: | ---: | --- | --- |
| Init (1) | 209 | 1,537,477 | 507,340 | — | — |
| 2 | 75 | 1,436,608 | 231,491 | 0 (9 full) | 130 / 39 |
| 3 | 70 | 1,563,357 | 172,976 | 1 (depth 1) | 128 / 37 |
| 4 | 126 | 2,161,870 | 363,025 | 3 (depth 1) | 220 / 66 |
| 5 | 94 | 1,973,199 | 196,781 | 1 (depth 2) | 220 / 33 |

Final Store 2,056,192 B allocated for 11,973,660 logical bytes.
