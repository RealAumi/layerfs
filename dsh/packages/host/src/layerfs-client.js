// LayerFS SDK clients the Host uses for a project: Init, and the project
// state the views draw (inspect.snapshot through the model's mirror). The
// SDK captures its deployment from the environment at construction, so the
// project's settings are set for that synchronous step only. A simulated
// project (backend "sim") has a client of the simulator instead (sim/).
import { Mirror } from "@dsh-layerfs/model/mirror.js";
import { DAEMON_HOST, storePathOf } from "./box.js";
import { simClient } from "./sim/client.js";

export const isSim = (project) => project.backend === "sim";

/** The environment one project's SDK client and its agents' bash calls use. */
export function deploymentEnv(spec, project) {
  // the SDK asks for every deployment setting and, for Store calls, a Store
  // path (#352 F-020); a simulated project uses none of them
  if (isSim(project)) return { HOME: spec.home, DOCKER: "sim", IMAGE: "sim", DAEMON: "sim", VOLUME: project.volume, STORE_PATH: "sim" };
  return {
    HOME: spec.home,
    DOCKER: spec.docker,
    IMAGE: project.image ?? spec.image ?? "",
    DAEMON: spec.daemon ?? "",
    VOLUME: project.volume,
    // macOS: the calls run in the LayerFS box, which sees the volume under
    // Docker's volume directory and Sandbox daemons at the Docker host
    ...(spec.box ? { STORE_PATH: storePathOf(project.volume), DAEMON_HOST, BOX: spec.box, BUNDLE: spec.bundle } : {}),
  };
}

/** Constructs a LayerFS client and operator for one project. */
export async function clientFor(spec, project) {
  if (isSim(project)) return simClient(spec.home, project.name);
  const { LayerFS } = await import(spec.sdk);
  const { LayerFSOperator } = await import(spec.operator);
  const env = deploymentEnv(spec, project), saved = {};
  for (const [name, value] of Object.entries(env)) { saved[name] = process.env[`LAYERFS_${name}`]; process.env[`LAYERFS_${name}`] = value; }
  try {
    const layerfs = new LayerFS(project.name);
    return { layerfs, operator: new LayerFSOperator(layerfs) };
  } finally {
    for (const [name, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[`LAYERFS_${name}`];
      else process.env[`LAYERFS_${name}`] = value;
    }
  }
}

/**
 * Releases a Host client: closes the Sandboxes it opened and its Store. The
 * project's service Sandbox (`_service.<project>`) is shared with every agent
 * script, so it stays open unless `service` is set: for a removal or a failed
 * Init, whose volume must have no running container.
 */
export async function release({ layerfs }, { service = false } = {}) {
  for (const id of [...layerfs.sandboxes]) if (service || !id.startsWith("_service.")) await layerfs.sandbox.close(id);
  await layerfs.close?.();
}

/**
 * The project as the views draw it: the mirror of one inspect.snapshot, with
 * the Sandboxes the traced calls created (ids from the trace lines). Read
 * through the Host's shared client for the project (TreeReader.use), so the
 * Host does not start and close a service Sandbox per read.
 * @param {object} client a project's client @param {string[]} sandboxes real Sandbox ids
 */
export async function stateOf(client, sandboxes) {
  const snap = await olderCommits(client.layerfs, await client.operator.inspect.snapshot());
  const m = new Mirror(), boxes = [];
  for (const real of sandboxes) {
    const listed = (snap.sandboxes || []).find((x) => x.id === real);
    boxes.push({ label: m.label("sb", real), real, closed: !listed, workspaces: {}, processes: [] });
  }
  m.absorb(snap, boxes);
  return { s: { ...m.s, roots: {} }, labels: Object.fromEntries(m.toLabel) };
}

/**
 * The snapshot holds only each Branch's newest Commits (a few per Branch, to
 * fit one answer) and names in `more` every Branch it cut short; the rest come
 * from branch.list_commits, so History shows every Commit and links each to
 * its parent. A Commit another Branch already listed comes once.
 */
async function olderCommits(layerfs, snap) {
  const cut = Object.keys(snap.more || {});
  if (!cut.length) return snap;
  const commits = [...snap.commits], seen = new Set(commits.map((c) => c.id));
  for (const branch of cut) {
    for (let pos = 0; pos !== null;) {
      const page = await layerfs.branch.list_commits(branch, LIST_PAGE, pos);
      for (const c of page.items) if (!seen.has(c.id)) { seen.add(c.id); commits.push(c); }
      pos = page.hasMore ? page.nextPagePos : null;
    }
  }
  return { ...snap, commits, more: {} };
}
const LIST_PAGE = 50;
