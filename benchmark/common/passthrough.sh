# The FUSE baseline arm, sourced by a speed suite's run.sh after lib.sh.
#
# A Sandbox cannot host a second FUSE mount: its container runs with
# no-new-privileges and a seccomp filter against user namespaces, and
# sandbox.exec commands run as uid 501 with no capability
# (core/crates/layerfs-sandbox/src/backend/docker/container.rs, topology.rs).
# So the baseline runs in a sibling container on the same Docker VM and
# kernel: the suite's own Sandbox image plus libfuse's passthrough_ll
# (passthrough/Dockerfile), with /dev/fuse and CAP_SYS_ADMIN only. Root
# mounts passthrough_ll over /tmp/pt-src at /tmp/pt with allow_other and
# its defaults (multi-threaded, max 10 threads, cache timeout 1.0 s,
# writeback off, as LayerFS); the measured command runs as uid 501, gid 20,
# HOME=/tmp, the same identity as sandbox.exec. This arm is not LayerFS and
# does not use the SDK; the LayerFS arm is unchanged.
#
#   bench_pt_image  SUITE_IMAGE_TAG OUT_FILE   build <tag>-pt, write pt_image=<digest>
#   bench_pt_start  RUN PT_IMAGE_FILE          start the sibling, mount, record it
#   bench_pt_exec   RUN COMMAND                one command in /tmp/pt as 501:20 (bench_limit)
#   bench_pt_stop   RUN                        unmount, remove the sibling (none: recorded, exit 0)
#
# Every docker call has a limit (lib.sh bench_timeout). Killing a docker exec
# CLI leaves its process running in the container, so each exec also runs
# under GNU timeout inside the sibling: bench_pt_exec's command gets TERM at
# bench_limit - 2 s (113) and KILL 1 s later, and exits 124 (137 after KILL),
# before the host limit at bench_limit (115).
bench_pt_name() { echo "bench-$suite-$(basename "$1")-pt"; }

bench_pt_image() {
  local base_image=$1 out=$2 digest
  bench_timeout "$bench_limit" docker build --load -q --build-arg BASE="$base_image" -t "$base_image-pt" "$bench_common/passthrough" >/dev/null
  digest=$(docker image inspect "$base_image-pt" --format '{{.Id}}')
  { printf 'pt_image=%s\npt_tag=%s\npt_base=%s\n' "$digest" "$base_image-pt" "$(docker image inspect "$base_image" --format '{{.Id}}')"
    bench_timeout 60 docker run --rm --entrypoint cat "$base_image-pt" /opt/passthrough-identity.txt | sed 's/^/pt_/'
  } >"$out"
  cat "$out"
}

bench_pt_start() {
  local run=$1 imagefile=$2 name pt_image
  name=$(bench_pt_name "$run")
  pt_image=$(bench_field "$imagefile" pt_image)
  [[ -n "$pt_image" ]] || { echo "passthrough.sh: no pt_image in $imagefile" >&2; exit 2; }
  ! docker inspect "$name" >/dev/null 2>&1 || { echo "passthrough.sh: $name exists" >&2; exit 2; }
  bench_timeout 60 docker run -d --name "$name" --device /dev/fuse --cap-add SYS_ADMIN \
    --security-opt apparmor=unconfined --entrypoint sleep "$pt_image" infinity >/dev/null
  bench_timeout 30 docker exec "$name" timeout -k 2 25 sh -c 'mkdir -p /tmp/pt-src /tmp/pt && chown 501:20 /tmp/pt-src /tmp/pt \
    && passthrough_ll -o source=/tmp/pt-src -o allow_other /tmp/pt && grep " /tmp/pt " /proc/mounts' >"$run/pt-mount.txt"
  { echo "pt_container=$name image=$pt_image started=$(date -u +%FT%TZ)"
    echo "pt_mount=$(cat "$run/pt-mount.txt")"
    echo "pt_options=passthrough_ll -o source=/tmp/pt-src -o allow_other /tmp/pt (defaults: multi-threaded, max_threads 10, timeout 1.0 s, writeback off, no xattr, no flock)"
    sed 's/^/pt_identity: /' "$imagefile"
  } >>"$run/identity.txt"
  cat "$run/pt-mount.txt"
}

bench_pt_exec() {
  local run=$1 command=$2
  bench_timeout "$bench_limit" docker exec -u 501:20 -e HOME=/tmp -w /tmp/pt "$(bench_pt_name "$run")" timeout -k 1 $((bench_limit - 2)) bash -c "$command"
}

bench_pt_stop() {
  local run=$1 name
  name=$(bench_pt_name "$run")
  if ! bench_timeout 30 docker inspect "$name" >/dev/null 2>&1; then
    echo "pt_removed=$name absent at $(date -u +%FT%TZ)" >>"$run/identity.txt"
    return 0
  fi
  bench_timeout 30 docker exec "$name" timeout -k 2 25 sh -c 'fusermount3 -u /tmp/pt' || true
  bench_timeout 60 docker rm -f "$name" >/dev/null
  echo "pt_removed=$name at $(date -u +%FT%TZ)" >>"$run/identity.txt"
}
