#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
case "$1" in
  apply) exec "$writer" workspace-apply "$2" 1 0 performance ;;
  verify) exec "$writer" workspace-verify-tree "$2" 1 1 ;;
  *) exit 2 ;;
esac
