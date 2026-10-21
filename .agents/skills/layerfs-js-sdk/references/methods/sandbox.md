# sandbox methods

> **Status:** Current general guide. Part of the `layerfs-js-sdk` skill. Examples were
> captured live in issue #334 Phase A at `b30e4fb8f`. Opaque IDs are shortened;
> the full replies and trace are in `core/target/issue334/phase-a/`.

A Sandbox is one container with one LayerFS daemon. A Workspace is a complete, writable
view of a Branch mounted inside it, where ordinary commands run. **Use the Sandbox for
Bash commands** (install, build, test, run, generators, changes across many files);
every file a command changes is recorded at the Commit. For one small read or edit,
[`fs.*`](fs-read.md) is cheaper. Examples follow
[SKILL.md](../../SKILL.md#one-script-for-each-group): `layerfs` is the client, `id` a
Sandbox name and `path` a mounted Workspace of the Branch `"work"`, as `mount` returned it.

**Shared rules**

- A Sandbox's id is the name you gave it at `create`. It persists: any later process
  with the same `LAYERFS_HOME` can use it and its mount paths.
- A Sandbox belongs to one project and one image for its whole life. It can hold
  several Workspaces at once, each mounted from any Branch of that project.
- One operation at a time per Sandbox. A second process using it at once gets `Busy`.
- No restart recovery: if the container dies, its Workspaces are gone. Stop and report.

## Workspaces

The same model as [How an agent works in LayerFS](../../SKILL.md#how-an-agent-works-in-layerfs),
from the Sandbox's side:

- **Each mount is a new Workspace.** `mount` returns a fresh path (such as
  `/workspaces/3`), numbered per Sandbox. The path is the Workspace's handle: pass it
  to `exec`, `status`, `commit` and `unmount`. Two mounts of one Branch are two separate
  Workspaces, each with its own uncommitted changes. Keep the `path` from the result;
  never build one yourself, and never use one after its unmount.
- **A Workspace per Bash call is the default:** mount, exec, commit, unmount. Mounting
  doesn't copy or scan the tree, so it's cheap; the Commit then holds exactly what that
  call changed.
- **Longer and parallel work is supported.** Keep a Workspace mounted across several
  `exec` calls and commit at any point, or mount several at once in one Sandbox, on one
  Branch or several.
- **Commands use relative paths.** `exec` starts at the Workspace root: write
  `npm test` or `cat src/cart.js`, never the mount path. The path changes with every
  mount, and one written into a file would be committed with it.
- **The view is fixed at mount.** It shows the Branch as it was then and doesn't follow
  later Commits. `commit` merges in what moved; to *see* it, mount a new Workspace.
- **Everything in it is committed:** sources, `.git`, `node_modules`, build output and
  caches. Scratch files belong in `/tmp`, which is outside the Workspace.

One Bash call as one Workspace:

```js
const path = await layerfs.sandbox.mount(id, "work");                  // a NEW Workspace with a new path
const run = await layerfs.sandbox.exec(id, path, "timeout 110 npm test 2>&1", "step 12");
await layerfs.sandbox.commit(id, path, `step 12: npm test (exit ${run.exitCode})`);
await layerfs.sandbox.unmount(id, path);                          // path is now invalid
```

## `sandbox.create(name, project, image)`

Starts a Sandbox named `name`, bound to `project` and running `image`, and waits until
it's ready.

| Arg | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Unique in this `LAYERFS_HOME`: 1–63 lowercase letters, digits, `_`, `-`, `.`, starting and ending with a letter or digit |
| `project` | string | yes | The project it serves: this client's project (`layerfs.projectName`) |
| `image` | string | yes | A local image digest, `sha256:<64 hex>`; `LAYERFS_IMAGE` holds the deployment's |

**Returns:** the Sandbox id, which is `name`.

**Refusals**

| Code | Meaning | Do |
| --- | --- | --- |
| `InvalidInput` | A bad name, another client's project, an image that isn't a digest, or a missing `LAYERFS_*` deployment variable | Fix the argument, or check the environment ([SKILL.md](../../SKILL.md#connect-to-a-project)) |
| `Exists` | A Sandbox with this name is open | Use it, or pick another name |
| `Failed` | Creation failed. With `detail.removed: true` its container is already removed and nothing of it is left, and `detail.log` holds its daemon's last log lines (also in the message); otherwise it names what stays | Stop and report the message; don't create another |
| `Unknown` | An earlier creation of this project has an unknown outcome; every create is refused until it is resolved | Stop and report the message, which says what a person must remove; don't remove or retry anything yourself |

```js
const id = await layerfs.sandbox.create("builder", layerfs.projectName, process.env.LAYERFS_IMAGE);
// id === "builder"; each sandbox.mount(id, …) in it creates a new Workspace with its own path
```

## `sandbox.mount(id, branch)`

Mounts a Workspace showing the Branch head at this moment. Doesn't scan or copy the tree.

| Arg | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Sandbox id |
| `branch` | string | yes | Branch to mount. Not `main`: fork a Branch from it |

**Returns:** the Workspace path, a string such as `"/workspaces/1"`. Pass it to
`exec`, `status`, `commit` and `unmount`; `status` tells which Commit it shows.

**Refusals:** `NoSuchBranch` (fork first), `NoSuchSandbox`, `Busy`, and `Failed` with
`Capacity` ("daemon Workspace capacity") in the message: the Sandbox's daemon already
holds its limit of Workspaces (16 by default). Don't retry the mount as it is. Unmount
Workspaces you no longer need; to find leftovers, see
[Clearing idle Workspaces](#clearing-idle-workspaces).

```js
const path = await layerfs.sandbox.mount(id, "work");   // a NEW Workspace: "/workspaces/1"; never hard-code it
```

**Notes:** every call mounts a new Workspace with its own `path`, even on the same
Branch (see [Workspaces](#workspaces)). The view doesn't follow the Branch: after an
`fs.*` write on the same Branch, mount again to see it (or let the next `sandbox.commit`
merge it in).

## `sandbox.exec(id, path, command, message?)`

Runs one shell command in a mounted Workspace and waits for it to end.

| Arg | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Sandbox id |
| `path` | string | yes | Workspace path from `mount` |
| `command` | string | yes | Run with `bash -c`; the working directory is the Workspace root, so use relative paths (`src/cart.js`), never the mount path; `HOME=/tmp` |
| `message` | string | no | Labels the run; at most 4096 bytes; creates no history |

**Returns**

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | string | `"exit:<code>"` |
| `exitCode` | number | The command's exit code. Non-zero is **not** a refusal |
| `stdout`, `stderr` | string | First 1 MiB of each stream |
| `truncated` | boolean | True if either stream went beyond 1 MiB |
| `message` | string \| null | Your message, echoed |

**Refusals**

| Code | Meaning | Do |
| --- | --- | --- |
| `NotMounted` | `path` isn't mounted in this Sandbox | Use the `path` saved from `mount` |
| `NoSuchSandbox` | Wrong id, or a different `LAYERFS_HOME` | Check both; don't create a replacement silently |
| `Busy` | Another process is using this Sandbox | Run steps one after another |
| `Unknown` | The exit code isn't known | Stop: the command may or may not have run |

**Limits**

- No timeout: put `timeout 110` inside the command.
- Waits until everything holding its output has ended, including background jobs.
- Keeps the first 1 MiB per stream; redirect bigger output to a file in `/tmp`.
- Files the command writes are in the Workspace and get committed; keep scratch files
  in `/tmp`.

**Run a check and report its output**

```js
// path: from sandbox.mount. Every mount creates a new Workspace with a new path; never hard-code one.
const run = await layerfs.sandbox.exec(id, path, "timeout 110 npm test 2>&1", "cart tests");
console.log(JSON.stringify(run, null, 2));
const saved = await layerfs.sandbox.commit(id, path, `step 12: npm test (exit ${run.exitCode})`);
console.log(saved.kind);                  // "UpToDate" when the command changed nothing
```
```json
{
  "kind": "exit:0",
  "exitCode": 0,
  "stdout": "\n> test\n> node --test\n\nTAP version 13\n# Subtest: cart\nok 1 - cart\n  ---\n  duration_ms: 0.433125\n  type: 'test'\n  ...\n# Subtest: cart-api\nok 2 - cart-api\n  ---\n  duration_ms: 0.453209\n  type: 'test'\n  ...\n# Subtest: loads\nok 3 - loads\n  ---\n  duration_ms: 0.533125\n  type: 'test'\n  ...\n1..3\n# tests 3\n# suites 0\n# pass 3\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 56.672166\n",
  "stderr": "",
  "message": "cart tests",
  "truncated": false
}
```

Commit whatever the command did, failure or not, so the step is recorded. If
`exitCode` isn't 0, read the failing output and the code it points at before you
decide what to change.

**Big output:** write it to `/tmp` and read the end in a second call.

```js
// path: from sandbox.mount. Every mount creates a new Workspace with a new path; never hard-code one.
await layerfs.sandbox.exec(id, path, "timeout 110 npm run build >/tmp/build.log 2>&1; echo $? >/tmp/build.code", "build");
const tail = await layerfs.sandbox.exec(id, path, "cat /tmp/build.code; tail -n 60 /tmp/build.log", "build log");
```

**Smoke-test a server:** start, probe and stop in **one** call. Send the server's output
to `/tmp`, so it doesn't hold `exec` open or land in the Workspace.

```js
// path: from sandbox.mount. Every mount creates a new Workspace with a new path; never hard-code one.
const cmd = [
  "timeout 60 bash -c '",
  "node src/main.js >/tmp/server.log 2>&1 & pid=$!;",
  "sleep 2;",
  "node -e \"fetch(\\\"http://127.0.0.1:3000/health\\\").then(r => { console.log(r.status); process.exit(r.ok ? 0 : 1) }).catch(e => { console.error(e.message); process.exit(1) })\";",
  "s=$?; kill $pid; cat /tmp/server.log; exit $s'",
].join(" ");
const run = await layerfs.sandbox.exec(id, path, cmd, "smoke test");
```

**Write a file inside a mounted Workspace:** only when this Workspace must see the
change before its next Commit; otherwise use `fs.*` and mount again. Pass the content as
base64 so the shell doesn't reinterpret it (command lines have an OS length limit, so
use this for files up to a few tens of KiB).

```js
// path: from sandbox.mount. Every mount creates a new Workspace with a new path; never hard-code one.
const content = "export const TAX = 0.08;\n";
const b64 = Buffer.from(content).toString("base64");
const run = await layerfs.sandbox.exec(id, path, `printf '%s' ${b64} | base64 -d > src/tax.js`, "write src/tax.js");
if (run.exitCode !== 0) console.log(run.stderr);
```

## `sandbox.status(id, path)`

Describes a mounted Workspace without reading the Store.

**Returns**

| Field | Meaning |
| --- | --- |
| `base` | Commit the Workspace is based on |
| `branchHead` | The Branch's current head |
| `headMovedSinceMount` | True if a Commit now would merge first |
| `activity` | The daemon's activity state for the Workspace |
| `overlay` | `{ inodes, entries, pendingMerge }`: changed files and directory entries |
| `branch` | Branch name |

**Refusals:** `NotMounted`, `NoSuchSandbox`, `Busy`.

```js
// path: from sandbox.mount. Every mount creates a new Workspace with a new path; never hard-code one.
const s = await layerfs.sandbox.status(id, path);
if (s.headMovedSinceMount) console.log("the next commit will merge with", s.branchHead);
```
```json
{
  "kind": "ok",
  "base": "123648aa594a…",
  "baseLayer": "32a35edb1f9f…",
  "branchHead": "123648aa594a…",
  "headMovedSinceMount": false,
  "activity": "Idle",
  "overlay": {
    "inodes": 0,
    "entries": 0,
    "pendingMerge": false
  },
  "branch": "work"
}
```

## `sandbox.commit(id, path, message?, force?)`

Saves everything changed in the Workspace as one Commit on its Branch. If the Branch
moved since the mount, it merges first. The Workspace stays mounted.

| Arg | Meaning |
| --- | --- |
| `id`, `path` | The Sandbox and the Workspace path from `mount` |
| `message` | Commit message |
| `force` | `true` to overwrite a newer head with this Workspace's view instead of merging. Drops the other changes; avoid |

**Returns**

| `kind` | Fields | Meaning |
| --- | --- | --- |
| `"Committed"` | `head`, `commit`, `displacedHead`, `merged`, `lww` | New Commit. `merged` is `{ from, head }` when a merge ran, else `null`. `lww` lists files decided last-writer-wins by the head's [`/.lww`](../rules/lww.md), each `{ path, kept, deleted, rule }` |
| `"UpToDate"` | `head`, `root`, `merged`, `lww` | Nothing changed; no Commit |

**Refusals**

| Code | Meaning | Do |
| --- | --- | --- |
| `Conflict` | The merge with the moved head overlaps. Markers are written into the Workspace; nothing is committed | See [resolving conflicts](../rules/conflicts.md#commit-conflicts) |
| `NotMounted`, `Busy`, `HeadMoved` | As elsewhere | Check the path; run steps one at a time; commit again after a look at `status` |

```js
// path: from sandbox.mount. Every mount creates a new Workspace with a new path; never hard-code one.
const c = await layerfs.sandbox.commit(id, path, "deps: npm install");
```
```json
{
  "kind": "Committed",
  "head": "122215f69eba…",
  "commit": {
    "id": "122215f69eba…",
    "branch": null,
    "parent": "12df71934c6f…",
    "secondParent": null,
    "base": "32a35edb1f9f…",
    "root": "caf388018578…",
    "via": "exec",
    "message": "A: resolved both changes",
    "mergedFrom": null,
    "time": 1792085429866,
    "logical": 2478,
    "newCanonical": 2849,
    "newStored": 1204,
    "newMetadata": 783,
    "displaced": null,
    "lww": [],
    "lwwTruncated": false
  },
  "displacedHead": null,
  "merged": null,
  "lww": []
}
```

**When Commit reports a `Conflict`:** nothing was committed, and the conflicted files in
the Workspace now hold markers. Read both sides before changing anything. Fixing the
files, ruling generated ones in `/.lww`, and overwriting with `force` are covered,
scenario by scenario, in [resolving conflicts](../rules/conflicts.md#commit-conflicts).

Merge diagnostic lists use byte windows. `lwwTruncated` marks omitted decisions;
conflict detail also exposes `conflictsTruncated`, and individual conflicts mark
`hunksOmitted`. Full marker files remain in the Workspace even when a reply omits
their text. Inspect those files with bounded `sandbox.exec` commands and Commit
each command. The omission flags never mean the unresolved source is safe to drop.

## `sandbox.unmount(id, path, discard?)`

Unmounts a Workspace.

| Arg | Meaning |
| --- | --- |
| `id`, `path` | The Sandbox and the Workspace path from `mount` |
| `discard` | `true` to drop uncommitted changes instead of refusing |

**Returns:** `{ kind: "Unmounted" }`.

**Refusals**

| Code | Meaning | Do |
| --- | --- | --- |
| `Dirty` | Uncommitted changes; `detail.changed` lists paths | Commit them, so the step is recorded; discard only a Workspace you're abandoning |
| `Busy` | A background process still runs there, or another process uses the Sandbox | Stop it, or wait for the other process |
| `NotMounted` | Already unmounted, or the wrong path | Use the `path` from `mount` |

```js
// path: from sandbox.mount. Every mount creates a new Workspace with a new path; never hard-code one.
await layerfs.sandbox.unmount(id, path);
```

## Clearing idle Workspaces

Nothing unmounts a Workspace for you: a script that exits, throws or is cut off before
its `unmount` leaves it mounted until the Sandbox closes, and it counts against the
daemon's Workspace limit. Put every `unmount` in a `finally` block.

To clear leftovers, for example after a mount is refused for capacity, scan the
Sandbox's paths with `status` (paths are numbered per Sandbox) and unmount only the
Workspaces that are idle, have nothing uncommitted, and that no agent is keeping on
purpose, such as a build Workspace or one running a dev server:

```js
const keep = new Set([/* paths agents said they're keeping */]);
for (let n = 1; n <= 1024; n++) {
  const path = `/workspaces/${n}`;
  let s;
  try { s = await layerfs.sandbox.status(id, path); } catch (e) { if (e.code === "NotMounted") continue; throw e; }
  const clean = !s.overlay.inodes && !s.overlay.entries && !s.overlay.pendingMerge;
  if (s.activity === "Idle" && clean && !keep.has(path)) await layerfs.sandbox.unmount(id, path);
}
```

Don't pass `discard` for a Workspace another agent mounted. Without it, a Workspace
with uncommitted changes is refused `Dirty` and stays mounted for its owner to commit.

## `sandbox.close(id)`

Stops and deletes the Sandbox container and frees its name for a new `create`. The
project and its history are unaffected.

**Returns:** `{ kind: "Closed", id }`.

**Refusals:** `MountsActive` (unmount every Workspace first), `Busy`, `NoSuchSandbox`.

When `LAYERFS_TRACE` is set, preserve the daemon log **before** this call: on the
host, save `docker logs <container-id> > <run>/daemon-<container-id>.log 2>&1`,
where `<container-id>` is `$(cat $LAYERFS_HOME/_sandboxes/<id>/container)` and `<run>`
is the folder containing `LAYERFS_TRACE`. Closing deletes the container and its log.
This is diagnostic collection; project reads and changes still use the SDK.

Inside dsh, skip the next paragraph: the service Sandbox is shared by every
agent and the dsh view, so never close it there.

Direct Store calls also create or reuse an automatic service Sandbox. At the end,
after all `fs.*` and Branch calls, obtain its id (`_service.<project>`) with `await layerfs.service()`,
save its log, and call `sandbox.close` for that id too. `service()` creates one if
none exists, so use it to finish a client that has already made Store calls; do
not use it merely to probe for a service after cleanup. A cached service id on
that client is invalid after close. The method return and close were captured in
issue #334 Phase B `observe-service-cleanup.out`.
