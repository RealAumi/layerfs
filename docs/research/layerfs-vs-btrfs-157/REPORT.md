> **Status:** Historical experiment report, 2026-09-09, restored 2026-10-20.
> Written by a Codex session into this path and never committed; the file was
> later lost from the working tree. This copy is its exact text, recovered from
> that session's log (`~/.codex/sessions/2026/09/09/rollout-2026-09-09T07-30-21-…`).
> Its `comparison.png`, `comparison.svg` and `evidence.json`, and the raw runs
> under `~/Ephemeral-AI-Lab/deepseek-history-runs/`, are lost; links to them
> below no longer resolve. The LayerFS comparator here (184,598,528 B) is the
> September research candidate in commit `0cdd2f3533`; the current LayerFS
> result for the same 157 checkpoints is
> [dsh-dedup v1.0.0](../../../benchmark/data/dsh-dedup/README.md). The Btrfs
> numbers are copied into
> [btrfs-reference.csv](../../../benchmark/data/dsh-dedup/v1.0.0/btrfs-reference.csv).

# LayerFS vs. Btrfs: retaining 157 DeepSeek Harness checkpoints

Experiment report · 9 September 2026 · Storage capacity and historical-state correctness

## 1. Environment setup and benchmark

### 1.1 What the benchmark retains

The benchmark reconstructs **157 selected Git tree states** from [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), preserving each state as a historical checkpoint. It measures the space required to retain that history. It is a replay of source-tree transitions, not a recording of 157 agent execution sessions or their original filesystem syscalls.

| Input property | Frozen value |
|---|---|
| Source tip | `b0a7d2ce3b4c19d7452e364b2d7acbfa87e707ed` |
| Reachable source commits | 15,632 |
| Selection | Ordinals 100, 200, …, 15,600, then 15,632 in reverse topological order |
| Retained checkpoints | 157 |
| Sum of logical file/symlink content across the retained states | **4,936,693,030 bytes** |
| Historical path occurrences, including directories | **904,143** |
| Unique Git blob bytes across the selected states | 891,893,320 bytes |
| Largest blob | 1,241,221 bytes |
| Unique regular-file contents smaller than 8 KiB | 64.51% by count |
| Manifest SHA-256 | `03f21acfb415907f521217e7a972ed512265c8d0c2da0f8034e2ff3014334271` |

The source trees exclude `.git`, installed dependencies, and generated build artifacts. The sum of retained logical bytes counts content once per historical occurrence; it is the denominator for history-storage savings, not an allocated-disk baseline. The file-size distribution makes this primarily a **small-file, many-version workload**. Input and distribution provenance are recorded in [the evidence manifest](evidence.json).

### 1.2 Common mutation and retention method

For each selected tree, the frozen importer removes obsolete or conflicting paths, creates required directories, writes changed file contents, and preserves unchanged files. Changed regular-file contents are **rewritten in full**. File executable modes, symlink targets, and normalized directory/file metadata follow the original benchmark contract; directory metadata is normalized at every checkpoint.

Across the history, this program performs **181,002 regular-file content writes totaling 1,719,803,660 bytes**. It does not substitute byte-range patches, Git-object hardlinks, cross-path reflinks, or rename detection to improve one backend's result.

The systems retain states differently:

- **LayerFS:** ordinary Workspace imports run through the public Exec/Commit path, with the Store, SDK coordinator, publication, and spool on the macOS host. The Linux container supplies the workload and daemon/FUSE execution environment. All 157 states are retained as Commits.
- **Btrfs:** the importer updates one writable subvolume. After each import, the coordinator creates a read-only snapshot. The mutable head is deleted before final accounting, leaving exactly 157 historical snapshots.

The selected source trees and operation semantics match. The LayerFS research candidate and the Btrfs tests use different product/runtime images; this report does not claim their helper binaries or complete execution paths are identical. No LayerFS or Btrfs workload was rerun to write this report.

### 1.3 Test environment

| Item | Configuration |
|---|---|
| Host | macOS on ARM64; Python coordinator |
| Docker Engine for the Btrfs experiments | Docker Desktop 29.5.2 |
| Linux kernel | `6.12.76-linuxkit`, aarch64 |
| Container limit | 2 CPUs, 2 GiB RAM, no swap, 256 PIDs |
| Btrfs tools | `btrfs-progs v6.2` |
| Measured Btrfs device | Fresh 8 GiB sparse loop device per history experiment |
| Btrfs profiles | Data `single`; metadata `DUP` |
| Common Btrfs mount options | `noatime,compress=zstd:3` |
| Input placement | Prepared input files outside the measured Btrfs filesystem |
| Filesystem access | Privileged, isolated test container for loop mounts and dedupe ioctls |

These are **native Btrfs snapshot experiments**, not 157 calls to `docker commit`, and not a change to the user's Docker storage driver. Test containers and loop filesystems were removed after the runs or the explicit stop request.

The Btrfs runtime image is pinned to `sha256:c5552ae4e06e938aae61a463dd871304407ed5325b529c9d2d52c19a045e64e4`. The LayerFS comparator is the completed `issue88-SP-candidate-full157-1` research run: measured host producer `d4f26f0d16f0f91c1f75767cf699012b8794ac01`, host binary SHA-256 `ed0fc0ea0a04a77651a46c1a156e313df94f3a2bbc7abec88dae497f56da5a32`, runtime image `sha256:f4b00c4555de1edca86f4a4d251c756355188853a8120927ffff54057e0cdcce`. Its archived build-custody qualification, source/product seals, and original dirty-image-build declaration remain part of the evidence; this report does not relabel a later checkout as the measured producer.

### 1.4 The three Btrfs cases

| Case | Configuration and stopping rule |
|---|---|
| **A — Btrfs + zstd** | Snapshot sharing and compression; no additional content-deduplication tool. Completed construction and all-state verification. |
| **B — Btrfs + zstd + duperemove** | v0.15.2; 4 KiB partial-block lookup; two I/O and two CPU threads; periodic scans during replay with a reusable external hashfile. Four online rounds completed, followed by a static full-history pass that was interrupted at the user's request. |
| **C — Btrfs + zstd + bees** | Revision `2d53565c74d3b1db9e035f55c5d67868147b568f`; extent scan mode 4; two workers; throttle factor 1; 32 MiB external hash table. Started before replay, followed by a fixed 300-second catch-up window, clean shutdown, and all-state verification. |

An initial duperemove v0.15.1 attempt encountered repeated `EINVAL` retries. A short syscall trace confirmed the loop; the failure was preserved and excluded from the comparison. The official [v0.15.2 fix](https://github.com/markfasheh/duperemove/releases/tag/v0.15.2) was then used with a fresh filesystem and hashfile. The later interruption of the v0.15.2 scan is a separate event, not evidence that the old loop persisted.

### 1.5 Storage accounting and correctness

All displayed **MB are decimal: 1 MB = 1,000,000 bytes**.

Btrfs history storage is synchronized `btrfs filesystem usage -b` **Used**: allocated data in use plus metadata/system usage with profile replication. Unused block-group reservations are reported in the raw receipts but excluded from this metric. Neither the 8 GiB device capacity nor the sum of per-snapshot `du` values is used as history storage. Summing `du` would repeatedly count shared extents.

External deduplication indexes/state are measured by actual file allocation and added separately. For a deployment that keeps these tools active, this is a real persistent cost. For one-time deduplication, indexes can be discarded afterward; the history-only column makes that distinction visible.

LayerFS uses the **complete Store allocation at the final acknowledged checkpoint**, including its internal indexes and any sidecars. The documented value is **184,598,528 bytes, or 184.6 MB**, with zero acknowledged sidecar allocation. This replaces the earlier conversational shorthand “180 MB”; the report does not treat that rounded number as an exact measurement.

These metrics compare the capacity of the measured representations. They are not identical whole-device accounting: Btrfs includes its internal filesystem metadata and DUP copies, whereas LayerFS's Store-file allocation does not include all outer host-filesystem metadata. The measurements also do not establish equal redundancy or durability guarantees.

After construction, completed runs read every historical state and compare paths, types, content SHA-256, lengths, executable modes, and symlink targets against the original oracles. The report-generation check independently matched the LayerFS run's ordered 157 `(index, commit, tree, logical size)` tuples to the frozen input manifest and reconciled its final allocation with its original acknowledgement receipt.

## 2. Results: LayerFS and the three Btrfs cases

### 2.1 Total retained-history capacity

**The documented LayerFS Store occupied 184.6 MB. The completed Btrfs baseline occupied 1,994.6 MB; the completed bees run occupied 2,068.9 MB including its state.** The duperemove row is an interrupted observation, not a completed benchmark outcome.

| System | History/Store MB | External index/state MB | Combined MB | Combined / LayerFS | Verification and completion |
|---|---:|---:|---:|---:|---|
| **LayerFS research candidate** | **184.599** | Included in Store | **184.599** | **1.00×** | Completed; **157/157 PASS** |
| **A — Btrfs + zstd** | 1,994.596 | 0 | **1,994.596** | **10.81×** | Completed; **157/157 PASS** |
| **B — Btrfs + zstd + duperemove** | 2,027.602 | 406.827 | **2,434.429** | **13.19× observed** | **Interrupted; only 55/157 final verification checks completed** |
| **C — Btrfs + zstd + bees** | 2,035.290 | 33.571 | **2,068.861** | **11.21×** | Fixed window completed; **157/157 PASS** |

The incomplete duperemove row must not be cited as its converged result or used to rank fully processed tools. All 157 snapshots had been constructed, but both the final scan and subsequent full-history verification were stopped. The 55 recorded checks passed; the remaining 102 were not completed, rather than recorded as failures.

![Retained storage for LayerFS and three Btrfs cases; hatched duperemove bar denotes interrupted evidence](comparison.png)

Relative to 4,936,693,030 logical retained bytes, the LayerFS Store saves **96.26%**, the completed Btrfs baseline saves **59.60%**, and bees including state saves **58.09%**. These are physical-representation-to-logical-history ratios, not dedupe-hit rates.

For supplementary context, a fourth, earlier Btrfs run **without compression** occupied **3,209,113,600 bytes** and passed all 157 checks. Compression alone reduced that to 1,994,596,352 bytes, a **37.85%** reduction. The three principal cases above all retain zstd compression to isolate the addition of deduplication tools more clearly.

### 2.2 Did the tools actually deduplicate?

Yes. The data region became smaller in both observed tool runs. The net filesystem result was worse because the metadata region grew by more than the data-region reduction.

| Physical region | A: zstd baseline MB | B: duperemove, interrupted MB | C: bees MB |
|---|---:|---:|---:|
| Data | 700.785 | 478.364 | **327.291** |
| Metadata, including DUP copies and inline file data | 1,293.779 | 1,549.206 | **1,707.966** |
| System | 0.033 | 0.033 | 0.033 |
| **Filesystem Used** | **1,994.596** | **2,027.602** | **2,035.290** |

For bees, the complete accounting is:

```text
Data-region reduction                  −373,493,760 B
Metadata-region increase               +414,187,520 B
System-region change                              0 B
Filesystem net increase                 +40,693,760 B
External bees index/state               +33,570,816 B
Combined increase versus baseline       +74,264,576 B  (+3.72%)
```

Thus **bees reduced the data region by 53.30%**, yet the filesystem alone grew **2.04%**. Including persistent state, the observed capacity increased **3.72%**. Deduplication was effective at sharing file data; it did not improve total capacity in this workload.

The interrupted duperemove observation shows the same direction: data decreased by 222,420,992 bytes, metadata increased by 255,426,560 bytes, and its external index occupied another 406,827,008 bytes. This explains the observed footprint but does not predict its eventual completed result.

### 2.3 bees progress, settling, and correctness

The bees-only replay took **95.80 seconds**. bees ran concurrently with the importer, then received exactly 300 seconds of catch-up. It exited with code 0. It reported **220,732 successful dedupe operations** and **2,470,822,098 logical dedupe bytes**; those counters are not physical bytes reclaimed and are not substituted into the capacity calculation.

| Observation | Filesystem Used MB |
|---|---:|
| Replay complete, mutable head still present | 1,974.399 |
| Catch-up ~31 s | 1,991.225 |
| Catch-up ~92 s | 2,075.509 |
| Catch-up ~122 s | 2,083.836 |
| Catch-up ~153 s | 2,035.290 |
| Catch-up ~214 s | 2,035.290 |
| Catch-up ~300 s | 2,035.290 |
| After clean shutdown and final settling | **2,035.290** |

Space remained unchanged for the final approximately 147 seconds. At the 214-second sample, bees reported an empty work queue and no active dedupe worker in its thread-status listing. This supports a **settled observation within the measured run**; it is not proof of a global optimum across different settings, snapshot schedules, or workloads.

All 157 snapshots subsequently passed independent verification: **904,143 path occurrences and 4,936,693,030 bytes**. A live process sample during replay showed approximately 55 MiB RSS, and a later sample was about 71 MiB. These are sampled process values, not a claim about total system memory or a separately measured lifetime peak. No OOM kill or swap was recorded at the sampled boundaries.

The replay duration is not comparable to LayerFS's public Commit latency: the operations, host/container split, transfers, filesystem synchronization, background work, and observation boundaries differ. This report makes no Btrfs-versus-LayerFS speed claim.

## 3. Why Btrfs used more storage in this workload

Btrfs is an **extent-based copy-on-write filesystem**. “Block based” should not be read as “automatically deduplicates all repeated content.” LayerFS also ultimately stores bytes on a block-backed filesystem. The relevant distinction is the representation of content and history above that storage, and the work needed to preserve it.

### 3.1 CoW preserves existing sharing; full rewrites require new sharing to be discovered

A Btrfs snapshot initially shares data and metadata with its source. If an application modifies a small range in place, the unchanged ranges can remain shared. This is different from recognizing repeated bytes in an entirely rewritten file.

The frozen importer rewrites changed file contents in full. Btrfs must first accept those writes; an out-of-band tool then finds equal ranges and asks the kernel to share them. That adds scanning and reference updates after the write. Btrfs's own documentation distinguishes this out-of-band deduplication from inline deduplication. [Btrfs deduplication documentation](https://btrfs.readthedocs.io/en/latest/Deduplication.html)

The measured LayerFS candidate applies content-addressed admission and encoded representations during its normal Commit path. Its storage account includes **28,106 native FULL records and 58,306 native PREFIX records**, with bounded dependency depth, as well as structural deltas. It can retain a new logical version using existing canonical objects and encoded relationships to prior content instead of retaining a separately allocated ordinary-file representation for every changed version. This describes the documented candidate, not a claim that every LayerFS version or import path uses the same encoding.

### 3.2 Updating deduplicated extent references can break metadata sharing

File data and the metadata that refers to it are different storage populations. Snapshots share metadata pages initially, but changing an extent reference in a historical view can cause metadata CoW. With many snapshots referring to the affected data, one data-sharing change may require updates in multiple views.

The bees documentation explicitly describes this metadata-growth effect and recommends deduplicating before snapshots accumulate when possible. In this experiment, bees started before replay, but snapshot creation was not held back until background deduplication completed. It therefore still processed some content after multiple snapshots had retained references. [bees snapshot considerations](https://github.com/Zygo/bees/blob/2d53565c74d3b1db9e035f55c5d67868147b568f/docs/gotchas.md#snapshots)

The measured increase of **414.2 MB in the metadata region** is consistent with that mechanism. The experiment did not separately attribute every new metadata page to dedupe reference updates, importer directory normalization, inline file data, or other filesystem structures. It establishes the net growth, not a complete causal census.

### 3.3 Small files and metadata DUP amplify the cost

Nearly two-thirds of the distinct regular-file contents are smaller than 8 KiB. For these files, the absolute data saving from merging a range can be small relative to the inode, directory, extent-reference, and metadata-page work associated with maintaining many filesystem views.

The default metadata DUP profile stores two physical copies of metadata. This is included in all Btrfs numbers and amplifies the cost of metadata growth. The metadata region also carries inline small-file data, so it must not be characterized entirely as removable bookkeeping.

This report did not test metadata `single`, different node sizes, alternative inline-data policies, or a different snapshot schedule. Removing one redundancy copy would change the storage profile and would still leave the underlying representation costs; no unmeasured configuration is assigned a performance or capacity result here.

### 3.4 LayerFS compresses the historical structure as well as the payload

The most concrete architectural evidence comes from LayerFS's audited byte account:

| LayerFS component | Bytes | MB |
|---|---:|---:|
| Encoded payload groups | 98,256,041 | 98.256 |
| Encoded structural groups | 56,719,413 | 56.719 |
| Pack headers and directories | 378,096 | 0.378 |
| Logical database outside pack BLOB content | 26,357,298 | 26.357 |
| Allocated-minus-logical database adjustment, unattributed | 2,887,680 | 2.888 |
| **Complete acknowledged Store allocation** | **184,598,528** | **184.599** |

These five components reconcile exactly. The database component already includes the Store's indexes and page-space costs; the result is not merely a payload-compression subtotal. The selected objects-index pages alone occupy 18,722,816 bytes inside this accounting.

The candidate represents filesystem structure as canonical objects stored in encoded groups and uses selected structural deltas, including **4,583 inode-table-leaf DELTAs**. Its historical namespace is therefore stored in a different form from a collection of native Btrfs snapshot trees. The 56.7 MB of structural groups demonstrates that the structural representation itself is compact in this run.

The categories are not interchangeable: LayerFS structural groups are not a like-for-like measurement of every byte in Btrfs's metadata region, which includes DUP and inline content. Nevertheless, the complete accounts show that **compact payload encoding plus compact history/structure encoding**, rather than file-content deduplication alone, explains the direction of LayerFS's advantage. The exact causal fraction attributable to each architectural choice would require additional controlled experiments.

### 3.5 What the experiment establishes—and what it does not

For these 157 small-file source-tree checkpoints and this full-rewrite importer, the completed Btrfs configurations occupy **10.81× and 11.21×** the complete documented LayerFS Store. bees substantially reduces duplicated data but incurs enough metadata growth to increase total capacity. The interrupted duperemove result is supporting diagnostic evidence only.

This does **not** establish that Btrfs is universally worse, that CoW is ineffective, or that every LayerFS workload has the same advantage. A preliminary, separate 512 MiB-file test in this session showed that changing only 4 KiB through a native Btrfs snapshot required only about 36 KiB of additional reported Used space. That was a different workload and methodology, but it illustrates why large-file in-place updates must not be judged from this small-file history result.

The LayerFS comparator is a completed **research checkpoint**, not a claim that the latest checkout is release-qualified. The original report records additional read-performance tradeoffs and broader qualification limits. Compact representations can require decoding and dependency traversal; this capacity comparison does not quantify those costs or establish equivalent filesystem features, crash behavior, read latency, or redundancy.

### Evidence and reproduction

[**evidence.json**](evidence.json) contains exact integer accounting, compact LayerFS provenance, the source-file SHA-256 inventory, completed/partial verification counts, and the bees catch-up trajectory. It was generated by checking saved receipts, without rerunning benchmarks or opening live Stores.

The principal original artifacts are:

- [LayerFS completed findings and accounting](/Users/yifanxu/Ephemeral-AI-Lab/layerfs-storage-v3-runs/issue88-SP-report-1/findings-and-next-experiment.md), [final comparison receipts](/Users/yifanxu/Ephemeral-AI-Lab/layerfs-storage-v3-runs/issue88-SP-report-1/comparison.json).
- [Btrfs zstd baseline](/Users/yifanxu/Ephemeral-AI-Lab/deepseek-history-runs/btrfs-157-20260909/zstd3-result.json), [baseline reproduction](/Users/yifanxu/Ephemeral-AI-Lab/deepseek-history-runs/btrfs-157-20260909/reproduce.sh).
- [Interrupted duperemove measurement](/Users/yifanxu/Ephemeral-AI-Lab/deepseek-history-runs/btrfs-live-dedupe-v0152-20260909/duperemove-stopped-result.json), [partial verification](/Users/yifanxu/Ephemeral-AI-Lab/deepseek-history-runs/btrfs-live-dedupe-v0152-20260909/duperemove-stopped-verification.jsonl).
- [Completed bees measurement](/Users/yifanxu/Ephemeral-AI-Lab/deepseek-history-runs/bees-157-20260909/summary.json), [bees reproduction](/Users/yifanxu/Ephemeral-AI-Lab/deepseek-history-runs/bees-157-20260909/reproduce.sh).
- [File-size distribution](/Users/yifanxu/Ephemeral-AI-Lab/deepseek-history-data/size-analysis/report.md), [original small-range CoW probe](/tmp/layerfs-cow-test-20260909/output.log).

These original paths are machine-local. The report, figure, and compact evidence file can be shared together; reproducing the underlying measurements additionally requires the frozen input data, pinned images/source revisions, and an appropriate Linux Btrfs environment.
