#!/usr/bin/env bash
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
repo=$(cd "$here/../.." && pwd -P)
bench="$here/fs-bench.sh"
compare="$here/compare.py"
legacy_verifier="$here/verify_fs_bench.py"
results="$repo/benchmark-results/fs-bench"
expected_sha256=0e2004339a9269b88c2de451d56575957477bde16b96a10cf1837519e37230ef
computer_commit=de87919a4fd37242e960e13b7b3ba802d1eef0a0
computer_tree=4fb409d7e1356e1098439293d77d2fdc2dbf2190
scenarios='create 1000 files,stat 1000 files,rm 1000 files,mkdir tree (10x10x10),find tree,write 64 MiB,copy 64 MiB,read 64 MiB,pure read 64 MiB,pure copy 64 MiB,overwrite 64 MiB,git init + commit 100 files'

die() { printf 'fs-bench: %s\n' "$*" >&2; exit 2; }

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

check_frozen_runner() {
  [[ -f "$bench" ]] || die "missing canonical runner: $bench"
  bash -n "$bench"
  local actual
  actual=$(sha256_file "$bench")
  [[ "$actual" == "$expected_sha256" ]] ||
    die "canonical runner drifted: expected $expected_sha256, got $actual"
}

self_check_dir=
cleanup_self_check() {
  case "$self_check_dir" in
    */layerfs-fs-bench-check.*) rm -rf -- "$self_check_dir" ;;
  esac
}

self_check() {
  check_frozen_runner
  python3 "$legacy_verifier" --self-test
  python3 "$compare" --self-check
  if (( BASH_VERSINFO[0] < 4 )); then
    printf 'PASS fs-bench package syntax/hash/verifiers (sample requires Bash 4+)\n'
    return
  fi
  self_check_dir=$(mktemp -d "${TMPDIR:-/tmp}/layerfs-fs-bench-check.XXXXXX")
  trap cleanup_self_check EXIT
  mkdir "$self_check_dir/mount"
  MOUNT="$self_check_dir/mount" BASE= REPS=1 WARMUP=0 RANDOMIZE_TARGETS=0 \
    SCENARIOS='pure read 64 MiB' OUTPUT_JSON="$self_check_dir/result.json" \
    bash "$bench" >"$self_check_dir/stdout.txt" 2>"$self_check_dir/stderr.txt"
  python3 - "$self_check_dir/result.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    result = json.load(source)
rows = result["results"]
assert result["config"]["reps"] == 1
assert len(rows) == 1
assert rows[0]["scenario"] == "pure read 64 MiB"
assert rows[0]["target"] == "computerd"
assert rows[0]["samples"] == 1
assert rows[0]["medianNs"] > 0
PY
  cleanup_self_check
  trap - EXIT
  printf 'PASS fs-bench package and frozen-runner smoke test\n'
}

mountinfo_program='p=$1
test -d "$p" || exit 2
p=$(readlink -f "$p") || exit 2
awk -v p="$p" '\''
$5 == p {
  for (i = 1; i <= NF; i++) if ($i == "-") { fs = $(i + 1); break }
  if (fs !~ /^fuse([.]|$)/) exit 3
  print
  found = 1
}
END { if (!found) exit 4 }
'\'' /proc/self/mountinfo'

# One sandbox.exec call through the JS SDK (holder/exec.mjs, run by
# holder/client.sh in the holder's SDK home): $1 is the command, $2 the file
# that receives the outcome JSON. Fails when the call is refused.
sdk_exec() {
  printf '%s' "$1" | "$here/holder/client.sh" "$sdk_home" exec.mjs "$sandbox" "$mount" >"$2"
}

# One field of an outcome JSON, printed as text.
sdk_field() {
  python3 -c 'import json, sys; sys.stdout.write(str(json.load(open(sys.argv[1]))[sys.argv[2]]))' "$1" "$2"
}

if [[ "${1:-}" == "--self-check" ]]; then
  self_check
  exit 0
fi

[[ $# -ge 3 && $# -le 6 ]] ||
  die "usage: $0 computer-upstream|layerfs-core host MOUNT [PAIR_ID]\n       $0 computer-upstream|layerfs-core docker CONTAINER MOUNT [PAIR_ID]\n       $0 layerfs-core sdk SDK_HOME SANDBOX MOUNT [PAIR_ID]"
candidate=$1
mode=$2
shift 2

case "$candidate" in
  computer-upstream|layerfs-core) ;;
  layerfs-reference) die "layerfs-reference was retired by R9c; use layerfs-core" ;;
  *) die "candidate must be computer-upstream or layerfs-core" ;;
esac
case "$mode" in
  host)
    [[ $# -ge 1 && $# -le 2 ]] || die "host mode requires MOUNT [PAIR_ID]"
    mount=$1
    pair_id=${2:-$(date -u +%Y%m%dT%H%M%SZ)-$$}
    container=
    ;;
  docker)
    [[ $# -ge 2 && $# -le 3 ]] || die "docker mode requires CONTAINER MOUNT [PAIR_ID]"
    container=$1
    mount=$2
    pair_id=${3:-$(date -u +%Y%m%dT%H%M%SZ)-$$}
    [[ "$container" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "unsafe container name or id"
    ;;
  sdk)
    # Every command in the Sandbox goes through the JS SDK's sandbox.exec, as
    # an agent's would; docker is used only to read container metadata.
    [[ "$candidate" == layerfs-core ]] || die "sdk mode is for layerfs-core"
    [[ $# -ge 3 && $# -le 4 ]] || die "sdk mode requires SDK_HOME SANDBOX MOUNT [PAIR_ID]"
    sdk_home=$1
    sandbox=$2
    mount=$3
    pair_id=${4:-$(date -u +%Y%m%dT%H%M%SZ)-$$}
    [[ "$sdk_home" == /* && -f "$sdk_home/deploy.env" ]] || die "SDK_HOME must hold the holder's deploy.env"
    [[ "$sandbox" =~ ^[a-z0-9][a-z0-9_.-]*$ ]] || die "unsafe Sandbox id"
    # The SDK names a Sandbox's container <LAYERFS_CONTAINER_PREFIX><id>.
    container=$(. "$sdk_home/deploy.env" && docker inspect --type container --format '{{.Id}}' "$prefix$sandbox") ||
      die "no container for Sandbox $sandbox"
    [[ -z "${EXEC_USER:-}" ]] || die "sdk mode runs as the Sandbox command identity; EXEC_USER is not accepted"
    ;;
  *) die "execution mode must be host, docker or sdk" ;;
esac

[[ "$pair_id" =~ ^[A-Za-z0-9._-]+$ && "$pair_id" != . && "$pair_id" != .. && ${#pair_id} -le 128 ]] ||
  die "PAIR_ID must be 1-128 safe filename characters and cannot be . or .."
[[ "$mount" == /* ]] || die "MOUNT must be absolute"
case "$mount" in *[$' \t\n']*) die "MOUNT must not contain whitespace" ;; esac
check_frozen_runner

# One sample per arm, no warmup, fixed order: the repository measurement rules
# (AGENTS.md section 3) forbid best-of samples and warm-cache credit.
reps=${REPS:-1}
warmup=${WARMUP:-0}
randomize=${RANDOMIZE_TARGETS:-0}
[[ "$reps" =~ ^[1-9][0-9]*$ ]] || die "REPS must be a positive integer"
[[ "$warmup" =~ ^[0-9]+$ ]] || die "WARMUP must be a non-negative integer"
[[ "$randomize" == 0 || "$randomize" == 1 ]] || die "RANDOMIZE_TARGETS must be 0 or 1"
[[ -z "${BASE:-}" ]] || die "BASE is not accepted: paired arms must each contain exactly 12 mount rows"

# The user the runner executes as. Each arm runs as its mount's intended user:
# computerd's files belong to root, while LayerFS projects every inode as the
# Sandbox command identity (501:20 in the holder), so git as root would refuse
# a LayerFS repository as "dubious ownership". EXEC_USER overrides the default.
case "$candidate" in
  computer-upstream) default_user=0:0 ;;
  layerfs-core) default_user=501:20 ;;
esac
exec_user=${EXEC_USER:-$default_user}
[[ "$exec_user" =~ ^[0-9]+:[0-9]+$ ]] || die "EXEC_USER must be numeric UID:GID"

run_dir="$results/$pair_id/$candidate"
[[ ! -e "$run_dir" ]] || die "refusing to overwrite existing result: $run_dir"
sdk_check=

if [[ "$mode" == host ]]; then
  [[ "$(uname -s)" == Linux ]] || die "host mode requires Linux; use docker mode for an in-container mount"
  [[ "$exec_user" == "$(id -u):$(id -g)" ]] || die "host mode runs as the caller ($(id -u):$(id -g)); EXEC_USER=$exec_user needs docker mode"
  (( BASH_VERSINFO[0] >= 4 )) || die "host mode requires Bash 4+"
  command -v shuf >/dev/null || die "host mode requires shuf"
  mount=$(readlink -f -- "$mount")
  mount_evidence=$(sh -c "$mountinfo_program" sh "$mount") || die "MOUNT is not an exact FUSE mountpoint: $mount"
elif [[ "$mode" == docker ]]; then
  command -v docker >/dev/null || die "docker is required for docker mode"
  docker inspect --type container --format '{{.State.Running}}' "$container" | grep -qx true || die "container is not running: $container"
  mount_evidence=$(docker exec "$container" sh -c "$mountinfo_program" sh "$mount") || die "MOUNT is not an exact in-container FUSE mountpoint: $mount"
else
  # The first call reports the command identity and the mount it runs on.
  sdk_check=$(mktemp "${TMPDIR:-/tmp}/layerfs-fs-bench-sdk.XXXXXX")
  sdk_exec "$(printf 'printf "%%s:%%s\\n" "$(id -u)" "$(id -g)" && sh -c %q sh %q' "$mountinfo_program" "$mount")" "$sdk_check" ||
    die "sandbox.exec refused the mount check"
  [[ "$(sdk_field "$sdk_check" exitCode)" == 0 ]] || die "MOUNT is not an exact FUSE mountpoint in the Sandbox: $mount"
  exec_user=$(sdk_field "$sdk_check" stdout | sed -n 1p)
  mount_evidence=$(sdk_field "$sdk_check" stdout | sed 1d)
  [[ "$exec_user" == "$default_user" ]] || die "the Sandbox runs commands as $exec_user, not $default_user"
fi

mkdir -p "$results/$pair_id"
mkdir "$run_dir"
printf '%s\n' "$mount_evidence" >"$run_dir/mountinfo.txt"
[[ -z "$sdk_check" ]] || mv "$sdk_check" "$run_dir/sdk-check.json"
git -C "$repo" status --short >"$run_dir/layerfs-source-status.txt"

intended_commit=$(git -C "$repo" rev-parse HEAD)
intended_tree=
if [[ "$candidate" == computer-upstream ]]; then
  intended_commit=$computer_commit
  intended_tree=$computer_tree
fi
observed_revision=
observed_tree=
provenance_status=unverified
provenance_basis='host-visible mount; candidate identity is caller-selected and not independently verified'

if [[ -n "$container" ]]; then
  docker inspect --type container "$container" >"$run_dir/container-inspect.json"
  image_id=$(docker inspect --type container --format '{{.Image}}' "$container")
  docker image inspect "$image_id" >"$run_dir/image-inspect.json"
  read -r observed_revision observed_tree < <(python3 - "$run_dir/image-inspect.json" <<'PY'
import json
import sys

image = json.load(open(sys.argv[1], encoding="utf-8"))[0]
labels = image.get("Config", {}).get("Labels") or {}
revision = (
    labels.get("org.opencontainers.image.layerfs.source-commit")
    or labels.get("dev.layerfs.upstream-commit")
    or labels.get("org.opencontainers.image.revision")
    or "-"
)
tree = (
    labels.get("org.opencontainers.image.layerfs.source-tree")
    or labels.get("dev.layerfs.upstream-tree")
    or labels.get("org.opencontainers.image.source-tree")
    or "-"
)
print(revision, tree)
PY
  )
  [[ "$observed_revision" == - ]] && observed_revision=
  [[ "$observed_tree" == - ]] && observed_tree=
  [[ -z "$observed_revision" || "$observed_revision" =~ ^[0-9a-f]{40}$ ]] || observed_revision=
  [[ -z "$observed_tree" || "$observed_tree" =~ ^[0-9a-f]{40}$ ]] || observed_tree=
  if [[ "$observed_revision" == "$intended_commit" ]]; then
    if [[ "$candidate" == layerfs-core && "$observed_tree" =~ ^[0-9a-f]{40}$ ]]; then
      provenance_status=verified
      provenance_basis='container image labels match the intended LayerFS revision and expose its exact source-tree seal; inspect evidence retained'
    elif [[ "$candidate" == computer-upstream && "$observed_tree" == "$intended_tree" ]]; then
      provenance_status=verified
      provenance_basis='container image labels match the pinned Computer commit and tree; inspect evidence retained'
    else
      provenance_basis='container image inspected, but required commit/tree labels are absent or do not match the intended source'
    fi
  else
    provenance_basis='container image inspected, but its revision label is absent or does not match the intended source'
  fi
fi

started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
set +e
if [[ "$mode" == host ]]; then
  MOUNT="$mount" BASE= REPS="$reps" WARMUP="$warmup" \
    RANDOMIZE_TARGETS="$randomize" SCENARIOS="$scenarios" \
    OUTPUT_JSON="$run_dir/result.json" bash "$bench" \
    >"$run_dir/stdout.txt" 2>"$run_dir/stderr.txt"
  status=$?
elif [[ "$mode" == sdk ]]; then
  # One call stages the frozen runner outside the Workspace, checks its hash
  # and runs it; the next returns its JSON and removes both files.
  remote_prefix="/tmp/layerfs-fs-bench-$pair_id-$candidate-$$"
  remote_bench="$remote_prefix.sh"
  remote_json="$remote_prefix.json"
  run_command=$(printf 'printf %%s %q | base64 -d >%q && printf "%%s  %%s\\n" %q %q | sha256sum -c --quiet && env MOUNT=%q BASE= REPS=%q WARMUP=%q RANDOMIZE_TARGETS=%q SCENARIOS=%q OUTPUT_JSON=%q bash %q' \
    "$(base64 <"$bench" | tr -d '\n')" "$remote_bench" "$expected_sha256" "$remote_bench" \
    "$mount" "$reps" "$warmup" "$randomize" "$scenarios" "$remote_json" "$remote_bench")
  if sdk_exec "$run_command" "$run_dir/sdk-run.json" 2>"$run_dir/sdk-run.stderr.txt"; then
    sdk_field "$run_dir/sdk-run.json" stdout >"$run_dir/stdout.txt"
    sdk_field "$run_dir/sdk-run.json" stderr >"$run_dir/stderr.txt"
    status=$(sdk_field "$run_dir/sdk-run.json" exitCode)
    [[ "$(sdk_field "$run_dir/sdk-run.json" truncated)" == False ]] || status=125
  else
    status=124
    : >"$run_dir/stdout.txt"
    : >"$run_dir/stderr.txt"
  fi
  collect=$(printf 'cat %q; code=$?; rm -f -- %q %q; exit $code' "$remote_json" "$remote_bench" "$remote_json")
  if sdk_exec "$collect" "$run_dir/sdk-collect.json" 2>"$run_dir/sdk-collect.stderr.txt"; then
    if [[ "$status" == 0 ]]; then
      sdk_field "$run_dir/sdk-collect.json" stdout >"$run_dir/result.json"
      status=$(sdk_field "$run_dir/sdk-collect.json" exitCode)
    fi
  elif [[ "$status" == 0 ]]; then
    status=124
  fi
else
  remote_prefix="/tmp/layerfs-fs-bench-$pair_id-$candidate-$$"
  remote_bench="$remote_prefix.sh"
  remote_json="$remote_prefix.json"
  docker cp "$bench" "$container:$remote_bench" >"$run_dir/docker-copy.stdout.txt" 2>"$run_dir/docker-copy.stderr.txt"
  copy_status=$?
  if [[ "$copy_status" == 0 ]]; then
    docker exec --user "$exec_user" "$container" env \
      MOUNT="$mount" BASE= REPS="$reps" WARMUP="$warmup" \
      RANDOMIZE_TARGETS="$randomize" SCENARIOS="$scenarios" OUTPUT_JSON="$remote_json" \
      bash "$remote_bench" >"$run_dir/stdout.txt" 2>"$run_dir/stderr.txt"
    status=$?
    if [[ "$status" == 0 ]]; then
      docker cp "$container:$remote_json" "$run_dir/result.json" >>"$run_dir/docker-copy.stdout.txt" 2>>"$run_dir/docker-copy.stderr.txt"
      status=$?
    fi
  else
    status=$copy_status
    : >"$run_dir/stdout.txt"
    : >"$run_dir/stderr.txt"
  fi
  docker exec "$container" rm -f -- "$remote_bench" "$remote_json" >/dev/null 2>&1
fi
set -e
finished=$(date -u +%Y-%m-%dT%H:%M:%SZ)

{
  printf 'schema\tlayerfs-fs-bench-v2\n'
  printf 'pair_id\t%s\n' "$pair_id"
  printf 'candidate\t%s\n' "$candidate"
  printf 'execution_mode\t%s\n' "$mode"
  case "$mode" in
    host) printf 'command_route\tbash on the host\n' ;;
    docker) printf 'command_route\tdocker exec\n' ;;
    sdk) printf 'command_route\tsandbox.exec (@layerfs/sdk), Sandbox %s\n' "$sandbox" ;;
  esac
  printf 'intended_candidate_commit\t%s\n' "$intended_commit"
  printf 'intended_candidate_tree\t%s\n' "$intended_tree"
  printf 'observed_candidate_revision\t%s\n' "$observed_revision"
  printf 'observed_candidate_tree\t%s\n' "$observed_tree"
  printf 'provenance_status\t%s\n' "$provenance_status"
  printf 'provenance_basis\t%s\n' "$provenance_basis"
  printf 'canonical_runner\tbenchmark/fs-bench/fs-bench.sh\n'
  printf 'canonical_runner_sha256\t%s\n' "$expected_sha256"
  printf 'runner_upstream_repository\thttps://github.com/cloudflare/computer\n'
  printf 'runner_upstream_commit\t%s\n' "$computer_commit"
  printf 'runner_upstream_tree\t%s\n' "$computer_tree"
  printf 'runner_upstream_path\tscript/fs-bench.sh\n'
  printf 'started_utc\t%s\n' "$started"
  printf 'finished_utc\t%s\n' "$finished"
  printf 'mount\t%s\n' "$mount"
  printf 'exec_user\t%s\n' "$exec_user"
  printf 'reps\t%s\n' "$reps"
  printf 'warmup\t%s\n' "$warmup"
  printf 'randomize_targets\t%s\n' "$randomize"
  printf 'exit_status\t%s\n' "$status"
  printf 'scope\tresident real-FUSE filesystem operations only\n'
  printf 'excludes\tsetup,pull,fork,mount,workspace-commit,push,add,reopen,persistent-space\n'
} >"$run_dir/manifest.tsv"

printf '%s\n' "$run_dir"
exit "$status"
