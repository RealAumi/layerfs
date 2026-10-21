#!/bin/bash
# Runs pjdfstest test files of one directory as the calling user (the
# Sandbox's uid 501), in ROOT/pjd/DIR, one `sh FILE.t` per file under its
# own timeout, and prints each file's TAP between markers:
#
#   ### group dir=DIR cwd=... fs=... uid=...
#   ### begin DIR/FILE.t
#   <TAP from the test>
#   # stderr: <each stderr line>
#   ### end DIR/FILE.t exit=E ms=M quick_exit=0|1 residue=N
#   ### deferred DIR/FILE.t      (not started; the next group runs it)
#
# quick_exit=1 marks a file that printed only "1..1 / ok 1" through
# misc.sh's quick_exit (the platform or filesystem does not support it).
#
# A file starts only while fewer than START_BUDGET_S seconds have passed
# since the group began. A file that calls `sleep` (the ctime checks; chown/00.t
# sleeps about 76 s) starts only as the group's first file, so one group stays
# within FILE_TIMEOUT_S plus the quick files' few seconds; the caller runs the
# deferred files in a later group.
#
#   run-group.sh ROOT DIR FILE_TIMEOUT_S START_BUDGET_S [FILE.t ...]   (all of DIR when no FILE)
set -u
root=$1 dir=$2 limit=$3 budget=$4
shift 4
tests=/opt/pjdfstest/tests
work=$root/pjd/$dir
mkdir -p "$work" && cd "$work" || { echo "### error cannot enter $work"; exit 3; }
files=("$@")
[[ ${#files[@]} -gt 0 ]] || mapfile -t files < <(cd "$tests/$dir" && ls -- *.t)
echo "### group dir=$dir cwd=$work fs=$(df -PT . | awk 'END {print $2}') uid=$(id -u):$(id -g)"
err=$(mktemp /tmp/pjd-stderr.XXXXXX)
start=$SECONDS
for f in "${files[@]}"; do
  if (( SECONDS - start >= budget )) || { [[ $f != "${files[0]}" ]] && grep -q 'sleep' "$tests/$dir/$f"; }; then
    echo "### deferred $dir/$f"
    continue
  fi
  echo "### begin $dir/$f"
  t0=$(date +%s%N)
  out=$(timeout -k 5 "$limit" sh "$tests/$dir/$f" 2>"$err")
  status=$?
  ms=$(( ($(date +%s%N) - t0) / 1000000 ))
  printf '%s\n' "$out"
  sed 's/^/# stderr: /' "$err"
  quick=0
  [[ "$out" == $'1..1\nok 1' ]] && grep -qE 'quick_exit|^require ' "$tests/$dir/$f" && quick=1
  echo "### end $dir/$f exit=$status ms=$ms quick_exit=$quick residue=$(find . -mindepth 1 -maxdepth 1 | wc -l)"
done
rm -f "$err"
