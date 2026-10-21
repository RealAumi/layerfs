// The next test group: one sandbox.exec of run-group.sh for the first
// pjdfstest directory with files not yet started in one arm (per directory,
// layerfs first, then sandbox-disk), from plan.json (setup). run-group.sh
// gives each file 100 s, starts quick files for 40 s and a file that sleeps
// only first, and is cut at 105 s, so the exec returns before the client's
// 115 s alarm; deferred files go to the next group. No file runs
// twice in an arm. The TAP goes to tap/<arm>-<dir>-<ms>.tap unchanged;
// groups.jsonl gets the exec's exit, wall time, truncation, stderr and the
// files started and deferred. Prints DONE when every file ran in both arms.
//
//   group.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, rows, session } from "../../common/session.mjs";

const FILE_TIMEOUT_S = 100, START_BUDGET_S = 40, GROUP_TIMEOUT_S = 105;
const ARMS = ["layerfs", "sandbox-disk"];
const plan = JSON.parse(readFileSync(join(home, "plan.json"), "utf8"));
const started = Object.fromEntries(ARMS.map((a) => [a, new Set(rows("groups.jsonl").filter((g) => g.arm === a).flatMap((g) => g.started))]));
let unit = null;
for (const dir of [...new Set(plan.map((f) => f.split("/")[0]))]) {
  for (const arm of ARMS) {
    const files = plan.filter((f) => f.startsWith(`${dir}/`) && !started[arm].has(f));
    if (files.length && !unit) unit = { arm, dir, files };
  }
}
if (!unit) {
  console.log("DONE");
} else {
  const { path } = session();
  const root = { layerfs: path, "sandbox-disk": "/tmp" }[unit.arm];
  const names = unit.files.map((f) => f.split("/")[1]);
  const r = await exec(path, `timeout -k 5 ${GROUP_TIMEOUT_S} /opt/pjd-bench/run-group.sh ${root} ${unit.dir} ${FILE_TIMEOUT_S} ${START_BUDGET_S} ${names.join(" ")}`);
  const tap = `${unit.arm}-${unit.dir}-${Date.now()}.tap`;
  writeFileSync(join(home, "tap", tap), r.stdout);
  const marked = (m) => [...r.stdout.matchAll(new RegExp(`^### ${m} (\\S+)`, "gm"))].map((x) => x[1]);
  append("groups.jsonl", {
    arm: unit.arm, dir: unit.dir, root, ms: r.ms, exitCode: r.exitCode, truncated: r.truncated, tap,
    stdout_bytes: r.stdout.length, stderr: r.stderr, started: marked("begin"), deferred: marked("deferred"),
  });
  if (r.truncated) throw new Error("output truncated");
  if (!marked("begin").length) throw new Error(`group started no file: exit ${r.exitCode} ${r.stderr.slice(0, 500)}`);
}
await lfs.close();
