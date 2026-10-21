#!/usr/bin/env bash
set -euo pipefail
# This family imports a native tree; its command only constructs that fixture.
exec "${NAMESPACE_WRITER:?sealed native fixture writer required}" "$1" "$2"
