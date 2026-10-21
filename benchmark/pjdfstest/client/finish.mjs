// Finish: the layerfs arm's residue under pjd/ (entries left after the
// tests), then, with `commit`, one timed sandbox.commit to show the Workspace
// still commits after the run; then unmount and close (common/session.mjs).
// Without `commit` it only tears down, for a run that cannot finish.
//
//   finish.mjs [commit]
import { append, commit, exec, lfs, session, teardown } from "../../common/session.mjs";

const { path } = session() ?? {};
if (path && process.argv[2] === "commit") {
  const residue = await exec(path, "for d in pjd/*/; do echo \"$d $(find \"$d\" -mindepth 1 | wc -l)\"; done; find pjd | wc -l");
  append("ledger.jsonl", { step: "residue", ...residue });
  await commit(path, "pjdfstest: after all groups");
}
await teardown();
await lfs.close();
