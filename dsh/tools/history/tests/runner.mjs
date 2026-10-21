// Tests of the headless runner's pure parts (#352): routing, the Sandbox
// step's commands, the checkpoint comparisons, trace counters and the disk
// guard, on synthetic data only. Nothing here touches Docker or LayerFS.
//   node dsh/tools/history/tests/runner.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  CHUNK, compareIds, comparePaths, diskGuard, EXIT, idBatches, parseTreePage, phaseOps, route,
  placeEntries, sameAsTree, sandboxCommands, sandboxExpect, sqlCounters, callOf, traceLines, Tree, TREE_IDS, viaSandbox,
  addDelta, deltaSummary, deltaWork,
} from "../steps.mjs";
import { blobId as blobOf, gitIgnored } from "../git.mjs";
import { safeCut } from "../agents.mjs";
import { baselineRows, caps, forkPlan, nextAttempt, options, outputs, POLICIES, SWITCHABLE } from "../run.mjs";
import { PLAN_VERSION } from "../plan.mjs";
import { deltaLine, stageLine } from "../report.mjs";

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const dir = mkdtempSync(join(tmpdir(), "lfs-history-runner-"));
const file = (blob = "a".repeat(40), mode = "100644", size = 10) => ({ mode, blob, size });

test("Tree: parents to make, the folder a removal takes, the largest folder", () => {
  const t = new Tree(new Map([["a/b/c.txt", file()], ["a/d.txt", file()], ["e.txt", file()]]));
  assert.equal(t.missingParent("a/b/new.txt"), null);
  assert.equal(t.missingParent("x/y/z.txt"), "x/y");
  assert.equal(t.missingParent("top.txt"), null);
  assert.equal(t.removalTarget("a/b/c.txt"), "a/b");
  assert.equal(t.removalTarget("a/d.txt"), "a/d.txt");
  assert.deepEqual(t.largestDir(), { dir: "", entries: 2 });
  t.delete("a/b/c.txt");
  assert.equal(t.isDir("a/b"), false);
  assert.equal(t.removalTarget("a/d.txt"), "a");
});

test("viaSandbox: modes and mode changes; size never routes (F-001)", () => {
  assert.equal(viaSandbox({ op: "write", mode: "100644", size: 60_000 }), false);
  assert.equal(viaSandbox({ op: "write", mode: "100644", size: 5 << 20 }), false);
  assert.equal(viaSandbox({ op: "write", mode: "100755", size: 1 }), true);
  assert.equal(viaSandbox({ op: "write", mode: "120000", size: 1 }), true);
  assert.equal(viaSandbox({ op: "write", mode: "100644", size: 1, modeChange: true }), true);
  assert.equal(viaSandbox({ op: "rm", mode: "100755" }), false);
});

test("route: write, apply with parents, removal of emptied folders, Sandbox files", () => {
  const t = new Tree(new Map([["a/b/c.txt", file()], ["a/d.txt", file()]]));
  const { calls, sandbox } = route([
    { op: "write", path: "a/b/c.txt", mode: "100644", blob: "b".repeat(40), size: 5 },
    { op: "write", path: "n/m.txt", mode: "100644", blob: "c".repeat(40), size: 5 },
    { op: "write", path: "bin/run", mode: "100755", blob: "d".repeat(40), size: 5 },
    { op: "rm", path: "a/b/c.txt" },
    { op: "rm", path: "gone.txt" },
  ], t);
  assert.deepEqual(calls.map((c) => [c.call, c.path, c.call === "rm" ? c.target : c.parent]), [["write", "a/b/c.txt", null], ["apply", "n/m.txt", "n"], ["rm", "a/b/c.txt", "a/b"]]);
  assert.equal(sandbox.length, 1);
  assert.equal(sandbox[0].previous, null);
  assert.ok(t.has("bin/run") && !t.has("a/b/c.txt") && t.has("n/m.txt"));
  assert.equal(sandboxExpect(sandbox), "Committed");
  assert.equal(sandboxExpect([{ expect: "UpToDate" }]), "UpToDate");
});

test("phaseOps: P1 plays fs/apply/stale-apply files and leaves out the conflicts' own steps", () => {
  const w = { op: "write", path: "x", mode: "100644", blob: "a".repeat(40) };
  const plan = {
    steps: [
      { id: "s1", kind: "fs", files: [w] },
      { id: "s2", kind: "apply", files: [w, { op: "read", path: "y" }] },
      { id: "s3", kind: "stale-apply", files: [w] },
      { id: "s4", kind: "hold", files: [w] },
      { id: "s5", kind: "check" },
      { id: "s6", kind: "decoy", files: [w] },
      { id: "s7", kind: "fs", files: [] },
    ],
    consolidation: [{ op: "reconcile", files: [w] }, { op: "publish" }],
  };
  const { ops, reconcile, left } = phaseOps(plan, "p1");
  assert.deepEqual(ops.map((o) => o.id), ["s1", "s2", "s3"]);
  assert.equal(ops[1].files.length, 1);
  assert.deepEqual(left, { hold: 1, check: 1, decoy: 1, fs: 1 });
  assert.equal(reconcile[0].expect, "Committed");
  assert.throws(() => phaseOps(plan, "p4"), /no player/);
});

test("sandboxCommands: chunks stay under one request and the script restores bytes and modes", () => {
  const big = Buffer.alloc(3 * CHUNK, 7);
  const cmds = sandboxCommands([
    { path: "d/big.bin", mode: "100644", bytes: big },
    { path: "run.sh", mode: "100755", bytes: Buffer.from(`#!/bin/sh\necho "it's"\n`) },
    { path: "empty", mode: "100644", bytes: Buffer.alloc(0) },
    { path: "d/link", mode: "120000", bytes: Buffer.from("big.bin") },
  ], join(dir, "scratch"));
  for (const c of cmds) assert.ok(Buffer.byteLength(c) <= 60_000);
  assert.ok(cmds.length > 3);
  const ws = join(dir, "ws");
  mkdirSync(ws);
  for (const c of cmds) execFileSync("sh", ["-c", c], { cwd: ws });
  assert.equal(execFileSync("wc", ["-c", "d/big.bin"], { cwd: ws, encoding: "utf8" }).trim().split(/\s+/)[0], String(big.length));
  assert.equal(execFileSync("sh", ["-c", "./run.sh"], { cwd: ws, encoding: "utf8" }), "it's\n");
  assert.equal(execFileSync("readlink", ["d/link"], { cwd: ws, encoding: "utf8" }).trim(), "big.bin");
  assert.equal(execFileSync("wc", ["-c", "empty"], { cwd: ws, encoding: "utf8" }).trim().split(/\s+/)[0], "0");
});

test("F-028: an apply leaves a regular file equal to the lane's tree untouched, mtime included", () => {
  const blob = (t) => blobOf(Buffer.from(t));
  const tree = new Tree(new Map([["d/same.txt", file(blob("same\n"))], ["d/changed.txt", file(blob("old\n"))], ["x.sh", file(blob("run\n"))]]));
  const files = [
    { path: "d/same.txt", op: "write", mode: "100644", blob: blob("same\n"), size: 5, expect: "UpToDate" },
    { path: "d/changed.txt", op: "write", mode: "100644", blob: blob("new\n"), size: 4 },
    { path: "x.sh", op: "write", mode: "100755", blob: blob("run\n"), size: 4 },
  ];
  const { sandbox } = route(files, tree, { all: true });
  assert.deepEqual(sandbox.map(sameAsTree), [true, false, false], "a mode change is not the same file");
  assert.equal(sandboxExpect(sandbox), "Committed", "a mixed step still commits; sandboxExpect is unchanged");
  assert.equal(sandboxExpect(sandbox.slice(0, 1)), "UpToDate");
  const ws = join(dir, "f028");
  mkdirSync(join(ws, "d"), { recursive: true });
  const old = new Date("2000-01-01T00:00:00Z");
  for (const [p, t] of [["d/same.txt", "same\n"], ["d/changed.txt", "old\n"], ["x.sh", "run\n"]]) { writeFileSync(join(ws, p), t); utimesSync(join(ws, p), old, old); }
  const entries = placeEntries(sandbox, sandbox.map((f) => (sameAsTree(f) ? null : Buffer.from(f.path === "x.sh" ? "run\n" : "new\n"))));
  assert.deepEqual(entries[0], { path: "d/same.txt", mode: "100644", same: true }, "no bytes are sent for it");
  const cmds = sandboxCommands(entries, join(dir, "f028-scratch"));
  assert.ok(!cmds.join("\n").includes("same.txt"), "the script never names the identical file");
  for (const c of cmds) execFileSync("sh", ["-c", c], { cwd: ws });
  assert.equal(statSync(join(ws, "d/same.txt")).mtimeMs, old.getTime(), "the identical file keeps its mtime");
  assert.equal(readFileSync(join(ws, "d/changed.txt"), "utf8"), "new\n");
  assert.equal(statSync(join(ws, "x.sh")).mode & 0o111, 0o111);
  // the pre-F-028 script: the same file sent without `same` is rewritten, and its mtime moves (what made r012.s0021 Commit)
  for (const c of sandboxCommands([{ path: "d/same.txt", mode: "100644", bytes: Buffer.from("same\n") }], join(dir, "f028-scratch"))) execFileSync("sh", ["-c", c], { cwd: ws });
  assert.notEqual(statSync(join(ws, "d/same.txt")).mtimeMs, old.getTime());
});

test("probe samples (owner 2026-10-18): the median of five, the first sample alone gives the counters", async () => {
  const { median, PROBE_SAMPLES, readTrace } = await import("../lib.mjs");
  assert.equal(PROBE_SAMPLES, 5);
  assert.deepEqual([median([0.77, 0.4, 0.5, 9, 0.45]), median([1, 2, 3, 4]), median([])], [0.5, 2.5, null]);
  const sql = (n) => [{ sql: { writer: { statements: n, vm_steps: n }, readers: {} } }];
  const f = join(dir, "samples.jsonl");
  writeFileSync(f, [["probe:fork#1", 16], ["probe-s1:fork#2", 16], ["probe-s2:fork#3", 16], ["probe-setup:fork#4", 99]]
    .map(([step, n]) => JSON.stringify({ step, method: "branch.fork", phase: "end", ms: 1, daemon: sql(n) })).join("\n"));
  const t = readTrace(f);
  assert.equal(t.probe.fork.statements, 16, "counters from the first sample only");
  assert.equal(t.calls.length, 0, "samples are probe calls, not the replay's");
});

test("idBatches: paths split by bytes, none empty", () => {
  const b = idBatches(["aaaa", "bbbb", "cccc"], 16);
  assert.deepEqual(b, [["aaaa", "bbbb"], ["cccc"]]);
  assert.deepEqual(idBatches([], 16), []);
});

test("TREE_IDS and parseTreePage: git blob ids, modes, skipped prefixes and node_modules", () => {
  const ws = join(dir, "tree");
  mkdirSync(join(ws, "src"), { recursive: true });
  mkdirSync(join(ws, "node_modules/x"), { recursive: true });
  mkdirSync(join(ws, ".lfs-probe"), { recursive: true });
  writeFileSync(join(ws, "src/a.txt"), "hello\n");
  writeFileSync(join(ws, "node_modules/x/i.js"), "x");
  writeFileSync(join(ws, ".lfs-probe/p"), "p");
  const out = execFileSync("node", ["-e", TREE_IDS, "0", "100", ".lfs-probe"], { cwd: ws, encoding: "utf8" });
  const { files, total } = parseTreePage(out);
  assert.equal(total, 1);
  assert.deepEqual(files.get("src/a.txt"), { mode: "100644", blob: "ce013625030ba8dba906f756967f9e9ca394464a" });
  assert.throws(() => parseTreePage("100644 xx /a\n"), /did not finish/);
});

test("comparePaths: missing, extra, folders, ignored prefixes and metadata-only changes", () => {
  const items = [
    { path: "/a.txt", kind: "Modified", content: true },
    { path: "/dir", type: "dir", kind: "Added" },
    { path: "/.lfs-probe/x", kind: "Added", content: true },
    { path: "/t.txt", kind: "Modified", content: false, metadata: true },
    { path: "/odd.txt", kind: "Added", content: true },
  ];
  const r = comparePaths(items, [{ path: "a.txt" }, { path: "b.txt" }, { path: "sub", gitlink: true }], [".lfs-probe"]);
  assert.deepEqual([r.ok, r.missing, r.extra, r.metadataOnly], [false, ["b.txt"], ["odd.txt"], ["t.txt"]]);
  assert.equal(comparePaths(items.slice(0, 4), [{ path: "a.txt" }], [".lfs-probe"]).ok, true);
});

test("compareIds: missing, content and mode", () => {
  const e = new Map([["a", file("1".repeat(40))], ["b", file("2".repeat(40))], ["c", file("3".repeat(40))], ["d", file("4".repeat(40))]]);
  const a = new Map([["a", file("1".repeat(40))], ["b", file("9".repeat(40))], ["c", file("3".repeat(40), "100755")]]);
  const r = compareIds(["a", "b", "c", "d"], a, e);
  assert.deepEqual([r.ok, r.missing, r.content, r.mode, r.checked], [false, ["d"], ["b"], ["c"], 4]);
});

test("trace parsing: SQL counters summed over writer and readers, call sizes and phases", () => {
  const line = {
    method: "fs.write", ms: 3, ok: true, args: { contentBytes: 100 },
    daemon: [{ sql: { writer: { statements: 2, vm_steps: 10, returned_rows: 1 }, readers: { statements: 1, fullscan_steps: 4 } }, timing: [{ name: "commit", ms: 2, children: [{ name: "save", ms: 1 }] }] }],
  };
  assert.deepEqual(sqlCounters(line), { statements: 3, vm_steps: 10, fullscan_steps: 4, sorts: 0, returned_rows: 1 });
  assert.deepEqual(callOf(line), { method: "fs.write", ms: 3, ok: true, size: { kind: "bytes", n: 100 }, phases: { commit: 2, "commit.save": 1 }, sql: { statements: 3, vm_steps: 10, fullscan_steps: 4 } }, "a trace-only call keeps its SQL work (SPEC §5)");
  assert.equal(traceLines(`${JSON.stringify({ phase: "start" })}\n${JSON.stringify(line)}\n`).length, 1);
});

test("diskGuard: twice the projection on both disks", () => {
  const G = 2 ** 30;
  assert.equal(diskGuard({ storeBytes: G, growthBytes: 0, dockerFree: 100 * G, hostFree: 100 * G, rangesLeft: 3 }).ok, true);
  const low = diskGuard({ storeBytes: G, growthBytes: G, installPeak: G, dockerFree: 9 * G, hostFree: 100 * G, rangesLeft: 1 });
  assert.equal(low.ok, false);
  assert.equal(low.docker, 5 * G);
  assert.equal(diskGuard({ storeBytes: G, growthBytes: G, dockerFree: 100 * G, hostFree: 5 * G, rangesLeft: 1 }).ok, false);
});

test("runner: exit codes, outputs by label, attempts, options and the control policy", () => {
  assert.deepEqual(EXIT, { done: 0, error: 1, usage: 2, optimize: 3, stop: 4, guard: 5 });
  assert.ok(outputs("measured", "/r").docs.endsWith("core/docs/issues/352"));
  assert.deepEqual(outputs("dev", "/r"), { metrics: "/r/metrics", docs: "/r/docs", snapshots: "/r/snapshots" });
  const m = join(dir, "metrics");
  assert.equal(nextAttempt(m, 4), 1);
  mkdirSync(m);
  writeFileSync(join(m, "range-004.a1.json"), "{}");
  writeFileSync(join(m, "range-004.a2.json"), "{}");
  writeFileSync(join(m, "range-005.a7.json"), "{}");
  assert.equal(nextAttempt(m, 4), 3);
  assert.deepEqual(options(["play", "--run", "x", "--from", "0"]), { _: ["play"], run: "x", from: "0" });
  assert.deepEqual(POLICIES.control, { smallFileThreshold: 131072, wholeFileDepth: 8, chunkDepth: 4 });
});

test("delta work: summed over trace lines, shares, cap and budget, the control caps", () => {
  const payload = (o) => ({ prepared_full: 0, trials: 0, prefix_selected: 0, full_losses: 0, no_candidate: 0, absent_candidates: 0, ineligible_candidates: 0, depth_capped: 0, work_exceeded: 0, whole_file_depths: [], chunk_depths: [], ...o });
  const metadata = (o) => ({ leaves: 0, delta_leaves: 0, full_leaves: 0, trials: 0, depth_capped: 0, work_exceeded: 0, depths: [], ...o });
  const lines = [
    { daemon: [{ delta: { payload: payload({ work_exceeded: 1, whole_file_depths: [2, 1], chunk_depths: [1, 0, 0, 0, 0, 0, 0, 0, 1] }), metadata: metadata({ depths: [3, 1] }) } }] },
    { daemon: [{ sql: {} }] },
    { daemon: [{ delta: { payload: payload({ depth_capped: 3, whole_file_depths: [0, 1] }), metadata: metadata({ work_exceeded: 1, depths: [1] }) } }] },
  ];
  const work = deltaWork(lines);
  assert.deepEqual(work.payload.whole_file_depths, [2, 2]);
  assert.deepEqual(work.metadata.depths, [4, 1]);
  assert.equal(deltaWork([{ daemon: [{}] }]), null);
  assert.equal(addDelta(null, work), work);
  const d = deltaSummary(work, caps(null));
  assert.deepEqual([d.objects, d.deltas, d.share, d.atCapObjects, d.refusedByBudget, d.refusedByCap, d.byBudget], [11, 4, 0.3636, 1, 2, 3, 0.4]);
  assert.deepEqual(caps(POLICIES.control), { wholeFile: 8, chunk: 4, metadata: 8 });
  assert.equal(deltaSummary(null, caps(null)), null);
  assert.ok(deltaLine(d).includes("whole-file [0:2 1:2]") && deltaLine(d).includes("caps 16/8/8"));
});

test("stage timing: tooling time per stage, labelled", () => {
  const line = stageLine({ kind: "tooling", totalMs: 15700, prepareMs: 400, playMs: 9000, consolidateMs: 1900, verifyMs: 600, verify: "diff_commits", sealMs: 2900, reportMs: 100 });
  assert.ok(line.startsWith("15.70 s tooling: prepare 0.40 · play 9 · consolidate 1.90 · verify 0.60 (diff_commits) · seal 2.90 · report 0.10"), line);
  assert.equal(stageLine(null), "—");
});

test("P3 switches and fork plans: git and Node for dev, measured and baseline runs; a slice plan for dev runs only", () => {
  assert.deepEqual([...SWITCHABLE].sort(), ["baseline", "dev", "measured"]);
  const full = join(dir, "plan-full"), slice = join(dir, "plan-slice");
  mkdirSync(full); mkdirSync(slice);
  writeFileSync(join(full, "plan.json"), JSON.stringify({ version: PLAN_VERSION }));
  writeFileSync(join(slice, "plan.json"), JSON.stringify({ version: PLAN_VERSION, slice: { range: 15 } }));
  assert.equal(forkPlan({ plan: full, label: "measured" }).plan, full);
  assert.equal(forkPlan({ plan: slice, label: "dev", oracle: dir }).oracle, dir);
  assert.throws(() => forkPlan({ plan: slice, label: "measured" }), /dev slice/);
  writeFileSync(join(full, "plan.json"), JSON.stringify({ version: PLAN_VERSION - 1 }));
  assert.throws(() => forkPlan({ plan: full, label: "baseline" }), /plan v/);
});

test("a baseline takes pass or watch ranges, and one named storage row at optimize only where it is accepted", () => {
  const at = (verdict, rows) => ({ attempt: 1, gate: { verdict, checks: rows.map(([name, result]) => ({ name, result, value: "v" })) } });
  const w = at("watch", [["Speed", "watch"]]), r = at("optimize", [["Speed", "watch"], ["Reinstall growth", "optimize"]]);
  const accept = { row: "Reinstall growth", ranges: [3], reason: "RESULTS 2026-10-19" };
  assert.deepEqual(baselineRows([[2, w], [3, r]]).refused, ["range 3 optimize (Reinstall growth optimize)"]);
  assert.deepEqual(baselineRows([[2, w], [3, r]], accept), { refused: [], accepted: [{ range: 3, attempt: 1, row: "Reinstall growth", result: "optimize", value: "v", reinstall: null }] });
  assert.equal(baselineRows([[4, r]], accept).refused.length, 1, "only the listed ranges");
  assert.equal(baselineRows([[3, at("optimize", [["Reinstall growth", "optimize"], ["Speed", "optimize"]])]], accept).refused.length, 1, "no other row");
  assert.equal(baselineRows([[3, at("stop", [["Reinstall growth", "stop"]])]], accept).refused.length, 1, "never a stop");
  assert.equal(baselineRows([[3, r]], { ...accept, row: "Range growth" }).refused.length, 1, "only a listed storage row");
  assert.equal(baselineRows([[3, r]], { ...accept, reason: undefined }).refused.length, 1, "a reason is required");
});

test("a baseline takes one named counter at optimize, never Counters in general (liaison 2026-10-20, r049)", () => {
  const at = (value) => ({ attempt: 1, gate: { verdict: "optimize", checks: [{ name: "Speed", result: "watch", value: "v" }, { name: "Counters", result: "optimize", value }] } });
  const r49 = at("oneshot_mount_unmount.statements: depth exponent 0.68");
  const accept = { row: "Counters", counter: "oneshot_mount_unmount.statements", ranges: [49], reason: "liaison 2026-10-20" };
  assert.deepEqual(baselineRows([[49, r49]], accept), { refused: [], accepted: [{ range: 49, attempt: 1, row: "Counters", counter: "oneshot_mount_unmount.statements", result: "optimize", value: "oneshot_mount_unmount.statements: depth exponent 0.68", reinstall: null }] });
  assert.equal(baselineRows([[49, at("oneshot_mount_unmount.vm_steps: depth exponent 0.4")]], accept).refused.length, 1, "another counter of the same probe is refused");
  assert.equal(baselineRows([[49, at("merge.returned_rows (chain-bounded): max …")]], accept).refused.length, 1, "another probe is refused");
  assert.equal(baselineRows([[48, r49]], accept).refused.length, 1, "only the listed range");
  assert.equal(baselineRows([[49, r49]], { ...accept, counter: undefined }).refused.length, 1, "Counters without a named counter is refused");
  assert.equal(baselineRows([[49, r49]], { row: "Reinstall growth", ranges: [49], reason: "x" }).refused.length, 1, "the storage form does not take a counter row");
});

test("a per-unit counter can be the named one (fix 074, rb-p3-c41a86d2 r057 glob_tree)", () => {
  const at = (value) => ({ attempt: 1, gate: { verdict: "optimize", checks: [{ name: "Counters", result: "optimize", value }] } });
  const r57 = at("glob_tree.statements per tree file: depth exponent 3.52");
  const accept = { row: "Counters", counter: "glob_tree.statements per tree file", ranges: [57], reason: "liaison 2026-10-20" };
  assert.equal(baselineRows([[57, r57]], accept).accepted.length, 1);
  assert.equal(baselineRows([[57, at("glob_tree.vm_steps per tree file: depth exponent 1.2")]], accept).refused.length, 1, "another counter of the probe is refused");
  assert.equal(baselineRows([[57, at("glob_tree.statements: depth exponent 3.52")]], accept).refused.length, 1, "the per-unit name is exact");
  assert.equal(baselineRows([[57, r57]], { ...accept, counter: "glob_tree.statements; rm" }).refused.length, 1, "only letters, the dot and a per-unit tail");
});

test("a lanes cut: any plan order outside a held sequence (commit-conflict, stale-clean-merge)", () => {
  const plan = { steps: [["s1", 1], ["s2", 2], ["s3", 2.5], ["s4", 3], ["s5", 4], ["s6", 5]].map(([id, order]) => ({ id, order })),
    conflicts: [{ kind: "commit-conflict", lane: "L1", steps: ["s2", "s3", "s4"] }, { kind: "stale-clean-merge", lane: "L2", steps: ["s5", "x", "s6"] }, { kind: "lww", lane: "L1", steps: ["s1", "s6"] }] };
  assert.equal(safeCut(plan, 2), null);
  assert.match(safeCut(plan, 2.5), /commit-conflict on L1/);
  assert.match(safeCut(plan, 3), /commit-conflict/);
  assert.equal(safeCut(plan, 3.5), null);
  assert.match(safeCut(plan, 4.5), /stale-clean-merge on L2/);
});

let failed = 0;
test("gitIgnored: the checkpoint's own .gitignore files decide; an ignored test output is no extra (fix 058, r038 a1)", () => {
  const work = join(dir, "ign-work"), bare = join(dir, "ign.git");
  mkdirSync(join(work, "sub"), { recursive: true });
  const g = (...a) => execFileSync("git", ["-C", work, ...a], { encoding: "utf8" });
  g("init", "-q"); writeFileSync(join(work, ".gitignore"), ".sessions/\nexamples/*/.sessions/\n"); writeFileSync(join(work, "sub", ".gitignore"), "*.db\n!keep.db\n");
  writeFileSync(join(work, "a.txt"), "a\n");
  g("add", "-A"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c");
  execFileSync("git", ["clone", "-q", "--bare", work, bare]);
  const head = execFileSync("git", ["--git-dir", bare, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const ign = gitIgnored(bare, head, [".sessions/session-query.db", "examples/acp-agent/.sessions/x", "sub/y.db", "sub/keep.db", "packages/a/src/x.ts"]).sort();
  assert.deepEqual(ign, [".sessions/session-query.db", "examples/acp-agent/.sessions/x", "sub/y.db"]);
  assert.deepEqual(gitIgnored(bare, head, []), []);
  const set = new Set(ign), outputs = { test: (p) => set.has(p) };
  const items = [{ path: "/.sessions/session-query.db", kind: "Added" }, { path: "/packages/a/src/x.ts", kind: "Added" }];
  const r = comparePaths(items, [], [], outputs);
  assert.deepEqual(r.extra, ["packages/a/src/x.ts"], "an ignored output is no extra; an unignored new file still is");
});
for (const [name, fn] of tests) {
  try { await fn(); console.log(`ok   ${name}`); } catch (error) { failed++; console.log(`FAIL ${name}\n${error.stack}`); }
}
rmSync(dir, { recursive: true, force: true });
console.log(`${tests.length - failed}/${tests.length} passed`);
if (failed) process.exit(1);
