// One mdtest case in one arm: one sandbox.exec that runs mdtest under
// mpirun in the case's folder (mdtest's own per-phase rates and times, the
// in-Sandbox wall time around mpirun, the Sandbox's 1-minute load), then
// prints mdtest's output. The output goes to cases/<case>-<arm>.txt and one
// row to results.jsonl; report.py parses both.
//
//   case.mjs CASE ARM PROCS ITEMS [MDTEST_ARG...]
// The folder is <arm base>/CASE; the commit pass's -C and -r cases share
// <arm base>/commit, so the removal finds what the create left.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, session } from "../../common/session.mjs";
import { armBase } from "./common.mjs";

const MPIRUN = "mpirun --oversubscribe --bind-to none";

const [name, arm, procs, items, ...args] = process.argv.slice(2);
if (!["layerfs", "sandbox-disk"].includes(arm) || !/^\d+$/.test(procs) || !/^\d+$/.test(items)) {
  throw new Error("usage: case.mjs CASE ARM PROCS ITEMS [MDTEST_ARG...]");
}
const { path } = session();
const dir = `${armBase(arm, path)}/${name.startsWith("commit-") ? "commit" : name}`;
const argv = ["-P", "-i", "1", "-n", items, ...args, "-d", dir].join(" ");
const log = `/tmp/mdlog/${name}-${arm}.txt`;

const run = await exec(path, [
  `mkdir -p /tmp/mdlog ${dir} || exit 90`,
  "l=$(cut -d' ' -f1 /proc/loadavg)",
  `s=$(date +%s%N); ${MPIRUN} -np ${procs} mdtest ${argv} >${log} 2>&1; rc=$?; e=$(date +%s%N)`,
  `echo "rc=$rc ns=$((e - s)) vmload=$l"`,
  `cat ${log}`,
].join("\n"));
const m = /rc=(\d+) ns=(\d+) vmload=([\d.]+)/.exec(run.stdout);
mkdirSync(join(home, "cases"), { recursive: true });
writeFileSync(join(home, "cases", `${name}-${arm}.txt`), run.stdout + (run.stderr ? `=== stderr\n${run.stderr}` : ""));

append("results.jsonl", {
  case: name, arm, procs: Number(procs), items_per_proc: Number(items), args: args.join(" "),
  command: `${MPIRUN} -np ${procs} mdtest ${argv}`, rc: m ? Number(m[1]) : null, tool_ns: m ? Number(m[2]) : null,
  vm_load: m ? Number(m[3]) : null, exec_ms: run.ms, exec_exit: run.exitCode, truncated: run.truncated,
  exec_stderr: run.stderr.slice(0, 2000),
});
await lfs.close();
