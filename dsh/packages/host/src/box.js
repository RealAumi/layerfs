// The LayerFS box of ported Live projects (macOS; port/binding.js): one
// long-lived Linux container whose main process is the worker (port/
// worker.mjs) that makes every ported SDK call with the real Linux binding
// (owner direction of 2026-10-20, AGENTS.md). The worker's port is published
// to the Mac's loopback only, and its secret and port are written to the
// LayerFS home (boxFile) for the Host's and agents' processes. The box is
// labelled with its worker's code, so a changed worker gets a new box.
// It mounts only what the calls use, each at its own path so a path means the
// same inside as outside, for Docker too: the Docker socket, Docker's volume
// directory (inside Docker's VM), the LayerFS home (writable), the LayerFS
// build and port/ (read-only). Never a broad host folder: Docker Desktop
// forwards every file event under a shared folder into its VM, and sharing
// /Users stalled it (2026-10-20). Init, the one call that reads a source
// folder, runs in its own container with that folder (binding.js).
import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { readFileSync, renameSync, writeFileSync } from "node:fs";
import { connect } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { frame, readFrames } from "./port/frames.mjs";

const run = promisify(execFile);
export const VOLUMES = "/var/lib/docker/volumes";
export const PORT = dirname(fileURLToPath(new URL("./port/run.mjs", import.meta.url)));
/** Where a box process reaches a daemon's loopback-published port: the Mac. */
export const DAEMON_HOST = "host.docker.internal";
const WORKER_PORT = 7070;
const READY_MS = 15_000;

/** `docker run` mounts and settings of a ported call's process: the box's worker, or Init's own. */
export const callMounts = ({ home, bundle }) => [
  "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", `${VOLUMES}:${VOLUMES}`,
  "-v", `${home}:${home}`, "-v", `${bundle}:${bundle}:ro`, "-v", `${PORT}:${PORT}:ro`,
  "-e", `LAYERFS_NATIVE=${join(bundle, "layerfs.node")}`,
];

/** Where a ported call opens the Store of the project volume `volume`. */
export const storePathOf = (volume) => `${VOLUMES}/${volume}/_data/global/store.sqlite`;

/** The box's name: one per LayerFS home and build, so a new build gets a new box. */
export const boxName = (home, bundle) => `dsh-layerfs-box-${createHash("sha256").update(`${home}\n${bundle}`).digest("hex").slice(0, 12)}`;

/** The file that tells a home's processes how to reach its box's worker: { box, port, secret }. */
export const boxFile = (home) => join(home, ".dsh-layerfs-box.json");

/** The worker's code, as the box's label: a changed worker needs a new box. */
const workerVersion = () => {
  const hash = createHash("sha256");
  for (const file of ["worker.mjs", "call.mjs", "frames.mjs"]) hash.update(readFileSync(join(PORT, file)));
  return hash.digest("hex").slice(0, 12);
};

let starting = null;
/** Starts the box and its worker unless they run, and writes boxFile; one start at a time. */
export function ensureBox(spec) {
  starting ??= start(spec).finally(() => { starting = null; });
  return starting;
}

async function start(spec) {
  const docker = (...args) => run("docker", ["-H", `unix://${spec.docker}`, ...args]).then((r) => r.stdout.trim());
  const version = workerVersion();
  let state = await docker("inspect", "-f", '{{.State.Running}} {{index .Config.Labels "dsh-layerfs.worker"}}', spec.box).catch(() => null);
  if (state && state.split(" ")[1] !== version) {
    // a box of another worker (or of the per-call port before it): replaced
    await docker("rm", "-f", spec.box);
    state = null;
  }
  let secret;
  if (!state) {
    secret = randomBytes(32).toString("hex");
    await docker("run", "-d", "--pull", "never", "--name", spec.box, "--init",
      "--label", "dsh-layerfs.box=1", "--label", `dsh-layerfs.worker=${version}`,
      "-p", `127.0.0.1::${WORKER_PORT}`, "-e", `DSH_BOX_SECRET=${secret}`, "-e", "UV_THREADPOOL_SIZE=64",
      ...callMounts(spec), "--entrypoint", "node", spec.image, join(PORT, "worker.mjs"));
  } else {
    if (state.startsWith("false")) await docker("start", spec.box);
    const env = await docker("inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", spec.box);
    secret = /^DSH_BOX_SECRET=([0-9a-f]+)$/m.exec(env)?.[1];
    if (!secret) throw new Error(`the LayerFS box ${spec.box} has no secret`);
  }
  // "127.0.0.1:55012" (a second line for IPv6 when Docker adds one)
  const port = Number(/:(\d+)$/m.exec(await docker("port", spec.box, `${WORKER_PORT}/tcp`))?.[1]);
  if (!port) throw new Error(`the LayerFS box ${spec.box} publishes no worker port`);
  await listening(port, secret, spec.box);
  const file = boxFile(spec.home);
  writeFileSync(`${file}.tmp`, JSON.stringify({ box: spec.box, port, secret }), { mode: 0o600 });
  renameSync(`${file}.tmp`, file);
}

/** Waits until the worker answers a ping (a readiness wait, bounded): Docker's proxy may accept before it listens. */
async function listening(port, secret, box) {
  for (const until = Date.now() + READY_MS; ; ) {
    const ok = await new Promise((resolve) => {
      const socket = connect({ host: "127.0.0.1", port }, () => socket.write(Buffer.concat([frame({ secret }), frame({ id: 1, fn: "ping" })])));
      const done = (value) => { clearTimeout(timer); socket.destroy(); resolve(value); };
      const timer = setTimeout(() => done(false), 1000);
      readFrames(socket, (value) => { if (value?.id === 1) done(value.answer?.value === "ready"); }, () => done(false));
      socket.on("error", () => done(false));
      socket.on("close", () => done(false));
    });
    if (ok) return;
    if (Date.now() > until) throw new Error(`the LayerFS box ${box}'s worker did not answer within ${READY_MS / 1000} s`);
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}
