// smallfile setup: project.init of the run's seed folder, sandbox.create on
// the smallfile image, the run's own Branch, sandbox.mount
// (common/session.mjs setup). Then one untimed exec records the image's
// smallfile identity, the kernel and both arms' filesystems, and creates
// each arm's empty top folder.
//
//   setup.mjs SEED_DIR
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, setup } from "../../common/session.mjs";
import { DISK, layerfsTop } from "./common.mjs";

const [seed] = process.argv.slice(2);
const { path } = await setup(seed);
const top = layerfsTop(path);
const probe = await exec(path, [
  "cat /opt/smallfile-identity.txt",
  "echo uname=$(uname -srm)",
  "echo id=$(id -u):$(id -g)",
  "echo nproc=$(nproc)",
  `mkdir ${top} ${DISK}`,
  `stat -f -c 'fs %n type=%T bsize=%s' ${top} ${DISK}`,
  `awk '$2 == "${path}" || $2 == "/" { print $1, $2, $3, ($2 == "/" ? "(options not kept)" : $4) }' /proc/self/mounts`,
].join(" && "));
writeFileSync(join(home, "sandbox-identity.txt"), probe.stdout + probe.stderr);
append("ledger.jsonl", { step: "probe", exit: probe.exitCode, ms: probe.ms, layerfs: top, disk: DISK });
await lfs.close();
if (probe.exitCode !== 0) throw new Error(`probe exit ${probe.exitCode}: ${probe.stderr}`);
