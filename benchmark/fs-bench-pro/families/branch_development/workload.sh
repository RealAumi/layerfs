#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
edit=${EDIT_WRITER:-/code/writers/edit}
recipe=${WORKSPACE_RECIPE:-/code/writers/recipe}
[[ $# -ge 4 ]] || exit 2
mode=$1
case_id=$2
role=$3
local_step=$4
case "$case_id" in
  v016-branch-mixed-100mb-5000-k10-v1) tier=L100; commits=10 ;;
  v016-branch-mixed-100mb-5000-k100-v1) tier=L100; commits=100 ;;
  v016-branch-mixed-500mb-30000-k10-v1) tier=L500; commits=10 ;;
  v016-branch-mixed-500mb-30000-k100-v1) tier=L500; commits=100 ;;
  v016-branch-convergent-content-v1|v016-branch-fork-descendant-v1) tier=compact; commits=10 ;;
  *) exit 2 ;;
esac
case "$role" in
  trunk) tag=0; salt=branch0; cycle_start=1; maximum=10 ;;
  a) tag=1; salt=branch1; cycle_start=2; maximum=$commits ;;
  b) tag=2; salt=branch2; cycle_start=2; maximum=$commits ;;
  c)
    [[ "$case_id" == v016-branch-fork-descendant-v1 ]] || exit 2
    maximum=10 ;;
  *) exit 2 ;;
esac
[[ ${#local_step} -le 3 && "$local_step" =~ ^(0|[1-9][0-9]*)$ ]] && (( local_step <= maximum )) || exit 2
case "$mode" in
  stage)
    [[ $# -eq 4 ]] && (( local_step >= 1 )) || exit 2
    stage=$(( (local_step - 1) % 5 + 1 ))
    if [[ "$tier" == compact ]] || (( stage == 2 )); then
      [[ -n "${SDK_STEP_DESCRIPTOR:-}" && "${SDK_STEP_DESCRIPTOR_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || exit 2
    fi
    if [[ "$tier" == compact ]]; then
      exec "$edit" apply-context-step-prepared "$case_id" "$role" "$local_step" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256" 1
    fi
    cycle=$(( (local_step - 1) / 5 + cycle_start ))
    "$writer" v016-m1-stage "$tier" 1 "$cycle" "$tag" "$salt" "$stage"
    if (( stage == 2 )); then
      "$edit" apply-context-step-prepared "$case_id" "$role" "$local_step" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256" 1
      "$edit" apply-context-step-prepared "$case_id" "$role" "$local_step" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256" 2
    fi
    ;;
  verify-step)
    [[ $# -eq 6 ]] || exit 2
    if [[ "$tier" == compact ]]; then
      [[ "$6" == - ]] || exit 2
    fi
    exec "$recipe" verify-context "$case_id" "$role" "$local_step" "$5" "$6"
    ;;
  *) exit 2 ;;
esac
