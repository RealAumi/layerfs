#!/usr/bin/env bash
# smallfile, one step per command. Each client step runs one SDK client
# (common/client.sh) under the 115 s limit and logs its step, times, exit and
# the 1-minute load to RUN/commands.log (common/lib.sh).
#
#   run.sh image                    build bench-smallfile:<date>; benchmark-results/smallfile/image.txt
#   run.sh pt-image                 build <image tag>-pt (common/passthrough.sh); .../pt-image.txt
#   run.sh setup RUN FILES MODE [ARMS]
#                                   volumes, identity, RUN/params.env (FILES per thread; ARMS, default
#                                   "layerfs sandbox-disk passthrough-fuse"), then start
#   run.sh start RUN MODE           MODE measured takes the measurement lock (exit 75 while another run
#                                   holds it: wait, then start again), smoke does not; Init, create,
#                                   fork, mount; then the passthrough-fuse sibling when it is an arm
#   run.sh next RUN                 the next step of the plan below (repeat until DONE)
#   run.sh teardown RUN             remove the sibling, unmount, close, remove the volumes, release the lock
#   run.sh report RUN [OUT]         results.csv, commit.csv and summary.json (report.py)
#
# RUN is a new folder benchmark-results/smallfile/<UTC yyyymmddTHHMMSSZ>
# (smoke runs: smoke-<id>). The plan runs each smallfile operation in each
# arm in the order layerfs, sandbox-disk, passthrough-fuse, over the same
# top folder per arm; one sandbox.commit follows the layerfs create, in its
# own client. A run without ARMS in params.env (v1.0.0) has the first two.
set -euo pipefail
suite=smallfile
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=../common/lib.sh
. "$here/../common/lib.sh"
# shellcheck source=../common/passthrough.sh
. "$here/../common/passthrough.sh"
imagefile=$bench_repo/benchmark-results/smallfile/image.txt
ptimagefile=$bench_repo/benchmark-results/smallfile/pt-image.txt
pt_top=/tmp/pt/sf
step=${1:-}
shift || true

# arms RUN: the run's arms (params.env), in plan order.
arms() {
  local arms="layerfs sandbox-disk"
  # shellcheck source=/dev/null
  . "$1/params.env"
  echo "$arms"
}

# pt_op RUN NAME OP THREADS FILES FILE_SIZE_KB: one smallfile operation in
# the passthrough-fuse arm through bench_pt_exec, with client/op.mjs's
# command, in-container timing and read-back (ops/<op>-passthrough-fuse.txt,
# one results.jsonl row; exec_ms is the docker exec's host-side time). Logs
# the step to commands.log as bench_client does.
pt_op() {
  local run=$1 name=$2 op=$3 threads=$4 files=$5 size=$6 out argv start l0 t0 t1 rc status=0 bstatus=0
  out=/tmp/sf-out/passthrough-fuse/$op
  argv="--top $pt_top --operation $op --threads $threads --files $files --file-size $size --stonewall N --finish Y --output-json $out/result.json"
  start=$(date -u +%FT%TZ) l0=$(bench_load)
  t0=$(perl -MTime::HiRes=time -e 'printf "%.3f", time * 1000')
  bench_pt_exec "$run" "mkdir -p $out || exit 90
l=\$(cut -d' ' -f1 /proc/loadavg); s=\$(date +%s%N); TMPDIR=$out python3 /opt/smallfile/smallfile_cli.py $argv >$out/smallfile.out 2>&1; rc=\$?; e=\$(date +%s%N)
echo \"rc=\$rc ns=\$((e - s)) loadavg=\$l\"" >"$run/$name.out" 2>"$run/$name.err" || status=$?
  t1=$(perl -MTime::HiRes=time -e 'printf "%.3f", time * 1000')
  rc=$(sed -n 's/^rc=\([0-9]*\) .*/\1/p' "$run/$name.out")
  mkdir -p "$run/ops"
  bench_pt_exec "$run" "cd $out || exit 90
tail -c 200000 smallfile.out
echo '=== result.json'; cat result.json 2>&1
$([[ "$rc" == 0 ]] && echo true || echo 'for f in invoke_logs-*.log; do echo "=== $f tail"; tail -n 30 "$f"; done')" \
    >"$run/ops/$op-passthrough-fuse.txt" 2>"$run/ops/$op-passthrough-fuse.stderr" || bstatus=$?
  if [[ -s "$run/ops/$op-passthrough-fuse.stderr" ]]; then
    { echo "=== stderr"; cat "$run/ops/$op-passthrough-fuse.stderr"; } >>"$run/ops/$op-passthrough-fuse.txt"
  fi
  rm -f "$run/ops/$op-passthrough-fuse.stderr"
  python3 - "$run/$name" "$op" "$threads" "$files" "$size" "$argv" "$t0" "$t1" "$status" "$bstatus" <<'EOF' >>"$run/results.jsonl"
import json, re, sys
from pathlib import Path
step, op, threads, files, size, argv, t0, t1, status, bstatus = sys.argv[1:]
stdout, stderr = Path(f"{step}.out").read_text(), Path(f"{step}.err").read_text()
m = re.search(r"rc=(\d+) ns=(\d+) loadavg=([\d.]+)", stdout)
print(json.dumps({
    "case": f"{op}-passthrough-fuse", "op": op, "arm": "passthrough-fuse", "threads": int(threads),
    "files_per_thread": int(files), "file_size_kb": int(size), "argv": argv,
    "rc": int(m[1]) if m else None, "tool_ns": int(m[2]) if m else None, "sandbox_loadavg": float(m[3]) if m else None,
    "exec_ms": round(float(t1) - float(t0), 3), "exec_exit": int(status), "exec_stdout": stdout[:2000],
    "exec_stderr": stderr[:2000], "truncated": False, "readback_exit": int(bstatus),
}, separators=(",", ":")))
EOF
  printf '%s\t%s\t%s\texit=%s\tload=%s\n' "$name" "$start" "$(date -u +%FT%TZ)" "$status" "$l0" >>"$run/commands.log"
  cat "$run/$name.out"
  [[ $status -eq 0 ]] || { echo "$name: exit $status (see $run/$name.err)" >&2; tail -n 8 "$run/$name.err" >&2; exit "$status"; }
}

case "$step" in
image)
  mkdir -p "$(dirname "$imagefile")"
  bench_image "$here/sandbox" "bench-smallfile:$(date -u +%Y%m%d)" "$imagefile"
  docker run --rm --entrypoint cat "$(sed -n 's/^image=//p' "$imagefile")" /opt/smallfile-identity.txt >>"$imagefile"
  ;;
pt-image)
  tag=$(sed -n 's/^tag=//p' "$imagefile")
  [[ "$(docker image inspect "$tag" --format '{{.Id}}')" == "$(sed -n 's/^image=//p' "$imagefile")" ]] \
    || { echo "run.sh: $tag is not the digest in $imagefile; run.sh image first" >&2; exit 2; }
  bench_pt_image "$tag" "$ptimagefile"
  ;;
setup)
  run=$1 files=$2 mode=$3 arms=${4:-layerfs sandbox-disk passthrough-fuse}
  [[ "$mode" == measured || "$mode" == smoke ]] || { echo "run.sh: MODE is measured or smoke" >&2; exit 2; }
  [[ "$files" =~ ^[1-9][0-9]*$ ]] || { echo "run.sh: FILES is a positive integer" >&2; exit 2; }
  [[ "$arms" =~ ^layerfs\ sandbox-disk(\ passthrough-fuse)?$ ]] || { echo "run.sh: ARMS is \"layerfs sandbox-disk\" [passthrough-fuse]" >&2; exit 2; }
  bench_setup "$run" "$imagefile" smallfile "mode=$mode files_per_thread=$files arms=${arms// /,}"
  grep -E '^(smallfile_commit|smallfile_version|python|pyyaml)=' "$imagefile" | sed 's/^/image_/' >>"$run/identity.txt"
  printf 'threads=4\nfiles=%s\nfile_size_kb=4\narms="%s"\n' "$files" "$arms" >"$run/params.env"
  mkdir "$run/seed"
  echo "LayerFS smallfile benchmark Workspace; smallfile works under sf/." >"$run/seed/README"
  exec "$0" start "$run" "$mode"
  ;;
start)
  run=$1 mode=$2
  [[ "$mode" == smoke ]] || bench_lock "$run"
  bench_client "$run" setup setup.mjs "$run/seed"
  if [[ " $(arms "$run") " == *" passthrough-fuse "* ]]; then
    bench_pt_start "$run" "$ptimagefile"
    bench_pt_exec "$run" "cat /opt/smallfile-identity.txt && echo uname=\$(uname -srm) && echo id=\$(id -u):\$(id -g) \
      && echo nproc=\$(nproc) && mkdir $pt_top && stat -f -c 'fs %n type=%T bsize=%s' $pt_top" >"$run/pt-identity.txt" 2>&1
    cat "$run/pt-identity.txt"
  fi
  ;;
next)
  run=$1
  read -ra arm_list <<<"$(arms "$run")"
  plan=()
  for op in create read append stat chmod rename delete-renamed mkdir rmdir; do
    for arm in "${arm_list[@]}"; do
      plan+=("$op:$arm")
      [[ "$op:$arm" == create:layerfs ]] && plan+=(commit)
    done
  done
  for s in "${plan[@]}"; do
    if [[ "$s" == commit ]]; then
      grep -qs '"step":"commit"' "$run/ledger.jsonl" && continue
      bench_client "$run" commit commit.mjs
    else
      grep -qs "\"case\":\"${s/:/-}\"" "$run/results.jsonl" && continue
      # shellcheck source=/dev/null
      . "$run/params.env"
      if [[ "${s#*:}" == passthrough-fuse ]]; then
        pt_op "$run" "$(bench_next "$run" "op-${s/:/-}")" "${s%%:*}" "$threads" "$files" "$file_size_kb"
      else
        bench_client "$run" "$(bench_next "$run" "op-${s/:/-}")" op.mjs "${s%%:*}" "${s#*:}" "$threads" "$files" "$file_size_kb"
      fi
    fi
    exit 0
  done
  echo DONE
  ;;
teardown)
  run=$1
  if docker inspect "$(bench_pt_name "$run")" >/dev/null 2>&1; then bench_pt_stop "$run"; fi
  bench_client "$run" teardown teardown.mjs
  bench_cleanup "$run"
  if grep -q '^lock=taken' "$run/identity.txt"; then bench_unlock "$run"; fi
  ;;
report)
  python3 "$here/report.py" "$@"
  ;;
*)
  sed -n '2,22p' "$0" >&2
  exit 2
  ;;
esac
