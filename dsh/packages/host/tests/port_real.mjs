// The ported SDK of Live projects on macOS (src/port/, src/box.js), with real
// Docker and a sealed Linux LayerFS build:
//   node packages/host/tests/port_real.mjs <bundle folder> <image digest>
// A plain Mac script uses the ported SDK as an agent would: Init, the Store
// install (a first Sandbox), Store calls (fork, write, read, list, publish),
// Workspace calls (mount, exec, commit, unmount), a refusal and an exec whose
// output is spooled. Each SDK call goes to the box's long-lived worker, which
// keeps the project's Store open between calls; Init runs in its own
// container. The box, the volume, the containers and the home are removed
// afterwards.
// macOS only; under 2 minutes.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DAEMON_HOST, boxName, ensureBox, storePathOf } from "../src/box.js";

const [bundle, image] = process.argv.slice(2);
if (process.platform !== "darwin" || !bundle || !image) {
  console.log("usage (macOS): node packages/host/tests/port_real.mjs <bundle folder> <image digest>");
  process.exit(2);
}
const work = mkdtempSync(join(realpathSync(tmpdir()), "lfs-port-"));
const home = join(work, "home"), source = join(work, "shop"), id = Date.now().toString(36);
const volume = `lfs-port-test-${id}`, prefix = `lfs-port-test-${id}-`;
const spec = { docker: "/var/run/docker.sock", home, bundle, image, box: boxName(home, bundle) };
const docker = (...args) => execFileSync("docker", args, { encoding: "utf8" }).trim();
mkdirSync(home, { mode: 0o700 });
mkdirSync(source);
writeFileSync(join(source, "README.md"), "# Shop\n");
Object.assign(process.env, {
  DSH_LAYERFS_BOX: spec.box, DSH_LAYERFS_BUNDLE: bundle, LAYERFS_HOME: home, LAYERFS_DOCKER: spec.docker,
  LAYERFS_IMAGE: image, LAYERFS_VOLUME: volume, LAYERFS_DAEMON: join(bundle, "layerfs-daemon"),
  LAYERFS_STORE_PATH: storePathOf(volume), LAYERFS_DAEMON_HOST: DAEMON_HOST,
  LAYERFS_CONTAINER_PREFIX: prefix, LAYERFS_CONSTRUCTION_WORKERS: "1",
});

const timed = async (label, work) => {
  const t0 = performance.now();
  const value = await work();
  console.log(`${label.padEnd(26)} ${String(Math.round(performance.now() - t0)).padStart(5)} ms`);
  return value;
};
let layerfs;
try {
  docker("volume", "create", volume);
  await timed("box start", () => ensureBox(spec));
  const { LayerFS, isRefusal } = await import("../src/port/sdk.js");
  const { LayerFSOperator } = await import("../src/port/operator.js");
  layerfs = new LayerFS("shop");
  const operator = new LayerFSOperator(layerfs);
  // as the Host does: settings exist only while the client is made, so a call
  // must use its client's deployment, never this process's environment
  for (const name of ["IMAGE", "DAEMON_HOST"]) delete process.env[`LAYERFS_${name}`];
  const init = await timed("project.init", () => layerfs.project.init(source));
  assert.equal(init.kind, "Initialized");
  const sb = await timed("sandbox.create (install)", () => layerfs.sandbox.create("hello", "shop", image));
  const forked = await timed("branch.fork", () => layerfs.branch.fork("work"));
  assert.equal(forked.branch, "work");
  await timed("fs.write", () => layerfs.fs.write("work", "/hello.js", "console.log('hello, shop');\n", "add hello.js"));
  assert.equal((await timed("fs.read", () => layerfs.fs.read("work", "/hello.js"))).text, "console.log('hello, shop');\n");
  const refused = await timed("fs.read (missing)", () => layerfs.fs.read("work", "/nope.js").catch((e) => e));
  assert.ok(isRefusal(refused, "NoSuchPath"), `a refusal arrives as the SDK's own: ${refused}`);
  // the operator's Sandbox calls carry no deployment, yet reach the daemon
  const snap = await timed("operator inspect.snapshot", () => operator.inspect.snapshot());
  assert.equal(snap.kind, "ok");
  const path = await timed("sandbox.mount", () => layerfs.sandbox.mount(sb, "work"));
  const ran = await timed("sandbox.exec", () => layerfs.sandbox.exec(sb, path, "node hello.js | tee hello.txt", "run hello"));
  assert.equal(ran.exitCode, 0);
  assert.equal(ran.stdout, "hello, shop\n");
  const big = await timed("sandbox.exec (2 MiB out)", () => layerfs.sandbox.exec(sb, path, "head -c 2097152 /dev/zero | tr '\\0' a"));
  assert.equal(big.stdout.length, 2097152, "a spooled output arrives whole");
  assert.equal((await timed("sandbox.commit", () => layerfs.sandbox.commit(sb, path, "step 1: node hello.js (exit 0)"))).kind, "Committed");
  await timed("sandbox.unmount", () => layerfs.sandbox.unmount(sb, path));
  await timed("sandbox.close", () => layerfs.sandbox.close(sb));
  assert.equal((await timed("branch.publish", () => layerfs.branch.publish("work"))).kind, "Added");
  const branches = await timed("project.list_branches", () => layerfs.project.list_branches());
  assert.deepEqual(branches.items.map((b) => b.name).sort(), ["main", "work"]);
  console.log("port: ok");
} finally {
  await layerfs?.close().catch(() => {});
  // each step on its own, so one failure leaves the rest done; the box made
  // the home's files, so it removes them
  const step = (label, work) => { try { work(); } catch (error) { console.log(`cleanup ${label}: ${error.message.split("\n")[0]}`); } };
  step("containers", () => {
    const left = docker("ps", "-aq", "--filter", `name=^${prefix}`).split("\n").filter(Boolean);
    if (left.length) docker("rm", "-f", ...left);
  });
  step("home", () => docker("exec", spec.box, "find", home, "-mindepth", "1", "-delete")); // home is the box's mount point
  step("box", () => docker("rm", "-f", spec.box));
  step("volume", () => docker("volume", "rm", volume));
  step("work", () => rmSync(work, { recursive: true, force: true }));
}
