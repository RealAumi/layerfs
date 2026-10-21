#!/usr/bin/env bash
# fsx, one step per command. Each client step runs one SDK client
# (common/client.sh) under the 115 s limit and logs its step, times, exit and
# the 1-minute load to RUN/commands.log (common/lib.sh).
#
#   run.sh image                    build bench-fsx:<date>; benchmark-results/fsx/image.txt
#   run.sh setup RUN CASES MODE     volumes, identity, CASES copied to RUN/cases.tsv, then start
#   run.sh start RUN MODE           MODE measured takes the measurement lock (exit 75 while another run
#                                   holds it: wait, then start again), smoke does not; Init, create,
#                                   fork, mount
#   run.sh next RUN                 the next case and arm from RUN/cases.tsv (repeat until DONE)
#   run.sh commit RUN               one sandbox.commit of the Workspace
#   run.sh probe RUN                diagnostic (smoke runs): each fallocate mode's error text, both arms
#   run.sh teardown RUN             unmount, close, remove the volumes, release the lock
#   run.sh report RUN               results.csv, commit.csv and summary.json (report.py)
#
# RUN is a new folder benchmark-results/fsx/<UTC yyyymmddTHHMMSSZ> (smoke runs:
# smoke-<id>). CASES is cases.tsv (measured) or cases-smoke.tsv. Each
# cases.tsv row is one fsx case run in the layerfs arm, then sandbox-disk.
set -euo pipefail
suite=fsx
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=../common/lib.sh
. "$here/../common/lib.sh"
imagefile=$bench_repo/benchmark-results/fsx/image.txt
step=${1:-}
shift || true

case "$step" in
image)
  mkdir -p "$(dirname "$imagefile")"
  bench_image "$here/sandbox" "bench-fsx:$(date -u +%Y%m%d)" "$imagefile"
  docker run --rm --entrypoint cat "$(sed -n 's/^image=//p' "$imagefile")" /opt/fsx-identity.txt >>"$imagefile"
  ;;
setup)
  run=$1 cases=$2 mode=$3
  [[ "$mode" == measured || "$mode" == smoke ]] || { echo "run.sh: MODE is measured or smoke" >&2; exit 2; }
  bench_setup "$run" "$imagefile" fsx "mode=$mode cases=$(basename "$cases")"
  grep -E '^(xfstests_commit|fsx_sha256|gcc|liburing|libaio|xfslibs|HAVE_[A-Z_]+)=' "$imagefile" | sed 's/^/image_/' >>"$run/identity.txt"
  cp "$cases" "$run/cases.tsv"
  mkdir "$run/seed"
  echo "LayerFS fsx benchmark Workspace; fsx writes under fsx/." >"$run/seed/README"
  exec "$0" start "$run" "$mode"
  ;;
start)
  run=$1 mode=$2
  [[ "$mode" == smoke ]] || bench_lock "$run"
  bench_client "$run" setup setup.mjs "$run/seed"
  ;;
next)
  run=$1
  # The first (row, arm) without a results.jsonl line: VARIANT SEED ARM OPS ARGS.
  pick=$(python3 - "$run" <<'EOF'
import json, os, sys
run = sys.argv[1]
done = set()
if os.path.exists(f"{run}/results.jsonl"):
    done = {json.loads(l)["case"] for l in open(f"{run}/results.jsonl") if l.strip()}
for line in open(f"{run}/cases.tsv"):
    if not line.strip() or line.startswith("#"):
        continue
    variant, seed, ops, *args = line.rstrip("\n").split("\t")
    for arm in ("layerfs", "sandbox-disk"):
        if f"{variant}-s{seed}-{arm}" not in done:
            print(variant, seed, arm, ops, *(args[0].split() if args else []))
            sys.exit(0)
EOF
)
  if [[ -z "$pick" ]]; then echo DONE; exit 0; fi
  read -r -a argv <<<"$pick"
  bench_client "$run" "$(bench_next "$run" "case-${argv[0]}-s${argv[1]}-${argv[2]}")" case.mjs "${argv[@]}"
  ;;
commit)
  run=$1
  bench_client "$run" commit commit.mjs
  ;;
probe)
  run=$1
  bench_client "$run" probe probe.mjs
  ;;
teardown)
  run=$1
  bench_client "$run" teardown teardown.mjs
  bench_cleanup "$run"
  if grep -q '^lock=taken' "$run/identity.txt"; then bench_unlock "$run"; fi
  ;;
report)
  run=$1
  python3 "$here/report.py" "$run"
  ;;
*)
  sed -n '2,20p' "$0" >&2
  exit 2
  ;;
esac
