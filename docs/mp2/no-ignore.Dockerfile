FROM node:22-bookworm AS node
FROM public.ecr.aws/docker/library/rust:1.85.1-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jdk-headless maven python3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 runner
