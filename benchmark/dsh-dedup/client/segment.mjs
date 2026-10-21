// One segment: mount the run's Branch, then for each next selected state
// apply it in place (sandbox.exec, timed as apply), check it against its
// oracle (sandbox.exec, untimed) and Commit it (sandbox.commit, timed as
// Commit), one ledger line per state; start no new state after the budget;
// unmount. Prints DONE when every selected state is committed.
import { append, BRANCH, budget, exec, lfs, rows, SANDBOX, selection, timed, verify } from "./common.mjs";

const began = performance.now();
const ledger = rows("ledger.jsonl");
const done = new Set(ledger.map((r) => r.state));
const next = selection.filter((s) => !done.has(s));
if (next.length === 0) {
  console.log("DONE");
  process.exit(0);
}
const segment = rows("segments.jsonl").length + 1;
const [path, mountMs] = await timed(() => lfs.sandbox.mount(SANDBOX, BRANCH));
let previous = selection[selection.indexOf(next[0]) - 1];
const states = [];
for (const state of next) {
  if (states.length > 0 && performance.now() - began > budget) break;
  const applied = await exec(path, `python3 /corpus/apply.py ${previous} ${state}`);
  const checked = await verify(path, state);
  const [c, commitMs] = await timed(() => lfs.sandbox.commit(SANDBOX, path, `dsh state ${state}`));
  const record = c.commit ?? {};
  append("ledger.jsonl", {
    state, from: previous, segment, apply_ms: applied.ms, apply: applied.json,
    verify_ms: checked.ms, verify: checked.json, commit_ms: commitMs, kind: c.kind,
    commit: record.id ?? null, parent: record.parent ?? null,
    logical: record.logical, newCanonical: record.newCanonical, newStored: record.newStored, newMetadata: record.newMetadata,
  });
  states.push(state);
  previous = state;
}
const [, unmountMs] = await timed(() => lfs.sandbox.unmount(SANDBOX, path, true));
append("segments.jsonl", { segment, path, mount_ms: mountMs, unmount_ms: unmountMs, states, wall_ms: +(performance.now() - began).toFixed(1) });
console.log(states.length === next.length ? "DONE" : `MORE ${next.length - states.length}`);
await lfs.close();
