// Simulated LayerFS checks without Docker or a Store: the SDK on the
// simulator's binding (src/sim) through a Workspace's life, the Host's Init,
// views and removal of a simulated project, and the sed stand-in.
//   node dsh/packages/host/tests/sim.mjs
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = mkdtempSync(join(tmpdir(), "dsh-layerfs-sim-"));
const home = join(dir, "home"), trace = join(dir, "trace.jsonl");
const FOLDER = fileURLToPath(new URL("../../../demo-workspace", import.meta.url));
const NAME = "sim-test";
const ID = { commit: /^12[0-9a-f]{64}$/, layer: /^32[0-9a-f]{64}$/ };

try {
  const { resolveConfig } = await import("../src/config.js");
  const { BindingStore } = await import("../src/binding.js");
  const { TreeReader } = await import("../src/trees.js");
  const { removeProject } = await import("../src/remove.js");
  const { prepareInit, initProject } = await import("../src/init.js");
  const { deploymentEnv } = await import("../src/layerfs-client.js");
  const { alive } = await import("../src/sim/shell.js");

  // Init: no Docker and no deployment settings; a backend other than sim is refused.
  const spec = resolveConfig({ home }, { dir });
  const bindings = new BindingStore(spec.stateDir);
  assert.throws(() => prepareInit(spec, bindings, { folder: FOLDER, backend: "docker" }), { code: "invalid-backend" });
  assert.throws(() => prepareInit(spec, bindings, { folder: FOLDER }), { code: "not-configured" });
  const steps = [];
  const project = await initProject(spec, bindings, { folder: FOLDER, name: NAME, backend: "sim" }, (fields) => fields.step && steps.push(fields.step));
  assert.deepEqual(steps, ["scan", "volume", "import"]);
  assert.equal(project.backend, "sim");
  assert.equal(bindings.byName(NAME).backend, "sim");
  assert.deepEqual(deploymentEnv(spec, project), { HOME: home, DOCKER: "sim", IMAGE: "sim", DAEMON: "sim", VOLUME: `sim-${NAME}`, STORE_PATH: "sim" });

  // The SDK on the simulator, with the environment the Host gives a simulated project's bash calls.
  for (const [name, value] of Object.entries(deploymentEnv(spec, project))) process.env[`LAYERFS_${name}`] = value;
  process.env.LAYERFS_TRACE = trace;
  const { LayerFS, isRefusal } = await import("../src/sim/sdk.js");
  const { LayerFSOperator } = await import("../src/sim/operator.js");
  const lf = new LayerFS(NAME), op = new LayerFSOperator(lf);
  const refused = async (call, code) => {
    try { await call(); } catch (error) { assert.ok(isRefusal(error, code), `expected ${code}, got ${error.code}: ${error.message}`); return error; }
    assert.fail(`expected ${code}`);
  };

  const fork = await lf.branch.fork("feature");
  assert.equal(fork.kind, "Forked");
  assert.match(fork.base, ID.layer);
  const edit = await lf.fs.edit("feature", "/app/page.tsx", "Hello world", "Home", "headline");
  assert.equal(edit.kind, "Committed");
  assert.match(edit.commit.id, ID.commit);
  assert.equal(edit.commit.message, "headline");
  await refused(() => lf.fs.write("main", "/x", "x"), "ReadOnly");

  const sb = await lf.sandbox.create(`${NAME}-a`, NAME, "sim");
  assert.equal(sb, `${NAME}-a`);
  await refused(() => lf.sandbox.create(sb, NAME, "sim"), "Exists");
  const ws = await lf.sandbox.mount(sb, "feature");
  assert.equal(ws, "/workspaces/1");
  const built = await lf.sandbox.exec(sb, ws, "sh install.sh && sh build.sh");
  assert.equal(built.kind, "exit:0", built.stdout + built.stderr);
  assert.match(built.stdout, /Compiled successfully: 2 pages/);
  const sed = await lf.sandbox.exec(sb, ws, "sed -i 's/Home/Welcome/' app/page.tsx && grep h1 app/page.tsx");
  assert.match(sed.stdout, /<h1>Welcome<\/h1>/);
  assert.equal((await lf.sandbox.exec(sb, ws, "exit 3")).kind, "exit:3");

  // A background process keeps the Workspace busy until it is stopped.
  const server = await op.process.start(sb, ws, "sleep 30");
  assert.equal(server.kind, "running");
  const busy = await refused(() => lf.sandbox.unmount(sb, ws), "Busy");
  assert.deepEqual(busy.detail.processes, [server.process]);
  const listed = await op.process.list(sb);
  assert.equal(listed.items[0].status, "running");
  const pid = JSON.parse(readFileSync(join(home, NAME, "sim", "state.json"), "utf8")).sim.sandboxes[sb].processes[server.process].pid;
  assert.ok(alive(pid));
  assert.equal((await op.process.cancel(sb, server.process)).status, "stopped");

  // The head moves under the Workspace: commit writes the merge's markers and refuses, twice.
  await lf.fs.edit("feature", "/app/page.tsx", "<h1>Home</h1>", "<h1>Hi</h1>", "greeting");
  assert.equal((await lf.sandbox.status(sb, ws)).headMovedSinceMount, true);
  const conflict = await refused(() => lf.sandbox.commit(sb, ws, "welcome"), "Conflict");
  assert.equal(conflict.message, "Conflict: the head moved and 1 file(s) conflict with this Workspace; markers are written and nothing was committed");
  assert.deepEqual(conflict.detail.conflicts.map((c) => c.path), ["/app/page.tsx"]);
  assert.deepEqual(conflict.detail.conflicts[0].hunks[0], { line: 4, ours: ["      <h1>Welcome</h1>"], theirs: ["      <h1>Hi</h1>"] });
  const marked = await lf.sandbox.exec(sb, ws, "cat app/page.tsx");
  assert.match(marked.stdout, /^>>>>>>> feature@12[0-9a-f]{64}$/m);
  const markers = await refused(() => lf.sandbox.commit(sb, ws, "welcome"), "Conflict");
  assert.equal(markers.message, "Conflict: 1 file(s) still contain conflict markers; nothing committed");
  await lf.sandbox.exec(sb, ws, "sed -i '/^<<<<<<< /d; /^=======$/,/^>>>>>>> /d' app/page.tsx");
  const saved = await lf.sandbox.commit(sb, ws, "welcome");
  assert.equal(saved.kind, "Committed");
  assert.equal(saved.commit.via, "exec");
  assert.equal((await lf.sandbox.unmount(sb, ws)).kind, "Unmounted");
  assert.ok(!existsSync(join(home, NAME, "sim", "ws", sb, "1")), "an unmounted Workspace's folder is removed");
  assert.equal((await lf.sandbox.close(sb)).kind, "Closed");

  // Publish, then read main.
  const published = await lf.branch.publish("feature");
  assert.equal(published.kind, "Added");
  assert.match(published.publishedLayer.id, ID.layer);
  assert.equal((await lf.branch.publish("feature")).kind, "UpToDate");
  const app = await lf.fs.list("main", "/app");
  assert.deepEqual(app.items.map((i) => i.name), ["layout.tsx", "page.tsx"]);
  assert.ok(Number.isInteger(app.items[0].inode));
  assert.match((await lf.fs.read("main", "/app/page.tsx")).text, /<h1>Welcome<\/h1>/);
  assert.equal((await lf.fs.read("main", "/app/page.tsx", 4, 4)).text, "      <h1>Welcome</h1>\n");
  const blame = await lf.fs.blame("main", "/app/page.tsx");
  const welcome = blame.lines.find((l) => l.text.includes("Welcome"));
  assert.equal(welcome.n, 4);
  assert.match(welcome.commit, ID.commit, "main's lines are credited to the Commit that wrote them");
  assert.equal(welcome.message, "welcome");
  assert.match(blame.lines[0].commit, ID.layer, "an unchanged line is the Init Layer's");
  const both = await lf.branch.merge("feature", "main", "both");
  assert.equal(both.kind, "Merged");
  assert.equal(both.fastForward, true);
  if (lf.serviceSandbox) await lf.sandbox.close(await lf.serviceSandbox);

  // The SDK's own trace lines, with ids in LayerFS's formats.
  const lines = readFileSync(trace, "utf8").trim().split("\n").map((l) => JSON.parse(l));
  const codes = lines.filter((l) => l.method === "sandbox.commit").map((l) => (l.ok ? l.kind : l.code));
  assert.deepEqual(codes, ["Conflict", "Conflict", "Committed"]);
  assert.match(lines.find((l) => l.method === "sandbox.commit" && l.ok).commit, ID.commit);
  assert.equal(lines.find((l) => l.method === "sandbox.create").sandbox, sb);

  // The Host's views read the simulator: the state, Files reads of saved ids and the Store.
  const trees = new TreeReader(spec);
  const state = await trees.state(project, [sb]);
  assert.deepEqual(Object.keys(state.s.branches).sort(), ["both", "feature"]);
  assert.equal(Object.keys(state.s.commits).length, 3, "headline, greeting, welcome; the merge with main fast-forwards");
  const head = Object.entries(state.labels).find(([, label]) => label === state.s.branches.feature.head)[0];
  const q = (o) => new URLSearchParams(o);
  assert.ok((await trees.files(project, "list", q({ ref: head, dir: "/app" }))).items.some((e) => e.path === "/app/page.tsx" && e.type === "file"));
  assert.match((await trees.files(project, "read", q({ ref: head, path: "/app/page.tsx" }))).text, /Welcome/);
  const parent = Object.entries(state.labels).find(([, label]) => label === state.s.commits[state.s.branches.feature.head].parent)[0];
  assert.ok((await trees.files(project, "changes", q({ from: parent, to: head }))).items.some((e) => e.path === "/app/page.tsx" && e.kind === "Modified"));
  const storage = await trees.storage(project);
  assert.ok(storage.store.logical > 0 && storage.init.files > 0);
  assert.equal(typeof storage.store.dedupe, "number");
  assert.equal(storage.commits.length, 3);

  // Removal stops the project's background processes and deletes its home entry.
  const sb2 = await lf.sandbox.create(`${NAME}-b`, NAME, "sim");
  const ws2 = await lf.sandbox.mount(sb2, "feature");
  await op.process.start(sb2, ws2, "sleep 30");
  const running = Object.values(JSON.parse(readFileSync(join(home, NAME, "sim", "state.json"), "utf8")).sim.sandboxes[sb2].processes)[0].pid;
  assert.ok(alive(running));
  assert.deepEqual(await removeProject(spec, bindings, trees, NAME, () => assert.fail("a simulated project runs no docker")), { removed: NAME, volume: `sim-${NAME}` });
  for (let i = 0; i < 50 && alive(running); i++) await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(!alive(running), "removal stops the background process");
  assert.ok(!existsSync(join(home, NAME)));
  assert.equal(bindings.byName(NAME), null);
  await trees.dispose();

  // The sed stand-in, on the demos' scripts.
  const sedJs = fileURLToPath(new URL("../src/sim/sed.js", import.meta.url));
  const sedOn = (text, ...args) => { const file = join(dir, "sed.txt"); writeFileSync(file, text); execFileSync(process.execPath, [sedJs, "-i", ...args, file]); return readFileSync(file, "utf8"); };
  assert.equal(sedOn("<h1>We're</h1>\n", "s/We're/We\\&apos;re/"), "<h1>We&apos;re</h1>\n");
  assert.equal(sedOn("# Website\nx\n", "1s/.*/# Website (with navigation)/"), "# Website (with navigation)\nx\n");
  assert.equal(sedOn('"build": "sh build.sh"\n', 's/\\("build": "sh build.sh[^"]*\\)"/\\1 --profile"/'), '"build": "sh build.sh --profile"\n');
  assert.equal(sedOn("a\n<<<<<<< w\nb\n=======\nc\n>>>>>>> h\nd\n", "/^<<<<<<< /d; /^=======$/,/^>>>>>>> /d"), "a\nb\nd\n");
  assert.equal(sedOn("<<<<<<< w\n<h1>Welcome</h1>\n=======\n<h1>Home</h1>\n>>>>>>> h\n", "/<h1>Home<\\/h1>/d; /^<<<<<<<\\|^=======\\|^>>>>>>>/d; s/<h1>Welcome</<h1>Welcome home</"), "<h1>Welcome home</h1>\n");
  assert.equal(execFileSync(process.execPath, [sedJs, "-n", "2p"], { input: "a\nb\nc\n", encoding: "utf8" }), "b\n");

  console.log("sim: ok");
} finally {
  rmSync(dir, { recursive: true, force: true });
}
