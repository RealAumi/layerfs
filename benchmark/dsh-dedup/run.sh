#!/usr/bin/env bash
# dsh-dedup, one step per command. Each client step runs one SDK client
# (client/client.sh) under a 115 s alarm and logs its step, times, exit and
# the 1-minute load to RUN/commands.log.
#
#   run.sh image   PREPARED                 build the Sandbox image from prepare.py's context
#   run.sh setup   RUN PREPARED STRIDE      volumes, deploy.env, selection; Init of state 1
#   run.sh segment RUN                      apply / verify / Commit the next states (repeat until DONE)
#   run.sh history RUN                      fork, mount and verify every Commit (repeat until DONE)
#   run.sh finish  RUN                      Commit list, close; Store files and counts
#   run.sh cleanup RUN                      remove the run's two volumes
#
# RUN is a new absolute folder inside this checkout (for example
# benchmark-results/dsh-dedup/<id>-s10); STRIDE is 10, 3 or 1.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
repo=$(cd "$here/../.." && pwd -P)
runtime=layerfs-352-runtime:node24
bin=$repo/core/target/fs-bench-bin
base=sha256:66aeb6bbf7fc825686a0e6d8c8486d90c99d03ce81f854008f179a23bdf4097e
base_tag=fs-bench-computer:gawk-20261020
step=${1:-}
shift || true

load() { uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,; }

client() { # client RUN NAME SCRIPT [ARG...]
  local run=$1 name=$2 script=$3 start status=0
  shift 3
  start=$(date -u +%FT%TZ)
  local l0; l0=$(load)
  perl -e 'alarm 115; exec @ARGV' "$here/client/client.sh" "$run" "$script" "$@" \
    >"$run/$name.out" 2>"$run/$name.err" || status=$?
  printf '%s\t%s\t%s\texit=%s\tload=%s\n' "$name" "$start" "$(date -u +%FT%TZ)" "$status" "$l0" >>"$run/commands.log"
  tail -n 3 "$run/$name.out"
  [[ $status -eq 0 ]] || { echo "$name: exit $status (see $run/$name.err)" >&2; tail -n 5 "$run/$name.err" >&2; exit "$status"; }
}

next_name() { # next_name RUN STEP -> STEP-N
  local n=1
  while [[ -e "$1/$2-$n.out" ]]; do n=$((n + 1)); done
  echo "$2-$n"
}

case "$step" in
image)
  prepared=$1
  [[ "$(docker image inspect "$base_tag" --format '{{.Id}}')" == "$base" ]] || { echo "run.sh: $base_tag is not $base" >&2; exit 2; }
  tag=dsh-dedup:$(basename "$prepared")
  docker build --load -q -t "$tag" "$prepared/context" >/dev/null
  digest=$(docker image inspect "$tag" --format '{{.Id}}')
  printf 'image=%s\ntag=%s\nbase=%s\n' "$digest" "$tag" "$base" >"$prepared/image.txt"
  cat "$prepared/image.txt"
  ;;
setup)
  run=$1 prepared=$2 stride=$3
  [[ "$run" == "$repo"/* && ! -e "$run" ]] || { echo "run.sh: RUN must be a new folder inside $repo" >&2; exit 2; }
  [[ "$stride" =~ ^(10|3|1)$ ]] || { echo "run.sh: STRIDE is 10, 3 or 1" >&2; exit 2; }
  # shellcheck source=/dev/null
  . "$prepared/image.txt"
  id=$(basename "$run")
  volume=dsh-dedup-$id home_volume=dsh-dedup-$id-sdk-home
  for v in "$volume" "$home_volume"; do
    ! docker volume inspect "$v" >/dev/null 2>&1 || { echo "run.sh: volume $v exists" >&2; exit 2; }
  done
  mkdir -p "$run"
  docker volume create "$volume" >/dev/null
  docker volume create "$home_volume" >/dev/null
  printf 'image=%q\nvolume=%q\nhome_volume=%q\nbin=%q\nruntime=%q\nproject=%q\nprefix=%q\nstride=%q\nprepared=%q\n' \
    "$image" "$volume" "$home_volume" "$bin" "$runtime" "dshdedup-s$stride" "dshdedup-$id-" "$stride" "$prepared" >"$run/deploy.env"
  # The old history selections (history_corpus.py SELECTIONS).
  python3 - "$stride" "$prepared/states.json" >"$run/selection.json" <<'EOF'
import json, sys
stride = int(sys.argv[1]); n = len(json.load(open(sys.argv[2]))["states"])
picked = sorted(set(range(1, n + 1, 10)) | {n}) if stride == 10 else list(range(1, n + 1, stride))
print(json.dumps(picked))
EOF
  {
    echo "run=$id stride=$stride started=$(date -u +%FT%TZ)"
    echo "image=$image ($tag) base=$base runtime=$runtime@$(docker image inspect "$runtime" --format '{{.Id}}')"
    shasum -a 256 "$bin/layerfs-daemon" "$bin/layerfs.node"
    echo "source=$(git -C "$repo" rev-parse HEAD) harness_dirty_files=$(git -C "$repo" status --porcelain | wc -l | tr -d ' ')"
    echo "prepared=$prepared states=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["states"]))' "$prepared/states.json") selected=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$run/selection.json")"
    echo "policy=wholeFileDepth 16, chunkDepth 8, metadataDepth 8; profile Disposable; LAYERFS_CONSTRUCTION_WORKERS=1; trace off"
    echo "docker=$(docker version --format '{{.Server.Version}}') $(docker info --format '{{.OperatingSystem}} {{.KernelVersion}} cpus={{.NCPU}} mem={{.MemTotal}}')"
  } >"$run/identity.txt"
  client "$run" setup setup.mjs "$prepared/state1"
  ;;
segment)
  run=$1
  client "$run" "$(next_name "$run" segment)" segment.mjs
  ;;
history)
  run=$1
  client "$run" "$(next_name "$run" history)" history.mjs
  ;;
finish)
  run=$1
  # shellcheck source=/dev/null
  . "$run/deploy.env"
  client "$run" finish finish.mjs
  docker run --rm -v "$volume:/s:ro" --entrypoint sh "$runtime" -c \
    'cd /s && find . -type f -exec stat -c "%n %s %b %B" {} +' >"$run/store-files.txt"
  docker run --rm -v "$volume:/s" -v "$repo:$repo:ro" -w "$repo" --entrypoint node "$runtime" \
    benchmark/dsh-dedup/client/inspect.mjs /s/global/store.sqlite >"$run/store.json"
  cat "$run/store-files.txt"
  ;;
cleanup)
  run=$1
  # shellcheck source=/dev/null
  . "$run/deploy.env"
  docker volume rm "$volume" "$home_volume"
  echo "removed=$volume $home_volume at $(date -u +%FT%TZ)" >>"$run/identity.txt"
  ;;
*)
  sed -n '2,15p' "$0" >&2
  exit 2
  ;;
esac
