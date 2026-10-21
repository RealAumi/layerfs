# Published history

On 2026-10-21 the `mp2/*` branches were rewritten once before their first push
to the fork. Code is unchanged; only metadata and documentation text changed:

- Author and committer are the fork owner's GitHub identity.
- Internal host and platform names in docs and receipts became neutral words
  (`remote-host`, `cloud-sandbox`, `other`, `other-container`); local home
  paths became `~`.

Receipts and docs written before the rewrite still cite the old commit ids.
This table maps them, sorted by old id. Branch tips at the rewrite:
`mp2/remote-store` 131cfc021 → ec07fdde4, `mp2/ignore` 918608765 → 4f87119b5,
`mp2/local-paths` 40e949d72 → 7074947af.

Since the same day `main` carries our version. `mp2/remote-store` and
`mp2/ignore` were folded into it and deleted; `mp2/local-paths` became
`notes/local-paths`. Upstream is merged into `main` from `upstream/main`.

| Old | New | Subject |
| --- | --- | --- |
| 06a781cfc | 221f4aa16 | feat(remote-store): expose opt-in canonical read diagnostics |
| 07675573b | 8ee6cb0e7 | docs(mp2): design opt-in git-ignored local paths |
| 10d2c76b0 | 10ae25aea | refactor(mp2): share candidate publication behind Workspace backend ports |
| 131cfc021 | ec07fdde4 | Record Phase 8 receive costs and filesystem diagnostic receipts |
| 178cb1363 | eb8932b61 | test(ignore): preserve a deleted nested-rule reconciliation failure |
| 1d7c95677 | 3555acc47 | Record Phase 7 matched unmount rates and complete failure custody |
| 2ff9d0b95 | 0263a6a94 | feat(remote-store): keep Git-ignored names local with ignore=git |
| 3e7eba2a3 | 3a89d87d8 | docs(ignore): retain first restore e2e and cleanup receipts |
| 40e949d72 | 7074947af | docs(mp2): assess daemon-local subtree routing |
| 42f8a5ebb | b04400ec9 | fix(ignore): apply closed index policy and deferred rebase reconciliation |
| 4aa44bccd | 57de93f48 | test(ignore): reproduce lost installed local root on bind |
| 4c394e3fb | 79e4a4a84 | docs(mp2): ignore e2e reruns 05/06 with server-delete and rule-flip scenarios |
| 524862598 | 5dbafed2e | Wake idle FUSE receivers after known detach and request quiescence |
| 6394865a4 | a92bee173 | Record refreshed-index qualification and Phase 6 metadata diagnostics |
| 66a3d0456 | 53503a677 | test(ignore): capture kept writes under pruned local directories |
| 6771ecad8 | 721b8cc7e | test(mp2): verify mounted head refresh and root caller behavior |
| 684b981b5 | 29e8e5732 | docs(mp2): rerun the ignore e2e on metadata batching |
| 68f5dd3d6 | c5a741d7d | docs(mp2): record build-output costs and unresolved historical teardown cause |
| 6aa63705c | 58cc83077 | feat(mp2): serve remote Store objects and publish candidates over Noise |
| 6cc16e913 | 43491046a | Batch immutable generation metadata over the Store protocol |
| 8232aab09 | b485d8048 | test(ignore): retain adversarial failures before hardening |
| 8ec4118b4 | 515f2fcee | fix(ignore): reconcile stale bindings and harden local review coverage |
| 918608765 | 4f87119b5 | fix(ignore): refuse transient restore failures and reject old records |
| 9f8acbbbb | 4a6326ec1 | fix(cache): use WAL for local restore state and retain ignore09 results |
| a2dfc4fe0 | 4c1927eb9 | fix(ignore): move closure checking to restore and tolerate checkpoint failure |
| b927c453c | 87f3f7174 | test(ignore): retain manifest cost and restore failure regressions |
| babe80e0c | 1ce5d87da | test(ignore): capture round-two policy and placement failures |
| c73497e2c | 9de1310fb | Register exclusive FUSE receive waits once per receiver |
| c834e1ce2 | f733b4dec | feat(mp2): count acknowledged uploads for build-output diagnostics |
| cd2abaeab | 6e1cfc01b | docs(mp2): record remote Store proof and retained teardown failure |
| cfbd865f5 | d7acce867 | docs(mp2): design cross-machine Store prototype |
| d2fafd9eb | f5efe8aa6 | feat(ignore): restore installed local roots by caller key |
| ddf93133e | ae7290e34 | docs(mp2): reject unsafe cold Git stat-cache shortcuts |
| e4eae2953 | 1b6951d42 | docs(mp2): attribute cold Git reads and measure dependency commits |
| f3db52986 | e2ad7b141 | test(ignore): retain remount and restart loss baseline |
| fea73ceff | 6ccb51d5a | test(ignore): retain transient restore and old-record failures |
