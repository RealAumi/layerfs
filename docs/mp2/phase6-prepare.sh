#!/bin/bash
set -euo pipefail
cd ~/lfs-remote/mp2-remote-store
mkdir -p phase6/bin phase6/config phase6/receipts phase6/image
cp -a phase5/bin/. phase6/bin/
cp phase5/image/Dockerfile phase6/image/
/usr/local/bin/docker build -t mp2-p6-tools phase6/image
