# syntax=docker/dockerfile:1
# fsstress Sandbox image: the fs-bench base plus xfstests-dev's fsstress
# (ltp/fsstress.c) built from the pinned commit with its own autotools
# build (configure, lib/libtest, then `make -C ltp fsstress`), installed as
# /usr/local/bin/fsstress, and this suite's in-Sandbox scripts under
# /opt/fsstress-bench. Each RUN is one cached layer so every docker build
# command stays under the 115 s alarm (lib.sh bench_image).
FROM fs-bench-computer:gawk-20261020

ARG XFSTESTS_URL=https://git.kernel.org/pub/scm/fs/xfs/xfstests-dev.git
ARG XFSTESTS_COMMIT=22348afe338c0f6d540c0d7ef0db749eaa51b218
LABEL dev.layerfs.fsstress.upstream="${XFSTESTS_URL}" \
      dev.layerfs.fsstress.commit="${XFSTESTS_COMMIT}"

# Build dependencies from Debian bookworm, as xfstests' README lists them
# for fsstress: autotools, XFS headers and libhandle, uuid, acl/attr, aio and
# io_uring, and pkg-config for its m4 macros.
RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends autoconf automake libtool libtool-bin pkg-config \
      xfslibs-dev uuid-dev libacl1-dev libattr1-dev libaio-dev liburing-dev \
 && rm -rf /var/lib/apt/lists/*

RUN git init -q /src/xfstests-dev \
 && cd /src/xfstests-dev \
 && git fetch -q --depth 1 "$XFSTESTS_URL" "$XFSTESTS_COMMIT" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "$XFSTESTS_COMMIT"

RUN cd /src/xfstests-dev && make configure >/dev/null && make include/builddefs >/dev/null

RUN cd /src/xfstests-dev && make -j2 -C lib >/dev/null && make -C ltp fsstress \
 && install -m 0755 ltp/fsstress /usr/local/bin/fsstress \
 && fsstress -S c | head -c 4000 && echo

COPY run-case.sh manifest.py /opt/fsstress-bench/
RUN chmod 0755 /opt/fsstress-bench/run-case.sh /opt/fsstress-bench/manifest.py
