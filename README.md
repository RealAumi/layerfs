<p align="center">
  <img src="docs/assets/readme/layerfs-mark.svg" alt="LayerFS" width="112">
</p>

<h1 align="center">LayerFS</h1>

<p align="center"><strong>Ephemeral Workspaces. Durable Shared History.</strong></p>

<p align="center">
  LayerFS is the substrate under your agents. Each one mounts a complete, writable
  Workspace over shared committed history, does its work, commits what it changed,
  and goes away.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
  <a href="docs/release-notes/0.1.7/README.md"><img src="https://img.shields.io/badge/status-0.1.7%20developer%20preview-orange.svg" alt="0.1.7 Developer Preview"></a>
</p>

> **Status:** LayerFS 0.1.7 Developer Preview, released as source. It is for
> evaluation and agent-runtime integration, not production storage: there is no
> crash or power-loss durability. Read the [release record](docs/release-notes/0.1.7/README.md)
> and its waivers before relying on it.

## Core ideas

<table>
  <tr>
    <td width="33%" valign="top">
      <img src="docs/assets/readme/idea-01-ephemeral.svg" alt="fs calls go straight into the Store as Commits; each Bash call mounts a Workspace, runs, commits and unmounts" width="100%"><br>
      <img src="docs/assets/readme/icon-ephemeral.svg" width="16" height="16" alt=""> <b>01 · Ephemeral Computing</b><br>
      Compute exists only while a command runs.
    </td>
    <td width="33%" valign="top">
      <img src="docs/assets/readme/idea-02-decentralized.svg" alt="Four agents, each on its own computer, read and commit to one shared Store" width="100%"><br>
      <img src="docs/assets/readme/icon-decentralized.svg" width="16" height="16" alt=""> <b>02 · Decentralized Agents</b><br>
      Agents on different computers share one serverless Store.
    </td>
    <td width="33%" valign="top">
      <img src="docs/assets/readme/idea-03-coordination.svg" alt="Main with two Branches, three agents on each; a commit to a file that already changed is refused with a Conflict" width="100%"><br>
      <img src="docs/assets/readme/icon-coordination.svg" width="16" height="16" alt=""> <b>03 · Multiagent Coordination</b><br>
      One project, many Branches. One Branch, many agents.
    </td>
  </tr>
  <tr>
    <td width="33%" valign="top">
      <img src="docs/assets/readme/idea-04-recursive.svg" alt="Agents fork instantly into new Branches, recursively; each Branch is scored and the best one is kept" width="100%"><br>
      <img src="docs/assets/readme/icon-recursive.svg" width="16" height="16" alt=""> <b>04 · Recursive Filesystem</b><br>
      Fork recursively any Commit, at any depth.
    </td>
    <td width="33%" valign="top">
      <img src="docs/assets/readme/idea-05-storage.svg" alt="Four agents commit the same packages; the first stores every chunk and each later Commit adds only what is new" width="100%"><br>
      <img src="docs/assets/readme/icon-storage.svg" width="16" height="16" alt=""> <b>05 · Ultra Storage Optimization</b><br>
      10 copies compress into 0.31.
    </td>
    <td width="33%" valign="top">
      <img src="docs/assets/readme/idea-06-bootstrap.svg" alt="Without ignored files the tests fail until packages are installed; with LayerFS the mount already has them" width="100%"><br>
      <img src="docs/assets/readme/icon-bootstrap.svg" width="16" height="16" alt=""> <b>06 · Instant Bootstrap</b><br>
      Dependencies come with every mount. No time lost reinstalling.
    </td>
  </tr>
</table>

**And underneath them**

| | Supporting idea | In one line |
| --- | --- | --- |
| <img src="docs/assets/readme/icon-checkpoints.svg" width="16" height="16" alt=""> | **07 · Auto Checkpoints** | Every step an agent takes is a checkpoint to return to. |
| <img src="docs/assets/readme/icon-immutable.svg" width="16" height="16" alt=""> | **08 · Append-only Objects** | Saved objects are never rewritten. The Store only grows. |
| <img src="docs/assets/readme/icon-lww.svg" width="16" height="16" alt=""> | **09 · Conflict Rules (`.lww`)** | Name the files that should never conflict. The newest edit wins. |
| <img src="docs/assets/readme/icon-bigfile.svg" width="16" height="16" alt=""> | **10 · Big File, Small Edit** | An edit costs the size of the edit, not the size of the file. |

## See it run

<p align="center">
  <img src="docs/assets/official_release/page3-demo.gif" alt="The LayerFS demo: agents on several Branches run tool calls in Sandboxes and fs, each call becomes a Commit, and the history tree grows" width="100%">
</p>
<p align="center"><sub>Agents fork Branches, work in Workspaces inside Sandboxes, commit, merge and publish to <code>main</code>. The history grows as they go.</sub></p>

## Get started

Paste this into your coding agent. It sets LayerFS up and works on a Branch of its own:

```text
Set up LayerFS for this project and start using it for your work.

1. Read the setup guide in https://github.com/Ephemeral-AI-Lab/layerfs: sdk/js/README.md explains the JavaScript SDK, its native binding, the Linux daemon and the environment it reads (LAYERFS_HOME, LAYERFS_DOCKER, LAYERFS_IMAGE, LAYERFS_VOLUME, LAYERFS_DAEMON).
2. Check the requirements before you start: a Linux host, Docker Engine, Node 20 or newer, and a local ext4, xfs or btrfs filesystem for the Store. If one is missing, stop and tell me which.
3. Build what the guide says to build and set those variables.
4. Run project.init once on this repository. It captures the whole tree, ignored files included, as main @ L0.
5. Fork a Branch for your work. From now on, use sdk.fs for file reads and edits, and for each Bash command mount a Workspace on your Branch, exec, commit, then unmount.
6. Check it worked: write a file on your Branch and confirm list_commits shows the Commit.

Report what you ran and what each step returned. If a step fails, stop and give me the exact error; don't retry it on your own.
```

To set it up by hand, follow the [JavaScript SDK guide](sdk/js/README.md).

## Works with

- **LayerFS × [DSH](dsh/README.md)** (preview): agents in a DeepSeek Harness session fork, test, merge and
  publish from bash, and a LayerFS tab draws what each one did.
- **LayerFS × Pi**: planned.

## Learn more

| | |
| --- | --- |
| The 0.1.7 manual | [Manual](docs/versioned/0.1.7/README.md) · [SDK and terminal UI](docs/versioned/0.1.7/sdk-and-ui.md) · [SDK reference](docs/versioned/0.1.7/sdk-reference.md) |
| Concepts | [Core concepts](docs/general/concepts.md) · [Documentation index](docs/README.md) |
| Release and limits | [0.1.7 release record](docs/release-notes/0.1.7/README.md) · [Known limits](docs/versioned/0.1.7/sdk-and-ui.md#7-known-limits) |
| Benchmarks | Released fs-bench-pro results: [v0.1.4](docs/release-notes/0.1.4/benchmark-closeout.md) · [v0.1.5](docs/release-notes/0.1.5/benchmark-closeout.md) · [v0.1.6](docs/release-notes/0.1.6/benchmark-closeout.md) (0.1.7 published none) |

## License

LayerFS is licensed under the [MIT License](LICENSE).
