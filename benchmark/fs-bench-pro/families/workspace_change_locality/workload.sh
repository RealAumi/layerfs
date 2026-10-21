#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
edit_writer=${EDIT_WRITER:-/code/writers/edit}
case "$1" in
  apply)
    case "$2" in
      workspace-clean-commit-*) echo 'clean Commit must use control_only with no Exec' >&2; exit 2 ;;
      workspace-distributed-sdk-edit-*) exec "$edit_writer" apply-workspace "$2" ;;
      *) exec "$writer" workspace-apply "$2" 1 0 performance ;;
    esac ;;
  verify) exec "$writer" workspace-verify-tree "$2" 1 1 ;;
  *) exit 2 ;;
esac
