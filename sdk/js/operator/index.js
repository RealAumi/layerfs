// Internal operator surface; public dispatch cannot admit these names.
import { snapshot } from "./inspect/snapshot.js";
import { invokeOperator, sandboxArgs, page } from "../src/client.js";
export class LayerFSOperator {
  constructor(client) {
    // Workspace and process calls go to the named Sandbox; Store calls run in
    // this process against the client's Store.
    const call = async (method, args = {}, sandbox) => sandbox
      ? invokeOperator(`operator.${method}`, { ...args, ...sandboxArgs(client, sandbox) }, client.options)
      : (await client.store(), invokeOperator(`operator.${method}`, { ...args, project: client.projectName, home: client.options.home, storePath: client.options.storePath }, client.options));
    this.store = {
      stats: async () => { const v = await call("store.stats"); return { ...v, dedupe: v.dedupe === null ? null : Number(v.dedupe), compression: v.compression === null ? null : Number(v.compression) }; },
      commits: (branch, pageSize, pagePos) => call("store.commits", { branch, ...page(pageSize,pagePos) }),
      // every Layer one publication overwrote, newest first, one page
      overwritten: (layer, pageSize, pagePos) => call("store.overwritten", { layer, ...page(pageSize,pagePos) }),
    };
    this.files = {
      stats: (ref,path) => call("files.stats", { branch: ref,path }),
      history: (ref,path,pageSize,pagePos) => call("files.history", { branch:ref,path,...page(pageSize,pagePos) }),
    };
    this.workspace = {
      overlay: (sandbox,path) => call("workspace.overlay", { path }, sandbox),
      changes: (sandbox,path,pageSize,pagePos) => call("workspace.changes", { path,...page(pageSize,pagePos) },sandbox),
    };
    this.inspect = { snapshot: (since) => snapshot(client,since) };
    // the running Init of this project, read while project.init runs (no Sandbox): { step, entries, files, bytes } or null
    this.project = { progress: () => invokeOperator("operator.project.progress", { project: client.projectName }, client.options) };
    this.process = {
      start: (sandbox,path,command) => call("process.start", { path,command,background:true },sandbox),
      list: (sandbox) => call("process.list", {},sandbox),
      cancel: (sandbox,process) => call("process.cancel", { process },sandbox),
    };
  }
}
