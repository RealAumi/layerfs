#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
edit=${EDIT_WRITER:-/code/writers/edit}
[[ $# == 3 ]] || exit 2
route=$1; id=$2; step=$3
[[ $step =~ ^(0|[1-9][0-9]*)$ ]] || exit 2
case "$id" in
  dedup-history-distributed-1) maximum=1; kind=distributed ;;
  dedup-history-distributed-100) maximum=100; kind=distributed ;;
  dedup-history-distributed-500) maximum=500; kind=distributed ;;
  dedup-history-hotset-1) maximum=1; kind=hotset ;;
  dedup-history-hotset-100) maximum=100; kind=hotset ;;
  dedup-history-recurring-1) maximum=1; kind=recurring ;;
  dedup-history-recurring-100) maximum=100; kind=recurring ;;
  dedup-history-metadata-1) maximum=1; kind=metadata ;;
  dedup-history-metadata-100) maximum=100; kind=metadata ;;
  dedup-history-unrelated-1) maximum=1; kind=unrelated ;;
  dedup-history-unrelated-100-mixed-v2) maximum=100; kind=unrelated ;;
  dedup-history-unrelated-500-mixed-v2) maximum=500; kind=unrelated ;;
  v016-history-large-hotset-k10-v1) maximum=10; kind=large-hotset ;;
  v016-history-large-hotset-k100-v1) maximum=100; kind=large-hotset ;;
  v016-history-namespace-inode-k10-v1) maximum=10; kind=namespace-inode ;;
  v016-history-namespace-inode-k100-v1) maximum=100; kind=namespace-inode ;;
  v016-history-boundary-cycle-k10-v1) maximum=10; kind=boundary-cycle ;;
  v016-history-boundary-cycle-k100-v1) maximum=100; kind=boundary-cycle ;;
  *) exit 2 ;;
esac
(( step <= maximum )) || exit 2
apply_sdk_step() {
  if [[ -n ${SDK_STEP_DESCRIPTOR:-} || -n ${SDK_STEP_DESCRIPTOR_SHA256:-} ]]; then
    [[ -n ${SDK_STEP_DESCRIPTOR:-} && -n ${SDK_STEP_DESCRIPTOR_SHA256:-} ]] || exit 2
    exec "$edit" apply-sdk-step-prepared "$id" "$step" "$SDK_STEP_DESCRIPTOR" "$SDK_STEP_DESCRIPTOR_SHA256"
  fi
  exec "$edit" apply-sdk-step "$id" "$step"
}
case "$route" in
  apply)
    (( step >= 1 )) || exit 2
    case "$kind" in
      metadata|unrelated) exec "$writer" workspace-apply "$id" 1 "$((step-1))" performance ;;
      namespace-inode)
        cycle=$(((step-1)/5+1)); stage=$(((step-1)%5+1))
        if (( stage == 2 )); then apply_sdk_step; fi
        exec "$writer" v016-hn-stage 1 "$cycle" "$stage" ;;
      *) apply_sdk_step ;;
    esac ;;
  verify) exec "$writer" workspace-verify-tree "$id" 1 "$step" ;;
  *) exit 2 ;;
esac
