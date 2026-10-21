#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || exit 2
case "$1" in
  reader|verifier) ;;
  *) exit 2 ;;
esac
case "$2" in
  v016-access-boundary-before-v1|v016-access-boundary-after-v1|v016-access-inode-before-v1|v016-access-inode-after-v1|v016-access-fork-point-v1|v016-access-divergent-head-v1) ;;
  *) exit 2 ;;
esac
exec "${WORKLOAD_HELPER:-/code/writers/workload}" v016-access-read "$2" 1 "$1"
