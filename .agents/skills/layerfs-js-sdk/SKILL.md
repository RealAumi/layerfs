---
name: layerfs-js-sdk
description: Use when building, editing, testing or inspecting a project through LayerFS with the JavaScript SDK (`@layerfs/sdk`) from the command line. Activates on LayerFS projects, Branches, Commits, Workspaces or Sandboxes; `layerfs.project.*`, `layerfs.fs.*`, `layerfs.branch.*` or `layerfs.sandbox.*` calls; running npm install, build or tests inside a mounted Workspace; or resolving LayerFS Conflict, Dirty or Busy refusals.
---

# LayerFS JavaScript SDK

> **Status:** Current general guide for the current SDK source. Base example
> outputs were captured live in issue #334 Phase A at `b30e4fb8f`. Explicit
> per-agent Sandbox routing was verified in #340 Phase A at `123fee2a2`.

Your project lives in LayerFS, not on your local disk. You read and change it through
the SDK, from small Node scripts you run with `node`.

## Inside dsh: start here

If `echo $DSH_LAYERFS_PROJECT` prints a name, dsh has set everything up. Skip
[Import the SDK](#import-the-sdk) and [Connect to a project](#connect-to-a-project):

- There's no npm install. Import the SDK with `await import(process.env.DSH_LAYERFS_SDK)`,
  in a module script. A static `import` of a variable is a syntax error.
- `new LayerFS(process.env.DSH_LAYERFS_PROJECT)` reads every other setting from the
  `DSH_LAYERFS_*` variables. The `LAYERFS_*` names in this guide are their twins; in
  dsh they're unset. Pass `process.env.DSH_LAYERFS_IMAGE` to `sandbox.create`.
- Don't look into Docker, the LayerFS box, Store files or the dsh host's source.
  Nothing there helps, and the SDK is the only way in.
- Your current folder is the dsh workspace the user selected. It's for temporary files
  only: your scripts, notes and scratch output. Files you find there may be an old copy,
  not the project. Do all
  work on the project through the SDK: `fs.*` and the Sandbox for files and commands, and
  `project.*` and `branch.*` for versioning, as you would use git.
- `node "$DSH_LAYERFS_CLI" status` lists the Branches. The same CLI does `log`, `ls`, `cat`,
  `grep`, `diff`, `fork` and `write` (content from stdin), and `run <branch> "<bash>"`. That
  runs a command in a new Workspace and Commits what it changed. Use the CLI for single
  steps and an SDK script for anything more.
- **Always unmount.** Put every `sandbox.unmount` in a `finally` block. Forgotten
  Workspaces fill the Sandbox's daemon (16 Workspaces) and every later mount there fails
  with `Failed` / `Capacity`, for every agent sharing it. To clear idle, clean leftovers,
  see [Clearing idle Workspaces](references/methods/sandbox.md#clearing-idle-workspaces).
- **Never close the service Sandbox** (`_service.<project>`). In dsh, every agent's
  script and the dsh view share it, so the cleanup in this guide's setup sections and in
  `sandbox.md` doesn't apply: close only the Sandboxes you created, then `await lf.close()`.
- **`main` is read-only.** It's published, not a Branch: read it and fork from it, but
  don't write, edit, mount or commit to it. Those calls, and `branch.list_commits("main")`,
  are refused with `NoSuchBranch`. Fork a Branch, work there, and publish it. A new
  project's `main` is empty.

## How an agent works in LayerFS

Every tool call an agent makes is one **step**, and every step that changes files becomes
a Commit on the agent's Branch. The Branch's history is the record of what the agent
did, step by step.

| Agent tool | LayerFS calls | Recorded as |
| --- | --- | --- |
| File read: read, list, search, diff | `fs.read`, `fs.list`, `fs.grep`, `fs.glob`, `fs.diff_files` | Nothing: reads don't change history |
| File change: write, edit, many-file change | `fs.write`, `fs.edit`, `fs.apply`, `fs.mkdir`, `fs.mv`, `fs.cp`, `fs.rm` | One Commit per call. Atomic: the whole change lands, or nothing does |
| Bash | A Workspace per call: `sandbox.mount` → `sandbox.exec` → `sandbox.commit` → `sandbox.unmount` | One Commit with everything the command changed: sources, lockfiles, `node_modules`, build output |

Two ways in: **`fs.*` for cheap, targeted file work; the Sandbox for Bash commands**,
which often change files too, and for file work too heavy for single calls.

### Cheap file work: `fs.*`

Use `fs.*` for the reads and small changes your own file tools make: read a file, list a
folder, search, diff, write or edit one file, move or delete a path, or a handful of
related changes as one Commit (`fs.apply`).

- **Why:** an `fs.*` call goes to the Branch through a reusable service Sandbox, without
  an explicit user Workspace or kernel mount, so it avoids the Bash mount lifecycle. A change is atomic and is exactly one Commit with your
  message, so the Branch records each edit as its own step. A read returns the Branch's
  latest Commit, so it sees what every Workspace and every other writer has committed.
- **When:** reading code before you change it, creating a file, editing source, renaming
  or deleting a path.
- **No merge:** if another writer committed on the Branch during the call, it's refused
  with `HeadMoved` and nothing is written. Read the file again, then redo your change.
- **Reads see committed state only**, never a mounted Workspace's uncommitted changes.

### Bash commands: the Sandbox

Use the Sandbox to run Bash commands. Most of them change files as well, and all of
those changes are recorded:

- **Commands that change files as a side effect:** `npm install` (`node_modules`,
  the lockfile), builds (`dist/`), code generators, formatters, `git`, tests that write
  snapshots or coverage. The Commit holds everything the command changed.
- **Heavier file work:** changes across many files or a large tree (`find … | xargs
  sed -i …`, a scaffolder, unpacking an archive), where one command beats many `fs.*`
  calls.
- **Files `fs.*` can't reach:** a mounted Workspace's uncommitted state, such as
  conflict markers after a Commit merge ([resolving conflicts](references/rules/conflicts.md)).

A mount costs more than an `fs.*` call, and its changes are recorded only at the
Commit, so for one small read or edit prefer `fs.*`.

- **A Workspace per Bash call is the default.** Mounting is cheap: it doesn't copy or
  scan the tree. Each call sees the Branch as it is right now, and its Commit holds
  exactly what that call did.
- **Each mount is a new Workspace.** `sandbox.mount` returns a fresh `path` (such as
  `/workspaces/3`) and a `workspace` id; the `path` is that Workspace's handle for
  `exec`, `status`, `commit` and `unmount`. Two mounts of one Branch are two separate
  Workspaces, and a path is never valid after its unmount.
- **Inside a command, use relative paths.** `exec` starts in the Workspace root, so
  write `npm test` or `cat src/cart.js`, never the mount path. The path changes with
  every mount, and a mount path written into a file would be committed with it.
- **Longer and parallel work is supported.** A Workspace can stay mounted across calls
  for a long-running command (a dev server, a watcher, a long build) and commit at any
  point. Several Workspaces can be mounted at once, on one Branch or several; when their
  Commits touch the same lines, the later one merges or reports a `Conflict`.
- **Commit after every Bash call, even a failing one,** with a message naming the step
  and its result, such as `"step 12: npm test (exit 1)"`. The Branch then shows exactly
  what each step did, failures included. Discard only a Workspace you're deliberately
  abandoning. `main` is unaffected until you publish.
- **A step that changes nothing makes no Commit.** `sandbox.commit` returns `UpToDate`,
  and a message alone never creates history: a read or a passing `npm test` that writes
  nothing leaves no trace on the Branch, by design.

## Merge rules: `/.lww`

Parallel Workspaces and Branches meet in a merge, either when a `sandbox.commit` finds
that its Branch moved or in `branch.merge`. Source files merge line by line, and
overlaps become a `Conflict` you resolve by reading. Generated state (`node_modules`,
lockfiles, build output) can't be merged that way, so list it in a `/.lww` file at the
project root. Both kinds of merge then keep the **newer** version of those paths whole
and report each decision in the result's `lww` list.

```
%include .gitignore
```

Treat it as your `.gitignore`: `%include .gitignore` is normally the whole file. Add a
line only in the extreme case, for a generated file you keep in Git that keeps
conflicting, such as a lockfile. Never list source files. Create it in the project's
first step; syntax and which `/.lww` each merge reads are in [merge
rules](references/rules/lww.md). When a merge does conflict, [resolving
conflicts](references/rules/conflicts.md) covers each case: fix it, rule it, or
overwrite it.

## The pieces

| Piece | What it is | SDK group |
| --- | --- | --- |
| Project | One Store holding all files and their whole history. `project.init` copies a folder into it, once | `project` |
| Branch | A named line of Commits. `main` changes only through `branch.publish`; work on your own Branch | `branch` |
| Files | Read and change files on a Branch directly. Every write is one immutable Commit; `fs.apply` makes many changes as one | `fs` |
| Sandbox | A container running one LayerFS daemon, where Bash commands run. Its id is persistent: later processes can reuse it | `sandbox` |
| Workspace | A complete, writable view of a Branch, mounted in a Sandbox, where ordinary commands run. `sandbox.commit` saves **everything** in it: `node_modules`, `.git`, build output, caches | `sandbox` |

## Import the SDK

The SDK is the `sdk/js` folder of the LayerFS checkout. Link it into your folder once:

```bash
npm init -y >/dev/null && npm pkg set type=module
npm install --no-audit --no-fund "file:$LAYERFS_REPO/sdk/js"   # LAYERFS_REPO: the LayerFS checkout
```

Then, in any `.mjs` file:

```js
import { LayerFS, isRefusal } from "@layerfs/sdk";
```

## Connect to a project

The client reads its settings from the environment. They're set up for you; every
process of one run must see the same values.

| Variable | Meaning |
| --- | --- |
| `LAYERFS_HOME` | Private folder where LayerFS records your project and Sandboxes |
| `LAYERFS_DOCKER` | Docker daemon Unix socket/endpoint, such as `/var/run/docker.sock`; use the `docker` executable for log collection |
| `LAYERFS_IMAGE` | Runtime image digest, `sha256:…`: the service Sandbox's, and the one to pass to `sandbox.create` |
| `LAYERFS_VOLUME` | Existing named Docker volume for this project's Store |
| `LAYERFS_DAEMON` | Host path to the built Linux daemon executable |

```js
const layerfs = new LayerFS("shop");   // a project name; no I/O happens yet
```

For several agents, the coordinator first creates each agent's Bash Sandbox in
sequence, then gives its id to that agent. The agent selects it for Store calls:

```js
const layerfs = new LayerFS("shop", { sandbox: mySandboxId });
```

The same selected Sandbox serves `fs.*`, Branch and operator Store calls, and
`service()` returns its id without starting another service. Use this agent's id
for its Bash mounts too; one agent runs its own calls sequentially. Independent
agents use distinct Sandboxes. Creation and automatic service discovery share a
project lock, so concurrent startup can be refused `Busy` before any effect.
Create first in sequence, then do parallel work. A selected Sandbox that is closed,
missing or unauthorized is refused, never replaced automatically. After closing
it, finish the client and use a new client for its successor. Issue #340's seven-case
external regression covers routing and exact refusal without replacement. Its
six persistent clients then passed concurrent public file reads and Branch forks
on six own Sandboxes at `123fee2a2`; the initial shared-service discovery Busy and
sixth-connection EOF remain retained in the Phase A evidence.

A new project needs `project.init(folder)` once. After that, `new LayerFS("shop")` in
any later process connects to the same project. Store calls (`fs.*`, Branch calls
and branch listing) automatically start or reuse a service Sandbox. The client's
`await layerfs.service()` returns its id, `_service.<project>`, creating that service if none exists.
Close it last during final cleanup, after all Store reads and publications:
`const serviceId = await layerfs.service();` then preserve its daemon log and
`await layerfs.sandbox.close(serviceId)`. Close explicit Bash Sandboxes too. After
closing the service, finish that client; use a new client for later work. This
cleanup was observed live in issue #334 Phase B
`observe-service-cleanup.out`.

## One script for each group

The four scripts run in this order; each is complete and runs with `node <file>`.

### project.mjs: create the project

```bash
mkdir -p /work/shop/.git
printf 'ref: refs/heads/main\n' > /work/shop/.git/HEAD
printf '# Shop\n' > /work/shop/README.md
printf 'node_modules/\ndist/\ncoverage/\n*.log\n' > /work/shop/.gitignore
printf '%%include .gitignore\n' > /work/shop/.lww
```

```js
// project.mjs
import { LayerFS } from "@layerfs/sdk";

const layerfs = new LayerFS("shop");
const created = await layerfs.project.init("/work/shop");   // once per project
console.log(created.kind);

const branches = await layerfs.project.list_branches();
console.log(branches.items.map((b) => b.name));
```

```
Initialized
[ 'main' ]
```

### branch.mjs: make your own Branch

```js
// branch.mjs
import { LayerFS } from "@layerfs/sdk";

const layerfs = new LayerFS("shop");
const forked = await layerfs.branch.fork("work");   // from main
console.log(forked.kind, forked.branch, forked.head); // head: null until the first Commit

const branches = await layerfs.project.list_branches();
console.log(branches.items.map((b) => b.name));
```

```
Forked work null
[ 'main', 'work' ]
```

### fs.mjs: write and read files on the Branch

```js
// fs.mjs
import { LayerFS } from "@layerfs/sdk";

const layerfs = new LayerFS("shop");
await layerfs.fs.write("work", "/hello.js", "console.log('hello');\n", "add hello.js");
await layerfs.fs.edit("work", "/hello.js", "'hello'", "'hello, shop'", "greet the shop");

const file = await layerfs.fs.read("work", "/hello.js");
console.log(file.text);

const listing = await layerfs.fs.list("work", "/");
console.log(listing.items.map((e) => `${e.type} ${e.name}`));
```

```
console.log('hello, shop');

[ 'dir .git', 'file .gitignore', 'file .lww', 'file README.md', 'file hello.js' ]
```

### sandbox.mjs: run a command, commit, publish

```js
// sandbox.mjs
import { LayerFS } from "@layerfs/sdk";

const layerfs = new LayerFS("shop");
const id = await layerfs.sandbox.create("hello", "shop", process.env.LAYERFS_IMAGE);   // its name
const path = await layerfs.sandbox.mount(id, "work");   // a NEW Workspace path, "/workspaces/1": never hard-code it

const run = await layerfs.sandbox.exec(id, path, "node hello.js | tee hello.txt", "run hello");
console.log(run.exitCode, run.stdout);

const saved = await layerfs.sandbox.commit(id, path, "save hello.txt");
console.log(saved.kind);

await layerfs.sandbox.unmount(id, path);
await layerfs.sandbox.close(id);

const published = await layerfs.branch.publish("work");
console.log(published.kind);
```

```
0 hello, shop

Committed
Added
```

## Rules

1. **Read before you retry.** A refused call throws a `LayerFSError` with a stable
   `code`, a `message` and a `detail`; `isRefusal(error, "Dirty")` tests for one code.
   Look at the project, then decide; never resend the same call blindly. On `Unknown`
   or `Failed` the outcome is uncertain: stop, check with `branch.list_commits` and
   `fs.read`, and report. A `sandbox.create` refused `Failed` with `detail.removed`
   left nothing behind; report its message, which carries the cause.
2. **A non-zero exit is not a refusal.** `sandbox.exec` returns normally; check
   `exitCode`.
3. **Keep each command under 2 minutes.** `sandbox.exec` has no timeout: wrap long
   commands inside it, `timeout 110 npm test`.
4. **A Workspace shows its Branch as it was at mount.** After `fs.*` changes, mount
   again before you build or test.
5. **Commit every step that changes files, with a message naming the step and its
   result**, failures included; publish to `main` at milestones.
6. **One process at a time per Sandbox**; a second one gets `Busy`. Ids are reusable:
   a Sandbox id and mount path work from any later process with the same
   `LAYERFS_HOME`, so a long task can be split into small scripts.
7. **Clean up:** commit or discard, unmount every Workspace, and close your Sandboxes.
   With `LAYERFS_TRACE` set, first save each container's daemon log as described in
   [`sandbox.close`](references/methods/sandbox.md#sandboxcloseid); close deletes it.

## Which method for which job

| Job | Use |
| --- | --- |
| Create or change one file | `fs.write`, or `fs.edit` (exactly one match of `oldText`) |
| Create or change a few related files at once | `fs.apply(branch, [{op:"write",…}, …], message)`, one Commit |
| Change many files or a whole tree | A command in the Sandbox (`sed`, a generator, a formatter), then `sandbox.commit` |
| Create folders, copy, move, delete | `fs.mkdir`, `fs.cp`, `fs.mv`, `fs.rm` (recursive) |
| Install, build, test, run anything | `sandbox.mount`, then `sandbox.exec`, then `sandbox.commit` |
| Look at files | `fs.read` (line ranges), `fs.list`, `fs.stat`, `fs.grep`, `fs.glob` |
| Compare | `fs.diff_files`, `branch.diff_commits`, `branch.diff_branches` |
| History | `branch.list_commits`, `fs.blame` |
| Check a Workspace | `sandbox.status` (base, whether the head moved, overlay counts) |
| Combine Branches | `branch.merge(a, b, name)`, then `branch.publish(name)` |
| Resolve a `Conflict` | [resolving conflicts](references/rules/conflicts.md) |

For Rust projects, follow the live-checked [Cargo workflow](references/rules/cargo.md).

## Methods

Copied from [`sdk/js/README.md`](../../../sdk/js/README.md), which is the source of truth.
Every method is positional and returns a Promise. Each group's page has, for every
method, its arguments, result fields, refusals with what to do, limits and examples.

| Group | Methods |
| --- | --- |
| [project](references/methods/project.md) | `init(sourcePath)`, `list_branches(pageSize?, pagePos?)` |
| [fs reads](references/methods/fs-read.md) | `read(ref, path, startLine?, endLine?)`, `list(ref, path?, pageSize?, pagePos?)`, `stat(ref, path)`, `grep(ref, pattern, path?, pageSize?, pagePos?)`, `glob(ref, pattern, path?, pageSize?, pagePos?)`, `diff_files(leftRef, leftPath, rightRef, rightPath)`, `blame(ref, path, fromLine?)` |
| [fs writes](references/methods/fs-write.md) | `write(branch, path, content, message?)`, `edit(branch, path, oldText, newText, message?)`, `apply(branch, changes, message?)`, `mkdir(branch, path, message?)`, `rm(branch, path, message?)`, `cp(branch, from, to, message?)`, `mv(branch, from, to, message?)` |
| [branch](references/methods/branch.md) | `fork(name, fromRef?)`, `list_commits(branch, pageSize?, pagePos?)`, `diff_commits(from, to, pageSize?, pagePos?)`, `diff_branches(from, to, pageSize?, pagePos?)`, `merge(a, b, name, message?)`, `publish(branch, commit?)` |
| [sandbox](references/methods/sandbox.md) | `create(name, project, image)`, `mount(id, branch)` → path, `exec(id, path, command, message?)`, `status(id, path)`, `commit(id, path, message?, force?)`, `unmount(id, path, discard?)`, `close(id)` |

A `ref` is `main`, a Branch name, a Commit id or a Layer id. Paths are absolute in the
view (`/src/index.js`). Pages are `{ items, hasMore }`; advance with
`pagePos + items.length`.

Deeper material: the [SDK reference](../../../sdk/js/README.md) and the
[0.1.7 SDK and UI guide](../../../docs/versioned/0.1.7/sdk-and-ui.md).
