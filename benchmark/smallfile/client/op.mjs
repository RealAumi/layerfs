// One smallfile operation in one arm: a measured sandbox.exec that runs
// smallfile_cli.py over the arm's top folder (wall time taken inside the
// Sandbox with date +%s%N around smallfile alone, and the exec's
// client-side time), then an untimed exec that reads back smallfile's
// output, its --output-json result and, after a failure, the tail of its
// per-thread logs. The read-back goes to ops/<op>-<arm>.txt and one row to
// results.jsonl; report.py parses both.
//
// --stonewall N --finish Y make every thread process all its files, so
// each operation leaves the complete file set for the next one.
//
//   op.mjs OP ARM THREADS FILES FILE_SIZE_KB
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, session } from "../../common/session.mjs";
import { armTop, OUT, SMALLFILE } from "./common.mjs";

const [op, arm, threads, files, sizeKb] = process.argv.slice(2);
const ops = ["create", "read", "append", "stat", "chmod", "rename", "delete-renamed", "mkdir", "rmdir"];
if (!ops.includes(op) || !["layerfs", "sandbox-disk"].includes(arm) || ![threads, files, sizeKb].every((n) => /^\d+$/.test(n))) {
  throw new Error("usage: op.mjs OP ARM THREADS FILES FILE_SIZE_KB");
}
const { path } = session();
const name = `${op}-${arm}`;
const top = armTop(arm, path);
const out = `${OUT}/${arm}/${op}`;
const argv = [
  "--top", top, "--operation", op, "--threads", threads, "--files", files, "--file-size", sizeKb,
  "--stonewall", "N", "--finish", "Y", "--output-json", `${out}/result.json`,
].join(" ");

const run = await exec(path, [
  `mkdir -p ${out} || exit 90`,
  `l=$(cut -d' ' -f1 /proc/loadavg); s=$(date +%s%N); TMPDIR=${out} ${SMALLFILE} ${argv} >${out}/smallfile.out 2>&1; rc=$?; e=$(date +%s%N)`,
  `echo "rc=$rc ns=$((e - s)) loadavg=$l"`,
].join("\n"));
const m = /rc=(\d+) ns=(\d+) loadavg=([\d.]+)/.exec(run.stdout);
const rc = m ? Number(m[1]) : null;

const back = await exec(path, [
  `cd ${out} || exit 90`,
  "tail -c 200000 smallfile.out",
  "echo '=== result.json'; cat result.json 2>&1",
  rc === 0 ? "true" : "for f in invoke_logs-*.log; do echo \"=== $f tail\"; tail -n 30 \"$f\"; done",
].join("\n"));
mkdirSync(join(home, "ops"), { recursive: true });
writeFileSync(join(home, "ops", `${name}.txt`), back.stdout + (back.stderr ? `=== stderr\n${back.stderr}` : ""));

append("results.jsonl", {
  case: name, op, arm, threads: Number(threads), files_per_thread: Number(files), file_size_kb: Number(sizeKb), argv,
  rc, tool_ns: m ? Number(m[2]) : null, sandbox_loadavg: m ? Number(m[3]) : null, exec_ms: run.ms, exec_exit: run.exitCode,
  exec_stdout: run.stdout.slice(0, 2000), exec_stderr: run.stderr.slice(0, 2000), truncated: run.truncated || back.truncated,
  readback_exit: back.exitCode,
});
await lfs.close();
