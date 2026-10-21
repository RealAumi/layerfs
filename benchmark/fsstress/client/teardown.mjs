// Teardown: terminal unmount of the run's Workspace and sandbox.close
// (common/session.mjs teardown).
import { lfs, teardown } from "../../common/session.mjs";

await teardown();
await lfs.close();
