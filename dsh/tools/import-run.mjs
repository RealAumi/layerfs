// Converts a recorded application run into a replayed Live demo (issue #347):
//   node dsh/tools/import-run.mjs <format> <id> <store.json> key=value…
// <format> names the record's reader in import/ (shop, depot, crew); <store.json>
// is what restore-store.mjs printed for a restored copy of the run's stopped
// Store. Writes dsh/scenarios/<id>/: scenario.json, run/NNN.json (one per kept
// step), seed.json (the original Init's imported folder) and final.json (the
// tracked files of the recorded final main, and the recorded history for the
// order checks). The conversion formula is SPEC.md's (core/docs/issues/347).
// Each command is classed from the record: one whose following Commit changed
// no tracked file (or only CPython bytecode, which no recorded main holds) is
// verification only. `verification=off` keeps such a step but runs no command
// in it: the run file marks the call, the replay says so, and the Commit after
// it must be UpToDate. `no-browser` (Crew's default, the owner's decision for
// #350) does so only for those of a browser proof.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync, lstatSync, readlinkSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { variesOf } from "./checks/gates.mjs";
import { assemble } from "./import/turns.mjs";
import { storeReads } from "./import/reads.mjs";

const FORMATS = {
  shop: { read: async (i) => (await import("./import/shop.mjs")).readShop(i), title: "Shop", order: 7, blurb: "a builder agent's recorded run of a small web shop, from skeleton to admin page, over six milestones", target: 60, verification: "on", inputs: ["trace", "builder", "seed"] },
  depot: { read: async (i) => (await import("./import/depot.mjs")).readDepot(i), title: "Depot", order: 8, blurb: "a builder agent's recorded run of a Rust inventory service and its browser client", target: 240, verification: "on", inputs: ["receipts", "seed"] },
  crew: { read: async (i) => (await import("./import/crew.mjs")).readCrew(i), title: "Crew", order: 9, blurb: "a lead and its crew of agents building one application together, on Branches of their own", target: 120, floor: 50, verification: "no-browser", inputs: ["traces", "agents", "seed"] },
};
const IMAGE = "sha256:091f785ba7d5d036dfa350e8fd69ee1fcd2d8320c3706841c8c95e6411eee9d2";
const WRITES = new Set(["fs.apply", "fs.write", "fs.edit", "fs.mkdir", "fs.rm", "fs.cp", "fs.mv"]);
const HISTORY = new Set(["branch.fork", "branch.merge", "branch.publish"]);
const WORKSPACE = new Set(["sandbox.mount", "sandbox.exec", "sandbox.commit", "sandbox.unmount"]);
const LIFE = new Set(["sandbox.create", "sandbox.close"]);
const OUTPUT_LINES = 12, OUTPUT_BYTES = 2048;
// CPython bytecode a py_compile check leaves (tracked, but never on a recorded main)
const BYTECODE = /(^|\/)__pycache__(\/|$)|\.pyc$/;

const [format, id, storeFile, ...rest] = process.argv.slice(2);
const kind = FORMATS[format];
if (!kind || !id || !storeFile) {
  console.error(`usage: import-run.mjs <${Object.keys(FORMATS).join("|")}> <id> <store.json> key=value…`);
  process.exit(2);
}
const inputs = Object.fromEntries(rest.map((pair) => [pair.slice(0, pair.indexOf("=")), pair.slice(pair.indexOf("=") + 1)]));
for (const key of kind.inputs) if (!inputs[key]) throw new Error(`${format} needs ${key}=…`);
const verification = inputs.verification ?? kind.verification;
// no-browser: disable only the verification commands that drive a browser (import/crew.mjs decides)
if (!["on", "off", "no-browser"].includes(verification)) throw new Error("verification=on|off|no-browser");
const out = fileURLToPath(new URL(`../scenarios/${id}/`, import.meta.url));

const store = JSON.parse(readFileSync(storeFile, "utf8"));
Object.assign(process.env, store.env);
const { LayerFS } = await import(store.sdk);
const { LayerFSOperator } = await import(new URL("../operator/index.js", `file://${store.sdk}`).href);
const reads = await storeReads(store, inputs.cache, () => { const lf = new LayerFS(store.project); return { lf, operator: new LayerFSOperator(lf) }; });

const fail = (message) => { throw new Error(`import-run ${id}: ${message}`); };
const kindOf = (call) => (call.ok === false ? call.code : call.kind ?? "ok");

try {
  const record = await kind.read(inputs);
  const { history } = reads, branchNames = new Set(Object.keys(history.branches));

  // the agents' own Sandboxes: those a Workspace was mounted in
  const agentBoxes = new Set();
  const boxOwner = new Map(); // which agent mounted in each Sandbox
  for (const step of record.steps) for (const c of step.calls) if (c.method === "sandbox.mount") { agentBoxes.add(c.args.sandbox); boxOwner.set(c.args.sandbox, step.agent); }
  // each mount's Workspace path: a Sandbox numbers its Workspaces in mount order
  const mountPaths = new Map();
  for (const box of agentBoxes) {
    const all = record.steps.flatMap((s) => s.calls).filter((c) => c.args.sandbox === box);
    const paths = [...new Set(all.filter((c) => WORKSPACE.has(c.method) && c.method !== "sandbox.mount").map((c) => c.args.path).filter(Boolean))].sort((a, b) => num(a) - num(b));
    const mounts = all.filter((c) => c.method === "sandbox.mount" && c.ok !== false); // a refused mount has no Workspace
    if (paths.length !== mounts.length) fail(`Sandbox ${box}: ${mounts.length} mounts but ${paths.length} Workspace paths`);
    mounts.forEach((m, i) => mountPaths.set(m, paths[i]));
  }

  // each command's class, from the Commit that follows it in its Workspace
  const verifies = new Set(), before = new Map(), pending = new Map();
  for (const step of record.steps) for (const call of step.calls) {
    const key = `${step.origin ?? ""} ${call.args.sandbox} ${call.args.path}`;
    if (call.method === "sandbox.exec") pending.set(key, [...(pending.get(key) ?? []), call]);
    if (call.method !== "sandbox.commit" || !pending.has(key)) continue;
    const execs = pending.get(key), changes = call.ok && call.kind === "Committed" && call.commit ? await reads.tracked(call.commit) : null;
    pending.delete(key);
    before.set(call, execs);
    if ((call.ok && call.kind === "UpToDate") || (changes && changes.every((c) => BYTECODE.test(c.path)))) for (const e of execs) verifies.add(e);
  }
  for (const execs of pending.values()) for (const e of execs) verifies.add(e); // no Commit follows: it changed nothing kept
  const disabled = (call) => verifies.has(call) && (verification === "off" || (verification === "no-browser" && call.browser === true));
  // a Commit with only disabled commands since the mount or the last Commit
  const afterDisabled = (commit) => before.get(commit)?.length > 0 && before.get(commit).every(disabled);

  const dropped = new Set(), optional = new Set(), absent = new Set(), kept = [], notes = [], extras = [], wsBranch = new Map();
  const lastEnd = new Map();
  for (const step of record.steps) {
    const calls = [];
    for (const call of step.calls) {
      const m = call.method;
      if (m === "project.init") { lastEnd.set(step.agent, call.start + call.ms); continue; }
      if (WRITES.has(m)) {
        if (call.ok === false) fail(`${step.label}: a refused ${m} is not replayed yet`);
        const all = await changesOf(call.commit);
        // with verification off or no-browser no run makes bytecode (only the disabled py_compile checks did), so a write leaves it alone
        const changes = verification !== "on" ? all.filter((c) => !BYTECODE.test(c.path)) : all;
        if (!changes.length) { dropped.add(call.commit); notes.push(`${step.label}: ${m} ${short(call.commit)} has no tracked content change${all.length ? " but bytecode" : ""}; dropped`); continue; }
        if (changes.length < all.length) notes.push(`${step.label}: ${m} ${short(call.commit)}: its bytecode changes are left out (no run makes bytecode)`);
        calls.push({ op: "write", branch: call.args.branch, message: fullMessage(call), changes, commit: call.commit, expect: `fs.apply:${kindOf(call)}` });
      } else if (HISTORY.has(m)) {
        const a = call.args;
        if (m === "branch.fork") calls.push({ op: "fork", name: a.name, from: refOf(a.from ?? "main", history.ids, branchNames), expect: `${m}:${kindOf(call)}` });
        if (m === "branch.merge") calls.push({ op: "merge", a: a.branch, b: a.with, name: a.name, message: a.message ?? null, expect: `${m}:${kindOf(call)}` });
        if (m === "branch.publish") calls.push({ op: "publish", branch: a.branch, commit: a.commit ? refOf(a.commit, history.ids, branchNames) : null, expect: `${m}:${kindOf(call)}` });
      } else if (LIFE.has(m)) {
        if (m === "sandbox.close" && !agentBoxes.has(call.args.sandbox)) continue; // the service Sandbox, or one nobody used; each call closes its own
        if (m === "sandbox.create" && call.created && !agentBoxes.has(call.created)) { notes.push(`${step.label}: a Sandbox no agent mounted in; its create is dropped`); continue; }
        // the lead created a worker's Sandbox (Crew): the create stays the lead's and the Sandbox is the worker's
        const owner = m === "sandbox.create" && call.created ? boxOwner.get(call.created) : null;
        calls.push({ op: m === "sandbox.create" ? "create" : "close", ...(owner && owner !== step.agent ? { for: owner } : {}), expect: `${m}:${kindOf(call)}` });
      } else if (WORKSPACE.has(m)) {
        const recorded = m === "sandbox.mount" ? mountPaths.get(call) : call.args.path;
        // a role played by several recorded agents (Crew) keeps each one's Workspaces apart
        const ws = step.origin ? `${step.origin}:${recorded}` : recorded;
        if (m === "sandbox.mount") { wsBranch.set(`${call.args.sandbox} ${ws}`, call.args.branch); calls.push({ op: "mount", branch: call.args.branch, ws, expect: `${m}:${kindOf(call)}` }); }
        if (m === "sandbox.unmount") calls.push({ op: "unmount", ws, discard: call.args.discard === true, expect: `${m}:${kindOf(call)}` });
        if (m === "sandbox.exec") calls.push(execOf(step, call, ws, notes, verifies.has(call), disabled(call)));

        if (m === "sandbox.commit") {
          let expect = `${m}:${kindOf(call)}`;
          if (afterDisabled(call)) {
            // no command ran since the mount or the last Commit: nothing may have changed
            if (call.kind === "Committed") { optional.add(call.commit); absent.add(call.commit); }
            calls.push({ op: "commit", ws, message: fullMessage(call), force: call.args.force === true, commit: call.commit ?? null, expect: `${m}:UpToDate` });
            if (calls.at(-1).at === undefined) Object.defineProperty(calls.at(-1), "at", { value: call.start, enumerable: false });
            continue;
          }
          if (call.ok && call.kind === "Committed" && call.commit && (await reads.tracked(call.commit))?.length === 0) {
            expect = `${m}:Committed|UpToDate`;
            optional.add(call.commit);
          }
          // a recorded UpToDate may come back Committed when the command touched
          // only generated files (cargo's cache tracker writes last-use times
          // only once enough wall time has passed); replay.mjs and the order
          // check verify that such a Commit changes no tracked file
          const generated = call.ok && call.kind === "UpToDate";
          if (generated) {
            expect = `${m}:UpToDate|Committed`;
            extras.push({ branch: wsBranch.get(`${call.args.sandbox} ${ws}`), message: call.args.message ?? null, head: call.commit ?? null });
          }
          calls.push({ op: "commit", ws, message: fullMessage(call), force: call.args.force === true, commit: call.commit ?? null, expect, ...(generated ? { generated: true } : {}) });
        }
      }
      // reads, sandbox.service, status and operator calls are dropped
      if (calls.length && calls.at(-1).at === undefined) Object.defineProperty(calls.at(-1), "at", { value: call.start, enumerable: false });
    }
    const end = Math.max(...step.calls.map((c) => c.start + c.ms));
    if (!calls.length) continue;
    const start = Math.min(...step.calls.map((c) => c.start));
    const gap = Math.max(0, start - (lastEnd.get(step.agent) ?? start));
    lastEnd.set(step.agent, end);
    kept.push({ step, calls, gap, ms: Math.round(end - start), start });
  }

  // A recorded ref "branch#i" counts the recorded Commits; a run makes no
  // dropped Commit, nor one after a disabled command (it answers UpToDate). So
  // i counts only those the run makes, and a ref to one it does not make names
  // the one before it: the missing one changed no tracked file but bytecode.
  const made = (branch, i) => !dropped.has(idAt(branch, i)) && !absent.has(idAt(branch, i));
  const remap = (ref, where) => {
    const [, branch, index] = /^(.+)#([0-9]+)$/.exec(ref ?? "") ?? [];
    if (!branch) return ref;
    let i = Number(index);
    while (i >= 0 && !made(branch, i)) i--;
    if (i < 0) fail(`${where}: ${ref} and every Commit before it on ${branch} are not made by a run`);
    let n = 0;
    for (let j = 0; j < i; j++) if (made(branch, j)) n++;
    if (i !== Number(index)) notes.push(`${where}: ${ref} is not made by a run; the ref names ${branch}#${i} before it (the same tracked files, bytecode aside)`);
    return `${branch}#${n}`;
  };
  for (const s of kept) for (const c of s.calls) {
    if (c.op === "fork") c.from = remap(c.from, s.step.label);
    if (c.op === "publish" && c.commit) c.commit = remap(c.commit, s.step.label);
  }

  // Every replayed Store call goes through its agent's own Sandbox: the service
  // Sandbox is shared with the Host's reads, whose discovery lock would refuse
  // one of them as Busy depending on timing. So an agent's recorded create
  // that comes after its first Store call moves to just before that call.
  const who = (s) => s.step.origin ?? s.step.agent; // each recorded agent has its own Sandbox
  for (const agent of new Set(kept.map(who))) {
    const mine = kept.filter((s) => who(s) === agent);
    const at = (pred) => { for (const s of mine) { const i = s.calls.findIndex(pred); if (i >= 0) return { s, i }; } return null; };
    const first = at((c) => ["fork", "merge", "publish", "write"].includes(c.op)), create = at((c) => c.op === "create");
    if (!first) continue;
    if (!create) {
      // a Sandbox another agent created for this one: that create comes first (turns.mjs orders it)
      const role = mine[0].step.agent;
      if (kept.some((x) => kept.indexOf(x) < kept.indexOf(first.s) && x.calls.some((c) => c.op === "create" && c.for === role))) continue;
      fail(`${agent} makes Store calls but never creates a Sandbox`);
    }
    if (kept.indexOf(create.s) < kept.indexOf(first.s) || (create.s === first.s && create.i < first.i)) continue;
    const [call] = create.s.calls.splice(create.i, 1);
    first.s.calls.splice(first.s.calls.indexOf(first.s.calls[first.i]), 0, call);
    notes.push(`${agent}: its Sandbox is created before its first Store call (${first.s.step.label}), not at ${create.s.step.label}`);
    if (!create.s.calls.length) kept.splice(kept.indexOf(create.s), 1);
  }
  for (const s of kept) {
    const close = s.calls.findIndex((c) => c.op === "close");
    const after = kept.slice(kept.indexOf(s)).flatMap((x) => (x === s ? x.calls.slice(close + 1) : x.calls)).filter((c) => s.step.agent && ["fork", "merge", "publish", "write"].includes(c.op));
    if (close >= 0 && after.length && kept.some((x) => who(x) === who(s) && x.calls.includes(after[0]))) fail(`${who(s)} makes Store calls after closing its Sandbox`);
  }

  // pauses: clamp(gap × k, floor, 3000), k chosen so they sum to the target
  // thinking time; the floor is 400 ms, but Crew's 1,550 steps need 50 ms to fit 2 minutes
  const target = kind.target * 1000, floor = kind.floor ?? 400, pause = (k, gap) => Math.round(Math.min(3000, Math.max(floor, gap * k)));
  let lo = 0, hi = 1;
  while (kept.reduce((n, s) => n + pause(hi, s.gap), 0) < target && hi < 1e6) hi *= 2;
  for (let i = 0; i < 60; i++) { const k = (lo + hi) / 2; if (kept.reduce((n, s) => n + pause(k, s.gap), 0) < target) lo = k; else hi = k; }

  if (existsSync(out)) rmSync(out, { recursive: true });
  mkdirSync(join(out, "run"), { recursive: true });
  const stepsOf = [];
  kept.forEach((s, i) => {
    const n = String(i + 1).padStart(Math.max(3, String(kept.length).length), "0");
    const execs = s.calls.filter((c) => c.op === "exec"), writes = s.calls.filter((c) => c.op === "write");
    const running = execs.filter((c) => !c.disabled), expect = s.calls.map((c) => c.expect).filter(Boolean);
    const file = {
      step: s.step.label, agent: s.step.agent, ...(execs.some((c) => c.disabled) ? { verification } : {}),
      kind: execs.length ? "replay" : writes.length ? "write" : "history",
      branch: s.calls.find((c) => c.branch)?.branch ?? null,
      writes: writes.length ? Object.fromEntries(writes.flatMap((w) => w.changes.map((c) => [c.path, c.op === "write" ? c.content : c.op === "rm" ? null : "<dir>"]))) : null,
      command: execs[0]?.command ?? null, exit: execs[0]?.exit ?? null, output: execs[0]?.output ?? null,
      ms: s.ms, expect, calls: s.calls,
    };
    writeFileSync(join(out, "run", `${n}.json`), JSON.stringify(file, null, 1) + "\n");
    const inner = running.reduce((t, c) => t + (innerTimeout(c.command) ?? 110), 0);
    const description = execs.length && !running.length ? `${s.step.label} (verification disabled)` : s.step.label;
    stepsOf.push([{ pause: pause(hi, s.gap) }, {
      bash: { description, run: [["step", id, n]], ...(inner ? { timeoutMs: (inner + 60) * 1000 } : {}) },
      ...(expect.length ? { expect } : {}), ...(s.step.agent === "root" ? { phase: phaseOf(s.step.label) } : {}),
    }]);
  });
  const agents = kept.every((s) => s.step.agent === "root") ? { root: stepsOf.flat() } : assemble(kept, (i) => stepsOf[i]);

  // the recorded history without the dropped Commits (refs past one count
  // without it; a ref to one names the Commit before it, or the fork point),
  // and without the Branches only the dropped observer made; an optional
  // Commit may be missing
  const created = new Set(kept.flatMap((s) => s.calls.filter((c) => c.op === "fork" || c.op === "merge").map((c) => c.name)));
  const rename = (ref) => {
    const [, branch, index] = /^(.+)#([0-9]+)$/.exec(ref ?? "") ?? [];
    if (!branch) return ref;
    let i = Number(index);
    while (i >= 0 && dropped.has(idAt(branch, i))) i--;
    if (i < 0) return rename(history.branches[branch].forkedFrom);
    return `${branch}#${history.branches[branch].commits.slice(0, i).filter((c) => !dropped.has(c.id)).length}`;
  };
  const recorded = { branches: {}, layers: history.layers.map((l) => ({ ...l, source: rename(l.source) })) };
  for (const [branch, b] of Object.entries(history.branches)) {
    if (!created.has(branch)) { notes.push(`history: ${branch} is made by no kept step (the observer's); left out of the order checks`); continue; }
    recorded.branches[branch] = {
      forkedFrom: rename(b.forkedFrom),
      commits: b.commits.filter((c) => !dropped.has(c.id))
        .map(({ id: cid, ...c }) => ({ ...c, merged: rename(c.merged), ...(optional.has(cid) ? { optional: true } : {}) })),
    };
  }
  const refs = [...recorded.layers.map((l) => l.source), ...Object.values(recorded.branches).flatMap((b) => [b.forkedFrom, ...b.commits.map((c) => c.merged)])];
  for (const ref of refs) if (ref && /#[0-9]+$/.test(ref) && !recorded.branches[ref.replace(/#[0-9]+$/, "")]) fail(`the order check names ${ref}, of a Branch it leaves out`);
  if (dropped.size) notes.push(`history: ${dropped.size} dropped Commit(s) are left out of the order checks`);
  // where a run may hold an extra generated-only Commit: after the head the recorded UpToDate saw
  for (const e of extras) {
    const branch = recorded.branches[e.branch] ?? fail(`an UpToDate Commit on ${e.branch}, which is not in the history`);
    const ref = e.head && history.ids.get(e.head);
    const k = ref?.startsWith(`${e.branch}#`) ? Number(ref.slice(e.branch.length + 1)) : -1;
    const after = history.branches[e.branch].commits.slice(0, k + 1).filter((c) => !dropped.has(c.id)).length - 1;
    (branch.extras ??= []).push({ after, message: e.message });
  }
  // main's files hashed by their bytes, in a Workspace of a Sandbox of the converter's own
  const final = await reads.final();
  reads.save();
  writeFileSync(join(out, "final.json"), JSON.stringify({ main: final.files, varies: variesOf(final.files), history: recorded }, null, 1) + "\n");
  writeFileSync(join(out, "seed.json"), JSON.stringify(seedOf(inputs.seed), null, 1) + "\n");
  const scenario = {
    type: "layerfs-mock-scenario", version: 2, title: kind.title, order: kind.order, speed: 1,
    blurb: record.blurb ?? `Replays ${kind.blurb}. Every recorded write is applied and every recorded command runs again in a Workspace${verification !== "on" && verifies.size ? `, except those that only verify${verification === "no-browser" ? " and drive a browser" : ""}, which are disabled` : ""}.`,
    live: true, image: IMAGE, seed: "seed.json", lib: "../shared/replay.mjs",
    agents,
  };
  writeFileSync(join(out, "scenario.json"), JSON.stringify(scenario, null, 1) + "\n");
  for (const note of notes) console.log(note);
  const all = kept.flatMap((s) => s.calls.filter((c) => c.op === "exec"));
  console.log(`${id}: ${kept.length} steps, ${all.length} commands (${all.filter((c) => c.verification).length} verification only, ${all.filter((c) => c.disabled).length} disabled: verification ${verification}), pauses ${Math.round(kept.reduce((n, s) => n + pause(hi, s.gap), 0) / 1000)} s, ${Object.keys(final.files).length} tracked files on main`);
} finally {
  await reads.close();
}

/** A recorded Commit's message: the trace shortens a long one ("…"), the Store has it whole. */
function fullMessage(call) {
  const m = call.args.message ?? null, whole = call.commit && reads.commits.get(call.commit)?.message;
  return m?.endsWith("…") && whole?.startsWith(m.slice(0, -1)) ? whole : m;
}
/** The id of a Branch's i-th recorded Commit, as the Branch lists it. */
function idAt(branch, i) { return reads.history.branches[branch]?.commits[i]?.id; }
function num(path) { return Number(String(path).split("/").pop()); }
function short(cid) { return String(cid).slice(0, 12); }
/** A recorded fork or publish source: main, a Branch by name (its head then), or a Commit or Layer id by its place. */
function refOf(ref, ids, branches) { return ref === "main" || branches.has(ref) ? ref : ids.get(ref) ?? fail(`unknown ref ${ref}`); }
function phaseOf(label) { return label.replace(/^[0-9]+[-\s]*/, "").replace(/[-:].*$/, "").trim() || null; }
function innerTimeout(command) { const m = /\btimeout\s+(?:-[a-zA-Z]+\s+\S+\s+)*([0-9]+)/.exec(command ?? ""); return m ? Number(m[1]) : null; }

/**
 * The exec call of a recorded command: verbatim, the recorded Workspace path
 * made $PWD. A disabled verification command keeps its call, with no expect.
 */
function execOf(step, call, ws, notes, verifies, off) {
  const path = call.args.path, command = String(call.command ?? call.args.command);
  if (command.endsWith("…")) fail(`${step.label}: the record has only a shortened command`);
  const replaced = command.replace(new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![0-9])`, "g"), "$PWD");
  if (/\/(Users|private|var\/folders|home)\//.test(replaced)) fail(`${step.label}: the command names a host path`);
  const inner = innerTimeout(replaced);
  if (inner === null) {
    if (call.ms > 10_000) fail(`${step.label}: a command without an inner timeout ran ${Math.round(call.ms)} ms`);
    notes.push(`${step.label}: a command without an inner timeout (recorded ${Math.round(call.ms)} ms); the bash call's own timeout bounds it`);
  } else if (inner > 110) fail(`${step.label}: inner timeout ${inner} s is over 110 s`);
  const exit = /^exit:(-?[0-9]+)$/.exec(call.kind ?? "")?.[1];
  if (call.ok === false || exit === undefined) fail(`${step.label}: exec ended ${kindOf(call)}`);
  const lines = String(call.output ?? "").trimEnd().split("\n").slice(-OUTPUT_LINES).join("\n");
  // a recorded exit that came from a race (import/crew.mjs) may come out either way
  const flaky = call.flaky ? { flaky: call.flaky } : call.sandboxOwn ? { sandboxOwn: call.sandboxOwn } : {};
  const expect = off ? null : `sandbox.exec:exit:${exit}${flaky.flaky || flaky.sandboxOwn ? (exit === "0" ? "|1" : "|0") : ""}`;
  return { op: "exec", ws, command: replaced, message: call.args.message ?? null, exit: Number(exit), output: Buffer.from(lines).subarray(-OUTPUT_BYTES).toString(), ms: Math.round(call.ms), expect, ...(verifies ? { verification: true } : {}), ...(call.browser ? { browser: true } : {}), ...(off ? { disabled: true } : {}), ...flaky };
}

/** A write Commit's tracked changes, from the Store: what its fs.apply replays. */
async function changesOf(commitId) {
  const items = (await reads.tracked(commitId)) ?? fail(`no Commit ${commitId} in the Store`);
  const removed = items.filter((i) => i.kind === "Removed").map((i) => i.path);
  const top = removed.filter((p) => !removed.some((q) => q !== p && p.startsWith(`${q}/`)));
  const changes = [];
  for (const i of items.filter((i) => i.kind === "Added" && i.type === "dir").sort((x, y) => x.path.length - y.path.length)) changes.push({ op: "mkdir", path: i.path });
  for (const i of items) {
    if (i.kind === "Removed" || i.type === "dir") continue;
    if (i.type !== "file") fail(`${i.path}: a ${i.type} write is not replayed yet`);
    const read = await reads.text(commitId, i.path);
    if (read.problem) fail(`${i.path} at ${short(commitId)}: ${read.problem}`);
    changes.push({ op: "write", path: i.path, content: read.text });
  }
  for (const path of top) changes.push({ op: "rm", path });
  return changes;
}

/** The original Init's imported folder as data: every entry, its mode and its content. */
function seedOf(folder) {
  const entries = {};
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name), rel = `/${relative(folder, path)}`, st = lstatSync(path);
      if (st.isSymbolicLink()) entries[rel] = { type: "symlink", target: readlinkSync(path) };
      else if (st.isDirectory()) { entries[rel] = { type: "dir", mode: st.mode & 0o7777 }; walk(path); }
      else {
        const bytes = readFileSync(path), text = bytes.toString("utf8");
        entries[rel] = Buffer.from(text).equals(bytes) ? { type: "file", mode: st.mode & 0o7777, text } : { type: "file", mode: st.mode & 0o7777, base64: bytes.toString("base64") };
      }
    }
  };
  if (!statSync(folder).isDirectory()) fail(`seed ${folder} is not a folder`);
  walk(folder);
  return { format: "layerfs-demo-seed", version: 1, sha256: createHash("sha256").update(JSON.stringify(entries)).digest("hex"), entries };
}
