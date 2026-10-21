# Storing everything versus `ignore=git`

> **Status: Research; informative and not a product contract.**
> Local experiment, 2026-10-21. Every measured case/arm is one sample.

The measured incremental cost of storing everything was modest in these two
workloads. Across ten edits, Vite added 184,320 B more Store space and 38.55 ms
more total Commit time than `ignore=git`; Petclinic added 1,163,264 B and 0.996 s.
Maven resumed successfully without rebuilding in `off`. Node's resume test
failed in both modes, so this experiment does **not** establish reliable Node
resume or an unconditional recommendation to drop ignore.

The owner's separate cache-Branch design worked with **one daemon and two
Workspaces**. A cold machine mounted writable forks of both Branches and passed
Maven's offline tests. The new dependency was saved only to the cache fork;
readback proved the base cache did not acquire it. No second daemon or merge-back
was needed.

## Attempt 1 and retained failures

Attempt 1 selected Nest at `35c3ded6dbf3f23f917ae88d0ed966932788cae6`
(`v11.1.6`). Its unmodified `npm ci` failed after 2.970712042 s with ERESOLVE:
`@nestjs/graphql@13.1.0` excludes the root's `ts-morph@26.0.0` peer version.
No force flag, dependency adjustment or lockfile edit was applied. This is
valid evidence that this pin did not install with the selected npm invocation,
not a verdict on LayerFS or ignore.

The original 66 receipt files remain byte-for-byte unchanged after the owner's
correction. [Attempt-1 seal](receipts/noignore01/attempt2/attempt1-seal.json),
[install failure](receipts/noignore01/node2-install.log),
[complete npm log](receipts/noignore01/npm-debug.log).

Attempt 2 selected Vite, which installed cleanly using its frozen pnpm lockfile.
Its initial cold test failed because the harness had built only Vite, leaving
`create-vite` unbuilt, and Node 22's native TypeScript behavior differed from the
pinned test's expectation. That failed sample is retained. The revised treatment
used Node 20.19.0 and the full monorepo build, reusing the closed, installed base;
there was no unchanged-workload rerun selected as a replacement success.
[Initial cold failure](receipts/noignore01/attempt2/v2-vite-off2-S2-test.log.gz),
[revised build](receipts/noignore01/attempt2/v2-vite-fullbase-build.log),
[selection changes](receipts/noignore01/attempt2/workload-corrections.json).

## Method and scope

| Item | Selection |
| --- | --- |
| off source | `af9f2cec80b19d4613eec1e48b79c8a1cff93e14`, upstream behavior |
| on source | `801e9360fdbd177e8e126b89f2730bb9b5213d44`, `ignore=git`; no restore key supplied |
| Vite | [vitejs/vite](https://github.com/vitejs/vite), `051370a332df99d107365ed6beab418ef017eff6` (`v6.1.0`); pnpm 9.15.5 |
| Petclinic | [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic), `500158f732419217507c7656904b8e6aa1bcc0d6`; Maven 3.8.7, Java 17 |
| Daemons | Rust/Cargo 1.85.1, Linux ARM64, locked release builds, `-j 2` |
| off daemon SHA-256 | `eaf5c38b2719057633e4b163f44419adee906a01c34728fa814c128295d4e90d` |
| on daemon SHA-256 | `bfd1d36ae1d3f97b0cab192b90a02aa5307295535294cafa65f88aa82c3a9efe` |
| Store | Explicit Disposable / WAL / synchronous OFF; one construction worker |
| Runtime | This Mac's local Docker VM only; no remote execution or added network latency |

Both modes start from the same closed warm-base Store for their repository.
The base builder stores everything in both cases. The `on` source was built from
a separate archive, verified against Git blobs, then deleted. `cxi-target` was
reused for Cargo; an arm-specific target avoided stale cross-arm artifacts.
Build failures and harness setup refusals remain in their original logs.
[Build records](receipts/noignore01/preparation-commands.jsonl),
[archive proof](receipts/noignore01/archive-verification.json),
[attempt-2 commands and samples](receipts/noignore01/attempt2/events.jsonl).

The comparison is between the requested source trees, not one binary with a
flag toggle. No LayerFS production code, dependencies or existing Git
configuration changed. Only harness and docs under `docs/mp2/` are added.
Durable execution was **NOT_RUN — disabled by owner**. The frozen benchmark
was not built or run.

Workloads use ordinary filesystem access through FUSE; commands are externally
launched, with no Exec registration required. Commits are explicit. Branch and
Store operations use the public SDK method table in a process opening the Store
locally. Each arm owns a separate byte copy of the closed Store. Maven's external
cache volumes are also independent copies per arm, shared only between that
arm's machines, preventing S5 downloads from warming the other arm.

`/.lww` contains `%include .gitignore` and is excluded through
`.git/info/exclude`. S8b additionally lists `.m2/` in both the exclude and LWW
files. S8c mounts a separate cache Workspace read-write at `~/.m2`, then commits
cache and repo separately. Its fresh machine forks both Branches, and the cache
fork is never merged back.

**Timing:** `work` is external Docker-exec launch-to-exit. `Commit` is the
product control client's reported wall time; SDK merge time is its method-call
time. S2/S6 include mounting and the ensuing commands, after container/daemon
readiness. Exact command-only times are also retained. S6 `on` explicitly
reinstalls/rebuilds before testing; these are scripted recovery times, not a
claim about the fastest possible recovery. All test invocations have explicit
110-second limits; none reached the limit.

**Bytes:** uploaded means acknowledged canonical object payload, excluding
framing. Fetched means actual Store-to-daemon ciphertext, including protocol
and metadata, excluding public Git/package downloads. Store growth is SQLite
logical page allocation (`page_count × page_size`), not just new compressed
payload; physical main/WAL/SHM sizes remain in the raw snapshots. Zero growth
can mean reuse of allocated pages. Edit/build rows span the mutation through
Commit, including reservation effects. Server-local SDK merges have no daemon
transfer metric; their Store-growth interval also includes the preceding
unmount. `—` means unavailable or inapplicable, never zero.

**Cache and statistics:** fresh machines have empty local object/package caches;
S8a intentionally retains its shared Maven cache volume. Server OS cache is
uncontrolled. No warm-up or unchanged treatment resampling was used to select
numbers. Initial setup, source/config corrections and the separate native cause
diagnostic are labeled separately. Small read-only diagnostics and cleanup
sometimes overlapped public dependency downloads; paired test/Commit/build
selections ran sequentially. These are workflow observations, not cold-OS-cache
or release-performance admission. `PASS` in derived receipts denotes functional
command outcome only; the timings are diagnostic and performance-admission-ineligible. Sums below combine ten distinct single-sample
edits, not repeated samples of one case.

Vite's frozen install created 37,152 files in root `node_modules`; the complete
Workspace had 71,573 regular files before the revised full build, meeting the
requested scale. The edit loop changes one TypeScript source file and runs an
incremental declaration build with persistent tsbuildinfo. Clean rebuild removes
Vite's `dist`/`temp` and runs the full package builds. S5 adds `decimal.js@10.4.3`.
Petclinic changes one Java source file, uses offline incremental packaging,
cleans `target` for S4, and adds `com.google.zxing:core:3.5.3` for S5. The new jar
is proved absent before addition. Offline tests select the real `ValidatorTests`
unit class, avoiding external databases/services. Matched post-S5 source and
manifest hashes were verified across modes.

## Node results

All measured cells are **single samples**. Bytes are exact. Times are seconds.

| Scenario | Mode | Time (s) | Uploaded B | Fetched B | Store growth B | Notes |
| --- | --- | --- | ---: | ---: | ---: | --- |
| S1 shared warm base | off builder | clone 3.954; install 58.422; builds 7.363 + 18.515; Commits 18.452 + 0.077 | 512,651,948 | 52,033,562 | 189,661,184 | Initial partial build/Node 22 cold test failed; full build revised on Node 20, reusing installed base. Final 71,585 files / 1,182,803,886 B. |
| S2 cold mount + test | off | 6.037 | 0 | 37,860,746 | 0 | No reinstall |
| S6 mount → tests finish | off | 5.887 FAIL | 0 | 37,997,907 | 0 | Failed test; not time to pass |
| S3 edit 01 | off | work 2.619; Commit 0.053 | 175,280 | 12,723,215 | 73,728 |  |
| S3 edit 02 | off | work 2.358; Commit 0.020 | 132,878 | 1,040 | 24,576 |  |
| S3 edit 03 | off | work 2.406; Commit 0.022 | 132,879 | 1,040 | 24,576 |  |
| S3 edit 04 | off | work 2.373; Commit 0.020 | 132,880 | 1,040 | 20,480 |  |
| S3 edit 05 | off | work 2.375; Commit 0.020 | 132,881 | 1,040 | 24,576 |  |
| S3 edit 06 | off | work 2.393; Commit 0.020 | 132,882 | 1,040 | 28,672 |  |
| S3 edit 07 | off | work 2.432; Commit 0.020 | 132,883 | 1,040 | 24,576 |  |
| S3 edit 08 | off | work 2.364; Commit 0.020 | 132,884 | 1,040 | 24,576 |  |
| S3 edit 09 | off | work 2.436; Commit 0.020 | 132,885 | 1,040 | 24,576 |  |
| S3 edit 10 | off | work 2.453; Commit 0.020 | 132,888 | 1,040 | 24,576 |  |
| S4 clean build | off | work 16.641; Commit 0.064 | 53,773 | 23,005,467 | 57,344 |  |
| S5 dependency change | off | work 17.170; Commit 0.068 | 664,099 | 1,393,249 | 323,584 |  |
| S2 cold mount + test | on | 5.718 | 0 | 37,937,372 | 0 | No reinstall |
| S6 mount → tests finish | on | 25.880 FAIL | 0 | 74,061,358 | 0 | Failed test; not time to pass |
| S3 edit 01 | on | work 2.752; Commit 0.056 | 30,041 | 13,007,798 | 32,768 |  |
| S3 edit 02 | on | work 2.304; Commit 0.017 | 12,838 | 887 | 8,192 |  |
| S3 edit 03 | on | work 2.366; Commit 0.014 | 12,839 | 887 | 8,192 |  |
| S3 edit 04 | on | work 2.289; Commit 0.015 | 12,840 | 887 | 8,192 |  |
| S3 edit 05 | on | work 2.456; Commit 0.015 | 12,841 | 887 | 8,192 |  |
| S3 edit 06 | on | work 2.540; Commit 0.016 | 12,842 | 887 | 12,288 |  |
| S3 edit 07 | on | work 2.507; Commit 0.015 | 12,843 | 887 | 8,192 |  |
| S3 edit 08 | on | work 2.546; Commit 0.016 | 12,844 | 887 | 8,192 |  |
| S3 edit 09 | on | work 2.562; Commit 0.015 | 12,845 | 887 | 8,192 |  |
| S3 edit 10 | on | work 2.515; Commit 0.017 | 12,847 | 887 | 8,192 |  |
| S4 clean build | on | work 17.910; Commit 0.039 | 0 | 23,160,736 | 0 |  |
| S5 dependency change | on | work 16.988; Commit 0.069 | 210,600 | 1,295,415 | 106,496 |  |
| S7 rebuild left | off | work 19.445; Commit 0.093 | 174,140 | 51,828,215 | 69,632 |  |
| S7 rebuild right | off | work 17.741; Commit 0.077 | 186,043 | 18,575 | 61,440 |  |
| S7 generated merge | off | SDK 0.013 | — | — | 4,096 | 3 LWW decisions; no conflicts. Growth interval includes preceding unmount; SDK is Store-local. |
| S7 source-control left | off | work 0.048; Commit 0.014 | 15,311 | 818 | 16,384 |  |
| S7 source-control right | off | work 0.042; Commit 0.011 | 15,312 | 819 | 8,192 |  |
| S7 source conflict | off | SDK 0.003 | — | — | — | Expected Conflict; no merge Commit |

## Maven results

All measured cells are **single samples**. Bytes are exact. Times are seconds.

| Scenario | Mode | Time (s) | Uploaded B | Fetched B | Store growth B | Notes |
| --- | --- | --- | ---: | ---: | ---: | --- |
| S1 / S8a shared warm base | off builder | clone 1.421; install 414.735; build/test 11.728; Commit 0.911 | 69,412,328 | 14,171 | 64,937,984 | 360 repo files / 70,465,522 B; .m2 on separate shared volume. |
| S2 cold mount + test | off | 3.582 | 0 | 1,634,337 | 0 | No reinstall |
| S6 mount → tests finish | off | 3.311 | 0 | 1,648,509 | 0 | No reinstall |
| S3 edit 01 | off | work 3.765; Commit 0.500 | 563,887 | 1,207,273 | 163,840 |  |
| S3 edit 02 | off | work 3.559; Commit 0.457 | 150,938 | 7,238 | 126,976 |  |
| S3 edit 03 | off | work 4.301; Commit 0.553 | 159,970 | 6,495 | 131,072 |  |
| S3 edit 04 | off | work 4.131; Commit 0.452 | 145,731 | 6,495 | 114,688 |  |
| S3 edit 05 | off | work 4.126; Commit 0.415 | 151,048 | 6,499 | 126,976 |  |
| S3 edit 06 | off | work 3.983; Commit 0.442 | 151,182 | 6,499 | 126,976 |  |
| S3 edit 07 | off | work 3.713; Commit 0.442 | 151,316 | 6,499 | 126,976 |  |
| S3 edit 08 | off | work 3.784; Commit 0.447 | 164,941 | 6,498 | 131,072 |  |
| S3 edit 09 | off | work 3.808; Commit 0.411 | 146,051 | 6,495 | 118,784 |  |
| S3 edit 10 | off | work 3.721; Commit 0.467 | 150,843 | 6,498 | 122,880 |  |
| S4 clean build | off | work 3.740; Commit 0.605 | 354,698 | 151,762 | 303,104 |  |
| S5 dependency change | off | work 7.887; Commit 0.578 | 1,195,342 | 6,520 | 1,069,056 |  |
| S2 cold mount + test | on | 5.114 | 0 | 1,634,535 | 0 | No reinstall |
| S6 mount → tests finish | on | 9.118 | 0 | 1,827,495 | 0 | Recovery includes reinstall/rebuild |
| S3 edit 01 | on | work 4.511; Commit 0.481 | 16,898 | 1,201,904 | 24,576 |  |
| S3 edit 02 | on | work 4.349; Commit 0.342 | 5,838 | 886 | 4,096 |  |
| S3 edit 03 | on | work 4.326; Commit 0.450 | 5,838 | 886 | 8,192 |  |
| S3 edit 04 | on | work 4.304; Commit 0.322 | 5,838 | 886 | 8,192 |  |
| S3 edit 05 | on | work 4.063; Commit 0.331 | 16,906 | 890 | 16,384 |  |
| S3 edit 06 | on | work 3.935; Commit 0.315 | 5,838 | 886 | 8,192 |  |
| S3 edit 07 | on | work 4.112; Commit 0.303 | 5,838 | 886 | 4,096 |  |
| S3 edit 08 | on | work 3.887; Commit 0.321 | 17,040 | 890 | 16,384 |  |
| S3 edit 09 | on | work 4.059; Commit 0.376 | 17,150 | 889 | 16,384 |  |
| S3 edit 10 | on | work 4.156; Commit 0.349 | 17,285 | 963 | 20,480 |  |
| S4 clean build | on | work 4.637; Commit 0.312 | 12,113 | 146,038 | 12,288 |  |
| S5 dependency change | on | work 7.774; Commit 0.307 | 20,749 | 886 | 8,192 |  |
| S7 rebuild left | off | work 3.236; Commit 0.620 | 165,820 | 2,203,651 | 135,168 |  |
| S7 rebuild right | off | work 3.902; Commit 0.446 | 139,429 | 188,288 | 86,016 |  |
| S7 generated merge | off | SDK 0.004 | — | — | 4,096 | 4 LWW decisions; no conflicts. Growth interval includes preceding unmount; SDK is Store-local. |
| S7 source-control left | off | work 0.038; Commit 0.005 | 5,743 | 817 | 20,480 |  |
| S7 source-control right | off | work 0.037; Commit 0.005 | 5,744 | 818 | 4,096 |  |
| S7 source conflict | off | SDK 0.002 | — | — | — | Expected Conflict; no merge Commit |
| S8b repo-local .m2 | off | install 422.889; build 8.848 FAIL | 0 | — | — | 3,757 NoHTTP violations in downloaded POMs; no warm-base Commit or cold sample |
| S8c base, two Workspaces | off | install 422.994; build/test 12.931; cache Commit 3.855; repo Commit 0.721 | 235,354,623 | 155,194 | 213,155,840 | One daemon; 3,823 cache files / 226,857,786 B. |
| S8c cold repo + cache forks | off | 6.662 | 0 | 56,602,286 | 0 | No reinstall |
| S8c thread fork | off | 0.077 | 0 | — | 0 | Independent writable Branch; metadata-only fork |
| S8c cache-thread fork | off | 0.047 | 0 | — | 0 | Independent writable Branch; metadata-only fork |
| S8c S5 complete change | off | work 9.566; Commits 0.717 | 1,608,478 | 87,406,511 | 1,081,344 | Total row; following rows split the two explicit Commits |
| S8c S5 cache Commit | off | 0.026 | 657,958 | 866 | 614,400 | ZXing core 3.5.3; cache fork never merged back |
| S8c S5 repo Commit | off | 0.691 | 950,520 | 979,797 | 466,944 | ZXing core 3.5.3; cache fork never merged back |

## What these measurements buy and cost

**Node.** Ten edit Commits total 0.234 s / 1,371,220 B uploaded / 294,912 B Store
growth for `off`, versus 0.196 s / 145,620 B / 110,592 B for `on`. The generated
merge selected three newer generated paths via LWW; the source control conflicted
as expected. Both cold unit runs passed 510 tests, with one skipped.

Both resume runs failed the same source-map assertion: the prior unit run's
five-line fixture edit remained in the published Thread. The actual committed
fixture and post-S5 sources matched across modes. One full-suite diagnostic on
a plain container filesystem passed and restored the fixture. This narrows the
issue to filesystem-dependent test/cleanup behavior but does not isolate a
LayerFS fault or its cause. No production fix, test assertion change, or successful
rerun replaced either failed resume. The failed elapsed times are **not time to
passing tests**. [Readback comparison](receipts/noignore01/attempt2/thread-input-equivalence.json),
[native diagnostic](receipts/noignore01/attempt2/native-diagnostic-console.log),
[off failure](receipts/noignore01/attempt2/v2-vite-off3-S6-test.log.gz),
[on failure](receipts/noignore01/attempt2/v2-vite-on3-S6-test.log.gz).

**Maven.** Ten edit Commits total 4.586 s / 1,935,907 B uploaded / 1,290,240 B
Store growth for `off`, versus 3.590 s / 114,469 B / 126,976 B for `on`.
Both cold and resume tests passed. `off` resumed without rebuilding in 3.311 s;
`on`'s explicit rebuild and test took 9.118 s. Four generated-path LWW decisions
merged cleanly; the source-line conflict control was correctly refused.

| Maven cache placement, off | Base Store growth B | Cache logical bytes | Cold test alone s | Mount + test s | Store bytes fetched | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| S8a separate shared volume | 64,937,984 | 226,857,786 outside Store | 3.254 | 3.582 | 1,634,337 | Passed |
| S8b inside repo `.m2` | — | 225,749,437 in failed Workspace | — | — | — | Build failed, no completed warm base |
| S8c separate cache Branch | 213,155,840 combined repo + cache | 226,857,786 in cache Branch | 5.674 | 6.662 | 56,602,286 | Passed; one daemon, two Workspaces |

S8b's 422.889-second real dependency download succeeded, but Petclinic's NoHTTP
scanner then reported 3,757 violations in downloaded POMs. Git exclude/LWW rules
do not control that scanner. No check was disabled to manufacture a passing
sample. [Failure](receipts/noignore01/attempt2/v2-maven-b-build.log.gz),
[partial cache size](receipts/noignore01/attempt2/maven-b-failed-cache-size.json).

S8c adds 148,217,856 B of Store allocation versus S8a, while retaining the cache
in LayerFS instead of relying on the separate volume. Both initial forks caused
zero observable database page growth. S5 added a 607,650-byte ZXing jar only to
the writable cache fork: cache Commit growth 614,400 B, repo Commit growth
466,944 B. Cache-base lookup returned `NoSuchPath`; cache-fork lookup returned
the file. No merge-back occurred.
[Cache fork readback](receipts/noignore01/attempt2/v2-maven-c-off-cache-fork-jar.log),
[base absence](receipts/noignore01/attempt2/v2-maven-c-off-cache-base-no-jar.log).
The repo and cache are separate Commits; no cross-Branch atomicity claim is made.

**Verdict:** the observed incremental storage/Commit overhead is not an obvious
cost blocker for these workloads. Maven demonstrates the recovery benefit, and
the selected separate-cache-Branch design works locally. The measured cold-cache
fetch cost is real and should not be described as a free materialized environment.
Node resume remains an unresolved functional gap common to both modes; these
samples do not establish its reliability or performance on a real remote link.

## Evidence, hygiene and closeout

[Derived numeric rows](receipts/noignore01/attempt2/derived-metrics.json) link each
claim to original event labels; [raw events](receipts/noignore01/attempt2/events.jsonl)
retain exact nanoseconds, snapshots, commands and exit codes. Raw terminal logs
with whitespace are losslessly compressed; the [export map](receipts/noignore01/attempt2/publication-export.json)
resolves their logical ledger names to `.gz` artifacts. There are 63 timed
Workspace Commit calls: 62 created new records, while Vite `on` S4 answered
`UpToDate` and created no history. Two successful SDK merges also created timed
Commits. [Outcome classification](receipts/noignore01/attempt2/commit-outcome-classification.json). Expected source
conflicts and missing-cache-jar readbacks are negative controls, not retries.

Every failed workload/setup receipt is retained. Preparatory corrections include
Cargo target contamination, missing Init acquisition-table configuration,
copying a daemon-local overlay template into a fresh fixture, and reusing the
SDK helper's overlay-template path. The fixes were confined to the harness.
No LayerFS code was repaired or changed. The earlier SDK read diagnostics that
refused `AlreadyExists` never reached their requested read method.

All `cxn-` containers, networks and volumes were removed after log capture; the
runtime images and the archived `ignore` source were removed too. `cxi-target`
was retained. Disposed Store/overlay payloads cannot be reused as future proof.
Host space stayed below the repository's 100 GB threshold; the authorized scope
had no existing released allocation capable of the requested 300 GB reclaim, so
that initial cleanup target remained short by 300 GB. Docker's initial free
space exceeded 15 GiB. Final readback and hygiene checks are linked below.

Production LOC: **109,419 → 109,419 (delta +0)**, core 98,567; SDK 2,928;
dsh 7,924, unchanged. Method: pinned `tools/production_loc.py`, exact parent and
staged product snapshots, nonblank/non-comment source, inline tests excluded.
Reference absent (retired R9c; last counted 65,417 at tree 498dd1917812).
Only docs/harness changed; full product tests, fmt/clippy and the frozen benchmark
are inapplicable. Harness compilation, Python syntax, receipt cardinality,
source equivalence, report links, whitespace and publication hygiene are checked.
No push, remote issue or pull request was performed.

Final checks: [receipt validation](receipts/noignore01/attempt2/validation-final.json),
[hygiene](receipts/noignore01/attempt2/hygiene-final.json),
[exact LOC comparison](receipts/noignore01/attempt2/production-loc-final.json),
[cleanup/readback](receipts/noignore01/attempt2/cleanup-final.json),
[final space](receipts/noignore01/attempt2/space-final.json).
Publication hygiene counts: **home path 0; out-of-prefix resource names 0;
internal host/platform identifiers 0**, including decompressed receipts.
[Additional lossless log mapping](receipts/noignore01/attempt2/publication-extra-compression.json).
