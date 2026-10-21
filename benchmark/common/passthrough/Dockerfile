# syntax=docker/dockerfile:1
# FUSE baseline image: a suite's own Sandbox image (BASE, by local tag checked
# against its digest by passthrough.sh) plus libfuse's example passthrough_ll
# at the tag matching Debian bookworm's libfuse3 (fuse-3.14.0), built against
# libfuse3-dev. The tools the suite measures are the same bytes as in its
# Sandbox image; only the FUSE server is added.
ARG BASE
FROM ${BASE}

ARG LIBFUSE_COMMIT=3f65bb699cd2f0afe2b9519c39d29922229f2168
LABEL dev.layerfs.passthrough.upstream="https://github.com/libfuse/libfuse" \
      dev.layerfs.passthrough.commit="${LIBFUSE_COMMIT}"

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends libfuse3-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*

RUN for f in passthrough_ll.c passthrough_helpers.h; do \
      curl -fsSL "https://raw.githubusercontent.com/libfuse/libfuse/${LIBFUSE_COMMIT}/example/$f" -o "/opt/$f" || exit 1; \
    done \
 && gcc -O2 -Wall -I/opt -o /usr/local/bin/passthrough_ll /opt/passthrough_ll.c $(pkg-config fuse3 --cflags --libs) \
 && { echo "libfuse_commit=${LIBFUSE_COMMIT}"; \
      echo "passthrough_ll_c_sha256=$(sha256sum /opt/passthrough_ll.c | cut -d' ' -f1)"; \
      echo "passthrough_helpers_h_sha256=$(sha256sum /opt/passthrough_helpers.h | cut -d' ' -f1)"; \
      echo "passthrough_ll_sha256=$(sha256sum /usr/local/bin/passthrough_ll | cut -d' ' -f1)"; \
      echo "libfuse3=$(dpkg-query -W -f '${Version}' libfuse3-3)"; \
      echo "gcc=$(gcc -dumpfullversion)"; \
    } >/opt/passthrough-identity.txt \
 && cat /opt/passthrough-identity.txt
