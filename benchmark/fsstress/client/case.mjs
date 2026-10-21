// One fsstress case in one arm: one sandbox.exec of run-case.sh (fsstress
// timed inside the Sandbox), one cases.jsonl row, then each process's
// gzipped verbose log read back into RUN/logs/.
//
//   case.mjs CASE ARM SEED PROCS OPS
// ARM layerfs writes <Workspace>/fss-CASE; sandbox-disk writes /tmp/fss-CASE.
import { append, lfs, session } from "../../common/session.mjs";
import { execJson, readBack } from "./common.mjs";

const [c, arm, seed, procs, ops] = process.argv.slice(2);
const { path } = session();
const dir = arm === "layerfs" ? `${path}/fss-${c}` : `/tmp/fss-${c}`;
const name = `${c}-${arm}`;
const r = await execJson(path, `/opt/fsstress-bench/run-case.sh ${name} ${dir} ${seed} ${procs} ${ops}`);
append("cases.jsonl", { case: c, arm, dir, seed: +seed, procs: +procs, ops: +ops, exec_ms: r.ms, ...r.json });
for (const log of r.json.logs) {
  const got = await readBack(path, `/tmp/fsslog/${log.gz}`, log.gz_bytes, log.gz_sha256, `logs/${log.gz}`);
  append("readback.jsonl", { case: c, arm, file: log.gz, bytes: log.gz_bytes, ...got });
}
await lfs.close();
