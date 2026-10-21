// "Init LayerFS": imports a folder as a new LayerFS project on its own
// Docker volume, the dsh workspace folder's default project. A simulated project
// (backend "sim") is imported into the simulator (sim/) instead: no Docker,
// no deployment settings.
import { execFile } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { lstat, opendir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as pause } from "node:timers/promises";
import { promisify } from "node:util";
import { ensureBox } from "./box.js";
import { missingDeployment } from "./config.js";
import { clientFor, isSim, release } from "./layerfs-client.js";

const run = promisify(execFile);
const NAME = /^[a-z0-9](?:[a-z0-9_.-]{0,61}[a-z0-9])?$/;
const WATCH_MS = 250;
const IMAGE = /^sha256:[0-9a-f]{64}$/;
/** The demo scenarios (the mock plugin's default folder), for their `live` flag. */
const SCENARIOS = fileURLToPath(new URL("../../../scenarios/", import.meta.url));

const refuse = (code, message) => Object.assign(new Error(message), { code });

/** A project name from a folder name: lowercase, the SDK's alphabet, at most 63 characters. */
export function nameFrom(folder) {
  const base = basename(folder).toLowerCase().replace(/[^a-z0-9_.-]+/g, "-").replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, "").slice(0, 63);
  return NAME.test(base) ? base : "project";
}

const free = (name, taken, home) => !taken.has(name) && !existsSync(join(home, name));
/** The first free name: `base`, then `base-1`, `base-2`, … (the same folder imported again). */
function freeName(base, taken, home) {
  for (let i = 0; ; i++) {
    const name = i === 0 ? base : `${base.slice(0, 60)}-${i}`;
    if (free(name, taken, home)) return name;
  }
}

const ADJECTIVES = ["amber", "brave", "bright", "calm", "clever", "cosy", "gentle", "golden", "happy", "humble", "jolly", "keen", "lively", "lucky", "merry", "misty", "nimble", "quiet", "rapid", "shy", "silver", "sunny", "swift", "tidy", "witty"];
const NOUNS = ["badger", "comet", "coral", "dolphin", "falcon", "fern", "harbor", "heron", "island", "kelp", "lagoon", "lantern", "maple", "meadow", "otter", "pebble", "puffin", "reef", "river", "seal", "shell", "sparrow", "tide", "walrus", "whale"];
/** A new project's random name, adjective-noun (a number added once the pairs run out). */
export function randomName(taken, home, pick = Math.random) {
  const one = (list) => list[Math.floor(pick() * list.length)];
  for (let i = 0; i < 50; i++) { const name = `${one(ADJECTIVES)}-${one(NOUNS)}`; if (free(name, taken, home)) return name; }
  return freeName(`${one(ADJECTIVES)}-${one(NOUNS)}`, taken, home);
}

/**
 * Counts what Init will import, before it starts: every entry under `source`
 * (no ignore rules, links not followed, as Init itself reads it) and the
 * bytes of its regular files. `report` sees the running counts.
 * @returns {Promise<{ entries: number, files: number, bytes: number }>}
 */
export async function scanSource(source, report = () => {}) {
  const counts = { entries: 1, files: 0, bytes: 0 }, dirs = [source];
  while (dirs.length) {
    const dir = dirs.pop();
    for await (const entry of await opendir(dir)) {
      counts.entries++;
      const path = join(dir, entry.name);
      if (entry.isDirectory()) dirs.push(path);
      else if (entry.isFile()) { counts.files++; counts.bytes += (await lstat(path)).size; }
    }
    report({ ...counts });
  }
  return counts;
}

/** Whether `name` is the simulator project of a demo that runs on Live LayerFS only (`live` in its scenario). */
export function liveOnlyDemo(name, scenarios = SCENARIOS) {
  const id = /^demo-(.+)-sim$/.exec(name ?? "")?.[1];
  if (!id) return false;
  try { return JSON.parse(readFileSync(join(scenarios, id, "scenario.json"), "utf8")).live === true; } catch { return false; }
}

/**
 * Checks an Init request and names its project, without changing anything.
 * `image` gives the project's Sandboxes their own runtime image (a replayed
 * demo's), instead of the Host's.
 * @param {object} spec resolved Host settings
 * @param {import("./binding.js").BindingStore} bindings
 * @param {{ folder: string, source?: string, name?: string, backend?: "sim", image?: string, empty?: boolean }} request
 *   `empty`: a project with nothing in it (an empty folder made here, removed after Init), named at random unless `name` is given
 * @param {Set<string>} [pending] names of Inits still running
 */
export function prepareInit(spec, bindings, { folder, source = folder, name, backend, image, empty = false }, pending = new Set()) {
  if (backend !== undefined && backend !== "sim") throw refuse("invalid-backend", "backend is \"sim\" or omitted");
  if (image !== undefined && (backend === "sim" || !IMAGE.test(image))) throw refuse("invalid-image", "image is a runtime image digest sha256:<64 hex>, for a Live project");
  if (backend === "sim" && liveOnlyDemo(name)) throw refuse("live-only", `${name} is a demo that runs on Live LayerFS only`);
  const missing = backend === "sim" ? [] : missingDeployment(spec);
  if (missing.length) throw refuse("not-configured", `LayerFS is not configured: set ${missing.join(" and ")} for layerfs-host in the profile patch`);
  for (const path of empty ? [folder] : [folder, source]) {
    if (!isAbsolute(path) || !existsSync(path) || !statSync(path).isDirectory()) throw refuse("invalid-folder", `${path} is not an absolute directory`);
  }
  if (name !== undefined && !NAME.test(name)) throw refuse("invalid-name", "a project name is 1-63 lowercase letters, digits, _ . - and starts and ends alphanumeric");
  const taken = new Set([...bindings.allNames(), ...pending]);
  const project = { name: name ?? (empty ? randomName(taken, spec.home) : freeName(nameFrom(source), taken, spec.home)), source, volume: "", created: Date.now() };
  if (taken.has(project.name) || existsSync(join(spec.home, project.name))) throw refuse("name-taken", `a LayerFS project named ${project.name} exists`);
  project.volume = `dsh-layerfs-${project.name}-${project.created.toString(36)}`;
  if (image) project.image = image;
  if (backend === "sim") Object.assign(project, { backend, volume: `sim-${project.name}` });
  if (empty) Object.assign(project, { source: mkdtempSync(join(tmpdir(), "dsh-layerfs-empty-")), empty: true });
  return { folder, project };
}

/**
 * Runs a prepared Init: counts the source, makes the volume, imports the
 * source (LayerFS's Host Init, which seals the Store under the LayerFS home),
 * installs the Store into the volume (a live project's first Sandbox does,
 * and Store calls need it there) and makes it `folder`'s default. `report`
 * sees each step (scan, volume, import, install) and, while LayerFS imports
 * in this process, its counts as `imported`. On macOS the import runs in the
 * LayerFS box (box.js), where no counts are read. One attempt; a failure
 * leaves no project, and the volume and project entry it made are removed.
 */
export async function runInit(spec, bindings, { folder, project }, report = () => {}) {
  try {
    return await initFrom(spec, bindings, { folder, project }, report);
  } finally {
    if (project.empty) rmSync(project.source, { recursive: true, force: true });
  }
}
async function initFrom(spec, bindings, { folder, project }, report) {
  report({ step: "scan" });
  const totals = await scanSource(project.source, (counts) => report({ scanned: counts }));
  report({ step: "volume", totals });
  const docker = ["-H", `unix://${spec.docker}`];
  if (!isSim(project)) await run("docker", [...docker, "volume", "create", project.volume]);
  report({ step: "import" });
  let client, made = false;
  try {
    if (spec.box && !isSim(project)) await ensureBox(spec);
    client = await clientFor(spec, project);
    const init = () => client.layerfs.project.init(project.source);
    await (spec.box && !isSim(project) ? init() : watching(client, report, init));
    made = true;
    if (!isSim(project)) {
      report({ step: "install" });
      await client.layerfs.sandbox.create(`init-${project.created.toString(36)}`, project.name, project.image ?? spec.image);
    }
  } catch (error) {
    if (client) await release(client, { service: true }).catch(() => {});
    if (made && !isSim(project)) rmSync(join(spec.home, project.name), { recursive: true, force: true });
    if (!isSim(project)) await run("docker", [...docker, "volume", "rm", project.volume]).catch(() => {});
    throw error;
  }
  await release(client);
  bindings.addProject(folder, project);
  return project;
}

/**
 * Runs `init`, reading its counts (operator project.progress) every WATCH_MS
 * until it ends. One read at a time; a failed read stops the counts, not Init.
 */
export async function watching(client, report, init) {
  let running = true;
  const watch = (async () => {
    while (running) {
      const counts = await client.operator.project.progress().catch(() => (running = false, null));
      if (counts && running) report({ imported: counts });
      if (running) await pause(WATCH_MS);
    }
  })();
  try {
    return await init();
  } finally {
    running = false;
    await watch;
  }
}

/** Imports `source` (default: the workspace folder) as a LayerFS project, `folder`'s default. */
export const initProject = (spec, bindings, request, report) => runInit(spec, bindings, prepareInit(spec, bindings, request), report);
