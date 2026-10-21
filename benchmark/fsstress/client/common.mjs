// Shared by the fsstress clients: one sandbox.exec whose stdout is one JSON
// line (a failure is logged to failures.jsonl and stops the client), and
// the read-back of a Sandbox file into the run folder in base64 pieces
// that fit sandbox.exec's 1 MiB stream, checked against its sha256.
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { append, exec, home } from "../../common/session.mjs";

/** Raw bytes per read-back exec: 700,000 B is 933,336 base64 characters. */
const PIECE = 700000;

/** One exec that must exit 0 untruncated and print one JSON line. */
export async function execJson(path, command) {
  const r = await exec(path, command);
  if (r.exitCode !== 0 || r.truncated) {
    append("failures.jsonl", { command, ...r, stdout: r.stdout.slice(0, 4000), stderr: r.stderr.slice(0, 4000) });
    throw new Error(`exec failed: ${command} exit ${r.exitCode}`);
  }
  return { ms: r.ms, json: JSON.parse(r.stdout.trim().split("\n").pop()), stderr: r.stderr.slice(0, 4000) };
}

/** Copy Sandbox file REMOTE (BYTES long, SHA256) to RUN/LOCAL; returns the exec count and time. */
export async function readBack(path, remote, bytes, sha256, local) {
  const parts = [];
  let ms = 0;
  for (let offset = 0; offset < bytes; offset += PIECE) {
    const r = await exec(path, `tail -c +${offset + 1} '${remote}' | head -c ${PIECE} | base64 -w0`);
    if (r.exitCode !== 0 || r.truncated) throw new Error(`read-back of ${remote} at ${offset} failed: exit ${r.exitCode}`);
    parts.push(Buffer.from(r.stdout, "base64"));
    ms += r.ms;
  }
  const data = Buffer.concat(parts);
  const got = createHash("sha256").update(data).digest("hex");
  if (data.length !== bytes || got !== sha256) throw new Error(`read-back of ${remote}: ${data.length} B sha256 ${got}, expected ${bytes} B ${sha256}`);
  mkdirSync(dirname(join(home, local)), { recursive: true });
  writeFileSync(join(home, local), data);
  return { execs: parts.length, ms: +ms.toFixed(3) };
}
