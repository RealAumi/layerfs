// Project bindings: the LayerFS projects, each dsh workspace folder's default
// project (the one chosen there last), which project each root session uses,
// and the names of the agents seen. A session may use any project; the folder
// only remembers a default. One JSON file under the state directory, replaced
// atomically on every change.
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

/**
 * @typedef {object} Project
 * @property {string} name LayerFS project name (also its LayerFS home entry)
 * @property {string} source the folder Init imported
 * @property {string} volume Docker volume holding the project's Store
 * @property {"sim"} [backend] "sim": a simulated project (sim/), with no volume
 * @property {number} created Unix epoch milliseconds
 */

/**
 * Version 1 kept each folder's projects in the folder; version 2 kept projects
 * by name, each attached to a folder; version 3 keeps only each folder's
 * default. A folder whose one attached project was its default by being the
 * only one keeps it as the default.
 */
function upgrade(data) {
  if (data.version === 3) return data;
  const projects = {}, workspaces = {}, attached = {};
  const add = (p, folder) => { const { folder: _, ...rest } = p; projects[p.name] = rest; if (folder) (attached[folder] ||= []).push(p.name); };
  if (data.version === 1) {
    for (const [folder, w] of Object.entries(data.workspaces)) { for (const p of w.projects) add(p, folder); workspaces[folder] = { lastUsed: w.lastUsed ?? null }; }
  } else {
    for (const p of Object.values(data.projects)) add(p, p.folder);
    for (const [folder, w] of Object.entries(data.workspaces)) workspaces[folder] = { lastUsed: w.lastUsed ?? null };
  }
  for (const [folder, names] of Object.entries(attached)) if (names.length === 1) (workspaces[folder] ||= { lastUsed: null }).lastUsed ??= names[0];
  return { ...data, version: 3, projects, workspaces };
}

export class BindingStore {
  /** @param {string} stateDir */
  constructor(stateDir) {
    this.file = join(stateDir, "bindings.json");
    this.data = existsSync(this.file) ? upgrade(JSON.parse(readFileSync(this.file, "utf8"))) : { version: 3, projects: {}, workspaces: {}, sessions: {}, agents: {} };
  }

  save() {
    const tmp = `${this.file}.${process.pid}.tmp`;
    writeFileSync(tmp, JSON.stringify(this.data, null, 1) + "\n");
    renameSync(tmp, this.file);
  }

  /**
   * Every project a session in `folder` may use, those imported from the
   * folder first, and the folder's default.
   * @param {string} folder @returns {{ projects: Project[], lastUsed: string|null }}
   */
  workspace(folder) {
    const all = this.projects(), lastUsed = this.data.workspaces[folder]?.lastUsed ?? null;
    return { projects: [...all.filter((p) => p.source === folder), ...all.filter((p) => p.source !== folder)], lastUsed };
  }

  /** Each workspace folder's default project, as { folder: name }. */
  defaults() {
    return Object.fromEntries(Object.entries(this.data.workspaces).filter(([, w]) => w.lastUsed).map(([folder, w]) => [folder, w.lastUsed]));
  }

  /** @returns {Project[]} every project, oldest first */
  projects() {
    return Object.values(this.data.projects).sort((a, b) => a.created - b.created);
  }

  /** Every project name: names are unique per LayerFS home. */
  allNames() {
    return new Set(Object.keys(this.data.projects));
  }

  /** Adds a project, as the default of the folder it was imported for. @param {string} folder @param {Project} project */
  addProject(folder, project) {
    this.data.projects[project.name] = project;
    this.setDefault(folder, project.name);
  }

  /** @param {string} name @returns {Project|null} */
  byName(name) {
    return Object.hasOwn(this.data.projects, name) ? this.data.projects[name] : null;
  }

  /**
   * Makes a project the default of a workspace folder: a new session there
   * uses it until it chooses another. Sessions that already chose keep theirs.
   * @param {string} folder @param {string} name
   */
  setDefault(folder, name) {
    if (!this.byName(name)) throw Object.assign(new Error(`no LayerFS project named ${name}`), { code: "not-found", status: 404 });
    (this.data.workspaces[folder] ||= { lastUsed: null }).lastUsed = name;
    this.save();
  }

  /** The session's own choice: { project, locked, folder }, or null before one is made. */
  session(rootId) {
    return this.data.sessions[rootId] ?? null;
  }

  /**
   * The project a root session uses: its choice, else its folder's default.
   * Null when neither names one (a session without LayerFS).
   * @param {string} rootId @param {string|undefined} folder @returns {Project|null}
   */
  projectFor(rootId, folder) {
    const chosen = this.session(rootId);
    if (chosen) return chosen.project ? this.byName(chosen.project) : null;
    const name = folder ? this.data.workspaces[folder]?.lastUsed : null;
    return name ? this.byName(name) : null;
  }

  /**
   * Chooses a session's project (null: no LayerFS), any project; a project
   * also becomes the folder's default. Refused once locked.
   * @returns {boolean} whether the choice was taken
   */
  choose(rootId, folder, name) {
    const current = this.session(rootId);
    if (current && current.locked) return false;
    if (name !== null && !this.byName(name)) throw Object.assign(new Error(`no LayerFS project named ${name}`), { code: "not-found" });
    this.data.sessions[rootId] = { project: name, locked: false, folder };
    if (name !== null) (this.data.workspaces[folder] ||= { lastUsed: null }).lastUsed = name;
    this.save();
    return true;
  }

  /**
   * Forgets a removed project: no folder uses it, and sessions that chose it
   * have no project (a later project of the same name is not theirs).
   * @param {string} name
   */
  remove(name) {
    delete this.data.projects[name];
    for (const w of Object.values(this.data.workspaces)) if (w.lastUsed === name) w.lastUsed = null;
    for (const choice of Object.values(this.data.sessions)) if (choice.project === name) choice.project = null;
    this.save();
  }

  /** Locks a session's project at its first LayerFS-bound bash call. */
  lock(rootId, name, folder) {
    const current = this.session(rootId);
    if (current && current.locked) return;
    this.data.sessions[rootId] = { project: name, locked: true, folder };
    this.save();
  }

  /** @param {string} sessionId @returns {{ root: string, name: string }|null} */
  agent(sessionId) {
    return this.data.agents[sessionId] ?? null;
  }

  /** Records an agent's root session and display name. */
  setAgent(sessionId, root, name) {
    const known = this.data.agents[sessionId];
    if (known && known.root === root && known.name === name) return;
    this.data.agents[sessionId] = { root, name };
    this.save();
  }

  /** Agents of one root session, as { id: name }. */
  agentsOf(rootId) {
    return Object.fromEntries(Object.entries(this.data.agents).filter(([, a]) => a.root === rootId).map(([id, a]) => [id, a.name]));
  }
}
