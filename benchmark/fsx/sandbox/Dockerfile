# syntax=docker/dockerfile:1
# fsx Sandbox image: the fs-bench measurement image plus xfstests-dev's
# ltp/fsx at a pinned commit, built with the upstream autotools route
# (make configure, ./configure, make -C lib, make -C ltp fsx; CHECK_CMD=true
# as the top-level Makefile exports it when sparse is off). Packages come
# from Debian bookworm; the only other fetch is the pinned upstream commit.
# Each RUN stays well under the 115 s per-build-command ceiling (lib.sh
# bench_image), so BuildKit's cache carries finished layers between builds.
#
#   run.sh image
FROM fs-bench-computer:gawk-20261020

ARG XFSTESTS_URL=https://git.kernel.org/pub/scm/fs/xfs/xfstests-dev.git
ARG XFSTESTS_COMMIT=22348afe338c0f6d540c0d7ef0db749eaa51b218
LABEL dev.layerfs.fsx.upstream="${XFSTESTS_URL}" \
      dev.layerfs.fsx.commit="${XFSTESTS_COMMIT}"

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends autoconf automake libtool pkg-config \
      xfslibs-dev uuid-dev libattr1-dev libacl1-dev libaio-dev liburing-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/xfstests
RUN git init -q . \
 && git fetch -q --depth 1 "$XFSTESTS_URL" "$XFSTESTS_COMMIT" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "$XFSTESTS_COMMIT"

RUN make configure >/dev/null && ./configure >/opt/xfstests/configure.out \
 && grep -E '^(HAVE_AIO|HAVE_URING|HAVE_FALLOCATE|HAVE_COPY_FILE_RANGE) ' include/builddefs

RUN make -j2 -C lib CHECK_CMD=true >/dev/null && make -C ltp CHECK_CMD=true fsx \
 && install -m 755 ltp/fsx /usr/local/bin/fsx \
 && { echo "xfstests_commit=$(git rev-parse HEAD)"; \
      echo "fsx_sha256=$(sha256sum /usr/local/bin/fsx | cut -d' ' -f1)"; \
      echo "gcc=$(gcc -dumpfullversion)"; \
      echo "liburing=$(dpkg-query -W -f '${Version}' liburing-dev)"; \
      echo "libaio=$(dpkg-query -W -f '${Version}' libaio-dev)"; \
      echo "xfslibs=$(dpkg-query -W -f '${Version}' xfslibs-dev)"; \
      grep -E '^(HAVE_AIO|HAVE_URING|HAVE_FALLOCATE|HAVE_COPY_FILE_RANGE) ' include/builddefs | tr -d ' \t' | sort -u; \
    } >/opt/fsx-identity.txt \
 && cat /opt/fsx-identity.txt

WORKDIR /
