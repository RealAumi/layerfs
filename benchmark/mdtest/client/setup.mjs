// mdtest setup: project.init of the run's seed folder, sandbox.create on the
// mdtest image, the run's own Branch, sandbox.mount (common/session.mjs
// setup). Then one untimed exec records the image's mdtest and MPI
// identity, the kernel and both arms' filesystems, and creates each arm's
// empty md folder.
//
//   setup.mjs SEED_DIR
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, setup } from "../../common/session.mjs";
import { DISK, layerfsBase } from "./common.mjs";

const [seed] = process.argv.slice(2);
const { path } = await setup(seed);
const base = layerfsBase(path);
const probe = await exec(path, [
  "cat /opt/mdtest-identity.txt",
  "echo mpirun=$(mpirun --version 2>&1 | head -n 1)",
  "echo uname=$(uname -srm) nproc=$(nproc)",
  "echo id=$(id -u):$(id -g)",
  `mkdir ${base} ${DISK}`,
  `stat -f -c 'fs %n type=%T bsize=%s' ${base} ${DISK}`,
  `awk '$2 == "${path}" || $2 == "/" { print $1, $2, $3, ($2 == "/" ? "(options not kept)" : $4) }' /proc/self/mounts`,
].join(" && "));
writeFileSync(join(home, "sandbox-identity.txt"), probe.stdout + probe.stderr);
append("ledger.jsonl", { step: "probe", exit: probe.exitCode, ms: probe.ms, layerfs: base, disk: DISK });
await lfs.close();
if (probe.exitCode !== 0) throw new Error(`probe exit ${probe.exitCode}: ${probe.stderr}`);
