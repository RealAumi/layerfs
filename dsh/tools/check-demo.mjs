// Checks a finished mock demo session against its scenario, through a
// running dsh web Host's /layerfs route (checks/gates.mjs):
//   expected     every agent of the scenario ran, and each bash step with
//                `expect` produced those LayerFS outcome codes in order on its
//                trace lines (other calls may come between; a retried step may
//                leave earlier attempts). An outcome code is a refusal's code,
//                else the value's kind, else "ok"; an expected entry is a code
//                ("Committed"), method:code ("sandbox.commit:Committed") or
//                alternatives ("sandbox.commit:Committed|UpToDate").
// For a scenario with final.json (a replayed run), also:
//   closed       no container uses the project's volume (every Sandbox of the
//                run is closed, the service Sandbox included, so no Workspace
//                is mounted); the Host releases its own reading Sandbox after a
//                quiet minute, so this waits up to --wait seconds (default 120)
//   order        each Branch's Commits, forks, merges and publishes as recorded
//   final tree   main's tracked files have the recorded SHA-256s
// The last two read the project through a Sandbox of their own, closed after.
//   node dsh/tools/check-demo.mjs '<dsh web URL with ?token=…>' <session id> <scenario> [--wait <s>]
// Exit status 0 when every check holds; each failure is printed.
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { deploymentEnv } from "../packages/host/src/layerfs-client.js";
import { loadScenarios } from "../packages/mock/src/scenario.js";
import { expectedOutcomes, finalTreeFailures, openContainers, orderFailures } from "./checks/gates.mjs";

const [address, sessionId, name] = process.argv.slice(2);
const waitAt = process.argv.indexOf("--wait"), waitS = waitAt > 0 ? Number(process.argv[waitAt + 1]) : 120;
const dir = fileURLToPath(new URL("../scenarios/", import.meta.url));
const scenario = loadScenarios(dir).get(name ?? "");
if (!address || !sessionId || !scenario) {
  console.error("usage: check-demo.mjs '<dsh web URL with ?token=…>' <session id> <scenario> [--wait <s>]");
  process.exit(2);
}

const login = await fetch(address, { redirect: "manual" });
const cookie = login.headers.getSetCookie().map((c) => c.split(";")[0]).join("; ");
const get = async (path) => {
  const res = await fetch(`${new URL(address).origin}/layerfs${path}`, { headers: { cookie } });
  const body = await res.json();
  if (!res.ok) throw new Error(`${res.status} ${body.code}: ${body.message}`);
  return body;
};
const view = await get(`/session/${encodeURIComponent(sessionId)}`);

let failed = false;
const report = (gate, failures, note = "") => {
  for (const failure of failures) console.log(`FAIL ${gate}: ${failure}`);
  if (!failures.length) console.log(`PASS ${gate}${note}`);
  failed ||= failures.length > 0;
};

const finished = view.lines.filter((l) => l.ok !== undefined);
const agentOf = (line) => (line.agentId === view.root ? "root" : view.agents[line.agentId] ?? line.agent);
const expected = expectedOutcomes(scenario, (agent) => finished.filter((l) => agentOf(l) === agent));
for (const note of expected.notes) console.log(note);
report("expected", expected.failures, `: ${scenario.title}, every expected outcome is on the trace`);

const finalFile = `${dir}${name}/final.json`;
if (existsSync(finalFile) && view.project) {
  const final = JSON.parse(readFileSync(finalFile, "utf8"));
  const status = await get("/status");
  const project = view.project;
  console.log(`project ${project.name} · volume ${project.volume} · image ${project.image ?? status.image}`);
  // readiness wait for the Host's own reading Sandbox to be released
  let open = openContainers(project.volume, status.docker);
  for (const until = Date.now() + waitS * 1000; open.length && Date.now() < until; open = openContainers(project.volume, status.docker)) {
    await new Promise((r) => setTimeout(r, 2000));
  }
  report("closed", open.map((c) => `${c} still uses ${project.volume}`), ": no Sandbox of the run is open");

  // the Host's own settings for the project (on macOS, its ported SDK's too)
  const deploy = deploymentEnv(status, project);
  for (const [k, v] of Object.entries(deploy)) process.env[`LAYERFS_${k}`] = v;
  const { LayerFS } = await import(status.sdk);
  const { LayerFSOperator } = await import(status.operator ?? new URL("../operator/index.js", status.sdk).href);
  const creator = new LayerFS(project.name);
  const check = await creator.sandbox.create(`${project.name}-check`.slice(0, 63), project.name, deploy.IMAGE);
  const lf = new LayerFS(project.name, { sandbox: check });
  try {
    report("order", await orderFailures(final, lf, new LayerFSOperator(lf)), ": every Branch's Commits, forks, merges and publishes as recorded");
    const tree = await finalTreeFailures(final, lf, check);
    report("final tree", tree.failures, `: ${tree.files} tracked files on main as recorded (${tree.varies.stamped} by stamped name, ${tree.varies.content} by presence)`);
  } finally {
    await lf.sandbox.close(check);
  }
}
if (failed) process.exit(1);
console.log(`PASS ${scenario.title}`);
