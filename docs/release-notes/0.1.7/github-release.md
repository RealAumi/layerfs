# LayerFS v0.1.7: rewritten core, JavaScript SDK and live terminal UI

> **Status:** LayerFS 0.1.7 release announcement. Published as the GitHub release
> for tag [`v0.1.7`](https://github.com/Ephemeral-AI-Lab/layerfs/releases/tag/v0.1.7).

v0.1.7 is the last 0.1.x Developer Preview before LayerFS 1.0.0. It replaces the
v0.1.6 implementation with the rewritten `core/` workspace:
- every Sandbox daemon opens one shared Store directly;
- each mounted Workspace has its own overlay;
- Commit merges with a Branch head that has moved since the mount, and on
  conflict writes markers and commits nothing.

**New public surface: `@layerfs/sdk`.** 29 positional methods in `project`, `fs`,
`branch` and `sandbox`, with:
- optional commit messages;
- `pageSize`/`pagePos` paging;
- line-range reads and blame;
- recursive `cp`, `mv` and `rm`;
- atomic multi-change `apply`;
- Sandbox ids that another process can reuse.

An internal `@layerfs/sdk/operator` entry reports Store and per-Commit sizes,
file history, Workspace overlays and background processes.

**Terminal UI.** `sdk_sim/tui.html` runs four stories (Tour, Conflicts,
Commit & merge, 5 agents), either in an in-page simulator or live on the product
through `node sdk_sim/server/server.mjs`.

**Compatibility, an owner-approved exception to the 0.1.x promise:**
- **Removed.** The v0.1.6 CLI and Rust SDK are removed.
- **Store format.** Stores use schema 16–18 or 22–24 with `layerfs/commit/v3`
  identity. Older Stores, including v0.1.6 schema-10 Stores, are refused without
  migration.
- **Version matching.** SDK, addon and daemon must come from this tag.
- **Store profile.** Only the Disposable Store profile runs.

**Released as-is with waivers.** The owner chose to reuse the existing acceptance
evidence instead of rerunning every gate at the release commit:
- SDK standard cases and live stories PASS;
- B7 NOT_RUN; A9 kept as its historical FAIL;
- the whole workspace suite and the separate FUSE and container gates were not
  rerun.

No performance claim is made. The release is source-only: no npm package,
prebuilt binary or public image.

- [0.1.7 manual](https://github.com/Ephemeral-AI-Lab/layerfs/blob/v0.1.7/docs/versioned/0.1.7/README.md)
- [Release record, evidence and waivers](https://github.com/Ephemeral-AI-Lab/layerfs/blob/v0.1.7/release-notes/0.1.7/README.md)
- Next: the [LayerFS 1.0.0 plan](https://github.com/Ephemeral-AI-Lab/layerfs/blob/v0.1.7/docs/roadmap/1.0/README.md):
  documentation (#330), demos (#331) and benchmark preparation (#332).
