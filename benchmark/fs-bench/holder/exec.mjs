// One sandbox.exec call through the public JavaScript SDK, for run.sh's `sdk`
// mode: the command arrives on stdin and the outcome leaves as one JSON line
// on stdout ({ exitCode, stdout, stderr, truncated }). The Sandbox is the
// holder's, found by its id from the shared LAYERFS_HOME (see client.sh). A
// refusal exits 3 with its code and message on stderr; nothing is retried.
import { LayerFS } from "../../../sdk/js/src/index.js";

const [sandbox, path] = process.argv.slice(2);
if (!sandbox || !path) throw new Error("usage: exec.mjs SANDBOX PATH < command");
process.stdin.setEncoding("utf8");
let command = "";
for await (const chunk of process.stdin) command += chunk;

const layerfs = new LayerFS(process.env.FS_BENCH_PROJECT);
try {
  const run = await layerfs.sandbox.exec(sandbox, path, command);
  const { exitCode, stdout, stderr, truncated } = run;
  process.stdout.write(`${JSON.stringify({ exitCode, stdout, stderr, truncated })}\n`);
} catch (error) {
  process.stderr.write(`${error.code ?? "Error"}: ${error.message}\n`);
  process.exitCode = 3;
} finally {
  await layerfs.close();
}
