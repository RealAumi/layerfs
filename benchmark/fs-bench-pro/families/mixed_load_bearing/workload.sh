#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
edit=${EDIT_WRITER:-/code/writers/edit}
recipe=${WORKSPACE_RECIPE:-/code/writers/recipe}
case "$1" in
  apply) exec "$writer" workspace-apply "$2" 1 0 performance ;;
  verify) exec "$writer" workspace-verify-tree "$2" 1 1 ;;
  stage)
    case "$2" in
      v016-mixed-development-100mb-5000-k10-v1) tier=L100; commits=10 ;;
      v016-mixed-development-100mb-5000-k100-v1|v016-mixed-exhaustive-100mb-5000-k100-v1) tier=L100; commits=100 ;;
      v016-mixed-development-500mb-30000-k10-v1) tier=L500; commits=10 ;;
      v016-mixed-development-500mb-30000-k100-v1|v016-mixed-exhaustive-500mb-30000-k100-v1) tier=L500; commits=100 ;;
      *) exit 2 ;;
    esac
    [[ "$3" =~ ^[1-9][0-9]*$ ]] && (( $3 <= commits )) || exit 2
    cycle=$(( ($3 - 1) / 5 + 1 ))
    stage=$(( ($3 - 1) % 5 + 1 ))
    if (( stage == 2 )) && [[ -n "${SDK_STEP_DESCRIPTOR:-}${SDK_STEP_DESCRIPTOR_SHA256:-}" ]]; then
      [[ -n "${SDK_STEP_DESCRIPTOR:-}" && -n "${SDK_STEP_DESCRIPTOR_SHA256:-}" ]] || exit 2
    fi
    "$writer" v016-m1-stage "$tier" 1 "$cycle" 0 branch0 "$stage"
    if (( stage == 2 )); then
      if [[ -n "${SDK_STEP_DESCRIPTOR:-}" ]]; then
        "$edit" apply-sdk-step-prepared "$2" "$3" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256" 1
        "$edit" apply-sdk-step-prepared "$2" "$3" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256" 2
      else
        "$edit" apply-sdk-step "$2" "$3" 1
        "$edit" apply-sdk-step "$2" "$3" 2
      fi
    fi
    ;;
  verify-step) exec "$recipe" verify-m1-step "$2" "$3" . "$4" ;;
  *) exit 2 ;;
esac
