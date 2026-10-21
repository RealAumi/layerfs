// Proof only, after every state is committed: for each committed state,
// fork a Branch from its Commit, mount it, check it against the state's
// oracle, and unmount. One line per state in history.jsonl; start no new
// state after the budget. Prints DONE when every state is checked.
import { append, budget, lfs, rows, SANDBOX, timed, verify } from "./common.mjs";

const began = performance.now();
const checked = new Set(rows("history.jsonl").map((r) => r.state));
const todo = rows("ledger.jsonl").filter((r) => r.commit && !checked.has(r.state));
let count = 0;
for (const r of todo) {
  if (count > 0 && performance.now() - began > budget) break;
  const name = `at-${r.state}`;
  const forked = await lfs.branch.fork(name, r.commit);
  if (forked.head !== r.commit) throw new Error(`fork ${name} head ${forked.head}, expected ${r.commit}`);
  const [path, mountMs] = await timed(() => lfs.sandbox.mount(SANDBOX, name));
  const v = await verify(path, r.state);
  await lfs.sandbox.unmount(SANDBOX, path, true);
  append("history.jsonl", { state: r.state, commit: r.commit, mount_ms: mountMs, verify_ms: v.ms, verify: v.json });
  count++;
}
console.log(count === todo.length ? "DONE" : `MORE ${todo.length - count}`);
await lfs.close();
