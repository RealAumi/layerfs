#!/usr/bin/env bash
set -euo pipefail
# Native setup and independent byte/metadata verification only; Init is engine-owned.
[[ $# == 3 ]] || { echo 'fixture|verify CASE ROOT required' >&2; exit 2; }
case "$2" in
  dedup-cross-file-anchor-1|dedup-cross-file-unique-100|dedup-cross-file-identical-100|dedup-cross-file-mixed-100) ;;
  *) exit 2 ;;
esac
case "$1" in
  fixture) exec "${WORKSPACE_RECIPE:?sealed native recipe required}" fixture "$2" "$3" ;;
  verify) exec "${WORKSPACE_RECIPE:?sealed native recipe required}" verify-step "$2" 0 "$3" ;;
  *) echo 'fixture|verify required; imports have no filesystem apply' >&2; exit 2 ;;
esac
