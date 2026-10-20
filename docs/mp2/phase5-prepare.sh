#!/bin/bash
set -euo pipefail
cd ~/lfs-remote/mp2-remote-store
mkdir -p phase5/bin phase5/config phase5/receipts phase5/image
cp -a phase4/bin/. phase5/bin/
cp phase4/image/Dockerfile phase5/image/
/usr/local/bin/docker build -t mp2-p5-tools phase5/image
