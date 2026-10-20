# Ignore09 registration

Status: local diagnostic performance and crash qualification, not a release benchmark.

Owner explicitly selects ten samples per arm, superseding the ordinary one-sample
rule. Phase 8 hot-cache policy: persistent mounted workspace, identical untimed
preparation, local object/application and OS caches populated by initial Commit;
no cold claim. Host OS caches and other owners' workloads are uncontrolled. Arms
alternate keyed/unkeyed then unkeyed/keyed for ten pairs, no outlier deletion or
unchanged-arm reruns. There are no builds during samples. Numeric results are
local diagnostics; absence of OS residency control limits general speed claims.

Fixture: retained run04/phase4/full-manifest.json.gz, Phase 8 SHAKE payload recipe,
30,000 ignored node_modules files / 211,730,666 bytes / 9,470 directories. Prepared
once under ~/.cache/cxi-ignore09, independently copied to both workspace mounts.
0 ms added network delay, local OrbStack. One construction worker, Disposable
Store, existing cache mode initially MEMORY/OFF. Rust 1.85.1 test-profile binaries
from ignore08, exact hashes checked before reuse. No cx7/ign resource access.

Selections, all retained:
- baseline: manifest/MEMORY, keyed and unkeyed, 10 alternating pairs.
- small-record: restore walk/MEMORY, keyed and unkeyed, same ten-pair method.
- WAL candidate: restore walk/WAL, keyed and unkeyed, same ten-pair method.
- one restore on the same fixture per selected implementation.
- 20 varied-delay SIGKILL cycles on the selected final cache profile, no rerun.

Each measured Commit calls the public control CLI once after replacing one kept
file with a fixed-size unique value. Inner CLI wall_ns and outer subprocess ns
are retained separately. Full process startup/authentication is in CLI wall_ns;
file preparation, stats/SQLite queries, and verification are outside it. Every
child has <=120 s timeout; Commit samples <=25 s. Multi-sample orchestration is
not a single unbounded test. Setup and build wall are recorded separately.

Report median, min/max, every raw sample and median paired difference. A practical
noise screen is max(3 ms, 15% of the unkeyed median), taken from the repository's
ordinary regression-screen tolerance; ten user-selected pairs replace n3.
WAL is small-cost if its keyed median increase over small-record MEMORY is below
that same threshold; this is a diagnostic comparison, not statistical proof.
Independent verification: after the cohort, kept content equals published content,
ignored sentinel absent on server, all 30,000 local file paths present. Storage:
record blob size, local cache DB/WAL sizes and object bytes, outside sample timing.

Process-crash qualification does not include power loss. Kill samples retain the
original Commit result/uncertainty, database integrity/open observations, selected
restore state, and the explicit next Commit's no-ignored-publication proof.
