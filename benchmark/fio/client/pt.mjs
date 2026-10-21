// The passthrough-fuse arm: the same fio commands as layout.mjs, job.mjs and
// drop.mjs (common.mjs), each run in /tmp/pt/fio of the sibling container
// through common/passthrough.sh bench_pt_exec (docker exec as 501:20,
// HOME=/tmp, 115 s alarm). This arm is not LayerFS and makes no SDK call, so
// this client runs on the host with plain node, not in the runtime image.
// Rows go to the same receipts as the other arms (layout.jsonl,
// results.jsonl, drop.jsonl, ops/) and report.py parses them the same way;
// exec_ms here is the host-side time of the docker exec.
//
//   pt.mjs probe RUN          make the fio folder; kernel, memory, filesystem -> RUN/pt-identity.txt
//   pt.mjs layout RUN         untimed layout of the three files
//   pt.mjs job JOB RUN        one timed job, then its read-back
//   pt.mjs drop FILE RUN      untimed removal of one data file
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { appendRow, dropCommand, FILES, jobCommand, jobRow, JOBS, layoutCommand, PT, readbackCommand, readParams } from "./common.mjs";

const ARM = "passthrough-fuse";
const common = join(dirname(fileURLToPath(import.meta.url)), "../../common");
const [mode, ...rest] = process.argv.slice(2);
const home = rest.at(-1);
if (!home || !home.startsWith("/")) throw new Error("usage: pt.mjs probe|layout|job JOB|drop FILE RUN");

/** One command through bench_pt_exec; never throws on a non-zero exit. */
function ptExec(command) {
  const start = performance.now();
  const r = spawnSync("bash", ["-c", 'suite=fio; . "$1/lib.sh"; . "$1/passthrough.sh"; bench_pt_exec "$2" "$3"', "pt-exec", common, home, command],
    { encoding: "utf8", maxBuffer: 64 << 20 });
  const ms = +(performance.now() - start).toFixed(3);
  return { ms, exitCode: r.status ?? -1, signal: r.signal, truncated: false, stdout: r.stdout ?? "", stderr: (r.stderr ?? "") + (r.error ? `\n${r.error}` : "") };
}

const ops = (name, r) => {
  mkdirSync(join(home, "ops"), { recursive: true });
  writeFileSync(join(home, "ops", name), r.stdout + (r.stderr ? `=== stderr\n${r.stderr}` : ""));
};
const params = () => readParams(readFileSync(join(home, "params.env"), "utf8"));

if (mode === "probe") {
  const r = ptExec([
    "cat /opt/fio-identity.txt", "echo uname=$(uname -srm)", "echo id=$(id -u):$(id -g)", "echo nproc=$(nproc)",
    "grep -E '^(MemTotal|MemAvailable|Cached):' /proc/meminfo", `mkdir ${PT}`, `stat -f -c 'fs %n type=%T bsize=%s' ${PT} /tmp`,
    "awk '$2 == \"/tmp/pt\" || $2 == \"/\" { print $1, $2, $3, ($2 == \"/\" ? \"(options not kept)\" : $4) }' /proc/self/mounts",
  ].join(" && "));
  writeFileSync(join(home, "pt-identity.txt"), r.stdout + r.stderr);
  appendRow(home, "ledger.jsonl", { step: "pt-probe", exit: r.exitCode, ms: r.ms, dir: PT });
  if (r.exitCode !== 0) throw new Error(`pt probe exit ${r.exitCode}: ${r.stderr}`);
} else if (mode === "layout") {
  const { fio, command } = layoutCommand(ARM, PT, params());
  const r = ptExec(command);
  const m = /rc=(\d+) ns=(\d+)/.exec(r.stdout);
  ops(`layout-${ARM}.txt`, r);
  appendRow(home, "layout.jsonl", { arm: ARM, rc: m ? Number(m[1]) : null, ns: m ? Number(m[2]) : null, exec_ms: r.ms, exec_exit: r.exitCode, fio });
  if (!m || m[1] !== "0") throw new Error(`layout ${ARM} failed: ${r.stdout.slice(-2000)} ${r.stderr.slice(-2000)}`);
} else if (mode === "job" && JOBS[rest[0]]) {
  const job = rest[0];
  const p = params();
  const { argv, command } = jobCommand(job, ARM, PT, p);
  const run = ptExec(command);
  const back = ptExec(readbackCommand(job, ARM));
  ops(`${job}-${ARM}.txt`, back);
  appendRow(home, "results.jsonl", jobRow(job, ARM, p, argv, run, back));
} else if (mode === "drop" && FILES[rest[0]]) {
  const r = ptExec(dropCommand(PT, rest[0]));
  ops(`drop-${rest[0]}-${ARM}.txt`, r);
  appendRow(home, "drop.jsonl", { file: rest[0], arm: ARM, exec_ms: r.ms, exec_exit: r.exitCode });
  if (r.exitCode !== 0) throw new Error(`drop ${rest[0]} ${ARM} failed: ${r.stdout.slice(-2000)} ${r.stderr.slice(-2000)}`);
} else {
  throw new Error("usage: pt.mjs probe|layout|job JOB|drop FILE RUN");
}
