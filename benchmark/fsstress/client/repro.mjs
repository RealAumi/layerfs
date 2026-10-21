// Diagnostic, not a measurement: runs client/repro.sh through sandbox.exec
// in both arms (<Workspace>/repro and /tmp/repro) and appends one
// repro.jsonl row per probe with each arm's exit and output.
import { readFileSync } from "node:fs";
import { append, exec, lfs, session } from "../../common/session.mjs";

const script = readFileSync(new URL("./repro.sh", import.meta.url), "utf8");
const { path } = session();
const results = {};
for (const [arm, dir] of [["layerfs", `${path}/repro`], ["sandbox-disk", "/tmp/repro"]]) {
  const r = await exec(path, `cat >/tmp/repro.sh <<'REPRO_EOF'\n${script}REPRO_EOF\nbash /tmp/repro.sh ${dir}`);
  if (r.exitCode !== 0) throw new Error(`repro.sh in ${arm}: exit ${r.exitCode} ${r.stderr}`);
  for (const line of r.stdout.trim().split("\n")) {
    const [probe, status, ...out] = line.split("|");
    (results[probe] ??= { probe })[arm] = { exit: +status, output: out.join("|") };
  }
}
for (const row of Object.values(results)) append("repro.jsonl", row);
await lfs.close();
