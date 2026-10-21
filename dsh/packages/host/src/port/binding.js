// The native binding of a ported Live project (macOS only; the owner's
// exception of 2026-10-20 to the Direct Store rule, AGENTS.md). The real SDK
// runs in this process; each binding call goes to the LayerFS box's worker
// (box.js, worker.mjs), which makes it with the real Linux binding and keeps
// the project's Store and daemon connections open while they are in use. This
// process holds one connection to the worker, idle connections do not keep it
// alive, and the worker's port and secret come from the LayerFS home's box
// file. Init alone runs in its own container (run.mjs), which mounts its
// source folder.
import { execFile, spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { connect } from "node:net";
import { fileURLToPath } from "node:url";
import { deserialize, serialize } from "node:v8";
import { boxFile, callMounts, DAEMON_HOST } from "../box.js";
import { frame, readFrames } from "./frames.mjs";

const RUN = fileURLToPath(new URL("./run.mjs", import.meta.url));
/** Stores this process has opened, by path, with their clients. */
const opened = new Map();
const setting = (name) => process.env[`LAYERFS_${name}`] || process.env[`DSH_LAYERFS_${name}`];
const refused = (code, message) => ({ refused: { code, message, detail: null } });

/**
 * One binding call in Linux: its answer, `{ value }` or `{ refused }`. A call
 * to a named Sandbox (the operator's) carries no deployment, and the Linux
 * binding takes the daemon's host only from one: every call gets the box's.
 */
function inBox(fn, op, args) {
  const box = setting("BOX"), bundle = setting("BUNDLE");
  if (!box || !bundle) return Promise.resolve(refused("Unsupported", "no LayerFS box is set (DSH_LAYERFS_BOX, DSH_LAYERFS_BUNDLE): Store calls run only in Linux"));
  const sent = { ...args, deploy: { ...args.deploy, daemonHost: args.deploy?.daemonHost ?? DAEMON_HOST } };
  const request = { fn, op, args: sent, open: opened.has(args.storePath) };
  return op === "project.init" ? initCall(box, bundle, request) : worker(box, args.home ?? setting("HOME")).call(request);
}

export const call = (op, args) => inBox("call", op, args);
export const operatorCall = (op, args) => inBox("operatorCall", op, args);

/** The Store opens in the worker; here only its clients are counted. */
export async function storeOpen({ storePath }) {
  opened.set(storePath, (opened.get(storePath) ?? 0) + 1);
  return { value: null };
}
export async function storeClose({ storePath }) {
  const left = (opened.get(storePath) ?? 1) - 1;
  if (left > 0) opened.set(storePath, left); else opened.delete(storePath);
  return { value: null };
}

/** The worker returns a spooled exec's output whole, so no spool is left to read here. */
export async function execOutput() {
  return refused("Failed", "a ported exec's output arrives whole; there is no spool to read");
}

let link = null;
/**
 * This process's connection to the box's worker, opened on first use. Calls
 * wait for the worker's answer to the secret: a connection lost before it
 * carried none of them (Failed), one lost after may have run them (Unknown).
 */
function worker(box, home) {
  if (link && !link.closed) return link;
  let info;
  try { info = JSON.parse(readFileSync(boxFile(home), "utf8")); } catch { info = null; }
  if (!info || info.box !== box) return { call: async () => refused("Failed", `the LayerFS box ${box} has not started for ${home}: start dsh web`) };
  const pending = new Map(), waiting = [];
  let next = 1, greeted = false;
  const socket = connect({ host: "127.0.0.1", port: info.port });
  socket.setNoDelay(true);
  socket.unref();
  socket.write(frame({ secret: info.secret }));
  const send = (id, request) => socket.write(frame({ id, ...request }));
  readFrames(socket, ({ id, answer }) => {
    if (id === 0) {
      greeted = true;
      for (const [waitingId, request] of waiting.splice(0)) send(waitingId, request);
      return;
    }
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    if (!pending.size) socket.unref();
    if (answer?.thrown) p.reject(new Error(answer.thrown)); else p.resolve(answer);
  }, () => socket.destroy());
  const self = { closed: false };
  const lost = (error) => {
    self.closed = true;
    const why = error ? ` (${error.message})` : "";
    const answer = greeted
      ? refused("Unknown", `the connection to the LayerFS box ${box} was lost${why}: check the project before going on`)
      : refused("Failed", `the LayerFS box ${box}'s worker did not answer${why}: restart dsh web`);
    for (const p of pending.values()) p.resolve(answer);
    pending.clear();
    waiting.length = 0;
  };
  socket.on("error", lost);
  socket.on("close", () => lost(null));
  self.call = (request) => {
    if (self.closed) return worker(box, home).call(request);
    return new Promise((resolve, reject) => {
      const id = next++;
      pending.set(id, { resolve, reject });
      socket.ref();
      if (greeted) send(id, request); else waiting.push([id, request]);
    });
  };
  return (link = self);
}

/**
 * Init in its own container on the box's image, which the build was made for
 * (the project's Sandboxes may run another), with the source folder mounted
 * read-only, so the box shares no host folder beyond the ones every call uses.
 */
async function initCall(box, bundle, request) {
  const { args } = request;
  let image;
  try { image = await boxImage(box); } catch { return refused("Failed", `the LayerFS box ${box} is not there to run project.init`); }
  const env = Object.keys(process.env).filter((k) => /^(DSH_)?LAYERFS_/.test(k) && !k.endsWith("_NATIVE")).flatMap((k) => ["-e", k]);
  const where = ["run", "--rm", "-i", "--init", "--pull", "never", ...callMounts({ home: args.home, bundle }), "-v", `${args.path}:${args.path}:ro`, ...env, "--entrypoint", "node", image, RUN];
  return new Promise((resolve, reject) => {
    const child = spawn("docker", where, { stdio: ["pipe", "pipe", "inherit"] });
    const out = [];
    child.stdout.on("data", (chunk) => out.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      const bytes = Buffer.concat(out);
      if (code === 0 && bytes.length) {
        const answer = deserialize(bytes);
        return answer.thrown ? reject(new Error(answer.thrown)) : resolve(answer);
      }
      // 125 and up: docker could not start the process, so the call did not run
      resolve(code >= 125
        ? refused("Failed", `the LayerFS box ${box} did not run project.init (docker run exit ${code})`)
        : refused("Unknown", `project.init ended without an answer (exit ${code}): check the project before going on`));
    });
    child.stdin.end(serialize(request));
  });
}

/** The image the box runs. */
function boxImage(box) {
  return new Promise((resolve, reject) => execFile("docker", ["container", "inspect", "-f", "{{.Image}}", box], (error, out) => (error ? reject(error) : resolve(out.trim()))));
}
