#!/usr/bin/env bash
# Runs one dsh-dedup client (client/SCRIPT) in the SDK runtime image, as
# fs-bench's holder/client.sh does: the checkout at its host path, the
# daemon and addon folder read-only, the Docker socket, the Store volume at
# /layerfs-store and the SDK home on its own named volume. The deployment
# comes from RUN/deploy.env (run.sh setup). RUN is inside the checkout, so
# the client reads and appends its ledger files at the same path.
#
#   client.sh RUN SCRIPT [ARG...]
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: $0 RUN SCRIPT [ARG...]" >&2; exit 2; }
run=$1 script=$2
shift 2
[[ "$run" == /* && -f "$run/deploy.env" ]] || { echo "client.sh: $run/deploy.env is missing" >&2; exit 2; }
[[ "$script" =~ ^[a-z]+\.mjs$ ]] || { echo "client.sh: unsafe script name $script" >&2; exit 2; }
# shellcheck source=/dev/null
. "$run/deploy.env"
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)
case "$run" in "$repo"/*) ;; *) echo "client.sh: $run is outside $repo" >&2; exit 2 ;; esac
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
  -e DSH_HOME="$run" -e DSH_PROJECT="$project" \
  -w "$repo" --entrypoint node "$runtime" \
  "benchmark/dsh-dedup/client/$script" "$@"
