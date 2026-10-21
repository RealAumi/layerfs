# Shared shell steps for the SDK-route suites; source it from a suite's
# run.sh after setting `suite` (its folder name). Each client step runs one
# SDK client (common/client.sh) under the 115 s limit (bench_timeout) and
# logs its step, times, exit and the 1-minute load to RUN/commands.log.
#
# Measured steps hold the measurement lock (bench_lock / bench_unlock), so
# only one suite measures at a time on this host; building, image work and
# smoke runs need no lock. A measured run takes it before its setup client.
# Every global set here starts with bench_; key=value files (image.txt,
# deploy.env) are read with bench_field, never sourced.
bench_common=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
bench_repo=$(cd "$bench_common/../.." && pwd -P)
bench_runtime=layerfs-352-runtime:node24
bench_bin=$bench_repo/core/target/fs-bench-bin
bench_base=sha256:66aeb6bbf7fc825686a0e6d8c8486d90c99d03ce81f854008f179a23bdf4097e
bench_base_tag=fs-bench-computer:gawk-20261020
bench_lockdir=$bench_repo/benchmark-results/.measure.lock
# The per-command ceiling (s) for clients, builds and passthrough execs.
bench_limit=115

bench_load() { uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,; }

# bench_timeout SECS COMMAND [ARG...]: COMMAND under a wall-clock limit
# (watchdog.pl): TERM to it and its descendants at SECS, KILL 3 s later,
# exit 124. Unlike a perl alarm it also stops the docker CLI.
bench_timeout() { perl "$bench_common/watchdog.pl" "$@"; }

# bench_field FILE KEY -> the value of the first KEY=value line ('' if none).
bench_field() { sed -n "s/^$2=//p" "$1" | head -n 1; }

# bench_client RUN NAME SCRIPT [ARG...]: one client under bench_limit.
# After a timeout the client's container (named by client.sh) is removed.
bench_client() {
  local run=$1 name=$2 script=$3 start status=0 l0
  shift 3
  start=$(date -u +%FT%TZ)
  l0=$(bench_load)
  bench_timeout "$bench_limit" "$bench_common/client.sh" "$run" "$suite" "$script" "$@" \
    >"$run/$name.out" 2>"$run/$name.err" || status=$?
  if [[ $status -eq 124 ]]; then
    bench_timeout 30 docker rm -f "$(bench_field "$run/deploy.env" prefix)${script%.mjs}" >>"$run/$name.err" 2>&1 || true
  fi
  printf '%s\t%s\t%s\texit=%s\tload=%s\n' "$name" "$start" "$(date -u +%FT%TZ)" "$status" "$l0" >>"$run/commands.log"
  tail -n 5 "$run/$name.out"
  [[ $status -eq 0 ]] || { echo "$name: exit $status (see $run/$name.err)" >&2; tail -n 8 "$run/$name.err" >&2; exit "$status"; }
}

# bench_next RUN STEP -> STEP-N, the first unused name.
bench_next() {
  local n=1
  while [[ -e "$1/$2-$n.out" ]]; do n=$((n + 1)); done
  echo "$2-$n"
}

# bench_image CONTEXT_DIR TAG OUT_FILE: build the suite's Sandbox image FROM
# the pinned base tag (checked against its digest) and write image=<digest>.
# Several build commands may be needed under the 115 s ceiling; BuildKit's
# cache carries finished layers between them.
bench_image() {
  local ctx=$1 tag=$2 out=$3 digest
  [[ "$(docker image inspect "$bench_base_tag" --format '{{.Id}}')" == "$bench_base" ]] || { echo "lib.sh: $bench_base_tag is not $bench_base" >&2; exit 2; }
  bench_timeout "$bench_limit" docker build --load -q -t "$tag" "$ctx" >/dev/null
  digest=$(docker image inspect "$tag" --format '{{.Id}}')
  printf 'image=%s\ntag=%s\nbase=%s\n' "$digest" "$tag" "$bench_base" >"$out"
  cat "$out"
}

# bench_setup RUN IMAGE_FILE PROJECT [NOTE]: new run folder, its two volumes,
# deploy.env and identity.txt (with lock=taken when the run already holds
# the lock). The caller then runs its setup client.
bench_setup() {
  local run=$1 imagefile=$2 project=$3 note=${4:-} id volume home_volume image tag
  [[ "$run" == "$bench_repo"/benchmark-results/"$suite"/* && ! -e "$run" ]] || { echo "lib.sh: RUN must be a new folder under $bench_repo/benchmark-results/$suite" >&2; exit 2; }
  image=$(bench_field "$imagefile" image) tag=$(bench_field "$imagefile" tag)
  [[ "$image" == sha256:* ]] || { echo "lib.sh: no image=sha256:... in $imagefile" >&2; exit 2; }
  id=$(basename "$run")
  volume=bench-$suite-$id home_volume=bench-$suite-$id-sdk-home
  for v in "$volume" "$home_volume"; do
    ! docker volume inspect "$v" >/dev/null 2>&1 || { echo "lib.sh: volume $v exists" >&2; exit 2; }
  done
  mkdir -p "$run"
  docker volume create "$volume" >/dev/null
  docker volume create "$home_volume" >/dev/null
  printf 'image=%q\nvolume=%q\nhome_volume=%q\nbin=%q\nruntime=%q\nproject=%q\nprefix=%q\n' \
    "$image" "$volume" "$home_volume" "$bench_bin" "$bench_runtime" "$project" "bench-$suite-$id-" >"$run/deploy.env"
  {
    echo "suite=$suite run=$id started=$(date -u +%FT%TZ) $note"
    echo "image=$image ($tag) base=$bench_base runtime=$bench_runtime@$(docker image inspect "$bench_runtime" --format '{{.Id}}')"
    shasum -a 256 "$bench_bin/layerfs-daemon" "$bench_bin/layerfs.node"
    echo "source=$(git -C "$bench_repo" rev-parse HEAD) harness_dirty_files=$(git -C "$bench_repo" status --porcelain -- "benchmark/$suite" benchmark/common | wc -l | tr -d ' ')"
    echo "policy=wholeFileDepth 16, chunkDepth 8, metadataDepth 8; profile Disposable; LAYERFS_CONSTRUCTION_WORKERS=1; trace off"
    echo "docker=$(docker version --format '{{.Server.Version}}') $(docker info --format '{{.OperatingSystem}} {{.KernelVersion}} cpus={{.NCPU}} mem={{.MemTotal}}')"
  } >"$run/identity.txt"
  if [[ "$(awk '{print $2}' "$bench_lockdir/owner" 2>/dev/null)" == "$run" ]]; then
    echo "lock=taken $(awk '{print $3}' "$bench_lockdir/owner") (before setup)" >>"$run/identity.txt"
  fi
}

# bench_lock RUN: take the measurement lock (one measuring suite per host).
# Exit 75 when another run holds it; the caller waits and asks again. RUN
# need not exist yet: bench_setup then records the lock in identity.txt.
bench_lock() {
  local run=$1
  mkdir -p "$(dirname "$bench_lockdir")"
  if mkdir "$bench_lockdir" 2>/dev/null; then
    echo "$suite $run $(date -u +%FT%TZ)" >"$bench_lockdir/owner"
    if [[ -f "$run/identity.txt" ]]; then echo "lock=taken $(date -u +%FT%TZ)" >>"$run/identity.txt"; fi
  else
    echo "lib.sh: measurement lock held by: $(cat "$bench_lockdir/owner" 2>/dev/null)" >&2
    exit 75
  fi
}

# bench_unlock RUN: release the lock if this run holds it.
bench_unlock() {
  local run=$1
  if [[ -f "$bench_lockdir/owner" ]] && [[ "$(awk '{print $2}' "$bench_lockdir/owner")" == "$run" ]]; then
    rm -rf "$bench_lockdir"
    echo "lock=released $(date -u +%FT%TZ)" >>"$run/identity.txt"
  else
    echo "lib.sh: $run does not hold the lock" >&2
  fi
}

# bench_cleanup RUN: remove the run's two volumes (after the teardown client).
bench_cleanup() {
  local run=$1 volume home_volume
  volume=$(bench_field "$run/deploy.env" volume) home_volume=$(bench_field "$run/deploy.env" home_volume)
  bench_timeout 60 docker volume rm "$volume" "$home_volume"
  echo "removed=$volume $home_volume at $(date -u +%FT%TZ)" >>"$run/identity.txt"
}
