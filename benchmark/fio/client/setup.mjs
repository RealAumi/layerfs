// fio setup: project.init of the run's seed folder, sandbox.create on the
// fio image, the run's own Branch, sandbox.mount (common/session.mjs setup).
// Then one untimed exec records the image's fio identity, the kernel, the
// Sandbox's memory and both arms' filesystems, and creates each arm's empty
// fio folder.
//
//   setup.mjs SEED_DIR
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, setup } from "../../common/session.mjs";
import { DISK, layerfsDir } from "./common.mjs";

const [seed] = process.argv.slice(2);
const { path } = await setup(seed);
const dir = layerfsDir(path);
const probe = await exec(path, [
  "cat /opt/fio-identity.txt",
  "echo uname=$(uname -srm)",
  "echo id=$(id -u):$(id -g)",
  "echo nproc=$(nproc)",
  "grep -E '^(MemTotal|MemAvailable|Cached):' /proc/meminfo",
  `mkdir ${dir} ${DISK}`,
  `stat -f -c 'fs %n type=%T bsize=%s' ${dir} ${DISK}`,
  `awk '$2 == "${path}" || $2 == "/" { print $1, $2, $3, ($2 == "/" ? "(options not kept)" : $4) }' /proc/self/mounts`,
].join(" && "));
writeFileSync(join(home, "sandbox-identity.txt"), probe.stdout + probe.stderr);
append("ledger.jsonl", { step: "probe", exit: probe.exitCode, ms: probe.ms, layerfs: dir, disk: DISK });
await lfs.close();
if (probe.exitCode !== 0) throw new Error(`probe exit ${probe.exitCode}: ${probe.stderr}`);
