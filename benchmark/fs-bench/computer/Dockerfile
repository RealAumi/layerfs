# syntax=docker/dockerfile:1
# Native linux/arm64 image for the computer-upstream arm, recovered from the
# 2026-08-25/27 runs (images layerfs-lane-a-cloudflare-computerd-native:attempt-1
# and its git layer, layerfs-lane-a-cloudflare-fs-bench:attempt-2 =
# sha256:8c5100fabfd8...; both since deleted). The two Dockerfiles are merged
# here; the steps are unchanged.
#
# Build context: a clean export of Computer at the pinned commit, for example
#   git -C ~/Ephemeral-AI-Lab/study/cloudflare-computer archive de87919a4 | tar -x -C <ctx>
#   docker build --platform linux/arm64 -f benchmark/fs-bench/computer/Dockerfile -t <tag> <ctx>
#
# fuse-native ships an x64-only libfuse. The repair below is the one upstream
# documents for arm64 hosts in its AGENTS.md: copy the system libfuse.so.2 over
# the bundled library in node_modules, then node-gyp rebuild. No tracked
# Computer source is changed. computerd runs from its source CLI under native
# Node, with FUSE_MOUNT=fuse so it cannot fall back to the shim.
FROM --platform=linux/arm64 alpine:3.23 AS certificates

FROM --platform=linux/arm64 node:22-bookworm-slim

LABEL dev.layerfs.upstream-commit="de87919a4fd37242e960e13b7b3ba802d1eef0a0" \
      dev.layerfs.upstream-tree="4fb409d7e1356e1098439293d77d2fdc2dbf2190"

COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends build-essential libfuse-dev python3 \
 && rm -rf /var/lib/apt/lists/*

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends ca-certificates curl file fuse3 jq procps util-linux \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/cloudflare-computer
COPY --exclude=.git . .

RUN npm ci --ignore-scripts --no-audit --no-fund \
      --workspace @cloudflare/computerd \
      --workspace @cloudflare/computer-rpc \
      --workspace @cloudflare/dofs \
      --include-workspace-root \
 && printf '%s\n' 'bundled-libfuse-before-repair' \
 && file node_modules/fuse-shared-library-linux/libfuse/lib/libfuse.so \
 && sha256sum node_modules/fuse-shared-library-linux/libfuse/lib/libfuse.so \
 && cp /usr/lib/aarch64-linux-gnu/libfuse.so.2 node_modules/fuse-shared-library-linux/libfuse/lib/libfuse.so \
 && printf '%s\n' 'system-libfuse-after-repair' \
 && file node_modules/fuse-shared-library-linux/libfuse/lib/libfuse.so \
 && sha256sum node_modules/fuse-shared-library-linux/libfuse/lib/libfuse.so \
 && cd node_modules/fuse-native \
 && node /usr/local/lib/node_modules/npm/node_modules/node-gyp/bin/node-gyp.js rebuild \
 && file build/Release/fuse.node \
 && sha256sum build/Release/fuse.node \
 && cd /opt/cloudflare-computer \
 && npm run build --workspace @cloudflare/computer-rpc \
 && npm run build --workspace @cloudflare/computerd

# The measurement layer: git for the "git init + commit 100 files" row.
RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends git \
 && git --version \
 && rm -rf /var/lib/apt/lists/*

ENV FUSE_MOUNT=fuse \
    MOUNT_POINT=/workspace \
    PORT=45678

CMD ["node", "packages/computerd/dist/cli/computerd.cjs"]
