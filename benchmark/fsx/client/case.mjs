// One fsx case in one arm: a measured sandbox.exec that runs fsx in a new
// folder (wall time taken inside the Sandbox around fsx alone, and the
// exec's client-side time), then an untimed exec that reads back fsx's
// output, the .fsxlog tail and, after a failure, the first differing bytes
// against .fsxgood and its tail. The read-back goes to cases/<case>.txt
// and one row to results.jsonl; report.py parses both.
//
//   case.mjs VARIANT SEED ARM OPS [FSX_ARG...]
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, session } from "../../common/session.mjs";
import { armBase } from "./common.mjs";

const [variant, seed, arm, ops, ...args] = process.argv.slice(2);
if (!["layerfs", "sandbox-disk"].includes(arm) || !/^\d+$/.test(seed) || !/^\d+$/.test(ops)) {
  throw new Error("usage: case.mjs VARIANT SEED ARM OPS [FSX_ARG...]");
}
const { path } = session();
const name = `${variant}-s${seed}-${arm}`;
const dir = `${armBase(arm, path)}/${variant}-s${seed}`;
const argv = ["-N", ops, "-S", seed, ...args, "-P", dir, `${dir}/f`].join(" ");

const run = await exec(path, [
  `mkdir ${dir} && cd ${dir} || exit 90`,
  `s=$(date +%s%N); fsx ${argv} >fsx.out 2>&1; rc=$?; e=$(date +%s%N)`,
  `echo "rc=$rc ns=$((e - s))"`,
].join("\n"));
const m = /rc=(\d+) ns=(\d+)/.exec(run.stdout);
const rc = m ? Number(m[1]) : null;

const back = await exec(path, [
  `cd ${dir} || exit 90`,
  `n=$(stat -c %s fsx.out); if [ "$n" -le 800000 ]; then cat fsx.out; else head -c 300000 fsx.out; echo "[... fsx.out is $n bytes; middle not kept ...]"; tail -c 300000 fsx.out; fi`,
  "echo '=== f.fsxlog tail'; tail -n 40 f.fsxlog",
  "echo '=== ls'; ls -l --time-style=+%s .",
  rc === 0 ? "true" : "echo '=== cmp -l f f.fsxgood'; cmp -l f f.fsxgood 2>&1 | head -n 20; echo '=== f.fsxgood tail'; tail -c 256 f.fsxgood | od -A d -t x1 | tail -n 17",
].join("\n"));
mkdirSync(join(home, "cases"), { recursive: true });
writeFileSync(join(home, "cases", `${name}.txt`), back.stdout + (back.stderr ? `=== stderr\n${back.stderr}` : ""));

append("results.jsonl", {
  case: name, variant, seed: Number(seed), arm, ops_requested: Number(ops), args: args.join(" "), argv,
  rc, tool_ns: m ? Number(m[2]) : null, exec_ms: run.ms, exec_exit: run.exitCode, exec_stdout: run.stdout.slice(0, 2000),
  exec_stderr: run.stderr.slice(0, 2000), truncated: run.truncated || back.truncated, readback_exit: back.exitCode,
});
await lfs.close();
