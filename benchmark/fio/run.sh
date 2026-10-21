#!/usr/bin/env bash
# fio, one step per command. Each client step runs one SDK client
# (common/client.sh) under the 115 s limit and logs its step, times, exit and
# the 1-minute load to RUN/commands.log (common/lib.sh); passthrough-fuse
# steps run client/pt.mjs on the host the same way (common/passthrough.sh).
#
#   run.sh image                         build bench-fio:<date>; benchmark-results/fio/image.txt
#   run.sh pt-image                      build <image tag>-pt (passthrough_ll); benchmark-results/fio/pt-image.txt
#   run.sh setup RUN RUNTIME SEQ RAND SYNC MODE [ARMS [FILES]]
#                                        volumes, identity, RUN/params.env (RUNTIME s per job; file
#                                        sizes as fio --size, e.g. 1g 512m 64m; ARMS two (v1.0.0, the
#                                        default) or three (adds passthrough-fuse); FILES keep (default)
#                                        or drop, three arms only, see below), then start
#   run.sh start RUN MODE                MODE measured takes the measurement lock (exit 75 while another
#                                        run holds it: wait, then start again), smoke does not; Init,
#                                        create, fork, mount; three arms: start the passthrough sibling
#   run.sh next RUN                      the next step of the plan below (repeat until DONE)
#   run.sh teardown RUN                  stop the sibling, unmount, close, remove the volumes, release the lock
#   run.sh report RUN [OUT]              results.csv, commit.csv, summary.json (and ratios.csv) (report.py)
#
# RUN is a new folder benchmark-results/fio/<UTC yyyymmddTHHMMSSZ> (smoke
# runs: smoke-<id>). The plan lays out each arm's data files (untimed), runs
# each fio job in the layerfs arm, then sandbox-disk, then (three arms)
# passthrough-fuse, and ends with one sandbox.commit of the layerfs
# Workspace in its own client. With FILES drop, once every arm has run the
# last job that uses seq or sync, that file is removed (untimed) from the
# sandbox-disk and passthrough-fuse folders, so the three arms' later jobs
# share the VM's page cache under similar pressure; the layerfs copy stays
# for the Commit. No later job reads a removed file.
set -euo pipefail
suite=fio
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=../common/lib.sh
. "$here/../common/lib.sh"
imagefile=$bench_repo/benchmark-results/fio/image.txt
ptimagefile=$bench_repo/benchmark-results/fio/pt-image.txt
# shellcheck source=../common/passthrough.sh
. "$bench_common/passthrough.sh"
jobs=(seq-write seq-read rand-write rand-read rand-read-4j randrw-70-30 sync-write rand-write-direct rand-read-direct)

# plan RUN: the steps of this run, from its params.env (no arms= is v1.0.0's two-arm plan).
plan() {
  local arms files j a
  arms=$(sed -n 's/^arms=//p' "$1/params.env") files=$(sed -n 's/^files=//p' "$1/params.env")
  [[ "$arms" == three ]] && arms=(layerfs sandbox-disk passthrough-fuse) || arms=(layerfs sandbox-disk)
  for a in "${arms[@]}"; do echo "layout:$a"; done
  for j in "${jobs[@]}"; do
    for a in "${arms[@]}"; do echo "$j:$a"; done
    # seq's last job is seq-read, sync's is sync-write; rand is used to the end.
    if [[ "$files" == drop && ( "$j" == seq-read || "$j" == sync-write ) ]]; then
      echo "drop-${j%%-*}:sandbox-disk"
      echo "drop-${j%%-*}:passthrough-fuse"
    fi
  done
  echo commit
}

# pt_client RUN NAME MODE [ARG]: client/pt.mjs on the host under the 115 s
# limit (bench_timeout stops node and its docker exec children), logged to RUN/commands.log as bench_client logs an SDK client.
pt_client() {
  local run=$1 name=$2 start status=0 l0
  shift 2
  start=$(date -u +%FT%TZ)
  l0=$(bench_load)
  bench_timeout "$bench_limit" node "$here/client/pt.mjs" "$@" "$run" >"$run/$name.out" 2>"$run/$name.err" || status=$?
  printf '%s\t%s\t%s\texit=%s\tload=%s\n' "$name" "$start" "$(date -u +%FT%TZ)" "$status" "$l0" >>"$run/commands.log"
  tail -n 5 "$run/$name.out"
  [[ $status -eq 0 ]] || { echo "$name: exit $status (see $run/$name.err)" >&2; tail -n 8 "$run/$name.err" >&2; exit "$status"; }
}
step=${1:-}
shift || true

case "$step" in
image)
  mkdir -p "$(dirname "$imagefile")"
  bench_image "$here/sandbox" "bench-fio:$(date -u +%Y%m%d)" "$imagefile"
  docker run --rm --entrypoint cat "$(sed -n 's/^image=//p' "$imagefile")" /opt/fio-identity.txt >>"$imagefile"
  ;;
pt-image)
  bench_pt_image "$(sed -n 's/^tag=//p' "$imagefile")" "$ptimagefile"
  ;;
setup)
  run=$1 secs=$2 seq=$3 rand=$4 sync=$5 mode=$6 arms=${7:-two} files=${8:-keep}
  [[ "$mode" == measured || "$mode" == smoke ]] || { echo "run.sh: MODE is measured or smoke" >&2; exit 2; }
  [[ "$secs" =~ ^[1-9][0-9]*$ ]] || { echo "run.sh: RUNTIME is a positive integer" >&2; exit 2; }
  for s in "$seq" "$rand" "$sync"; do [[ "$s" =~ ^[1-9][0-9]*[kmg]$ ]] || { echo "run.sh: sizes look like 512m" >&2; exit 2; }; done
  [[ "$arms" == two || "$arms" == three ]] || { echo "run.sh: ARMS is two or three" >&2; exit 2; }
  [[ "$files" == keep || ( "$files" == drop && "$arms" == three ) ]] || { echo "run.sh: FILES is keep, or drop with three arms" >&2; exit 2; }
  if [[ "$arms" == three ]]; then
    [[ "$(sed -n 's/^pt_base=//p' "$ptimagefile")" == "$(sed -n 's/^image=//p' "$imagefile")" ]] \
      || { echo "run.sh: $ptimagefile is not built on $(sed -n 's/^image=//p' "$imagefile"); run.sh pt-image" >&2; exit 2; }
  fi
  bench_setup "$run" "$imagefile" fio "mode=$mode runtime=$secs seq=$seq rand=$rand sync=$sync arms=$arms files=$files"
  grep -E '^(fio_version|fio_package|libaio)=' "$imagefile" | sed 's/^/image_/' >>"$run/identity.txt"
  printf 'runtime=%s\nseq_size=%s\nrand_size=%s\nsync_size=%s\n' "$secs" "$seq" "$rand" "$sync" >"$run/params.env"
  [[ "$arms" == two ]] || printf 'arms=%s\nfiles=%s\n' "$arms" "$files" >>"$run/params.env"
  mkdir "$run/seed"
  echo "LayerFS fio benchmark Workspace; fio works under fio/." >"$run/seed/README"
  exec "$0" start "$run" "$mode"
  ;;
start)
  run=$1 mode=$2
  [[ "$mode" == smoke ]] || bench_lock "$run"
  bench_client "$run" setup setup.mjs "$run/seed"
  if grep -qs '^arms=three' "$run/params.env"; then
    bench_pt_start "$run" "$ptimagefile"
    echo "pt_client=node $(node --version) client/pt.mjs on the host" >>"$run/identity.txt"
    pt_client "$run" pt-probe probe
  fi
  ;;
next)
  run=$1
  for s in $(plan "$run"); do
    case "$s" in
    commit)
      grep -qs '"step":"commit"' "$run/ledger.jsonl" && continue
      bench_client "$run" commit commit.mjs
      ;;
    layout:passthrough-fuse)
      grep -qs '"arm":"passthrough-fuse"' "$run/layout.jsonl" && continue
      pt_client "$run" layout-passthrough-fuse layout
      ;;
    layout:*)
      grep -qs "\"arm\":\"${s#*:}\"" "$run/layout.jsonl" && continue
      bench_client "$run" "layout-${s#*:}" layout.mjs "${s#*:}"
      ;;
    drop-*)
      f=${s%%:*} f=${f#drop-}
      grep -qs "\"file\":\"$f\",\"arm\":\"${s#*:}\"" "$run/drop.jsonl" && continue
      if [[ "${s#*:}" == passthrough-fuse ]]; then
        pt_client "$run" "drop-$f-passthrough-fuse" drop "$f"
      else
        bench_client "$run" "drop-$f-sandbox-disk" drop.mjs "$f"
      fi
      ;;
    *:passthrough-fuse)
      grep -qs "\"case\":\"${s/:/-}\"" "$run/results.jsonl" && continue
      pt_client "$run" "$(bench_next "$run" "job-${s/:/-}")" job "${s%%:*}"
      ;;
    *)
      grep -qs "\"case\":\"${s/:/-}\"" "$run/results.jsonl" && continue
      bench_client "$run" "$(bench_next "$run" "job-${s/:/-}")" job.mjs "${s%%:*}" "${s#*:}"
      ;;
    esac
    exit 0
  done
  echo DONE
  ;;
teardown)
  run=$1
  if docker inspect "$(bench_pt_name "$run")" >/dev/null 2>&1; then bench_pt_stop "$run"; fi
  bench_client "$run" teardown teardown.mjs
  bench_cleanup "$run"
  if grep -q '^lock=taken' "$run/identity.txt"; then bench_unlock "$run"; fi
  ;;
report)
  python3 "$here/report.py" "$@"
  ;;
*)
  sed -n '2,30p' "$0" >&2
  exit 2
  ;;
esac
