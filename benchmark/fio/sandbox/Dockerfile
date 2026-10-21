# syntax=docker/dockerfile:1
# fio Sandbox image: the fs-bench measurement image plus fio from Debian
# bookworm apt (3.33; no upstream build). The exact fio and package versions
# go to /opt/fio-identity.txt. The only fetch is Debian's package archive;
# the RUN stays well under the 115 s build ceiling.
#
#   run.sh image
FROM fs-bench-computer:gawk-20261020

RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends fio \
 && rm -rf /var/lib/apt/lists/* \
 && { echo "fio_version=$(fio --version)"; \
      echo "fio_package=$(dpkg-query -W -f '${Version}' fio)"; \
      echo "libaio=$(dpkg-query -W -f '${Version}' libaio1)"; \
    } >/opt/fio-identity.txt \
 && cat /opt/fio-identity.txt
