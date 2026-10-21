# syntax=docker/dockerfile:1
# pjdfstest Sandbox image: the fs-bench base plus the classic pjdfstest
# (C binary and tests/**/*.t) at a pinned upstream commit, built with its
# own autotools as root at build time, and run-group.sh, which runs one test
# directory as the Sandbox user. Debian bookworm packages only.
#
#   run.sh image   (lib.sh bench_image builds it under a 115 s alarm)
FROM fs-bench-computer:gawk-20261020

ARG PJD_COMMIT=85a8aea9e685999ef0540392fd80535f873d7ff7

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends autoconf automake \
 && rm -rf /var/lib/apt/lists/*

RUN git init -q /opt/pjdfstest \
 && cd /opt/pjdfstest \
 && git fetch -q --depth 1 https://github.com/pjd/pjdfstest.git "$PJD_COMMIT" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "$PJD_COMMIT" \
 && autoreconf -ifs \
 && ./configure -q \
 && make -j2 pjdfstest \
 && test -x ./pjdfstest \
 && printf '%s\n' "$PJD_COMMIT" >/opt/pjdfstest/COMMIT

COPY run-group.sh /opt/pjd-bench/run-group.sh
RUN chmod 0755 /opt/pjd-bench/run-group.sh
