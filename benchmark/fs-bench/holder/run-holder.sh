#!/usr/bin/env bash
# Starts holder.mjs for the `layerfs-core` arm. HOME is a new host directory
# that the holder and run.sh's `sdk` mode share: this script saves the
# deployment there as deploy.env, creates the named volume VOLUME-sdk-home
# for the SDK home (see client.sh), then runs the holder through client.sh.
# stdin is passed through; closing it makes the holder unmount and close.
#
#   run-holder.sh HOME IMAGE_DIGEST VOLUME DAEMON ADDON PROJECT PREFIX
set -euo pipefail
[[ $# -eq 7 ]] || { echo "usage: $0 HOME IMAGE_DIGEST VOLUME DAEMON ADDON PROJECT PREFIX" >&2; exit 2; }
home=$1
[[ "$home" == /* && ! -e "$home" ]] || { echo "run-holder.sh: HOME must be a new absolute path" >&2; exit 2; }
home_volume="$3-sdk-home"
! docker volume inspect "$home_volume" >/dev/null 2>&1 || { echo "run-holder.sh: $home_volume already exists" >&2; exit 2; }
docker volume create "$home_volume" >/dev/null
mkdir -p "$home"
printf 'image=%q\nvolume=%q\nhome_volume=%q\ndaemon=%q\naddon=%q\nproject=%q\nprefix=%q\n' \
  "$2" "$3" "$home_volume" "$4" "$5" "$6" "$7" >"$home/deploy.env"
exec "$(dirname "${BASH_SOURCE[0]}")/client.sh" "$home" holder.mjs "$6" /tmp/fs-bench-source
