// One timed fio job in the layerfs or sandbox-disk arm: a measured
// sandbox.exec that runs fio alone (--output-format=json to a file in the
// container's /tmp; wall time taken inside the Sandbox with date +%s%N
// around fio, plus the exec's client-side time), then an untimed exec that
// reads back the VM's memory figures, fio's JSON and log. The read-back goes
// to ops/<job>-<arm>.txt and one row to results.jsonl; report.py parses
// both. The passthrough-fuse arm runs the same commands through pt.mjs.
//
//   job.mjs JOB ARM
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, session } from "../../common/session.mjs";
import { armDir, jobCommand, jobRow, JOBS, readbackCommand, readParams } from "./common.mjs";

const [job, arm] = process.argv.slice(2);
if (!JOBS[job] || !["layerfs", "sandbox-disk"].includes(arm)) throw new Error("usage: job.mjs JOB layerfs|sandbox-disk");
const params = readParams(readFileSync(join(home, "params.env"), "utf8"));
const { path } = session();
const { argv, command } = jobCommand(job, arm, armDir(arm, path), params);

const run = await exec(path, command);
const back = await exec(path, readbackCommand(job, arm));
mkdirSync(join(home, "ops"), { recursive: true });
writeFileSync(join(home, "ops", `${job}-${arm}.txt`), back.stdout + (back.stderr ? `=== stderr\n${back.stderr}` : ""));
append("results.jsonl", jobRow(job, arm, params, argv, run, back));
await lfs.close();
