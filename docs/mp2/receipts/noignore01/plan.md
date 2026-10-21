# noignore01 prospective selection

> **Status: Research; informative and not a product contract.**

Local single-sample exploratory comparison; no release admission. User's selected
remote Store prototype, one Linux VM, Disposable only, one construction worker.
Off source af9f2cec80b19d4613eec1e48b79c8a1cff93e14; on source
801e9360fdbd177e8e126b89f2730bb9b5213d44. Rust 1.85.1, release, ARM64.
Only public repository sources/registries. No production changes.

Workloads selected before sampling:
- Node: nestjs/nest, commit 35c3ded6dbf3f23f917ae88d0ed966932788cae6
  (peeled v11.1.6), npm ci; npm run build; npm test. Installed file count
  is not yet qualified against 30,000–150,000.
- Maven: spring-projects/spring-petclinic,
  500158f732419217507c7656904b8e6aa1bcc0d6 (HEAD resolution on 2026-10-21),
  Maven public dependency download, package with tests skipped, offline unit
  test selection. Exact test selection requires inspecting the pinned tree.

Rows: S1 shared warm-base (clone/install/build/explicit Commit); S2 fresh empty
client cache fork/test, off/on; S3 10 sequential source edits/builds/Commits per
arm; S4 clean build/Commit, off/on; S5 dependency addition/install/Commit,
off/on; S6 fresh-container resume, off/on; S7 two generated-path forks/merge
and source conflict control, off; S8 Maven external shared cache and internal
`.m2`, off. Keep all unrun rows visible if any prerequisite fails.

S1 base builder has ignore off. `/.lww` contains `%include .gitignore`; exclude
`.lww` in `.git/info/exclude`. S8 internal `.m2` additionally appears in both
`.git/info/exclude` and `/.lww`.

Primary Commit boundary: explicit remote control call, product's `wall_ns`
(handshake/control to reply); external command wall separately. Upload:
acknowledged canonical payload bytes (`uploadedBytes`), excludes framing.
Fetch: Store-link network bytes and empty canonical-cache content growth are
separate quantities, never presented as identical. Store growth: main SQLite
plus WAL physical/logical size deltas, report exact byte basis. Workspace files
and logical bytes counted after timing, never before fresh first access.

Fresh-machine cold means new daemon/container, empty local object cache and
package-manager home. Server OS cache is not cold; no host-global cache drop.
Same-mount edit/build rows are intentionally warm workflow diagnostics, not
cold performance admission. No repeated treatment samples. Independent
measurement arms get cloned closed Store inputs and private writable resources.

Every test uses explicit <=120 second timeout. Construction/Commit uses one
worker. Public control CLI's existing deadlines remain unchanged. A failed
product prerequisite stops the job; no product repair, replay, or success
substitution. Preparatory harness failures are retained and are not workload
samples. No numeric speed comparison without both completed arms.
