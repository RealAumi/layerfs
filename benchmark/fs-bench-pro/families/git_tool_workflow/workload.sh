#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
export LAYERFS_V013_GIT_REFERENCE=${LAYERFS_V013_GIT_REFERENCE:-/code/git-reference}
case "$1" in
  apply) exec "$writer" workspace-apply "$2" 1 0 performance ;;
  qualify) exec "$writer" workspace-apply "$2" 1 0 verify ;;
  verify) exec "$writer" workspace-git-verify "$2" 1 "$LAYERFS_V013_GIT_REFERENCE" ;;
  *) exit 2 ;;
esac
