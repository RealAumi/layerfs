FROM node:20.19.0-bookworm AS node20
FROM cxn-tools:noignore02-pnpm
COPY --from=node20 /usr/local/bin/node /usr/local/bin/node
