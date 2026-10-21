// Tests of the history replay's P1 tools (#352): snapshots, inspection, unit
// test selection and the new gates, on synthetic data only. Nothing here
// touches Docker, LayerFS or a dsh checkout.
//   node dsh/tools/history/tests/tools.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { blockify, due, manifestOf, manifestPath, newManifestPath, orphans, pageSizeOf, rebuild, verify } from "../snapshot.mjs";
import { parseIds, ROLES, storeFigures, trend } from "../inspect.mjs";
import { chooseRun, compareResults, packageOf, parseVitestJson, selectTests, vitestCommand } from "../unit-tests.mjs";
import { batchSize, checkedOut, dockerArgs, FETCH, INSTALL, nextSlice, noInstall, parseProbe } from "../calibrate-tests.mjs";
import { evaluate } from "../gates.mjs";
import { change, checkFinding, checkRebuild, checkRecord, checkRecords, loadFindings } from "../findings.mjs";
import { renderFinding, renderOptimization } from "../report.mjs";
import { renderFindingFormat } from "../format.mjs";
import { findingTableProblems } from "../reportcheck.mjs";

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const dir = mkdtempSync(join(tmpdir(), "lfs-history-tools-"));

/** A file that starts like a SQLite database with `pageSize`, then `blocks` blocks of `size` bytes, block i filled with i. */
function fakeStore(path, { pageSize = 4096, blocks = 4, size = 1024, change = null } = {}) {
  const body = Buffer.alloc(blocks * size);
  for (let i = 0; i < blocks; i++) body.fill(i === change ? 200 + i : i + 1, i * size, (i + 1) * size);
  body.write("SQLite format 3\0", 0, "latin1");
  body.writeUInt16BE(pageSize === 65536 ? 1 : pageSize, 16);
  writeFileSync(path, body);
}

test("blockify writes only new blocks, and a manifest rebuilds the file", () => {
  const snaps = join(dir, "snaps"), blocks = join(snaps, "blocks"), file = join(dir, "store.sqlite");
  fakeStore(file);
  const first = blockify(file, blocks, 1024);
  assert.equal(first.pageSize, 4096);
  assert.deepEqual([first.blocks.length, first.newBlocks, first.newBytes], [4, 4, 4096]);
  fakeStore(file, { change: 2 });
  const second = blockify(file, blocks, 1024);
  assert.deepEqual([second.newBlocks, second.newBytes], [1, 1024], "one changed block, one new block");
  assert.equal(second.blocks[0], first.blocks[0]);
  const m1 = manifestOf(1, "sha256:img", first, { depth: 10 }, 5), m2 = manifestOf(2, "sha256:img", second, { depth: 20 }, 7);
  writeFileSync(manifestPath(snaps, 1), JSON.stringify(m1));
  writeFileSync(manifestPath(snaps, 2), JSON.stringify(m2));
  assert.equal(rebuild(m1, blocks, join(dir, "out", "r1.sqlite")), first.sha256);
  assert.equal(rebuild(m2, blocks, join(dir, "out", "r2.sqlite")), second.sha256);
  assert.deepEqual(verify(m2, blocks), { ok: true, problems: [] });
  assert.deepEqual(orphans(snaps), []);
  writeFileSync(join(blocks, "f".repeat(64)), "stray");
  assert.deepEqual(orphans(snaps), [join(blocks, "f".repeat(64))]);
  writeFileSync(join(blocks, first.blocks[1]), "damaged");
  assert.equal(verify(m1, blocks).ok, false);
  assert.throws(() => rebuild(m1, blocks, join(dir, "out", "bad.sqlite")), /SHA-256/);
});

test("a rerun line's snapshot sits beside the old line's, each found by its run", () => {
  const snaps = join(dir, "lines");
  mkdirSync(snaps, { recursive: true });
  assert.equal(newManifestPath(snaps, 2, "old"), join(snaps, "range-002.json"), "the first line takes the plain name");
  writeFileSync(join(snaps, "range-002.json"), JSON.stringify({ range: 2, blocks: ["a"] }));
  assert.equal(manifestPath(snaps, 2, "old"), join(snaps, "range-002.json"), "a manifest that names no run serves its run");
  assert.equal(newManifestPath(snaps, 2, "new"), join(snaps, "range-002.new.json"), "a rerun of the range does not replace it");
  writeFileSync(join(snaps, "range-002.new.json"), JSON.stringify({ range: 2, run: "new", blocks: ["b"] }));
  assert.equal(manifestPath(snaps, 2, "new"), join(snaps, "range-002.new.json"));
  assert.equal(manifestPath(snaps, 2), join(snaps, "range-002.json"));
  writeFileSync(join(snaps, "range-003.json"), JSON.stringify({ range: 3, run: "new", blocks: ["c"] }));
  assert.equal(manifestPath(snaps, 3, "new"), join(snaps, "range-003.json"));
  assert.throws(() => manifestPath(snaps, 3, "old"), /no snapshot of range 3/);
  mkdirSync(join(snaps, "blocks"), { recursive: true });
  for (const id of ["a", "b", "c", "d"]) writeFileSync(join(snaps, "blocks", id.repeat(64)), id);
  for (const [f, id] of [["range-002.json", "a"], ["range-002.new.json", "b"], ["range-003.json", "c"]]) writeFileSync(join(snaps, f), JSON.stringify({ blocks: [id.repeat(64)] }));
  assert.deepEqual(orphans(snaps), [join(snaps, "blocks", "d".repeat(64))], "every line's manifest keeps its blocks");
});

test("a snapshot keeps the 4 KiB page size and needs a SQLite file", () => {
  const file = join(dir, "big-page.sqlite");
  fakeStore(file, { pageSize: 8192 });
  const made = blockify(file, join(dir, "other-blocks"), 1024);
  assert.equal(made.pageSize, 8192);
  assert.throws(() => manifestOf(1, null, made, {}, 1), /4096/);
  assert.throws(() => pageSizeOf(Buffer.alloc(100)), /not a SQLite/);
  const head = Buffer.alloc(100); head.write("SQLite format 3\0", 0, "latin1"); head.writeUInt16BE(1, 16);
  assert.equal(pageSizeOf(head), 65536);
});

test("a snapshot is due when planned, before a fix, or when fast-forwarding costs more", () => {
  assert.equal(due({ planned: true, verdict: "pass", sinceMs: [], lastCostMs: 9e9 }).due, true);
  assert.equal(due({ planned: false, verdict: "optimize", sinceMs: [1], lastCostMs: 9e9 }).due, true);
  assert.equal(due({ planned: false, verdict: "pass", sinceMs: [1000, 2000], lastCostMs: 5000 }).due, false);
  assert.equal(due({ planned: false, verdict: "watch", sinceMs: [3000, 3000], lastCostMs: 5000 }).due, true);
  assert.equal(due({ planned: false, verdict: "pass", sinceMs: [1], lastCostMs: null }).due, true);
});

test("inspect parses blob ids and reads a fork's figures read-only", () => {
  const ids = parseIds("100644 " + "a".repeat(40) + " /src/x.ts\n120000 " + "b".repeat(40) + " /link\n");
  assert.deepEqual(ids.get("src/x.ts"), { mode: "100644", blob: "a".repeat(40) });
  assert.equal(ids.get("link").mode, "120000");
  assert.throws(() => parseIds("garbage\n"), /unexpected/);
  assert.equal(ROLES.length, 14);
  const db = join(dir, "fork.sqlite");
  execFileSync("sqlite3", [db, [
    "create table store_policy(whole_file_delta_max_depth, chunk_delta_max_depth, metadata_delta_max_depth, small_file_threshold_bytes)",
    "insert into store_policy values(16, 16, 8, 131072)",
    "create table object_location(object_id, role, canonical_length)",
    "insert into object_location values(x'01', 1, 100), (x'02', 1, 5000), (x'03', 7, 300)",
    "create table pack(domain, length)", "insert into pack values(0, 1000), (1, 9000)",
    "create table \"commit\"(id)", "insert into \"commit\" values(1), (2)",
    "create table branch(id)", "insert into branch values(1)", "create table layer(id)",
  ].join(";")]);
  const f = storeFigures(db);
  assert.deepEqual(f.policy, { wholeFileDepth: 16, chunkDepth: 16, metadataDepth: 8, cutoff: 131072 });
  assert.equal(f.commits, 2);
  assert.deepEqual(f.objects.map((o) => [o.role, o.class, o.n]), [["whole file", "≤32 KiB", 1], ["whole file", "≤4 KiB", 1], ["directory leaf", "≤4 KiB", 1]]);
  assert.deepEqual(f.packs, [{ domain: 0, n: 1, bytes: 1000 }, { domain: 1, n: 1, bytes: 9000 }]);
  assert.ok(f.tables === null || f.tables.some((t) => t.name === "object_location"));
});

test("trend lines up manifests with the stats saved for them", () => {
  const snaps = join(dir, "trend");
  mkdirSync(snaps);
  writeFileSync(manifestPath(snaps, 4), JSON.stringify({ range: 4, depth: 900, size: 8 << 20, newBytes: 2 << 20, copyMs: 40, blocks: [] }));
  writeFileSync(manifestPath(snaps, 9), JSON.stringify({ range: 9, depth: 1900, size: 9 << 20, newBytes: 1 << 20, copyMs: 30, blocks: [] }));
  writeFileSync(join(snaps, "stats-009.json"), JSON.stringify({ sdk: { stored: 7, metadata: 2, dedupe: 1.5, compression: 3 }, sql: { freePages: 4 } }));
  const rows = trend(snaps);
  assert.deepEqual(rows.map((r) => [r.range, r.stored, r.freePages]), [[4, null, null], [9, 7, 4]]);
});

/** A checkpoint tree with three packages, and the contents of its files. */
function fixtureTree() {
  const files = {
    "package.json": "{}",
    "packages/core/a/package.json": "{}",
    "packages/core/a/src/a.ts": "export const a = 1",
    "packages/core/a/tests/a.spec.ts": "import { a } from '../src/a'",
    "packages/core/a/tests/browser.spec.ts": "import { chromium } from 'playwright'",
    "packages/core/a/tests/snap.spec.ts": "if (process.env.DSH_SNAPSHOT) {}",
    "packages/core/a/tests/e2e/flow.spec.ts": "test()",
    "packages/core/b/package.json": "{}",
    "packages/core/b/tests/b.test.ts": "const e = require('electron')",
    "packages/core/b/tests/c.test.ts": "test()",
    "packages/ssh/ssh/package.json": "{}",
    "packages/ssh/ssh/tests/s.spec.ts": "test()",
    "apps/desktop/package.json": "{}",
    "apps/desktop/tests/d.spec.ts": "test()",
    "README.md": "x",
  };
  const state = new Map(Object.keys(files).map((p, i) => [p, { mode: "100644", blob: String(i) }]));
  const bodies = new Map([...state].map(([p, e]) => [e.blob, Buffer.from(files[p])]));
  return { state, read: async (blob) => bodies.get(blob) };
}

test("test selection takes changed packages' unit tests and drops env-dependent ones", async () => {
  const { state, read } = fixtureTree();
  assert.equal(packageOf("packages/core/a/tests/a.spec.ts", new Set(["packages/core/a"])), "packages/core/a");
  assert.equal(packageOf("README.md", new Set(["packages/core/a"])), null);
  const r = await selectTests({ state, changed: ["packages/core/a/src/a.ts", "README.md"], milestone: false, read });
  assert.equal(r.tier, "range");
  assert.deepEqual(r.files, ["packages/core/a/tests/a.spec.ts"]);
  assert.deepEqual(r.dropped.path, ["packages/core/a/tests/e2e/flow.spec.ts"]);
  assert.deepEqual(r.dropped.content, ["packages/core/a/tests/browser.spec.ts", "packages/core/a/tests/snap.spec.ts"]);
  const all = await selectTests({ state, changed: [], milestone: true, read });
  assert.deepEqual(all.files, ["packages/core/a/tests/a.spec.ts", "packages/core/b/tests/c.test.ts"]);
  assert.ok(all.dropped.path.includes("apps/desktop/tests/d.spec.ts") && all.dropped.path.includes("packages/ssh/ssh/tests/s.spec.ts"));
  assert.ok(all.dropped.content.includes("packages/core/b/tests/b.test.ts"));
});

test("the run keeps native passes, fastest first, within the cap", () => {
  const native = [
    { path: "a", status: "pass", ms: 50_000 }, { path: "b", status: "pass", ms: 1_000 },
    { path: "c", status: "fail", ms: 10 }, { path: "d", status: "timeout", ms: 10_000 }, { path: "e", status: "pass", ms: 20_000 },
  ];
  const r = chooseRun(native, "range");
  assert.deepEqual(r.run, ["b", "e"]);
  assert.equal(r.nativeMs, 21_000);
  assert.deepEqual(r.skipped.map((s) => [s.path, s.reason]), [["c", "native fail"], ["d", "native timeout"], ["a", "over the cap"]]);
  assert.deepEqual(chooseRun(native, "milestone").run, ["a", "b", "e"]);
  const many = Array.from({ length: 40 }, (_, i) => ({ path: `f${String(i).padStart(2, "0")}`, status: "pass", ms: 10 }));
  assert.equal(chooseRun(many, "range").run.length, 30);
});

test("LayerFS's test results are compared file by file with the native ones", () => {
  assert.equal(vitestCommand(["a b.spec.ts", "it's.spec.ts"]), "CI=1 HOME=/tmp timeout 600 ./node_modules/.bin/vitest run --reporter=json 'a b.spec.ts' 'it'\\''s.spec.ts'");
  const results = parseVitestJson('noise\n{"testResults":[{"name":"/w/x.spec.ts","status":"passed"},{"name":"/w/y.spec.ts","status":"failed"}]}', "/w");
  assert.deepEqual([...results], [["x.spec.ts", "pass"], ["y.spec.ts", "fail"]]);
  assert.deepEqual(compareResults(["x.spec.ts", "y.spec.ts", "z.spec.ts"], results), { run: 3, equal: 1, differ: [
    { path: "y.spec.ts", native: "pass", layerfs: "fail" }, { path: "z.spec.ts", native: "pass", layerfs: "missing" }] });
});

test("calibration probes a large range across bounded commands", () => {
  const files = ["a", "b", "c", "d", "e"];
  assert.deepEqual(nextSlice(files, null, "c1", 0), { kept: [], todo: files, left: 0 }, "no limit: the whole range at once");
  const first = nextSlice(files, null, "c1", 2);
  assert.deepEqual([first.todo, first.left], [["a", "b"], 3]);
  const partial = { checkpoint: "c1", native: [{ path: "a" }, { path: "b" }] };
  const second = nextSlice(files, partial, "c1", 2);
  assert.deepEqual([second.kept.length, second.todo, second.left], [2, ["c", "d"], 1]);
  assert.deepEqual(nextSlice(files, { ...partial, native: [...partial.native, { path: "c" }, { path: "d" }] }, "c1", 2).todo, ["e"]);
  assert.deepEqual(nextSlice(files, partial, "c2", 2).kept, [], "another checkpoint's partial results are not kept");
});

test("fix 065: the calibration batch sizes itself: 15 after a checkout move, then about 60 s from the measured time per file", () => {
  assert.equal(batchSize({ moved: true }), 15, "the first command after the move (LESSONS R4)");
  assert.equal(batchSize({ moved: true, commands: [{ files: 10, wallMs: 5000 }] }), 15, "a move resets to 15 whatever the rate");
  assert.equal(batchSize({ moved: false }), 15, "no measured rate yet");
  // r049: 110 files at 2.65 s each natively; 15 files in 45 s gives 20 per command (60 s), never 40 (the alarmed batches)
  assert.equal(batchSize({ moved: false, commands: [{ files: 15, wallMs: 45_000 }] }), 20);
  assert.equal(batchSize({ moved: false, commands: [{ files: 15, wallMs: 45_000 }, { files: 20, wallMs: 80_000 }] }), 15, "the slowest rate decides");
  assert.equal(batchSize({ moved: false, commands: [{ files: 15, wallMs: 3000 }] }), 300, "fast files: a large batch");
  assert.equal(batchSize({ moved: false, commands: [{ files: 15, wallMs: 3000 }], cap: 40 }), 40, "--max-files only lowers it");
  assert.equal(batchSize({ moved: true, cap: 5 }), 5);
  assert.equal(batchSize({ moved: false, commands: [{ files: 1, wallMs: 90_000 }] }), 1, "at least one file");
  assert.equal(batchSize({ moved: false, commands: [{ files: 0, wallMs: 400 }] }), 15, "an empty command is no rate");
  // r051 (p3-main-x): the moved check must see the calibration's own record, not a HEAD the tree does not have
  const tree = join(dir, "checkout-x");
  assert.equal(checkedOut(tree), null, "never checked out: moved");
  writeFileSync(`${tree}.commit`, "abc\n");
  assert.equal(checkedOut(tree), "abc");
});

test("calibration runs offline in the runtime image", () => {
  const a = dockerArgs({ image: "img", tree: "/t/w", store: "pnpm", command: INSTALL });
  assert.deepEqual(a.slice(0, 6), ["run", "--rm", "--name", "layerfs-issue352-calibrate", "--network", "none"]);
  assert.ok(a.includes("pnpm:/pnpm-store:ro") && a.at(-1).includes("--offline"));
  assert.ok(dockerArgs({ image: "img", tree: "/t/w", store: "pnpm", network: "bridge", command: FETCH }).includes("pnpm:/pnpm-store"), "the fetch writes the store");
  assert.deepEqual(parseProbe('{"path":"a","status":"pass","ms":3}\nwarning\n'), [{ path: "a", status: "pass", ms: 3 }]);
  // pnpm 11's offline install reads registry metadata from the cache the fetch filled on the store volume, through a writable /tmp cache dir
  assert.ok(FETCH.includes("--store-dir /pnpm-store --cache-dir /pnpm-store/.cache"), FETCH);
  assert.ok(INSTALL.includes("for v in /pnpm-store/v*/") && INSTALL.includes("--store-dir /tmp/pnpm-store --cache-dir /tmp/pnpm-cache"), INSTALL);
  const tree = join(dir, "tree");
  mkdirSync(tree, { recursive: true });
  assert.match(noInstall(tree), /no pnpm-lock\.yaml/, "a yarn checkpoint installs nothing");
  writeFileSync(join(tree, "pnpm-lock.yaml"), "lockfileVersion: '9.0'\n");
  assert.equal(noInstall(tree), null);
  assert.deepEqual(chooseRun([{ path: "a", status: "skipped", reason: "no install", ms: 0 }], "range").skipped, [{ path: "a", reason: "no install" }]);
});

test("growth and snapshot-time gates", () => {
  const base = { checks: { tree: { ok: true }, history: { ok: true }, steps: { matched: 1, total: 1 }, conflicts: { planned: 0, hit: 0 }, tests: { equal: 2, run: 2 } }, health: { workspacesOpen: 0, overlaysLeft: 0 } };
  const MiB = 1 << 20;
  const history = [100, 120, 110].map((n, i) => ({ ...base, range: i, storage: { newStored: n * MiB } }));
  const row = (m) => evaluate(m, history).checks.find((c) => c.name === "Range growth").result;
  assert.equal(row({ ...base, range: 3, storage: { newStored: 300 * MiB } }), "pass");
  assert.equal(row({ ...base, range: 3, storage: { newStored: 400 * MiB } }), "optimize");
  assert.equal(row({ ...base, range: 3, storage: { newStored: 3 * 1024 * MiB } }), "optimize");
  assert.equal(evaluate({ ...base, checks: { ...base.checks, tests: { equal: 1, run: 2 } } }).verdict, "stop", "a test that differs from native stops");
  // copy time per new byte flat with size: pass; growing with size: optimize
  const snapped = (cost) => [1, 2, 4, 8].map((g, i) => ({ ...base, range: i, snapshot: { size: g * 2 ** 30, newBytes: 100 * MiB, copyMs: cost(g) } }));
  const snapRow = (ms) => { const all = snapped(ms); return evaluate(all.at(-1), all.slice(0, -1)).checks.find((c) => c.name === "Snapshot time").result; };
  assert.equal(snapRow(() => 400), "pass");
  assert.equal(snapRow((g) => 400 * g), "optimize");
});

/** A complete finding for range 12's attempt 1. */
const finding = () => ({
  range: 12, attempt: 1, verdict: "optimize",
  trigger: { check: "Range growth", value: "140.0 MiB, 4.52× the median", threshold: "≤ 3× median, ≤ 2 GiB" },
  diagnosis: { step: "D5", summary: "each install rewrote every node_modules directory leaf", counter: "directory_leaf_writes", exponent: { before: 0.94, after: 0.04 } },
  fix: { summary: "write a directory leaf only when its entries change", kind: 1, commit: "abcdef1234567", test: "layerfs-project directory_leaf_reuse",
    oldStores: "open unchanged", oldData: "still read as before", compat: "range-11 fork written by aaa opens and reads with bbb: proof ok" },
  improvement: [{ measure: "new stored bytes, range 12", before: 140, after: 33, unit: "MiB", oldBinary: "aaa", newBinary: "bbb", snapshot: "range-011", cache: "fresh daemon" }],
  recovery: "forked the range-11 snapshot and reran range 12 measured",
  record: "OPTIMIZATIONS.md#range-012-directory-leaves",
  records: [{ title: "directory leaves", path: "fixes/012-a1-directory-leaves.md" }],
  ledger: [{ file: "OPTIMIZATIONS.md", entry: "012.a1" }],
});

test("REBUILD.md §4: kind fields, the compatibility test for kinds 1-2, the four justifications for kind 3", () => {
  const ok = { kind: 2, oldStores: "open and migrate (adds t)", oldData: "read through a fallback", recovery: "migrate newest snapshot", compat: "r004 fork opens: ok" };
  assert.deepEqual(checkRebuild(ok), []);
  assert.ok(checkRebuild({ ...ok, compat: "pending" }).some((p) => /compatibility test/.test(p)));
  assert.ok(checkRebuild({ ...ok, oldData: "—" }).some((p) => /Old data/.test(p)));
  const three = { ...ok, kind: 3, compat: null, justification: { kind1: "old rows read wrong", kind2: "no fallback is correct", cost: "ranges 0-4, 3 min, 2 GiB" } };
  assert.deepEqual(checkRebuild(three), ["a kind 3 fix needs the newest good snapshot (REBUILD.md §3)"]);
  assert.deepEqual(checkRebuild({ ...three, justification: { ...three.justification, snapshot: "r003" } }), []);
  const record = (rows) => `# x\n\n| | |\n| --- | --- |\n${rows.map(([k, v]) => `| ${k} | ${v} |`).join("\n")}\n\n## Old design\n| Kind | 1 |\n`;
  const rows = [["Kind", "**2, additive migration** (REBUILD.md)"], ["Old Stores", "open and migrate"], ["Old data", "read through a fallback"], ["Compatibility test", "passed on r004"], ["Recovery", "migrate newest snapshot"]];
  assert.deepEqual(checkRecord("009-a1-x.md", record(rows)), []);
  assert.deepEqual(checkRecord("009-a1-x.md", record(rows.filter(([k]) => k !== "Compatibility test"))).length, 1);
  assert.deepEqual(checkRecord("009-a1-x.md", record([["Kind", "code path"], ...rows.slice(1)])), ["fixes/009-a1-x.md: kind is 1, 2 or 3 (REBUILD.md §2)"]);
  assert.deepEqual(checkRecord("002-a1-merge-ancestry.md", record([["Kind", "code path"]])), [], "records before REBUILD.md are exempt");
  assert.deepEqual(checkRecord("017-359-x.md", record([["Kind", "code path only"]])), [], "another lane's record without kind 1-3 is not the fixer's");
  assert.deepEqual(checkRecord("c01-x.md", record(rows.filter(([k]) => k !== "Compatibility test"))).length, 1, "another lane's record that declares a kind is checked");
  assert.deepEqual(checkRecord("009-a1-g.md", record([["Kind", "none: gate"], ["Recovery", "rerun"]])), [], "no product change");
  assert.deepEqual(checkRecord("009-a1-g.md", record([["Kind", "none"], ["Recovery", "rerun"]])).length, 1, "none says why");
  // every committed fixer record validates
  assert.deepEqual(checkRecords(new URL("../../../../core/docs/issues/352/fixes", import.meta.url).pathname), []);
});

test("a finding record is checked, loaded by range and attempt, and its change is signed", () => {
  assert.deepEqual(checkFinding(finding()), []);
  const bad = { ...finding(), diagnosis: { step: "D9" }, fix: { kind: "guess" }, improvement: [] };
  const problems = checkFinding(bad).join("; ");
  for (const p of ["diagnosis.step", "diagnosis.summary", "fix.summary", "fix.commit", "fix.kind", "improvement"]) assert.ok(problems.includes(p), p);
  const unlinked = checkFinding({ ...finding(), records: [{ title: "x", path: "fixes/013-a1-x.md" }], ledger: [], improvement: [{ measure: "m", before: 1, after: 2 }] }).join("; ");
  for (const p of ["needs oldBinary", "needs cache", "fixes/012-a1-<slug>.md", "ledger names"]) assert.ok(unlinked.includes(p), p);
  const metrics = join(dir, "metrics");
  mkdirSync(metrics);
  writeFileSync(join(metrics, "finding-012.a2.json"), JSON.stringify({ ...finding(), attempt: 2 }));
  writeFileSync(join(metrics, "finding-012.a1.json"), JSON.stringify(finding()));
  assert.deepEqual(loadFindings(metrics).get(12).map((f) => f.attempt), [1, 2]);
  assert.equal(loadFindings(join(dir, "nowhere")).size, 0);
  assert.equal(checkFinding({ ...finding(), fix: { ...finding().fix, kind: "code path" } }).join(), "fix.kind is 1, 2 or 3 (REBUILD.md §2)", "only PRE_REBUILD findings keep the SPEC §6 kind");
  assert.deepEqual(checkFinding({ ...finding(), range: 2, records: [{ title: "x", path: "fixes/002-a1-x.md" }], fix: { ...finding().fix, kind: "format", oldStores: null, compat: null } }), []);
  assert.deepEqual([change(140, 33), change(100, 120), change(5, 5), change(0, 3)], ["−76%", "+20%", "±0%", "—"]);
});

test("a finding closed without a code change (kind none): evidence table, no commit or regression test", () => {
  const none = { ...finding(), range: 13, records: [{ title: "x", path: "fixes/013-a1-x.md" }],
    fix: { kind: "none", summary: "not a product finding: the Sandbox's command launch" }, improvement: undefined,
    evidence: [{ measure: "exec true 10x median, range 13", value: 40.99, unit: "ms", binary: "daemon 6d467539", snapshot: "fork of range 13", cache: "fresh daemon" }] };
  assert.deepEqual(checkFinding(none), []);
  assert.deepEqual(checkFinding(none, { full: true }), [], "no design or cost without a code change");
  const missing = checkFinding({ ...none, evidence: [] }).join("; ");
  assert.ok(missing.includes("evidence has at least one row") && !missing.includes("fix.commit") && !missing.includes("compatibility") && !missing.includes("improvement has"), missing);
  assert.ok(checkFinding({ ...none, evidence: [{ measure: "m", value: 1 }] }).join().includes('evidence "m" needs binary'));
  assert.ok(checkFinding({ ...none, improvement: [{ measure: "m", before: 1, after: 2, oldBinary: "a", newBinary: "b", snapshot: "s", cache: "c" }] }).join().includes("improvement rows need a code change"));
  assert.ok(checkFinding({ ...finding(), fix: { ...finding().fix, commit: undefined } }).join().includes("fix.commit"), "a code fix still needs its commit");
  // rendered: the evidence table in place of the before/after one, no Commits row
  const block = renderFinding(13, 1, none);
  assert.ok(block.includes("| Measure | Value | Binary | Snapshot / checkpoint | Cache |") && block.includes("| exec true 10x median, range 13 | 40.99 ms |") && block.includes("none: no code change") && !block.includes("commits"), block);
  const fmt = renderFindingFormat(13, { attempt: 1, binary: { daemon: "6d467539aa" } }, { verdict: "optimize", checks: [] }, none, null);
  assert.ok(fmt.includes("→ closed without a code change") && fmt.includes("**3. Evidence**") && !fmt.includes("| Commits |") && fmt.includes("none: no code change."), fmt);
  assert.deepEqual(findingTableProblems(fmt, { none: true }), []);
  assert.ok(findingTableProblems(fmt)[0].includes("before/after columns"));
  const comment = renderOptimization({ plan: { range: 13 }, attempts: [{ attempt: 1 }, { attempt: 2 }], gates: [{ verdict: "optimize", checks: [] }, { verdict: "watch", checks: [] }], findings: [none] });
  assert.ok(comment.includes("**Closed without a code change:**") && comment.includes("| Evidence | Value |") && comment.includes("exec true 10x median"), comment);
  // the block: no design lines, the rerun under the same binary (or none), and the format check takes it
  assert.ok(!fmt.includes("| Old design |") && fmt.includes("**4. Attempt vs rerun") && fmt.includes("No rerun: no code change"), fmt);
  const rerun = renderFindingFormat(13, { attempt: 1, binary: { daemon: "6d467539aa" } }, { verdict: "optimize", checks: [] }, none, { attempt: 2, binary: { daemon: "6d467539aa" } });
  assert.ok(rerun.includes("| Measure | Attempt 1 · `6d467539aa` | Attempt 2 · `6d467539aa` |") && !rerun.includes("(without)"), rerun);
  // a later attempt that trips again keeps the earlier finding's evidence in the comment (F3)
  const again = renderOptimization({ plan: { range: 13 }, attempts: [{ attempt: 1 }, { attempt: 2 }], gates: [{ verdict: "optimize", checks: [] }, { verdict: "optimize", checks: [{ name: "Scaling", value: "fork 1.08", threshold: "< 0.15", result: "optimize" }] }], findings: [none] });
  assert.ok(again.includes("Optimization needed") && again.includes("#### Attempt 1: closed without a code change") && again.includes("exec true 10x median"), again);
  const both = renderOptimization({ plan: { range: 13 }, attempts: [{ attempt: 1 }, { attempt: 2 }], gates: [{ verdict: "optimize", checks: [] }, { verdict: "optimize", checks: [{ name: "Scaling", value: "x", threshold: "y", result: "optimize" }] }], findings: [none, { ...none, attempt: 2 }] });
  assert.ok(both.indexOf("#### Attempt 2: closed") < both.indexOf("#### Attempt 1: closed"), both);
});

test("the comment's optimization part: none, pending, then trigger, diagnosis, fix and improvement", () => {
  const plan = { range: 12 };
  const gate = (verdict, checks) => ({ verdict, checks });
  const pass = gate("pass", [{ name: "Range growth", value: "33.0 MiB, 1.06× the median", threshold: "≤ 3×", result: "pass" }]);
  const tripped = gate("optimize", [{ name: "Range growth", value: "140.0 MiB, 4.52× the median", threshold: "≤ 3×", result: "optimize" }]);
  assert.equal(renderOptimization({ plan, attempts: [{ attempt: 1 }], gates: [pass] }), "**Optimization:** none.");
  const pending = renderOptimization({ plan, attempts: [{ attempt: 1 }], gates: [tripped] });
  assert.ok(pending.includes("Optimization needed") && pending.includes("**Trigger:** Range growth: 140.0 MiB") && pending.includes("pending") && pending.includes("finding-012.a1.json"));
  const done = renderOptimization({ plan, attempts: [{ attempt: 1 }, { attempt: 2 }], gates: [tripped, pass], findings: [finding()] });
  for (const part of ["Optimization (from attempt 1)", "D5 · each install", "depth exponent 0.94 → 0.04", "1 forward-only · commit `abcdef123`", "**Now:** Range growth pass", "| new stored bytes, range 12 | 140 MiB | 33 MiB | −76% |", "OPTIMIZATIONS.md#"]) assert.ok(done.includes(part), part);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { await fn(); console.log(`ok   ${name}`); } catch (error) { failed++; console.log(`FAIL ${name}\n${error.stack}`); }
}
rmSync(dir, { recursive: true, force: true });
console.log(`${tests.length - failed}/${tests.length} passed`);
if (failed) process.exit(1);
