// Finish: the run Branch's Commit list, then sandbox.close and close.
// A page ends at the reply budget as well as at pageSize, so the list
// follows nextPagePos until hasMore is false, and must hold every Commit
// the ledger recorded.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { BRANCH, home, lfs, rows, SANDBOX } from "./common.mjs";

const items = [];
for (let pos = 0; ; ) {
  const page = await lfs.branch.list_commits(BRANCH, 1000, pos);
  items.push(...page.items);
  if (!page.hasMore) break;
  pos = page.nextPagePos;
}
writeFileSync(join(home, "commits.json"), JSON.stringify(items, null, 1));
const ledger = rows("ledger.jsonl").filter((r) => r.commit).map((r) => r.commit);
const listed = new Set(items.map((c) => c.id));
const missing = ledger.filter((id) => !listed.has(id));
console.log(JSON.stringify({ commits: items.length, ledger: ledger.length, missing: missing.length, closed: await lfs.sandbox.close(SANDBOX) }));
await lfs.close();
if (missing.length || items.length !== ledger.length) throw new Error(`Commit list ${items.length} does not match the ledger's ${ledger.length}`);
