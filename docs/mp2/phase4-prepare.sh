#!/bin/bash
set -euo pipefail
cd ~/lfs-remote/mp2-remote-store
D=/usr/local/bin/docker
printf '%s\n' 'FROM public.ecr.aws/docker/library/rust:1.85.1-bookworm' 'RUN apt-get update && apt-get install -y --no-install-recommends iproute2 iputils-ping strace && rm -rf /var/lib/apt/lists/*' > phase4/image/Dockerfile
$D build -t mp2-p4-tools phase4/image
$D run --rm --name mp2-p4-build -v "$PWD/source:/work" -w /work -e CARGO_HOME=/work/.cargo-home -e CARGO_TARGET_DIR=/work/target-remote mp2-p4-tools cargo build --manifest-path core/Cargo.toml --locked -j 2 --profile test -p layerfs-remote-store --bin layerfs-store
cp source/target-remote/debug/layerfs-store phase4/bin/
$D run --rm --name mp2-p4-npm --network none -v "$PWD/phase4/work:/work" -w /work public.ecr.aws/docker/library/node:22-bookworm-slim timeout 120 npm ci --offline --ignore-scripts --cache /work/npm-cache-root --no-audit --no-fund
