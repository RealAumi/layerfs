// Shared by the suite clients: the SDK client (Store policy 16/8/8, as
// dsh-dedup v1.0.0), the run's ledger files, one timed SDK call, one
// sandbox.exec, and a Workspace kept mounted across client processes.
// Every client runs on Linux in the runtime image (common/client.sh) with
// BENCH_HOME, the run folder at its host path, and BENCH_PROJECT.
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { LayerFS } from "../../sdk/js/src/index.js";

export const home = process.env.BENCH_HOME;
export const project = process.env.BENCH_PROJECT;
if (!home || !project) throw new Error("BENCH_HOME and BENCH_PROJECT are required");
export const SANDBOX = "bench";
export const BRANCH = "bench";
export const policy = { wholeFileDepth: 16, chunkDepth: 8, metadataDepth: 8 };

export const lfs = new LayerFS(project, { storePolicy: policy });

export const rows = (name) =>
  existsSync(join(home, name)) ? readFileSync(join(home, name), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
export const append = (name, row) => {
  appendFileSync(join(home, name), JSON.stringify(row) + "\n");
  console.log(JSON.stringify(row).slice(0, 2000));
};

/** One SDK call and its wall time in ms, measured in this client. */
export async function timed(call) {
  const start = performance.now();
  const value = await call();
  return [value, +(performance.now() - start).toFixed(3)];
}

/**
 * One sandbox.exec (bash -c as uid 501 in PATH, HOME=/tmp). Returns the
 * whole result with its client-side wall time; never throws on a non-zero
 * exit, so a suite records failures as results. `keep` caps each stream
 * kept in the result (the SDK itself keeps at most 1 MiB per stream).
 */
export async function exec(path, command, keep = 1 << 20) {
  const [r, ms] = await timed(() => lfs.sandbox.exec(SANDBOX, path, command));
  return { ms, exitCode: r.exitCode, truncated: r.truncated, stdout: r.stdout.slice(0, keep), stderr: r.stderr.slice(0, keep) };
}

/** The mounted Workspace recorded by setup (session.json), or null after unmount. */
export const session = () => (existsSync(join(home, "session.json")) ? JSON.parse(readFileSync(join(home, "session.json"), "utf8")) : null);
export const saveSession = (value) => writeFileSync(join(home, "session.json"), JSON.stringify(value, null, 2) + "\n");

/**
 * Setup: project.init of SEED (timed), sandbox.create on the suite image,
 * the run's own Branch forked from main, sandbox.mount. The mounted path is
 * kept in session.json for later clients; ledger.jsonl gets one setup row.
 */
export async function setup(seed) {
  const [init, initMs] = await timed(() => lfs.project.init(seed));
  const [id, createMs] = await timed(() => lfs.sandbox.create(SANDBOX, project, process.env.LAYERFS_IMAGE));
  const fork = await lfs.branch.fork(BRANCH, "main");
  const [path, mountMs] = await timed(() => lfs.sandbox.mount(id, BRANCH));
  saveSession({ sandbox: id, branch: BRANCH, path });
  append("ledger.jsonl", { step: "setup", init_ms: initMs, init, policy, create_ms: createMs, sandbox: id, fork, path, mount_ms: mountMs });
  return { id, path };
}

/** sandbox.commit of the mounted Workspace (timed), with a ledger row. */
export async function commit(path, message) {
  const [value, ms] = await timed(() => lfs.sandbox.commit(SANDBOX, path, message));
  append("ledger.jsonl", { step: "commit", message, commit_ms: ms, value });
  return value;
}

/** Unmount (terminal) and close the Sandbox, with a ledger row; clears session.json. */
export async function teardown() {
  const s = session();
  let unmountMs = null;
  if (s && s.path) [, unmountMs] = await timed(() => lfs.sandbox.unmount(SANDBOX, s.path, true));
  const [, closeMs] = await timed(() => lfs.sandbox.close(SANDBOX));
  saveSession({ ...(s ?? {}), path: null, closed: true });
  append("ledger.jsonl", { step: "teardown", unmount_ms: unmountMs, close_ms: closeMs });
}
