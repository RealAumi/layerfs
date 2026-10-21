#!/usr/bin/env bash
# fsstress, one step per command. Each client step runs one SDK client
# (common/client.sh) under the 115 s limit and logs its step, times, exit and
# the 1-minute load to RUN/commands.log (lib.sh bench_client).
#
#   run.sh image                              build bench-fsstress:<yyyymmdd>, write image.txt
#   run.sh lock     RUN                       take the measurement lock (measured runs: first)
#   run.sh setup    RUN [NOTE]                volumes, deploy.env, identity; Init, create, fork, mount
#   run.sh case     RUN CASE ARM SEED PROCS OPS   one fsstress exec, then its logs read back
#   run.sh capture  RUN                       manifest, Commit, fork, second mount, manifest, compare
#   run.sh repro    RUN                       diagnostic: minimal repros of the layerfs-only failures
#   run.sh teardown RUN                       unmount and close
#   run.sh cleanup  RUN                       remove the run's two volumes
#   run.sh unlock   RUN                       release the measurement lock
#
# CASE is c1 or c2 (the tree is fss-CASE); ARM is layerfs (the mounted
# Workspace, <path>/fss-CASE) or sandbox-disk (/tmp/fss-CASE in the Sandbox
# container). RUN is a new absolute folder under benchmark-results/fsstress/.
set -euo pipefail
suite=fsstress
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=../common/lib.sh
. "$here/../common/lib.sh"
step=${1:-}
shift || true

case "$step" in
image)
  bench_image "$here/sandbox" "bench-$suite:$(date -u +%Y%m%d)" "$here/image.txt"
  ;;
setup)
  run=$1 note=${2:-}
  bench_setup "$run" "$here/image.txt" "$suite" "$note"
  echo "upstream=https://git.kernel.org/pub/scm/fs/xfs/xfstests-dev.git@22348afe338c0f6d540c0d7ef0db749eaa51b218 ltp/fsstress.c (configure; make -C lib; make -C ltp fsstress)" >>"$run/identity.txt"
  mkdir -p "$run/seed" "$run/logs"
  printf 'fsstress seed: the run creates fss-<case> in the Workspace.\n' >"$run/seed/README"
  bench_client "$run" setup setup.mjs "$run/seed"
  ;;
lock) bench_lock "$1" ;;
unlock) bench_unlock "$1" ;;
case)
  run=$1 c=$2 arm=$3 seed=$4 procs=$5 ops=$6
  [[ "$c" =~ ^c[12]$ && "$arm" =~ ^(layerfs|sandbox-disk)$ && "$seed$procs$ops" =~ ^[0-9]+$ ]] \
    || { echo "run.sh: CASE c1|c2, ARM layerfs|sandbox-disk, numeric SEED PROCS OPS" >&2; exit 2; }
  echo "case=$c arm=$arm args=fsstress -d <arm>/fss-$c -p $procs -n $ops -s $seed -v -V -o /tmp/fsslog/$c-$arm.log" >>"$run/identity.txt"
  bench_client "$run" "case-$c-$arm" case.mjs "$c" "$arm" "$seed" "$procs" "$ops"
  ;;
repro)
  bench_client "$1" repro repro.mjs
  ;;
capture)
  bench_client "$1" capture-commit capture.mjs commit
  bench_client "$1" capture-verify capture.mjs verify
  ;;
teardown)
  bench_client "$1" teardown teardown.mjs
  ;;
cleanup)
  bench_cleanup "$1"
  ;;
*)
  sed -n '2,18p' "$0" >&2
  exit 2
  ;;
esac
