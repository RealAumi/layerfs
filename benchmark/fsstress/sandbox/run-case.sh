#!/usr/bin/env bash
# One fsstress case in one arm, inside the Sandbox (one sandbox.exec):
#
#   run-case.sh NAME DIR SEED PROCS OPS
#
# Runs `fsstress -d DIR -p PROCS -n OPS -s SEED -v -V -o /tmp/fsslog/NAME.log`
# in a new DIR. -v logs every operation with its result, -V leaves inode
# numbers out of the log so two arms' logs compare line by line, and -o
# gives each process its own file, NAME.log.<proc>. wall_ms covers fsstress
# alone (date before and after). The logs are then gzipped (outside the
# clock) for read-back in pieces, and one JSON line describes the result.
set -uo pipefail
[[ $# -eq 5 ]] || { echo "usage: $0 NAME DIR SEED PROCS OPS" >&2; exit 2; }
name=$1 dir=$2 seed=$3 procs=$4 ops=$5
logs=/tmp/fsslog
[[ ! -e "$dir" ]] || { echo "run-case.sh: $dir exists" >&2; exit 2; }
mkdir -p "$logs"
args=(-d "$dir" -p "$procs" -n "$ops" -s "$seed" -v -V -o "$logs/$name.log")
t0=$(date +%s%N)
fsstress "${args[@]}" >"$logs/$name.stdout" 2>"$logs/$name.stderr"
status=$?
t1=$(date +%s%N)
files=()
for f in "$logs/$name.log" "$logs/$name.log".*; do
  [[ -f "$f" && "$f" != *.gz ]] || continue
  gzip -9 -k -f "$f"
  files+=("$f")
done
python3 - "$status" "$(( (t1 - t0) / 1000 ))" "$logs/$name" "${files[@]}" -- "${args[@]}" <<'PY'
import hashlib, json, os, sys
argv = sys.argv[1:]
cut = argv.index("--")
status, wall_us, base, files, args = int(argv[0]), int(argv[1]), argv[2], argv[3:cut], argv[cut + 1:]
def tail(path, n=2000):
    data = open(path, "rb").read()
    return {"bytes": len(data), "tail": data[-n:].decode("utf-8", "replace")}
logs = []
for f in files:
    gz = open(f + ".gz", "rb").read()
    logs.append({"file": os.path.basename(f), "bytes": os.path.getsize(f),
                 "lines": sum(1 for _ in open(f, "rb")),
                 "gz": os.path.basename(f) + ".gz", "gz_bytes": len(gz),
                 "gz_sha256": hashlib.sha256(gz).hexdigest()})
print(json.dumps({"exit": status, "wall_ms": wall_us / 1000, "argv": ["fsstress"] + args,
                  "stdout": tail(base + ".stdout"), "stderr": tail(base + ".stderr"), "logs": logs}))
PY
