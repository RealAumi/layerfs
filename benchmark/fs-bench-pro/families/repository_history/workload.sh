#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 4 ]] || exit 2
mode=$1
case_id=$2
index=$3
path=$4
case "$case_id" in
  deepseek-full) states=157 ;;
  deepseek-stride3) states=53 ;;
  deepseek-stride10) states=17 ;;
  *) exit 2 ;;
esac
[[ ${#index} -le 3 && "$index" =~ ^[1-9][0-9]*$ ]] && (( index <= states )) || exit 2
[[ -n "$path" ]] || exit 2
writer=${WORKLOAD_WRITER:-/code/writers/workload}
mount=${LAYERFS_WORKSPACE_ROOT:-/workspace}
case "$mode" in
  apply) exec "$writer" storage-smoke-import "$path" "$mount" ;;
  verify) exec "$writer" storage-smoke-observe "$mount" "$path" ;;
  *) exit 2 ;;
esac
