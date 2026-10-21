#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then
  printf '%s\n' 'usage: workload.sh apply|verify CASE' >&2
  exit 2
fi
writer=${EDIT_WRITER:-/code/writers/edit}
case "$1" in
  apply) exec "$writer" apply "$2" ;;
  verify) exec "$writer" verify "$2" 1 ;;
  *) printf '%s\n' 'expected apply or verify' >&2; exit 2 ;;
esac
