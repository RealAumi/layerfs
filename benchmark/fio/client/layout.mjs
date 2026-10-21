// Untimed layout of the layerfs or sandbox-disk arm's three data files
// before any timed job: one sandbox.exec runs fio's own layout phase for
// seq, rand and sync (common.mjs layoutCommand), then lists the files and
// the VM's memory figures. Its wall time is recorded for information only.
// One row goes to layout.jsonl and fio's output to ops/layout-<arm>.txt.
//
//   layout.mjs ARM
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, session } from "../../common/session.mjs";
import { armDir, layoutCommand, readParams } from "./common.mjs";

const [arm] = process.argv.slice(2);
if (!["layerfs", "sandbox-disk"].includes(arm)) throw new Error("usage: layout.mjs layerfs|sandbox-disk");
const params = readParams(readFileSync(join(home, "params.env"), "utf8"));
const { path } = session();
const { fio, command } = layoutCommand(arm, armDir(arm, path), params);
const run = await exec(path, command);
const m = /rc=(\d+) ns=(\d+)/.exec(run.stdout);
mkdirSync(join(home, "ops"), { recursive: true });
writeFileSync(join(home, "ops", `layout-${arm}.txt`), run.stdout + (run.stderr ? `=== stderr\n${run.stderr}` : ""));
append("layout.jsonl", { arm, rc: m ? Number(m[1]) : null, ns: m ? Number(m[2]) : null, exec_ms: run.ms, exec_exit: run.exitCode, fio });
await lfs.close();
if (!m || m[1] !== "0") throw new Error(`layout ${arm} failed: ${run.stdout.slice(-2000)} ${run.stderr.slice(-2000)}`);
