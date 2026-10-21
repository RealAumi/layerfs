#!/usr/bin/env python3
"""Checks the Workspace (the current directory) against state K's oracle.

    python3 /corpus/verify.py K

Every path's type, Git mode (executable bit), size and SHA-256 (of the bytes,
or of a symlink's target) must match, with no path missing or extra. Prints
one JSON line; exits 1 on any mismatch.
"""
import hashlib
import json
import os
import stat
import sys

oracle = {bytes.fromhex(k): tuple(v) for k, v in json.load(open(f"/corpus/oracles/{sys.argv[1]}.json")).items()}
seen = {}
for dirpath, dirnames, filenames in os.walk(b"."):
    for name in dirnames + filenames:
        full = os.path.join(dirpath, name)
        rel = full[2:]
        st = os.lstat(full)
        if stat.S_ISLNK(st.st_mode):
            target = os.readlink(full)
            seen[rel] = ("120000", len(target), hashlib.sha256(target).hexdigest())
        elif stat.S_ISDIR(st.st_mode):
            seen[rel] = ("40755", 0, "-")
        else:
            with open(full, "rb") as f:
                data = f.read()
            mode = "100755" if st.st_mode & 0o100 else "100644"
            seen[rel] = (mode, len(data), hashlib.sha256(data).hexdigest())

bad = [p.decode("utf-8", "replace") for p in sorted(set(oracle) | set(seen)) if oracle.get(p) != seen.get(p)]
print(json.dumps({"state": int(sys.argv[1]), "entries": len(seen), "expected": len(oracle), "mismatches": len(bad), "first": bad[:5]}))
sys.exit(1 if bad else 0)
