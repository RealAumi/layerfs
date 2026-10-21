#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
[[ "$#" == 2 ]] || exit 2
case "$2" in
  dedup-workspace-exact-100|dedup-workspace-local-100|dedup-workspace-unique-100|dedup-workspace-unique-500|dedup-workspace-unique-1-base128-v3) ;;
  *) exit 2 ;;
esac
case "$1" in
  apply) exec "$writer" workspace-apply "$2" 1 0 performance ;;
  verify) exec "$writer" workspace-verify-tree "$2" 1 1 ;;
  *) exit 2 ;;
esac
