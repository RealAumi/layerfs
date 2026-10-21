#!/bin/bash
set -euo pipefail
case "$1" in
  apply)
    test "$2" = small-file-delta-10x30-v1
    test "$3" -ge 1 && test "$3" -le 30
    exec "${WORKLOAD_WRITER:-/code/writers/workload}" storage-smoke-import "/code/history/checkpoints/step-$3" "$PWD"
    ;;
  verify)
    test "$2" = small-file-delta-10x30-v1
    exec "${EDIT_WRITER:-/code/writers/edit}" verify-manifest /code/history/manifests/state-30.tsv
    ;;
  *) exit 2 ;;
esac
