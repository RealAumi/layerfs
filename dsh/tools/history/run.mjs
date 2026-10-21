#!/usr/bin/env node
// The headless player of the history replay (#352 SPEC §2, §3, §7; SCRIPTS.md §1):
//   node dsh/tools/history/run.mjs new  --run <id> --phase p1 [--label measured|baseline|dev|control] [--policy default|control] [--daemon <path>]
//   node dsh/tools/history/run.mjs play --run <id> --from N --to M [--mode measured|fast]
//   node dsh/tools/history/run.mjs fork --run <new id> --from-run <id> --range N [--label …] [--daemon <path>] [--addon <path>] [--sdk <dir>]
//     [--pnpm-store <volume>] [--native-states <volume>]   (the fork's own copies; its chain's native states move there)
//   node dsh/tools/history/run.mjs rebaseline --phase p2 --daemon <path> [--addon <path>] [--from-run <id>] [--run <id>]
//   node dsh/tools/history/run.mjs rebaseline --prepare --phase p3 --git --daemon <path> --addon <path> [--plan <dir>] [--run <id>]
//     then play ranges 2-4 one at a time (… --until lead, --resume --until lanes, --resume), then
//   node dsh/tools/history/run.mjs rebaseline --write --phase p3 --daemon <path> --addon <path> [--run <id>]
//     recent ranges (51-100): --prepare … --from-run <id> --range 46 --ranges 47-49 [--oracle <dir>] [--pnpm-store <v>] [--native-states none|<v>],
//     then play 47-49, then --write … --ranges 47-49
//     [--accept-storage-row "Reinstall growth" --accept-ranges 3,4 --reason <text>]   (a named exception, baselineRows)
//     [--accept-counter <probe.counter> --accept-ranges 49 --reason <text>]   (one named Counters row only)
// Every command that touches the Store (new, play, fork, rebaseline) runs in the runner container (runner.mjs): Store calls run in
// this process against the run's volume at /layerfs-store (F-020), Linux only.
// --sdk <dir> picks the SDK's JavaScript (default sdk/js of this checkout);
// it is recorded in the manifest (LAYERFS_SDK_JS) and its commit in binary.
// --addon pins the SDK addon file the same way (default: sdk/js/native, or the
// source run's for `fork`); the manifest records both binaries' SHA-256 and the
// binary guard checks both before every range, measured or fast.
// --daemon pins the run to that daemon file (default: the release build for
// `new`, the source run's for `fork`); a fork onto a newer daemon is a kind 1
// or 2 continuation (REBUILD.md). A `baseline` run re-measures ranges under a
// new daemon into its own folders; `report.mjs baseline` turns it into that
// daemon's speed baseline beside the pilot's.
//   node dsh/tools/history/run.mjs cleanup --run <id>
//   node dsh/tools/history/run.mjs phase --run <id> --phase p2
//   node dsh/tools/history/run.mjs devcheck --run <dev run> --range k   (devcheck.mjs: dev checks after the publish)
//   node dsh/tools/history/run.mjs play --run <id> --from k --to k --mode fast|measured --until lanes   then   … --resume
//     (git and Node on: … --until lead, then … --resume --until lanes, then … --resume)
//     (a long lanes stage: … --resume --until lanes --cut <plan order> one or more times, each stopping there (agents.mjs safeCut))
//     (a range in two commands, each under 120 s: halves.mjs; the P3 command shape with git on)
//   node dsh/tools/history/run.mjs git --run <dev run> --on   (F-031 option (c) from the next range; dev runs only until the dev proof is accepted)
//   node dsh/tools/history/run.mjs snapshots --run <id> --every   (a snapshot after every measured range from the next one, fix 071)
//   node dsh/tools/history/run.mjs node --run <dev run> --on [--inputs-rule plan|r1] [--store-policy verified|release-age-off]
//     (NODE_RULE from the next range: the lead's first install, lane test points, the lead's repair; dev runs only.
//     Owner 2026-10-19: §3 is R1, which plays a plan made with plan.mjs --inputs-rule r1; the store is fetched and
//     verified, so `verified` keeps dsh's policy)
//   fork … --plan <dir> --oracle <dir>   (a dev run on a dev slice's plan and oracle, slice.mjs)
// `phase` moves a run to the next phase (P1 → P2 …) at the range it stands
// at, keeping its pinned binaries and its Store; the move is recorded in the
// run's manifest (`phases`) and ledger. A dirty run cannot move.
// `new` makes the run's folder (~/lfs-history/runs/<id>/), its Docker volume
// layerfs-issue352-<id>, and its Store by Init of dsh's first commit; every
// container is named layerfs-issue352-<id>-<sandbox> (LAYERFS_CONTAINER_PREFIX).
// `play` plays ranges N..M back to back, continuing where the run stands
// (state.json). Before each range: the binary-vs-manifest check and the disk
// guard. Each range: its steps in the phase's player, the reconcile and the
// publish, the proof checkpoint (diff_commits against git's changed paths with
// blob ids and modes; the whole tree at snapshots), the unit tests when the
// phase has them, the scale probes, then the seal and snapshot when due, the
// metrics (range-NNN.aK.json) and report.mjs. Measured mode traces every call
// (LAYERFS_TRACE) with LAYERFS_CONSTRUCTION_WORKERS=1; fast mode (fast-forward
// after a fork) plays and checks the changed paths only: no trace, probes,
// tests, snapshots or metrics.
// P2 (agents.mjs) plays the plan's lanes as Branches and its agents as
// concurrent tasks ordered by the plan's barriers, with the lead's merges,
// race, reconcile and publish; every call is recorded (lib.mjs record) for
// the call table, size classes and the Overview (stats.mjs).
// The wall budget is read from ~/lfs-history/budget.json ({ wallBudgetMs,
// ranges, reason, phases: { <phase>: { wallBudgetMs, … } } }): the phase's own
// entry, else the top-level P1-close one (loadBudget); the projection is the
// mean tooling wall time of the phase's latest attempts (this one included)
// × `ranges` (SPEC §5).
// Exit codes: 0 the last range passed (or watch); 3 optimize; 4 stop (a gate,
// a step that differs from the plan, or a failed checkpoint); 5 the guard
// refused a range (disk, binary, missing calibration); 1 an error; 2 usage.
// It never commits, pushes or comments. It leaves the Store live, so the next
// `play --from M+1` continues; a stopped range leaves the run dirty, to be
// recovered by `fork` from a snapshot (SPEC §6).
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { blobSizes, diffTrees, lsTree } from "./git.mjs";
import { due, manifestPath, rebuild } from "./snapshot.mjs";
import { aggregate } from "./gates.mjs";
import { PLAN_VERSION } from "./plan.mjs";
import {
  binaries, closure, consolidate, expectCall, HISTORY, loadNow, median, Mismatch, PREFIX, probeFixture, probes, readTrace, REPO, Run,
  sandboxHealth, setup, sha256, step, teardown, verify, writeJson,
} from "./lib.mjs";
import { addDelta, checkpointDiff, deltaSummary, deltaWork, diskGuard, diskModel, EXIT, nextPhase, oneshotSplit, p2Plan, pad, poolSharing, PHASES, phaseOps, Tree } from "./steps.mjs";
import { ctxFromJson, cutTrace, decodeLate, dropHalf, LATE_STAGES, lateCtxFromJson, loadHalf, saveHalf } from "./halves.mjs";
import { consolidateLanes, playAgents, pool, safeCut, startRange } from "./agents.mjs";
import { NATIVE_STATES } from "./nativestate.mjs";
import { growthByClass } from "./growth.mjs";
import { gitFacts } from "./gitplay.mjs";
import { checkNode, groupsFile, nodeOf } from "./nodelanes.mjs";
import { fillP3, p3Raw } from "./p3record.mjs";
import { STORE_POLICIES } from "./closure.mjs";
import { buildOverview, callTable } from "./stats.mjs";
import { area } from "./plan-range.mjs";
import { nextChain, rangeClosure, studyMeasurements } from "./closure.mjs";
import { versionStats } from "./version.mjs";
import { d6Triggers } from "./gates.mjs";
import { devcheck } from "./devcheck.mjs";
import { addedBySource, changedGroupBytes, cumulative, liveParts, sealedParts, seedBySource, stepSource, storageFigures } from "./storage.mjs";

const here = new URL(".", import.meta.url).pathname;
const IMAGE = "sha256:d3773b4eac6a7a644887b17e36956cd1553786d47103f0170a3bb2b0ff6988de";
const DAEMON = join(REPO, "core/target/cluster2-linux/release/layerfs-daemon");
const ADDON = join(REPO, "sdk/js/native/layerfs.node");
/** The SDK the player loads (its JavaScript; the addon is ADDON) and the Store file as the runner and every Sandbox see it. */
export const SDK_JS = join(REPO, "sdk/js"), STORE_PATH = "/layerfs-store/global/store.sqlite";
/** SPEC §8's control arm: the old depths. */
export const POLICIES = { default: null, control: { smallFileThreshold: 131072, wholeFileDepth: 8, chunkDepth: 4 } };
/** The depth cap per role of a run's Store policy (the defaults of SPEC §8, or its override). */
export const caps = (policy) => ({ wholeFile: policy?.wholeFileDepth ?? 16, chunk: policy?.chunkDepth ?? 8, metadata: policy?.metadataDepth ?? 8 });
const RUN_ID = /^[a-z0-9][a-z0-9-]{0,40}$/;
const docker = (args) => execFileSync("docker", args, { encoding: "utf8" }).trim();

/** Where a run's folders go by its label: a measured run reports into the issue's docs; others keep theirs. */
export function outputs(label, dir) {
  return label === "measured"
    ? { metrics: join(HISTORY, "metrics"), docs: join(REPO, "core/docs/issues/352"), snapshots: join(HISTORY, "snapshots") }
    : { metrics: join(dir, "metrics"), docs: join(dir, "docs"), snapshots: join(dir, "snapshots") };
}

/**
 * The wall budget for `phase` (SPEC §5; budget.json), or null. The file's top
 * level is the P1-close budget, which every phase without its own entry
 * uses; `phases.<phase>` is a phase's own entry (P3: owner 2026-10-19).
 * `phase` names the entry used.
 */
export function loadBudget(file = join(HISTORY, "budget.json"), phase = null) {
  if (!existsSync(file)) return null;
  const b = JSON.parse(readFileSync(file, "utf8")), own = phase ? b.phases?.[phase] : null;
  const e = own ? { ...own, ranges: own.ranges ?? b.ranges } : b;
  return Number.isFinite(e.wallBudgetMs) && Number.isInteger(e.ranges) ? { ...e, phase: own ? phase : "p1" } : null;
}

/** The metrics' wall budget fields: the phase's budget entry and the projection gates.mjs judges against it. */
export const wallBudget = (budget, phase, attempts, own) => ({ wallBudgetMs: budget.wallBudgetMs, wallBudgetOf: budget.phase, ...wallProjection(attempts, phase, own, budget.ranges) });

/**
 * The projected wall time of the whole history (SPEC §5, lead decision at P1
 * close): the mean tooling wall time of the phase's latest attempts, this
 * one included (`own`), × the history's ranges.
 */
export function wallProjection(attempts, phase, own, ranges) {
  const latest = new Map();
  for (const a of attempts) if (a.phase === phase && a.range !== own.range && a.wall?.totalMs != null && (!latest.has(a.range) || latest.get(a.range).attempt < a.attempt)) latest.set(a.range, a);
  const walls = [...[...latest.values()].map((a) => a.wall.totalMs), own.totalMs];
  return { wallProjectedMs: Math.round((walls.reduce((n, x) => n + x, 0) / walls.length) * ranges), wallMeanOf: walls.length };
}

/** Metrics files of `dir`, as recorded. */
function readAttempts(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).filter((f) => /^range-\d{3}\.a\d+\.json$/.test(f)).map((f) => JSON.parse(readFileSync(join(dir, f), "utf8")));
}

/** The Store file's size and allocation (bytes) and its WAL's, in the run's volume, from a short container. */
function statDisk(run, extra = "") {
  const py = `import os,json,sqlite3
def st(p):
  try:
    s=os.stat(p); return [s.st_size, s.st_blocks*512]
  except FileNotFoundError: return [0,0]
m=st('/v/global/store.sqlite'); w=st('/v/global/store.sqlite-wal')
out={'disk':{'size':m[0],'allocated':m[1],'wal':w[0],'walAllocated':w[1]}}
${extra}
print(json.dumps(out))`;
  return JSON.parse(docker(["run", "--rm", "--network", "none", "-v", `${run.manifest.volume}:/v:ro`, "--entrypoint", "python3", run.manifest.env.LAYERFS_IMAGE, "-c", py]));
}
/** A live Store's size and allocation (its WAL not checkpointed). */
const liveDisk = (run) => statDisk(run).disk;
/**
 * The sealed Store's allocation and its figures (inspect.mjs storeFigures'
 * queries, read-only on the sealed file): pages, objects by role and size
 * class, packs, bytes per table and index.
 */
function sealedFacts(run) {
  return statDisk(run, `c=sqlite3.connect('file:/v/global/store.sqlite?mode=ro&immutable=1', uri=True)
q=lambda s: c.execute(s).fetchall()
f={'pageSize':q('pragma page_size')[0][0],'pages':q('pragma page_count')[0][0],'freePages':q('pragma freelist_count')[0][0],
 'commits':q('select count(*) from "commit"')[0][0],'branches':q('select count(*) from branch')[0][0],'layers':q('select count(*) from layer')[0][0],
 'objects':[{'role':r,'n':n,'canonical':b} for r,n,b in q('select role, count(*), sum(canonical_length) from object_location group by role order by role')],
 'packs':[{'domain':d,'n':n,'bytes':b} for d,n,b in q('select domain, count(*), sum(length) from pack group by domain')]}
try: f['tables']=[{'name':a,'pages':b,'bytes':d,'unused':e} for a,b,d,e in q('select name, count(*), sum(pgsize), sum(unused) from dbstat group by name order by sum(pgsize) desc')]
except Exception: f['tables']=None
out['figures']=f`);
}

/** The range's dsh facts for the headline: commit dates, side commits, the areas changed most by bytes. */
export function dshFacts(repo, plan, changes, sizes) {
  const date = (id) => { try { return execFileSync("git", ["--git-dir", repo, "show", "-s", "--format=%cs", id], { encoding: "utf8" }).trim(); } catch { return null; } };
  const areas = new Map();
  let total = 0;
  for (const c of changes) { const n = sizes.get(c.blob) ?? 0, a = area(c.path); areas.set(a, (areas.get(a) ?? 0) + n); total += n; }
  return { first: date(plan.dsh.first), last: date(plan.checkpoint), commits: plan.dsh.commits, mainline: plan.dsh.mainline, side: plan.dsh.commits - plan.dsh.mainline,
    areas: [...areas].sort((a, b) => b[1] - a[1]).map(([name, bytes]) => ({ name, bytes, share: total ? +(bytes / total).toFixed(3) : 0 })).slice(0, 8), changedBytes: total };
}

/** Exec commands by kind (SPEC §3b): JS (node, npm, pnpm, npx, yarn, vitest) or shell, and non-zero exits. */
export function execFacts(lines) {
  const ex = lines.filter((l) => l.method === "sandbox.exec");
  const js = (c) => /^\s*(node|npm|pnpm|npx|yarn|vitest|corepack)\b/.test(String(c ?? ""));
  return { total: ex.length, js: ex.filter((l) => js(l.args?.command)).length, shell: ex.filter((l) => !js(l.args?.command)).length,
    nonZero: ex.filter((l) => l.ok && l.exitCode != null && l.exitCode !== 0).length, refused: ex.filter((l) => !l.ok).length,
    // the trace shortens long commands, so the closure's installs are known by their step too (dev352-p3h: 0 counted)
    installs: ex.filter((l) => /pnpm (install|i)\b/.test(String(l.args?.command ?? "")) || /^r\d+\.(install|incremental-install|clean-install|reinstall-check)#/.test(String(l.step ?? "")) && /pnpm-store/.test(String(l.args?.command ?? "")) && !/^test -d /.test(String(l.args?.command ?? ""))).length, tests: ex.filter((l) => /vitest/.test(String(l.args?.command ?? ""))).length,
    // the version figures' own execs (version.mjs): tooling, inside the total
    version: ex.filter((l) => /^r\d+\.version(#|$)/.test(String(l.step ?? ""))).length,
    // REPORT_FORMAT §10.1: every exec by tool, summing to the total
    ...execTools(ex) };
}

/**
 * Execs by tool (REPORT_FORMAT §10.1 `m.execs`): git (a git exec of the seed,
 * a lane, the lead or a check), pnpm (an install or refresh), tsc, vitest,
 * other (file placing, listers, ids, scratch). The trace shortens long
 * commands, so a step's label decides where its command's head cannot.
 */
export function execTools(ex) {
  const out = { git: 0, pnpm: 0, tsc: 0, vitest: 0, other: 0 };
  for (const l of ex) out[execTool(String(l.args?.command ?? ""), String(l.step ?? ""))]++;
  return out;
}
export function execTool(command, step) {
  if (/\bvitest\b/.test(command)) return "vitest";
  if (/\btsc -b\b/.test(command)) return "tsc";
  if (/pnpm install\b/.test(command) || (/(^|\.)(install|incremental-install|clean-install|reinstall-check|refresh|repair-install)(#\d+)?$/.test(step) && /pnpm-store/.test(command) && !/^test -d /.test(command))) return "pnpm";
  if (/GIT_CONFIG_COUNT|(^|[;&|]\s*)git /.test(command) || /LEAD_WRITER|unpack-objects/.test(command)) return "git";
  return "other";
}

const q = (xs, p) => { const v = [...xs].sort((a, b) => a - b); return v.length ? v[Math.min(v.length - 1, Math.floor((v.length - 1) * p))] : null; };
/**
 * The Speed section's key operations (REPORT_FORMAT.md §3.4) over all their
 * calls: p50, p95, SQL statements p50, the dominant size class; the cost of a
 * Sandbox Commit per changed file; the one-shot Workspace total (mount start
 * to unmount end, Workspaces held across steps left out); the slowest calls.
 */
export function keyOps(calls, lines, log) {
  const key = {};
  for (const op of ["fs.write", "fs.read", "fs.list", "sandbox.commit", "sandbox.mount", "branch.merge", "sandbox.exec", "branch.diff_commits"]) {
    const cs = calls.filter((c) => c.method === op);
    if (!cs.length) continue;
    const classes = new Map();
    for (const c of cs) { const k = c.size ? `${c.size.kind}:${c.size.n}` : "—"; classes.set(k, (classes.get(k) ?? 0) + 1); }
    key[op] = { n: cs.length, p50: q(cs.map((c) => c.ms), 0.5), p95: q(cs.map((c) => c.ms), 0.95), statements: q(cs.filter((c) => c.sql).map((c) => c.sql.statements), 0.5) };
  }
  const commits = calls.filter((c) => c.method === "sandbox.commit" && c.size?.n > 0);
  const files = commits.reduce((n, c) => n + c.size.n, 0);
  const held = new Set(log.filter((e) => /hold-mount|stale-mount/.test(e.label ?? "")).map((e) => e.seq));
  const open = new Map(), totals = [];
  for (const l of lines) {
    const id = `${l.args?.sandbox}\u0000${l.method === "sandbox.mount" ? l.path : l.args?.path}`;
    if (l.method === "sandbox.mount" && l.ok && !held.has(l.seq)) open.set(id, Date.parse(l.start));
    if (l.method === "sandbox.unmount" && open.has(id)) { totals.push(Date.parse(l.start) + l.ms - open.get(id)); open.delete(id); }
  }
  const slowest = [...calls].sort((a, b) => b.ms - a.ms).slice(0, 3).map((c) => ({ op: c.method, ms: c.ms, size: c.size ?? null }));
  return { ops: key, commitPerFileMs: files ? +(commits.reduce((n, c) => n + c.ms, 0) / files).toFixed(2) : null, oneShotP50: q(totals, 0.5), oneShots: totals.length, slowest };
}

/** The range's Node facts for the metrics: the context without its plan copy, plus NODE_RULE §11 b's consistency when computed (nodeproof.mjs inputs). */
export function nodeFacts(run, k, ctx) {
  const { plan, done, ...rest } = ctx.node, f = join(run.planDir, `inputs-${pad(k)}.json`);
  let inputs = null;
  try { const x = JSON.parse(readFileSync(f, "utf8")); inputs = { consistent: x.consistent, total: x.total, states: x.states, policy: x.policy, rule: x.rule }; } catch { inputs = null; }
  return { ...rest, inputs };
}

/** The next attempt number of range k in `metrics`. */
export function nextAttempt(metrics, k) {
  if (!existsSync(metrics)) return 1;
  const re = new RegExp(`^range-${pad(k)}\\.a(\\d+)\\.json$`);
  return 1 + Math.max(0, ...readdirSync(metrics).map((f) => Number(re.exec(f)?.[1] ?? 0)));
}

function create({ id, phase, label, policy, image, daemon, addon = ADDON, sdk = SDK_JS, source, plan = null, oracle = null, pnpmStore = null, nativeStates = null }) {
  if (!RUN_ID.test(id)) throw new Error(`run id ${id}: lowercase letters, digits and -`);
  if (!PHASES[phase]) throw new Error(`phase ${phase} has no player yet (built: ${Object.keys(PHASES).join(", ")})`);
  const dir = join(HISTORY, "runs", id);
  if (existsSync(dir)) throw new Error(`${dir} exists`);
  const volume = `${PREFIX}-${id}`;
  const host = docker(["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]);
  const env = {
    LAYERFS_HOME: join(dir, "home"), LAYERFS_DOCKER: host.replace(/^unix:\/\//, ""), LAYERFS_IMAGE: image, LAYERFS_VOLUME: volume,
    LAYERFS_DAEMON: daemon, LAYERFS_NATIVE: addon, LAYERFS_CONTAINER_PREFIX: `${PREFIX}-${id}-`,
    LAYERFS_CONSTRUCTION_WORKERS: "1", LAYERFS_STORE_PATH: STORE_PATH, LAYERFS_SDK_JS: sdk,
    // the run's own pnpm store and native-state volume (--pnpm-store, --native-states; owner 2026-10-20)
    ...(pnpmStore ? { LAYERFS_PNPM_STORE: pnpmStore } : {}), ...(nativeStates ? { LFS_NATIVE_STATES: nativeStates } : {}),
  };
  return { dir, volume, env, manifest: {
    run: id, phase, label, policyName: policy, policy: POLICIES[policy], project: "dsh", volume, env,
    repo: join(HISTORY, "dsh.git"), plan: plan ?? join(HISTORY, "plan"), oracle: oracle ?? join(HISTORY, "oracle"),
    outputs: outputs(label, dir), created: new Date().toISOString(), source,
  } };
}

async function cmdNew(o) {
  const { dir, volume, env, manifest } = create({ id: o.run, phase: o.phase ?? "p1", label: o.label ?? "measured", policy: o.policy ?? "default", image: o.image ?? IMAGE, daemon: resolve(o.daemon ?? DAEMON), addon: resolve(o.addon ?? ADDON), sdk: resolve(o.sdk ?? SDK_JS) });
  const summary = JSON.parse(readFileSync(join(manifest.plan, "plan.json"), "utf8"));
  if (summary.version !== PLAN_VERSION) throw new Error(`the plan is v${summary.version}; regenerate it as v${PLAN_VERSION}`);
  manifest.binary = binaries(env);
  if (manifest.binary.image !== env.LAYERFS_IMAGE) throw new Error(`image ${env.LAYERFS_IMAGE} is not a local image id (${manifest.binary.image})`);
  manifest.planVersion = summary.version;
  mkdirSync(dir, { recursive: true });
  writeJson(join(dir, "run.json"), manifest);
  const run = new Run(dir);
  run.note({ kind: "folder", name: dir });
  docker(["volume", "create", volume]);
  run.note({ kind: "volume", name: volume });
  // the seed is dsh's Init commit's tree (SCRIPTS.md §8)
  const src = join(dir, "init-src");
  mkdirSync(src);
  execFileSync("sh", ["-c", `git --git-dir ${JSON.stringify(manifest.repo)} archive ${summary.init.commit} | tar -x -C ${JSON.stringify(src)}`]);
  Object.assign(process.env, env);
  const { LayerFS } = await import(join(env.LAYERFS_SDK_JS, "src/index.js"));
  const t0 = performance.now();
  const init = await new LayerFS(manifest.project, manifest.policy ? { storePolicy: manifest.policy } : {}).project.init(src);
  run.state = { next: 0, layer: init.layer, head: null, prevCommit: summary.init.commit, heads: {}, layers: { init: init.layer }, depth: { commits: 0, layers: 1, branches: 0 }, initMs: Math.round(performance.now() - t0), dirty: null, sinceMs: [], lastSnapshotMs: null, growth: [] };
  run.save();
  console.log(JSON.stringify({ run: o.run, dir, volume, layer: init.layer, initMs: run.state.initMs, binary: manifest.binary, outputs: manifest.outputs }, null, 1));
}

/**
 * Store calls run in the player's process (F-020): only in the runner
 * container (Linux, the Store volume at /layerfs-store, LAYERFS_RUNNER set).
 * The host is refused here, before the SDK would refuse it `Unsupported`.
 * `cleanup` stays on the host: it makes no Store call, and the runner itself
 * holds the run's volume, which cleanup removes.
 */
export const IN_RUNNER = new Set(["new", "play", "fork", "rebaseline"]);
export function checkRunner(cmd, env, platform = process.platform) {
  if (!IN_RUNNER.has(cmd)) return null;
  if (platform !== "linux" || !env.LAYERFS_RUNNER) return `run.mjs ${cmd} plays through the in-process Store: run it in the runner container (node dsh/tools/history/runner.mjs -- ${cmd} …)`;
  if (env.LAYERFS_STORE_PATH !== STORE_PATH) return `LAYERFS_STORE_PATH is ${env.LAYERFS_STORE_PATH ?? "unset"}, not ${STORE_PATH}`;
  return null;
}

/** Where the runner ran (recorded in every metrics file beside the binaries): its image id when in the runner container. */
export const runnerFacts = (env) => ({ container: env.LAYERFS_RUNNER ?? null, image: env.LAYERFS_RUNNER_IMAGE ?? null, platform: process.platform, arch: process.arch, node: process.version });

/** The binary-vs-manifest check: the run's daemon, addon and image are still the ones it was made with. */
function checkBinaries(run) {
  const now = binaries(run.manifest.env), was = run.manifest.binary;
  const differ = ["daemon", "sdk", "image"].filter((k) => now[k] !== was[k]);
  return differ.length ? `${differ.map((k) => `${k} ${now[k]} is not the manifest's ${was[k]}`).join("; ")}` : null;
}

function freeBytes(run) {
  const host = execFileSync("df", ["-k", HISTORY], { encoding: "utf8" }).trim().split("\n").at(-1).split(/\s+/);
  const vm = docker(["run", "--rm", "--network", "none", "-v", `${run.manifest.volume}:/v:ro`, "--entrypoint", "df", run.manifest.env.LAYERFS_IMAGE, "-k", "/v"]).split("\n").at(-1).split(/\s+/);
  return { hostFree: Number(host[3]) * 1024, dockerFree: Number(vm[3]) * 1024 };
}

/** Seals the Store for a snapshot: every Sandbox closed, then one WAL checkpoint (TRUNCATE) and close in the image. */
async function seal(run) {
  const t0 = performance.now();
  const problems = await teardown(run);
  if (problems.length) throw new Error(`seal: ${problems.join("; ")}`);
  run.lf = null;
  const v = run.manifest.volume, image = run.manifest.env.LAYERFS_IMAGE;
  const walBytes = Number(docker(["run", "--rm", "--network", "none", "-v", `${v}:/v:ro`, "--entrypoint", "sh", image, "-c", "stat -c %s /v/global/store.sqlite-wal 2>/dev/null || echo 0"]));
  // The daemons are gone; this is the only connection. Handles::seal does the same
  // checkpoint, but needs the catalog keys the runner does not hold.
  const out = docker(["run", "--rm", "--network", "none", "--user", "0", "-v", `${v}:/v`, "--entrypoint", "python3", image, "-c",
    "import sqlite3,os;c=sqlite3.connect('/v/global/store.sqlite');r=c.execute('pragma wal_checkpoint(TRUNCATE)').fetchone();p=c.execute('pragma page_size').fetchone()[0];c.close();w='/v/global/store.sqlite-wal';print(r[0],p,os.path.getsize(w) if os.path.exists(w) else 0)"]);
  const [busy, page, after] = out.split(" ").map(Number);
  if (busy !== 0 || after !== 0) throw new Error(`seal: checkpoint busy ${busy}, WAL ${after} bytes after`);
  if (page !== 4096) throw new Error(`seal: page size ${page}, not 4096`);
  return { walBytes, sealMs: Math.round(performance.now() - t0) };
}

function snapshot(run, k, facts) {
  const factsFile = join(run.dir, `facts-${pad(k)}.json`);
  writeJson(factsFile, facts);
  const dir = run.manifest.outputs.snapshots;
  mkdirSync(dir, { recursive: true });
  const r = spawnSync("node", [join(here, "snapshot.mjs"), "take", "--range", String(k), "--volume", run.manifest.volume, "--image", run.manifest.env.LAYERFS_IMAGE, "--dir", dir, "--facts", factsFile], { encoding: "utf8" });
  if (r.status !== 0) throw new Error(`snapshot: ${r.stderr.slice(0, 400)}`);
  const file = manifestPath(dir, k, run.manifest.run), m = JSON.parse(readFileSync(file, "utf8"));
  return { size: m.size, newBlocks: m.newBlocks, newBytes: m.newBytes, copyMs: m.copyMs, sealMs: facts.sealMs, walBytes: facts.walBytes, manifest: file };
}

/**
 * The runner process's memory (lead, 2026-10-18, after the p3j OOM): peak
 * resident set since the process started (one play command), and the current
 * split: JS heap, external and ArrayBuffer memory (Buffers), the rest native
 * (the SDK's in-process Store among it).
 */
export function runnerMemory() {
  const u = process.memoryUsage(), mb = (n) => +(n / 2 ** 20).toFixed(1);
  return { peakRssMb: mb(process.resourceUsage().maxRSS * 1024), rssMb: mb(u.rss), heapUsedMb: mb(u.heapUsed), heapTotalMb: mb(u.heapTotal), externalMb: mb(u.external), arrayBuffersMb: mb(u.arrayBuffers) };
}

/** Thrown inside playRange to end a `--until lanes` first half (never an error). */
const HALFWAY = Symbol("halfway");

/** Plays range k. Returns the exit code the range ends with (0 to go on). */
async function playRange(run, k, mode, half = null, until = null, cut = null) {
  const phase = PHASES[run.manifest.phase], measured = mode === "measured";
  // Tooling wall time per stage (never operation latency: that is m.ops).
  const plan = run.plan(k), wall = {};
  let t0 = performance.now();
  // per-stage progress on stderr (lead 2026-10-18), so a command stopped at its ceiling shows where the time went
  run.progress = (what) => console.error(`[${new Date().toISOString().slice(11, 19)} r${pad(k)} +${((performance.now() - t0) / 1000).toFixed(1)}s] ${what}`);
  const lap = (name, since) => { wall[name] = Math.round(performance.now() - since); run.progress(`${name} ${wall[name]} ms`); };
  // the second half of a range played in two commands (halves.mjs): its saved first half, checked before anything runs
  const saved = half === "resume" ? loadHalf(run, k) : null;
  if (saved?.refused) { console.error(`range ${k} resume refused: ${saved.refused}`); return EXIT.guard; }
  const late = !!saved && LATE_STAGES.has(saved.stage);
  if (late && cutTrace(saved)) console.error(`range ${k}: trace cut back to ${saved.traceBytes} bytes (a killed step after ${saved.stage})`);
  // prepare: binaries, disk, calibration
  const binaryProblem = checkBinaries(run);
  if (binaryProblem) { console.error(`range ${k} refused: ${binaryProblem}`); return EXIT.guard; }
  const free = freeBytes(run);
  const growth = Math.max(0, ...run.state.growth);
  const guard = diskGuard({ storeBytes: run.state.storeBytes ?? 0, growthBytes: growth, installPeak: phase.tests ? 3 * 2 ** 30 : 0, ...free, rangesLeft: 202 - k });
  if (!guard.ok) { console.error(`range ${k} refused: ${guard.why}`); return EXIT.guard; }
  if (phase.tests && measured && !existsSync(join(run.planDir, `tests-${pad(k)}.json`))) { console.error(`range ${k} refused: no tests-${pad(k)}.json; calibrate it first`); return EXIT.guard; }
  if (!run.lf) await run.client();
  const p2 = phase.lanes === "plan";
  if (p2) await pool(run, k, plan.agents.length);
  lap("prepareMs", t0);
  const outputs = run.manifest.outputs, attempt = saved ? saved.attempt : measured ? nextAttempt(outputs.metrics, k) : 0;
  const traceFile = measured ? join(run.dir, "trace", `range-${pad(k)}.a${attempt}.jsonl`) : null;
  if (traceFile) mkdirSync(join(run.dir, "trace"), { recursive: true });
  run.traceTo(traceFile, `r${pad(k)}`);
  const m = { range: k, attempt, run: run.manifest.run, phase: run.manifest.phase, label: run.manifest.label, mode, started: new Date().toISOString(),
    binary: run.manifest.binary, plan: { version: run.manifest.planVersion, checkpoint: plan.checkpoint }, policy: run.manifest.policyName,
    runner: runnerFacts(process.env),
    // owner 2026-10-18: the 1-min load average where the player runs, at the start and end of the range (end: metrics)
    hostLoad: { where: "runner (Docker VM kernel)", start: loadNow() } };
  if (saved) Object.assign(m, { started: saved.started, hostLoad: { ...m.hostLoad, start: saved.hostLoadStart, resume: m.hostLoad.start } });
  const before = saved ? saved.before : measured ? await run.op.store.stats() : null;
  const { ops, reconcile, left } = p2 ? { ops: [], reconcile: [], left: {} } : phaseOps(plan, run.manifest.phase);
  let branch = `r${pad(k)}-lane`;
  let ctx = p2 ? null : { ops, reconcile, branch, tree: new Tree(lsTree(run.repo, run.state.prevCommit).files), work: { fs: 0, sandbox: 0, commits: 0 }, measured };
  const depthBefore = saved ? saved.depthBefore : run.state.depth.commits;
  let failure = null, published = null, proof = null, tests = null, probeOut = {}, versionOut = null;
  const startedFrom = Object.keys(run.state.heads ?? {}).length || !run.state.forkedFrom ? { kind: "live", range: k - 1 } : { kind: "fork", range: run.state.forkedFrom.range, run: run.state.forkedFrom.run };
  run.tally.calls = 0;
  run.sink.log.length = 0;
  let halfway = false;
  if (saved) {
    // the first half's calls, laps and wall: the range's figures cover both commands; nothing is replayed
    run.sink.seq = saved.sink.seq; run.sink.log.push(...saved.sink.log); run.tally.calls = saved.calls;
    Object.assign(wall, saved.wall, { resumePrepareMs: wall.prepareMs, prepareMs: saved.wall.prepareMs });
    t0 -= saved.elapsedMs;
    run.state.halfway = null;
    dropHalf(run, k);
  }
  try {
    let since = performance.now();
    if (p2) {
      if (!run.state.head) throw new Error("P2 continues a run whose first range wrote the probe fixture (a P1 run, or a fork of one)");
      const stop = (stage, extra = {}) => { saveHalf(run, k, { stage, ctx, attempt, traceFile, started: m.started, hostLoadStart: m.hostLoad.start, before, depthBefore, wall, elapsedMs: Math.round(performance.now() - t0), ...extra }); throw HALFWAY; };
      const rebuildP2 = (base) => p2Plan(plan, new Set(new Tree(base).dirs.keys()));
      if (late) { ctx = lateCtxFromJson(saved.ctx, rebuildP2); published = decodeLate(saved.published); branch = ctx.final; ctx.tree = ctx.mainTree; }
      else if (saved) ctx = ctxFromJson(saved.ctx, rebuildP2);
      else ctx = await startRange(run, k, plan, measured);
      if (!late) {
      // `--until lead` stops after the fork, the seed and the lead's first install (NODE_RULE §2); playMs then sums both parts
      if (until === "lead" && !saved) { lap("startMs", since); stop("lead"); }
      if (!saved || saved.stage === "lead" || saved.stage === "part") {
        // --cut (lanes in parts, each command under 120 s): this part's agents stop at that plan order; playMs sums the parts
        const playedMs = saved?.stage === "part" ? saved.wall.playMs ?? 0 : 0;
        await playAgents(run, k, ctx, { cut });
        lap("playMs", since);
        wall.playMs += playedMs;
        if (wall.startMs != null && saved?.stage !== "part") wall.playMs += wall.startMs;
        if (cut != null) stop("part");
      }
      if (until === "lanes" && (saved?.stage === "lead" || saved?.stage === "part")) stop("lanes");
      else if (until === "lanes" && !saved) stop("lanes");
      since = performance.now();
      const beforePublish = phase.closure ? async (cur) => rangeClosure(run, k, plan, cur, { sb: await setup(run), expectCall, Mismatch, oracleDir: run.manifest.oracle, checks: run.manifest.label === "dev", lwwPicked: !!ctx.lww?.picks.some((p) => p.picks > 0), dumpTo: run.manifest.label === "dev" ? (mkdirSync(join(run.dir, "closure"), { recursive: true }), join(run.dir, "closure", `dump-${pad(k)}.json`)) : null }) : null;
      published = await consolidateLanes(run, k, plan, ctx, { beforePublish });
      branch = ctx.final;
      ctx.tree = ctx.mainTree;
      // the node_modules chain since the last install proved equal to a clean one (closure.mjs nextChain)
      if (ctx.closure?.executed) run.state.closureChain = nextChain(run.state.closureChain, k, plan.checkpoint, ctx.closure.executed);
      if (ctx.closure?.groups) {
        const file = join(run.dir, "closure", `groups-${pad(k)}.json`);
        writeJson(file, ctx.closure.groups);
        run.state.installed = true; run.state.nmGroupsFile = file;
      }
      lap("consolidateMs", since);
      // step 4: the final command in steps, each under its own alarm (repair, then verify, then the rest)
      if (until === "repair") stop("published", { published });
      }
    } else {
      run.label(`r${pad(k)}.fork`);
      await run.lf.branch.fork(branch, "main");
      // The first range writes the probe fixture (ignored paths) first: its Commit
      // is the checkpoint check's base, since Init's Layer has no Commit.
      if (!run.state.head) {
        run.label(`r${pad(k)}.probe-fixture`);
        run.state.head = (await run.lf.fs.apply(branch, probeFixture(), "scale probe fixture (SPEC §3c)")).head;
        run.state.depth.commits++;
      }
      run.rec.agent = "a01";
      for (const op of ops) await step(run, k, op.id, ctx);
      run.rec.agent = "lead";
      lap("playMs", since);
      since = performance.now();
      await consolidate(run, k, "reconcile", ctx);
      published = await consolidate(run, k, "publish", ctx);
      lap("consolidateMs", since);
    }
    since = performance.now();
    const snapshotDue = measured && (snapshotsEvery(phase, run.manifest) || due({ planned: plan.snapshot, verdict: "pass", sinceMs: run.state.sinceMs, lastCostMs: run.state.lastSnapshotMs }).due);
    if (saved?.stage === "verified") proof = decodeLate(saved.proof);
    else {
      proof = await verify(run, k, { prevHead: run.state.head, head: published.source.commit, layer: published.publishedLayer.id, prevCommit: run.state.prevCommit, full: snapshotDue });
      lap("verifyMs", since);
      if (p2 && until === "verified") { saveHalf(run, k, { stage: "verified", ctx, attempt, traceFile, started: m.started, hostLoadStart: m.hostLoad.start, before, depthBefore, wall, elapsedMs: Math.round(performance.now() - t0), published, proof }); throw HALFWAY; }
    }
    wall.verify = snapshotDue ? "diff_commits + full compareTree" : "diff_commits";
    if (!proof.ok) failure = `the checkpoint differs from git: ${JSON.stringify({ paths: proof.paths, ids: proof.ids, gitStray: proof.gitStray?.slice(0, 5), tree: proof.tree && { missing: proof.tree.missing.slice(0, 5), extra: proof.tree.extra.slice(0, 5), content: proof.tree.content.slice(0, 5), mode: proof.tree.mode.slice(0, 5) } }).slice(0, 1500)}`;
    if (!failure && phase.tests && !phase.closure && measured) { since = performance.now(); tests = await closure(run, k, "tests", { layer: published.publishedLayer.id }); lap("testsMs", since); }
    if (!failure && phase.probes && measured) { since = performance.now(); probeOut = await probes(run, k, { branch, tree: ctx.tree }); lap("probesMs", since); }
    // the latest version as LayerFS shows it (REPORT_FORMAT.md §4), every range
    if (!failure && measured) { since = performance.now(); versionOut = await versionStats(run, k, published.publishedLayer.id, { items: proof?.items ?? null, crossCheck: snapshotDue || !!plan.milestone }); lap("versionMs", since); }
    m.snapshotDue = snapshotDue;
  } catch (error) {
    if (error === HALFWAY) halfway = true;
    else {
      if (!(error instanceof Mismatch)) console.error(error.stack ?? error);
      failure = error instanceof Mismatch ? error.message : `error: ${error.message}`;
    }
  }
  if (run.rec) run.rec.agent = "lead";
  run.traceTo(null, undefined);
  if (halfway) {
    run.state.halfway = k;
    run.save();
    console.log(`range ${k}: first half saved (${run.tally.calls} calls; tooling ${JSON.stringify({ kind: "tooling", firstHalfMs: Math.round(performance.now() - t0), ...wall })}); continue with play --resume`);
    return EXIT.done;
  }
  const head = published?.source?.commit ?? null, layer = published?.publishedLayer?.id ?? null;
  m.head = head; m.layer = layer; m.failure = failure;
  m.depth = { before: depthBefore, after: run.state.depth.commits + (ctx?.work.commits ?? 0) };
  if (!measured) {
    const stages = { kind: "tooling", totalMs: Math.round(performance.now() - t0), ...wall };
    // a closure's steps and development checks are kept in fast mode too; their stored bytes need the trace (measured mode)
    const cl = ctx?.closure && !ctx.closure.skipped ? { steps: ctx.closure.steps, rows: ctx.closure.rows, oracleOk: ctx.closure.oracle?.ok ?? null, rebuild: ctx.closure.rebuild ?? null, reinstallCheck: ctx.closure.reinstallCheck ?? null } : null;
    writeJson(join(run.dir, "fast", `range-${pad(k)}.json`), { range: k, mode, head, failure, calls: run.tally.calls, wall: stages, runnerMemory: runnerMemory(), ...(cl ? { closure: cl } : {}), ...(ctx?.git ? { git: gitFacts(ctx) } : {}), ...(ctx?.node ? { node: nodeFacts(run, k, ctx) } : {}), ...(ctx?.lww ? { lww: { ...ctx.lww, total: ctx.lww.picks.reduce((n, p) => n + p.picks, 0) } } : {}) });
    console.log(`range ${k}: ${failure ? `STOP ${failure}` : "ok"} (${run.tally.calls} calls; tooling ${JSON.stringify(stages)})`);
    if (failure) { run.state.dirty = k; run.save(); return EXIT.stop; }
    advance(run, k, plan, head, layer, ctx, performance.now() - t0);
    return EXIT.done;
  }
  // measured: storage, metrics, snapshot, report
  let since = performance.now();
  const t = readTrace(traceFile, run.sink.log);
  const deltaTotal = addDelta(run.state.deltaTotal ?? null, t.delta);
  const after = await run.op.store.stats().catch(() => null);
  const snap = await run.op.inspect.snapshot().catch(() => null);
  const changes = diffTrees(run.repo, run.state.prevCommit, plan.checkpoint).filter((c) => !c.gitlink && c.mode !== "000000");
  const sizes = blobSizes(run.repo, changes.map((c) => c.blob));
  const newStored = after && before ? after.stored + after.metadata - before.stored - before.metadata : null;
  m.storage = after && {
    logical: after.logical, canonical: after.canonical, stored: after.stored, metadata: after.metadata, file: after.file, free: after.free,
    newStored, newMetadata: after.metadata - before.metadata, newPacks: after.stored - before.stored,
    changedBytes: changes.reduce((n, c) => n + (sizes.get(c.blob) ?? 0), 0),
    directoryShare: newStored > 0 ? +((after.metadata - before.metadata) / newStored).toFixed(3) : null,
    delta: deltaSummary(t.delta, caps(run.manifest.policy)),
    deltaTotal: deltaSummary(deltaTotal, caps(run.manifest.policy)),
    reinstall: null,
  };
  // owner S4: the generated /.lww and the picks its rules made, per merge
  if (ctx?.git) m.git = gitFacts(ctx);
  // NODE_RULE: the points as played (their proofs come from nodeproof.mjs proofs), the trace facts p3 needs
  if (ctx?.node) m.node = nodeFacts(run, k, ctx);
  if (m.phase === "p3") m.p3raw = p3Raw(t.all);
  if (ctx?.lww) m.lww = { ...ctx.lww, total: ctx.lww.picks.reduce((n, p) => n + p.picks, 0) };
  if (ctx?.units) m.units = ctx.units;
  if (ctx?.closure && !ctx.closure.skipped) {
    // P3: storage by the step's own Commit (traced sizes), the reinstall gate, STORAGE_STUDY §8
    const commitOf = (kind) => t.all.find((l) => l.method === "sandbox.commit" && l.step === `r${pad(k)}.${kind}`);
    const inst = ctx.closure.rows.find((r) => /install/.test(r.kind)), build = ctx.closure.rows.find((r) => r.kind === "build");
    const instSizes = inst ? commitOf(inst.kind)?.sizes ?? null : null;
    if (ctx.closure.reinstall && m.storage) m.storage.reinstall = { changedPackages: ctx.closure.reinstall.changedPackages, rawChangedBytes: ctx.closure.reinstall.rawChangedBytes, storedNewBytes: instSizes?.newStored ?? null };
    m.closure = { lwwPicked: !!ctx?.lww?.picks.some((p) => p.picks > 0), steps: ctx.closure.steps, rows: ctx.closure.rows, oracle: ctx.closure.oracle ?? null, oracleKind: ctx.closure.oracleKind ?? null, normalized: ctx.closure.normalized ?? null, earlierRoots: ctx.closure.earlierRoots ?? null, outputOk: ctx.closure.outputOk ?? null, repairGroups: ctx.closure.repairGroups ?? null };
    // the development checks run after the publish: run.mjs devcheck (devcheck.mjs)
    m.study = studyMeasurements({
      fsWrites: t.all.filter((l) => l.method === "fs.write" && l.sizes).map((l) => ({ sizes: l.sizes })),
      install: inst ? { sizes: instSizes, delta: deltaSummary(deltaWork(t.all.filter((l) => l.step === `r${pad(k)}.${inst.kind}`)), caps(run.manifest.policy)), prevGroups: ctx.closure.prevGroups, groups: ctx.closure.groups, changed: ctx.closure.reinstall?.changed } : null,
      build: build ? { sizes: commitOf("build")?.sizes ?? null, bytes: build.bytes } : null,
    });
  }
  m.ops = aggregate(t.calls);
  m.opsTrace = aggregate(t.callsTrace);
  // owner 2026-10-19: per tracked class, read counters and the WAL beside p50 and SQL work (growth.mjs; watch only)
  m.growth = growthByClass(t.all, run.sink.log);
  // the call records beside the trace, so a later re-derivation keeps the size classes (SPEC §5)
  if (traceFile) writeFileSync(traceFile.replace(/\.jsonl$/, ".calls.jsonl"), run.sink.log.map((e) => JSON.stringify({ seq: e.seq, method: e.method, size: e.size ?? null, kind: e.kind ?? null, ...(e.newCommit ? { newCommit: true } : {}), ...(e.io ? { io: e.io } : {}), ...(e.wal ? { wal: e.wal } : {}) })).join("\n") + "\n");
  // every call by method (SPEC §3b), and the checkpoint diff's cost per entry it lists (SPEC §4)
  m.calls = callTable(t.all, run.sink.log);
  const diff = checkpointDiff(t.all, run.sink.log, `r${pad(k)}.verify`, proof?.changedDirs ?? null);
  m.perUnit = diff ? { "branch.diff_commits": diff } : {};
  // the checkpoint tree the scoped probes read (gates.mjs SCOPED)
  const oracle = JSON.parse(readFileSync(join(run.manifest.oracle, `oracle-${pad(k)}.json`), "utf8"));
  m.inputs = { tree: { files: oracle.files, bytes: oracle.bytes } };
  m.probes = Object.fromEntries(Object.entries(probeOut).map(([name, p]) => [name, { ms: p.ms, ...(p.samples ? { samples: p.samples, load: p.load } : {}), ...(p.version ? { version: p.version } : {}), ...(p.input ? { input: p.input } : {}), ...(p.error ? { error: p.error } : {}), counters: t.probe[name] ?? {} }]));
  // the one-shot probe split (steps.mjs oneshotSplit): both values from the trace, per sample, then their median;
  // the counters stay the first sample's (as every probe's)
  if (m.probes.oneshot_mount_unmount && !m.probes.oneshot_mount_unmount.error) {
    const per = (m.probes.oneshot_mount_unmount.samples ?? [null]).map((_, i) => oneshotSplit(t.all.filter((l) => String(l.step) === `${i ? `probe-s${i}` : "probe"}:oneshot_mount_unmount` || String(l.step) === `${i ? `probe-s${i}` : "probe"}:oneshot_exec`))).filter(Boolean);
    if (per.length) {
      const med = (f) => median(per.map(f).filter((x) => x != null));
      const [mu, ex] = [per[0].oneshot_mount_unmount, per[0].oneshot_exec];
      const fuse = Math.max(...per.map((x) => x.oneshot_exec.fuseRequests));
      Object.assign(m.probes, {
        oneshot_mount_unmount: { ...mu, ms: med((x) => x.oneshot_mount_unmount.ms), samples: per.map((x) => x.oneshot_mount_unmount.ms), load: m.probes.oneshot_mount_unmount.load, sequenceMs: m.probes.oneshot_mount_unmount.ms },
        oneshot_exec: { ...ex, ms: med((x) => x.oneshot_exec.ms), samples: per.map((x) => x.oneshot_exec.ms), wallMs: med((x) => x.oneshot_exec.wallMs), fuseRequests: fuse, ...(fuse ? { untimed: true } : { untimed: undefined }), load: m.probes.oneshot_mount_unmount.load },
      });
      if (!fuse) delete m.probes.oneshot_exec.untimed;
    }
  }
  m.hostLoad = { ...m.hostLoad, end: loadNow() };
  m.runnerMemory = runnerMemory();
  // the Sandbox pool's sharing (P3: 4 shared Sandboxes): Workspaces and mount/unmount calls at once, per Sandbox
  m.pool = { size: run.pool?.length ?? null, sharing: poolSharing(t.all) };
  const open = snap?.sandboxes?.reduce((n, s) => n + (s.workspaces?.length ?? 0), 0) ?? null;
  const hl = await sandboxHealth(run);
  m.health = { workspacesOpen: open, overlaysLeft: hl?.overlaysLeft ?? null, daemonRssMb: hl?.daemonRssMb ?? null, openFiles: hl?.openFiles ?? null, sandboxes: hl ? `${hl.sandboxes} of ${hl.of}` : null };
  m.startedFrom = startedFrom;
  // the latest version: LayerFS's walk, split by git's tracked figures (the tree matched git) and node_modules
  if (versionOut) {
    const v = versionOut, nm = v.nm, git = v.git ?? { files: 0, bytes: 0 }, tracked = { files: oracle.files, bytes: oracle.bytes };
    m.version = { how: v.how, looked: v.looked, bytes: v.bytes, files: v.files, dirs: v.dirs, symlinks: v.symlinks, largestFile: v.largestFile, largestDir: v.largestDir,
      tracked, nodeModules: { files: nm.files, bytes: nm.bytes }, build: { files: Math.max(0, v.files - nm.files - git.files - tracked.files), bytes: Math.max(0, v.bytes - nm.bytes - git.bytes - tracked.bytes) },
      ...(git.files ? { git: { files: git.files, bytes: git.bytes } } : {}) };
  }
  m.dsh = dshFacts(run.repo, plan, changes, sizes);
  m.execs = execFacts(t.all);
  m.defer = { d6: d6Triggers(t.all) };
  m.construction = t.construction;
  m.key = keyOps(t.calls, t.all, run.sink.log);
  const mounts = run.sink.log.filter((e) => e.method === "sandbox.mount");
  const heldIds = new Set(p2 ? [...ctx.p2.held.keys()].filter((id) => /mount/.test(plan.steps.find((s) => s.id === id)?.kind ?? "")) : []);
  const held = mounts.filter((e) => heldIds.has(e.label)).length;
  const played = p2 ? ctx.played : new Map([["a01", { fs: ops.length, sandbox: 0, branch: 0, project: 0 }]]);
  const leadSteps = p2 ? ctx.leadSteps : [{ op: "reconcile", category: "fs" }, { op: "publish", category: "branch" }];
  const stepLane = new Map(plan.steps.map((s) => [s.id, s.lane]));
  m.work = { bashCalls: [...played.values()].reduce((n, by) => n + Object.values(by).reduce((x, y) => x + y, 0), 0) + leadSteps.length,
    lanes: p2 ? plan.lanes.length : 1, agents: p2 ? plan.agents.length : 1, lfsCommits: ctx.work.commits,
    workspaces: mounts.length, oneShot: mounts.length - held, longLived: held, oneShotShare: mounts.length ? +((mounts.length - held) / mounts.length).toFixed(3) : null,
    fileMutations: { fs: ctx.work.fs, sandbox: ctx.work.sandbox }, mutations: ctx.work.mutations ?? null,
    reads: p2 ? plan.steps.reduce((n, s) => n + (s.reads?.length ?? 0), 0) : ops.reduce((n, o) => n + o.reads.length, 0),
    reconcile: p2 ? ctx.p2.reconcile.length : reconcile.length, leftOut: p2 ? ctx.p2.left : left, sdkCalls: t.lines };
  m.overview = buildOverview({ plan: p2 ? plan : { ...plan, conflicts: [], lanes: [{ name: branch, agents: ["a01"] }], agents: ["a01"] }, log: run.sink.log, played, leadSteps,
    // a step's lane git exec (`<step>.git-commit`, gitplay.mjs) and a test point's labels (`<lane>.<mid|end>.install|refresh|
    // tsc|vitest`, nodelanes.mjs) are that lane's
    laneOf: (label) => (p2 ? stepLane.get(label) ?? stepLane.get(String(label ?? "").replace(/\.git-commit$/, "")) ?? plan.lanes.find((l) => String(label ?? "").startsWith(`${l.name}.`))?.name ?? null : String(label ?? "").startsWith(`r${pad(k)}.s`) ? branch : null),
    events: ctx.events ?? [], race: ctx.race ?? null, merged: ctx.merged ?? new Map(), tries: ctx.tries ?? new Map(), published: ctx.published ?? new Set(),
    lanesPlayed: p2 ? plan.lanes.map((l) => ({ name: l.name, agents: l.agents, steps: l.agents.reduce((n, a) => n + (ctx.steps.get(a) ?? 0), 0) })) : [{ name: branch, agents: ["a01"], steps: ops.length }],
    runningBefore: run.state.depth.commits, phase: run.manifest.phase });
  if (!p2) m.overview.planned = { branches: plan.lanes.length + 1, agents: plan.agents.length };
  const made = run.sink.log.filter((e) => (e.method === "branch.fork" && e.kind === "Forked") || (e.method === "branch.merge" && e.kind === "Merged")).length;
  m.history = { commits: m.depth.after, layers: run.state.depth.layers + 1, branches: run.state.depth.branches + made };
  const pathsOk = proof?.paths?.ok, idsOk = proof?.ids?.ok;
  m.checks = {
    tree: proof ? { ok: proof.ok, files: proof.tree?.files ?? proof.paths.git, missing: [...proof.paths.missing, ...proof.ids.missing, ...(proof.tree?.missing ?? [])], extra: [...proof.paths.extra, ...(proof.tree?.extra ?? [])],
      content: [...proof.ids.content, ...(proof.tree?.content ?? [])], mode: [...proof.ids.mode, ...(proof.tree?.mode ?? [])], paths: pathsOk, ids: idsOk, full: !!proof.tree,
      // fix 058: the untracked paths exempted because the checkpoint's .gitignore files ignore them, kept for review
      gitIgnored: proof.paths.gitIgnored ?? [] } : { ok: false, files: 0, missing: [], extra: [], content: [], mode: [] },
    history: { ok: !!layer },
    steps: { matched: failure ? Math.max(run.tally.calls - 1, 0) : run.tally.calls, total: run.tally.calls },
    conflicts: { planned: p2 ? plan.conflicts.length : 0, hit: p2 ? m.overview.conflicts.reduce((n, c) => n + c.hit, 0) : 0, unplanned: 0,
      byKind: Object.fromEntries(m.overview.conflicts.map((c) => [c.kind, { hit: c.hit, planned: c.planned }])) },
    ignored: { ok: true },
    tests: tests ?? (ctx?.closure?.rows?.find((r) => r.kind === "test")?.results ?? { equal: 0, run: 0 }),
  };
  lap("metricsMs", since);
  m.budget = { diskProjected: guard.projected, diskBudget: free.dockerFree + (run.state.storeBytes ?? 0),
    diskModel: diskModel({ storeBytes: m.storage?.file ?? run.state.storeBytes ?? 0, k, perCommitBytes: m.storage?.newStored && m.work?.lfsCommits ? m.storage.newStored / m.work.lfsCommits : null, ranges: JSON.parse(readFileSync(join(run.planDir, "plan.json"), "utf8")).ranges }) };
  if (!failure && m.snapshotDue) {
    try {
      const sealed = await seal(run);
      wall.sealMs = sealed.sealMs;
      since = performance.now();
      const sf = sealedFacts(run);
      m.storeDisk = { ...sf.disk, sealed: true };
      m.figures = sf.figures;
      lap("figuresMs", since);
      since = performance.now();
      m.snapshot = snapshot(run, k, { run: run.manifest.run, dsh: plan.checkpoint, tree: plan.tree, head, layer, depth: m.depth.after, daemon: run.manifest.binary.daemon,
        sdk: run.manifest.binary.sdk, planVersion: run.manifest.planVersion, policy: run.manifest.policy ?? "default", pageSize: 4096, ...sealed,
        state: { next: k + 1, layer, head, prevCommit: plan.checkpoint, depth: { ...run.state.depth, commits: m.depth.after }, deltaTotal, ...p3StateOf(run.state) } });
      lap("snapshotMs", since);
    } catch (error) { failure = `snapshot: ${error.message}`; m.failure = failure; m.checks.history.ok = false; }
  }
  if (!m.storeDisk && !failure) { since = performance.now(); m.storeDisk = { ...liveDisk(run), sealed: false }; lap("diskMs", since); }
  if (!failure && m.storeDisk) {
    // REPORT_FORMAT §3/§9: parts, sources, per change and per Commit
    const store = m.storeDisk.allocated + (m.storeDisk.walAllocated ?? 0);
    const added = addedBySource(t.all, stepSource(k));
    const total = (key) => Object.values(added).reduce((n, x) => n + x[key], 0);
    const parts = m.figures ? sealedParts(m.figures, store) : liveParts(run.state.parts, { content: total("content"), metadata: total("metadata") }, store);
    const prevBy = run.state.bySource ?? seedBySource(parts, added);
    if (parts && prevBy) {
      const bySource = cumulative(prevBy, added);
      const changed = { tracked: m.storage?.changedBytes ?? 0, nodeModules: ctx?.closure?.groups ? changedGroupBytes(ctx.closure.prevGroups, ctx.closure.groups) : 0,
        build: Object.values(ctx?.closure?.rows?.find((r) => r.kind === "build")?.bytes ?? {}).reduce((n, x) => n + x, 0), git: ctx?.git?.changedBytes ?? 0 };
      m.storageReport = storageFigures({ parts, prevParts: run.state.parts ?? null, bySource, added, version: m.version, changed, commits: m.work?.lfsCommits });
      run.state.parts = parts; run.state.bySource = bySource;
    }
  }
  // REPORT_FORMAT §10.1: the P3 object (proofs NOT_RUN until nodeproof.mjs proofs runs the native oracles)
  if (m.phase === "p3") m.p3 = fillP3(m, { groupsOf: (id) => { try { return JSON.parse(readFileSync(groupsFile(run, k, id), "utf8")); } catch { return null; } } });
  m.wall = { kind: "tooling", totalMs: Math.round(performance.now() - t0), ...wall };
  const budget = loadBudget(undefined, m.phase);
  if (budget) Object.assign(m.budget, wallBudget(budget, m.phase, readAttempts(outputs.metrics), { range: k, totalMs: m.wall.totalMs }));
  const file = join(outputs.metrics, `range-${pad(k)}.a${attempt}.json`);
  writeJson(file, m);
  if (failure) { run.state.dirty = k; run.save(); }
  else { run.state.deltaTotal = deltaTotal; advance(run, k, plan, head, layer, ctx, m.wall.totalMs, m); }
  since = performance.now();
  // Only range k's report (SPEC §3 F2): it stores this attempt's gate result in its metrics file.
  const r = spawnSync("node", [join(here, "report.mjs"), "--metrics", outputs.metrics, "--plan", run.planDir, "--docs", outputs.docs, "--oracle", run.manifest.oracle, "--range", String(k)], { encoding: "utf8" });
  // The report's own time is known only after it ran: added to the metrics
  // file as report.mjs left it (with the stored gate result).
  const stored = JSON.parse(readFileSync(file, "utf8"));
  stored.wall = { ...m.wall, reportMs: Math.round(performance.now() - since), totalMs: Math.round(performance.now() - t0) };
  writeJson(file, stored);
  process.stdout.write(r.stdout); process.stderr.write(r.stderr);
  console.log(`range ${k} attempt ${attempt}: ${failure ? `STOP ${failure}` : "checkpoint ok"}; metrics ${file}`);
  if (failure) return EXIT.stop;
  return { 0: EXIT.done, 3: EXIT.optimize, 4: EXIT.stop }[r.status] ?? EXIT.error;
}

function advance(run, k, plan, head, layer, ctx, ms, m = null) {
  const s = run.state;
  s.next = k + 1; s.layer = layer; s.head = head; s.prevCommit = plan.checkpoint; s.heads[k] = head; s.layers[k] = layer;
  // Branches made in the range: forks and merges (every Merged makes one), probes and checks included
  const made = run.sink.log.filter((e) => (e.method === "branch.fork" && e.kind === "Forked") || (e.method === "branch.merge" && e.kind === "Merged")).length;
  s.depth = { commits: s.depth.commits + ctx.work.commits, layers: s.depth.layers + 1, branches: s.depth.branches + (made || 1) };
  if (m?.storage) { s.storeBytes = m.storage.file; s.growth = [...s.growth, m.storage.newStored ?? 0].slice(-20); }
  if (m?.snapshot) { s.sinceMs = []; s.lastSnapshotMs = (m.snapshot.sealMs ?? 0) + m.snapshot.copyMs; s.lastSnapshot = k; } else s.sinceMs = [...s.sinceMs, Math.round(ms)];
  s.dirty = null;
  run.save();
}

async function cmdPlay(o) {
  const run = new Run(join(HISTORY, "runs", o.run));
  const mode = o.mode ?? "measured", from = Number(o.from), to = Number(o.to);
  if (!["measured", "fast"].includes(mode) || !Number.isInteger(from) || !Number.isInteger(to) || to < from) return usage();
  if (run.state.dirty != null) { console.error(`run ${o.run} stopped in range ${run.state.dirty}; recover by fork from a snapshot (SPEC §6)`); return EXIT.guard; }
  if (from !== run.state.next) { console.error(`run ${o.run} stands at range ${run.state.next}, not ${from}`); return EXIT.usage; }
  // a range in two commands (halves.mjs): one range per command; a run halfway through a range only resumes it
  // `--until lead` (after the lead's install), `--until lanes` (after the agents); `--resume` continues from either, and
  // `--resume --until lanes` continues a lead stop to the lanes stop: a range with git and Node on in three commands
  const until = o.until ?? null, half = "resume" in o ? "resume" : until ? "until" : null;
  if (until && !["lead", "lanes", "repair", "verified"].includes(until)) return usage();
  // --cut <order> (with --until lanes): the lanes stage stops at that plan order and saves; a later --resume continues it
  const cut = o.cut == null ? null : Number(o.cut);
  if (cut != null) {
    if (until !== "lanes" || !Number.isFinite(cut)) { console.error("--cut <plan order> goes with --until lanes"); return EXIT.usage; }
    const why = safeCut(run.plan(from), cut);
    if (why) { console.error(`--cut ${cut}: ${why}`); return EXIT.usage; }
  }
  if (half && to !== from) { console.error("--until and --resume play one range (--to = --from)"); return EXIT.usage; }
  if (until && PHASES[run.manifest.phase]?.lanes !== "plan") { console.error(`--until ${until} needs a lanes phase (P2 on), not ${run.manifest.phase}`); return EXIT.usage; }
  if (until === "lead" && half === "resume") { console.error("--until lead starts a range; it does not resume one"); return EXIT.usage; }
  if (run.state.halfway != null && half !== "resume") { console.error(`run ${o.run} is halfway through range ${run.state.halfway}; continue it with play --resume`); return EXIT.guard; }
  if (mode === "measured") process.env.LAYERFS_CONSTRUCTION_WORKERS = "1";
  let code = EXIT.done;
  try {
    for (let k = from; k <= to && code === EXIT.done; k++) code = await playRange(run, k, mode, half, until, cut);
  } catch (error) {
    console.error(error.stack ?? error);
    code = EXIT.error;
  } finally {
    const problems = await teardown(run);
    if (problems.length) console.error(`teardown: ${problems.join("; ")}`);
    run.close();
  }
  return code;
}

/** Moves a run to the next phase at the range it stands at; its binaries and Store stay (SPEC §9). */
function cmdPhase(o) {
  const dir = join(HISTORY, "runs", o.run), run = new Run(dir);
  const why = nextPhase(run.manifest.phase, o.phase);
  if (why) { console.error(`run ${o.run}: ${why}`); return EXIT.usage; }
  if (run.state?.dirty != null) { console.error(`run ${o.run} stopped in range ${run.state.dirty}; recover by fork first`); return EXIT.guard; }
  const entry = { from: run.manifest.phase, to: o.phase, atRange: run.state.next, at: new Date().toISOString(), binary: run.manifest.binary };
  run.manifest.phases = [...(run.manifest.phases ?? []), entry];
  run.manifest.phase = o.phase;
  writeJson(join(dir, "run.json"), run.manifest);
  run.note({ kind: "phase", name: `${entry.from}->${entry.to}`, atRange: entry.atRange });
  console.log(JSON.stringify({ run: o.run, ...entry }, null, 1));
  return EXIT.done;
}

/** The labels git and NODE_RULE can be switched on for (a control run never). */
export const SWITCHABLE = new Set(["dev", "measured", "baseline"]);

/** Turns F-031 option (c) on for a run in a closure phase, from the range it stands at (gitplay.mjs). */
function cmdGit(o) {
  const dir = join(HISTORY, "runs", o.run), run = new Run(dir);
  if (!("on" in o)) return usage();
  // the dev proof was accepted on f031-r1-slice-h (liaison under owner delegation 2026-10-19): main line and baselines too
  if (!SWITCHABLE.has(run.manifest.label)) { console.error(`run ${o.run}: git is for ${[...SWITCHABLE].join(", ")} runs (label ${run.manifest.label})`); return EXIT.usage; }
  if (!PHASES[run.manifest.phase]?.closure) { console.error(`run ${o.run}: git starts in a closure phase (P3)`); return EXIT.usage; }
  if (run.state?.dirty != null) { console.error(`run ${o.run} stopped in range ${run.state.dirty}; recover by fork first`); return EXIT.guard; }
  run.manifest.git = { on: true, atRange: run.state.next, at: new Date().toISOString() };
  writeJson(join(dir, "run.json"), run.manifest);
  run.note({ kind: "git", name: "F-031 option (c) on", atRange: run.state.next });
  console.log(JSON.stringify({ run: o.run, git: run.manifest.git }));
  return EXIT.done;
}

/** Whether a measured range takes a snapshot whatever due() says: the phase's own "every", or the run's switch (fix 071). */
export const snapshotsEvery = (phase, manifest) => phase.snapshot === "every" || manifest.snapshots?.every === true;

/** Snapshots every measured range for a run, from the range it stands at (liaison 2026-10-20 for ranges 51-60, fix 071). */
function cmdSnapshots(o) {
  const dir = join(HISTORY, "runs", o.run), run = new Run(dir);
  if (!("every" in o)) return usage();
  if (run.state?.dirty != null) { console.error(`run ${o.run} stopped in range ${run.state.dirty}; recover by fork first`); return EXIT.guard; }
  run.manifest.snapshots = { every: true, atRange: run.state.next, at: new Date().toISOString() };
  writeJson(join(dir, "run.json"), run.manifest);
  run.note({ kind: "snapshots", name: "every range", atRange: run.state.next });
  console.log(JSON.stringify({ run: o.run, snapshots: run.manifest.snapshots }));
  return EXIT.done;
}

/** Turns NODE_RULE on for a dev run in a closure phase, from the range it stands at (nodelanes.mjs), with its two switches. */
function cmdNode(o) {
  const dir = join(HISTORY, "runs", o.run), run = new Run(dir);
  if (!("on" in o)) return usage();
  if (!SWITCHABLE.has(run.manifest.label)) { console.error(`run ${o.run}: NODE_RULE churn is for ${[...SWITCHABLE].join(", ")} runs (label ${run.manifest.label})`); return EXIT.usage; }
  if (!PHASES[run.manifest.phase]?.closure) { console.error(`run ${o.run}: NODE_RULE starts in a closure phase (P3)`); return EXIT.usage; }
  const node = { on: true, inputsRule: o["inputs-rule"] ?? "plan", storePolicy: o["store-policy"] ?? "verified", atRange: run.state.next, at: new Date().toISOString() };
  const why = checkNode(nodeOf({ node })) ?? (STORE_POLICIES[node.storePolicy] == null ? `store policy ${node.storePolicy}: one of ${Object.keys(STORE_POLICIES).join(", ")}` : null);
  if (why) { console.error(`run ${o.run}: ${why}`); return EXIT.usage; }
  run.manifest.node = node;
  writeJson(join(dir, "run.json"), run.manifest);
  run.note({ kind: "node", name: "NODE_RULE on", atRange: run.state.next, inputsRule: node.inputsRule, storePolicy: node.storePolicy });
  console.log(JSON.stringify({ run: o.run, node }));
  return EXIT.done;
}

/** The pilot lines a phase-matched re-baseline forks from, newest format first (their range-1 snapshot). */
export const REBASELINE_SOURCES = ["p1-rebase-d", "p1-pilot-b"];

/**
 * A phase-matched speed baseline (lead decision, 2026-10-18): the pilot's
 * ranges 2-4 replayed with `phase`'s player on the given daemon and addon. It
 * forks the newest pilot range-1 snapshot (REBASELINE_SOURCES, or --from-run),
 * moves the fork to the phase, plays ranges 2-4 measured (label baseline,
 * its own folders), and writes baseline-<daemon12>-<addon12>-<phase>.json
 * beside the others. A range that does not pass or watch stops it; no baseline.
 */
async function cmdRebaseline(o) {
  if (o.prepare || o.write) return cmdRebaselineSplit(o);
  if (!o.phase || !o.daemon) return usage();
  const daemon = resolve(o.daemon), addon = resolve(o.addon ?? ADDON);
  const from = o["from-run"] ?? REBASELINE_SOURCES.find((r) => existsSync(join(HISTORY, "runs", r, "run.json"))
    && existsSync(manifestPath(new Run(join(HISTORY, "runs", r)).manifest.outputs.snapshots, 1, r)));
  if (!from) { console.error(`no pilot range-1 snapshot in ${REBASELINE_SOURCES.join(", ")}`); return EXIT.usage; }
  const id = o.run ?? rebaselineId(o);
  await cmdFork({ run: id, "from-run": from, range: 1, label: "baseline", daemon, addon, sdk: o.sdk });
  const run = new Run(join(HISTORY, "runs", id));
  if (run.manifest.phase !== o.phase && cmdPhase({ run: id, phase: o.phase }) !== EXIT.done) return EXIT.usage;
  const code = await cmdPlay({ run: id, from: 2, to: 4, mode: "measured" });
  const played = new Run(join(HISTORY, "runs", id)).state.next;
  if (code !== EXIT.done || played !== 5) { console.error(`rebaseline ${id}: stopped at range ${played} (exit ${code}); no baseline written`); return code === EXIT.done ? EXIT.stop : code; }
  const { writeBaseline } = await import("./report.mjs");
  const r = writeBaseline({ metricsDir: run.manifest.outputs.metrics, ranges: [2, 3, 4], out: join(HISTORY, "metrics"), run: id, phase: o.phase });
  run.note({ kind: "baseline", name: r.file, phase: o.phase, from: { run: from, range: 1 } });
  console.log(JSON.stringify({ run: id, from, phase: o.phase, file: r.file, ops: Object.keys(r.baseline.ops).length }));
  return EXIT.done;
}

/**
 * The split re-baseline (liaison under owner delegation 2026-10-19, for P3 with `.git`): `--prepare` forks the
 * pilot's range-1 snapshot (label baseline), moves it to the phase and turns git on from range 2 (`--git`); the
 * ranges 2-4 are then played one by one with `play` (each in commands under 120 s); `--write` checks the run
 * stands at range 5, clean, and writes the baseline. A range that stops leaves the run dirty and no baseline.
 */
/**
 * The measured ranges of a split re-baseline: `--ranges a-b` (owner 2026-10-20, ranges 51-100: recent ranges on a
 * fork of `--range a-1`'s snapshot), else the pilot's 2-4 from range 1. Three consecutive ranges after the fork point.
 */
export function baselineRanges(o) {
  if (o.ranges == null) return { from: 1, ranges: [2, 3, 4] };
  const m = /^(\d+)-(\d+)$/.exec(String(o.ranges));
  if (!m || Number(m[2]) - Number(m[1]) !== 2) throw new Error(`--ranges ${o.ranges}: three consecutive ranges a-b`);
  const a = Number(m[1]), from = o.range != null ? Number(o.range) : a - 1;
  if (from !== a - 1) throw new Error(`--ranges ${o.ranges} starts after the fork range ${from}: it must start at ${from + 1}`);
  return { from, ranges: [a, a + 1, a + 2] };
}

async function cmdRebaselineSplit(o) {
  if (!o.phase || !o.daemon) return usage();
  const id = o.run ?? rebaselineId(o);
  const { from: at, ranges } = baselineRanges(o);
  if (o.prepare) {
    const daemon = resolve(o.daemon), addon = resolve(o.addon ?? ADDON);
    const from = o["from-run"] ?? REBASELINE_SOURCES.find((r) => existsSync(join(HISTORY, "runs", r, "run.json"))
      && existsSync(manifestPath(new Run(join(HISTORY, "runs", r)).manifest.outputs.snapshots, 1, r)));
    if (!from) { console.error(`no pilot range-1 snapshot in ${REBASELINE_SOURCES.join(", ")}`); return EXIT.usage; }
    await cmdFork({ run: id, "from-run": from, range: at, label: "baseline", daemon, addon, sdk: o.sdk, ...(o.plan ? { plan: o.plan } : {}), ...(o.oracle ? { oracle: o.oracle } : {}),
      ...(o["pnpm-store"] ? { "pnpm-store": o["pnpm-store"] } : {}), ...(o["native-states"] ? { "native-states": o["native-states"] } : {}) });
    const run = new Run(join(HISTORY, "runs", id));
    // one phase at a time (p1 → p2 → p3), each move recorded at range 2
    const order = Object.keys(PHASES).sort((a, b) => PHASES[a].order - PHASES[b].order);
    for (const ph of order.slice(order.indexOf(run.manifest.phase) + 1, order.indexOf(o.phase) + 1)) if (cmdPhase({ run: id, phase: ph }) !== EXIT.done) return EXIT.usage;
    if (o.git && !run.manifest.git?.on && cmdGit({ run: id, on: true }) !== EXIT.done) return EXIT.usage;
    console.log(JSON.stringify({ run: id, from, range: at, phase: o.phase, git: !!o.git, next: `play ranges ${ranges[0]}-${ranges[2]}, then rebaseline --write` }));
    return EXIT.done;
  }
  const run = new Run(join(HISTORY, "runs", id));
  if (run.manifest.label !== "baseline" || run.manifest.phase !== o.phase) { console.error(`rebaseline ${id}: not a ${o.phase} baseline run`); return EXIT.usage; }
  if (run.state.dirty != null || run.state.next !== ranges[2] + 1) { console.error(`rebaseline ${id}: stands at range ${run.state.next}${run.state.dirty != null ? `, dirty at ${run.state.dirty}` : ""}; no baseline written`); return EXIT.stop; }
  // as the one-command form: a range whose latest attempt does not pass or watch gives no baseline
  const { writeBaseline, loadAttempts } = await import("./report.mjs");
  const latest = loadAttempts(run.manifest.outputs.metrics);
  const ranges_ = String(o["accept-ranges"] ?? "").split(",").filter(Boolean).map(Number);
  const accept = o["accept-storage-row"] ? { row: o["accept-storage-row"], ranges: ranges_, reason: o.reason }
    : o["accept-counter"] ? { row: "Counters", counter: o["accept-counter"], ranges: ranges_, reason: o.reason } : null;
  const judged = baselineRows(ranges.map((k) => [k, latest.get(k)?.at(-1)]), accept);
  if (judged.refused.length) { console.error(`rebaseline ${id}: ${judged.refused.join("; ")}; no baseline written`); return EXIT.stop; }
  const note = judged.accepted.length ? { ...(o.note ? { text: o.note } : {}), acceptedRows: judged.accepted, reason: accept.reason } : o.note;
  const r = writeBaseline({ metricsDir: run.manifest.outputs.metrics, ranges, out: join(HISTORY, "metrics"), run: id, phase: o.phase, ...(note ? { note } : {}) });
  run.note({ kind: "baseline", name: r.file, phase: o.phase, from: run.manifest.source });
  console.log(JSON.stringify({ run: id, phase: o.phase, file: r.file, ops: Object.keys(r.baseline.ops).length }));
  return EXIT.done;
}

/**
 * The storage rows a baseline may take at optimize as a named exception (`--accept-storage-row`). A Counters row is
 * accepted only for one named counter (`--accept-counter <probe.counter>`, or a per-unit one such as
 * "glob_tree.statements per tree file", fix 074, liaison 2026-10-20, rb-p3-32eda22d-…-b
 * r049: `oneshot_mount_unmount.statements`), never Counters in general; the counter stays judged in later ranges.
 */
export const ACCEPTABLE_STORAGE_ROWS = new Set(["Reinstall growth"]);
const acceptsRow = (accept, c) => c.name === accept.row && (accept.row !== "Counters" || String(c.value).startsWith(`${accept.counter}: `));

/**
 * Which baseline ranges may make a baseline. Each latest attempt must pass or watch. The one exception is a named
 * storage row (`accept`: { row, ranges, reason }) at optimize in the listed ranges, with every other row at pass or
 * watch (liaison under owner delegation 2026-10-19: rb-p3-…-d r003 and r004, Reinstall growth on link-unit
 * denominators). A stop, or any other row, still refuses.
 */
export function baselineRows(attempts, accept = null) {
  const refused = [], accepted = [];
  const named = accept && (ACCEPTABLE_STORAGE_ROWS.has(accept.row) || (accept.row === "Counters" && /^[a-z_]+\.[a-z_]+( per [a-z ]+)?$/.test(accept.counter ?? "")));
  if (accept && (!named || !accept.ranges.length || !accept.reason)) return { refused: [`--accept-storage-row needs one of ${[...ACCEPTABLE_STORAGE_ROWS].join(", ")} (or --accept-counter <probe.counter>), --accept-ranges and --reason`], accepted };
  for (const [k, m] of attempts) {
    const v = m?.gate?.verdict ?? "none";
    if (v === "pass" || v === "watch") continue;
    const off = (m?.gate?.checks ?? []).filter((c) => c.result !== "pass" && c.result !== "watch");
    const ok = accept && v === "optimize" && accept.ranges.includes(k) && off.length === 1 && acceptsRow(accept, off[0]) && off[0].result === "optimize";
    if (ok) accepted.push({ range: k, attempt: m.attempt, row: off[0].name, ...(accept.counter ? { counter: accept.counter } : {}), result: off[0].result, value: off[0].value, reinstall: m.storage?.reinstall ?? null });
    else refused.push(`range ${k} ${v}${off.length ? ` (${off.map((c) => `${c.name} ${c.result}`).join(", ")})` : ""}`);
  }
  return { refused, accepted };
}

/** The run id `rebaseline` makes when none is given (the runner mounts its volume). */
export const rebaselineId = (o) => `rb-${o.phase}-${sha256(resolve(o.daemon)).slice(0, 8)}-${sha256(resolve(o.addon ?? ADDON)).slice(0, 8)}`;

/** fork's --plan/--oracle: a slice (slice.mjs) for dev runs only; a full plan for any label, the oracle defaulting to the shared one. */
export function forkPlan(o) {
  const plan = resolve(o.plan ?? join(HISTORY, "plan")), summary = JSON.parse(readFileSync(join(plan, "plan.json"), "utf8"));
  if (summary.slice && o.label && o.label !== "dev") throw new Error(`${plan} is a dev slice; --plan with a slice is for dev runs`);
  if (summary.version !== PLAN_VERSION) throw new Error(`${plan} is plan v${summary.version}; this player plays v${PLAN_VERSION}`);
  return { plan, oracle: resolve(o.oracle ?? join(HISTORY, "oracle")) };
}

/**
 * The runner state a P3 range needs from the ranges before it (the git seed, the installed chain, /.lww, the
 * storage parts). Snapshots before r016.a2 carried none of it, so a fork of a P3 snapshot replayed as a fresh
 * git and Node start. `parts`/`bySource` are a range's after its snapshot, so a snapshot's copy is the range before.
 */
export const P3_STATE_KEYS = ["gitSeeded", "installed", "closureChain", "lwwSha", "nmGroupsFile", "parts", "bySource"];
export const p3StateOf = (s) => Object.fromEntries(P3_STATE_KEYS.filter((key) => s?.[key] != null).map((key) => [key, s[key]]));
/**
 * Where a fork of range k's snapshot takes that state from: the source run's own state while it never advanced past
 * range k (it stands at k + 1, dirty or not, nothing of k + 1 saved), else the snapshot's. Null when the source has
 * git or Node on and neither holds it: the fork is refused rather than replayed as a different workload.
 */
export function forkP3State(source, snapState, k) {
  const on = !!(source.manifest.git?.on || source.manifest.node?.on);
  if (!on) return { from: "none", state: {} };
  // a stopped k + 1 that got past its closure has moved the chain on: then the source state is not range k's
  const movedOn = (s) => (s.closureChain ?? []).some((c) => c.range > k) || Number(/groups-(\d+)\.json$/.exec(s.nmGroupsFile ?? "")?.[1] ?? -1) > k;
  if (source.state?.next === k + 1 && source.state.halfway == null && !movedOn(source.state)) return { from: "source run state (never advanced past the snapshot)", state: p3StateOf(source.state) };
  if (P3_STATE_KEYS.slice(0, 5).some((key) => snapState?.[key] != null)) return { from: "snapshot", state: p3StateOf(snapState) };
  return null;
}

/**
 * Range k's storage parts and per-source totals as its metrics recorded them (storageReport): what the run's state
 * held after range k, which a snapshot's copy (taken before the range's figures) does not.
 */
export function partsFromMetrics(m) {
  const r = m?.storageReport;
  if (!r?.parts || !r.sources) return null;
  return { parts: r.parts, bySource: Object.fromEntries(Object.entries(r.sources).filter(([, v]) => v?.content != null).map(([s, v]) => [s, { content: v.content, metadata: v.metadata }])) };
}

/** A new run from run `from`'s snapshot of range N (SPEC §7, Forking): its file rebuilt into a new volume and home. */
async function cmdFork(o) {
  const source = new Run(join(HISTORY, "runs", o["from-run"]));
  const k = Number(o.range);
  const manifest = JSON.parse(readFileSync(manifestPath(source.manifest.outputs.snapshots, k, source.manifest.run), "utf8"));
  if (!manifest.state) throw new Error(`snapshot ${k} carries no runner state`);
  const p3 = forkP3State(source, manifest.state, k);
  if (!p3) throw new Error(`snapshot ${k} of ${source.manifest.run} carries no git/Node state and the run has advanced past it; the fork would replay a fresh git and Node start`);
  if (p3.from === "snapshot") {
    // the snapshot's parts are the range before's: range k's come from its latest metrics of this run
    const dir = source.manifest.outputs.metrics, own = readdirSync(dir).filter((f) => new RegExp(`^range-${pad(k)}\\.a\\d+\\.json$`).test(f))
      .map((f) => JSON.parse(readFileSync(join(dir, f), "utf8"))).filter((x) => x.run === source.manifest.run).sort((a, b) => a.attempt - b.attempt);
    const got = partsFromMetrics(own.at(-1));
    if (!got) throw new Error(`range ${k} of ${source.manifest.run}: no metrics with storage parts; the fork's storage figures would start from range ${k - 1}`);
    Object.assign(p3.state, got); p3.from = `snapshot; parts from range-${pad(k)}.a${own.at(-1).attempt} metrics`;
  }
  const { dir, volume, env, manifest: runManifest } = create({ id: o.run, phase: source.manifest.phase, label: o.label ?? "dev", policy: source.manifest.policyName, image: source.manifest.env.LAYERFS_IMAGE, daemon: resolve(o.daemon ?? source.manifest.env.LAYERFS_DAEMON), addon: resolve(o.addon ?? source.manifest.env.LAYERFS_NATIVE ?? ADDON), sdk: resolve(o.sdk ?? source.manifest.env.LAYERFS_SDK_JS ?? SDK_JS), source: { run: source.manifest.run, range: k }, pnpmStore: o["pnpm-store"] ?? source.manifest.env.LAYERFS_PNPM_STORE ?? null, nativeStates: o["native-states"] === "none" ? null : o["native-states"] ?? source.manifest.env.LFS_NATIVE_STATES ?? null,
    // a dev slice (slice.mjs): its own plan and oracle folders; never a measured run
    // a full plan (plan.mjs, e.g. plan-r1) for any label; a dev slice's plan and oracle for dev runs only
    ...(o.plan || o.oracle ? forkPlan(o) : {}) });
  runManifest.binary = binaries(env);
  runManifest.planVersion = source.manifest.planVersion;
  // git and Node stay as the source run played them (F-031, NODE_RULE), with their original atRange
  for (const key of ["git", "node"]) if (source.manifest[key]) runManifest[key] = source.manifest[key];
  mkdirSync(dir, { recursive: true });
  writeJson(join(dir, "run.json"), runManifest);
  const run = new Run(dir);
  run.note({ kind: "folder", name: dir });
  const restored = join(dir, "restore", "global", "store.sqlite");
  rebuild(manifest, join(source.manifest.outputs.snapshots, "blocks"), restored);
  docker(["volume", "create", volume]);
  run.note({ kind: "volume", name: volume });
  docker(["run", "--rm", "--network", "none", "--user", "0", "-v", `${volume}:/v`, "-v", `${join(dir, "restore")}:/src:ro`, "--entrypoint", "sh", env.LAYERFS_IMAGE, "-c",
    "mkdir -p /v/global && cp /src/global/store.sqlite /v/global/store.sqlite && chown -R 0:0 /v && chmod 755 /v && chmod 700 /v/global && chmod 600 /v/global/store.sqlite"]);
  // the project record: copied from the source run (same catalog binding); it says the Store is installed
  const record = join(source.manifest.env.LAYERFS_HOME, source.manifest.project, "project.record");
  mkdirSync(join(env.LAYERFS_HOME, runManifest.project), { recursive: true, mode: 0o700 });
  execFileSync("chmod", ["700", env.LAYERFS_HOME]);
  execFileSync("cp", ["-p", record, join(env.LAYERFS_HOME, runManifest.project, "project.record")]);
  run.state = { ...manifest.state, ...p3.state, heads: {}, layers: {}, dirty: null, sinceMs: [], lastSnapshotMs: null, growth: [], storeBytes: manifest.size, probeFixture: true, forkedFrom: { run: source.manifest.run, range: k, sha256: manifest.sha256, p3StateFrom: p3.from } };
  // the fork's own native-state volume (--native-states): the chain's snapshot tars are copied there, one cp each
  // `--native-states none` (51-100 re-baseline): no volume and no copy, so the fork never reads another run's states;
  // its native proofs cannot run (NOT_RUN), and its play needs none
  const own = env.LFS_NATIVE_STATES;
  if (o["native-states"] === "none") run.note({ kind: "native-states", name: "none: proofs NOT_RUN" });
  if (own) for (const e of run.state.closureChain ?? []) {
    const from = e.state?.volume ?? (e.state ? NATIVE_STATES : null);
    if (!from || from === own) continue;
    docker(["volume", "create", own]);
    docker(["run", "--rm", "--network", "none", "--user", "0", "-v", `${from}:/a:ro`, "-v", `${own}:/b`, "--entrypoint", "cp", env.LAYERFS_IMAGE, `/a/${e.state.file}`, `/b/${e.state.file}`]);
    run.note({ kind: "native-state copy", name: `${from}/${e.state.file} -> ${own}` });
    e.state = { ...e.state, volume: own };
  }
  run.save();
  // inspect.mjs reads the fork through this: its project, SDK, environment and rebuilt file
  writeJson(join(dir, "store.json"), { project: runManifest.project, sdk: join(env.LAYERFS_SDK_JS, "src/index.js"), env, file: restored, range: k, fork: o.run });
  console.log(JSON.stringify({ run: o.run, dir, volume, from: run.state.forkedFrom, next: run.state.next, store: join(dir, "store.json") }, null, 1));
}

/** The development checks of a played dev range, on a fork of its published main (devcheck.mjs). */
async function cmdDevcheck(o) {
  const run = new Run(join(HISTORY, "runs", o.run)), k = Number(o.range);
  if (!Number.isInteger(k)) return usage();
  try {
    console.log(JSON.stringify(await devcheck(run, k)));
    return EXIT.done;
  } catch (error) {
    console.error(error instanceof Mismatch ? `devcheck r${pad(k)}: ${error.message}` : (error.stack ?? error));
    return error instanceof Mismatch ? EXIT.stop : EXIT.error;
  } finally {
    const problems = await teardown(run);
    if (problems.length) console.error(`teardown: ${problems.join("; ")}`);
    run.close();
  }
}

/** Removes a run's resources by the literal names its ledger recorded. */
async function cmdCleanup(o) {
  const dir = join(HISTORY, "runs", o.run);
  const ledger = readFileSync(join(dir, "ledger.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
  const run = new Run(dir);
  await run.client();
  for (const id of existsSync(join(run.manifest.env.LAYERFS_HOME, "_sandboxes")) ? readdirSync(join(run.manifest.env.LAYERFS_HOME, "_sandboxes")) : []) {
    run.lf.sandboxes.add(id);
  }
  const problems = await teardown(run);
  for (const e of ledger.filter((x) => x.kind === "container" && !x.removed)) {
    if (docker(["ps", "-a", "--filter", `name=^${e.name}$`, "--format", "{{.Names}}"]) === e.name) { docker(["rm", "-f", e.name]); console.log(`removed container ${e.name}`); }
  }
  for (const e of ledger.filter((x) => x.kind === "volume" && !x.removed)) {
    try { docker(["volume", "rm", e.name]); console.log(`removed volume ${e.name}`); } catch (err) { problems.push(`volume ${e.name}: ${err.message.split("\n")[0]}`); }
  }
  run.close();
  const folder = ledger.find((x) => x.kind === "folder" && x.name === dir);
  if (folder && !problems.length) { rmSync(folder.name, { recursive: true, force: true }); console.log(`removed folder ${folder.name}`); }
  if (problems.length) { console.error(problems.join("\n")); return EXIT.error; }
  return EXIT.done;
}

function usage() {
  console.error("usage: run.mjs new|play|fork|cleanup|phase|devcheck … (see the file's header)");
  return EXIT.usage;
}

export function options(argv) {
  const o = { _: [] };
  // a flag with no value (--resume, --on) is true; it never swallows the next flag
  for (let i = 0; i < argv.length; i++) if (argv[i].startsWith("--")) o[argv[i].slice(2)] = argv[i + 1] == null || argv[i + 1].startsWith("--") ? true : argv[++i]; else o._.push(argv[i]);
  return o;
}

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const o = options(rest);
  if (!o.run && cmd !== "rebaseline") process.exit(usage());
  const outside = checkRunner(cmd, process.env);
  if (outside) { console.error(outside); process.exit(EXIT.guard); }
  const code = cmd === "new" ? (await cmdNew(o), EXIT.done) : cmd === "play" ? await cmdPlay(o) : cmd === "phase" ? cmdPhase(o) : cmd === "fork" ? (await cmdFork(o), EXIT.done) : cmd === "cleanup" ? await cmdCleanup(o) : cmd === "devcheck" ? await cmdDevcheck(o) : cmd === "git" ? cmdGit(o) : cmd === "node" ? cmdNode(o) : cmd === "snapshots" ? cmdSnapshots(o) : cmd === "rebaseline" ? await cmdRebaseline(o) : usage();
  process.exit(code);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  // step 6 (ranges 21–30): the harness the container sees must be the host's (Docker Desktop's share can be stale)
  const { harnessHash } = await import("./quiet.mjs");
  if (process.env.LFS352_HARNESS_SHA && process.env.LFS352_HARNESS_SHA !== harnessHash()) { console.error(`refused: the container sees another harness (${harnessHash().slice(0, 12)}) than the host (${process.env.LFS352_HARNESS_SHA.slice(0, 12)}); Docker's file share is stale, wait and run again`); process.exit(EXIT.guard); }
  main().catch((error) => { console.error(error.stack ?? error); process.exit(EXIT.error); });
}
