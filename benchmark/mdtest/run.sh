#!/usr/bin/env bash
# mdtest, one step per command. Each client step runs one SDK client
# (common/client.sh) under the 115 s limit and logs its step, times, exit and
# the 1-minute load to RUN/commands.log (common/lib.sh).
#
#   run.sh image                    build bench-mdtest:<date>; benchmark-results/mdtest/image.txt
#   run.sh pt-image                 build its passthrough FUSE image; benchmark-results/mdtest/pt-image.txt
#   run.sh setup RUN CASES MODE [ARMS]
#                                   volumes, identity, CASES copied to RUN/cases.tsv, then start.
#                                   ARMS is two (layerfs, sandbox-disk; the default, as the v1.0.0
#                                   run) or three (adds passthrough-fuse; written to RUN/arms.txt)
#   run.sh start RUN MODE           MODE measured takes the measurement lock (exit 75 while another run
#                                   holds it: wait, then start again), smoke does not; Init, create,
#                                   fork, mount; with three arms, then the passthrough sibling
#   run.sh next RUN                 the next case and arm from RUN/cases.tsv (repeat until DONE)
#   run.sh commit RUN               the commit pass, layerfs only: mdtest -C, sandbox.commit, mdtest -r
#   run.sh teardown RUN             sibling removed, unmount, close, volumes removed, lock released
#   run.sh report RUN [OUT]         results.csv, commit.csv, summary.json; three arms: ratios.csv
#
# RUN is a new folder benchmark-results/mdtest/<UTC yyyymmddTHHMMSSZ> (smoke
# runs: smoke-<id>). CASES is cases.tsv (measured) or cases-smoke.tsv. Each
# row is one mdtest case run in the layerfs arm, then sandbox-disk, then
# (three arms) passthrough-fuse; the row named `commit` gives the commit
# pass's procs, items and mode flag. The passthrough-fuse arm runs the same
# mpirun command in /tmp/pt/md/<case> of a sibling container through
# docker exec (common/passthrough.sh), not through the SDK.
set -euo pipefail
suite=mdtest
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=../common/lib.sh
. "$here/../common/lib.sh"
# shellcheck source=../common/passthrough.sh
. "$here/../common/passthrough.sh"
imagefile=$bench_repo/benchmark-results/mdtest/image.txt
ptimagefile=$bench_repo/benchmark-results/mdtest/pt-image.txt
MPIRUN="mpirun --oversubscribe --bind-to none"
step=${1:-}
shift || true

# row RUN CASE -> "PROCS ITEMS ARGS..." of that cases.tsv row.
row() { awk -F'\t' -v c="$2" '$1 == c { print $2, $3, $4 }' "$1/cases.tsv"; }

# arms RUN -> the run's arms on one line (a run without arms.txt has two).
arms() { if [[ -f "$1/arms.txt" ]]; then tr '\n' ' ' <"$1/arms.txt"; else echo "layerfs sandbox-disk"; fi; }

# pt_case RUN CASE PROCS ITEMS [MDTEST_ARG...]: one case in the passthrough-fuse
# arm with the same exec script and receipts as client/case.mjs: mdtest's
# output in cases/<case>-passthrough-fuse.txt, one results.jsonl row (exec_ms
# is the host-side docker exec time), one commands.log line.
# The case's own ceiling is enforced in the sibling: GNU timeout sends
# mpirun TERM after 110 s (it then stops its ranks; KILL 3 s later) and the
# case records rc=124 (137 after KILL), a hang. That is inside
# bench_pt_exec's limits (113 s in the sibling, 115 s on the host), so the
# rc line and the log still print.
pt_case() {
  local run=$1 name=$2 procs=$3 items=$4 step start l0 t0 t1 status=0
  shift 4
  local dir=/tmp/pt/md/$name log=/tmp/mdlog/$name-passthrough-fuse.txt
  local command="$MPIRUN -np $procs mdtest -P -i 1 -n $items${*:+ $*} -d $dir"
  step=$(bench_next "$run" "case-$name-passthrough-fuse")
  start=$(date -u +%FT%TZ) l0=$(bench_load) t0=$(perl -MTime::HiRes=time -e 'printf "%.1f", time * 1000')
  bench_pt_exec "$run" "mkdir -p /tmp/mdlog $dir || exit 90
l=\$(cut -d' ' -f1 /proc/loadavg)
s=\$(date +%s%N); timeout -k 3 110 $command >$log 2>&1; rc=\$?; e=\$(date +%s%N)
echo \"rc=\$rc ns=\$((e - s)) vmload=\$l\"
cat $log" >"$run/$step.out" 2>"$run/$step.err" || status=$?
  t1=$(perl -MTime::HiRes=time -e 'printf "%.1f", time * 1000')
  printf '%s\t%s\t%s\texit=%s\tload=%s\n' "$step" "$start" "$(date -u +%FT%TZ)" "$status" "$l0" >>"$run/commands.log"
  python3 - "$run" "$step" "$name" "$procs" "$items" "$*" "$command" "$status" "$t0" "$t1" <<'PY'
import json, os, re, sys
run, step, name, procs, items, args, command, status, t0, t1 = sys.argv[1:]
out, err = (open(f"{run}/{step}.{x}").read() for x in ("out", "err"))
os.makedirs(f"{run}/cases", exist_ok=True)
open(f"{run}/cases/{name}-passthrough-fuse.txt", "w").write(out + (f"=== stderr\n{err}" if err else ""))
m = re.search(r"rc=(\d+) ns=(\d+) vmload=([\d.]+)", out)
row = {"case": name, "arm": "passthrough-fuse", "procs": int(procs), "items_per_proc": int(items), "args": args,
       "command": command, "rc": int(m[1]) if m else None, "tool_ns": int(m[2]) if m else None,
       "vm_load": float(m[3]) if m else None, "exec_ms": round(float(t1) - float(t0), 1), "exec_exit": int(status),
       "truncated": False, "exec_stderr": err[:2000]}
open(f"{run}/results.jsonl", "a").write(json.dumps(row) + "\n")
PY
  tail -n 5 "$run/$step.out"
  [[ $status -eq 0 ]] || { echo "$step: exit $status (see $run/$step.err)" >&2; tail -n 8 "$run/$step.err" >&2; exit "$status"; }
}

case "$step" in
image)
  mkdir -p "$(dirname "$imagefile")"
  bench_image "$here/sandbox" "bench-mdtest:$(date -u +%Y%m%d)" "$imagefile"
  docker run --rm --entrypoint cat "$(sed -n 's/^image=//p' "$imagefile")" /opt/mdtest-identity.txt >>"$imagefile"
  ;;
pt-image)
  bench_pt_image "$(sed -n 's/^tag=//p' "$imagefile")" "$ptimagefile"
  ;;
setup)
  run=$1 cases=$2 mode=$3 narms=${4:-two}
  [[ "$mode" == measured || "$mode" == smoke ]] || { echo "run.sh: MODE is measured or smoke" >&2; exit 2; }
  [[ "$narms" == two || "$narms" == three ]] || { echo "run.sh: ARMS is two or three" >&2; exit 2; }
  bench_setup "$run" "$imagefile" mdtest "mode=$mode cases=$(basename "$cases")${4:+ arms=$narms}"
  grep -E '^(ior_commit|mdtest_sha256|mdtest_version|mpi|gcc)=' "$imagefile" | sed 's/^/image_/' >>"$run/identity.txt"
  cp "$cases" "$run/cases.tsv"
  [[ "$narms" == two ]] || printf 'layerfs\nsandbox-disk\npassthrough-fuse\n' >"$run/arms.txt"
  mkdir "$run/seed"
  echo "LayerFS mdtest benchmark Workspace; mdtest works under md/." >"$run/seed/README"
  exec "$0" start "$run" "$mode"
  ;;
start)
  run=$1 mode=$2
  [[ "$mode" == smoke ]] || bench_lock "$run"
  bench_client "$run" setup setup.mjs "$run/seed"
  if [[ " $(arms "$run") " == *" passthrough-fuse "* ]]; then
    bench_pt_start "$run" "$ptimagefile"
    # The sibling's identity, as setup.mjs probes the Sandbox: tools, kernel, uid, the arm's filesystem.
    bench_pt_exec "$run" "cat /opt/mdtest-identity.txt && echo mpirun=\$(mpirun --version 2>&1 | head -n 1) \
      && echo uname=\$(uname -srm) nproc=\$(nproc) && echo id=\$(id -u):\$(id -g) && mkdir /tmp/pt/md \
      && stat -f -c 'fs %n type=%T bsize=%s' /tmp/pt/md && awk '\$2 == \"/tmp/pt\"' /proc/self/mounts" \
      >"$run/pt-identity.txt" 2>&1
    cat "$run/pt-identity.txt"
  fi
  ;;
next)
  run=$1
  # The first (row, arm) without a results.jsonl line: CASE ARM PROCS ITEMS ARGS.
  pick=$(python3 - "$run" "$(arms "$run")" <<'PY'
import json, os, sys
run, arms = sys.argv[1], sys.argv[2].split()
done = set()
if os.path.exists(f"{run}/results.jsonl"):
    done = {(r["case"], r["arm"]) for r in map(json.loads, filter(str.strip, open(f"{run}/results.jsonl")))}
for line in open(f"{run}/cases.tsv"):
    if not line.strip() or line.startswith("#"):
        continue
    case, procs, items, args = (line.rstrip("\n").split("\t") + [""])[:4]
    if case == "commit":
        continue
    for arm in arms:
        if (case, arm) not in done:
            print(case, arm, procs, items, args)
            sys.exit(0)
PY
)
  if [[ -z "$pick" ]]; then echo DONE; exit 0; fi
  read -r -a argv <<<"$pick"
  if [[ "${argv[1]}" == passthrough-fuse ]]; then
    pt_case "$run" "${argv[0]}" "${argv[@]:2}"
  else
    bench_client "$run" "$(bench_next "$run" "case-${argv[0]}-${argv[1]}")" case.mjs "${argv[@]}"
  fi
  ;;
commit)
  run=$1
  read -r procs items flags <<<"$(row "$run" commit)"
  [[ -n "$items" ]] || { echo "run.sh: $run/cases.tsv has no commit row" >&2; exit 2; }
  bench_client "$run" commit-create case.mjs commit-create layerfs "$procs" "$items" "$flags" -C
  bench_client "$run" commit commit.mjs
  bench_client "$run" commit-remove case.mjs commit-remove layerfs "$procs" "$items" "$flags" -r
  ;;
teardown)
  run=$1
  # The sibling goes first and on every path, also after a failed start or case.
  if docker inspect "$(bench_pt_name "$run")" >/dev/null 2>&1; then bench_pt_stop "$run"; fi
  bench_client "$run" teardown teardown.mjs
  bench_cleanup "$run"
  if grep -q '^lock=taken' "$run/identity.txt"; then bench_unlock "$run"; fi
  ;;
report)
  python3 "$here/report.py" "$@"
  ;;
*)
  sed -n '2,26p' "$0" >&2
  exit 2
  ;;
esac
