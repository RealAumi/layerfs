// Setup: project.init of the run's one-file seed, sandbox.create on the
// fsstress image, the run's own Branch forked from main, sandbox.mount
// (common/session.mjs setup), then one exec recording the Sandbox's
// fsstress identity and the Workspace root it will write in.
//
//   setup.mjs SEED_DIR
import { append, lfs, setup } from "../../common/session.mjs";
import { execJson } from "./common.mjs";

const { path } = await setup(process.argv[2]);
const probe = await execJson(path, `python3 -c 'import hashlib, json, os, platform, subprocess; print(json.dumps({"uid": os.getuid(), "gid": os.getgid(), "kernel": platform.release(), "fsstress_sha256": hashlib.sha256(open("/usr/local/bin/fsstress", "rb").read()).hexdigest(), "workspace": os.listdir("${path}"), "mounts": [" ".join(l.split()[1:4]) if l.split()[1].startswith("/workspaces") else " ".join(l.split()[1:3]) for l in open("/proc/mounts").read().splitlines() if l.split()[1] in ("/", "/tmp") or l.split()[1].startswith("/workspaces")]}))'`);
append("ledger.jsonl", { step: "probe", ms: probe.ms, ...probe.json });
await lfs.close();
