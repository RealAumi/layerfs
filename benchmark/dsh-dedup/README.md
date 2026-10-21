# dsh-dedup

> **Status:** Current harness, 2026-10-20. Root AGENTS.md §1–3 and
> [benchmark/AGENTS.md](../AGENTS.md) govern.

How much a LayerFS Store holds, and how long Commit takes, when an agent's
Workspace walks through the DeepSeek-harness history: 157 checkpoints (every
100th of 15,632 Commits, 4,936,693,030 logical bytes) taken at stride 10, 3
or 1. The selections are the old history family's (`history_corpus.py`):
17, 53 and 157 states. A Git pack of the same trees is the reference.

## Route

Everything goes through the public JavaScript SDK, as an agent uses it.
Every command in the Sandbox goes through `sandbox.exec`.

```text
setup    new LayerFS(project, { storePolicy: { wholeFileDepth: 16, chunkDepth: 8, metadataDepth: 8 } })
         project.init(state1)                  timed: Init
         sandbox.create("dedup", project, image)
         branch.fork("dedup", "main")
         sandbox.mount → exec verify.py 1 → sandbox.unmount
segment  sandbox.mount("dedup", "dedup")
         per state k:  exec apply.py <prev> <k>     timed: apply
                       exec verify.py <k>           untimed check
                       sandbox.commit("dedup", path, "dsh state <k>")   timed: Commit
         sandbox.unmount(…, discard true)      (nothing is left uncommitted)
history  per Commit: branch.fork("at-<k>", commit) → mount → exec verify.py <k> → unmount
finish   branch.list_commits("dedup", 1000, 0) → sandbox.close → layerfs.close()
```

- **Apply.** `sandbox/apply.py` moves the Workspace from one state to the
  next. A file whose path stays a regular file is overwritten in place:
  same inode, `O_WRONLY|O_TRUNC`, rewritten whole. Captured Commit then gives
  it its previous version as a delta predecessor (`owner.rs`). Removed paths
  and type changes are unlinked; new paths are created; emptied directories
  are removed (Git trees have none).
- **Verify.** `sandbox/verify.py` checks every path's type, executable bit,
  size and SHA-256 against the corpus oracle, with no path missing or extra.
- **Policy.** Store policy 16/8/8, the defaults since `4ab6e3c7b4`, passed
  explicitly so the record shows them. Disposable profile,
  `LAYERFS_CONSTRUCTION_WORKERS=1`, SDK tracing off.
- **Segments.** A segment starts no new state after 80 s, so every command
  stays under its 115 s alarm. Mount and unmount are recorded per segment and
  kept out of every timer.

## Files

| Path | Role |
| --- | --- |
| `prepare.py` | Host setup: all 157 states' blobs (891,893,320 bytes, once each), manifests, oracles and the in-Sandbox scripts as one root-owned `corpus.tar`; the image Dockerfile; state 1 materialized for Init. |
| `reference.py` | Git reference per stride: a fresh bare repo with one linear Commit per selected tree, `git repack -a -d -f -F --window=10 --depth=50 --threads=2`, checked with `fsck` and tree equality, no alternates file. |
| `run.sh` | One step per command: `image`, `setup`, `segment`, `history`, `finish`, `cleanup`. |
| `report.py` | `states.csv` and `summary.json` from a run's receipts. |
| `client/` | `client.sh` runs one SDK client in the runtime image; `common.mjs`, `setup.mjs`, `segment.mjs`, `history.mjs`, `finish.mjs`; `inspect.mjs` reads the closed Store's totals read-only. |
| `sandbox/` | `apply.py`, `verify.py`, copied into the image under `/corpus`. |
| `records/` | One record per run, including the probe. |

## Running one stride

```bash
P=$PWD/core/target/dsh-dedup/prepared-<date>
python3 benchmark/dsh-dedup/prepare.py ~/Ephemeral-AI-Lab/deepseek-history-data $P
benchmark/dsh-dedup/run.sh image $P
python3 benchmark/dsh-dedup/reference.py ~/Ephemeral-AI-Lab/deepseek-history-data 10 $PWD/benchmark-results/dsh-dedup/git-reference/s10
RUN=$PWD/benchmark-results/dsh-dedup/<UTC id>-s10
benchmark/dsh-dedup/run.sh setup $RUN $P 10
benchmark/dsh-dedup/run.sh segment $RUN      # repeat until it prints DONE
benchmark/dsh-dedup/run.sh history $RUN      # repeat until it prints DONE
benchmark/dsh-dedup/run.sh finish $RUN
python3 benchmark/dsh-dedup/report.py $RUN benchmark-results/dsh-dedup/git-reference/s10/result.json
benchmark/dsh-dedup/run.sh cleanup $RUN
```

`run.sh` uses the daemon and addon staged at `core/target/fs-bench-bin`
(see [benchmark/AGENTS.md](../AGENTS.md#environment)) and the runtime image
`layerfs-352-runtime:node24`. One sample per stride; a change to the
harness, image or binaries means a new run, not a retry.

## Reading the result

- **Headline:** the closed Store's allocated bytes and the sum of Commit
  times, beside the Git pack plus index for the same trees.
- **Not the old pins.** The 2026-10-07 history results (50.7 / 64.2 /
  85.2 MB) came from an in-process Rust driver with depth 8/4,
  GroupRowsIndexed packs, a predecessor for every changed file and the
  similarity index off. This route uses SDK Init (Monolithic), depth 16/8/8,
  Commit's own predecessors and the similarity index on. They are context,
  not a baseline.
- **Cache.** Each Commit reads what the apply step just wrote through the
  mount; nothing else is pre-touched. That is the agent case, not a cold
  claim.
