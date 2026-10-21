// After every layerfs job: one sandbox.commit of the Workspace (timed, with
// its result and counters in ledger.jsonl), the Commit cost of the three
// data files the layerfs jobs wrote. It runs in its own client, outside
// every timed job.
import { commit, lfs, session } from "../../common/session.mjs";

const { path } = session();
await commit(path, "fio: data files after the layerfs jobs");
await lfs.close();
