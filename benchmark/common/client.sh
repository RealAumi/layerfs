#!/usr/bin/env bash
# Runs one suite client (benchmark/SUITE/client/SCRIPT) in the SDK runtime
# image, as dsh-dedup's client.sh does: the checkout at its host path, the
# daemon and addon folder read-only, the Docker socket, the Store volume at
# /layerfs-store and the SDK home on its own named volume. The deployment
# comes from RUN/deploy.env (lib.sh bench_setup). RUN is inside the
# checkout, so the client reads and appends its ledger files at that path.
#
#   client.sh RUN SUITE SCRIPT [ARG...]
set -euo pipefail
[[ $# -ge 3 ]] || { echo "usage: $0 RUN SUITE SCRIPT [ARG...]" >&2; exit 2; }
run=$1 suite=$2 script=$3
shift 3
[[ "$run" == /* && -f "$run/deploy.env" ]] || { echo "client.sh: $run/deploy.env is missing" >&2; exit 2; }
[[ "$suite" =~ ^[a-z0-9-]+$ ]] || { echo "client.sh: unsafe suite name $suite" >&2; exit 2; }
[[ "$script" =~ ^[a-z0-9-]+\.mjs$ ]] || { echo "client.sh: unsafe script name $script" >&2; exit 2; }
# shellcheck source=/dev/null
. "$run/deploy.env"
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
case "$run" in "$repo"/*) ;; *) echo "client.sh: $run is outside $repo" >&2; exit 2 ;; esac
[[ -f "$repo/benchmark/$suite/client/$script" ]] || { echo "client.sh: no benchmark/$suite/client/$script" >&2; exit 2; }
exec docker run --rm -i --name "${prefix}${script%.mjs}" \
  -v "$repo:$repo" -v "$bin:$bin:ro" \
  -v /var/run/docker.sock:/var/run/docker.sock -v "$volume:/layerfs-store" \
  -v "$home_volume:/layerfs-sdk" -e LAYERFS_HOME=/layerfs-sdk/home \
  -e LAYERFS_DOCKER=/var/run/docker.sock \
  -e LAYERFS_IMAGE="$image" -e LAYERFS_VOLUME="$volume" \
  -e LAYERFS_DAEMON="$bin/layerfs-daemon" -e LAYERFS_NATIVE="$bin/layerfs.node" \
  -e LAYERFS_CONTAINER_PREFIX="$prefix" -e LAYERFS_CONSTRUCTION_WORKERS=1 \
  -e LAYERFS_STORE_PATH=/layerfs-store/global/store.sqlite \
  -e LAYERFS_DAEMON_HOST=host.docker.internal \
  -e BENCH_HOME="$run" -e BENCH_PROJECT="$project" \
  -w "$repo" --entrypoint node "$runtime" \
  "benchmark/$suite/client/$script" "$@"
