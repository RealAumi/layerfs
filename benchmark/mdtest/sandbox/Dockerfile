# syntax=docker/dockerfile:1
# mdtest Sandbox image: the fs-bench base plus IOR/mdtest from the pinned
# hpc/ior commit, built with its own route (./bootstrap, ./configure,
# make -j2) against Debian bookworm's Open MPI (libopenmpi-dev,
# openmpi-bin). Installs /usr/local/bin/mdtest and writes
# /opt/mdtest-identity.txt. Each RUN is one cached layer, so every docker
# build command stays under the 115 s alarm (common/lib.sh bench_image).
#
#   run.sh image
FROM fs-bench-computer:gawk-20261020

ARG IOR_URL=https://github.com/hpc/ior.git
ARG IOR_COMMIT=f1172addabada77d13cf37773d1ffdb202b4fc4a
LABEL dev.layerfs.mdtest.upstream="${IOR_URL}" \
      dev.layerfs.mdtest.commit="${IOR_COMMIT}"

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends autoconf automake libtool pkg-config \
      libopenmpi-dev openmpi-bin \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ior
RUN git init -q . \
 && git fetch -q --depth 1 "$IOR_URL" "$IOR_COMMIT" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "$IOR_COMMIT"

RUN ./bootstrap >/dev/null && ./configure >/opt/ior/configure.out

RUN make -j2 >/dev/null \
 && install -m 755 src/mdtest /usr/local/bin/mdtest \
 && { echo "ior_commit=$(git rev-parse HEAD)"; \
      echo "mdtest_sha256=$(sha256sum /usr/local/bin/mdtest | cut -d' ' -f1)"; \
      echo "mdtest_version=$(sed -n 's/^#define META_VERSION "\(.*\)"/\1/p' src/config.h)"; \
      echo "mpi=openmpi-bin_$(dpkg-query -W -f '${Version}' openmpi-bin),libopenmpi-dev_$(dpkg-query -W -f '${Version}' libopenmpi-dev)"; \
      echo "gcc=$(gcc -dumpfullversion)"; \
    } >/opt/mdtest-identity.txt \
 && cat /opt/mdtest-identity.txt

WORKDIR /
