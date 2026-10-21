# syntax=docker/dockerfile:1
# The measurement image with GNU awk as `awk`, one layer over the image
# built from ./Dockerfile. fs-bench.sh prints its statistics with awk's %d,
# and Debian's default mawk saturates that at 2**31 - 1: a row of 2.147 s or
# more reads as 2,147,483,647 ns (pair 20261019T194736Z). awk runs only after
# each row's clock stops, so this changes no timed work. gawk takes the awk
# alternative over mawk by priority; the build fails unless it did.
#
#   docker tag <Dockerfile image> fs-bench-computer:base
#   docker build --platform linux/arm64 --build-arg BASE=fs-bench-computer:base \
#     -f benchmark/fs-bench/computer/gawk.Dockerfile -t <tag> benchmark/fs-bench/computer
ARG BASE
FROM --platform=linux/arm64 ${BASE}

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends gawk \
 && rm -rf /var/lib/apt/lists/* \
 && test "$(readlink -f "$(command -v awk)")" = /usr/bin/gawk \
 && test "$(awk 'BEGIN { printf "%d", 3000000000 }')" = 3000000000
