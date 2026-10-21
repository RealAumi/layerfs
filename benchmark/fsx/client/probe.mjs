// Diagnostic, not a measurement: the exact error text of each fallocate
// mode fsx probes, in both arms, with util-linux fallocate(1) on a 64 KiB
// file (fsx only says "does not support ... disabling!" for ENOSYS or
// EOPNOTSUPP). One line per arm and mode in probe.jsonl.
import { append, exec, lfs, session } from "../../common/session.mjs";
import { armBase } from "./common.mjs";

const modes = {
  "0": "-l 131072", KEEP_SIZE: "-n -o 65536 -l 65536", PUNCH_HOLE: "-p -o 4096 -l 4096",
  ZERO_RANGE: "-z -o 4096 -l 4096", COLLAPSE_RANGE: "-c -o 0 -l 4096", INSERT_RANGE: "-i -o 0 -l 4096",
};
const { path } = session();
for (const arm of ["layerfs", "sandbox-disk"]) {
  const dir = `${armBase(arm, path)}/probe`;
  for (const [mode, flags] of Object.entries(modes)) {
    const command = `mkdir -p ${dir} && cd ${dir} && head -c 65536 /dev/zero >f-${mode} && fallocate ${flags} f-${mode}`;
    const r = await exec(path, command);
    append("probe.jsonl", { arm, mode, command, exit: r.exitCode, stderr: r.stderr.trim() });
  }
}
await lfs.close();
