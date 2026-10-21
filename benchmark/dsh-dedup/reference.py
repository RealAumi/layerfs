#!/usr/bin/env python3
"""Git storage reference for one stride: the recipe of the corpus's
git-snapshots-157-v1 control, applied to the stride's selected states.

    reference.py CORPUS STRIDE OUT

A fresh bare repository gets one linear Commit per selected state, each with
that checkpoint's exact root tree (git commit-tree), reading objects from
CORPUS/source.git through GIT_ALTERNATE_OBJECT_DIRECTORIES only, so no
alternates file is ever written. Then
`git repack -a -d -f -F --window=10 --depth=50 --threads=2` copies the whole
closure into one pack, loose objects are pruned, and the repository is
checked without the alternate: no alternates file, `git fsck --full`, and
every Commit's tree equal to its checkpoint's. Writes OUT/result.json.
Storage only; the repack time is recorded, not compared.
"""
import json
import os
import subprocess
import sys
import time

corpus, stride, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
if os.path.exists(out):
    sys.exit(f"reference.py: {out} exists")
states = json.load(open(os.path.join(corpus, "checkpoint-manifest.json")))["checkpoints"]
n = len(states)
picked = sorted(set(range(1, n + 1, 10)) | {n}) if stride == 10 else list(range(1, n + 1, stride))
repo = os.path.join(out, "repo.git")
os.makedirs(out)
env = {**os.environ, "GIT_AUTHOR_NAME": "dsh-dedup", "GIT_AUTHOR_EMAIL": "dsh-dedup@invalid",
       "GIT_COMMITTER_NAME": "dsh-dedup", "GIT_COMMITTER_EMAIL": "dsh-dedup@invalid",
       "GIT_AUTHOR_DATE": "1700000000 +0000", "GIT_COMMITTER_DATE": "1700000000 +0000"}
alt = {**env, "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.path.join(corpus, "source.git", "objects")}


def git(*args, environ=env):
    return subprocess.run(["git", "-C", repo, *args], env=environ, check=True, capture_output=True, text=True).stdout.strip()


subprocess.run(["git", "init", "-q", "--bare", repo], check=True)
parent = None
for k in picked:
    tree = states[k - 1]["tree"]
    parent = git("commit-tree", tree, *(["-p", parent] if parent else []), "-m", f"dsh state {k}", environ=alt)
git("update-ref", "refs/heads/main", parent)
command = ["repack", "-a", "-d", "-f", "-F", "--window=10", "--depth=50", "--threads=2"]
start = time.perf_counter_ns()
git(*command, environ=alt)
repack_ns = time.perf_counter_ns() - start
git("prune-packed")

assert not os.path.exists(os.path.join(repo, "objects", "info", "alternates")), "alternates file written"
git("fsck", "--full", "--no-dangling")
trees = git("log", "--format=%T", "--reverse", "main").split("\n")
assert trees == [states[k - 1]["tree"] for k in picked], "a Commit's tree differs from its checkpoint"


def allocated(root):
    total = apparent = files = 0
    for dirpath, _, names in os.walk(root):
        for name in names:
            st = os.lstat(os.path.join(dirpath, name))
            total += st.st_blocks * 512
            apparent += st.st_size
            files += 1
    return total, apparent, files


pack_dir = os.path.join(repo, "objects", "pack")
pack = sum(os.path.getsize(os.path.join(pack_dir, f)) for f in os.listdir(pack_dir) if f.endswith(".pack"))
index = sum(os.path.getsize(os.path.join(pack_dir, f)) for f in os.listdir(pack_dir) if f.endswith(".idx"))
total, apparent, files = allocated(repo)
objects_total, objects_apparent, _ = allocated(os.path.join(repo, "objects"))
result = {
    "stride": stride, "states": len(picked), "selection": picked,
    "logical_bytes": sum(states[k - 1]["logical_bytes"] for k in picked),
    "git_version": subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip(),
    "command": command, "repack_ns": repack_ns,
    "pack_bytes": pack, "index_bytes": index,
    "objects_allocated_bytes": objects_total, "objects_apparent_bytes": objects_apparent,
    "repo_allocated_bytes": total, "repo_apparent_bytes": apparent, "repo_files": files,
    "object_count": int(git("count-objects", "-v").split("in-pack: ")[1].split("\n")[0]),
    "verification": {"fsck": "PASS", "trees_matched": len(trees), "no_alternates": True},
}
json.dump(result, open(os.path.join(out, "result.json"), "w"), indent=1)
print(json.dumps({k: result[k] for k in ("stride", "states", "pack_bytes", "objects_allocated_bytes", "repo_allocated_bytes")}))
