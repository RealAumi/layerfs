#!/usr/bin/env python3
"""Tree manifest for the capture proof, inside the Sandbox.

  manifest.py build ROOT OUT    write OUT (JSON lines, sorted by path); print a summary
  manifest.py compare A B       compare two manifests; print equality and differences

One line per entry under ROOT, ROOT itself included as ".", never
following symlinks: path, type, mode (permission bits, octal), size and
sha256 for a regular file, target for a symlink, nlink for every
non-directory, and link_group (the smallest path sharing the inode) for a
non-directory with more than one link inside ROOT. A file that cannot be
read records its errno in place of the sha256.
"""
import hashlib, json, os, stat, sys

KINDS = [(stat.S_ISREG, "file"), (stat.S_ISDIR, "dir"), (stat.S_ISLNK, "symlink"), (stat.S_ISCHR, "char"),
         (stat.S_ISBLK, "block"), (stat.S_ISFIFO, "fifo"), (stat.S_ISSOCK, "socket")]


def kind(mode):
    return next(name for test, name in KINDS if test(mode))


def sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError as e:
        return f"unreadable:{e.errno}"
    return h.hexdigest()


def build(root, out):
    rows, inodes, errors = {}, {}, []
    def visit(rel, full):
        st = os.lstat(full)
        row = {"path": rel, "type": kind(st.st_mode), "mode": oct(stat.S_IMODE(st.st_mode))}
        if row["type"] == "file":
            row["size"], row["sha256"] = st.st_size, sha256(full)
        elif row["type"] == "symlink":
            row["size"], row["target"] = st.st_size, os.readlink(full)
        if row["type"] != "dir":
            row["nlink"] = st.st_nlink
            if st.st_nlink > 1:
                inodes.setdefault((st.st_dev, st.st_ino), []).append(rel)
        rows[rel] = row
        if row["type"] == "dir":
            try:
                names = sorted(os.listdir(full))
            except OSError as e:
                errors.append({"path": rel, "errno": e.errno})
                return
            for name in names:
                visit(name if rel == "." else f"{rel}/{name}", os.path.join(full, name))
    visit(".", root)
    for paths in inodes.values():
        if len(paths) > 1:
            for p in paths:
                rows[p]["link_group"] = min(paths)
    if errors:
        rows["."]["listing_errors"] = errors
    with open(out, "w") as f:
        for rel in sorted(rows):
            f.write(json.dumps(rows[rel], sort_keys=True) + "\n")
    types = {}
    for r in rows.values():
        types[r["type"]] = types.get(r["type"], 0) + 1
    data = open(out, "rb").read()
    print(json.dumps({"root": root, "manifest": out, "entries": len(rows), "types": types,
                      "bytes": sum(r.get("size", 0) for r in rows.values() if r["type"] == "file"),
                      "hardlinked": sum(1 for r in rows.values() if "link_group" in r),
                      "listing_errors": len(errors), "manifest_bytes": len(data),
                      "manifest_sha256": hashlib.sha256(data).hexdigest()}))


def compare(a, b):
    load = lambda p: {r["path"]: r for r in map(json.loads, open(p))}
    left, right = load(a), load(b)
    diffs = []
    for path in sorted(set(left) | set(right)):
        x, y = left.get(path), right.get(path)
        if x is None or y is None:
            diffs.append({"path": path, "only_in": a if y is None else b})
        elif x != y:
            keys = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
            diffs.append({"path": path, "fields": {k: [x.get(k), y.get(k)] for k in keys}})
    print(json.dumps({"a": a, "b": b, "entries_a": len(left), "entries_b": len(right),
                      "equal": not diffs, "differences": len(diffs), "first": diffs[:200]}))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
