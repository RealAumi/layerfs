// Setup: project.init of state 1 (timed as Init), sandbox.create on the
// dsh-dedup image (installs the Store), the run's own Branch forked from main,
// then a mount to check state 1 against its oracle, and unmount.
//
//   setup.mjs STATE1_DIR
import { append, BRANCH, exec, lfs, policy, project, SANDBOX, selection, timed, verify } from "./common.mjs";

const [state1] = process.argv.slice(2);
if (selection[0] !== 1) throw new Error("a selection starts at state 1");
const [init, initMs] = await timed(() => lfs.project.init(state1));
const id = await lfs.sandbox.create(SANDBOX, project, process.env.LAYERFS_IMAGE);
const forked = await lfs.branch.fork(BRANCH, "main");
const [path, mountMs] = await timed(() => lfs.sandbox.mount(id, BRANCH));
const checked = await verify(path, 1);
const [, unmountMs] = await timed(() => lfs.sandbox.unmount(id, path, true));
append("ledger.jsonl", {
  state: 1, init_ms: initMs, init, policy, sandbox: id, fork: forked,
  mount_ms: mountMs, verify_ms: checked.ms, verify: checked.json, unmount_ms: unmountMs,
});
await lfs.close();
