// Shared by the dsh-dedup clients: the SDK client with Store policy 16/8/8,
// the run's ledger files and one timed SDK call. Every client runs on Linux
// in the runtime image (client.sh) with DSH_HOME, the run folder, at the same
// path as on the host, and DSH_PROJECT.
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { LayerFS } from "../../../sdk/js/src/index.js";

export const home = process.env.DSH_HOME;
export const project = process.env.DSH_PROJECT;
if (!home || !project) throw new Error("DSH_HOME and DSH_PROJECT are required");
export const SANDBOX = "dedup";
export const BRANCH = "dedup";
export const policy = { wholeFileDepth: 16, chunkDepth: 8, metadataDepth: 8 };
/** A segment starts no new state after this many ms (the command's alarm is 115 s). */
export const budget = Number(process.env.DSH_BUDGET_MS ?? 80000);

export const lfs = new LayerFS(project, { storePolicy: policy });
export const selection = JSON.parse(readFileSync(join(home, "selection.json"), "utf8"));

export const rows = (name) =>
  existsSync(join(home, name)) ? readFileSync(join(home, name), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
export const append = (name, row) => {
  appendFileSync(join(home, name), JSON.stringify(row) + "\n");
  console.log(JSON.stringify(row));
};

/** One SDK call and its wall time in ms, measured in this client. */
export async function timed(call) {
  const start = performance.now();
  const value = await call();
  return [value, +(performance.now() - start).toFixed(3)];
}

/** One sandbox.exec; a non-zero exit stops the client after it is logged. */
export async function exec(path, command) {
  const [r, ms] = await timed(() => lfs.sandbox.exec(SANDBOX, path, command));
  const out = { ms, exitCode: r.exitCode, truncated: r.truncated, stdout: r.stdout.trim().slice(0, 4000), stderr: r.stderr.trim().slice(0, 4000) };
  if (r.exitCode !== 0 || r.truncated) {
    append("failures.jsonl", { command, ...out });
    throw new Error(`exec failed: ${command} exit ${r.exitCode}`);
  }
  return { ...out, json: JSON.parse(out.stdout) };
}

export const verify = (path, state) => exec(path, `python3 /corpus/verify.py ${state}`);
