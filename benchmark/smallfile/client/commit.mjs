// After the layerfs create: one sandbox.commit of the Workspace (timed, with
// its result and counters in ledger.jsonl), the Commit cost of the files
// smallfile created. It runs in its own client, outside every timed op.
import { commit, lfs, session } from "../../common/session.mjs";

const { path } = session();
await commit(path, "smallfile: files after create");
await lfs.close();
