#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
edit=${EDIT_WRITER:-/code/writers/edit}
recipe=${WORKSPACE_RECIPE:-/code/writers/recipe}
case "${2:-}" in
  v016-workspace-mixed-100mb-5000-k10-v1) tier=L100; commits=10; workers=2 ;;
  v016-workspace-mixed-100mb-5000-k100-v1) tier=L100; commits=100; workers=2 ;;
  v016-workspace-mixed-500mb-30000-k10-v1) tier=L500; commits=10; workers=2 ;;
  v016-workspace-mixed-500mb-30000-k100-v1) tier=L500; commits=100; workers=2 ;;
  v016-workspace-four-100mb-5000-k100-v1) tier=L100; commits=100; workers=4 ;;
  *) exit 2 ;;
esac
case "${1:-}" in
  stage|verify-step)
    [[ "${3:-}" =~ ^[1-9][0-9]*$ ]] && (( $3 <= commits )) || exit 2
    if [[ "$1" == stage ]]; then worker=${4:-}; else worker=${5:-}; fi
    [[ "$worker" =~ ^[0-3]$ ]] && (( worker < workers )) || exit 2
    ;;
  witness)
    [[ "$workers" == 2 && "${3:-}" == 0 ]] || exit 2
    marker=${5:-}
    [[ -n "${4:-}" && "$marker" =~ ^[0-9a-f]+$ ]] && (( ${#marker} == 512 )) || exit 2
    exec "$writer" v016-m1-witness "$4" "$5"
    ;;
  *) exit 2 ;;
esac
if [[ "$1" == verify-step ]]; then
  exec "$recipe" verify-context "$2" "$worker" "$3" . "$4"
fi
cycle=$(( ($3 - 1) / 5 + 1 ))
stage=$(( ($3 - 1) % 5 + 1 ))
if (( stage == 2 )); then
  [[ -n "${SDK_STEP_DESCRIPTOR:-}" && -n "${SDK_STEP_DESCRIPTOR_SHA256:-}" ]] || exit 2
fi
"$writer" v016-m1-stage "$tier" 1 "$cycle" "$worker" "branch$worker" "$stage"
if (( stage == 2 )); then
  "$edit" apply-context-step-prepared "$2" "$worker" "$3" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256" 1
  "$edit" apply-context-step-prepared "$2" "$worker" "$3" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256" 2
fi
