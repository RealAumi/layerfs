// Between the commit pass's create-only (-C) and removal-only (-r) cases:
// one sandbox.commit of the Workspace (timed, with its result in
// ledger.jsonl) that captures the files the create left.
import { commit, lfs, session } from "../../common/session.mjs";

const { path } = session();
await commit(path, "mdtest: files left by the create-only pass");
await lfs.close();
