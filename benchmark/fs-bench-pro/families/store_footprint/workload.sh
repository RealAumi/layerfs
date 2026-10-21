#!/usr/bin/env bash
set -euo pipefail
writer=${WORKLOAD_WRITER:-/code/writers/workload}
[[ "$#" -ge 2 ]] || exit 2
case "$2" in
  store-footprint-unique-100000|store-footprint-metadata-cardinality-100000|store-footprint-large-object-500m) tier=100000 ;;
  store-footprint-unique-100-low-v1|store-footprint-metadata-cardinality-100-low-v1) tier=100 ;;
  *) exit 2 ;;
esac
case "$1" in
  fixture) [[ "$#" == 3 ]] || exit 2; exec "$writer" store-footprint-fixture "$3" "$2" "$tier" ;;
  verify-source) [[ "$#" == 3 ]] || exit 2; exec "$writer" store-footprint-digest "$3" ;;
  apply) [[ "$#" == 3 ]] || exit 2; exec "$writer" namespace-edit "$3" ;;
  verify) [[ "$#" == 5 ]] || exit 2; exec "$writer" digest-range-inode "$3" "$4" "$5" ;;
  *) exit 2 ;;
esac
