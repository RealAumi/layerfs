# Ignore restart baseline

> **Status: Dated failure evidence; restore is not implemented.**

Product: **42f8a5ebb**, using the exact ignore05/06 Linux binaries. Every binary
SHA-256 was verified against ignore06 before copying host files into
`~/.cache/cxi-ignore-e2e/bin`; see `tested-identities.txt`. No `ign-*` Docker
resource was accessed. The checkout's parent is 4c394e3fb, whose changes since
42f8a5ebb are documentation/harness/receipts only. No production changes were
made. `harness-first.py` preserves the first executed harness; subsequent
subdirectories preserve their own executed versions.

All runs used this Mac's OrbStack, Disposable Store, one construction worker,
and exclusively `cxi-` containers, networks and volumes. These are correctness
checks, not performance measurements. The 1.85.1 binaries were reused without a
build. Each invocation had a 120-second outer timeout; none reached it.

## Runs, in order

1. `IGN_RECEIPTS=ignore07 timeout 120s python3 -B docs/mp2/run-ignore-e2e.py restart`
   — **FAIL**, 18/21 checks. Remount succeeded, but both ignored files disappeared.
   The kill/restart prelude also committed successfully. Restart then refused
   startup with `Overlay(Io(... AlreadyExists ...))`: the configured overlay
   template already existed. This is the first run, retained unchanged.
2. After diagnosing `layerfs-overlay/src/database/startup.rs::initialize`
   (`create_new(true)`), changed only the harness restart setup to select a new
   disposable overlay path while retaining the cache.
   `IGN_RECEIPTS=ignore07/fresh-overlay IGN_RESTART_ONLY=1 timeout 120s python3 -B docs/mp2/run-ignore-e2e.py restart`
   — **FAIL**, 7/8 checks. Daemon readiness succeeded; attaching the new Workspace
   refused `attach:mount`, `Directory: File exists`. The old mount directory
   survived in the container filesystem and the restarted namespace began at 1.
3. After that diagnosis, the harness also selected a new mount directory root.
   `IGN_RECEIPTS=ignore07/fresh-process-paths IGN_RESTART_ONLY=1 timeout 120s python3 -B docs/mp2/run-ignore-e2e.py restart`
   — **FAIL**, 10/12 checks. Restart and new mount succeeded. Both ignored files
   disappeared, while tracked content survived exactly.

Runs 2 and 3 select only restart; the already observed remount case was not
rerun. Each has its own logs, JSONL commands, results and binary identities.
Neither failed startup attempt is replaced by the final observation. The
harness historically exits 0 after recording failed assertions; `results.json`
and console checks are the verdict, not the process exit status.

| Path | Before each Commit/removal | After remount (run 1) | After restart (run 3) |
| --- | --- | --- | --- |
| `.gitignore` | `node_modules/\ntarget/\n` | exact | exact |
| `src/restart.txt` | `tracked at last Commit\n` | exact | exact |
| `node_modules/restart/index.js` | `module.exports = "local dependency";\n` | missing | missing |
| `target/restart.bin` | `local build output\n` | missing | missing |

Every prelude verified that the tracked edit was published and that both ignored
paths were absent from the published head. The actual path bytes and presence
flags are in each `results.json` under `facts.restart_inventory`. The daemon
was killed with SIGKILL while its committed Workspace was still mounted; Docker
restarted that container with the same cache volume. Old overlay and mount paths
were left untouched until whole-run resource cleanup. No overlay recovery or
FUSE teardown changes were made.

## Budget stop: proposed implementation, not built

The owner permits stopping after reproduction if restore needs substantially more
than about 250 production lines. Source review estimates **350–450 nonblank,
non-comment production lines**, excluding tests and documentation:

| Responsibility | Estimated added/changed production lines |
| --- | ---: |
| Optional key through creation control/codec, API/CLI and bind request | 45–60 |
| Live key admission/lease, refusal and release with existing ownership | 45–60 |
| Restore record/seed codec and transactional cache access | 100–125 |
| Reachability evidence, missing/corrupt local-object validation and status | 85–110 |
| Restore binding and post-install Commit integration/error handling | 75–95 |
| Total | 350–450 |

These are planning estimates, not a measured patch or per-file LOC listing.
No production implementation was started, and there is no ignore08 run.

Proposed key: optional caller-supplied `restore_key` on remote Workspace creation
(the prototype's `Mount` request), scoped by cache, Store scope and Branch.
The current `WorkspaceId` is explicitly an incarnation; the CLI generates a new
one on every mount. A daemon's key does not distinguish multiple Workspaces.
Neither is an appropriate implicit restore key. Absence must keep today's
behavior, and ignore-off must bypass restore. A lease must cover admission,
binding, live use and retained uncertain custody; ordinary successful close can
release it through the existing owner lifetime without changing teardown.

The record should contain `L`, its published partner, pending seeds, and the
**original BranchSnapshot** (existing bridge snapshot codec is reusable). Merely
mounting `L` under a freshly fetched head is incorrect: `commit_remote` sends the
binding to the server, so using the new head would skip the moved-head merge and
could overwrite kept changes made while down.

Use one new `CREATE TABLE IF NOT EXISTS` in cache SQLite, without version changes.
After successful install, atomically replace that key's record and a manifest of
its reachable local-only object IDs. Reuse the existing closure traversal to
produce the manifest while objects are known present. The upload traversal alone
is not a restore validator: `Cache::local` deliberately returns `None` for both
remote objects and missing rows. A missing local leaf, or even a missing `L`,
would otherwise be silently skipped. Validate manifest presence and canonical
identity before selecting `L`; remote objects remain demand fetchable. Decode,
identity and missing-object failures need explicit fallback status, including
`missing-local-objects`, and must select a fresh published-head binding without
restoring seeds from the rejected record. Hints rebuild through the existing walk.

The persistence write must occur after install and use existing failure custody
if it fails; this does not authorize a post-publication recovery protocol.
Uncommitted overlay recovery, eviction/GC, ctime and teardown remain excluded.
The six requested restore cases and the full ignore08 run remain **NOT_RUN**.

## Checks and cleanup

Python syntax and AST comparison verify that all ten existing scenario functions
are unchanged. The fuser integrity check passed before baseline execution. Rust
unit tests/clippy were not rerun: no product, dependency or Rust test code changed.
Whitespace check reports two trailing spaces in the first raw console/invocation
logs (the stopped daemon yielded an empty diagnostic count); these original
receipts are preserved byte-for-byte. Maintained source/docs are whitespace-clean.
All created `cxi-` containers, networks and volumes were removed after every run;
`cleanup.json` is the final empty inventory. No cargo target volume was created
or retained (binary reuse needed none). Other owners' resources were untouched.

## Production LOC

Production LOC: **108,828 → 108,828 (delta +0)**. Core 99,919; SDK 2,861;
dsh 6,048. Reference absent (retired R9c; last counted 65,417 at tree
`498dd1917812`). Only documentation, the Python harness and receipts changed.

Method: counter `tools/production_loc.py` pinned at `4c394e3fb`, run with
`--root <export> --json` on separate `git archive <revision> core/crates sdk/js
dsh/packages` exports of the first parent and final staged tree (`git write-tree`).
The counter excludes tests/fixtures and inline test items. The staged production
subtree identities are also checked unchanged before committing. This is source
size, not performance evidence.
