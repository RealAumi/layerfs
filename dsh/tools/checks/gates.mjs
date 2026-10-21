// The checks a finished demo run must pass, shared by check-demo.mjs (a dsh
// web session) and run-scenario.mjs (a headless run):
//   expected     each bash step with `expect` left those LayerFS outcomes, in
//                order, on its agent's trace lines ("a|b" allows either)
//   order        the project's history equals the recorded one (final.json):
//                each Branch's Commits in the recorded order, each fork from
//                and each merge and publish of the recorded node
//   final tree   every tracked file on main has the recorded SHA-256, and no
//                other tracked file exists. final.json's `varies` names what a
//                run cannot reproduce byte for byte: a name's clock reading
//                (`stamp`, matched as a pattern) and files whose format holds
//                the run's clock or an OS-assigned value (`content`, compared
//                by presence); variesOf() decides both from the record
//   closed       no container uses the project's volume: every Sandbox of the
//                run, the service Sandbox included, is closed, so no Workspace
//                is mounted
import { execFileSync } from "node:child_process";
import { compareHistory, historyOf } from "./history.mjs";
import { trackedChanges, trackedHashes } from "./tree.mjs";

// an expected entry is a code ("Committed"), method:code, or alternatives
// sharing one method ("sandbox.commit:Committed|UpToDate")
const matches = (code, want) => {
  const bar = want.indexOf("|");
  if (bar < 0) return code === want || code.endsWith(`:${want}`);
  const head = want.slice(0, want.lastIndexOf(":", bar) + 1);
  return want.slice(head.length).split("|").some((kind) => matches(code, head + kind));
};
/** Whether `want` appears in `codes` in order. */
const inOrder = (codes, want) => { let i = 0; for (const c of codes) if (i < want.length && matches(c, want[i])) i++; return i === want.length; };
export const codeOf = (line) => `${line.method}:${line.ok ? line.kind ?? "ok" : line.code}`;

/**
 * @param {object} scenario compiled scenario
 * @param {(agent: string) => object[]} linesOf the agent's finished trace lines, in order
 * @returns {{ failures: string[], notes: string[] }}
 */
export function expectedOutcomes(scenario, linesOf) {
  const failures = [], notes = [];
  for (const [agent, steps] of Object.entries(scenario.agents)) {
    const groups = [];
    for (const line of linesOf(agent).filter((l) => l.ok !== undefined && l.method !== "sandbox.service")) {
      let group = groups.find((g) => g.step === line.step);
      if (!group) groups.push(group = { step: line.step, codes: [], start: line.start });
      group.codes.push(codeOf(line));
      if (line.start < group.start) group.start = line.start;
    }
    // bash calls in the order they began: a background call's first line may
    // end after a later call's (the lines arrive as their calls end)
    groups.sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
    const expecting = steps.filter((s) => s.kind === "call" && s.call.name === "bash" && s.expect);
    if (expecting.length && !groups.length) { failures.push(`${agent}: no LayerFS calls on the trace`); continue; }
    let next = 0;
    for (const step of expecting) {
      const at = groups.findIndex((g, i) => i >= next && inOrder(g.codes, step.expect));
      if (at < 0) {
        failures.push(`${step.at} (${step.call.args.description}): expected ${step.expect.join(", ")}; ${agent}'s later calls show ${groups.slice(next).map((g) => `[${g.codes.join(", ")}]`).join(" ") || "nothing"}`);
        continue;
      }
      if (at > next && !step.retry) failures.push(`${step.at}: ${at - next} earlier bash call(s) of ${agent} did not match and the step has no retry rule`);
      next = at + 1;
    }
    notes.push(`${agent}: ${groups.length} bash call(s) with LayerFS lines, ${expecting.length} checked`);
  }
  return { failures, notes };
}

/** The order checks: the run's history against final.json's recorded one. */
export async function orderFailures(final, lf, operator) {
  const run = await historyOf(lf, operator), failures = compareHistory(final.history, run);
  // a run's Commit where the record has UpToDate must change no tracked file
  const byRef = new Map([...run.ids].map(([id, ref]) => [ref, id]));
  for (const ref of failures.extras) {
    const changes = await trackedChanges(lf, run.items.get(byRef.get(ref)));
    if (changes.length) failures.push(`${ref} is a Commit where the record has UpToDate, and it changes ${changes.length} tracked path(s), first ${changes[0].path}`);
  }
  return [...failures];
}

/** The patterns `varies` uses: a clock reading in a name, and the formats whose bytes hold run-time values. */
const STAMP = /[0-9]{16,}/g;
const CONTENT = [
  [/\.sqlite$/, "an SQLite database (page headers count writes; rows hold times)"],
  [/\.pyc$/, "CPython bytecode (holds its source's modification time)"],
  [/\/server-[0-9]{16,}\.stdout$/, "a test server's log (holds its OS-assigned port)"],
];

/**
 * What of a recorded final main a run cannot reproduce byte for byte, from
 * the record alone (import-run.mjs writes it to final.json).
 * @returns {{ stamp: string, content: Record<string, string> }}
 */
export function variesOf(main) {
  const content = {};
  for (const path of Object.keys(main)) for (const [pattern, why] of CONTENT) if (pattern.test(path)) content[path] = why;
  return { stamp: STAMP.source, content };
}

/** The final-tree check: main's tracked files against final.json's. */
export async function finalTreeFailures(final, lf, sandbox) {
  const run = await trackedHashes(lf, sandbox), failures = [];
  const varies = final.varies ?? { stamp: null, content: {} };
  const stamp = varies.stamp ? new RegExp(varies.stamp, "g") : null;
  const name = (path) => (stamp ? path.replace(stamp, "<stamp>") : path);
  const exempt = new Set(Object.keys(varies.content).map(name));
  // each file as (name pattern, SHA-256, or "*" when its bytes vary), counted
  const count = (files) => {
    const out = new Map();
    for (const [path, sha] of Object.entries(files)) {
      const key = `${name(path)} ${exempt.has(name(path)) ? "*" : sha}`;
      out.set(key, [...(out.get(key) ?? []), path]);
    }
    return out;
  };
  const [want, got] = [count(final.main), count(run.files)];
  for (const [key, paths] of want) {
    const have = got.get(key)?.length ?? 0;
    if (have >= paths.length) continue;
    const pattern = key.slice(0, key.lastIndexOf(" ")), there = [...got].filter(([k]) => k.startsWith(`${pattern} `)).flatMap(([, p]) => p);
    const recorded = paths.map((p) => final.main[p].slice(0, 12)).join(", ");
    failures.push(there.length ? `${paths[have]} differs: ${there.map((p) => run.files[p].slice(0, 12)).join(", ")}, recorded ${recorded}` : `${paths[have]} is missing from main`);
  }
  for (const [key, paths] of got) {
    const extra = paths.length - (want.get(key)?.length ?? 0);
    if (extra > 0) failures.push(`${paths[paths.length - extra]} (${run.files[paths[0]].slice(0, 12)}) is tracked on main but not in the record`);
  }
  return { failures, files: Object.keys(run.files).length, varies: { stamped: Object.keys(final.main).filter((p) => name(p) !== p).length, content: exempt.size } };
}

/** The closed check: the containers that still use the project's volume. */
export function openContainers(volume, docker = "/var/run/docker.sock") {
  const out = execFileSync("docker", ["-H", `unix://${docker}`, "ps", "-a", "--filter", `volume=${volume}`, "--format", "{{.Names}} {{.State}}"], { encoding: "utf8" });
  return out.split("\n").filter(Boolean);
}
