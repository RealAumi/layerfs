// Capture proof, layerfs only, after the fsstress processes have exited.
// Two clients, so each stays far inside its 115 s alarm:
//   capture.mjs commit   manifest of the live Workspace (sandbox.exec),
//                        sandbox.commit (timed), branch.fork("capture", <Commit id>)
//   capture.mjs verify   sandbox.mount of Branch "capture" as a second
//                        Workspace in the same Sandbox, the same manifest
//                        there, the comparison, both manifests read back
//                        into the run folder, terminal unmount of it
// Each phase appends one capture.jsonl row.
import { append, commit, lfs, rows, SANDBOX, session, timed } from "../../common/session.mjs";
import { execJson, readBack } from "./common.mjs";

const tool = "python3 /opt/fsstress-bench/manifest.py";
const phase = process.argv[2];
const { path } = session();
if (phase === "commit") {
  const live = await execJson(path, `${tool} build ${path} /tmp/manifest-live.jsonl`);
  const value = await commit(path, "fsstress capture");
  const id = value.commit?.id;
  if (!id) throw new Error(`Commit returned no Commit id: ${JSON.stringify(value)}`);
  const fork = await lfs.branch.fork("capture", id);
  if (fork.head !== id) throw new Error(`fork capture head ${fork.head}, expected ${id}`);
  append("capture.jsonl", { phase, live_ms: live.ms, live: live.json, commit: value, fork });
} else if (phase === "verify") {
  const done = rows("capture.jsonl").find((r) => r.phase === "commit");
  if (!done) throw new Error("capture.mjs verify needs the commit phase first");
  const [second, mountMs] = await timed(() => lfs.sandbox.mount(SANDBOX, "capture"));
  const captured = await execJson(second, `${tool} build ${second} /tmp/manifest-capture.jsonl`);
  const compared = await execJson(second, `${tool} compare /tmp/manifest-live.jsonl /tmp/manifest-capture.jsonl`);
  for (const m of [done.live, captured.json]) await readBack(second, m.manifest, m.manifest_bytes, m.manifest_sha256, m.manifest.slice(5));
  const [, unmountMs] = await timed(() => lfs.sandbox.unmount(SANDBOX, second, true));
  append("capture.jsonl", { phase, second, mount_ms: mountMs, captured_ms: captured.ms, captured: captured.json, compare_ms: compared.ms, compare: compared.json, unmount_ms: unmountMs });
} else {
  throw new Error("usage: capture.mjs commit|verify");
}
await lfs.close();
