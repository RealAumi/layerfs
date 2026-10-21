// Holds one LayerFS Workspace mounted for the `layerfs-core` fs-bench arm,
// through the public JavaScript SDK (@layerfs/sdk), as an agent would:
// project.init, sandbox.create (which installs the Store into the volume),
// branch.fork of its own Branch from main, sandbox.mount of that Branch,
// then sandbox.unmount and sandbox.close at the end, following
// the layerfs-js-sdk skill and sdk/js/test/verify. Setup only: nothing here is timed.
//
// Runs on Linux, where the SDK opens the Store directly (#352 F-020): inside
// the runtime image, with the Docker socket, the Store volume at
// /layerfs-store and the LAYERFS_* deployment variables (see run-holder.sh).
// Prints the Sandbox's container id and the Workspace path, then waits for
// stdin to close. A refusal stops the holder with its error; nothing is retried.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { LayerFS } from "../../../sdk/js/src/index.js";

const [project, source] = process.argv.slice(2);
if (!project || !source) throw new Error("usage: holder.mjs PROJECT FRESH_SOURCE_DIR");
mkdirSync(source, { mode: 0o755 });
writeFileSync(join(source, "README"), "fs-bench layerfs-core arm\n", { mode: 0o644 });

const layerfs = new LayerFS(project);
const created = await layerfs.project.init(source);
console.log(`INIT ${created.kind}`);
const id = await layerfs.sandbox.create("bench", project, process.env.LAYERFS_IMAGE);
const container = readFileSync(join(process.env.LAYERFS_HOME, "_sandboxes", id, "container"), "utf8").trim();
console.log(`CONTAINER ${container}`);
const branches = await layerfs.project.list_branches();
console.log(`BRANCHES ${branches.items.map((b) => b.name).join(" ")}`);
const forked = await layerfs.branch.fork("bench", "main");
console.log(`FORK ${forked.kind} ${forked.branch} ${forked.head}`);
const path = await layerfs.sandbox.mount(id, "bench");
console.log(`MOUNT ${path}`);

// The frozen runner needs Bash 4+, GNU date with %N, shuf, awk and git.
const probe = await layerfs.sandbox.exec(id, path,
  "echo bash=${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}; date +%s%N | grep -Eq '^[0-9]{19}$' && echo date_ns=ok; " +
  "for t in shuf awk git seq dd cp cat find; do printf '%s=%s\\n' $t $(command -v $t); done; git --version; id; " +
  "touch probe && rm probe && echo write=ok");
process.stdout.write(probe.stdout);
if (probe.exitCode !== 0) throw new Error(`probe exit ${probe.exitCode}: ${probe.stderr}`);
console.log("HOLDING close stdin to unmount and close");

for await (const _ of process.stdin) { /* wait for EOF */ }

// The runner removes its own directories, so nothing is left to keep.
const unmounted = await layerfs.sandbox.unmount(id, path, true);
console.log(`UNMOUNTED ${path} ${JSON.stringify(unmounted)}`);
await layerfs.sandbox.close(id);
console.log(`CLOSED ${id}`);
await layerfs.close();
