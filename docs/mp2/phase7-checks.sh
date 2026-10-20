#!/bin/bash
set -euo pipefail
# Run in the scoped Linux build container, from /work.
export CARGO_HOME=/target/cargo-home CARGO_TARGET_DIR=/target/cargo
export CARGO_TERM_COLOR=never
# Each selected test was compiled with --no-run before this command.
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-fuse --tests
timeout 120 cargo test --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-daemon --test workspace_databases
cargo clippy --manifest-path core/Cargo.toml --locked -j 2 -p layerfs-fuse --all-targets -- -D warnings
cargo clippy --manifest-path core/Cargo.toml --locked -j 2 -p fuser --lib -- -D warnings
timeout 30 rustfmt --edition 2024 --check core/vendor/fuser-0.18.0/src/session/receive_stop.rs core/vendor/fuser-0.18.0/src/session/lifecycle.rs
timeout 30 rustfmt --edition 2024 --config skip_children=true --check core/vendor/fuser-0.18.0/src/session.rs
timeout 30 rustfmt --edition 2021 --check core/crates/layerfs-fuse/src/session/drain.rs
timeout 120 python3 -B core/tools/check_fuser_integrity.py
timeout 120 python3 -B -m unittest discover -s core/tools -p 'test_*.py'
# Retain the guard's existing nonzero verdict separately, without hiding it.
set +e
timeout 120 python3 -B core/tools/check_product_boundary.py
result=$?
echo "PRODUCT_BOUNDARY_EXIT=$result"
exit "$result"
