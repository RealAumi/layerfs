#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
edit_writer=${EDIT_WRITER:-/code/writers/edit}
case "$1" in
  apply)
    case "$2" in
      v016-boundary-alias-roundtrip-v1)
        if [[ "$3" == 5 ]]; then
          exec "$edit_writer" apply-boundary-alias "$3" "$writer"
        fi
        exec "$writer" v016-boundary-alias 1 "$3" ;;
      *)
        if [[ -n ${SDK_STEP_DESCRIPTOR:-} || -n ${SDK_STEP_DESCRIPTOR_SHA256:-} ]]; then
          : "${SDK_STEP_DESCRIPTOR:?prepared original descriptor required}"
          : "${SDK_STEP_DESCRIPTOR_SHA256:?prepared original descriptor seal required}"
          exec "$edit_writer" apply-sdk-step-prepared "$2" "$3" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256"
        fi
        exec "$edit_writer" apply-sdk-step "$2" "$3" ;;
    esac ;;
  verify)
    if [[ $# == 4 ]]; then
      exec "$edit_writer" verify "$2" "$3" "$4"
    fi
    exec "$edit_writer" verify "$2" "$3" ;;
  *) exit 2 ;;
esac
