// Untimed removal of one sandbox-disk data file after the last job that
// uses it (run.sh drop steps), through sandbox.exec, with the VM's memory
// figures before and after. One row goes to drop.jsonl and the output to
// ops/drop-<file>-sandbox-disk.txt. The passthrough-fuse removal is pt.mjs.
//
//   drop.mjs FILE
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { append, exec, home, lfs, session } from "../../common/session.mjs";
import { DISK, dropCommand, FILES } from "./common.mjs";

const [file] = process.argv.slice(2);
if (!FILES[file]) throw new Error("usage: drop.mjs seq|rand|sync");
const { path } = session();
const run = await exec(path, dropCommand(DISK, file));
mkdirSync(join(home, "ops"), { recursive: true });
writeFileSync(join(home, "ops", `drop-${file}-sandbox-disk.txt`), run.stdout + (run.stderr ? `=== stderr\n${run.stderr}` : ""));
append("drop.jsonl", { file, arm: "sandbox-disk", exec_ms: run.ms, exec_exit: run.exitCode });
await lfs.close();
if (run.exitCode !== 0) throw new Error(`drop ${file} sandbox-disk failed: ${run.stdout.slice(-2000)} ${run.stderr.slice(-2000)}`);
