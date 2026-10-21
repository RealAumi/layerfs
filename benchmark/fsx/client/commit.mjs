// After every case: one sandbox.commit of the Workspace (timed, with its
// result in ledger.jsonl), to show it still commits what fsx left there.
import { commit, lfs, session } from "../../common/session.mjs";

const { path } = session();
await commit(path, "fsx: files left by every case");
await lfs.close();
