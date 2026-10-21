# #352 — Script generation

> **Status:** Current guideline, 2026-10-17. It describes how a range's plan
> becomes the steps that run it: a dsh mock scenario (main agent and
> subagents), and the same steps played headlessly. It reuses what Crew, Depot
> and Shop already proved (#347, #350). Improve it where the build shows it is
> wrong, in the same commit as the change.

Read with [SPEC.md](SPEC.md) §2 (the plan, maximum speed) and `dsh/README.md`
("Mock model and demos").

## 1. One step library, two players

Every bash call does the same work whichever player runs it. Only the
orchestration differs.

| | Headless runner (`run.mjs`) | dsh mock scenario (`scenario.mjs`) |
| --- | --- | --- |
| Used for | Every measured range, fast rebuild | Seeing or debugging any range Live in dsh; the P4 demo window |
| Who runs a step | One concurrent task per agent | The agent's subagent, through dsh's bash tool |
| Order between agents | The plan's `after` barriers, awaited directly | The lead's turns: `send_message` to start, `reply until` to wait |
| Step body | `step(range, id)` of `dsh/tools/history/step.mjs` | The same call, as the bash step's `run` |
| Checks | The step's own outcome checks, then the range's gates | The same, then check-demo |

So a bug a scenario shows is reproduced headlessly in seconds, and the
reverse.

## 2. What is copied from earlier scenarios

| From | What | Where |
| --- | --- | --- |
| Crew (#350) | Lead as root and one subagent per role, started once and woken per turn; turns cut where a dependency enters or leaves | `dsh/tools/import/turns.mjs` (`assemble`) |
| Crew, Depot, Shop | Bash step = `run: [["step", …]]` of a shared lib; one attempt; the first reply that differs exits 1 and stops the run | `dsh/scenarios/shared/replay.mjs` |
| Crew | The lead creates Sandboxes one at a time (a create during another create is refused Busy) | `tools/import/crew.mjs` |
| Crew, Depot | Kept Workspaces and Sandbox ids recorded under the project's LayerFS home entry, removed with the project | `replay.mjs` |
| 5 agents, Conflicts | A Workspace per call; after a Conflict, a fresh Workspace resolves it | `scenarios/agents`, `scenarios/conflicts` |
| All replays | `expect` per bash step, checked on the trace by check-demo; static checks before any run | `tools/check-scenario.mjs`, `tools/check-demo.mjs` |

## 3. Scenario format

`layerfs-mock-scenario` version 2, as the loader (`packages/mock/src/scenario.js`)
checks it:

```json
{
  "type": "layerfs-mock-scenario",
  "version": 2,
  "title": "dsh history · ranges 100–102",
  "order": 90,
  "speed": 0,
  "live": true,
  "image": "sha256:<runtime image digest>",
  "seed": "seed.json",
  "lib": "../../tools/history/lib.mjs",
  "blurb": "deepseek-harness's history, ranges 100–102: 8 agents on 3 lanes, …",
  "agents": { "root": [ … ], "a01": [ … ], "a02": [ … ] }
}
```

- `speed: 0` (Max): there are no pauses and no typing. The loader accepts 0 as
  of this commit.
- `live: true`: LayerFS only, never the simulator.
- `seed`: see §8.
- `lib` is the scenario's module of exported calls (§6).
- **Generated, never hand-written.** Run `scenario.mjs --plan <dir> --from k --to m
  --out <dir>`. Only the P4 demo window is committed, as
  `dsh/scenarios/dsh-history/`. Any other window goes to
  `~/lfs-history/scenarios/<k>-<m>/`.

## 4. Agents

| Scenario agent | Plan | Role |
| --- | --- | --- |
| `root` | the lead | Creates the window's Sandboxes; starts and wakes agents; consolidates each range (merges, reconcile, publish); runs closure (install, build, unit tests); closes Sandboxes |
| `a01` … `a10` | the plan's agents | Run their own steps, turn by turn |

- **Names.** An agent's `description` is its name (`a03`). The plan numbers
  agents per range, so `a03` in range 100 and in range 101 is the same subagent.
  A range with fewer agents leaves the rest idle.
- **Prompt** (copy of Crew's): `You are a03 of the dsh history replay. Each turn
  runs your planned steps from the one the lead names; report when they are done.`
- **Start and wake.** An agent is started once with `subagent`, the first time
  it has a turn. Every later turn is a `send_message` "Go on from r100.s0042."
- **End of a turn.** Each turn ends with one short `reply`: `a03: turn 4 done,
  through r100.s0057.` The last one is `a03: done.`

## 5. Steps

One plan step is one bash step, except the lead's consolidation (one bash step
per merge, reconcile, publish, install, build and unit-test run).

```json
{
  "bash": {
    "description": "r100.s0042 a03 fs · fix(cli): handle empty config (5 files)",
    "run": [["step", 100, "r100.s0042"]]
  },
  "expect": ["fs.write:Committed", "fs.write:Committed", "fs.rm:Committed", "fs.write:UpToDate", "fs.write:Committed"]
}
```

- **Description:** `<step id> <agent> <kind> · <dsh commit subject> (<n> files)`,
  cut to 120 characters. The strip and the trace show it, and a failure names it.
- **`expect`** comes from the plan's outcomes, in call order. Reads carry no
  `expect`: their result is checked inside the step.

| Plan kind | SDK calls (in order) | `expect` |
| --- | --- | --- |
| `fs` | `fs.write` / `fs.rm` per file, then the step's reads (`fs.stat`, `read`, `list`, `grep`, `glob`, `diff_files`) | per file: `Committed` or `UpToDate` |
| `apply` | `sandbox.mount`, `sandbox.exec` (writes the files from inline content; `chmod`, `ln -s`), `sandbox.commit`, `sandbox.unmount` | `sandbox.mount:Mounted`, `sandbox.commit:Committed` (or `UpToDate`), `sandbox.unmount:Unmounted` |
| `check` | mount, exec (prints git blob ids of the files; the step compares), commit, unmount | `commit:UpToDate` |
| `hold-mount` | `sandbox.mount`; the Workspace path is kept | `mount:Mounted` |
| `hold-write` | `sandbox.exec` in the kept Workspace (the decoy) | — |
| `hold-commit` | `sandbox.commit` | `commit:Conflict` |
| `hold-resolve` | unmount (discard), mount, exec (verify), commit, unmount | `commit:UpToDate` |
| `stale-mount` | `sandbox.mount`; kept | `mount:Mounted` |
| `stale-apply` | exec in the kept Workspace, commit, unmount | `commit:Committed` |
| lead: merge | `branch.merge` lane into main | `branch.merge:Merged` (a race: `branch.merge:Merged\|Conflict`) |
| lead: reconcile | `fs.write` / `fs.rm` on the lead's Branch | per file |
| lead: publish | `branch.publish` | `branch.publish:Added` |
| lead: install, build, unit tests | one-shot Workspace each; exec exit 0, and each test file's result equal to its native one (SPEC §2, Tests) | `commit:Committed` / `UpToDate` |

Write each entry in full as `method:Kind`, using the names the existing
scenarios use (`sandbox.mount:Mounted`, `sandbox.commit:Committed|UpToDate`,
`branch.publish:Added`, …); the table shortens them. `a|b` allows either. Add `fs.write`, `fs.rm` and the read methods to
check-scenario's method list.

## 6. The lib (`dsh/tools/history/lib.mjs`)

Its exports are the calls a bash step's `run` may name:

| Export | Does |
| --- | --- |
| `setup(window)` | The lead creates the window's 4–8 Sandboxes one at a time and records their ids |
| `step(range, id)` | Runs one plan step: content from the blob cache (fs) or inlined into the exec command (Sandbox), every call's outcome checked against the plan, exit 1 at the first difference |
| `consolidate(range, op)` | One consolidation entry: a merge, the reconcile, a publish |
| `closure(range, what)` | Install, the build of changed packages, or the range's unit tests (`vitest run <files>`, the plan's list), in a one-shot Workspace |
| `verify(range)` | The checkpoint check: one exec of a node script printing each tracked file's git blob id and mode, compared with `compareTree` |
| `teardown(window)` | Closes the Sandboxes |

Rules, as in `replay.mjs`:

- **One attempt.** No retry, no wait, no sleep. Order comes from the scenario's
  turns or the runner's barriers.
- **State between steps lives on disk.** Sandbox ids and kept Workspace paths
  are kept under the project's LayerFS home entry, keyed by step id, never in a
  process.
- **Output.** One line per call (`fs.write packages/cli/x.ts Committed 4 ms`),
  then the step's summary. Never file contents.
- **The trace step label** is the step id (`LAYERFS_TRACE_STEP`), so the
  per-call trace joins with the plan.
- **Content.** The lib reads `LFS_HISTORY` (default `~/lfs-history`) for the
  plan, and `dsh.git` for blobs.

The headless runner imports the same exports and calls them directly.

## 7. Main agent orchestration (turns)

Use `turns.mjs`'s `assemble` with the plan's own barriers. Change
`assemble(kept, stepsOf)` to `assemble(kept, stepsOf, waits = dependencies(kept))`,
then pass `waits` built from each step's `after` (cross-agent edges only). The
algorithm stays Crew's:

1. **Cut turns.** An agent's steps (in plan order) are cut into turns only where
   a dependency enters (the turn starts at that step) or leaves (the turn ends
   after that step).
2. **Lead events in plan order:**
   - start each turn: `subagent` the first time, then `send_message`;
   - before an event, `reply until: [agents]` for the turns it depends on;
   - the lead's own steps go between.
3. **Ranges in sequence.** After a range's last agent turn, the lead waits for
   every agent, then consolidates, runs closure and verify, then starts the next
   range's first turns.
4. **End.** Wait for all agents, run `teardown`, then `reply: "Done."`.

The plan is already checked to finish (`finishes`), so the turns cannot
deadlock.

**Worked example** (a planned Commit Conflict; B = a02 holds, A = a01 commits):

```text
root: send a02 "Go on from r100.s0101"   a02: s0101 hold-mount, s0102 hold-write; reply
root: reply until [a02]
root: send a01 "Go on from r100.s0042"   a01: s0042 fs (writes the file); reply
root: reply until [a01]
root: send a02 "Go on from r100.s0103"   a02: s0103 hold-commit (Conflict), s0104 hold-resolve (UpToDate); reply
```

Agents with no dependency between them run their turns at the same time. The
lead only waits where the plan has a barrier.

## 8. Seed and window

- **Range 0:** the seed is the Init commit's tree. `oracle.mjs checkout`, then
  `seed.js`'s format.
- **Any later window:** it starts from the milestone snapshot before it. That
  needs the one new dsh feature (SPEC §2): **seed a demo from a Store
  snapshot**. The scenario's `seed` names the snapshot manifest, and Play
  forks it into the demo's own volume and LayerFS home (SPEC §7, Forking from a
  snapshot) instead of Initing.

## 9. Speed

- `speed: 0`; no `pause` steps; replies of one short line; no thinking text.
- **Order comes from turns only.** A scenario that passes only at a lower speed
  is a bug in the generator (`agents` lost its Conflict to pacing, #347 BUGS
  row 54).
- **Nothing waits on time:** no `sleep`, polling or readiness loops in the lib
  beyond the SDK's own calls.

## 10. Validation, before any run

1. **`check-scenario.mjs dsh-history`**, extended for a plan-backed scenario.
   It has no `run/` files, so it checks that:
   - every plan step of the window appears exactly once;
   - each `expect` equals the plan's outcomes;
   - the lead starts each agent once before waking or waiting on it;
   - every turn is answered.
2. **A turn check.** Simulate the scenario's turns: every step's `after` is done
   before the turn holding it starts.
3. **A headless dry run of the window** (`run.mjs --from k --to m`) before the
   Live Play. Same steps, faster to diagnose.
4. **Live Play passes check-demo:**
   - expected outcomes;
   - nothing left open;
   - Branch order against the oracle's `expect`;
   - the final tree by `compareTree` (git blob ids), instead of `final.json`'s
     SHA-256.

## 11. Builder tasks this adds

- `dsh/tools/history/lib.mjs` (the step library) and `scenario.mjs` (the
  generator).
- `turns.mjs`: an optional `waits` argument to `assemble`.
- `check-scenario.mjs`: plan-backed mode and the fs and read methods.
- `check-demo.mjs`: a final-tree check by oracle and git blob id.
- Seeding a demo from a Store snapshot (SPEC §2, P4).

## 12. As built for P1 (2026-10-18)

The headless player is `dsh/tools/history/run.mjs` over `lib.mjs` (SDK
calls) and `steps.mjs` (pure routing and checks, tested by
`tests/runner.mjs`). Its header gives the commands and exit codes. Where it
differs from the text above:

- **Non-regular files go through a Sandbox.** Executables, symlinks and mode
  changes are written by one Sandbox step per op (base64 chunks, then one
  script) and committed by unmount. Large regular files go through fs: since
  F-001 (daemon `71001f65`) an fs body streams, so size no longer routes a
  file (before, files over 60,000 bytes went through a Sandbox because one
  request carried at most 65,519 bytes). Since F-028 the script leaves alone a
  regular file whose blob and mode already equal the lane's tree. Rewriting
  it would set an mtime the root records. `check-apply.mjs --step <id>`
  replays one planned apply's script on the plan's real files.
- **The seal** checkpoints the WAL with `pragma wal_checkpoint(TRUNCATE)` in
  the runtime image after every daemon of the run is gone. Closing the
  Sandboxes alone leaves the WAL non-empty.
- **The checkpoint's base is a Commit.** diff_commits takes saved Commits
  only, so range 0 compares against the probe fixture's Commit, and each
  later range against the previous range's head. Metadata-only items (a
  timestamp that changed while the bytes came back) are checked by blob id.
- **Range 0 is a yarn project** with no pnpm lock; its calibration marks
  every test file skipped with that reason. Offline pnpm installs need the
  metadata cache on the store volume (`--cache-dir /pnpm-store/.cache`).
- **Calibration is per phase.** A phase with tests refuses a range whose
  tests-NNN.json is missing (exit 5). P1 has no tests.
- **Probe branches accumulate.** The SDK has no branch removal, so each
  range adds its lane, check and probe branches (about seven). Counters that
  grow with the branch count (fork `returned_rows`) climb with depth for
  that reason; read such a verdict with the branch count beside it.
- **Scoped probes are fitted per unit of their own input** (finding 002).
  SPEC §4 lets grep over the whole tree grow with the bytes in its scope, so
  the Scaling and Counters gates fit `grep_tree` per tree byte against depth
  (`gates.mjs` `SCOPED`). The runner records the checkpoint tree's files and
  bytes from the oracle as `inputs.tree`; report.mjs attaches the same to
  earlier ranges' metrics in memory. An attempt recorded without `inputs` is
  judged raw, exactly as it was, so recorded outcomes do not change.
- **A rerun line's snapshots sit beside the old line's.** A run that snaps a
  range another run already snapped writes `range-NNN.<run>.json`; manifests
  name their run, and `fork` and the runner read a run's own manifest first.
  A plain manifest that names no run (taken before this) serves its run.
- **Gates use one binary's points** (finding 002, SPEC §6 "never merge series
  across binaries"). `evaluate` keeps only earlier attempts measured with the
  judged attempt's daemon for every series, fit and baseline; a baseline built
  from another daemon is reported, not compared. Fewer than three same-binary
  points make Scaling and Counters say `insufficient same-binary points: n of 3`
  and count as watch, never as a silent pass (ranges 0 and 1 of `p1-pilot` now
  read so; their verdicts were already watch). A fix seeds its new daemon's
  series with the probe points it measured on the earlier snapshots:
  `metrics/probes-<daemon>.json` `{ daemon, points: [{ range, depth, binary,
  cache, probes }] }`, read by report.mjs (`loadSeeds`). A seed fills only a
  range that no same-binary attempt covers.

## 13. As built for P2 (2026-10-18)

The P2 player is `dsh/tools/history/agents.mjs`, called by `run.mjs` when the
run's phase is `p2` (`PHASES.p2`, `p2Plan` and `consolidationSteps` in
`steps.mjs`, tested by `tests/p2.mjs`). A run moves to P2 with `run.mjs phase
--run <id> --phase p2`: same pinned binaries and Store, the move recorded in
`run.json` (`phases`) and the ledger. Where it differs from the text above:

- **Agents are concurrent tasks with their own SDK client.** Each agent runs
  its steps in plan order and awaits only the `after` barriers of each step;
  a failure rejects every pending barrier so no agent waits forever. Each
  agent has its own client (Store calls through the run's service Sandbox) so
  trace labels never mix; every call is recorded (`lib.mjs record`) and its
  trace label is `<step>#<seq>`, which joins the trace line to its record.
- **Superseded from P3 (lead, 2026-10-18, after the owner asked why there are so
  many daemons):** a small shared pool of 4 Sandboxes, each holding Workspaces
  of agents from different lanes. Agent aN uses pool[(N−1) mod 4], and lanes'
  agents are consecutive, so every Sandbox mixes Branches. Several agents mount,
  exec and unmount concurrently in one Sandbox (F-009 fixed). This matches SPEC
  §2 (4–8 Sandboxes, each holding many Workspaces). Ranges 5–14 keep their
  recorded shape: 10–11 Sandboxes and daemons, one per agent. The earlier rule
  follows.
  - **P3 rule, per-call Sandbox scratch (lead, 2026-10-18):** nothing outside
    a Workspace in a shared Sandbox is shared between calls. Each file-placing
    call stages its bytes in its own `/tmp/lfs352-<pid>-<seq>`. Its script
    removes the folder on success. A failed exec gets one cleanup exec that
    removes it, so long-lived Sandboxes don't accumulate folders. This
    replaces the common `/tmp/lfs352`, which a concurrent step in the same
    Sandbox removed (dev352-p3a, r015.s0023: tooling only, not a product
    issue). pnpm's private `/tmp` layer (`/tmp/pnpm-store`, `/tmp/pnpm-cache`)
    is per Sandbox while closure installs run one at a time. If concurrent
    installs ever share a Sandbox, it gets the same per-call treatment.
- **One Sandbox per agent** (at least 4), created once by the lead, kept
  across ranges until a seal. Two concurrent unmounts of different Workspaces
  in one Sandbox failed "Workspace absent" on daemon `511dceed` (dev run,
  F-009, fixed in addon `3da0f665`). The pool is kept after the fix (builder
  decision, 2026-10-18): dropping it would change P2's measured shape and need
  its own dev run, and one agent per Sandbox matches the target.
  The seal closes named Sandboxes at once and the service last.
- **Lanes are the plan's Branch names**, forked from main by the lead at the
  range start (one lead step), with the lead's own Branch `r<k>-main`. Each
  merge makes a new Branch `r<k>-main-<n>`; the reconcile and the publish run
  on the last one.
- **The race** (`merge-race`): the first raced lane publishes (from its own
  client) while the lead merges the second; then the lead merges the published
  lane. A raced merge answering Conflict is merged again before the reconcile.
- **Decoys change every line** of the base (prefixed with the marker). A
  decoy that only appended a line merged cleanly with the real change, so the
  planned Commit Conflict answered Committed.
- **Removals never take a folder another agent of the lane writes under**
  (`p2Plan` `keep`), and a write under such a folder that did not exist at the
  range start makes it again (`mkdir` of an existing folder is a no-op), so
  concurrent agents never race on a folder. A folder left empty is invisible
  to every check (git and the checks list files only).
- **Apply and stale-apply steps put removals in the Sandbox too** (`rm -rf` of
  the removal target in the step's script).
- **Same-Branch concurrent Commits** answered HeadMoved on daemon `511dceed`
  (F-008). Daemon `71001f65` merges at publish, so concurrent Commits on one
  lane need no player aid; the development-only `--serialize-commits` aid is
  removed, and a HeadMoved now is an unplanned outcome (stop).
- **Not in P2:** installs and unit tests (P3); `p2Plan` reports them as left out.
- **The proof checkpoint pages by cursor** (F-010, daemon `71001f65`):
  `verify()` asks `diff_commits(prev, head, 1000, 0, { cursor, hunks: false })`
  and resumes each page at the previous `nextCursor`; a page that says
  `hasMore` without a new cursor fails the checkpoint.
- **Fix kinds are checked** (REBUILD.md §4): `findings.mjs checkFinding`
  requires `fix.kind` 1–3 with `oldStores`, `oldData`, `recovery`, and
  `compat` (kinds 1–2) or `justification { kind1, kind2, cost, snapshot }`
  (kind 3). `report.mjs check` applies the same rule to each fixes/ record a
  finding names, and `report.mjs records` to every record (rows Kind, Old
  Stores, Old data, Compatibility test, Recovery; kind 3: Why not kind 1, Why
  not kind 2, Rebuild cost, Start snapshot). Finding `002.a1` and its six
  records predate REBUILD.md and keep the SPEC §6 kind (F2).
- **The diff_commits gate is per checkpoint, per changed entry** (F-012, lead
  decision 2026-10-18). `steps.mjs checkpointDiff` sums ms and SQL work over
  every page of the step `rNNN.verify` and divides by the changed entries it
  listed (`perUnit["branch.diff_commits"]`, `basis: "checkpoint"`). Scaling
  fits statements per entry, then ms per entry, against depth and against tree
  files (the oracle's count); a rise against either is a finding. It is never
  normalised by tree files. The one-file `diff_commits` probe stays on raw
  counters, fitted against depth and tree files (`TREE_FLAT`). Older attempts'
  per-page medians are a different basis and never share a fit.
- **Probe inputs and versions** (F-014): see SPEC §3c "As built". A probe's
  setup (forks, fixture writes, the stats that size its input) runs untimed
  under `probe-setup:<name>`; only the probed call is timed and counted under
  `probe:<name>`. `report.mjs regate --metrics <dir>` is the gates' dry run.
- **Speed as history grows** (owner 2026-10-19; watch only; REPORT_FORMAT
  §3.4):
  - `node dsh/tools/history/control.mjs --run <id> --range N [--b live|snapshot:<range>[:<run>]] [--label <name>]`,
    run after a range's proofs, one command (about 3 s), one sample per arm.
  - It clones the range 15 terminal Store and the range's Store into two fresh
    volumes, runs the same 45 Store calls in each, writes
    `metrics/control-NNN.a<attempt>.json` (or `.<label>.json` for a
    diagnostic), and removes the volumes (both recorded in the run's ledger).
  - `record()` adds each call's `/proc/self/io` delta and WAL size to
    `calls.jsonl`, and the play's metrics gain `growth`.
  - `runner.mjs` appends the host's 1-min load around each command to
    `runs/<id>/hostload.jsonl`.
- **The runner container** (DIRECT_STORE_IMPL.md step 4, builder
  2026-10-18; one route since F-020): `node dsh/tools/history/runner.mjs --
  <run.mjs arguments>` runs `run.mjs` in `layerfs-issue352-runner` from
  `layerfs-352-runtime:node24`. It mounts the checkout and `~/lfs-history` at
  their host paths, the Docker socket, the run's Store volume
  (`layerfs-issue352-<run>`) at `/layerfs-store` with
  `LAYERFS_STORE_PATH=/layerfs-store/global/store.sqlite`, and an SDK folder
  given with `--sdk` outside the checkout (read-only). It shares the Docker
  VM's network (`--network host`). Store calls run in that process; `run.mjs`
  refuses `new`, `play`, `fork` and `rebaseline` anywhere else (`checkRunner`;
  `cleanup` stays on the host, since the runner holds the volume it removes).
  There is no `--route` and no route field. `docker` inside is
  `runner/docker-shim.mjs` over the Engine API (no Docker CLI, nothing
  downloaded). A run needs a Linux addon pinned with `--addon`; `--sdk <dir>`
  picks the SDK JavaScript (recorded as `LAYERFS_SDK_JS` and
  `binary.sdkJs` {dir, sha256}). Every metrics file records `runner`
  (container, image id, platform, Node) beside `binary` (daemon, addon, SDK
  JavaScript, Sandbox image). **Open (2026-10-18):** a Sandbox's daemon
  endpoint is `127.0.0.1:<published port>` (endpoint.rs), which a container
  on Docker Desktop cannot reach, on the bridge or with `--network host`; the
  dev range on F-020's binaries stopped at Sandbox create (ConnectionRefused).
- **Uncontended vs contended** (SPEC §5, owner direction 2026-10-18; builder
  as built). `steps.mjs markContention` classes every trace line from its
  start and ms: contended when another Commit or merge (a merge, a Workspace
  Commit, a publish, an fs call that published a Commit) overlaps it by more
  than the start's 1 ms resolution. `aggregate` suffixes each class
  ` · uncontended` / ` · contended` (`series`). Speed judges the uncontended
  rows only. The new check **Contended work** fits each contended class's
  SQL VM steps p50 against tree files, banded like Counters, and never uses
  wall time. From fix 067 (owner "yes", 2026-10-20) it reads the call's own
  `sql.call` when the trace has it, and otherwise `writer` + `readers`,
  labelled process-wide. A point needs 5 calls in its range, and the tree must have grown
  1.5× over the points. Existing baselines were re-derived from their runs'
  stored traces (`report.mjs baseline-series`, `derivation: "trace"`,
  earlier classes kept as `previousOps`). Those classes come from the trace
  alone, since the call records were not kept, so reads have no size class.
  An attempt is compared with them through `opsTrace`, classed the same way;
  `regate` derives it from the attempt's trace. Measured ranges now record
  `opsTrace` and keep their call records beside the trace
  (`range-NNN.aK.calls.jsonl`). Earlier reports keep their verdicts (F2).
- **Phase-matched speed baselines** (lead decision 2026-10-18). From P2 on,
  the speed baseline is the pilot's ranges 2–4 replayed with the current
  phase's player on the current binaries: `run.mjs rebaseline --phase p2
  --daemon <file> [--addon <file>]` forks the newest pilot range-1 snapshot
  (`p1-rebase-d`, else `p1-pilot-b`), moves the fork to the phase, plays
  ranges 2–4 measured (label `baseline`) and writes
  `baseline-<daemon12>-<addon12>-<phase>.json`. An attempt from P2 on is
  compared only with the baseline of its own daemon, addon and phase; with
  none, Speed is not judged. `new` and `fork` take `--addon <file>`; the
  manifest records both binaries and the guard checks both before every range,
  measured or fast.
- **A speed baseline per daemon.** `baseline.json` stays the pilot's
  (`511dceed`, `p1-pilot-b` ranges 2–4). A later daemon gets its own
  `baseline-<daemon12>.json` beside it, built by `report.mjs baseline --run
  <id> --metrics <run>/metrics --ranges 2-4` from one re-baseline run (label
  `baseline`, its own folders) under that daemon alone, with all its size
  classes. Each attempt is compared with its own daemon's baseline; a mix of
  daemons, an unmeasured attempt or a second baseline for one daemon is
  refused. `run.mjs new|fork --daemon <file>` pins a run to a daemon file.
- **STATS.md bytes:** a derived range (†) has no byte data; a method seen only
  in derived ranges reads "—", and a total over both carries ‡ (measured
  ranges only).


## 14. As built for P3 (2026-10-18)

- **Development checks after the publish (lead, 2026-10-18): a departure
  from the in-range checks.** A dev range used to run `reinstall-check` (a
  clean reinstall, 79 s with its Commit) and `rebuild` inside its closure,
  before the publish. That made a fast dev P3 range about 176 s, over the
  120 s command rule. Its published `node_modules` also became the clean
  reinstall's, not the measured route's. Now
  `run.mjs devcheck --run <dev run> --range k` runs them after the publish,
  as its own command, on a fork of the published main (`dev-r<k>`). Each
  check runs in a one-shot Workspace with its own Commit (`devcheck.mjs`).
  Results go to `metrics/devcheck-<k>.json` and the trace to
  `trace/devcheck-<k>.jsonl`. The range's own closure no longer changes the
  node_modules chain by a check. Every step stays at or under 120 s: the
  longest is the reinstall at about 79 s. A dev run's `oracle --run` also
  builds the clean oracle the reinstall check compares with. The in-range
  dev-only step that remains is the F-034 fact: `./node_modules/.bin/tsc
  --version` after an install on top.
- **Dev P3 ranges are played fast** when bytes aren't the point. The
  probes (about 49 s) and the version figures are measured-mode stages. A
  dev step that can't fit 120 s is reported with its time, never run with a
  longer ceiling.

- **Changed measured-step command (lead interim yes 2026-10-18, reported to
  the owner).** From P3 on, the clean install (milestone `clean-install`
  and the dev `reinstall-check`) runs `find . -name node_modules -type d
  -prune -exec rm -rf {} +` before `pnpm install` instead of `rm -rf
  node_modules`. Reason: a package that left the workspace keeps its
  untracked `node_modules` (dev352-p3p r016: `packages/core/agent-core`).
  P2 clean-install numbers keep the old command's label and are not compared
  across the change (INSTALLS §1).

- **The P3 command shape: a range in two commands (lead 2026-10-18).** With
  F-031 option (c) on, a range does not fit one 118 s command (dev352-p3s
  r015 reached the ceiling). Each range is played as two commands, each at
  or under 120 s:
  1. `play --run <id> --from k --to k --mode <m> --until lanes`: the fork,
     the `.git` seed (first git range), `/.lww`, and every agent step with
     its lane git exec. It saves the range context (`half-<k>.json`: lane
     trees, counters, the call log, the tooling laps, the trace file and
     attempt, the Store figures before the range) and marks the run
     `halfway`.
  2. `play --run <id> --from k --to k --mode <m> --resume`: the merges, the
     reconcile, the lead's git, the fresh-Workspace status check, the
     closure, the publish, verify and the rest, as in one command.
  - Nothing measured is redone or warmed. The resume reads the saved
    context and appends to the same trace file, so each stage's timing is
    in the trace as if one command had played it. Its new Sandbox pool is
    timed as `resumePrepareMs`.
  - The saved context pins the daemon, native addon, SDK JavaScript and
    image ids, so a resume under other binaries is refused.
  - A run halfway through a range accepts only `--resume` for that range. A
    failure in either half leaves the run dirty: no auto-resume, no retry.
  - Every stage prints a progress line on stderr
    (`[HH:MM:SS r015 +12.3s] …`), so a command stopped at its ceiling shows
    where the time went.

## 15. A P3 range from range 21 (step 0, 2026-10-20)

Built before range 21 for faster preparation and fewer failed first attempts
(liaison, under the owner's delegation). Commands, in order, with the alarm
each runs under (`perl -e 'alarm N; exec @ARGV'`):

| Step | Command | Alarm |
| --- | --- | --- |
| Oracle | `closure.mjs oracle --run R --range k …` (host) | 115 s |
| Native first | `nodeproof.mjs calibrate --run R --range k` until every point is done, then once more: the predicted repair natively; exit 4 and `NATIVE REFERENCE BROKEN` stop the range before any LayerFS attempt | 115 s each |
| Lead and lanes | `play … --until lead`, `--resume --until lanes --cut N` …, `--resume --until lanes` | 118 s each |
| Repair | `play … --resume --until repair`: merges, lead git, the closure (repair install, build, tests), publish | 200 s from r34 (owner 2026-10-20: "increase it to 200s", after r32's 130 s of 160 s); 160 s r24–r33; 130 s r21–r23. From r51 a repair over 170 s is reported to the liaison, with its install/build/test split, before the next range plays (liaison 2026-10-20; the alarm is unchanged) |
| Verify | `play … --resume --until verified`: the checkpoint check | 70 s from r24 (115 s r21–r23) |
| Finish | `play … --resume`: probes, version, metrics, snapshot, report | 90 s for r51–r60 (owner 2026-10-20, asked "Raise its alarm to 90 s for ranges 51–60?": "Yes, 90 s"; r47–r50 finished in 55, 43, 59 and 65 s); 65 s r24–r50 (50 s r21–r23) |
| Proofs | `nodeproof.mjs proofs --run R --range k --budget-s 20` until `"left":0` | 115 s each |
| Control | `control.mjs --run R --range k`; releases QUIET | 118 s |
| Native state | after a terminal range: `nodeproof.mjs savestate --run R`, then `--adopt` | 115 s |

- **Steps resume.** The repair, verify and finish steps share the old final
  command's 295 s (335 s from r34, each step its own command under the 5-minute ceiling); a kill inside verify or finish resumes at that step
  (`halves.mjs` `LATE_STAGES`): the trace is cut back to its length at the
  save and nothing before it runs again. A kill inside the repair step ends
  the attempt.
- **Fail loud.** Every native replay prints a marker per state, snapshot,
  native clean, reconcile removal, lane capture and merge, build and test
  run (`nativestate.mjs` `provenRun`). A missing marker makes the replay an
  error; a point whose native reference did not run has its proofs `NOT_RUN`
  with the reason, never a fallback. The counts are in each proof's `ran`.
- **Re-judge on retained state.** A stop caused only by the oracle, harness or
  report, with LayerFS's recorded state and timings retained, is fixed and the
  same attempt is judged again: the first proofs command takes
  `--rejudge "fix NNN"`. The report's headline says `re-judged after fix NNN`;
  the earlier results stay in the metrics (`rejudged`). A product-caused stop,
  or lost state, needs a new attempt. Timings are never measured again.
- **QUIET** is a lock the harness holds (`quiet.mjs`): a play, calibrate,
  proofs or savestate command takes it for its run, a failed command releases
  it, and the control sample releases it at the attempt's end. Another run's
  QUIET never refuses a command (owner 2026-10-20: sessions do not queue
  against each other, and each clones its own Store). The command goes on, the
  holder is kept, and the overlap is appended to
  `~/lfs-history/QUIET.overlaps.jsonl` for the measured window's record.
  QUIET means the replay owns timing-sensitive Docker work: other sessions
  may run Docker with -j 2 (one heavy batch at a time) and must not wait for
  it to clear. Their builds use -j 6 only while QUIET is absent; each test
  command stays within 120 s.
- **Native state snapshots.** `savestate` replays the run's closure chain once
  and tars the native folder (node_modules, lib/ and every untracked file) into
  the Docker volume `layerfs-issue352-native-states`; `--adopt` puts one
  `native-state` entry in the chain in place of those states. Every native
  replay extracts it instead (a cache of the same model). Validated once:
  r15–r19's 17 states as a snapshot against two cached r20 proof oracles
  (`r020-1-root.end`, `r020-3-docs-rfc.end`): equal installs, groups (build
  caches out, as P1), builds and 175 test results; 17–18 s against 74–94 s.
  `--check <oracle file>` repeats that check.
- **Harness hash.** `runner.mjs` hashes the harness files on the host;
  `run.mjs` refuses inside the container when its view differs (Docker
  Desktop's share can be stale).
- **Fix numbers** come from `fixno.mjs`, which fetches and reads every origin
  branch, at commit time. Rebase on origin/main before each hand-off.

## 16. Ranges 51–100 preparation (2026-10-20)

### Pre-scan before each range (fix 064)

Before a range's oracle, the lead reads its pre-scan, made from the dsh git
history alone (previous checkpoint to this one) and the range's plan file:

```
node dsh/tools/history/prescan.mjs --repo ~/lfs-history/dsh.git --plan <run's plan dir> --from k --to k --out ~/lfs-history/prescan
```

It writes `prescan-NNN.md` (the range's plan notes) and `prescan-NNN.json`.
About 2–3 s per range; run at most 25 ranges per command under a 115 s
alarm. It never writes into a plan directory. The four sections, and the
ranges that taught each one:

| Section | What it flags | Lesson |
| --- | --- | --- |
| 1. Packages added and removed | a workspace folder (`pnpm-workspace.yaml` globs) or package.json folder that some range commit writes into and neither checkpoint holds, with the plan lanes that write there (those with no lane are side-branch commits only) | r044, fix 060, R9 |
| 2. .gitignore | every added or removed line of a changed `.gitignore` | r038, fix 058, R7 |
| 3. Writers | added lines of changed test or script files that write files (Node fs calls, `new Database(`, shell redirections, `mkdir`/`cp`/`mv`/`tee`), excluding the OS temp folder and comments; changed package.json scripts (a new package's only when a lifecycle script is not plain tsdown/tsc/vitest). A text match: the lead checks the target | R7 |
| 4. New packages | workspace folders and top-level folders the checkpoint has and the previous one did not | R5 |

A flag is a reading aid, not a verdict, and changes no gate. The 51–100
notes were made at plan-r31 on 2026-10-20: section 1 lists lane-written
transient packages in 35 of the 50 ranges, about 30 each in r84–r88 and
r91; `.gitignore` changes at r52 and r86.

### Test calibration sizes its own batch (fix 065)

`calibrate-tests.mjs` no longer needs `--max-files 40`. Each command probes
at most 15 files when the working tree moves to a new checkpoint, or when
this checkpoint has no measured rate yet (LESSONS R4). Later commands size
the batch from the slowest probe wall per file of this checkpoint's earlier
commands (kept in `tests-NNN.partial.json` `commands`), so the probe projects
under 60 s inside the 115 s alarm. `--max-files M` only lowers the batch.
The command prints the next batch size.

### F-063 active in the 51–100 lane (fix 066)

Owner 2026-10-20: "the .git improvements should be ported into the 51-100
lane once it starts running". The re-baseline report and the first 51–100
range report each quote the line from

```
node dsh/tools/history/f063.mjs --run <run> --range k --attempt a --build <daemon/addon build commit>
```

It reads the attempt's own trace. For the lane git Commits
(`<step>.git-commit`, `sandbox.commit`) it sums
`daemon[].delta.payload.chunk_depths`: depth 0 is FULL, depth > 0 is PREFIX.
It also checks that the build commit contains `2de43d0a02`.

- Exit 0: active.
- Exit 4: the build lacks the fix, or chunk PREFIX is 0 while chunks were
  stored. Stop and tell the liaison before playing r51.
- Exit 2: nothing to judge.

Pre-fix reference, r049.a1 (`p3-main-w`, daemon `27a769a4`): 139 lane git
Commits, chunk FULL 782 / PREFIX 0.

### Snapshots every range from r52 (fix 071)

The liaison approved a snapshot after every measured range for ranges 51–60,
on one condition: one snapshot adds at most 2 GB on disk, and host free space
stays at or above 100 GB (`tools/cleanup.py check`) over the ten ranges.
Otherwise even ranges stay.

Measured:

| | r50 (`p3-main-w`) | r51 (`p3-main-x`) |
| --- | --- | --- |
| Store (sealed) | 1,533,022,208 B | 1,558,138,880 B |
| New blocks on disk | 1,279 (1,340,084,224 B) | 1,282 (1,344,229,376 B) |
| Copy / seal | 6,180 ms / 1,492 ms | 4,903 ms / 1,587 ms |

Host free space was 397.6 GB at r51 (`cleanup.py check`, floor 100 GB).
Ten snapshots at about 1.35 GB each come to about 14 GB, which leaves about
384 GB. The condition holds, so the choice is **every range**.

r51 was already snapshotted by `due()`, the fork's first range. The switch
is `run.mjs snapshots --run p3-main-x --every`. It sets `snapshots.every`
in `run.json` from the range the run stands at (52) and adds a ledger note.
`snapshotsEvery()` then makes `snapshotDue` true for every measured range.
The phase's own `"every"` (p1) still works as before.

### Re-baseline for ranges 51–100 from recent ranges (owner 2026-10-20)

Owner, 2026-10-20: "Re-baseline for 51-100 on a fresh main build (with fixes
056-061), measured on recent ranges (e.g. replaying 48-50 from snapshots), so
ratios reflect today's tree size." This is the split procedure (§13) with
recent ranges in place of the pilot's 2–4. It forks `p3-main-w`'s r046
snapshot, the newest even snapshot whose next three ranges are calibrated and
terminal, and measures r47, r48 and r49 on the new binaries.

- **Binaries:** built from main `6928ca809d` (fixes 056–067 included, and F-063
  `2de43d0a02`) in image `378b799ef433` with `--release --locked --offline -j 2`
  (QUIET present) and `--network none`.
  - Daemon `32eda22d657d…` and addon `4c52d23cd1b4…`, pinned at
    `core/target/lead51/{daemon-32eda22d,sdk-linux-4c52d23c}/` with a `SOURCE`
    file.
  - SDK JS: `core/target/lead51/sdk-js-6928ca80` (sha256 `f58788de…`, as the
    harness hashes it).
  - **Setup:** the private registry cache (`layerfs-issue352-prep51-cargo-home`,
    copied from `layerfs-issue367-cargo-home`) was refreshed once with
    `cargo fetch --manifest-path core/Cargo.toml --locked` in the same image.
    The copied index was unreadable by cargo 1.85.1, so the offline build could
    not resolve `libproc`. That fetch is the one step with network access.
    `Cargo.lock` is unchanged. The build then ran with `--offline` and
    `--network none`.
  - **Host sharing (r50):** r50 plays on `p3-main-w` while this run plays.
    Each range records the host's 1-minute load (`hostload.jsonl`) and the
    baseline note declares the overlap. Nothing is rerun for load.
- **Isolation:**
  - Prefix `LFS_RESOURCE_PREFIX=layerfs-issue352-prep51`.
  - Run `rb-p3-32eda22d-4c52d23c`, label `baseline`.
  - Its own copies: `~/lfs-history/plan-rb51` (of plan-r31, with r47–49's
    `tests-NNN.json`), `~/lfs-history/oracle-rb51` (of oracle-r31) and the
    pnpm store volume `layerfs-issue352-prep51-pnpm-store` (of
    `layerfs-issue352-pnpm-store`).
  - `--native-states none`: the fork never reads `layerfs-issue352-lead31-*`.
    Nothing writes to `p3-main-w`; its snapshot blocks and manifest are only
    read.
- **Node:** the fork keeps `p3-main-w`'s git and Node settings, so lanes,
  points and the repair play as in r47–49. Native proofs are not run (no
  native states), so the Node proofs row is NOT_RUN, which is watch (F8). The
  native-first checks for these trees passed on `p3-main-w`. A baseline needs
  every range at pass or watch (`baselineRows`).
- **Per range k = 47, 48, 49,** each command under its alarm, as §15:
  1. `closure.mjs oracle --range k --run <run>`. The chain differs from
     `p3-main-w`'s (install, not native-state, after r47), so r48 and r49
     compute their own oracle.
  2. `play --until lead`, `--resume --until lanes [--cut N]`, `--resume
     --until lanes`, `--until repair` (200 s), `--until verified` (70 s),
     `--resume` (65 s). All in measured mode.
  3. `f063.mjs --run <run> --range k --build 6928ca809d`. Exit 4 stops the
     procedure; I report to the liaison before anything else.
- **Write:** `rebaseline --write --phase p3 --daemon … --addon … --run <run>
  --range 46 --ranges 47-49` writes `baseline-32eda22d657d-4c52d23cd1b4-p3.json`.
  The only exception it can take is the named Reinstall growth row, and only
  with the liaison's word.
- **Checks after the write:**
  - per-call `sql.call` in the traces (fix 067's Contended work reads "per call");
  - whether the compact vitest workaround is still needed with the new addon (fix 056).
- **One sample per range, no reruns.** Host 1-minute load is recorded. r50
  plays on `p3-main-w` at the same time, so the two runs share the host.

#### As run (2026-10-20)

- **Run:** `rb-p3-32eda22d-4c52d23c-b`. The first fork,
  `rb-p3-32eda22d-4c52d23c`, lost r047 a1 when Docker Desktop crashed at
  07:28:57Z. It is a dead run, and none of its numbers are used.
- **Isolation:** after each fork, the run's chain entries were pointed at an
  empty volume, `layerfs-issue352-prep51-native-states`. A native replay
  then fails loudly instead of reading `lead31`, and r47's oracle did fail
  that way.
- **Oracle aliases** (liaison, under owner delegation). The fork's chain is
  r46's pre-adopt chain, so it misses `p3-main-w`'s oracle keys. Each
  range's sequence oracle was copied under the fork's key, in `oracle-rb51`
  only, and checked for range, checkpoint and install command:

  | Range | p3-main-w file | Fork's key | sha256 |
  | --- | --- | --- | --- |
  | 47 | `seq-7ea232f40b92765f668f8c97` | `seq-b95a31f093bd723b41145510` | `5bda09dc30a2…` |
  | 48 | `seq-ac1af8fe636a8aea72611917` | `seq-26a4a0a128e7e6de1fc8e2f2` | `724f70dbd021…` |
  | 49 | `seq-12aaa72a54532963638e09b6` | `seq-09722d69d5790c26a2aa3f88` | `fa8690f2919a…` |

  The baseline report reads correctness and oracle-dependent rows (Node
  proofs, Reinstall growth, install inputs) as "not judged: aliased oracle
  (speed baseline)".
- **Cuts:** as `p3-main-w` played these ranges. r47 at 18, 37, 48, 61 and
  75; r48 at 12, 32 and 46; r49 at 44, 55 and 66.
- **Repair:** 128 / 124 / 135 s.
- **Verdicts:** r47 watch, r48 watch, r49 optimize: Counters
  `oneshot_mount_unmount.statements`, depth exponent 0.68.
  - The row was accepted with `--accept-counter
    oneshot_mount_unmount.statements --accept-ranges 49` (liaison under owner
    delegation; `baselineRows`).
  - Statements were 64 / 66 / 66 and VM steps 2,235 / 2,290 / 2,290, over
    depth 56,578 → 59,295.
  - `p3-main-w` shows the same step on the old binaries.
  - The counter stays judged from r51.
- **Written:** `baseline-32eda22d657d-4c52d23cd1b4-p3.json`, 112 classes,
  with the note and `acceptedRows`.
- **F-063:** active in all three ranges (RESULTS 2026-10-20).


### Re-baseline on main `d06a2b81fa` binaries for r58 on (owner 2026-10-20)

Owner, 2026-10-20 (option 1): "rebuild binaries from main d06a2b81fa,
re-baseline on recent ranges (e.g. 55-57), then replay r58 on them and
continue 59-60." `d06a2b81fa` carries fix 073: equal-bytes files are no
change in diffs and merges.

- **Binaries:** built from `d06a2b81fa` (the worktree clean at that HEAD) in
  image `378b799ef433`, with cargo `+1.85.1 --release --locked --offline -j 6`
  (QUIET absent) and `--network none`. The build ran incrementally on the
  prep51 cargo-target volume.
  - daemon `c41a86d23822…`: `core/target/lead58/daemon-c41a86d2/`
  - addon `a1078e6935cd…`: `core/target/lead58/sdk-linux-a1078e69/`
  - SDK JS: `git archive` of `sdk/js`, at `core/target/lead58/sdk-js-d06a2b81/`
  - Each folder has a `SOURCE` file.
- **Run:** `rb-p3-c41a86d2-a1078e69`, prefix `layerfs-issue352-rb57`.
  - `rebaseline --prepare --from-run p3-main-x --range 54 --ranges 55-57`.
  - Its own copies: `plan-rb57` and `oracle-rb57` (of the r51 ones), and the
    volume `layerfs-issue352-rb57-pnpm-store` (of prep51's).
  - `--native-states none`, with the chain's native-state entries pointed at
    the empty `layerfs-issue352-rb57-native-states`.
- **Oracle aliases** (copies, oracle-rb57 only). The r54 snapshot's chain is
  pre-adopt and its r53 tar was pruned, so the keys differ from `p3-main-x`'s:

  | Range | Old key → new key | sha256 |
  | --- | --- | --- |
  | 55 | `a3bf7a2e…` → `3c4f63e6…` | `5d72bb63…` |
  | 56 | `b639c9ae…` → `a9344c5e…` | `adcb1e19…` |
  | 57 | `7834d61d…` → `2115e605…` | `85d40da4…` |

- **Ranges:**

  | Range | Verdict | Repair s | Finish s | F-063 PREFIX / FULL |
  | --- | --- | --- | --- | --- |
  | 55 | watch | 138 | 62 | 454 / 145 |
  | 56 | watch | 145 | 48 | 698 / 235 |
  | 57 | optimize, one row | 146 | 63 | 486 / 201 |

  Host load was 5.6–12.8.
- **The accepted row** (liaison ruling, the r49 form, narrowed to r57):
  Counters `glob_tree.statements per tree file`, depth exponent 3.52.

  | | r55 | r56 | r57 |
  | --- | --- | --- | --- |
  | depth | 65,543 | 66,733 | 67,927 |
  | statements | 139 | 136 | 163 |
  | vm_steps | 21,627 | 20,735 | 22,244 |
  | returned rows | 2,201 | 2,106 | 2,207 |
  | statements on `p3-main-x` (old binaries `32eda22d`) | 138 | 134 | 164 |

  It is one +27 step on the r57 tree, seen on both builds. Fix 074 lets
  `--accept-counter` name a per-unit counter.
- **Written:** `baseline-c41a86d23822-a1078e6935cd-p3.json`, 108 classes,
  with `acceptedRows` and the reason.

### Timing-sensitive tests (judged, not skipped; liaison 2026-10-20)

Some test files pass or fail depending on how fast the run is, not on the
tree. Each one is named here when a liaison ruling accepts a P5 stop on it.
It stays in the calibrated run list and P5 judges it in every later range.
Nothing skips it. If it fails again, the lead stops and sends the liaison the
same evidence: the assertion, the run's vitest and tsc ms against an earlier
pass on the same point or tree, and the host load.

| Test file | First stop | Why it is timing-sensitive |
| --- | --- | --- |
| `packages/skill/skill-local/tests/skill-local-watcher.spec.ts` | r58 a3 `r058-1-root.end` (passed a1, a2) | asserts the rewatch and invalidation that follow a watcher error after two `setTimeout(0)` settles, racing real async I/O in tmpdir |
