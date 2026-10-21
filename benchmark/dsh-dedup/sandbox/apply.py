#!/usr/bin/env python3
"""Moves the Workspace (the current directory) from state FROM to state TO.

    python3 /corpus/apply.py FROM TO

A regular file whose path stays a regular file is overwritten in place: the
same inode, opened O_WRONLY|O_TRUNC and rewritten. A removed path, or one
whose type changes, is unlinked; new paths are created. Directories left
empty are removed, since the corpus (Git trees) has none. Prints one JSON
line of counts.
"""
import json
import os
import shutil
import sys

CORPUS = "/corpus"


def manifest(k):
    rows = {}
    for line in open(f"{CORPUS}/manifests/{k}.tsv", "rb"):
        mode, blob, size, hexpath = line.rstrip(b"\n").decode().split("\t")
        rows[bytes.fromhex(hexpath)] = (mode, blob)
    return rows


def blob(blob_id):
    with open(f"{CORPUS}/blobs/{blob_id}", "rb") as f:
        return f.read()


old, new = manifest(int(sys.argv[1])), manifest(int(sys.argv[2]))
kind = lambda mode: "link" if mode == "120000" else "file"
counts = {"removed": 0, "created": 0, "overwritten": 0, "overwritten_bytes": 0, "created_bytes": 0, "relinked": 0, "chmod": 0, "dirs_removed": 0}

for path, (mode, _) in old.items():
    if path not in new or kind(new[path][0]) != kind(mode):
        os.unlink(path)
        counts["removed"] += 1

for path, (mode, blob_id) in sorted(new.items()):
    before = old.get(path)
    if before == (mode, blob_id):
        continue
    parent = os.path.dirname(path)
    if parent:
        # A path that was a file and is now a directory was unlinked above.
        os.makedirs(parent, mode=0o755, exist_ok=True)
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)  # a directory replaced by a file or link
    data = blob(blob_id)
    if mode == "120000":
        if before is not None and kind(before[0]) == "link":
            os.unlink(path)
            counts["relinked"] += 1
        else:
            counts["created"] += 1
        os.symlink(data, path)
        continue
    perm = 0o755 if mode == "100755" else 0o644
    if before is not None and kind(before[0]) == "file":
        if before[1] != blob_id:
            fd = os.open(path, os.O_WRONLY | os.O_TRUNC)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            counts["overwritten"] += 1
            counts["overwritten_bytes"] += len(data)
        if before[0] != mode:
            os.chmod(path, perm)
            counts["chmod"] += 1
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, perm)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(path, perm)
        counts["created"] += 1
        counts["created_bytes"] += len(data)

for dirpath, dirnames, filenames in os.walk(b".", topdown=False):
    if dirpath != b"." and not os.listdir(dirpath):
        os.rmdir(dirpath)
        counts["dirs_removed"] += 1

print(json.dumps(counts))
