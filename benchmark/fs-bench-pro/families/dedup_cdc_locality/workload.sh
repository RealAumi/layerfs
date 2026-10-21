#!/usr/bin/env bash
set -euo pipefail
# Native input only. The engine owns the one public fresh-Store Project Init.
fail() { printf '%s\n' "$1" >&2; exit 2; }
[[ $# == 3 ]] || fail 'fixture|verify-native CASE NATIVE_ROOT required'
operation=$1
case_id=$2
root=$3
case "$case_id" in
  dedup-cdc-boundaries-proof) ;;
  dedup-cdc-overwrite-*|dedup-cdc-insert-*|dedup-cdc-delete-*|dedup-cdc-common-body-*|dedup-cdc-scattered-*)
    tier=${case_id##*-}
    case "$tier" in 100) ;; *) fail 'unregistered original CDC tier' ;; esac
    # Exact reconstruction refuses prefixes such as overwrite-extra-1.
    profile=${case_id#dedup-cdc-}
    profile=${profile%-*}
    case "$profile" in overwrite|insert|delete|common-body|scattered) ;;
      *) fail 'unregistered original CDC profile' ;; esac
    [[ "$case_id" == "dedup-cdc-$profile-$tier" ]] || fail 'unregistered original CDC case'
    ;;
  *) fail 'unregistered original CDC case' ;;
esac
[[ -n "$root" ]] || fail 'native root required'
case "$operation" in
  fixture) exec "${WORKSPACE_RECIPE:?sealed native recipe required}" fixture "$case_id" "$root" ;;
  verify-native) exec "${WORKSPACE_RECIPE:?sealed native recipe required}" verify-step "$case_id" 0 "$root" ;;
  *) fail 'CDC imports run through public Project Init, not a filesystem apply' ;;
esac
