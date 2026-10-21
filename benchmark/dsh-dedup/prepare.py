#!/usr/bin/env python3
"""Prepares dsh-dedup from the 157-checkpoint corpus. Setup only, untimed.

    prepare.py CORPUS OUT [COUNT]

Takes checkpoints 1..COUNT (default all 157, corpus order) and writes:
  OUT/corpus/blobs/<git blob id>            every blob those states use, once
  OUT/corpus/manifests/<k>.tsv              state k's manifest, unchanged
  OUT/corpus/oracles/<k>.json               state k's oracle, unchanged
  OUT/corpus/{apply,verify}.py              the in-Sandbox steps (sandbox/)
  OUT/context/corpus.tar                    OUT/corpus as one archive, owned by root
  OUT/context/Dockerfile                    FROM the fs-bench image, ADD corpus.tar
  OUT/state1/                               state 1 materialized for project.init
  OUT/states.json                           index, ordinal, sha, tree per state

Every stride starts at state 1, so one prepared folder and one image serve
all three.
"""
import json
import os
import shutil
import subprocess
import sys

if len(sys.argv) not in (3, 4):
    sys.exit("usage: prepare.py CORPUS OUT [COUNT]")
corpus, out = sys.argv[1], sys.argv[2]
BASE = "sha256:66aeb6bbf7fc825686a0e6d8c8486d90c99d03ce81f854008f179a23bdf4097e"
# BuildKit cannot take an image id in FROM: the local tag, checked against BASE
# by run.sh image before building.
BASE_TAG = "fs-bench-computer:gawk-20261020"
here = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(out):
    sys.exit(f"prepare.py: {out} exists")
checkpoints = json.load(open(os.path.join(corpus, "checkpoint-manifest.json")))["checkpoints"]
if len(sys.argv) == 4:
    checkpoints = checkpoints[: int(sys.argv[3])]
ctx = os.path.join(out, "corpus")
for sub in ("blobs", "manifests", "oracles"):
    os.makedirs(os.path.join(ctx, sub))


def manifest(path):
    rows = []
    for line in open(path, "rb"):
        mode, blob, size, hexpath = line.rstrip(b"\n").decode().split("\t")
        rows.append((mode, blob, int(size), bytes.fromhex(hexpath)))
    return rows


where = {}  # blob id -> first input folder holding it
states = []
for k, cp in enumerate(checkpoints, 1):
    folder = os.path.join(corpus, "inputs", cp["sha"])
    for blob in os.listdir(os.path.join(folder, "blobs")):
        where.setdefault(blob, os.path.join(folder, "blobs", blob))
    shutil.copyfile(os.path.join(folder, "manifest.tsv"), os.path.join(ctx, "manifests", f"{k}.tsv"))
    shutil.copyfile(os.path.join(corpus, "oracles", cp["sha"] + ".json"), os.path.join(ctx, "oracles", f"{k}.json"))
    for _, blob, _, _ in manifest(os.path.join(folder, "manifest.tsv")):
        if blob not in where:
            sys.exit(f"prepare.py: blob {blob} of state {k} is in no earlier input")
        dest = os.path.join(ctx, "blobs", blob)
        if not os.path.exists(dest):
            shutil.copyfile(where[blob], dest)
    states.append({key: cp[key] for key in ("index", "ordinal", "sha", "tree", "files", "logical_bytes")} | {"index": k})

for name in ("apply.py", "verify.py"):
    shutil.copyfile(os.path.join(here, "sandbox", name), os.path.join(ctx, name))
# One archive, not 75,000 files: the build context then transfers in seconds.
# Owned by root, so the Sandbox identity cannot change the corpus; ADD unpacks it.
os.makedirs(os.path.join(out, "context"))
subprocess.run(["tar", "--no-mac-metadata", "--no-xattrs", "--uid", "0", "--gid", "0", "--uname", "root", "--gname", "root",
                "-C", out, "-cf", os.path.join(out, "context", "corpus.tar"), "corpus"], check=True)
with open(os.path.join(out, "context", "Dockerfile"), "w") as f:
    f.write(f"FROM {BASE_TAG}\nADD corpus.tar /\n")

# State 1 for project.init, with the manifest's modes; directories 0755.
root = os.path.join(out, "state1")
os.makedirs(root)
for mode, blob, size, path in manifest(os.path.join(ctx, "manifests", "1.tsv")):
    dest = os.path.join(root.encode(), path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    data = open(os.path.join(ctx, "blobs", blob), "rb").read()
    if len(data) != size:
        sys.exit(f"prepare.py: blob {blob} is {len(data)} bytes, manifest says {size}")
    if mode == "120000":
        os.symlink(data, dest)
    else:
        with open(dest, "wb") as f:
            f.write(data)
        os.chmod(dest, 0o755 if mode == "100755" else 0o644)
for dirpath, dirnames, _ in os.walk(root):
    for d in dirnames:
        os.chmod(os.path.join(dirpath, d), 0o755)
os.chmod(root, 0o755)

json.dump({"corpus": corpus, "base_image": BASE, "base_tag": BASE_TAG, "states": states}, open(os.path.join(out, "states.json"), "w"), indent=1)
total = sum(os.path.getsize(os.path.join(ctx, "blobs", b)) for b in os.listdir(os.path.join(ctx, "blobs")))
print(json.dumps({"states": len(states), "blobs": len(os.listdir(os.path.join(ctx, "blobs"))), "blob_bytes": total}))
