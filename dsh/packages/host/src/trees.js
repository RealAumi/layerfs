// The Host's reads of a project, through one SDK client per project: the
// project's state (inspect.snapshot), its storage (storage.js) and the Files
// pane's reads of saved ids (reads.js). One client means one service Sandbox
// start, so the Host takes the project's discovery lock (which the SDK
// refuses as Busy while another client holds it) once, not per read. The
// client is released after a quiet minute; the service Sandbox, shared with
// the agents' scripts, stays open. Saved ids never change, so a Files read is
// kept (the newest KEEP_READS of them).
import { clientFor, release, stateOf } from "./layerfs-client.js";
import { READS } from "./reads.js";
import { storageOf } from "./storage.js";

const IDLE_MS = 60_000;
/** Files reads kept (reads.js): each at most a page of 1000 names or a 48 KiB window. */
const KEEP_READS = 500;

export class TreeReader {
  /** @param {object} spec @param {(project: object) => Promise<object>} [open] a project's SDK client */
  constructor(spec, open = (project) => clientFor(spec, project)) {
    this.spec = spec;
    this.open = open;
    /** project name -> { client: Promise, users, timer } */
    this.clients = new Map();
    /** `${project}\n${kind}\n${args}` -> Promise of a Files read */
    this.reads = new Map();
  }

  /** One Files read of saved ids (reads.js: list, read, changes, diff); kept, unless it fails. */
  files(project, kind, query) {
    const r = READS[kind], args = r.args(query), key = `${project.name}\n${kind}\n${JSON.stringify(args)}`;
    const kept = this.reads.get(key);
    if (kept) { this.reads.delete(key); this.reads.set(key, kept); return kept; }
    const reading = this.use(project, (client) => r.run(client, args));
    this.reads.set(key, reading);
    reading.catch(() => this.reads.delete(key));
    while (this.reads.size > KEEP_READS) this.reads.delete(this.reads.keys().next().value);
    return reading;
  }

  /** The project's state as the views draw it; see stateOf. */
  state(project, sandboxes) {
    return this.use(project, (client) => stateOf(client, sandboxes));
  }

  /** What the project's Store holds and what made it; see storageOf. */
  storage(project) {
    return this.use(project, storageOf);
  }

  async use(project, fn) {
    let entry = this.clients.get(project.name);
    if (!entry) {
      entry = { client: this.open(project), users: 0, timer: null };
      this.clients.set(project.name, entry);
      entry.client.catch(() => { if (this.clients.get(project.name) === entry) this.clients.delete(project.name); });
    }
    clearTimeout(entry.timer);
    entry.users++;
    try {
      return await fn(await entry.client);
    } catch (error) {
      // the project's service Sandbox is shared, and any client may close it: this
      // client can't use it again, so the next read starts a new one
      if (error?.code === "NoSuchSandbox" && /_service\./.test(error.message ?? "") && this.clients.get(project.name) === entry) {
        this.clients.delete(project.name);
        clearTimeout(entry.timer);
        // its container is gone (removed outside LayerFS), so nothing can be
        // using it: closing it frees its name. This read still fails; the next
        // one starts a new service Sandbox.
        if (error.detail?.containerGone) {
          const { layerfs } = await entry.client;
          await layerfs.sandbox.close(error.detail.sandbox).catch((closing) => console.warn(`LayerFS: could not close ${error.detail.sandbox}, whose container is gone: ${closing.message}`));
        }
      }
      throw error;
    } finally {
      if (--entry.users === 0 && this.clients.get(project.name) === entry) {
        entry.timer = setTimeout(() => this.drop(project.name, entry), IDLE_MS);
        entry.timer.unref?.();
      }
    }
  }

  async drop(name, entry) {
    if (this.clients.get(name) !== entry || entry.users) return;
    this.clients.delete(name);
    await release(await entry.client).catch(() => {});
  }

  /** Drops a project's kept reads and releases its client now (before removal). */
  async forget(name) {
    for (const key of [...this.reads.keys()]) if (key.startsWith(`${name}\n`)) this.reads.delete(key);
    const entry = this.clients.get(name);
    if (!entry) return;
    this.clients.delete(name);
    clearTimeout(entry.timer);
    await entry.client.then((client) => release(client, { service: true })).catch(() => {});
  }

  /** Releases every client; runs with the plugin fiber. */
  async dispose() {
    const entries = [...this.clients.entries()];
    this.clients.clear();
    for (const [, entry] of entries) {
      clearTimeout(entry.timer);
      await entry.client.then(release).catch(() => {});
    }
  }
}
