// Replays a recorded SDK trace through the view model: the Branches, heads
// and Sandboxes LayerFS reported, attribution, and the merge cases of #347
// row 51. Ported from the former sdk_sim/test_dsh_view.mjs's trace mode.
//   node dsh/packages/model/tests/trace.mjs [trace.jsonl]
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as X from "../src/index.js";

const file = process.argv[2] || new URL("./fixtures/real-trace.jsonl", import.meta.url);
const expected = JSON.parse(readFileSync(new URL("./fixtures/real-trace.expect.json", import.meta.url), "utf8"));
const lines = X.parseTrace(readFileSync(file, "utf8"));
const E = new X.ReplayEngine({ project: expected.project });
const w = X.createView(E, { lead: "main" });
X.derive(w);
for (const st of X.traceSteps(lines)) await X.runStep(w, st, {});
const s = E.s;
// Branches and heads, Sandboxes and their Workspaces, as LayerFS reported them at the end
const branches = Object.fromEntries(s.branchOrder.map((b) => [b, E.m.real(s.branches[b].head) ?? null]));
assert.deepEqual(branches, expected.branches);
assert.equal(E.m.real(s.main.head), expected.mainLayer);
assert.deepEqual(s.sandboxOrder.map((id) => [E.m.real(id), s.sandboxes[id].closed]), expected.sandboxes);
assert.deepEqual(Object.keys(w.ws), [], "nothing mounted at the end");
// attribution: every call in the trace is the main agent's; the script's step groups them
for (const [node, by] of Object.entries(w.attrib)) assert.equal(by, "main", node);
assert.ok(Object.keys(w.attrib).length >= expected.minNodes);
assert.ok(w.hist.every((h) => h.group === expected.step) && w.hist.length > 0);
// A merge that needs no Commit (head null) makes a fresh Branch on main's Layer, and a
// later merge with an unknown Commit is a new Commit, not a fast-forward to it (#347 row 51)
const R = new X.ReplayEngine({ project: "p" }), L0 = "a".repeat(64), C1 = "12" + "b".repeat(64);
const end = (method, args, rest) => R.apply({ method, args, ok: true, phase: "end", ...rest });
end("project.init", {}, {});
end("branch.fork", { name: "a", from: "main" }, { branch: "a", base: L0, head: null });
end("branch.merge", { branch: "a", with: "main", name: "b" }, { branch: "b", head: null });
end("branch.merge", { branch: "b", with: "main", name: "c" }, { branch: "c", head: C1, commit: C1 });
end("branch.fork", { name: "d", from: "c" }, { branch: "d", base: L0, head: C1 });
assert.ok(!("null" in R.s.commits), "no Commit without an id");
assert.equal(R.s.branches.b.head, null);
assert.equal(R.s.branches.b.base, R.s.main.head);
assert.equal(R.m.real(R.s.branches.c.head), C1);
assert.equal(R.s.commits[R.s.branches.c.head].via, "merge");
assert.equal(R.s.branches.d.from, R.s.branches.c.head);
console.log(`PASS model trace: ${lines.length} lines, ${s.branchOrder.length} Branches, ${s.sandboxOrder.length} Sandboxes, ${Object.keys(w.attrib).length} attributed nodes`);
