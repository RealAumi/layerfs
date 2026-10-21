// `sandbox.close`: stops and deletes the container; refused while Workspaces are mounted.
// A container Docker no longer has is already gone, and only its records are removed.
import { invokeClient, sandboxId } from "../client.js";

/** `sandbox.close(sandbox)`: `{ kind: "Closed" }`; `MountsActive`, `Busy`. */
export async function close(client, sandbox) {
  const id = sandboxId(sandbox);
  const value = await invokeClient(client, "sandbox.close", { sandbox: id });
  client.sandboxes.delete(id);
  return value;
}
