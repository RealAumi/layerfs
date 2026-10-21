// Issue #340's record format (Crew, Builder 2 r3): one SDK trace per agent
// (trace/<agent>.jsonl, trace.mjs's format) and each agent's call records
// (agents/<agent>/out/calls/*.json). The 19 recorded agents play as 6 roles,
// one dsh agent each: lead → root; P1… → people; W1… → work-a; W2… → work-b;
// I1… → insight-a; I2… → insight-b. A role's agents ran one after another, so
// its steps keep their recorded order. The observer (main) only read and is
// left out.
//
// The lead created each worker's Sandbox (one at a time: a create while
// another holds the project's lock is refused Busy); a create's Sandbox id is
// in the lead's call record (`created`).
//
// The trace shortens a long command to 200 characters and "…", or keeps only
// its size and SHA-256 (commandPayload). The whole command is the one in the
// agent's call record of that call: the step label's n-th sandbox.exec record
// in sequence order for its n-th exec (a record's start is taken a few
// milliseconds before the trace's). It must have the trace's SHA-256, or start
// with the trace's text. The lead's records keep only a command's SHA-256: its
// scripts/control.mjs wrapped an inner command kept in a file of its folder
// (`timeout 110 bash -c '<CREW_* variables>; <inner>'`), so the lead's command
// is rebuilt from each of those files in turn and taken when the SHA-256 is
// the trace's.
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join } from "node:path";
import { readTrace } from "./trace.mjs";

/**
 * Tests that pass or fail by chance in the builders' application, each run 12
 * or more times in its replayed Workspace (BUGS.md rows 25, 29–35 and 37–39),
 * from `from` (if given) until the step whose change fixed it (`until`, if one
 * did). A recorded command in
 * which such a test ran (its output lists it ok or not ok) may exit 0 or 1
 * unless the record's other failures decide its exit, and a failure must not
 * fail a test the record ran and passed, other than such tests (replay.mjs
 * checks). A racing test that passes this time may let a command chained
 * after it run, which the record never reached: its tests have no recorded
 * outcome (W2b-070 then fails the CLI tests the builders broke at W2b-050). The
 * tests work in temporary folders, so a failure leaves every Workspace as a
 * pass does, and the final tree is checked anyway.
 *   - rank exhaustion: orders equal-rank issues by random ids (failed 5 of 12);
 *     W2-0061 made its fixture deterministic;
 *   - signed credentials: a tampered signature ending "zz" still decodes to
 *     the same bytes about once in 1,024 tokens (passed 60 of 60); P1c-008
 *     rejects non-canonical endings;
 *   - deleted relation activity: depended on random issue ids (failed 20 of
 *     30); W1b-105 includes both endpoints;
 *   - planning browser: waits time out (line 75, failed 1 of 12 at W1b-157's
 *     state) or read a re-rendered element (line 106, failed 6 of 12 at
 *     W2b-066's state); no later step fixed it;
 *   - hierarchy browser: focus on an asynchronously appended child (line 28,
 *     failed 5 of 12 at W1c-031's state); W1c-038 waits for it;
 *   - shell browser: read an element the page re-rendered (lines 49 and 52,
 *     failed 2 of 12 at lead-298's state); lead-301 changed its readiness;
 *   - search browser: from I1-139 (the step after its last fix) the record
 *     passes it 33 times in 4 to 7.6 s and fails it once, lead-309, by a
 *     timeout after 11.2 s, while every agent ran browsers; it passed 24 of 24
 *     times at lead-309's state here, alone, in the full suite and under two
 *     parallel suites (up to 9.5 s), so it races only under load (`from`).
 */
const RACES = [
  { test: "rank exhaustion rebalances destination atomically and preserves order", until: "W2-0061" },
  { test: "signed credentials are purpose bound and reject tampering or changed secret", until: "P1c-008" },
  { test: "deleted relation activity still checks both endpoint grants before filters and cursors", until: "W1b-105" },
  { test: "pinned browser planning planning preserves resource lifecycle" },
  { test: "actual pinned browser authenticates deep links protects abandoned forms and recovers a failed session check", until: "lead-301" },
  { test: "actual pinned browser uses keyboard query completions safe results saved-filter form and live pause", from: "I1-139" },
  { test: "pinned hierarchy browser explores keyboard depth later pages and delayed resource switches", until: "W1c-038" },
];
/**
 * Commands of a browser proof that is not a node test: they may exit 0 or 1,
 * and a failure must be one of `errors` raised in `where`, with no test
 * failing. scripts/people-browser.py looked up elements while the page
 * re-rendered: a stale table row (line 37, P1b-0118's recorded failure) or a
 * missing button after a save (line 57/58), in 13 of 16 runs at P1b-0118's
 * state and 9 of 12 at P1b-0123's (recorded exit 0). P1b-0121 made its waits
 * ignore stale elements, which does not cover the button lookup.
 */
const PROOF_RACES = [
  { step: /^P1b-01(18|23) /, errors: ["selenium.common.exceptions.StaleElementReferenceException", "selenium.common.exceptions.NoSuchElementException"], where: "scripts/people-browser.py" },
];
/**
 * Process censuses written for the recorded runtime, which started a
 * command under the Sandbox's daemon: P1f-045 counts every live process that
 * is not the command's ancestor (nor pid 1) as left over. The current
 * runtime starts a command beside the daemon (the daemon supervises no
 * commands), so the census also finds the daemon. Such a command may exit 0
 * or 1, and a failure must list only the Sandbox's own processes (`own`) as
 * unexpected (replay.mjs reads the census's JSON line).
 */
const SANDBOX_CENSUSES = [{ step: /^P1f-045 /, own: ["layerfs-daemon"] }];
/** The names of the tests a node --test run reports passed or failed. */
const ranTests = (output) => [...String(output).matchAll(/^(?:not )?ok \d+ - (.*)$/gm)].map((m) => m[1].trim());

/**
 * Whether a recorded command belongs to a browser proof (`verification=no-browser`):
 * it names a browser (a browser script, proof, flag or the proof's data), or
 * its recorded output shows Selenium or a test named for a browser. A command
 * that reads a proof's data needs the proof to have run (W2-0100 logs in to
 * W2-0096's server), and the bytecode a script's py_compile leaves is removed
 * only by its proof (P1b-0110), so both go with the proof.
 */
export const drivesBrowser = (command, output) =>
  /browser|selenium/i.test(String(command)) ||
  /selenium|chromedriver|^(?:not )?ok \d+ - .*\bbrowser\b/im.test(String(output));

/** Whether `output` fails with one of the race's errors, raised in its file, and no test. */
export const raceError = (output, { errors, where }) => !failedTests(output).length && output.includes(`${where}", line`) && errors.some((e) => output.includes(`${e}:`));
/** The names of the tests a node --test run reports failed. */
export const failedTests = (output) => [...String(output).matchAll(/^not ok \d+ - (.*)$/gm)].map((m) => m[1].trim());

export const ROLES = { lead: "root", P1: "people", W1: "work-a", W2: "work-b", I1: "insight-a", I2: "insight-b" };
const roleOf = (agent) => ROLES[agent] ?? ROLES[agent.slice(0, 2)] ?? null;

/** An agent's mounted Workspaces by path, from its sandbox.mount records: { branch, workspace }. */
function mountsOf(dir) {
  const out = new Map();
  for (const name of readdirSync(dir).filter((f) => f.endsWith(".json"))) {
    const r = JSON.parse(readFileSync(join(dir, name), "utf8"));
    if (r.method === "sandbox.mount" && r.result?.path) out.set(r.result.path, { branch: r.result.branch, workspace: r.result.workspace });
  }
  return out;
}

/** An agent's sandbox.exec records by step label, in sequence order: each one's command and result. */
function execRecords(dir, method = "sandbox.exec") {
  const out = new Map();
  const records = readdirSync(dir).filter((f) => f.endsWith(".json")).map((name) => JSON.parse(readFileSync(join(dir, name), "utf8")));
  for (const r of records.filter((x) => x.method === method).sort((a, b) => a.sequence - b.sequence)) {
    // the agents wrote three record shapes: inputs or input (positional), or args (by name)
    const inputs = r.inputs ?? r.input ?? r.args;
    const command = Array.isArray(inputs) ? inputs[2] : inputs?.command;
    out.set(r.traceStep ?? r.step, [...(out.get(r.traceStep ?? r.step) ?? []), { command, result: r.result }]);
  }
  return out;
}

const quote = (text) => `'${text.replaceAll("'", `'"'"'`)}'`;
const sha256 = (text) => createHash("sha256").update(text).digest("hex");

/** Every text file in the lead's folder (not its call records): the inner commands it ran. */
function leadFiles(dir) {
  const out = [];
  const walk = (d) => {
    for (const name of readdirSync(d)) {
      const path = join(d, name);
      if (statSync(path).isDirectory()) { if (path !== join(dir, "out", "calls")) walk(path); continue; }
      const text = readFileSync(path, "utf8");
      if (!text.includes("\uFFFD")) out.push(text, text.replace(/\n+$/, ""));
    }
  };
  walk(dir);
  return out;
}

/** The lead's command for one exec, rebuilt as control.mjs built it, whose SHA-256 is `want`. */
function leadCommand(files, { branch, workspace }, label, want) {
  for (const inner of files) {
    const env = `export CREW_AGENT=lead CREW_LANE=${quote(branch)} CREW_WORKSPACE=${quote(workspace)} CREW_INSTALL_TRACE_STEP=${quote(label)}; `;
    const command = `timeout 110 bash -c ${quote(env + inner)}`;
    if (sha256(command) === want) return command;
  }
  return null;
}

/**
 * @param {{ traces: string, agents: string }} inputs the trace folder and the agents folder
 * @returns {{ steps: { label: string, agent: string, origin: string, calls: object[] }[] }}
 */
export function readCrew({ traces, agents }) {
  const steps = [];
  for (const file of readdirSync(traces).filter((f) => f.endsWith(".jsonl")).sort()) {
    const origin = basename(file, ".jsonl"), agent = roleOf(origin);
    if (!agent) continue; // the observer
    const records = execRecords(join(agents, origin, "out", "calls"));
    // the lead created each worker's Sandbox: which one each create made
    const creates = execRecords(join(agents, origin, "out", "calls"), "sandbox.create");
    let lead = null; // the lead's files and its Workspaces by path, read when first needed
    const leadOf = () => (lead ??= { files: leadFiles(join(agents, origin)), mounts: mountsOf(join(agents, origin, "out", "calls")) });
    for (const step of readTrace(join(traces, file))) {
      for (const [n, call] of step.calls.filter((c) => c.method === "sandbox.exec").entries()) {
        const record = records.get(step.label)?.[n];
        const short = call.args.command, payload = call.args.commandPayload;
        if (typeof short === "string" && !short.endsWith("…")) {
          call.command = short;
        } else {
          let command = typeof record?.command === "string" ? record.command : null;
          // the SHA-256 the trace or the record keeps of the whole command
          const want = payload?.sha256 ?? record?.command?.sha256 ?? null;
          if (!command && origin === "lead" && want) {
            const ws = leadOf().mounts.get(call.args.path);
            command = ws ? leadCommand(leadOf().files, ws, step.label, want) : null;
          }
          if (!command) throw new Error(`${origin} ${step.label}: no call record holds the whole command`);
          if (want && sha256(command) !== want) throw new Error(`${origin} ${step.label}: the whole command does not have the recorded SHA-256`);
          if (typeof short === "string" && !command.startsWith(short.slice(0, -1))) throw new Error(`${origin} ${step.label}: the call record's command does not start with the trace's`);
          call.command = command;
        }
        call.output = record ? `${record.result?.stdout ?? ""}${record.result?.stderr ?? ""}` : "";
        call.exitCode = record?.result?.exitCode ?? null;
        if (drivesBrowser(call.command, call.output)) call.browser = true;
        const census = SANDBOX_CENSUSES.find((f) => f.step.test(step.label));
        if (census) {
          if (!/"unexpected"/.test(call.command) || call.exitCode !== 0) throw new Error(`${origin} ${step.label}: the record is not a passing census of unexpected processes`);
          call.sandboxOwn = census.own;
        }
        const proof = PROOF_RACES.find((f) => f.step.test(step.label));
        if (proof) {
          if (call.exitCode !== 0 && !raceError(call.output, proof)) throw new Error(`${origin} ${step.label}: the record does not fail with ${proof.errors.join(" or ")} in ${proof.where}`);
          call.flaky = { errors: proof.errors, where: proof.where };
        }
      }
      for (const [n, call] of step.calls.filter((c) => c.method === "sandbox.create" && c.ok).entries()) {
        const result = creates.get(step.label)?.[n]?.result;
        call.created = typeof result === "string" ? result : result?.id ?? result?.sandbox ?? null;
      }
      steps.push({ ...step, agent, origin });
    }
  }
  steps.sort((a, b) => a.calls[0].start - b.calls[0].start);
  markRaces(steps);
  return { steps };
}

/** Marks each command in which a racing test ran while it raced (RACES). */
function markRaces(steps) {
  const indexOf = (label) => {
    const at = steps.findIndex((s) => s.label.startsWith(`${label} `));
    if (at < 0) throw new Error(`${label}, named in RACES, is not a step`);
    return at;
  };
  const fixedAt = new Map(RACES.filter((r) => r.until).map((r) => [r.test, indexOf(r.until)]));
  const fromAt = new Map(RACES.filter((r) => r.from).map((r) => [r.test, indexOf(r.from)]));
  steps.forEach((step, i) => {
    for (const call of step.calls.filter((c) => c.method === "sandbox.exec" && c.output && !c.flaky)) {
      const racing = RACES.filter((r) => i >= (fromAt.get(r.test) ?? 0) && i < (fixedAt.get(r.test) ?? Infinity) && ranTests(call.output).includes(r.test)).map((r) => r.test);
      if (!racing.length) continue;
      const failed = failedTests(call.output);
      // the record's other failures decide its exit: nothing to allow
      if (failed.some((t) => !racing.includes(t))) continue;
      if (call.exitCode !== 0 && !failed.length) continue;
      // passed: what the record ran and passed, which must pass again
      call.flaky = { tests: [...new Set([...racing, ...failed])], passed: ranTests(call.output).filter((t) => !racing.includes(t) && !failed.includes(t)) };
    }
  });
}
