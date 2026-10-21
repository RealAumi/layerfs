// Replayed steps of a recorded run (issue #347): a scenario step's bash `run`
// is ["step", <scenario>, "NNN"], and step() makes the SDK calls of
// scenarios/<scenario>/run/NNN.json in their recorded order:
//   fork, merge, publish          the Branch calls, with the recorded arguments
//   write                         one fs.apply with the recorded Commit's changes
//   create, close                 the agent's own Sandbox
//   mount, exec, commit, unmount  a Workspace in it; exec runs the recorded
//                                 command verbatim ($PWD is the Workspace)
// Each call's outcome must be the recorded one (`expect`; "a|b" allows
// either), and each command's exit code the recorded one. A Commit the record
// has as UpToDate may come back Committed only if it changes no tracked file
// (a tool's own cache, such as cargo's last-use times, is all it holds). A
// command whose recorded failures were only tests that fail by chance (`flaky`)
// may exit 0 or as recorded, and a failure must be the recorded one; a
// process census written for the recorded runtime (`sandboxOwn`) may fail
// only by finding the Sandbox's own processes (import/crew.mjs). A
// verification-only command the scenario disables (`disabled`, with the run
// file's `verification`, "off" or "no-browser") does not run; the step says so. The first call that
// differs ends the step with exit code 1, which stops the demo there: a run
// is never patched up. Nothing waits or retries; order between agents comes
// from the scenario's own waits.
// What later steps need (the agent's Sandbox, its mounted Workspaces by
// their recorded path) is kept under the project's LayerFS home entry,
// which is removed with the project.
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { differenceAt, runIndex } from "../../tools/checks/refs.mjs";

const project = process.env.DSH_LAYERFS_PROJECT;
if (!project) { console.log("no LayerFS project in this conversation"); process.exit(1); }
const { LayerFS } = await import(process.env.DSH_LAYERFS_SDK);

const NOTES = join(process.env.DSH_LAYERFS_HOME, project, "demo-notes");
const note = (key) => { try { return JSON.parse(readFileSync(join(NOTES, `${key}.json`), "utf8")); } catch { return null; } };
function keep(key, value) {
  const file = join(NOTES, `${key}.json`);
  if (value === null) return rmSync(file, { force: true });
  mkdirSync(NOTES, { recursive: true });
  writeFileSync(`${file}.tmp`, JSON.stringify(value));
  renameSync(`${file}.tmp`, file);
}

class Mismatch extends Error {}
const outcome = (value) => (value?.kind ?? "ok");
// create and mount answer only the Sandbox's name or the Workspace's path, and only when Ready or Mounted
const ANSWERED = { "sandbox.create": "Ready", "sandbox.mount": "Mounted" };
// alternatives share what comes before the last ":" ahead of the first "|"
// ("sandbox.exec:exit:1|0" allows exit:1 and exit:0), as check-demo reads them
const allowed = (expect, got) => {
  const bar = expect.indexOf("|"), head = bar < 0 ? expect.indexOf(":") + 1 : expect.lastIndexOf(":", bar) + 1;
  const prefix = expect.slice(expect.indexOf(":") + 1, head);
  return expect.slice(head).split("|").some((kind) => prefix + kind === got);
};
/** Runs one SDK call and checks its outcome against the record. */
async function expectCall(call, method, work) {
  let value, got;
  try { value = await work(); got = method === "sandbox.exec" ? `exit:${value.exitCode}` : ANSWERED[method] ?? outcome(value); } catch (error) {
    if (!error.code) throw error;
    got = error.code;
    value = { refused: error };
  }
  const want = call.expect;
  if (want && !(want.startsWith(`${method}:`) && allowed(want, got))) {
    if (value?.refused) console.log(`✕ ${value.refused.message}`);
    else if (method === "sandbox.exec") console.log(tail(`${value.stdout ?? ""}${value.stderr ?? ""}`));
    throw new Mismatch(`${method} answered ${got}; the record has ${want.slice(method.length + 1)}`);
  }
  return value;
}

const tail = (text, lines = 12) => String(text ?? "").trimEnd().split("\n").slice(-lines).join("\n");
const short = (id) => String(id ?? "").slice(0, 12);

/** A recorded ref ("main", "orders#2", "L3": main's fourth Layer, or a Branch by name) as this run's id. */
async function resolveRef(lf, ref) {
  if (ref === "main" || ref == null) return ref ?? undefined;
  const layer = /^L([0-9]+)$/.exec(ref);
  if (layer) {
    const { LayerFSOperator } = await import(process.env.DSH_LAYERFS_OPERATOR);
    const snap = await new LayerFSOperator(lf).inspect.snapshot();
    // main's Layers from Init's, each the parent of the next
    const byParent = new Map(snap.layers.map((l) => [l.parent ?? null, l]));
    let l = byParent.get(null);
    for (let i = 0; l && i < Number(layer[1]); i++) l = byParent.get(l.id);
    if (!l) throw new Mismatch(`main has no Layer ${layer[1]} yet`);
    return l.id;
  }
  const [, branch, index] = /^(.+)#([0-9]+)$/.exec(ref) ?? [];
  if (!branch) return ref; // a Branch by name: its head now
  const own = await ownCommits(lf, branch);
  const at = runIndex(Number(index), note(commitsKey(branch)) ?? { skipped: [], extra: [] });
  if (at < 0) throw new Mismatch(`${ref} and every Commit before it on ${branch} were not made by this run`);
  if (!own[at]) throw new Mismatch(`${branch} has no Commit ${index} yet`);
  return own[at].id;
}

/** A Branch's own Commits, oldest first (a merged Branch lists its first input's too, up to its fork point). */
async function ownCommits(lf, branch) {
  const items = [];
  for (let pos = 0; ;) { const page = await lf.branch.list_commits(branch, 1000, pos); items.push(...page.items); if (!page.hasMore) break; pos += page.items.length; }
  const b = (await lf.project.list_branches(1000, 0)).items.find((x) => x.name === branch);
  const cut = items.findIndex((c) => c.id === b?.forkedFrom);
  return (cut < 0 ? items : items.slice(0, cut)).reverse();
}

const commitsKey = (branch) => `commits-${encodeURIComponent(branch)}`;

/** Notes that this run's Commits on `branch` differ from the record's: one skipped, or one extra. */
async function noteDifference(lf, branch, kind) {
  const key = commitsKey(branch), d = note(key) ?? { skipped: [], extra: [] };
  d[kind].push(differenceAt(kind, (await ownCommits(lf, branch)).length, d));
  keep(key, d);
}

export async function step(scenario, number) {
  const file = new URL(`../${scenario}/run/${number}.json`, import.meta.url);
  const run = JSON.parse(readFileSync(file, "utf8"));
  const agent = run.agent, boxKey = `sandbox-${agent}`, wsKey = `workspaces-${agent}`;
  const own = note(boxKey);
  // the agent's own Sandbox serves its Store calls once it has one
  let lf = own ? new LayerFS(project, { sandbox: own }) : new LayerFS(project);
  const first = lf;
  const workspaces = note(wsKey) ?? {};
  try {
    for (const call of run.calls) {
      const ws = call.ws ? workspaces[call.ws] : null;
      if (call.ws && call.op !== "mount" && !ws) throw new Mismatch(`no Workspace ${call.ws} is mounted`);
      switch (call.op) {
        case "fork": {
          const from = await resolveRef(lf, call.from);
          await expectCall(call, "branch.fork", () => (from === undefined || from === "main" ? lf.branch.fork(call.name) : lf.branch.fork(call.name, from)));
          console.log(`✓ fork ${call.name} from ${call.from}`);
          break;
        }
        case "merge": {
          const r = await expectCall(call, "branch.merge", () => lf.branch.merge(call.a, call.b, call.name, call.message ?? undefined));
          console.log(`✓ merge ${call.a} + ${call.b} → ${call.name} · ${outcome(r)}`);
          break;
        }
        case "publish": {
          const commit = call.commit ? await resolveRef(lf, call.commit) : undefined;
          const r = await expectCall(call, "branch.publish", () => (commit ? lf.branch.publish(call.branch, commit) : lf.branch.publish(call.branch)));
          console.log(`✓ publish ${call.branch} → main · ${outcome(r)}`);
          break;
        }
        case "write": {
          const r = await expectCall(call, "fs.apply", () => lf.fs.apply(call.branch, call.changes, call.message ?? undefined));
          console.log(`✓ ${call.changes.length} change(s) on ${call.branch} · ${outcome(r)} ${short(r.commit?.id ?? r.head)}`);
          break;
        }
        case "create": {
          // `for`: the lead creates a worker's Sandbox, which the worker then uses and closes
          const owner = call.for ?? agent;
          const name = `${project}-${owner}`.slice(0, 63).replace(/[^a-z0-9]+$/, "");
          const id = await expectCall(call, "sandbox.create", () => lf.sandbox.create(name, project, process.env.DSH_LAYERFS_IMAGE));
          keep(`sandbox-${owner}`, id);
          if (owner === agent) lf = new LayerFS(project, { sandbox: id });
          console.log(`● Sandbox ${name}${owner === agent ? "" : ` for ${owner}`}`);
          break;
        }
        case "close": {
          const id = note(boxKey);
          if (!id) throw new Mismatch("the agent has no Sandbox to close");
          const r = await expectCall(call, "sandbox.close", () => lf.sandbox.close(id));
          if (r?.refused) { console.log(`✓ close refused ${r.refused.code}, as recorded`); break; }
          keep(boxKey, null);
          console.log(`✓ closed ${id}`);
          break;
        }
        case "mount": {
          const id = note(boxKey);
          if (!id) throw new Mismatch("the agent has no Sandbox to mount in");
          const r = await expectCall(call, "sandbox.mount", () => lf.sandbox.mount(id, call.branch));
          if (r?.refused) { console.log(`✓ mount ${call.branch} refused ${r.refused.code}, as recorded`); break; }
          const path = r;
          workspaces[call.ws] = { sandbox: id, path, branch: call.branch };
          keep(wsKey, workspaces);
          console.log(`⟳ mount ${call.branch} → ${path}`);
          break;
        }
        case "exec": {
          if (call.disabled && ["off", "no-browser"].includes(run.verification)) {
            // a verification-only command, disabled for this scenario: nothing runs and nothing stands in for it
            console.log(`verification disabled: ${call.command.slice(0, 120).replace(/\s+/g, " ")}… (recorded exit ${call.exit})`);
            break;
          }
          console.log(`$ ${call.command.length > 300 ? `${call.command.slice(0, 300)}…` : call.command}`);
          const r = await expectCall(call, "sandbox.exec", () => lf.sandbox.exec(ws.sandbox, ws.path, call.command, call.message ?? undefined));
          const out = tail(`${r.stdout ?? ""}${r.stderr ?? ""}`);
          if (out) console.log(out);
          console.log(`[exit ${r.exitCode}] (recorded exit ${call.exit})`);
          if (call.flaky && r.exitCode !== 0) {
            // the record failed only by a race its next step fixed: a failure must be that one
            const text = `${r.stdout ?? ""}${r.stderr ?? ""}`;
            const failed = [...text.matchAll(/^not ok \d+ - (.*)$/gm)].map((m) => m[1].trim());
            // a racing test that passed may let a chained command run that the
            // record never reached; a test the record ran and passed must pass
            const same = call.flaky.tests
              ? failed.length > 0 && failed.every((t) => call.flaky.tests.includes(t) || !(call.flaky.passed ?? []).includes(t))
              : !failed.length && text.includes(`${call.flaky.where}", line`) && call.flaky.errors.some((e) => text.includes(`${e}:`));
            if (!same) throw new Mismatch(`it failed otherwise than the record (${failed.length ? `tests ${failed.filter((t) => !call.flaky.tests?.includes(t)).join(", ") || failed.join(", ")}` : "no test named"})`);
            const unrecorded = call.flaky.tests ? failed.filter((t) => !call.flaky.tests.includes(t)) : [];
            if (unrecorded.length) console.log(`  (failed tests the record never reached: ${unrecorded.join(", ")})`);
          }
          if (call.sandboxOwn && r.exitCode !== 0) {
            // a census written for the recorded runtime: it may find only the Sandbox's own processes
            const line = String(r.stdout ?? "").split("\n").find((l) => l.startsWith("{") && l.includes('"unexpected"'));
            let census = null;
            try { census = line ? JSON.parse(line) : null; } catch { /* not the census line */ }
            const others = census?.unexpected?.filter((p) => !call.sandboxOwn.includes(p.comm)) ?? null;
            if (!census?.unexpected?.length || others.length) throw new Mismatch(`the census found ${others?.length ? `processes other than the Sandbox's own: ${others.map((p) => `${p.pid} ${p.comm}`).join(", ")}` : "no census line"}`);
            console.log(`  (the census found only the Sandbox's own ${census.unexpected.map((p) => p.comm).join(", ")}: the recorded runtime started commands under it, this one beside it)`);
          }
          if (call.flaky) console.log(`  (the recorded exit came from a race only: ${call.flaky.tests?.join(", ") ?? `${call.flaky.errors.join(" or ")} in ${call.flaky.where}`}; this run exited ${r.exitCode})`);
          break;
        }
        case "commit": {
          const r = await expectCall(call, "sandbox.commit", () => lf.sandbox.commit(ws.sandbox, ws.path, call.message ?? undefined, call.force));
          if (call.generated && outcome(r) === "Committed") {
            // the record has UpToDate: this Commit may hold only generated (ignored) files
            const { trackedChanges } = await import("../../tools/checks/tree.mjs");
            let made = null;
            for (let pos = 0; !made; ) {
              const page = await lf.branch.list_commits(ws.branch, 100, pos);
              made = page.items.find((c) => c.id === r.commit?.id) ?? null;
              if (!page.hasMore) break;
              pos += page.items.length;
            }
            if (!made) throw new Mismatch(`the Commit ${short(r.commit?.id)} is not on ${ws.branch}`);
            const changes = await trackedChanges(lf, made);
            if (changes.length) throw new Mismatch(`sandbox.commit answered Committed with ${changes.length} tracked change(s), first ${changes[0].path}; the record has UpToDate`);
            console.log("  (only generated files changed; the record has UpToDate)");
          }
          if (call.generated && outcome(r) === "Committed") await noteDifference(lf, ws.branch, "extra");
          if (call.expect?.endsWith("Committed|UpToDate") && outcome(r) === "UpToDate") await noteDifference(lf, ws.branch, "skipped");
          console.log(`✓ commit · ${outcome(r)} ${r.commit ? short(r.commit.id) : ""}${r.merged ? " · merged with the head" : ""}`);
          break;
        }
        case "unmount": {
          await expectCall(call, "sandbox.unmount", () => lf.sandbox.unmount(ws.sandbox, ws.path, call.discard));
          delete workspaces[call.ws];
          keep(wsKey, Object.keys(workspaces).length ? workspaces : null);
          console.log(`  unmounted ${ws.path}`);
          break;
        }
        default: throw new Error(`unknown call ${call.op}`);
      }
    }
  } catch (error) {
    if (!(error instanceof Mismatch)) throw error;
    console.log(`✕ ${run.step}: ${error.message}`);
    process.exitCode = 1;
  } finally {
    // the converter puts an agent's create before its first Store call, so
    // the service Sandbox is never started here; if it was, that is a fault
    if (!own && first.serviceSandbox) {
      console.log("✕ a call went through the project's service Sandbox");
      process.exitCode = 1;
    }
  }
}
