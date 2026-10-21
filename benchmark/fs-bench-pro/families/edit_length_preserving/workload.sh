#!/usr/bin/env bash
set -euo pipefail
writer=${EDIT_WRITER:-/code/writers/edit}
case "$1" in
  apply) exec "$writer" apply "$2" ;;
  verify) exec "$writer" verify "$2" 1 ;;
  *) exit 2 ;;
esac
