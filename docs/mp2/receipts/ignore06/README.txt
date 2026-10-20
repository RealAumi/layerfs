ignore06: one run of docs/mp2/run-ignore-e2e.py on 42f8a5ebb (same binaries as ignore05, identical sha256 in
tested-identities.txt), then the transport tests. Nothing was rerun; every unmount below is a single sample.

This run corrects the 5b/6b spec. ignore05 is the first-run record and stays unchanged (5b and 6b failed there).
  6b: ignore05's script defect fixed (B2 now runs `git rm -r -f -q pkg`; B1 had only staged pkg/, never committed it).
  5b: ignore05 expected one no-change Commit to publish the newly kept out/local.txt. docs/mp2/ignore.md documents a
      one-Commit lag, so 5b is now two steps:
      (a) B1's merge Commit after B2's rule change: B1 gets the new .gitignore, keeps out/local.txt, and out/local.txt
          is NOT on the published head (asserted as the EXPECTED lag).
      (b) a second B1 Commit with no local change: out/local.txt is on the published head with B1's bytes, a fresh B2
          mount shows it, and nothing else under ignored paths was uploaded (5 objects, 11,289 B; big2.bin,
          node_modules/z and target/old.class "again" stay off the published head).

Result: all 10 scenarios PASS (1 7/7, 2 25/25, 3 9/9, 4 7/7, 5 26/26, 6 22/22, 5b 24/24, 6b 24/24, 8 3/3, 9 3/3);
transport 5 passed. All 16 unmounts were clean in this one run.

Scenario 6 merge Commit, 13 server reads (ignore02: 10): see results.json facts.s6_merge_reads. Twelve single-object
requests plus one request carrying two ids. Three requests read M's `.git/index` (a chunked 22 KB file): two LFS4MAP
objects (106 B, 604 B), then one request with both LFS4CHK chunks (19563 B and 2989 B, the first starting "DIRC").
The other ten are tree objects of the merged root M (root, inode tables, root directory, .git directory, docs
directory, one .git/objects/xx directory). That the two LFS4MAP objects are the index's chunk maps is inferred
from their position right before the DIRC chunks, not decoded. Attribution to the code is by reading 42f8a5ebb vs 684b981b5, not an A/B run:
IgnoreState::rebase (store/ignore/project.rs) now parses the index of the merged tree (`self.tracked(reader, &after)`),
which the earlier rebase never did. P's own index and the .gitignore are already in B1's cache and are not read.
