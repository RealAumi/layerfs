#!/usr/bin/env bash
# Runs one JS SDK client from this folder in the Linux runtime image, the way
# the SDK's own verify harness runs Linux clients
# (sdk/js/test/verify/container.mjs): the checkout at its host path, the
# daemon and addon folders read-only, the Docker socket, and the Store volume
# at /layerfs-store. The deployment comes from HOME/deploy.env, written by
# run-holder.sh. Every client's LAYERFS_HOME is /layerfs-sdk/home on the
# named volume deploy.env names, which the SDK creates private to the
# client's user on first use. So a later client finds the holder's Sandbox
# from the shared records. stdin and stdout pass through.
#
#   client.sh HOME SCRIPT [ARG...]
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: $0 HOME SCRIPT [ARG...]" >&2; exit 2; }
home=$1 script=$2
shift 2
[[ "$home" == /* && -f "$home/deploy.env" ]] || { echo "client.sh: $home/deploy.env is missing" >&2; exit 2; }
[[ "$script" =~ ^[a-z-]+\.mjs$ ]] || { echo "client.sh: unsafe script name $script" >&2; exit 2; }
# shellcheck source=/dev/null
. "$home/deploy.env"
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)
runtime=${LAYERFS_RUNTIME_IMAGE:-layerfs-352-runtime:node24}
folders=()
for f in "$(dirname "$daemon")" "$(dirname "$addon")"; do
  case "$f" in "$repo"/*) ;; *) folders+=(-v "$f:$f:ro") ;; esac
done
exec docker run --rm -i --name "${prefix}${script%.mjs}" \
  -v "$repo:$repo" ${folders[@]+"${folders[@]}"} \
  -v /var/run/docker.sock:/var/run/docker.sock -v "$volume:/layerfs-store" \
  -v "$home_volume:/layerfs-sdk" -e LAYERFS_HOME=/layerfs-sdk/home \
  -e LAYERFS_DOCKER=/var/run/docker.sock \
  -e LAYERFS_IMAGE="$image" -e LAYERFS_VOLUME="$volume" \
  -e LAYERFS_DAEMON="$daemon" -e LAYERFS_NATIVE="$addon" \
  -e LAYERFS_CONTAINER_PREFIX="$prefix" -e LAYERFS_CONSTRUCTION_WORKERS=1 \
  -e LAYERFS_STORE_PATH=/layerfs-store/global/store.sqlite \
  -e LAYERFS_DAEMON_HOST=host.docker.internal \
  -e FS_BENCH_PROJECT="$project" \
  -w "$repo" --entrypoint node "$runtime" \
  "benchmark/fs-bench/holder/$script" "$@"
