# Attempt 2

> **Status: Research; informative and not a product contract.**

Owner correction: stop only for LayerFS failures. Preserve failed workload pins,
then select another public unmodified lockfile install. Prior receipts are frozen.
Vite v6.1.0 at 051370a332df99d107365ed6beab418ef017eff6 is candidate 2.
Use its pinned pnpm 9.15.5; frozen lockfile, public registry, no force flags.
Build bundle and incremental TypeScript declarations; edit-loop builds use the
incremental TypeScript declaration command, with persistent tsbuildinfo.
Tests use its unit suite, never browser/integration services. Each test <=120 s.
Package acquisition/base setup may take 600 s; compilation preparation 300 s.
No release-performance admission or cold-OS-cache claim is made.

Store growth is committed logical database bytes (page_count times page_size),
with actual main/WAL/SHM sizes separately recorded. Upload is canonical payload;
fetched bytes are Store-link ciphertext including protocol overhead, excluding
public registry downloads. Every explicit Commit is timed. Fresh clients have
empty local object caches; server OS caches are declared uncontrolled.

Maven uses Petclinic 500158f732419217507c7656904b8e6aa1bcc0d6. Compare S8a
shared cache volume, S8b repo-local .m2, and S8c separate writable cache-Branch
fork. S8c tries two Workspaces in one daemon first; cache forks never merge back.
Workloads do not run Docker or start external services. Preserve all refusals,
failed candidates and incomplete rows. Each scenario/arm/iteration is one sample.

Revisions before the remaining selections:
- Vite's initial partial build/Node 22 cold test failed; retained. The revised
  base reuses the closed frozen-lockfile installation, builds all packages on
  Node 20.19.0, and has independent off/on forks (suffix 3).
- S8b Petclinic download succeeded but repo-local .m2 triggered its NoHTTP
  scanner (3,757 violations). No check is disabled. S8b remains failed; S8a
  supplies the full Maven off/on loop. S8c stays a separate off-only variant.
- SDK setup/read helper uses a unique per-process overlay-template path. The
  fixed-path read diagnostics correctly refused AlreadyExists before the SDK
  method ran. Those failed diagnostics remain; product code is unchanged.
