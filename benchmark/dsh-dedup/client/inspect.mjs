// Reads a closed Store's totals and object counts per role, read-only.
//   inspect.mjs STORE_PATH
import { DatabaseSync } from "node:sqlite";

const db = new DatabaseSync(process.argv[2], { readOnly: true });
const all = (sql) => db.prepare(sql).all();
console.log(JSON.stringify({
  policy: all("SELECT * FROM store_policy"),
  totals: all("SELECT * FROM store_totals"),
  roles: all("SELECT role, count(*) AS objects, sum(canonical_length) AS canonical FROM object_location GROUP BY role ORDER BY role"),
  signatures: all("SELECT count(*) AS n FROM content_signature")[0].n,
  pages: all("PRAGMA page_count")[0], page_size: all("PRAGMA page_size")[0],
}));
db.close();
