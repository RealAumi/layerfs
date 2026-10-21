# Upstream merge qualification

> **Status:** Dated local qualification of `c5925f3f5`; not a release or reliability claim.

The product tree is unchanged throughout this round: merge `c5925f3f5`, core
tree `8d0076c40b05660ad11310730cb8595ecb727818`. The rewritten pre-merge tip is
`1fd693a95`; [published-history.md](../../published-history.md) maps historical
receipt IDs. No Git configuration, backup refs, remotes or publication changed.

## Mac

- Locked, all-target `--no-run` build passes for store-service, remote-store,
  daemon, bridge and API. Frozen benchmarks were excluded.
- **72 requested tests pass:** ignore 42 (including 200 deterministic seeds × 30
  steps), restore/cache 12, transport five, control codec four, mount control nine.
- **Nine upstream regressions pass:** `sdk_written_back` three,
  `write_refusals` one, `lane_merge` five. See [semantics.md](semantics.md) for
  file/function review of all four upstream commits and the unchanged oracle.
- Fuser integrity exits 0 with no errors on both tips; authorized patches verify.
  `registry_package_verified: false` on both is expected: `main` only runs
  `package_errors` and sets that field true when all three optional inputs
  (`--archive`, `--package-directory`, `--locked-checksum`) are supplied.
  These checks omitted them. The merged checker scans 87 manifests/locks/configs,
  versus 94 before merge, following upstream benchmark deletion. STOP/EXCLUSIVE
  verification remains intact. This is not evidence that a registry package was checked.

All commands/results are under [mac/](mac/). The worktree launcher registered a
private Mac Cargo home and used this checkout's target. Its toolchain constant
was overridden only in the invocation wrapper to installed **1.98.1**, as in
ignore08/ignore10; no repository toolchain or Git configuration changed. Preparation
fetched locked dependencies; checks were offline/locked. Test builds precede
execution, which has a 100-second launcher deadline. Store tests select Disposable;
Durable was not run. Root ARM64 Cargo flags are unchanged.

The first pre-merge fuser attempt used a file export without a Git index and failed
before checking. `mac/fuser-premerge.json` retains that setup failure. A private
index populated from the exact tip fixed the checker setup; the indexed result is
`mac/fuser-premerge-indexed.json`. Neither repository refs nor index were changed.

## Linux and the one e2e run

Local OrbStack, Rust **1.85.1**, jobs=2, one construction worker, existing private
`cxi-target`. The original harness built both CLI binaries, daemon and driver;
[identities.json](identities.json), [tested-identities.txt](tested-identities.txt)
and [build/](build/) pin source, configuration, image and binaries. Product source
was exactly `c5925f3f5`; the dirty diff was receipt tooling, not core code.

The **first and only** full invocation passed **11/11 scenarios, 185/185 checks**
in 83.56 seconds under a 120-second deadline. Includes moved head, server rule
flip, server delete, remount/restart, missing leaf and missing root fallback.
[results.json](results.json) and [e2e-invocation.log](e2e-invocation.log) retain it.
No scenario or Docker e2e was rerun.

All 25 mounted Workspaces are accounted for in [unmounts.md](unmounts.md):
**23/23 explicit unmounts succeeded**, each recorded once (34.56–87.96 ms control
round trip). Two live Workspaces ended in the restart scenario's SIGKILL and had
**no explicit unmount attempt**. They are not clean-unmount passes. This run does
not establish that the intermittent unmount problem is fixed. Uncontrolled host
and OS-cache state also makes these single durations unsuitable as a performance
comparison or latency guarantee.

## Receipt hygiene and harness-only change

All three Docker resource listings filter `name=cxi-` before execution. Text
receipt writers redact the current home to `~`. Copied daemon logs use a temporary
file and the same redacting writer, including logs copied from the stopped daemon.
The existing eleven scenario ASTs are unchanged; before/final AST records are kept.
No production fix was needed.

The full e2e ran after listing/text redaction but before the copied-log hook was
finished. Its actual copied logs contain no home paths; the audit is zero. A
synthetic copied-log test exposed the uncovered writer afterward; its failure is
committed in `06062b9`, then the hook makes all **three local hygiene tests pass**.
The fix changes receipt handling only and was not grounds to repeat the e2e.
The initial audit script also lacked `docker cp` classification; its setup error
is retained in `audit-setup-failure.log` before adding that command form.

[audit-hygiene.py](audit-hygiene.py) literal-greps every new receipt for the home
path and validates every recorded Docker resource argument/listing and mount
container identity. **Home-path matches: 0; non-`cxi-` resource names: 0.**
The final counts and checked names are in [hygiene-final.json](hygiene-final.json).
The copies of test failures redact private strings too; their failure verdicts
remain unchanged. Raw Cargo logs retain trailing blank lines.

## Cleanup and remaining limits

The harness removed all its containers, networks and writable data volumes.
Filtered cleanup receipts show no containers/networks and only **cxi-target**.
No other job's runtime resource was listed in the publication receipts or touched.
Linux binaries and receipts remain pinned for review.

Host headroom was 13.18 GB initially. The required 300 GB cleanup episode could
not be satisfied within this job's scope. Initial exact-scope plan had no safe
candidates while builds were active. At handoff the launcher exported this job's
Mac compiler cache for release; apply refused **“Cache changed since plan;
preserve the whole profile”**, removed nothing and was not retried. The sanitized
own-job result is [cleanup-mac-report.json](cleanup-mac-report.json). Around 10.84 GB
remained then; this is an unresolved space shortfall, not successful reclamation.
Other allocations are protected or outside this job's established ownership.
Temporary pre-merge source/index exports were removed after recording checks.

## Production LOC / commits

Counter: `tools/production_loc.py` at `c5925f3f5`, identical `git archive` exports
of first parent and final staged tree for `core/crates`, `sdk/js`, `dsh/packages`;
excludes tests, tooling, docs and inline test items.

- `06062b9`: **111301 → 111301 (+0)**; initial receipt hygiene and failing copied-log test.
- Final qualification/copy-hook commit: **111301 → 111301 (+0)**.

Core 100449, SDK 2928, dsh 7924 in both. Reference absent (retired R9c; last counted
65,417 at tree `498dd1917812`). **Production lines changed: 0.** No merge-induced
break was confirmed, no product fix or new dependency was introduced, and nothing
was pushed.
