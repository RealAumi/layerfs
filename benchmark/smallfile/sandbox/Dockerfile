# syntax=docker/dockerfile:1
# smallfile Sandbox image: the fs-bench measurement image plus
# distributed-system-analysis/smallfile at a pinned commit in /opt/smallfile.
# smallfile is pure Python 3; PyYAML (optional, for --yaml-input-file) comes
# from Debian bookworm. numpy/scipy serve only its response-time statistics
# script, which this suite does not run. The only other fetch is the pinned
# upstream commit. Each RUN stays well under the 115 s build ceiling.
#
#   run.sh image
FROM fs-bench-computer:gawk-20261020

ARG SMALLFILE_URL=https://github.com/distributed-system-analysis/smallfile
ARG SMALLFILE_COMMIT=aa2519de5bf0b3b383db2c31eacbf8ac4328e19c
LABEL dev.layerfs.smallfile.upstream="${SMALLFILE_URL}" \
      dev.layerfs.smallfile.commit="${SMALLFILE_COMMIT}"

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends python3-yaml \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/smallfile
RUN git init -q . \
 && git fetch -q --depth 1 "$SMALLFILE_URL" "$SMALLFILE_COMMIT" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "$SMALLFILE_COMMIT" \
 && python3 smallfile_cli.py --help >/dev/null \
 && { echo "smallfile_commit=$(git rev-parse HEAD)"; \
      echo "smallfile_version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"; \
      echo "python=$(python3 -c 'import platform; print(platform.python_version())')"; \
      echo "pyyaml=$(dpkg-query -W -f '${Version}' python3-yaml)"; \
    } >/opt/smallfile-identity.txt \
 && cat /opt/smallfile-identity.txt

WORKDIR /
