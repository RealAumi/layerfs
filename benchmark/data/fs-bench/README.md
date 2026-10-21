# fs-bench release data

> **Status:** Current general guide.

One folder per release with fs-bench results: Cloudflare Computer's frozen
twelve-scenario real-FUSE workload (`fs-bench.sh`, SHA-256 `0e2004339a92…`),
run once against pinned Cloudflare Computer and once against LayerFS core, as
one pair. The collector is [benchmark/fs-bench](../../fs-bench/README.md).
The website's fs-bench page reads these files.

| Release | Pair | LayerFS faster | Sum, Computer ÷ LayerFS | Record |
| --- | --- | ---: | ---: | --- |
| [v1.0.0](v1.0.0/) | `20261019T195401Z`, VALID | 10 / 12 | 1.71× | [record](v1.0.0/record.md) |

Each folder holds:

| File | What it is |
| --- | --- |
| `benchmark-performance.csv` | One row per scenario: raw ns for each arm (one sample, so median = sample), the cache state, the ratio `computer_upstream_ns ÷ layerfs_core_ns`, the winner |
| `environment.csv` | Each arm's source, image, route, user, mount, container, daemon, load and collector exit |
| `comparison.json`, `comparison.md` | `compare.py`'s verdict and report, unchanged; the JSON hashes every raw receipt |
| `<arm>/result.json`, `<arm>/manifest.tsv`, `<arm>/mountinfo.txt` | Each arm's raw receipts, unchanged |
| `layerfs-core/sdk-check.json`, `sdk-collect.json` | The first and last `sandbox.exec` outcomes; the run's own stdout and stderr are in `result.json` |
| `record.md` | The campaign record, copied from `benchmark/fs-bench/records/`; its relative links point into that folder |

v1.0.0 was measured at `main` `e5c7aaae05`. Both arms ran on one image
(`sha256:66aeb6bb…`, with gawk so no statistic can saturate at 2³¹−1 ns), one
after the other, on Docker Desktop on an arm64 Mac at 1-minute load 7–8.
Computer ran through `docker exec` as root. LayerFS was set up and run only
through the public JS SDK: `project.init`, `sandbox.create`, `branch.fork`,
`sandbox.mount`, and three `sandbox.exec` calls as uid 501. One sample per
arm; the three own-write warm rows (`pure read`, `pure copy`, `overwrite`)
measure warm-state behaviour. Not a qualifying pair for a native x86-64
Linux host.

To add a release, create `v<version>/` with the same files from that
release's pair, copied unchanged from `benchmark-results/fs-bench/<pair>/`.
