// Teardown: terminal unmount and sandbox.close (common/session.mjs).
import { lfs, teardown } from "../../common/session.mjs";

await teardown();
await lfs.close();
