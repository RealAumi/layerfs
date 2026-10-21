#!/usr/bin/env bash
# pjdfstest, one step per command. Each client step runs one SDK client
# (common/client.sh) under the 115 s limit and logs its step, times, exit and
# the 1-minute load to RUN/commands.log (lib.sh bench_client).
#
#   run.sh image                       build bench-pjdfstest:<yyyymmdd>, write image.txt
#   run.sh setup    RUN [DIR...]       volumes, deploy.env, identity; Init, create, fork, mount,
#                                      probe, plan.json (all test files, or DIRs' for a smoke run)
#   run.sh group    RUN                one sandbox.exec: the next pending group (repeat until DONE)
#   run.sh finish   RUN                residue listing, one timed Commit, unmount, close
#   run.sh repro    RUN                diagnostic: minimal repros of the LayerFS-only classes, both arms
#   run.sh teardown RUN                unmount and close only (when finish could not run)
#   run.sh cleanup  RUN                remove the run's two volumes (after finish or teardown)
#
# Arms: layerfs (the mounted Workspace, <path>/pjd/DIR) and sandbox-disk
# (/tmp/pjd/DIR in the Sandbox container); each directory runs in layerfs,
# then sandbox-disk. RUN is a new absolute folder
# under benchmark-results/pjdfstest/. A measured run takes the measurement
# lock before setup (lock RUN) and releases it after cleanup (unlock RUN).
set -euo pipefail
suite=pjdfstest
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=../common/lib.sh
. "$here/../common/lib.sh"
step=${1:-}
shift || true
[[ -z "$step" || "$step" == image || "${1:-}" == /* ]] || { echo "run.sh: RUN must be an absolute path" >&2; exit 2; }

case "$step" in
image)
  bench_image "$here/sandbox" "bench-$suite:$(date -u +%Y%m%d)" "$here/image.txt"
  ;;
setup)
  run=$1
  shift
  bench_setup "$run" "$here/image.txt" "$suite" "${*:+smoke dirs: $*}"
  echo "upstream=https://github.com/pjd/pjdfstest@85a8aea9e685999ef0540392fd80535f873d7ff7 (classic C binary + tests/**/*.t, run as uid 501; run-group.sh: sh FILE.t, file timeout 100 s, start budget 40 s, a file that sleeps starts only first, group timeout 105 s)" >>"$run/identity.txt"
  mkdir -p "$run/seed" "$run/tap"
  printf 'pjdfstest seed: the run creates pjd/<dir> in the Workspace.\n' >"$run/seed/README"
  bench_client "$run" setup setup.mjs "$run/seed" "$@"
  ;;
lock) bench_lock "$1" ;;
unlock) bench_unlock "$1" ;;
group)
  bench_client "$1" "$(bench_next "$1" group)" group.mjs
  ;;
finish)
  bench_client "$1" finish finish.mjs commit
  ;;
repro)
  bench_client "$1" "$(bench_next "$1" repro)" repro.mjs
  ;;
teardown)
  bench_client "$1" teardown finish.mjs
  ;;
cleanup)
  grep -q '"step":"teardown"' "$1/ledger.jsonl" || { echo "run.sh: no teardown in $1/ledger.jsonl; run finish or teardown first" >&2; exit 2; }
  bench_cleanup "$1"
  ;;
*)
  sed -n '2,19p' "$0" >&2
  exit 2
  ;;
esac
