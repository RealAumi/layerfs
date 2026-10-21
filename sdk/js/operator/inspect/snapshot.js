// One internal read model over the client's current service and Sandboxes.
import { invokeOperator, sandboxArgs } from "../../src/client.js";

export async function snapshot(client, since) {
  const service = await client.service();
  const ids = [...new Set([service, ...client.sandboxes])];
  const answers = await Promise.all(ids.map((sandbox) => invokeOperator("operator.inspect.snapshot", sandboxArgs(client, sandbox), client.options)));
  await Promise.all(answers.map(async (answer, index) => {
    await Promise.all(answer.workspaces.filter(w => w.mounted && w.directory).map(async workspace => {
      workspace.overlay = await invokeOperator("operator.workspace.overlay", { ...sandboxArgs(client, ids[index]), path: workspace.directory }, client.options);
    }));
  }));
  const version = answers.map((answer) => answer.version).join(".");
  if (since === version) return { kind: "unchanged", version };
  const history = answers[0];
  return {
    kind: "ok", version, project: history.project, store: history.store,
    branches: history.branches, moreBranches: history.moreBranches, commits: history.commits, more: history.more,
    layers: history.layers, moreLayers: history.moreLayers,
    sandboxes: ids.map((id, index) => ({
      id, status: "Ready",
      workspaces: answers[index].workspaces.map((workspace) => ({ ...workspace, path: workspace.directory })),
    })),
  };
}
