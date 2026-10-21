// Setup: project.init of the run's one-file seed, sandbox.create on the
// pjdfstest image, the run's Branch, sandbox.mount (common/session.mjs
// setup), then one probe exec that creates both arms' pjd/ roots and records
// the Sandbox user, each arm's filesystem type and the image's pjdfstest;
// a second exec lists the image's test files into plan.json (only the named
// directories', for a smoke run).
//
//   setup.mjs SEED_DIR [DIR ...]
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, setup } from "../../common/session.mjs";

const [seed, ...dirs] = process.argv.slice(2);
const { path } = await setup(seed);
const probe = await exec(path, [
  "set -e; mkdir -p pjd /tmp/pjd",
  "echo id=$(id -u):$(id -g) groups=$(id -G | tr ' ' ,) umask=$(umask) shell=$(readlink -f /bin/sh)",
  "echo layerfs=$(df -PT pjd | awk 'END {print $2}') sandbox-disk=$(df -PT /tmp/pjd | awk 'END {print $2}')",
  "stat -c 'stat %n %u:%g %a' . pjd /tmp/pjd",
  "grep -E 'fuse|workspaces' /proc/mounts || true",
  "echo kernel=$(uname -r) pjdfstest=$(cat /opt/pjdfstest/COMMIT) $(sha256sum /opt/pjdfstest/pjdfstest)",
].join("; "));
append("ledger.jsonl", { step: "probe", ...probe });
if (probe.exitCode !== 0) throw new Error(`probe exit ${probe.exitCode}`);
const list = await exec(path, "cd /opt/pjdfstest/tests && ls -- */*.t");
if (list.exitCode !== 0) throw new Error(`test list exit ${list.exitCode}`);
const plan = list.stdout.split("\n").filter((f) => f && (!dirs.length || dirs.includes(f.split("/")[0])));
writeFileSync(join(home, "plan.json"), JSON.stringify(plan, null, 1) + "\n");
await lfs.close();
