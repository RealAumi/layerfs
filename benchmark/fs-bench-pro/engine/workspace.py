"""The working SDK/Sandbox path with separate phases and exact raw counters."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
import time
import uuid

from . import cache, fixtures, identity, io_observer, oracle, receipts

sys.path.insert(0, str(identity.ROOT / "benchmark/cluster-two"))
from cells import counts, runner as cell_runner, workloads

BASELINE = identity.ROOT / "core/docs/issues/307/checks/timing-baseline-20261010/baseline.json"
BASELINE_SHA256 = "a6ada570050f14bb6ff5bd61c74c0d0fda439f323f695fdea1212b26b590d3f8"
# Issue319 phase 14: the frozen C10 row holds one kernel-shaped extra READ (513).
# The source model gives 512: 67,108,864 file bytes in READ_WINDOW 131,072 requests;
# the frozen sample's own warm-up mount of the same command and frozen C09 on the
# same file both count 512. One READ is one request, one owner job and two
# statements. The baseline file itself stays unchanged.
# Issue 320 lowered statements for the same requests and owner jobs; issue 321 (one
# file and one lock per Workspace, open state in memory, remembered fence rows) lowers
# them again. Each statement count below is the per-request model of the final #321
# source (core/docs/issues/320/REQUEST-PATH.md section 10) applied to the cell's frozen
# request mix. C10 keeps its phase 14 request and owner-job correction.
# #320 runtime-row removal: each of C06's 512 WRITE requests loses four
# SQL base-source custody updates and one Workspace-state update (14 -> 9).
# Its constant prefix/suffix loses four more custody statements (15 -> 11).
# Thus 512 * 9 + 11 = 4619. Retained C06 raw logs independently reproduce it.
CELL_COUNT_CORRECTIONS = {
    "C01": {"statements": 21002}, "C02": {"statements": 22002}, "C04": {"statements": 19612},
    "C05": {"statements": 20269}, "C06": {"statements": 4619}, "C07": {"statements": 17440},
    "C08": {"statements": 7185}, "C09": {"statements": 517},
    "C10": {"requests": 1547, "owner_jobs": 1546, "statements": 10773}, "C11": {"statements": 7174}}
# Two cells cannot be one number: a request that runs while a removed file still waits
# for the kernel's FORGET costs more. C03 is 49,038 + 2P, P the inode reads made in such
# windows (at most one for each of 2,000 GETATTRs and two for each of 1,000 UNLINKs).
# C12 runs git, whose LINK, RENAME and SYMLINK requests no replay measures and whose
# LOOKUPs split between absent and present names: 10,977 is the one count observed at
# the final source, kept with the same forty statements either side as before. It is
# an estimate, not a model result. Requests and owner jobs of both stay exact.
CELL_STATEMENT_RANGES = {"C03": {"low": 49038, "high": 49038 + 2 * 4000, "step": 2},
                         "C12": {"low": 10937, "high": 11017, "step": 1}}


def cell_expected_counts(cell, names):
    """Frozen twelve-cell counts with the named source-model correction, and the frozen row."""
    wanted = next(item for item in json.loads(BASELINE.read_text())["selections"] if item["cell"] == cell)
    frozen = {name: wanted[name] for name in names}
    return {**frozen, **{name: value for name, value in CELL_COUNT_CORRECTIONS.get(cell, {}).items() if name in frozen}}, frozen


def cell_counts_reproduced(cell, totals, wanted):
    """Exact for every count, except the statements of a cell with a declared range."""
    allowed = CELL_STATEMENT_RANGES.get(cell)
    for name in totals:
        if name == "statements" and allowed is not None:
            value = totals[name]
            if not (allowed["low"] <= value <= allowed["high"] and (value - allowed["low"]) % allowed["step"] == 0):
                return False
        elif totals[name] != wanted[name]:
            return False
    return True
BATCH4_HISTORY_SCHEMAS = frozenset(("original-v016-boundary-sequence-v1",
    "original-dedup-history-sequence-v1", "original-m1-commit-sequence-v1"))
BATCH4_FAMILIES = frozenset(("file_size_transition","dedup_branch_history","mixed_load_bearing"))



# Owner D-3, issue319: only the six previously failing largest checks.
LARGE_CHECK_CASES = frozenset(("dedup-workspace-unique-500",
    "store-footprint-unique-100000", "store-footprint-metadata-cardinality-100000"))


def alias_parent_custody(case, prepared, command, output):
    """Bind the independently qualified single automatic alias field."""
    declaration = case.get("automatic_parent_mtime")
    expected = {"schema":"original-boundary-parent-mtime-v1", "path":"data", "step":5,
                "native_precision_allowance_ns":1000000000, "max_operation_ns":60000000000,
                "publication":"exact observed nanoseconds on fresh native and persisted trees"}
    if (case.get("v016_case") != "v016-boundary-alias-roundtrip-v1"
            or command["fields"].get("exit_code") != "0"
            or not isinstance(declaration,dict) or any(declaration.get(k) != v for k,v in expected.items() if k != "publication")
            or prepared.get("native_verification",{}).get("automatic-parent-mtime",{}).get("verification_status") != "pass"):
        raise ValueError("original alias automatic-time declaration/native qualification differs")
    text = Path(command["fields"]["stdout"]).read_text()
    marker = expected["schema"] + "\n"
    if text.count(marker) != 1:
        raise ValueError("exactly one alias parent custody observation required")
    body = text[text.index(marker):]
    lines = body.splitlines()
    if (len(lines) != 8 or not body.endswith("\n") or lines[:4] !=
            [expected["schema"],"case\tv016-boundary-alias-roundtrip-v1","step\t5","path\tdata"]):
        raise ValueError("alias parent custody fixed-domain rows differ")
    values=[]
    for name,line in zip(("initial","started","finished","observed"),lines[4:]):
        fields=line.split("\t")
        if len(fields)!=3 or fields[0]!=name:
            raise ValueError("alias custody timestamp row differs")
        seconds,nanos=map(int,fields[1:])
        if seconds<0 or not 0<=nanos<1000000000 or line!=f"{name}\t{seconds}\t{nanos}":
            raise ValueError("alias custody timestamp domain/canonical form differs")
        values.append(seconds*1000000000+nanos)
    initial,start,end,observed=values
    if (initial!=1700000000000000000 or observed==initial or end<start
            or end-start>60000000000 or observed<start-1000000000 or observed>end):
        raise ValueError("alias custody original epoch/clock envelope differs")
    path=script(output,"boundary-parent-mtime.tsv",body)
    return {"index":5,"path":str(path),"sha256":identity.sha256(path),
            "helper_stdout":command["fields"]["stdout"],
            "helper_stdout_sha256":identity.sha256(command["fields"]["stdout"]),
            "scope":"only alias data parent automatic mtime; all publication comparisons exact"}


# Owner direction 2026-10-12, issue319 phase 13: only the six 500 MiB mixed
# cases, whose mounted proof of one 30298-path root alone takes 17-21 s.
LARGE_ROOT_PROOF_LIMITS = {
    "v016-mixed-development-500mb-30000-k10-v1": (50000, 60000),
    "v016-mixed-development-500mb-30000-k100-v1": (50000, 60000),
    "v016-workspace-mixed-500mb-30000-k10-v1": (80000, 90000),
    "v016-workspace-mixed-500mb-30000-k100-v1": (80000, 90000),
    "v016-branch-mixed-500mb-30000-k10-v1": (105000, 115000),
    "v016-branch-mixed-500mb-30000-k100-v1": (105000, 115000),
}


def import_proof_deadlines(case, charged_ns=0):
    budget = case["budget"]
    reserve = budget.get("cleanup_reserve_ms", case.get("original_resource_guards", {}).get("verification_cleanup_reserve_ms", 4000))
    work, hard = (75000, 89000) if case.get("id") in LARGE_CHECK_CASES else (45000, 59000)
    if (budget["verifier_ms"], budget["verification_hard_watchdog_ms"], reserve, budget.get("publication_guard_ms", 250)) != (work, hard, 4000, 250):
        raise ValueError("original import work/cleanup/publication limits required")
    if type(charged_ns) is not int or charged_ns < 0:
        raise ValueError("nonnegative original charged proof wall required")
    now = time.monotonic()-charged_ns/1e9
    return {"work": now+(work-reserve)/1000, "cleanup": now+work/1000, "publication": now+hard/1000}


def verify_import_mount(case, prepared, build, output, row, deadlines):
    """Original post-import Fork and complete fresh-mounted native verifier."""
    import shutil
    def stop(limit=15, cleanup=False):
        deadline = deadlines["cleanup" if cleanup else "work"]
        return operation_deadline(deadline, limit)
    def seconds(limit=15, cleanup=False):
        return stop(limit, cleanup)-time.monotonic()
    provision = row.get("installation")
    if (not isinstance(provision, dict) or provision.get("schema") != "fs-bench-pro-public-init-install-v1"
            or provision.get("status") != "PASS" or provision.get("global_profile") != "Disposable/WAL/OFF"
            or provision.get("volume") != row.get("clone", {}).get("volume")
            or provision.get("container") not in row.get("additional_containers", [])
            or identity.sha256(Path(provision["manifest"])) != provision.get("manifest_sha256")
            or identity.sha256(output/"store.sqlite") != provision.get("store_sha256")):
        raise ValueError("actual public installation of exact measured Init required before fresh verifier")
    volume = provision["volume"]
    row["verification"]["installation"] = provision
    helpers = fixtures.assets(output/"verification-code")
    binary = Path(helpers["root"])/"writers/workload"
    binary.parent.mkdir()
    shutil.copy2(build["binaries"]["workload-linux"]["path"], binary)
    binary.chmod(0o555)
    helpers["files"]["writers/workload"] = identity.sha256(binary)
    staged = {"helpers": helpers}
    runtime = None
    key = secrets.token_hex(32)
    mounted = False
    try:
        argv = [build["binaries"]["runtime"]["path"], "serve", "--socket", build["socket"],
                "--volume", volume, "--daemon", build["binaries"]["daemon"]["path"],
                "--manifest", provision["manifest"], "--receipt", str(output/"runtime.events.jsonl"),
                "--uid", str(prepared["source_uid"]), "--gid", str(prepared["source_gid"]),
                "--observation-scope", secrets.token_hex(32)]
        runtime = cell_runner.EventProcess(argv, output, "runtime")
        runtime.event("protocol_ready", stop())
        row["container"] = runtime.container
        docker = ["docker", "--host", "unix://"+build["socket"]]
        receipts.command([*docker,"update","--cpus","2","--memory","2147483648","--memory-swap","2147483648","--pids-limit","256",runtime.container],
                         output,"import-verifier-profile",seconds())
        inspected = receipts.command([*docker,"inspect",runtime.container,"--format","{{json .HostConfig}}"],
                                     output,"import-verifier-profile-readback",seconds())
        wanted = {"NanoCpus":2_000_000_000,"Memory":2_147_483_648,"MemorySwap":2_147_483_648,"PidsLimit":256}
        actual = json.loads(Path(inspected["stdout"]).read_text())
        if any(actual.get(name)!=value for name,value in wanted.items()):
            raise ValueError("original independent verifier resource profile differs")
        row["verification"]["container_profile"] = wanted
        fixtures.stage(runtime.container, staged, output/"verification-staging", build, deadline=deadlines["work"])
        before = ordinary_resource_guard(runtime,build,output,"import-verifier-resources-before",seconds=seconds())
        identifier = "11"+secrets.token_hex(16)
        request = script(output,"import-verifier-fork.tsv",f"layer\t{identifier}\tverify-import\n")
        fork = runtime.send("fork","verify-import",request,deadline=stop())
        if (fork["fields"].get("branch_id")!=identifier or fork["fields"].get("root")!=row["init"]["fields"]["root"]
                or fork["fields"].get("head")!="-" or fork["fields"].get("stack")!=row["init"]["fields"]["stack"]):
            raise ValueError("original verifier Fork differs from exact imported Layer")
        row["verification"]["fork"] = fork
        context_send(runtime,"mount-branch",key,"verify-import",deadline=stop())
        mounted = True
        body = "/code/writers/workload workspace-verify-tree "+shlex.quote(case["v016_case"])+" 1 0"
        verified = runtime.send("verify",key,script(output,"import-native-proof.sh",body),deadline=stop(45))
        row["verification"]["native"] = verify_native_receipt(case,verified)
        runtime.send("unmount",key,deadline=stop(cleanup=True))
        mounted = False
        row["verification"]["cleanup"] = readiness(runtime,key,seconds(5,True))
        row["cleanup"] = "Gone"
        row["verification"]["resources_after"] = ordinary_resource_guard(runtime,build,output,
            "import-verifier-resources-after",before,seconds=seconds(cleanup=True))
        runtime.send("observe",deadline=stop(cleanup=True))
        observed = {}
        cell_runner.snapshot_observations(runtime,observed)
        row["verification"]["observations"] = observed
        runtime.send("stop",deadline=stop(cleanup=True))
        runtime.event("finished",stop(cleanup=True))
        if runtime.process.wait(timeout=seconds(1,True))!=0:
            raise ValueError("known independent verifier Stop exit differs")
        row.update(custody="KNOWN_STOP",resource_removal_pending=True,
                   resource_disposition="known stopped verification-only sample pair retained pending outer publication acknowledgement")
        logs = receipts.command([*docker,"logs","--timestamps=false",runtime.container],output,"import-verifier-daemon-logs",seconds(cleanup=True))
        row["verification"]["numeric_telemetry"] = {"stdout":logs["stdout"],"stderr":logs["stderr"],
            "scope":"verifier-only original raw telemetry; host Init has no daemon counts; no verifier work credited as performance"}
    except BaseException as error:
        if runtime is not None:
            row.update(container=runtime.container, retained_host_custody=runtime.retain(error),
                       retained_mount_keys=[key] if mounted else [], resource_disposition="failed independent verifier resources retained; no inferred End/Stop")
        raise
    finally:
        if runtime is not None:
            for value in (runtime.selector,runtime.raw,runtime.stderr,getattr(runtime.process,"stdin",None),getattr(runtime.process,"stdout",None)):
                if value is not None:
                    value.close()


def script(folder, name, body):
    path = Path(folder) / name
    with path.open("x") as stream:
        stream.write(body)
    path.chmod(0o444)
    return path


def readiness(runtime, key, seconds=5):
    deadline = time.monotonic() + seconds
    observations = []
    while True:
        row = runtime.send("cleanup", key, deadline=deadline)
        observations.append(row)
        if row["fields"]["state"] == "Gone":
            return observations
        # New read-only observations of ongoing automatic cleanup, not retries
        # of a mutation/unmount and never a maintenance invocation.
        if time.monotonic() >= deadline:
            raise TimeoutError("original physical cleanup did not reach Gone")
        time.sleep(min(0.005, max(0, deadline - time.monotonic())))


def endpoint(event, position="last"):
    return {"event_sequence": event["sequence"], "event": event["event"], "position": position}


def terminal_cache_observation(runtime, key, build, output, cache_class="B"):
    # Reclamation mutates overlay bytes after unmount. Establish the original
    # physical terminal boundary before observing stable backing identity.
    cleaned = readiness(runtime, key)
    observer = ["docker", "--host", "unix://" + build["socket"], "exec", "--user", "0:0", runtime.container,
                "python3", "-B", "/code/cache/residency.py", "--class", cache_class,
                "--store", "/layerfs-store/global/store.sqlite", "--overlay", "/layerfs-local/overlay/overlay.sqlite"]
    observed = receipts.command(observer, output, "cache-observation", 15, allow_failure=True)
    residency = json.loads(Path(observed["stdout"]).read_text())
    if observed["exit_code"] != 0:
        declared_miss = (observed["exit_code"] == 3 and cache_class == "A"
            and residency.get("cache_class") == "A" and residency.get("status") == "INELIGIBLE"
            and type(residency.get("resident_pages")) is int and residency["resident_pages"] > 0
            and type(residency.get("attempts")) is int and residency["attempts"] == 0
            and residency.get("exploratory") is True and residency.get("admission_eligible") is False
            and type(residency.get("payload_bytes_read")) is int and residency["payload_bytes_read"] == 0)
        declared_unknown = (observed["exit_code"] == 4 and cache_class == "A"
            and residency.get("cache_class") == "A" and residency.get("status") == "UNAVAILABLE"
            and type(residency.get("attempts")) is int and residency["attempts"] == 0
            and type(residency.get("errno")) is int and residency["errno"] >= 0
            and isinstance(residency.get("error"), str) and bool(residency["error"])
            and residency.get("admission_eligible") is not True)
        if not (declared_miss or declared_unknown):
            raise RuntimeError(f"cache-observation failed with exit {observed['exit_code']}; see {output}")
    return cleaned, residency


def price(groups, events, bindings, measured_label="measured command", with_warm_mount=True):
    correlated = counts.correlate(events, groups)
    selectors = [{"label": measured_label, "before": "measured_mount_attach", "end": "command_end_status"}]
    if with_warm_mount:
        selectors.append({"label": "measured mount after warm terminal", "before": "warmup_unmount", "end": "measured_mount_attach"})
    resolved = counts.resolve_selectors(selectors, bindings, correlated)
    priced = []
    for row in resolved:
        if row["status"] != "RESOLVED":
            raise ValueError("original count endpoint unavailable: " + row.get("reason", "unknown"))
        value = counts.phase_counts(groups, row["before_identity"], row["end_identity"],
                                    exclusive_observer_scope=True, label=row["label"], control_correlation=correlated)
        if value["status"] != "AVAILABLE":
            raise ValueError("original phase counters unavailable: " + value.get("reason", "unknown"))
        priced.append(value)
    command = priced[0]
    if "opcodes" not in command["raw"]:
        raise ValueError("original kernel opcode count unavailable")
    totals = {"requests": sum(command["raw"]["opcodes"]["by_opcode"]),
              "owner_jobs": command["adjusted"]["owner"]["jobs" if "jobs" in command["adjusted"]["owner"] else "admitted"],
              "statements": sum(row["executions"] for row in command["adjusted"]["sql_foreground"])}
    return totals, priced, correlated


def claim_key(cell, current, prepared, build):
    # The owner-directed final baseline is scoped to the exact committed source.
    # Clone IDs, authority randomness and report dates never alter its claim.
    harness = {name: digest for name, digest in current["files"].items()
               if name.startswith(("benchmark/fs-bench-pro/engine/", "benchmark/cluster-two/cells/",
                                   "benchmark/cluster-two/cache/")) or name.endswith("/bench.py")}
    value = {"cell": cell, "cache_class": "B", "fixture": prepared["fixture"]["fixture_sha256"],
             "product": current["product_tree"], "harness": harness,
             "binaries": {name: row["sha256"] for name, row in build["binaries"].items()},
             "image": identity.IMAGE, "body": workloads.COMMANDS[cell]}
    return receipts.sample_claim_key(value, current["source_commit"])


def one_cell(cell, prepared_folder, build_folder, output):
    current = identity.source_identity()
    if cell not in fixtures.CELL_RECIPES:
        raise ValueError("cell is not in the twelve-cell stage 0.4 selection")
    build = identity.load_build(build_folder)
    prepared = fixtures.load(prepared_folder, fixtures.CELL_RECIPES[cell])
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    claims = identity.ROOT / "benchmark-results/fs-bench-pro/claims"
    claims.mkdir(parents=True, exist_ok=True)
    key = claim_key(cell, current, prepared, build)
    with (claims / key).open("x") as stream:
        stream.write(str(output) + "\n")
    body = workloads.COMMANDS[cell]
    row = {"schema": "fs-bench-pro-workspace-cell-v1", "family": "cluster-two/cells", "case": cell,
           "source_commit": current["source_commit"], "product_tree": current["product_tree"],
           "identity": current, "build": str(build_folder), "daemon_sha256": build["binaries"]["daemon"]["sha256"],
           "runtime_sha256": build["binaries"]["runtime"]["sha256"], "image": identity.IMAGE,
           "status": "NOT_RUN", "attempted_operation_count": 0, "completed_operation_count": 0,
           "sample_count": 0, "cache_class": "B", "cache": {"class": "B"}, "phases": {},
           "counts": {}, "cleanup": "UNAVAILABLE", "proof_status": "NOT_RUN", "admission_eligible": False,
           "declared_limit_ns": 15_000_000_000, "verifier_limit_ns": 9_500_000_000,
           "global_profile": "Disposable/WAL/OFF", "overlay_profile": "MEMORY/OFF/EXCLUSIVE",
           "construction_workers": 1, "durable": "NOT_RUN — disabled by owner until explicit reauthorization",
           "interference": "single checkout lock; existing unrelated Docker containers share the VM, unquantified",
           "command_sha256": hashlib.sha256(body.encode()).hexdigest(), "claim": key}
    receipts.write_new(output / "selection.json", row)
    runtime = None
    bindings = {}
    clock = cell_runner.PerformanceClock()
    started = time.monotonic_ns()
    mounted = {}
    try:
        if identity.sha256(BASELINE) != BASELINE_SHA256:
            raise ValueError("closed twelve-cell count baseline differs from its pinned source")
        cloned = fixtures.clone(prepared, output / "clone", build)
        row["clone"] = cloned
        environment = output / "environment.txt"
        environment.write_text("".join(name + "=" + value + "\n" for name, value in workloads.ENV.items()))
        argv = [build["binaries"]["runtime"]["path"], "serve", "--socket", build["socket"],
                "--volume", cloned["volume"], "--daemon", build["binaries"]["daemon"]["path"],
                "--manifest", prepared["provision"]["manifest"], "--receipt", str(output / "runtime.events.jsonl"),
                "--uid", str(prepared["source_uid"]), "--gid", str(prepared["source_gid"]),
                "--environment-file", str(environment), "--observation-scope", secrets.token_hex(32)]
        runtime = cell_runner.EventProcess(argv, output, "runtime")
        runtime.event("protocol_ready", time.monotonic() + 15)
        if runtime.container is None:
            raise ValueError("original acknowledged container identity unavailable")
        row["container"] = runtime.container
        row["staging"] = fixtures.stage(runtime.container, prepared, output / "staging", build)
        warm = secrets.token_hex(32)
        mounted[warm] = runtime.send("mount", warm, deadline=time.monotonic() + 15)
        runtime.send("command", warm, script(output, "warmup.sh", body), deadline=time.monotonic() + 15)
        warm_unmount = runtime.send("unmount", warm, deadline=time.monotonic() + 15)
        bindings["warmup_unmount"] = endpoint(warm_unmount)
        mounted.pop(warm)
        row["warmup_cleanup"] = readiness(runtime, warm)
        row["cache"].update(fresh_mount=True, warmup_terminal_unmount=True, warmup_cleanup="Gone",
                            declaration="fresh mount on same warm daemon after one identical untimed call and terminal cleanup; no cold source claim")
        row["setup_ns"] = time.monotonic_ns() - started
        clock.begin(time.monotonic_ns())
        row.update(attempted_operation_count=1, sample_count=1)
        measured = secrets.token_hex(32)
        mount = runtime.send("mount", measured, deadline=time.monotonic() + 15)
        mounted[measured] = mount
        bindings["measured_mount_attach"] = endpoint(mount)
        row["phases"]["mount_ns"] = mount["span"]["duration_ns"]
        runtime.send("observe", deadline=time.monotonic() + 15)
        command = runtime.send("command", measured, script(output, "command.sh", cell_runner.inner_timed(body)),
                               deadline=time.monotonic() + 15)
        row["phases"]["command_ns"] = command["span"]["duration_ns"]
        row["command_in_container"] = cell_runner.inner_clock_observation(command)
        runtime.send("snapshot", measured, deadline=time.monotonic() + 15)
        status = next(event for event in reversed(runtime.rows) if event["event"] == "workspace_status")
        bindings["command_end_status"] = endpoint(status)
        proof_start = time.monotonic_ns()
        clock.begin_verifier(proof_start)
        inside = "/tmp/layerfs-r7-fsb-observed-" + secrets.token_hex(8)
        verify_body = "python3 -B /code/engine/oracle.py verify --case " + cell + " --root . --output " + inside + " --expected /code/expected-" + cell + " --helpers /code/cells --policy /code/git-default-policy.json"
        verified = runtime.send("verify", measured, script(output, "verify.sh", verify_body),
                                deadline=time.monotonic() + 9.5)
        proof = json.loads(Path(verified["fields"]["stdout"]).read_text())
        if proof["status"] != "PASS":
            raise ValueError("original independent oracle did not pass")
        row["proof_status"] = "PASS"
        row["verification"] = proof
        row["proof_wall_ns"] = time.monotonic_ns() - proof_start
        clock.end_verifier(time.monotonic_ns())
        unmounted = runtime.send("unmount", measured, deadline=time.monotonic() + 15)
        mounted.pop(measured)
        row["phases"]["unmount_ns"] = unmounted["span"]["duration_ns"]
        clock.finish(time.monotonic_ns())
        row["complete_wall_ns"] = clock.observe(time.monotonic_ns())["performance_ns"]
        row["performance_clock"] = clock.observe(time.monotonic_ns())
        # This per-file mincore observer is outside product time. No eviction,
        # sync call, cache coldness claim or missing-counter credit is added.
        row["cleanup_observations"], row["cache"]["residency"] = terminal_cache_observation(runtime, measured, build, output)
        row["cleanup"] = "Gone"
        runtime.send("observe", deadline=time.monotonic() + 15)
        runtime.send("stop", deadline=time.monotonic() + 15)
        runtime.event("finished", time.monotonic() + 15)
        if runtime.process.wait(timeout=1) != 0:
            raise ValueError("runtime process failed after its stop acknowledgement")
        row["custody"] = "KNOWN_STOP"
        row["completed_operation_count"] = 1
        docker = ["docker", "--host", "unix://" + build["socket"]]
        receipts.command([*docker, "cp", runtime.container + ":" + inside, str(output / "actual")],
                         output, "oracle-export", 15)
        # Preserve expected raw observations too, so verify never needs a mount
        # or a disposed sample volume and performs no second product sample.
        import shutil
        shutil.copytree(prepared["oracles"]["cases"][cell]["path"], output / "expected")
        logs = receipts.command([*docker, "logs", "--timestamps=false", runtime.container], output, "daemon-logs", 15)
        groups = {}
        for path in (logs["stdout"], logs["stderr"]):
            groups.update(cell_runner.telemetry(path))
        words = lambda value: [int(value[index:index+16], 16) for index in range(0, 64, 16)]
        for group in groups.values():
            if group[0]["daemon"] != words(runtime.daemon_instance) or group[0]["scope"] != words(runtime.scope):
                raise ValueError("original numeric daemon/scope differs from authenticated runtime")
        totals, priced, correlated = price(groups, runtime.rows, bindings)
        row.update(counts=totals, phase_counts=priced, control_correlation=correlated)
        observations = {}
        cell_runner.snapshot_observations(runtime, observations)
        cell_runner.ingest_observations(groups, observations, row["cache"])
        row["observations"] = observations
        row["cache"]["status"] = cache.validate("B", row["cache"])
        row["status"] = "PASS" if row["cache"]["status"] == "ELIGIBLE" else "INELIGIBLE"
        wanted, frozen = cell_expected_counts(cell, totals)
        row["count_reproduction"] = {"expected": wanted,
                                      "actual": totals, "status": "PASS" if cell_counts_reproduced(cell, totals, wanted) else "FAIL"}
        if cell in CELL_STATEMENT_RANGES:
            row["count_reproduction"]["statements_range"] = CELL_STATEMENT_RANGES[cell]
        if wanted != frozen:
            row["count_reproduction"]["frozen_baseline"] = frozen
        if row["count_reproduction"]["status"] != "PASS":
            row.update(status="FAIL", tag="stage 0.4 exact request/owner-job/statement counts differ")
        if row["status"] == "PASS":
            stopped = receipts.command([*docker, "inspect", runtime.container, "--format", "{{.State.Running}}"],
                                       output, "container-state", 15)
            if Path(stopped["stdout"]).read_text().strip() != "false":
                raise ValueError("original container Stop is not confirmed")
            receipts.command([*docker, "rm", runtime.container], output, "remove-passing-container", 15)
            receipts.command([*docker, "volume", "rm", cloned["volume"]], output, "remove-passing-volume", 15)
            row["resource_disposition"] = "passing sample container and volume removed"
        else:
            row["resource_disposition"] = "stopped container and sample volume retained for failed/ineligible evidence"
    except BaseException as error:
        row.update(status="FAIL", original_failure_type=type(error).__name__, original_failure=str(error),
                   retained_mount_keys=list(mounted), resource_disposition="original resources retained; no inferred unmount/stop/removal")
        if clock.started is not None:
            row["complete_wall_ns"] = clock.observe(time.monotonic_ns())["performance_ns"]
        if clock.verifier_started is not None:
            row.update(proof_status="FAIL", proof_wall_ns=time.monotonic_ns() - clock.verifier_started)
        if runtime is None:
            runtime = getattr(error, "event_process", None)
        if runtime is not None:
            row["retained_host_custody"] = runtime.retain(error)
            row["container"] = runtime.container
    finally:
        if runtime is not None:
            for value in (runtime.selector, runtime.raw, runtime.stderr,
                          getattr(runtime.process, "stdin", None), getattr(runtime.process, "stdout", None)):
                if value is not None:
                    try:
                        value.close()
                    except BaseException as closing:
                        row.setdefault("independent_close_failures", []).append(str(closing))
                        row["status"] = "FAIL"
        row["external_driver_wall_ns"] = time.monotonic_ns() - started
        row["timing_scope"] = "matrix controller: measured mount through terminal unmount, independent verifier excluded; setup/cache residency/cleanup/Stop separate; original control observation overhead retained"
        row["evidence"] = str(output.relative_to(identity.ROOT.resolve()))
        io_observer.attach(output, row)
        receipts.write_new(output / "receipt.json", row)
        receipts.manifest(output)
    return row


def collect_family_observations(runtime, row, build, output, bindings, deadline=None):
    docker = ["docker", "--host", "unix://" + build["socket"]]
    logs = receipts.command([*docker, "logs", "--timestamps=false", runtime.container], output, "daemon-logs",
                            15 if deadline is None else operation_deadline(deadline, 15)-time.monotonic())
    groups = {}
    for path in (logs["stdout"], logs["stderr"]):
        groups.update(cell_runner.telemetry(path))
    words = lambda value: [int(value[index:index+16], 16) for index in range(0, 64, 16)]
    for group in groups.values():
        if group[0]["daemon"] != words(runtime.daemon_instance) or group[0]["scope"] != words(runtime.scope):
            raise ValueError("original numeric daemon/scope differs from authenticated channel")
    totals, priced, correlated = price(groups, runtime.rows, bindings, row.get("counts_scope", "measured command and Commit"),
                                      with_warm_mount="warmup_unmount" in bindings)
    row.update(counts=totals, phase_counts=priced, control_correlation=correlated)
    cell_runner.snapshot_observations(runtime, row["observations"])
    cell_runner.ingest_observations(groups, row["observations"], row["cache"])
    row["cache"]["status"] = cache.validate(row.get("cache_class", "B"), row["cache"])


def operation_deadline(group_stop, seconds):
    stop = time.monotonic() + seconds
    if group_stop is not None:
        if time.monotonic() >= group_stop:
            raise TimeoutError("original edit/Commit/End group watchdog expired")
        stop = min(stop, group_stop)
    return stop


def storage_source_observations(runtime, build, output, seconds):
    """Actual source stat before known Stop; copies never stand in for source."""
    docker = ["docker", "--host", "unix://" + build["socket"]]
    result = {}
    for kind in ("store", "overlay"):
        label = "closed-" + kind + "-source-stat"
        command = receipts.command([*docker, "exec", "--user", "0:0", runtime.container,
            "python3", "-B", "-c", oracle.storage_source_stat_body(kind)], output, label, seconds(15))
        completion = Path(output) / (label + ".completion.json")
        result[kind] = {"completion": str(completion), "completion_sha256": identity.sha256(completion),
                        "stdout": command["stdout"], "stdout_sha256": identity.sha256(command["stdout"])}
    return result


def observe_family_closed_storage(runtime, row, build, output, census_store, custody, source_stats, seconds):
    """Namespace cleanup and shared allocation after actual known terminal Stop."""
    output = Path(output)
    store = oracle.observe_closed_storage(census_store, {**custody, "source_stat": source_stats["store"]}, kind="store")
    docker = ["docker", "--host", "unix://" + build["socket"]]
    overlay_path = output / "closed-overlay.sqlite"
    label = "closed-overlay-export"
    receipts.command([*docker, "cp", runtime.container + ":/layerfs-local/overlay/overlay.sqlite",
                      str(overlay_path)], output, label, seconds(15))
    completion = output / (label + ".completion.json")
    # Every member of the stopped daemon's overlay directory: the template, and the file of any
    # Workspace whose terminal unmount did not delete it.
    listing = receipts.command([*docker, "cp", runtime.container + ":" + oracle.OVERLAY_DIRECTORY, "-"],
                               output, "closed-overlay-directory", seconds(15))
    listed = output / "closed-overlay-directory.completion.json"
    events = output / "runtime.events.jsonl"
    owners = [{"key": event["fields"]["key"], "namespace": event["fields"]["workspace_namespace"],
               "incarnation": event["fields"]["workspace_incarnation"]}
              for event in runtime.rows if event["event"] == "mount"]
    overlay_custody = {"custody": row["custody"], "container": runtime.container, "volume": row["clone"]["volume"],
        "remote_source": "/layerfs-local/overlay/overlay.sqlite", "local_source": str(overlay_path),
        "source_sha256": identity.sha256(overlay_path), "source_size": overlay_path.stat().st_size,
        "export_completion": str(completion), "export_completion_sha256": identity.sha256(completion),
        "runtime_events": str(events), "runtime_events_sha256": identity.sha256(events),
        "source_stat": source_stats["overlay"],
        "directory": {"completion": str(listed), "completion_sha256": identity.sha256(listed),
                      "stdout": listing["stdout"], "stdout_sha256": identity.sha256(listing["stdout"])}}
    overlay = oracle.observe_closed_storage(overlay_path, overlay_custody, kind="overlay", owners=owners)
    record = {"store": store, "overlay": overlay,
        "original_physical_resource_status": "UNAVAILABLE",
        "reason": "a Workspace's overlay file is deleted at terminal unmount, so closed storage holds only the empty template and the count of files left; no allocated/live/superseded/peak bytes of a Workspace and no inferred zero"}
    receipts.write_new(output / "closed-storage-observations.json", record)
    row["closed_storage_observations"] = record
    if (store["source_main_store_4gib_status"] != "PASS" or overlay["namespace_cleanup_status"] != "PASS"
            or overlay["owned_files_after_cleanup_status"] != "PASS"):
        raise ValueError("original main Store boundary or exact Workspace file cleanup failed")
    return record


def footprint_boundary(prepared):
    """Frozen clipped marker oracle from the immutable original native file."""
    fixture=prepared["fixture"]
    size=fixture["edit_size"];path=fixture["edit_path"]
    marker=b"E000000001"
    if type(size) is not int or size<=len(marker) or path.startswith("/") or any(part in ("",".","..") for part in path.split("/")):
        raise ValueError("original footprint selected path/size required")
    offset=2_654_435_761%(size-len(marker))
    start,end=max(0,offset-65536),min(size,offset+len(marker)+65536)
    with (Path(prepared["source"])/path).open("rb") as source:
        if os.fstat(source.fileno()).st_size!=size:
            raise ValueError("original immutable footprint selected file length changed")
        source.seek(start);body=bytearray(source.read(end-start))
    if len(body)!=end-start:
        raise ValueError("original footprint clipped source read was short")
    left,right=max(start,offset),min(end,offset+len(marker))
    body[left-start:right-start]=marker[left-offset:right-offset]
    return {"path":path,"file_size":size,"offset":offset,"start":start,"end":end,
            "sha256":hashlib.sha256(body).hexdigest(),"verified_bytes":end-start}


def verify_native_receipt(case, verified, boundary=None):
    text = Path(verified["fields"]["stdout"]).read_text()
    if case.get("store_footprint_schedule"):
        fields=text.strip().split("\t")
        if (boundary is None or len(fields)!=3 or verified["fields"].get("exit_code")!="0"
                or not fields[0].isdecimal() or int(fields[0])!=boundary["file_size"]
                or fields[1]!=boundary["sha256"] or not fields[2].isdecimal() or int(fields[2])<=0):
            raise ValueError("original freshly mounted footprint size/clipped bytes/inode receipt differs")
        return {"verification_status":"pass","scope":"storage-accounting-reopen-and-edit-boundary-v1",
            **boundary,"inode":int(fields[2]),"full_namespace_verified":False,"full_file_bytes_verified":False}
    if case.get("m1_schedule"):
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:
                    raise ValueError("duplicate native M1 receipt field")
                result[key]=value
            return result
        proof=json.loads(text,object_pairs_hook=unique)
        keys={"case","seed","step","verification_status","scope","scope_digest","created_modes_digest","entries","checked_range_bytes"}
        if (not isinstance(proof,dict) or set(proof)!=keys or verified["fields"].get("exit_code")!="0"
                or proof["case"]!=case["v016_case"] or type(proof["seed"]) is not int or proof["seed"]!=1
                or type(proof["step"]) is not int or proof["step"]!=case["history_schedule"]["commits"]
                or proof["verification_status"]!="pass" or proof["scope"]!="original-m1-selective-scope-v1"
                or any(type(proof[name]) is not int or proof[name]<0 for name in ("entries","checked_range_bytes"))
                or proof["entries"]==0
                or any(not isinstance(proof[name],str) or len(proof[name])!=64
                       or any(char not in "0123456789abcdef" for char in proof[name])
                       for name in ("scope_digest","created_modes_digest"))):
            raise ValueError("exact successful original selective M1 native receipt required")
        return {**proof,"status":"PASS","original_stdout_sha256":hashlib.sha256(text.encode()).hexdigest()}
    if case["v016_case"] == "local-snapshot-create-25000-onebyte-v1":
        paths = [".", *[f"f{i:05}" for i in (0, 1, 97, 194, 12500, 24998, 24999)]]
        omissions = "unselected paths, bytes beyond selected ranges, exhaustive inode/object/reference census, alias and failure injection semantics"
        contract = {"schema": "original-local-snapshot-sample-v1", "sampled_paths": paths,
                    "sampled_ranges": {path: [[0, 1]] for path in paths[1:]}, "absent_paths": [],
                    "full_namespace_verified": False, "full_file_bytes_verified": False, "omissions": omissions}
        expected = ("absent_paths=\nfull_file_bytes_verified=false\nfull_namespace_verified=false\nomissions=" + omissions +
                    "\nsampled_paths=" + "\n".join(paths) + "\nsampled_ranges=" + "\n".join(path + ":0..1" for path in paths[1:]) + "\n")
        if case.get("native_verifier") != contract or verified["fields"].get("exit_code") != "0" or text != expected:
            raise ValueError("original local snapshot sample receipt/selection/successful exit differs")
        return {**contract, "status": "PASS", "original_omissions": omissions,
                "original_stdout_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "scope": "unchanged original bounded native sample; full four-root/public census proof remains separately required"}
    proof = dict(line.split("=", 1) for line in text.splitlines())
    if proof.get("verification_status") != "pass":
        raise ValueError("original complete native verifier refused freshly remounted published root")
    return proof


def history_free_space(output):
    import shutil
    free = shutil.disk_usage(output).free
    if free < 50 * 1024**3:
        raise RuntimeError("smoke free disk reserve")
    return free


def history_resource_guard(runtime, build, output, label, before=None):
    """Original smoke guards in current ownership domains; no mounted payload read."""
    free = history_free_space(output)
    body = """import json,os
from pathlib import Path
def disk(root):
    return sum(os.lstat(Path(base)/name).st_blocks*512 for base,_,files in os.walk(root) for name in files)
cgroup={}
for name in ('cpu.stat','memory.events','memory.stat'):
    for line in Path('/sys/fs/cgroup/'+name).read_text().splitlines():
        key,value=line.split();cgroup[key]=int(value)
for key,name in (('memory_peak','memory.peak'),('memory_current','memory.current'),('swap_current','memory.swap.current')):
    cgroup[key]=int(Path('/sys/fs/cgroup/'+name).read_text())
store=[Path('/layerfs-store/global/store.sqlite'+suffix) for suffix in ('','-wal','-shm','-journal')]
print(json.dumps({'cgroup':cgroup,'spool_allocated_bytes':disk('/layerfs-local'),'staging_allocated_bytes':disk('/code'),
 'store_logical_bytes':sum(p.stat().st_size for p in store if p.exists()),'store_allocated_bytes':sum(p.stat().st_blocks*512 for p in store if p.exists())}))
"""
    docker = ["docker", "--host", "unix://" + build["socket"]]
    observed = receipts.command([*docker, "exec", "--user", "0:0", runtime.container,
                                 "python3", "-B", "-c", body], output, label, 30)
    row = json.loads(Path(observed["stdout"]).read_text())
    row["host_free_bytes"] = free
    row["receipt_allocated_bytes"] = sum(path.stat().st_blocks * 512 for path in Path(output).rglob("*") if path.is_file())
    row["scope"] = "actual own container cgroup; current overlay/local backing and staged helpers; host receipt tree; lifetime peaks diagnostic only"
    for key in ("oom", "oom_kill", "swap_current"):
        if type(row["cgroup"].get(key)) is not int:
            raise ValueError("original smoke resource observation unavailable: " + key)
    if row["cgroup"]["swap_current"] or before and any(row["cgroup"][key] != before["cgroup"][key] for key in ("oom", "oom_kill")):
        raise RuntimeError("container OOM/swap")
    if row["spool_allocated_bytes"] + row["staging_allocated_bytes"] > 16 * 1024**3 or row["receipt_allocated_bytes"] > 32 * 1024**3:
        raise RuntimeError("smoke disk budget")
    if row["store_logical_bytes"] > 16 * 1024**3 or row["store_allocated_bytes"] > 16 * 1024**3:
        raise RuntimeError("storage smoke Store budget")
    return row


def history_container_profile(runtime, build, output):
    """Select the frozen original container profile before any measured work."""
    docker = ["docker", "--host", "unix://" + build["socket"]]
    receipts.command([*docker, "update", "--cpus", "2", "--memory", "2147483648", "--memory-swap", "2147483648", "--pids-limit", "256", runtime.container],
                     output, "history-container-profile", 30)
    observed = receipts.command([*docker, "inspect", runtime.container, "--format", "{{json .HostConfig}}"],
                                output, "history-container-profile-readback", 30)
    config = json.loads(Path(observed["stdout"]).read_text())
    wanted = {"NanoCpus": 2_000_000_000, "Memory": 2_147_483_648, "MemorySwap": 2_147_483_648, "PidsLimit": 256}
    if any(config.get(name) != value for name, value in wanted.items()):
        raise ValueError("original small-delta container resource profile differs")
    return wanted


def ordinary_resource_values(row, before=None):
    """Frozen ordinary main-file/cgroup guards; no substituted peak or pager claim."""
    for name in ("store_main_logical_bytes", "store_main_allocated_bytes", "oom", "oom_kill", "swap_current"):
        if type(row.get(name)) is not int or row[name] < 0:
            raise ValueError("original ordinary resource observation unavailable: " + name)
    if any(row[name] > 4 * 1024**3 for name in ("store_main_logical_bytes", "store_main_allocated_bytes")):
        raise RuntimeError("sample Store exceeds frozen 4 GiB bound")
    if row["swap_current"] or before and any(row[name] != before[name] for name in ("oom", "oom_kill")):
        raise RuntimeError("original ordinary container OOM/swap")
    return row


def ordinary_resource_guard(runtime, build, output, label, before=None, seconds=15):
    """Observe only the actual sample's backing stat/cgroup outside product time."""
    from . import resource_exec
    attempted = resource_exec.command(build['socket'], runtime.container, output, label, seconds)
    row = json.loads(Path(attempted["stdout"]).read_text())
    row["scope"] = "original 4GiB main Store apparent/allocated bound; actual own container OOM/swap; retired host Store RSS/physical-spool peak not asserted"
    return ordinary_resource_values(row, before)


def original_operation_counts(command, wanted):
    """Check retained frozen semantic work counters without replaying any work."""
    if command is None:
        raise ValueError("original operation counters require the acknowledged workload")
    lines = Path(command["fields"]["stdout"]).read_text().splitlines()
    found = {}
    for name, value in wanted.items():
        matches = [line.partition("=")[2] for line in lines if line.partition("=")[0] == name]
        if (type(value) is not int or value < 0 or len(matches) != 1
                or not matches[0].isascii() or not matches[0].isdigit() or int(matches[0]) != value):
            raise ValueError("original measured workload semantic count differs: " + name)
        found[name] = value
    return found


def git_custody_values(body, fields):
    """Validate the complete frozen repository seal, including raw index SHA."""
    lines = body.decode("utf-8").splitlines()
    if not lines or lines.pop(0) != "workspace-independent-manifest-v1":
        raise ValueError("original Git custody manifest header differs")
    paths, logical = [], 0
    for row in lines:
        columns = row.split("\t")
        if len(columns) != 7:
            raise ValueError("original Git custody requires seven columns")
        path, kind, length, mode, seconds, nanos, digest = columns
        if path != "." and (not (path == ".git" or path.startswith(".git/"))
                or any(part in ("", ".", "..") for part in path.split("/"))):
            raise ValueError("original Git custody path outside .git")
        if (kind not in ("file", "directory") or not length.isascii() or not length.isdigit()
                or not mode or any(value not in "01234567" for value in mode)
                or not seconds.lstrip("-").isascii() or not seconds.lstrip("-").isdigit()
                or not nanos.isascii() or not nanos.isdigit() or not 0 <= int(nanos) < 1_000_000_000):
            raise ValueError("original Git custody kind/metadata differs")
        if kind == "directory" and (length != "0" or digest != "-"):
            raise ValueError("original Git custody directory content differs")
        if kind == "file":
            if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
                raise ValueError("original Git custody requires complete SHA-256")
            logical += int(length)
        paths.append(path)
    if (paths != sorted(set(paths)) or paths[:2] != [".", ".git"]
            or ".git/index" not in paths or logical > 256 * 1024**2
            or fields.get("repository_manifest_sha256") != hashlib.sha256(body).hexdigest()
            or fields.get("repository_path_count") != str(len(paths) - 1)):
        raise ValueError("original complete Git custody identity/count/bound differs")
    return {"manifest_sha256": hashlib.sha256(body).hexdigest(), "repository_paths": len(paths)-1,
            "repository_logical_bytes": logical, "index_stat_bytes": "complete raw index bytes covered by SHA-256, not tuple substitution"}


def _capture_git_custody(runtime, selected, prepared, build, output, label, seconds):
    if (prepared.get("family") != "git_tool_workflow" or not prepared.get("git_reference")
            or prepared["git_reference"].get("case") != prepared.get("case")):
        raise ValueError("explicit qualified frozen Git workflow preparation required")
    if seconds <= 0 or seconds > 59:
        raise ValueError("bounded original Git custody proof allowance required")
    folder = Path(output) / label
    folder.mkdir(parents=True, exist_ok=False)
    stop = time.monotonic() + seconds
    inside = "/tmp/layerfs-fsb-" + label + "-" + uuid.uuid4().hex + ".tsv"
    body = "exec /code/writers/workload workspace-git-custody-out " + shlex.quote(inside)
    event = runtime.send("verify", selected, script(folder, "capture.sh", body), deadline=stop)
    fields = dict(line.split("=", 1) for line in Path(event["fields"]["stdout"]).read_text().splitlines())
    left = stop - time.monotonic()
    if left <= 0:
        raise TimeoutError("original Git custody proof allowance expired")
    path = folder / "repository.tsv"
    receipts.command(["docker", "--host", "unix://" + build["socket"], "cp", runtime.container + ":" + inside, str(path)],
                     folder, "export", min(15, left))
    values = git_custody_values(path.read_bytes(), fields)
    path.chmod(0o444)
    witness = {"schema": "fs-bench-pro-original-git-custody-v1", "status": "PASS", "case": prepared["case"],
               "mount_key": selected, "path": str(path), "values": values, "capture": event,
               "reference": prepared["git_reference"],
               "scope": "original complete .git names/kinds/modes/mtime/lengths/full SHA, index stat bytes included; read-only mounted observer, no Git command or mounted write"}
    receipts.write_new(folder / "custody.json", witness)
    receipts.manifest(folder)
    return witness


def before_git_commit(runtime, selected, prepared, build, output, seconds):
    """One excluded mounted observer immediately before the one measured Commit."""
    return _capture_git_custody(runtime, selected, prepared, build, output, "git-precommit", seconds)


def verify_git_custody(runtime, verify_mount, prepared, build, output, prior, seconds):
    """Fresh published-root parity BEFORE any semantic Git command can edit index."""
    receipts.verify_manifest(Path(prior["path"]).parent)
    if prior.get("case") != prepared.get("case") or identity.sha256(prior["path"]) != prior["values"]["manifest_sha256"]:
        raise ValueError("precommit Git custody source identity differs")
    fresh = _capture_git_custody(runtime, verify_mount, prepared, build, output, "git-reopened", seconds)
    if Path(prior["path"]).read_bytes() != Path(fresh["path"]).read_bytes():
        raise ValueError("original complete precommit/reopened Git custody mismatch")
    return {"status": "PASS", "precommit": prior, "reopened": fresh,
            "scope": "exact full manifest equality; all .git bytes/metadata including raw index stat-cache retained before semantic verification"}


def verify_git_semantic_fields(proof, prepared):
    """Require every frozen native Git proof field, independently prepared IDs."""
    bundle = Path(prepared["helpers"]["root"]) / "git-reference"
    for name in ("head", "tree", "parent"):
        wanted = (bundle / ("expected-" + name)).read_text().strip()
        if proof.get("git_" + name) != wanted:
            raise ValueError("original independent Git semantic identity differs: " + name)
    if (proof.get("verification_status") != "pass" or proof.get("git_semantic_verification_status") != "pass"
            or proof.get("git_custody_status") != "requires_precommit_reopen_comparison"):
        raise ValueError("original Git semantic/fsck/clean/two-commit proof missing")
    return {"status": "PASS", "head": proof["git_head"], "tree": proof["git_tree"], "parent": proof["git_parent"],
            "scope": "original verify_git performed exact HEAD/tree/parent, fsck--strict, clean status, exactly2Gitcommits and complete independent working source"}


def verify_git_qualification(command, case):
    """Original intermediate mounted guards run once outside performance time."""
    if not case.get("git_workflow") or not case.get("git_qualification"):
        raise ValueError("explicit original Git prior verification variant required")
    wanted = {**case["original_operation_counts"], "benchmark_verifier_count": 1}
    found = original_operation_counts(command, wanted)
    lines = Path(command["fields"]["stdout"]).read_text().splitlines()
    if lines.count("workload_status=pass") != 1 or lines.count("scenario_id="+case["v016_case"]) != 1 or lines.count("seed=1") != 1:
        raise ValueError("original mounted Git verification-variant identity/status differs")
    return {"status": "PASS", "counts": found,
            "scope": "unchanged original verify variant: exact first-status paths/statuses, native reference tracked diff bytes/membership and alternating temporary-save readback/rename absence; prior mounted original genesis, discarded without Commit"}


def git_proof_deadlines(case, charged_ns):
    """Frozen ordinary work/cleanup/publication policy, cumulative across proofs."""
    if (not case.get("git_workflow") or type(charged_ns) is not int or charged_ns < 0
            or case["budget"]["verifier_ms"] != 45000
            or case["budget"]["verification_hard_watchdog_ms"] != 59000):
        raise ValueError("original Git 45s work/4s cleanup reserve/59s hard policy required")
    now = time.monotonic()
    return {"work": now+41-charged_ns/1e9, "cleanup": now+45-charged_ns/1e9,
            "publication": now+59-charged_ns/1e9}


def history_observer(clock, row, label, action):
    """Retain raw observer wall and exclude it even when a resource guard fails."""
    started = time.monotonic_ns()
    clock.begin_verifier(started)
    try:
        return action()
    finally:
        ended = time.monotonic_ns()
        clock.end_verifier(ended)
        row.setdefault("observer_intervals", []).append({"label": label, "start_monotonic_ns": started,
            "end_monotonic_ns": ended, "complete_wall_ns": ended-started,
            "scope": "read-only original observer/verifier; excluded from product time, included in the applicable original absolute watchdog"})


def qualify_history_mechanism(proofs):
    """Frozen existence condition, separate from byte/history proof and quotas."""
    known = all(type(item.get("fields", {}).get("payload_dependency_records")) is int
                and item["fields"]["payload_dependency_records"] >= 0
                and type(item["fields"].get("payload_objects")) is int
                and item["fields"]["payload_objects"] > 0 for item in proofs)
    if len(proofs) != 31 or not known:
        return {"status": "FAIL", "reason": "original actual payload DELTA-path evidence unavailable",
                "semantic_proof_status": "PASS", "payload_dependency_record_observations": "UNAVAILABLE"}
    count = sum(item["fields"]["payload_dependency_records"] for item in proofs)
    return {"status": "PASS" if any(item["fields"]["payload_dependency_records"] for item in proofs) else "FAIL",
            "reason": "authenticated selected payload dependency reconstruction observed" if count else
                      "original actual payload DELTA-path condition unmet: all selected payload records FULL",
            "semantic_proof_status": "PASS", "payload_dependency_record_observations": count,
            "scope": "existence only; per-state/file observations may repeat content IDs; no count/percentage/storage/latency quota; retired schema10 counters N/A"}


def exhaustive_owner_ceiling(case):
    """Only the named large verification invocation gets the expanded ceiling."""
    large = case.get("v016_case") == "v016-mixed-exhaustive-500mb-30000-k100-v1"
    expected = 275000 if large else 120000
    if case.get("owner_test_ceiling_ms") != expected:
        raise ValueError("exact exhaustive owner ceiling required")
    if large and (case.get("historical_owner_test_ceiling_ms") != 120000
            or (case["budget"]["verifier_ms"],case["budget"]["verification_hard_watchdog_ms"]) != (300000,310000)):
        raise ValueError("large exhaustive exception retains its original proof declaration")
    return expected


def family_proof_deadlines(case, charged_ns=0, owner_stop=None):
    """Original work/reserve/publication limits, with separate owner test ceiling."""
    if case.get("git_workflow"):
        return git_proof_deadlines(case, charged_ns)
    if case.get("reuse_schedule") or case.get("store_footprint_schedule"):
        expected = "original-dedup-workspace-reuse-v1" if case.get("reuse_schedule") else "original-store-footprint-init-edit-v1"
        if (case.get("reuse_schedule") or case.get("store_footprint_schedule")).get("schema")!=expected:
            raise ValueError("exact original storage schedule required")
        return import_proof_deadlines(case, charged_ns)
    if (case.get("history_schedule", {}).get("schema") not in BATCH4_HISTORY_SCHEMAS
            and case.get("registry",{}).get("family") not in BATCH4_FAMILIES):
        return None
    if type(charged_ns) is not int or charged_ns < 0:
        raise ValueError("nonnegative original charged proof wall required")
    budget = case["budget"]
    work, hard = budget["verifier_ms"], budget["verification_hard_watchdog_ms"]
    if case.get("proof_only"):
        if work not in (120000, 300000) or hard != work + 10000:
            raise ValueError("original exhaustive declaration required")
        exhaustive_owner_ceiling(case)
        reserve = budget.get("verification_cleanup_reserve_ms", 3000)
    else:
        named = LARGE_ROOT_PROOF_LIMITS.get(case.get("id"))
        if (work, hard) not in ((named,) if named else ((25000,35000),(45000,59000))):
            raise ValueError("original history verification limits required")
        reserve = budget.get("cleanup_reserve_ms", budget.get("verification_cleanup_reserve_ms", 4000 if work==45000 else 3000))
    if reserve != (4000 if work==45000 else 3000) or budget.get("publication_guard_ms",250) != 250:
        raise ValueError("original history cleanup reserve and publication guard required")
    now = time.monotonic()
    result = {"work":now+(work-reserve)/1000-charged_ns/1e9,
              "cleanup":now+work/1000-charged_ns/1e9,
              "publication":now+hard/1000-charged_ns/1e9}
    if owner_stop is not None:
        result = {name:min(stop,owner_stop) for name,stop in result.items()}
        result["work"]=min(result["work"],owner_stop-reserve/1000)
    return result


def history_transcript(case, prepared, history):
    """Bind every acknowledgement, but only original selected payload manifests."""
    count = case["history_schedule"]["commits"]
    if len(history["commits"]) != count or [item["index"] for item in history["commits"]] != list(range(1,count+1)):
        raise ValueError("all original ordered Commit acknowledgements required")
    selected = (fixtures.history_verification_steps(case) if case["history_schedule"].get("schema") in BATCH4_HISTORY_SCHEMAS
                else list(range(count+1)))
    states = {item["index"]:item for item in prepared["history_states"]}
    if len(states) != len(prepared["history_states"]) or sorted(states) != selected:
        raise ValueError("exact original selected checkpoint manifests required")
    manifest = lambda index: states[index]["manifest"] if index in states else "-"
    rows = [f"0\t-\t-\t{history['initial_root']}\t{manifest(0)}"]
    seen, previous = set(), "-"
    for record in history["commits"]:
        fields = record["commit"]["fields"]
        commit_id = fields["commit_id"]
        if commit_id in seen or fields["parent"] != previous:
            raise ValueError("original Commit IDs must be unique with exact predecessor parents")
        seen.add(commit_id);previous=commit_id
        rows.append(f"{record['index']}\t{commit_id}\t{fields['parent']}\t{fields['root']}\t{manifest(record['index'])}")
    return "\n".join(rows)+"\n", selected


def m1_created_modes(command, prior):
    """Use original measured helper observations, never setup/default modes."""
    if command["fields"].get("exit_code") != "0":
        raise ValueError("successful original M1 helper required for created modes")
    lines = Path(command["fields"]["stdout"]).read_text().splitlines()
    values = [line[len("m1_created_directory_modes="):] for line in lines if line.startswith("m1_created_directory_modes=")]
    if len(values) != 1:
        raise ValueError("one original M1 created-directory observation required")
    result, seen = dict(prior), set()
    for item in values[0].split(",") if values[0] else []:
        columns = item.split(":")
        if len(columns) != 2:
            raise ValueError("original M1 mode observation geometry differs")
        path, mode = columns
        if (not path or path in seen or any(part in ("", ".", "..") for part in path.split("/"))
                or any(char.isspace() for char in path) or not mode or any(char not in "01234567" for char in mode)
                or int(mode,8) > 0o777):
            raise ValueError("unsafe/duplicate original M1 created-directory mode")
        seen.add(path);result[path]=int(mode,8)
    return result


def operation_commit_expectation(case, index):
    """Select the actual mutation declaration; Init is a separate operation."""
    if case.get("store_footprint_schedule"):
        mutations = [step for step in case["steps"] if step.get("run") and step.get("commit")]
        if (index != 1 or len(mutations) != 1
                or mutations[0].get("expected_commit") != "Committed"
                or case["store_footprint_schedule"].get("expected_commit") != "Committed"):
            raise ValueError("original footprint requires exactly one declared Committed mutation")
        return mutations[0]["expected_commit"]
    value = case["steps"][index-1].get("expected_commit")
    if value is None:
        value = case.get("expected_commit")
    if value not in ("Committed", "UpToDate"):
        raise ValueError("explicit original Commit outcome required")
    return value



def commit_deadline(case, overall, ordinary_seconds):
    """Owner D-4: only Commit consumes the capped two-second watchdog."""
    cap = case["budget"].get("commit_watchdog_ms")
    if cap is not None:
        if (case.get("registry", {}).get("family") != "edit_length_changing_capped"
                or cap != 2000 or case["budget"].get("historical_edit_commit_end_watchdog_ms") != 2000):
            raise ValueError("D-4 requires the exact capped Commit-only2000ms declaration")
        ordinary_seconds = cap / 1000
    return operation_deadline(overall, ordinary_seconds)


def one_family_case(family, case, prepared_folder, build_folder, output, *, preparation_only=False):
    """Single ordinary call/Commit through the same SDK/Sandbox machinery."""
    if case.get('historical_access'):
        if preparation_only:
            raise ValueError('historical reader cannot substitute for a producer setup')
        return one_access_case(family, case, prepared_folder, build_folder, output)
    if case.get("branch_schedule") or case.get("topology_schedule"):
        return one_context_case(family, case, prepared_folder, build_folder, output,
                                preparation_only=preparation_only)
    started_test_ns = time.monotonic_ns()
    current = identity.source_identity()
    build = identity.load_build(build_folder)
    prepared = fixtures.load(prepared_folder, case["fixture"]["recipe"])
    helper_admission = fixtures.validate_runtime_helpers(case,prepared,build)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    ordered = bool(case.get("history_schedule"))
    small_history = ordered and case["v016_case"] == "small-file-delta-10x30-v1"
    recipe_history = case.get("history_schedule", {}).get("schema") in BATCH4_HISTORY_SCHEMAS
    batch4 = family in BATCH4_FAMILIES
    proof_only = case.get("proof_only") is True
    reuse = case.get("reuse_schedule")
    footprint = case.get("store_footprint_schedule")
    if reuse and (family!="dedup_workspace_reuse" or reuse.get("schema")!="original-dedup-workspace-reuse-v1"
                  or reuse.get("commits")!=1 or reuse.get("verification_states")!=[0,1]):
        raise ValueError("exact original single-Commit reuse schedule required")
    if footprint and (family!="store_footprint" or footprint.get("schema")!="original-store-footprint-init-edit-v1"
                      or prepared["schema"]!="fs-bench-pro-prepared-native-footprint-v1"):
        raise ValueError("exact original fresh Init/edit footprint preparation required")
    if footprint:
        operation_commit_expectation(case, 1)
    owner_ceiling_ms = exhaustive_owner_ceiling(case) if proof_only else None
    owner_stop = started_test_ns/1_000_000_000+owner_ceiling_ms/1000 if proof_only else None
    body = None if case.get("control_only") else "/bin/bash /code/workload.sh apply " + shlex.quote(case["v016_case"])
    if footprint:
        body += " "+shlex.quote(prepared["fixture"]["edit_path"])
    bodies = ["/bin/bash /code/" + prepared.get("prepared_step_runs",{}).get(str(index),step["run"])
              for index,step in enumerate(case["steps"],1)] if ordered else [body]
    if ordered and (len(bodies) != case["history_schedule"]["commits"] or any(not step.get("commit") for step in case["steps"])):
        raise ValueError("original ordered history requires all declared saves and Commits")
    treatment = {"family": family, "case": case, "fixture": prepared["fixture"]["fixture_sha256"],
                 "product": current["product_tree"], "body": bodies, "helpers": prepared["helpers"]["files"],
                 "binaries": {name: row["sha256"] for name, row in build["binaries"].items()},
                 "engine": identity.sha256(__file__), "image": identity.IMAGE}
    key = receipts.sample_claim_key(treatment, current["source_commit"])
    claims = identity.ROOT / "benchmark-results/fs-bench-pro/claims"
    claims.mkdir(parents=True, exist_ok=True)
    if not preparation_only:
        with (claims / key).open("x") as stream:
            stream.write(str(output) + "\n")
    row = {"schema": "fs-bench-pro-workspace-family-v1", "family": family, "case": case["id"],
           "source_commit": current["source_commit"], "product_tree": current["product_tree"], "identity": current,
           "build": str(Path(build_folder).resolve()), "prepared": str(Path(prepared_folder).resolve()),
           "daemon_sha256": build["binaries"]["daemon"]["sha256"], "runtime_sha256": build["binaries"]["runtime"]["sha256"],
           "image": identity.IMAGE, "status": "NOT_RUN", "proof_status": "NOT_RUN", "counts": {}, "phases": {},
           "observations": {}, "cache_class": case.get("cache_class", "B"), "cache": {"class": case.get("cache_class", "B")}, "cleanup": "UNAVAILABLE",
           "declared_limit_ns": case["budget"]["command_ms"] * 1_000_000 if case["budget"]["command_ms"] is not None else "N/A",
           "verifier_limit_ns": case["budget"]["verifier_ms"] * 1_000_000,
           "global_profile": "Disposable/WAL/OFF", "overlay_profile": "MEMORY/OFF/EXCLUSIVE", "construction_workers": 1,
           "durable": "NOT_RUN — disabled by owner until explicit reauthorization", "claim": key,
           "attempted_operation_count": 0, "completed_operation_count": 0, "sample_count": 0,
           "verification_attempt_count":1 if proof_only else 0,
           "interference": current.get("cross_worktree_interference","shared host/Docker VM/protected and own failed services, unquantified"),
           "proof_only": proof_only, "performance_mode":"verification-only" if proof_only else "single original performance attempt",
           "performance_declaration":case.get("performance_mode","single original performance attempt"),
           "owner_test_ceiling_ns":owner_ceiling_ms*1_000_000 if proof_only else None}
    row["helper_admission"]=helper_admission
    if preparation_only:
        row.update(schema="fs-bench-pro-prepared-producer-attempt-v1", setup_only=True,
                   sample_count=0, performance_mode="setup-only; no performance sample",
                   declared_limit_ns="N/A")
    receipts.write_new(output / "selection.json", row)
    runtime = None
    host_observer = None
    fresh_init_handle = None
    mounted = set()
    bindings = {}
    clock = cell_runner.PerformanceClock()
    proof_started = None
    preproof_ns = 0
    publication_stop = None
    proof_cleanup_stop = None
    proof_deadlines = None
    created_modes = {}
    final_modes = None
    try:
        if footprint:
            from . import project
            row.update(attempted_operation_count=1,sample_count=1)
            clock.begin(time.monotonic_ns())
            fresh_init_handle = project.fresh_init_start(case, prepared, build, output, row,
                deadline=clock.started/1e9+120, host_rss_limit_bytes=None)
            acknowledged = fresh_init_handle["ack"]
            if any(acknowledged["fields"][name]>4*1024**3 for name in ("logical_bytes","allocated_bytes")):
                raise RuntimeError("original initialized main Store exceeds4GiB")
            row["initialization"] = {"ack": acknowledged,
                "complete_wall_ns": fresh_init_handle["init_complete_wall_ns"],
                "scope": "measured original fresh public directory Init plus current Store/main Branch/seal; exact actual SealedProject retained for one public install"}
            row["phases"]["init_ns"] = acknowledged["span"]["duration_ns"]
            provision = project.fresh_init_finish(fresh_init_handle, row, deadline=clock.started/1e9+120)
            prepared = {**prepared, "provision": provision}
            row["initialization"]["installation"] = provision
        if reuse:
            import shutil
            initial_store = output/"pristine-store.sqlite"
            shutil.copy2(prepared["provision"]["sealed_store"], initial_store)
            if identity.sha256(initial_store)!=prepared["provision"]["store_sha256"]:
                raise ValueError("pristine initial attribution copy differs from sealed master")
            initial_events = output/"pristine.events.jsonl"
            initial_args = [build["binaries"]["runtime"]["path"],"verify-reuse-initial","--socket",build["socket"],
                "--volume","unused-pristine-observer","--daemon",build["binaries"]["daemon"]["path"],
                "--manifest",prepared["provision"]["manifest"],"--sealed",str(initial_store),
                "--case",case["v016_case"],"--receipt",str(initial_events),
                "--uid",str(prepared["source_uid"]),"--gid",str(prepared["source_gid"])]
            initial = receipts.command(initial_args,output,"pristine-payload-attribution",41,
                environment={**os.environ,"LAYERFS_CONSTRUCTION_WORKERS":"1"})
            initial_rows = [json.loads(line) for line in initial_events.read_text().splitlines()]
            proved = [event for event in initial_rows if event["event"]=="reuse_initial_verified"]
            if len(proved)!=1 or proved[0]["fields"].get("status")!="PASS" or initial_rows[-1]["event"]!="finished":
                raise ValueError("complete original pristine public payload attribution required")
            row["pristine_payload_attribution"] = {"attempt":initial,"proof":proved[0],
                "scope":"separate exact sealed-master copy before original fresh measured mount; structural input reads outside paid product timer; charged independent proof, no cold claim"}
            preproof_ns += initial["complete_wall_ns"]
        if not footprint:
            row["clone"] = fixtures.clone(prepared, output / "clone", build)
        environment = output / "environment.txt"
        environment.write_text("".join(name + "=" + value + "\n" for name, value in workloads.ENV.items()))
        argv = [build["binaries"]["runtime"]["path"], "serve", "--socket", build["socket"],
                "--volume", row["clone"]["volume"], "--daemon", build["binaries"]["daemon"]["path"],
                "--manifest", prepared["provision"]["manifest"], "--receipt", str(output / "runtime.events.jsonl"),
                "--uid", str(prepared["source_uid"]), "--gid", str(prepared["source_gid"]),
                "--environment-file", str(environment), "--observation-scope", secrets.token_hex(32)]
        if ordered:
            argv.extend(["--case", case["v016_case"]])
        runtime = cell_runner.EventProcess(argv, output, "runtime")
        if footprint:
            host_observer = receipts.HostProcessObserver(runtime.process, output, "footprint-host", None)
            host_observer.check()
        runtime.event("protocol_ready", time.monotonic() + 15)
        row["container"] = runtime.container
        if runtime.container is None:
            raise ValueError("original container acknowledgement unavailable")
        if ordered or footprint or case.get("original_ordinary_guards"):
            row["container_profile"] = history_container_profile(runtime, build, output)
        row["staging"] = fixtures.stage(runtime.container, prepared, output / "staging", build)
        if footprint or case.get("original_ordinary_guards"):
            row["ordinary_resource_guards"] = {"before": ordinary_resource_guard(runtime, build, output, "ordinary-resources-before"), "steps": []}
        if ordered:
            if small_history:
                row["resource_guards"] = {"before": history_resource_guard(runtime, build, output, "history-resources-before"), "steps": []}
            row["cache"].update(same_mount=True, warm_interval_ns=None,
                declaration="one original Workspace for all declared saves/Commits; setup and prior own-write cache uncontrolled; no warmup Commit or independent coldness proof")
            row["history"] = {"initial_root": next(event for event in runtime.rows if event["event"] == "history_initial_root")["fields"]["root"], "commits": []}
        elif reuse or footprint:
            row["cache"].update(fresh_mount=True, warmup_performed=False,
                declaration="one original fresh measured mount; no warmup workload or Commit; prepared clone and pristine structural observer warmth remain INELIGIBLE")
        else:
            warm = secrets.token_hex(32)
            git_proof_start = time.monotonic_ns() if case.get("git_workflow") else None
            git_deadlines = git_proof_deadlines(case, preproof_ns) if git_proof_start is not None else None
            git_proof_stop = git_deadlines["work"] if git_deadlines else None
            git_cleanup_stop = git_deadlines["cleanup"] if git_deadlines else None
            if git_deadlines:
                publication_stop = git_deadlines["publication"]
                row["git_proof_policy"] = {"work_limit_seconds": 45, "cleanup_reserve_seconds": 4,
                    "hard_limit_seconds": 59, "publication_guard_seconds": .25,
                    "scope": "cumulative prior qualification, precommit custody and final proof; required early mount cleanup/Stop/export also charged, measured performance interval excluded"}
            try:
                runtime.send("mount", warm, deadline=operation_deadline(git_proof_stop, 15))
                mounted.add(warm)
                if case.get("git_workflow"):
                    qualification_body = "/bin/bash /code/" + case["git_qualification"]["run"]
                    qualified = runtime.send("command", warm, script(output, "prior-qualification.sh", qualification_body),
                                             deadline=operation_deadline(git_proof_stop, case["budget"]["verifier_ms"]/1000))
                    row["git_prior_qualification"] = {"command": qualified, "proof": verify_git_qualification(qualified, case),
                        "disposition": "original mounted verification variant; End without Commit discards changes before exact performance variant"}
                elif body is not None:
                    runtime.send("command", warm, script(output, "warmup.sh", body), deadline=time.monotonic() + 120)
                warm_end = runtime.send("unmount", warm, deadline=operation_deadline(git_cleanup_stop, 15))
                mounted.remove(warm)
                cleanup_seconds = 5 if git_cleanup_stop is None else min(5, git_cleanup_stop-time.monotonic())
                if cleanup_seconds <= 0:
                    raise TimeoutError("original Git prior qualification watchdog expired before cleanup")
                row["warmup_cleanup"] = readiness(runtime, warm, cleanup_seconds)
            finally:
                if git_proof_start is not None:
                    preproof_ns += time.monotonic_ns()-git_proof_start
                    publication_stop = git_proof_deadlines(case, preproof_ns)["publication"]
                    row["prior_proof_wall_ns"] = preproof_ns
                    row["proof_status"] = "FAIL"
            bindings["warmup_unmount"] = endpoint(warm_end)
            row["cache"].update(fresh_mount=True, warmup_terminal_unmount=True, warmup_cleanup="Gone",
                                declaration=("prior read-only mount ended without Exec; fresh measured connection; setup warmth declared; no cold claim" if body is None else
                                             "same untimed ordinary workload on prior mount, then terminal cleanup; fresh measured connection; setup warmth declared; no cold claim"))
            if case.get("git_workflow"):
                row["cache"].update(identical_warmup=False,
                    declaration="prior original verification variant includes additional verifier reads and ends without Commit; measured performance variant unchanged; identical-body/cache qualification unavailable")
        selected = secrets.token_hex(32)
        if not footprint:
            clock.begin(time.monotonic_ns())
        phase_started = time.monotonic()
        row.update(attempted_operation_count=1, sample_count=0 if proof_only or preparation_only else 1,
                   verification_attempt_count=1 if proof_only else 0)
        mount = runtime.send("mount", selected, deadline=time.monotonic() + 15)
        mounted.add(selected)
        if footprint:
            initial=row["initialization"]["ack"]["fields"]
            bound=oracle._manifest_identity(Path(prepared["provision"]["manifest"]))
            if (mount["fields"].get("root")!=initial["root"] or mount["fields"].get("head")!="-"
                    or mount["fields"].get("stack")!=initial["stack"] or mount["fields"].get("branch_id")!=bound["branch_id"]):
                raise ValueError("fresh footprint mount differs from exact measured Init/root/first Branch")
        bindings["measured_mount_attach"] = endpoint(mount)
        row["phases"]["mount_ns"] = mount["span"]["duration_ns"]
        row["commit_watchdog"] = {"watchdog_ms": case["budget"].get("commit_watchdog_ms"),
                                  "scope": "Commit only; ordinary command and unmount watchdogs unchanged"}
        operation_seconds = min(120,case["budget"].get("operation_watchdog_ms", 120000) / 1000)
        phase_stop = (phase_started if recipe_history else time.monotonic()) + case["budget"].get("performance_hard_watchdog_ms", case["budget"]["command_ms"]) / 1000 if ordered else None
        if footprint:
            phase_stop=clock.started/1e9+case["budget"]["performance_hard_watchdog_ms"]/1000
        if owner_stop is not None:
            phase_stop = min(phase_stop,owner_stop)
        row["phases"].update(command_ns=row["phases"].get("init_ns",0), commit_ns=0)
        for index, command_body in enumerate(bodies, 1):
            if small_history:
                history_observer(clock, row, f"free-space-before-state-{index}", lambda: history_free_space(output))
            step_started = time.monotonic_ns()
            step_stop = operation_deadline(phase_stop, operation_seconds) if ordered else None
            command = None
            if command_body is not None:
                command = runtime.send("command", selected, script(output, f"command-{index}.sh" if ordered else "command.sh", command_body),
                                       deadline=operation_deadline(step_stop, operation_seconds))
                row["phases"]["command_ns"] += command["span"]["duration_ns"]
            if case.get("original_operation_counts"):
                row["original_operation_counts"] = history_observer(clock, row, f"original-operation-counts-{index}",
                    lambda: original_operation_counts(command, case["original_operation_counts"]))
            if ordered and case["steps"][index-1].get("original_operation_counts"):
                checked = history_observer(clock,row,f"original-step-operation-counts-{index}",
                    lambda:original_operation_counts(command,case["steps"][index-1]["original_operation_counts"]))
                row.setdefault("original_step_operation_counts",[]).append({"index":index,"counts":checked})
            if case.get("m1_schedule"):
                def capture_modes():
                    values = m1_created_modes(command,created_modes)
                    path = script(output,f"m1-created-modes-{index}.tsv","".join(f"{path}\t{mode:o}\n" for path,mode in sorted(values.items())))
                    return values,{"index":index,"path":str(path),"sha256":identity.sha256(path),
                        "helper_stdout":command["fields"]["stdout"],"helper_stdout_sha256":identity.sha256(command["fields"]["stdout"])}
                created_modes,final_modes = history_observer(clock,row,f"original-created-modes-{index}",capture_modes)
                row.setdefault("created_mode_prefixes",[]).append(final_modes)
            if case.get("automatic_parent_mtime") and index == 5:
                row["automatic_parent_mtime_custody"] = history_observer(clock,row,"original-alias-parent-custody",
                    lambda: alias_parent_custody(case,prepared,command,output))
            if footprint or case.get("original_ordinary_guards"):
                row["ordinary_resource_guards"]["steps"].append(history_observer(clock, row, f"ordinary-before-commit-{index}",
                    lambda: ordinary_resource_guard(runtime, build, output, f"ordinary-resources-before-commit-{index}", row["ordinary_resource_guards"]["before"],operation_deadline(phase_stop,15)-time.monotonic())))
            if case.get("git_workflow"):
                custody_start = time.monotonic_ns()
                try:
                    deadlines = git_proof_deadlines(case, preproof_ns)
                    publication_stop = deadlines["publication"]
                    seconds = deadlines["work"]-time.monotonic()
                    row["git_precommit"] = history_observer(clock, row, "git-precommit-custody-proof",
                        lambda: before_git_commit(runtime, selected, prepared, build, output, seconds))
                finally:
                    preproof_ns += time.monotonic_ns()-custody_start
                    publication_stop = git_proof_deadlines(case, preproof_ns)["publication"]
                    row["prior_proof_wall_ns"] = preproof_ns
                if preproof_ns >= 41_000_000_000:
                    raise TimeoutError("original cumulative Git proof work allowance exhausted before measured Commit")
                row["counts_scope"] = "measured Git command, excluded precommit custody verifier FUSE/SQL work and Commit; only original Status observer adjusted; no guessed verifier subtraction"
            row["cache"]["commit_started_monotonic_ns"] = time.monotonic_ns()
            committed = runtime.send("commit", selected, deadline=commit_deadline(case, step_stop, operation_seconds))
            row["phases"]["commit_ns"] += committed["span"]["duration_ns"]
            row["commit"] = committed
            expected_kind = operation_commit_expectation(case, index) if ordered or footprint else case["expected_commit"]
            if committed["fields"]["commit_kind"] != expected_kind:
                raise ValueError("original known Commit outcome differs from frozen mutation/read-only case")
            if footprint or case.get("original_ordinary_guards"):
                row["ordinary_resource_guards"]["steps"].append(history_observer(clock, row, f"ordinary-after-commit-{index}",
                    lambda: ordinary_resource_guard(runtime, build, output, f"ordinary-resources-after-commit-{index}", row["ordinary_resource_guards"]["before"],operation_deadline(phase_stop,15)-time.monotonic())))
            if ordered:
                record = {"index": index, "command": command, "commit": committed,
                          "step_wall_ns": time.monotonic_ns() - step_started}
                row["history"]["commits"].append(record)
                if small_history:
                    row["resource_guards"]["steps"].append(history_observer(clock, row, f"resources-step-{index}",
                        lambda: history_resource_guard(runtime, build, output, f"history-resources-step-{index}",
                                                        row["resource_guards"]["before"])))
        row["cache"].update(has_own_write_input=committed["fields"]["commit_kind"] == "Committed",
                            own_write_cold_observation=None,
                            own_write_cache_reason="no independent pre-Commit cold backing/metadata observation; own-write warmth is not eligible")
        runtime.send("snapshot", selected, deadline=operation_deadline(phase_stop, 15))
        bindings["command_end_status"] = endpoint(next(event for event in reversed(runtime.rows) if event["event"] == "workspace_status"))
        end = runtime.send("unmount", selected, deadline=operation_deadline(phase_stop, 15))
        mounted.remove(selected)
        row["phases"]["unmount_ns"] = end["span"]["duration_ns"]
        clock.finish(time.monotonic_ns())
        row["complete_wall_ns"] = clock.observe(time.monotonic_ns())["performance_ns"]
        row["performance_clock"] = clock.observe(time.monotonic_ns())
        row["cleanup_observations"], row["cache"]["residency"] = terminal_cache_observation(runtime, selected, build, output, row["cache_class"])
        row["cleanup"] = "Gone"
        row["proof_status"] = "FAIL"
        proof_started = time.monotonic_ns()
        proof_stop = time.monotonic() + case["budget"]["verification_hard_watchdog_ms"] / 1000-preproof_ns/1e9
        git_deadlines = git_proof_deadlines(case, preproof_ns) if case.get("git_workflow") else None
        proof_deadlines = family_proof_deadlines(case,preproof_ns,owner_stop)
        proof_work_stop = proof_deadlines["work"] if proof_deadlines else None
        proof_cleanup_stop = proof_deadlines["cleanup"] if proof_deadlines else None
        if proof_deadlines:
            proof_stop = publication_stop = proof_deadlines["publication"]
            row["proof_policy"] = {"work_cutoff_monotonic":proof_work_stop,"cleanup_cutoff_monotonic":proof_cleanup_stop,
                "publication_cutoff_monotonic":publication_stop,"original_verifier_ms":case["budget"]["verifier_ms"],
                "original_hard_watchdog_ms":case["budget"]["verification_hard_watchdog_ms"],"owner_test_ceiling_ms":owner_ceiling_ms if proof_only else None}
        def proof_seconds(limit, cleanup=False):
            left = proof_stop - time.monotonic()
            if proof_work_stop is not None:
                left = min(left, (proof_cleanup_stop if cleanup else proof_work_stop)-time.monotonic())
            if left <= 0:
                raise TimeoutError("original frozen verification hard watchdog expired")
            return min(limit, left)
        native_stop = min(proof_stop, time.monotonic() + operation_seconds) if ordered else proof_stop
        def native_seconds(limit):
            left = native_stop - time.monotonic()
            if left <= 0:
                raise TimeoutError("original per-state native proof watchdog expired")
            return min(proof_seconds(limit), left)
        verify_mount = secrets.token_hex(32)
        runtime.send("mount", verify_mount, deadline=time.monotonic() + native_seconds(15))
        mounted.add(verify_mount)
        if case.get("git_workflow"):
            row["git_custody"] = verify_git_custody(runtime, verify_mount, prepared, build, output,
                                                    row["git_precommit"], native_seconds(case["budget"]["verifier_ms"]/1000))
        docker = ["docker", "--host", "unix://" + build["socket"]]
        if case.get("m1_schedule"):
            if final_modes is None:
                raise ValueError("original measured created-mode observations unavailable")
            receipts.command([*docker,"cp",final_modes["path"],runtime.container+":/code/history/observed-final-modes.tsv"],output,"native-created-modes-stage",proof_seconds(15))
            verify_body = "/bin/bash /code/workload.sh verify-step " + shlex.quote(case["v016_case"])+f" {case['history_schedule']['commits']} /code/history/observed-final-modes.tsv"
        elif case.get("automatic_parent_mtime"):
            custody=row["automatic_parent_mtime_custody"]
            receipts.command([*docker,"cp",custody["path"],runtime.container+":/code/history/observed-parent-mtime.tsv"],output,"native-alias-custody-stage",proof_seconds(15))
            verify_body="/bin/bash /code/workload.sh verify "+shlex.quote(case["v016_case"])+" 5 /code/history/observed-parent-mtime.tsv"
        elif footprint:
            boundary=footprint_boundary(prepared)
            row["footprint_boundary"]=boundary
            verify_body="/bin/bash /code/workload.sh verify "+shlex.quote(case["v016_case"])+" "+shlex.quote(boundary["path"])+f" {boundary['start']} {boundary['end']}"
        else:
            verify_body = "/bin/bash /code/workload.sh verify " + shlex.quote(case["v016_case"])
            if recipe_history:
                verify_body += " "+str(case["history_schedule"]["commits"])
        verified = runtime.send("verify", verify_mount, script(output, "verify.sh", verify_body),
                                deadline=time.monotonic() + native_seconds(case["budget"]["verifier_ms"] / 1000))
        proof = verify_native_receipt(case, verified, row.get("footprint_boundary"))
        if case.get("m1_schedule") and proof["created_modes_digest"]!=final_modes["sha256"]:
            raise ValueError("native selective proof did not bind exact measured mode observations")
        if case.get("automatic_parent_mtime") and proof.get("parent_mtime_custody_sha256") != row["automatic_parent_mtime_custody"]["sha256"]:
            raise ValueError("native alias proof differs from exact measured timestamp custody")
        if case.get("git_workflow"):
            row["git_semantics"] = verify_git_semantic_fields(proof, prepared)
        runtime.send("unmount", verify_mount, deadline=time.monotonic() + (proof_seconds(15, cleanup=True) if proof_deadlines else native_seconds(15)))
        mounted.remove(verify_mount)
        row["verification_cleanup"] = readiness(runtime, verify_mount, proof_seconds(5, cleanup=True) if proof_deadlines else native_seconds(5))
        if footprint or case.get("original_ordinary_guards"):
            row["ordinary_resource_guards"]["after_native_proof"] = ordinary_resource_guard(runtime, build, output,
                "ordinary-resources-after-native-proof", row["ordinary_resource_guards"]["before"], proof_seconds(15))
        if small_history:
            row["resource_guards"]["after_native_proof"] = history_resource_guard(runtime, build, output,
                "history-resources-after-native-proof", row["resource_guards"]["before"])
        runtime.send("observe", deadline=time.monotonic() + proof_seconds(15, cleanup=True))
        if reuse or footprint:
            source_stats = storage_source_observations(runtime, build, output, proof_seconds)
        runtime.send("stop", deadline=time.monotonic() + proof_seconds(15, cleanup=True))
        runtime.event("finished", time.monotonic() + proof_seconds(15, cleanup=True))
        if runtime.process.wait(timeout=proof_seconds(1, cleanup=True) if proof_deadlines else 1) != 0:
            raise ValueError("original runtime exit differs after known Stop")
        row["custody"] = "KNOWN_STOP"
        if host_observer is not None:
            row["host_process_observations"] = host_observer.finish()
            if row["host_process_observations"]["status"] != "PASS":
                raise ValueError("original footprint zero expanded-child swaps guard failed")
        row["completed_operation_count"] = 1
        docker = ["docker", "--host", "unix://" + build["socket"]]
        # Closed sample input to the independent offline oracle, after Stop;
        # never a host data-serving route or construction/materialization path.
        exported = receipts.command([*docker, "cp", runtime.container + ":/layerfs-store/global", str(output / "graph-store")], output, "closed-store-export", proof_seconds(15))
        exported_store = output / "graph-store/store.sqlite"
        census_store = exported_store
        typed_store = exported_store
        if recipe_history:
            import shutil
            # A known-Stop WAL still contains acknowledged history. Preserve
            # its raw export, and bind a standalone recovery snapshot before
            # making the public provider's independently writable copy.
            normalized = oracle.prepare_closed_store(output/"graph-store", output/"census-store/store.sqlite",
                                                     proof_work_stop if proof_work_stop is not None else proof_stop)
            row["closed_store_normalization"] = normalized
            census_store = Path(normalized["path"])
            proof_seconds(.001)
            (output/"typed-store").mkdir()
            typed_store = output/"typed-store/store.sqlite"
            shutil.copy2(census_store,typed_store)
            if identity.sha256(typed_store)!=identity.sha256(census_store):
                raise ValueError("independent public provider copy differs from normalized closed export")
            row["typed_store_input"]={"path":str(typed_store),"sha256":identity.sha256(typed_store),"bytes":typed_store.stat().st_size}
        elif reuse or footprint:
            import shutil
            normalized = oracle.prepare_closed_store(output/"graph-store",output/"census-store/store.sqlite",proof_work_stop)
            row["closed_store_normalization"] = normalized
            census_store = Path(normalized["path"])
            (output/"typed-store").mkdir()
            typed_store = output/"typed-store/store.sqlite"
            shutil.copy2(census_store,typed_store)
            if identity.sha256(typed_store)!=identity.sha256(census_store):
                raise ValueError("reuse public provider copy differs from exact normalized closed Store")
        graph_args = [build["binaries"]["runtime"]["path"], "verify-workspace", "--socket", build["socket"],
                      "--volume", row["clone"]["volume"], "--daemon", build["binaries"]["daemon"]["path"],
                      "--manifest", prepared["provision"]["manifest"], "--sealed", str(typed_store),
                      "--case", case["v016_case"], "--receipt", str(output / "graph.events.jsonl"),
                      "--uid", str(prepared["source_uid"]), "--gid", str(prepared["source_gid"])]
        if ordered:
            transcript_body,selected_steps = history_transcript(case,prepared,row["history"])
            transcript = script(output, "acknowledged-history.tsv", transcript_body)
            row["history"]["verification_steps"]=selected_steps
            graph_args[1] = "verify-history"
            graph_args.extend(["--history-file", str(transcript)])
            if case.get("m1_schedule"):
                graph_args.extend(["--source-copy",final_modes["path"]])
        if case.get("automatic_parent_mtime"):
            graph_args.extend(["--source-copy",row["automatic_parent_mtime_custody"]["path"]])
        if case.get("git_workflow"):
            graph_args.extend(["--source-copy", row["git_precommit"]["path"]])
        if footprint:
            bound=oracle._manifest_identity(Path(prepared["provision"]["manifest"]))
            fields=committed["fields"]
            initial=row["initialization"]["ack"]["fields"]
            footprint_ack=script(output,"footprint-acknowledgements.tsv",
                "fs-bench-pro-store-footprint-ack-v1\n"+case["v016_case"]+"\n"+
                "init\t"+bound["branch_id"]+"\t"+initial["root"]+"\t"+mount["fields"]["base_layer"]+"\t"+initial["stack"]+"\n"+
                "commit\t"+fields["commit_id"]+"\t"+fields["root"]+"\t"+fields["parent"]+"\t"+fields["base_layer"]+"\t"+fields["stack"]+"\n")
            transcript=script(output,"footprint-census.tsv","0\t-\t-\t"+initial["root"]+"\toriginal-footprint-initial\n"+
                "1\t"+fields["commit_id"]+"\t"+fields["parent"]+"\t"+fields["root"]+"\toriginal-footprint-final-boundary\n")
            graph_args[1]="verify-footprint"
            graph_args.extend(["--source-copy",prepared["source"],"--history-file",str(footprint_ack)])
        if reuse:
            initial_root = row["pristine_payload_attribution"]["proof"]["fields"]["root"]
            transcript = script(output,"acknowledged-reuse.tsv",
                "0\t-\t-\t"+initial_root+"\t"+str(Path(prepared["source"]).resolve().with_suffix(".manifest.tsv"))+"\n"+
                "1\t"+committed["fields"]["commit_id"]+"\t"+committed["fields"]["parent"]+"\t"+
                committed["fields"]["root"]+"\t"+str(Path(prepared_folder).resolve()/"expected-native.manifest.tsv")+"\n")
            graph_args.extend(["--history-file",str(transcript)])
        if small_history:
            graph_events, roots, physical = [], [], []
            wanted = [row["history"]["initial_root"], *[item["commit"]["fields"]["root"] for item in row["history"]["commits"]]]
            for step, expected_root in enumerate(wanted):
                history_free_space(output)
                seconds = proof_seconds(operation_seconds)
                events_path = output / f"graph-state-{step}.events.jsonl"
                state_args = [*graph_args, "--history-step", str(step)]
                state_args[state_args.index("--receipt") + 1] = str(events_path)
                attempted = receipts.command(state_args, output, f"independent-graph-state-{step}", seconds,
                    environment={**os.environ, "LAYERFS_CONSTRUCTION_WORKERS": "1"})
                events = [json.loads(line) for line in events_path.read_text().splitlines()]
                proved = [item for item in events if item["event"] == "workspace_verified"]
                selected_roots = [item for item in events if item["event"] == "history_root_verified"]
                encoding = [item for item in events if item["event"] == "history_payload_encoding"]
                if (len(proved) != 1 or events[-1]["event"] != "finished"
                        or proved[0]["fields"]["root"] != expected_root
                        or proved[0]["fields"]["final_head_root"] != committed["fields"]["root"]
                        or len(selected_roots) != 1 or selected_roots[0]["fields"]["step"] != step
                        or selected_roots[0]["fields"]["root"] != expected_root):
                    raise ValueError("independent selected state/full-acknowledgement history binding differs")
                roots.extend(selected_roots)
                graph_events.extend(proved)
                if len(encoding) == 1 and encoding[0]["fields"].get("root") == expected_root:
                    physical.extend(encoding)
                row["history"].setdefault("proof_attempts", []).append({"index": step, "wall_stop_seconds": seconds,
                    "attempt": attempted, "root": expected_root, "semantic_proof": proved[0], "payload_encoding": encoding})
            row["history"]["verified_roots"] = roots
            row["mechanism"] = qualify_history_mechanism(physical)
            proof_events = [graph_events[-1]]
        else:
            graph = receipts.command(graph_args, output, "independent-graph", proof_seconds(case["budget"]["verifier_ms"] / 1000),
                                     environment={**os.environ, "LAYERFS_CONSTRUCTION_WORKERS": "1"})
            events = [json.loads(line) for line in (output / "graph.events.jsonl").read_text().splitlines()]
            proof_events = [item for item in events if item["event"] == ("store_footprint_verified" if footprint else "workspace_verified")]
            if len(proof_events) != 1 or events[-1]["event"] != "finished" or proof_events[0]["fields"]["final_root" if footprint else "root"] != committed["fields"]["root"]:
                raise ValueError("original persisted root proof differs from exact acknowledged Commit root")
            if case.get("automatic_parent_mtime") and proof_events[0]["fields"].get("parent_mtime_custody_sha256") != row["automatic_parent_mtime_custody"]["sha256"]:
                raise ValueError("persisted alias proof differs from exact measured timestamp custody")
            if footprint:
                fields=proof_events[0]["fields"]
                if any(fields.get(key)!=boundary[expected] for key,expected in (("selected_path","path"),("boundary_start","start"),("boundary_end","end"),("file_size","file_size"),("boundary_sha256","sha256"))):
                    raise ValueError("footprint independent native/public clipped boundary identity differs")
            if ordered:
                roots = [item for item in events if item["event"] == "history_root_verified"]
                wanted = [row["history"]["initial_root"], *[item["commit"]["fields"]["root"] for item in row["history"]["commits"]]]
                if ([item["fields"]["step"] for item in roots]!=selected_steps
                        or [item["fields"]["root"] for item in roots] != [wanted[index] for index in selected_steps]):
                    raise ValueError("exact selected original sequence proof differs from acknowledged states")
                row["history"]["verified_roots"] = roots
        if recipe_history:
            fields = proof_events[0]["fields"]
            tuples=[{"commit_id":record["commit"]["fields"]["commit_id"],
                     "layer_stack_id":record["commit"]["fields"]["stack"],
                     "root_id":record["commit"]["fields"]["root"],
                     "parent_commit_id":None if record["commit"]["fields"]["parent"]=="-" else record["commit"]["fields"]["parent"],
                     "base_layer_id":record["commit"]["fields"]["base_layer"]} for record in row["history"]["commits"]]
            export_completion=output/"closed-store-export.completion.json"
            runtime_events=output/"runtime.events.jsonl"
            custody={"custody":row["custody"],"container":runtime.container,"volume":row["clone"]["volume"],
                "remote_source":"/layerfs-store/global/store.sqlite","local_source":str(exported_store),
                "source_sha256":identity.sha256(exported_store),"source_size":exported_store.stat().st_size,
                "prepared_manifest":prepared["provision"]["manifest"],"prepared_manifest_sha256":identity.sha256(prepared["provision"]["manifest"]),
                "transcript":str(transcript),"transcript_sha256":identity.sha256(transcript),
                "export_completion":str(export_completion),"export_completion_sha256":identity.sha256(export_completion),
                "runtime_events":str(runtime_events),"runtime_events_sha256":identity.sha256(runtime_events)}
            custody["normalization"] = {"receipt":normalized["receipt"], "receipt_sha256":normalized["receipt_sha256"]}
            census = oracle.commit_census(census_store,tuples,fields,custody)
            proof_seconds(.001)
            receipts.write_new(output/"global-commit-census.json",census)
            row["history"]["global_commit_census"]=census
        elif reuse or footprint:
            fields = proof_events[0]["fields"]
            if (fields.get("initial_root")!=(row["initialization"]["ack"]["fields"]["root"] if footprint else row["pristine_payload_attribution"]["proof"]["fields"]["root"])
                    or not footprint and fields.get("roots")!=2):
                raise ValueError("reuse persisted initial/final roots differ from pristine/actual Commit acknowledgements")
            tuples = [{"commit_id":committed["fields"]["commit_id"],"layer_stack_id":committed["fields"]["stack"],
                "root_id":committed["fields"]["root"],"parent_commit_id":None if committed["fields"]["parent"]=="-" else committed["fields"]["parent"],
                "base_layer_id":committed["fields"]["base_layer"]}]
            export_completion, runtime_events = output/"closed-store-export.completion.json", output/"runtime.events.jsonl"
            custody = {"custody":row["custody"],"container":runtime.container,"volume":row["clone"]["volume"],
                "remote_source":"/layerfs-store/global/store.sqlite","local_source":str(exported_store),
                "source_sha256":identity.sha256(exported_store),"source_size":exported_store.stat().st_size,
                "prepared_manifest":prepared["provision"]["manifest"],"prepared_manifest_sha256":identity.sha256(prepared["provision"]["manifest"]),
                "transcript":str(transcript),"transcript_sha256":identity.sha256(transcript),
                "export_completion":str(export_completion),"export_completion_sha256":identity.sha256(export_completion),
                "runtime_events":str(runtime_events),"runtime_events_sha256":identity.sha256(runtime_events),
                "normalization":{"receipt":normalized["receipt"],"receipt_sha256":normalized["receipt_sha256"]}}
            census = oracle.commit_census(census_store,tuples,fields,custody)
            receipts.write_new(output/("global-footprint-commit-census.json" if footprint else "global-reuse-commit-census.json"),census)
            row["footprint_global_commit_census" if footprint else "reuse_global_commit_census"] = census
            observe_family_closed_storage(runtime, row, build, output, census_store, custody, source_stats, proof_seconds)
        row.update(proof_status="PASS", proof_wall_ns=time.monotonic_ns() - proof_started+preproof_ns,
                   verification={"scope": case["oracle"]["scope"], "omissions": case["oracle"]["omissions"],
                                 "native": proof, "persisted": proof_events[0]})
        collect_family_observations(runtime, row, build, output, bindings, proof_work_stop)
        if proof_deadlines:
            proof_seconds(.001)
        row.update(status="PASS" if proof_only or row["cache"]["status"] == "ELIGIBLE" else "INELIGIBLE", functional_status="PASS")
        if proof_only:
            row["verification_execution_wall_ns"]=row["complete_wall_ns"]
            row["proof_wall_ns"]=time.monotonic_ns()-started_test_ns
            row["performance_note"]="original exhaustive verification-only case; raw work/count observations diagnostic, performance N/A"
        if small_history:
            row["semantic_proof_status"] = "PASS"
            row["verification"]["mechanism"] = row["mechanism"]
            if row["mechanism"]["status"] != "PASS":
                row.update(status="FAIL", proof_status="FAIL", functional_status="FAIL", tag=row["mechanism"]["reason"])
                row["resource_disposition"] = "known stopped container and sample volume retained for unmet original mechanism condition; all31 byte/history/census proofs and clean unmount remain PASS"
                return row
        if row["status"] == "INELIGIBLE":
            row["tag"] = ("same-mount history paid backing/metadata/SQLite, own-write coldness and initial/warm interval evidence unavailable; all declared retained-state proofs and clean unmount pass" if ordered else
                          "class B source demands or own-write cold backing precondition unavailable; functional/native/persisted proofs and clean unmount pass")
            if footprint:
                row["tag"] = "class A pre-phase backing/metadata/SQLite and own-write coldness unqualified; terminal cache observation " + row["cache"]["residency"]["status"] + "; functional/native/persisted proofs and clean unmount pass"
            if case.get("git_workflow"):
                row["tag"] += "; prior original verification reads and full paid cache inputs unqualified; numeric counts include excluded precommit custody verifier FUSE/SQL work"
        state = receipts.command([*docker, "inspect", runtime.container, "--format", "{{.State.Running}}"], output, "container-state", proof_seconds(15, cleanup=True) if proof_deadlines else 15)
        if Path(state["stdout"]).read_text().strip() != "false":
            raise ValueError("original container Stop not confirmed")
        row["resource_removal_pending"] = True
        row["resource_disposition"] = "known stopped sample container/volume retained pending final publication and known outer return; administrative removal separate"
    except BaseException as error:
        row.update(status="FAIL", original_failure_type=type(error).__name__, original_failure=str(error),
                   retained_mount_keys=sorted(mounted), resource_disposition="original resources retained; no inferred unmount/Stop/removal")
        if clock.started is not None:
            row["complete_wall_ns"] = clock.observe(time.monotonic_ns())["performance_ns"]
        if proof_started is not None:
            row["proof_wall_ns"] = time.monotonic_ns() - proof_started+preproof_ns
        elif preproof_ns:
            row["proof_wall_ns"] = preproof_ns
        if runtime is not None and row.get("custody") == "KNOWN_STOP" and not (output / "daemon-logs.attempt.json").exists():
            try:
                collect_family_observations(runtime, row, build, output, bindings)
            except BaseException as observing:
                row["independent_observation_failure"] = str(observing)
        if runtime is None:
            runtime = getattr(error, "event_process", None)
        if runtime is not None:
            row["retained_host_custody"] = runtime.retain(error)
            row["container"] = runtime.container
    finally:
        if fresh_init_handle is not None:
            from . import project
            project.fresh_init_close(fresh_init_handle, row)
        if host_observer is not None:
            try:
                row["host_process_observations"] = host_observer.finish()
            except BaseException as observing:
                row.update(status="FAIL", host_observer_failure=str(observing))
                if host_observer.completion_path.exists():
                    row["host_process_observations"] = json.loads(host_observer.completion_path.read_text())
        if runtime is not None:
            for value in (runtime.selector, runtime.raw, runtime.stderr, getattr(runtime.process, "stdin", None), getattr(runtime.process, "stdout", None)):
                if value is not None:
                    try:
                        value.close()
                    except BaseException as closing:
                        row.setdefault("independent_close_failures", []).append(str(closing))
                        row["status"] = "FAIL"
        row["timing_scope"] = "matrix controller from measured mount through command/Commit/terminal unmount; read-only resource-observer intervals excluded and separately retained; absolute phase stop includes those intervals; setup/warmup/cleanup/fresh native and persisted verification/Stop separate"
        if footprint:
            row["timing_scope"] = "controller from original fresh measured public Init through actual-project public SDK installation, SDK runtime/setup, first fresh mount, ordinary clipped edit, Commit and terminal End; declared read-only resource-observer intervals excluded and retained; cleanup/fresh mounted and typed verification/Stop separate"
        if proof_only:
            row["proof_wall_ns"]=time.monotonic_ns()-started_test_ns
            row["proof_wall_scope"]="verification-only complete invocation from source/build/prepared admission through setup, all original calls/Commits, native/public/census proof, required cleanup/Stop and prepublication close; declared owner invocation ceiling separately enforced"
        row["evidence"] = str(output.relative_to(identity.ROOT.resolve()))
        io_observer.attach(output, row)
        if (case.get("git_workflow") or batch4 or reuse or footprint) and publication_stop is not None:
            if proof_started is not None:
                if not proof_only:
                    row["proof_wall_ns"] = time.monotonic_ns()-proof_started+preproof_ns
                    row["proof_wall_scope"] = "cumulative prior qualification/precommit custody/final proof and known cleanup/observations through prepublication close; publication timing is separately bound in publication receipts"
            if proof_cleanup_stop is not None and time.monotonic() >= proof_cleanup_stop:
                row.update(status="FAIL", proof_status="FAIL",
                           tag="; ".join(filter(None, (row.get("tag"), "original cumulative verification cleanup deadline reached before publication"))))
            if batch4 or reuse or footprint:
                row.update(receipts.finalize_guarded(output,row,publication_stop,scope=receipts.HISTORY_PUBLICATION_SCOPE))
            else:
                row.update(receipts.finalize_guarded(output, row, publication_stop))
        else:
            receipts.write_new(output / "receipt.json", row)
            receipts.manifest(output)
    return row


def dispose_family_resources(folder, returned_row):
    """Driver-only administration after publication and an actual known return.

    End, Gone, Stop and their deadlines stay inside the original case. Docker
    removal is outside those clocks. Failed/uncertain publication causes no
    deletion; partial deletion has exact separate custody, never a retry.
    """
    folder = Path(folder)
    if returned_row.get("resource_removal_pending") is not True:
        return None
    receipts.verify_manifest(folder)
    original = json.loads((folder / "receipt.json").read_text())
    effective = receipts._publication_overlay(folder, original, original)
    owned_identity = receipts.resource_removal_identity(original)
    names = tuple(owned_identity)
    if (any(returned_row.get(name) != original.get(name) for name in names)
            or ("additional_containers" in returned_row) != ("additional_containers" in original)):
        raise ValueError("resource removal returned source/resource identity differs")
    if (returned_row.get("status") not in ("PASS", "INELIGIBLE")
            or effective.get("status") not in ("PASS", "INELIGIBLE")
            or any(row.get("functional_status") != "PASS" or row.get("proof_status") != "PASS"
                   or row.get("custody") != "KNOWN_STOP" or row.get("cleanup") != "Gone"
                   for row in (returned_row, effective))):
        return None
    container, volume = original["container"], original["clone"]["volume"]
    additional=original.get("additional_containers",[])
    if (not isinstance(container, str) or len(container) != 64
            or any(char not in "0123456789abcdef" for char in container)
            or not isinstance(volume, str) or not volume.startswith("layerfs-fsb-sample-")):
        raise ValueError("exact owned sample resource identity required for removal")
    build = json.loads((Path(original["build"]) / "build.json").read_text())
    docker = ["docker", "--host", "unix://" + build["socket"]]
    output = folder / "resource-removal"
    output.mkdir(exist_ok=False)
    binding = {"schema": "fs-bench-pro-resource-removal-v1",
        "receipt_sha256": identity.sha256(folder / "receipt.json"),
        "manifest_sha256": identity.sha256(folder / "manifest.json"),
        "outer_ack_sha256": identity.sha256(folder / "publication-outer-acknowledgement.json")
            if original.get("publication_guard") else None,
        "identity": owned_identity,
        "known_outer_return": True, "container": container, "volume": volume,
        "scope": "post-publication Docker administration; original mount cleanup/Stop proof and timing unchanged",
        "container_custody": "KNOWN_STOP_RETAINED", "volume_custody": "RETAINED"}
    if "additional_containers" in original:
        binding.update(additional_containers=additional,
                       additional_container_custody={value: "KNOWN_STOP_RETAINED" for value in additional})
    receipts.write_new(output / "attempt.json", binding)
    record = dict(binding)
    try:
        state = receipts.command([*docker, "inspect", container, "--format", "{{.State.Running}}"], output, "state", 15)
        if Path(state["stdout"]).read_text().strip() != "false":
            raise ValueError("owned sample Stop readback differs before administrative removal")
        record["container_custody"] = "REMOVAL_ATTEMPT_UNCERTAIN"
        receipts.command([*docker, "rm", container], output, "container", 15)
        record["container_custody"] = "REMOVED"
        for index,extra in enumerate(additional,1):
            extra_state=receipts.command([*docker,"inspect",extra,"--format","{{.State.Running}}"],output,f"additional-{index}-state",15)
            if Path(extra_state["stdout"]).read_text().strip()!="false":
                raise ValueError("additional owned verifier runtime Stop readback differs")
            record["additional_container_custody"][extra]="REMOVAL_ATTEMPT_UNCERTAIN"
            receipts.command([*docker,"rm",extra],output,f"additional-{index}-container",15)
            record["additional_container_custody"][extra]="REMOVED"
        record["volume_custody"] = "REMOVAL_ATTEMPT_UNCERTAIN"
        receipts.command([*docker, "volume", "rm", volume], output, "volume", 15)
        record.update(volume_custody="REMOVED", status="PASS")
    except BaseException as error:
        record.update(status="FAIL", failure_type=type(error).__name__, failure=str(error))
    record["resource_disposition"] = receipts.resource_removal_custody(record, original)
    receipts.write_new(output / "completion.json", record)
    receipts.manifest(output)
    returned_row["resource_disposition"] = record["resource_disposition"]
    return record


# Batch 5 uses the same SDK/runtime owner, with explicit role-local histories.
CONTEXT_FAMILIES = frozenset(('branch_development', 'multi_workspace_development'))


def access_deadlines(case, started, owner_stop):
    guard = case['original_v016_guards']
    wanted = {'verification_complete_work_ms': 25000, 'verification_worker_work_ms': 22000,
              'cleanup_reserve_ms': 3000, 'verification_hard_ms': 35000,
              'publication_guard_seconds': 0.25, 'owner_test_invocation_ceiling_ms': 120000}
    if any(guard.get(key) != value for key, value in wanted.items()):
        raise ValueError('original access25/22/3/35/.25/120 limits required')
    return {'work': min(owner_stop, started + 22), 'cleanup': min(owner_stop, started + 25),
            'publication': min(owner_stop, started + 35), 'owner': owner_stop}


def access_selected_history(runtime, prepared, graph, output, deadline):
    selected = prepared['historical_selection']; role = selected['source_role']; branch = graph['branches'][role]
    history = context_history(runtime, '@' + branch['branch_id'], branch, graph, output, deadline)
    offset = len(branch['commits']) - selected['local']
    actual = history['records'][offset]
    expected = branch['commits'][selected['local'] - 1]['commit']['fields']
    if any(actual.get(key) != expected[key] for key in ('commit_id', 'stack', 'root', 'parent', 'base_layer')):
        raise ValueError('access local ordinal differs from exact anchored public History record')
    ack = selected['acknowledged_commit']
    if (ack['commit_id'] != actual['commit_id'] or ack['root_id'] != actual['root']
            or ack['local'] != selected['local'] or ack['role'] != role):
        raise ValueError('access selection differs from authenticated producer acknowledgement')
    return {'source_role': role, 'original_source_role': selected['original_source_role'], 'local': selected['local'],
            'source_branch_id': branch['branch_id'], 'source_head': branch['final_head'], 'history': history, 'selected': actual}


def access_fork(runtime, case, selected, graph, output, deadline):
    identifier = '11' + secrets.token_hex(16)
    name = f"access-{selected['local']}-{case['v016_case']}"
    ack = selected['selected']
    body = f"commit\t{identifier}\t{name}\t@{selected['source_branch_id']}\t{ack['commit_id']}\n"
    request = script(output, 'access-fork.tsv', body)
    fork = context_send(runtime, 'fork', 'access', request, deadline=deadline)
    fields = fork['fields']
    wanted = {'branch_id': identifier, 'name': name, 'head': ack['commit_id'], 'root': ack['root'],
              'stack': ack['stack'], 'base_layer': ack['base_layer']}
    if any(fields.get(key) != value for key, value in wanted.items()):
        raise ValueError('access public Fork differs from actual selected source Branch/Commit')
    graph['branches']['access'] = {'branch_id': identifier, 'name': name, 'stack': ack['stack'], 'base_layer': ack['base_layer'],
        'initial_parent': ack['commit_id'], 'initial_root': ack['root'], 'final_head': ack['commit_id'], 'final_root': ack['root'],
        'source_role': selected['source_role'], 'source_local': selected['local'], 'commits': [], 'fork': fork}
    return fork


def access_command(runtime, case, key, phase, output, deadline):
    body = '/bin/bash /code/workload.sh ' + shlex.join([phase, case['v016_case']])
    path = script(output, 'access-' + phase + '.sh', body)
    event = runtime.send('command' if phase == 'reader' else 'verify', key, path, deadline=deadline)
    fields = event['fields']
    if (fields.get('exit_code') != '0' or fields.get('registered_execs') != '0'
            or fields.get('command_sha256') != identity.sha256(path) or fields.get('key') != key):
        raise ValueError('access original helper known zero/body/ordinary command custody differs')
    return event


def access_graph_proof(case, prepared, graph, runtime, row, build, output, commands, deadline):
    import shutil
    docker = ['docker', '--host', 'unix://' + build['socket']]
    receipts.command([*docker, 'cp', runtime.container + ':/layerfs-store/global', str(output / 'graph-store')],
                     output, 'closed-store-export', operation_deadline(deadline, 15) - time.monotonic())
    raw = output / 'graph-store/store.sqlite'
    normalized = oracle.prepare_closed_store(output / 'graph-store', output / 'census-store/store.sqlite', deadline)
    row['closed_store_normalization'] = normalized
    census_store = Path(normalized['path']); (output / 'typed-store').mkdir()
    typed = output / 'typed-store/store.sqlite'; shutil.copy2(census_store, typed)
    if identity.sha256(typed) != identity.sha256(census_store):
        raise ValueError('access typed copy differs from immutable normalized census input')
    selected = prepared['historical_selection']
    producer = {'v016_case': prepared['closed_producer']['producer_case']}
    checkpoints = {'context_checkpoints': [{'role': selected['source_role'], 'index': selected['local'], 'manifest': selected['manifest']}]}
    roles = [*fixtures.historical_plan(case)['graph_roles'], 'access']
    if set(graph['branches']) != set(roles):
        raise ValueError('access exact original producer and zero-ACK Branch membership required')
    ordered = {'branches': {role: graph['branches'][role] for role in roles}}
    transcript = script(output, 'access-topology.tsv', context_transcript(producer, checkpoints, ordered))
    argv = [build['binaries']['runtime']['path'], 'verify-access', '--socket', build['socket'], '--volume', row['clone']['volume'],
        '--daemon', build['binaries']['daemon']['path'], '--manifest', prepared['provision']['manifest'], '--sealed', str(typed),
        '--case', case['v016_case'], '--receipt', str(output / 'access.events.jsonl'), '--history-file', str(transcript),
        '--uid', str(prepared['source_uid']), '--gid', str(prepared['source_gid'])]
    observed = receipts.command(argv, output, 'public-access-proof', operation_deadline(deadline, 120) - time.monotonic())
    events = [json.loads(line) for line in Path(observed['stdout']).read_text().splitlines()]
    completed = [event for event in events if event['event'] == 'workspace_verified']
    if (len(completed) != 1 or not events or events[-1]['event'] != 'finished'
            or completed[0]['fields'].get('status') != 'PASS' or completed[0]['fields'].get('case') != case['v016_case']
            or completed[0]['fields'].get('topology_case') != producer['v016_case']
            or completed[0]['fields'].get('root') != selected['acknowledged_commit']['root_id']):
        raise ValueError('access complete independent public typed selected-root proof required')
    branches = [event['fields'] for event in events if event['event'] == 'topology_branch_verified']
    if (len(branches) != len(graph['branches']) or {item['role'] for item in branches} != set(graph['branches'])
            or any(any(item.get(key) != graph['branches'][item['role']][field] for key, field in
                       (('branch_id', 'branch_id'), ('head', 'final_head'), ('root', 'final_root'))) for item in branches)):
        raise ValueError('access producer heads or new zero-ACK Branch changed')
    roots = [event['fields'] for event in events if event['event'] == 'topology_root_verified']
    if len(roots) != 1 or any(roots[0].get(key) != value for key, value in
            {'role': selected['source_role'], 'local': selected['local'], 'commit_id': selected['acknowledged_commit']['commit_id'],
             'root': selected['acknowledged_commit']['root_id']}.items()):
        raise ValueError('access exact retained selected root/Commit/local scope differs')
    passes = oracle.verify_access_passes(case, Path(commands['reader']['fields']['stdout']).read_text(),
                                       Path(commands['verifier']['fields']['stdout']).read_text(), events)
    tuples = [{key: ack[key] for key in ('commit_id', 'layer_stack_id', 'root_id', 'parent_commit_id', 'base_layer_id')}
              for ack in prepared['closed_producer']['acknowledgements']]
    completion, runtime_events = output / 'closed-store-export.completion.json', output / 'runtime.events.jsonl'
    custody = {'custody': row['custody'], 'container': runtime.container, 'volume': row['clone']['volume'],
        'remote_source': '/layerfs-store/global/store.sqlite', 'local_source': str(raw), 'source_sha256': identity.sha256(raw),
        'source_size': raw.stat().st_size, 'prepared_manifest': prepared['provision']['manifest'],
        'prepared_manifest_sha256': identity.sha256(prepared['provision']['manifest']), 'transcript': str(transcript),
        'transcript_sha256': identity.sha256(transcript), 'export_completion': str(completion),
        'export_completion_sha256': identity.sha256(completion), 'runtime_events': str(runtime_events),
        'runtime_events_sha256': identity.sha256(runtime_events),
        'normalization': {'receipt': normalized['receipt'], 'receipt_sha256': normalized['receipt_sha256']}}
    census = oracle.graph_commit_census(census_store, tuples, completed[0]['fields'], custody)
    if passes.get('status') != 'PASS' or census.get('status') != 'PASS' or time.monotonic() >= deadline:
        raise ValueError('access original two-pass/global census proof failed or exhausted deadline')
    receipts.write_new(output / 'global-access-census.json', census)
    row['topology'].update(public_proof=events, transcript=str(transcript), transcript_sha256=identity.sha256(transcript), global_census=census)
    return {'status': 'PASS', 'scope': case['oracle']['scope'], 'read_passes': passes, 'global_census': census}


def one_access_case(family, case, prepared_folder, build_folder, output):
    started_ns = time.monotonic_ns(); owner_stop = time.monotonic() + 120
    current, build = identity.source_identity(), identity.load_build(build_folder)
    prepared = fixtures.load(prepared_folder, case['fixture']['recipe'])
    admission = fixtures.validate_runtime_helpers(case, prepared, build)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    treatment = {'family': family, 'case': case, 'product': current['product_tree'], 'engine': identity.sha256(__file__),
                 'helpers': prepared['helpers']['files'], 'producer_store': prepared['closed_producer']['store_sha256'],
                 'producer_transcript': prepared['closed_producer']['transcript_sha256'],
                 'binaries': {name: value['sha256'] for name, value in build['binaries'].items()}, 'image': identity.IMAGE}
    claim = receipts.sample_claim_key(treatment, current["source_commit"])
    claims = identity.ROOT / 'benchmark-results/fs-bench-pro/claims'; claims.mkdir(parents=True, exist_ok=True)
    with (claims / claim).open('x') as stream:
        stream.write(str(output) + '\n')
    row = {'schema': 'fs-bench-pro-workspace-family-v1', 'family': family, 'case': case['id'], 'source_commit': current['source_commit'],
        'product_tree': current['product_tree'], 'identity': current, 'build': str(Path(build_folder).resolve()), 'prepared': str(Path(prepared_folder).resolve()),
        'image': identity.IMAGE, 'runtime_sha256': build['binaries']['runtime']['sha256'], 'daemon_sha256': build['binaries']['daemon']['sha256'],
        'status': 'NOT_RUN', 'functional_status': 'NOT_RUN', 'proof_status': 'NOT_RUN', 'proof_only': True,
        'sample_count': 0, 'verification_attempt_count': 1, 'attempted_operation_count': 1, 'completed_operation_count': 0,
        'performance_mode': 'verification-only', 'performance_description': 'original historical-access VERIFY-ONLY', 'declared_limit_ns': 'N/A',
        'verifier_limit_ns': 25_000_000_000, 'owner_test_ceiling_ns': 120_000_000_000, 'phases': {}, 'counts': {}, 'observations': {},
        'cache_class': 'B', 'cache': {'class': 'B', 'status': 'INELIGIBLE', 'declaration': case['cache_contract']},
        'global_profile': 'Disposable/WAL/OFF', 'overlay_profile': 'MEMORY/OFF/EXCLUSIVE', 'construction_workers': 1,
        'durable': 'NOT_RUN — disabled by owner until explicit reauthorization', 'interference': current.get('cross_worktree_interference'),
        'claim': claim, 'helper_admission': admission, 'cleanup': 'UNAVAILABLE', 'custody': 'UNAVAILABLE',
        'topology': {'branches': json.loads(json.dumps(prepared['closed_producer']['graph']['branches']))},
        'producer_dependency': prepared['producer_dependency']}
    receipts.write_new(output / 'selection.json', row)
    runtime, active, deadlines = None, {}, None
    try:
        row['clone'] = fixtures.clone(prepared, output / 'clone', build)
        environment = script(output, 'environment.txt', ''.join(name + '=' + value + '\n' for name, value in workloads.ENV.items()))
        argv = [build['binaries']['runtime']['path'], 'serve', '--socket', build['socket'], '--volume', row['clone']['volume'],
                '--daemon', build['binaries']['daemon']['path'], '--manifest', prepared['provision']['manifest'], '--receipt', str(output / 'runtime.events.jsonl'),
                '--uid', str(prepared['source_uid']), '--gid', str(prepared['source_gid']), '--environment-file', str(environment),
                '--observation-scope', secrets.token_hex(32), '--case', case['v016_case']]
        runtime = cell_runner.EventProcess(argv, output, 'runtime'); runtime.event('protocol_ready', min(owner_stop, time.monotonic() + 15))
        row['container'] = runtime.container
        if runtime.container is None:
            raise ValueError('access original container acknowledgement missing')
        row['container_profile'] = history_container_profile(runtime, build, output)
        row['staging'] = fixtures.stage(runtime.container, prepared, output / 'staging', build)
        row['current_supplemental_resources'] = {'scope': 'current supplemental4GiB main Store bound; original access profile2CPU/2GiB/noSwap/256PID and OOM delta retained',
            'before': ordinary_resource_guard(runtime, build, output, 'access-resources-before')}
        row['current_supplemental_resources']['before']['scope'] = row['current_supplemental_resources']['scope']
        row['setup_ns'] = time.monotonic_ns() - started_ns
        deadlines = access_deadlines(case, time.monotonic(), owner_stop); row['absolute_deadlines'] = deadlines
        graph = row['topology']
        selected = access_selected_history(runtime, prepared, graph, output, deadlines['work']); row['access_selection'] = selected
        access_fork(runtime, case, selected, graph, output, deadlines['work'])
        key = secrets.token_hex(32)
        active['access'] = key
        mounted = context_send(runtime, 'mount-branch', key, 'access', deadline=deadlines['work'])
        if mounted['fields'].get('key') != key:
            raise ValueError('access exact fresh mount key acknowledgement differs')
        row['phases']['mount_ns'] = mounted['span']['duration_ns']
        commands = {phase: access_command(runtime, case, key, phase, output, deadlines['work']) for phase in ('reader', 'verifier')}
        row['access_commands'] = commands; row['phases']['command_ns'] = sum(event['span']['duration_ns'] for event in commands.values())
        if any(event['event'] == 'commit' for event in runtime.rows):
            raise ValueError('original access reader must create zero Commits')
        row['phases']['commit_ns'] = 0
        row['current_instrumented_status'] = runtime.send('snapshot', key, deadline=deadlines['work'])
        ended = context_end(runtime, key, row, deadlines['cleanup']); active.pop('access')
        row['phases']['unmount_ns'] = ended['span']['duration_ns']; row['cleanup'] = 'Gone'
        row['current_supplemental_resources']['after'] = ordinary_resource_guard(runtime, build, output, 'access-resources-after',
            row['current_supplemental_resources']['before'], operation_deadline(deadlines['cleanup'], 15) - time.monotonic())
        row['current_supplemental_resources']['after']['scope'] = row['current_supplemental_resources']['scope']
        context_observations(runtime, row, build, output, deadlines['cleanup'])
        row['counts_scope'] = 'current instrumented diagnostic counts only; no performance attribution or numeric speed claim'
        runtime.send('observe', deadline=deadlines['cleanup']); runtime.send('stop', deadline=deadlines['cleanup'])
        runtime.event('finished', deadlines['cleanup'])
        if runtime.process.wait(timeout=operation_deadline(deadlines['cleanup'], 1) - time.monotonic()) != 0:
            raise ValueError('access runtime exit differs after acknowledged Stop')
        row['custody'] = 'KNOWN_STOP'
        row['verification'] = access_graph_proof(case, prepared, graph, runtime, row, build, output, commands, deadlines['work'])
        row.update(status='PASS', functional_status='PASS', proof_status='PASS', completed_operation_count=1,
                   resource_removal_pending=True, resource_disposition='known stopped sample pair retained pending publication and outer ACK',
                   tag='original two full reads, exact selected history/Fork, unchanged producer heads/Commit union and clean close; performance N/A')
    except BaseException as error:
        row.update(status='FAIL', functional_status='FAIL', proof_status='FAIL', original_failure=str(error), original_failure_type=type(error).__name__,
                   retained_mount_keys=dict(active), resource_disposition='failed/uncertain access resources retained; no inferred Stop or retry')
        if runtime is None:
            runtime = getattr(error, 'event_process', None)
        if runtime is not None:
            row['retained_host_custody'] = runtime.retain(error); row['container'] = runtime.container
    finally:
        if runtime is not None:
            for handle in (runtime.selector, runtime.raw, runtime.stderr, getattr(runtime.process, 'stdin', None), getattr(runtime.process, 'stdout', None)):
                if handle is not None:
                    try:
                        handle.close()
                    except BaseException as error:
                        row.setdefault('independent_close_failures', []).append(str(error)); row.update(status='FAIL', proof_status='FAIL')
        row['proof_wall_ns'] = time.monotonic_ns() - started_ns
        row['proof_wall_scope'] = 'verification-only complete invocation including setup; original25s worker/cleanup and35s publication scopes separately bound; owner120 ceiling'
        row['evidence'] = str(output.relative_to(identity.ROOT.resolve()))
        io_observer.attach(output, row)
        if deadlines is not None:
            if time.monotonic() >= deadlines['cleanup']:
                row.update(status='FAIL', proof_status='FAIL', tag='original access25s completion/cleanup deadline exhausted')
            row.update(receipts.finalize_guarded(output, row, deadlines['publication'], scope=receipts.HISTORY_PUBLICATION_SCOPE))
        else:
            receipts.write_new(output / 'receipt.json', row); receipts.manifest(output)
    return row


def context_send(runtime, operation, key='', path=None, *, deadline):
    """One original write, followed by its declared acknowledgement; no replay."""
    if time.monotonic() >= deadline:
        raise TimeoutError('context operation not sent after wall stop: ' + operation)
    columns = [operation]
    if key or path is not None:
        columns.append(key)
    if path is not None:
        columns.append(str(path))
    if any('\n' in column or '\r' in column or '\t' in column for column in columns):
        raise ValueError('unsafe context protocol field')
    raw = ('\t'.join(columns) + '\n').encode()
    if runtime.process.stdin.write(raw) != len(raw):
        raise cell_runner.OriginalFailure('short original context write; outcome uncertain; no resend')
    expected = {'mount-branch': 'mount', 'round': 'round_finished',
                'history': 'history_finished'}.get(operation, operation)
    return runtime.event(expected, deadline)


def context_layout(case):
    if case.get('branch_schedule', {}).get('schema') == 'original-branch-development-v1':
        schedule = case['branch_schedule']
        branches = []
        for branch in schedule['branches']:
            source = branch['fork_source']
            branches.append({'role': branch['role'], 'name': branch['name'],
                'count': branch['local_commits'],
                'source_role': source.get('source_role'), 'source_local': source.get('local_commit', 0)})
        groups = schedule['execution_groups']
        total = schedule['created_commit_acknowledgements']
        references = schedule['retained_root_references']
        segments = None
    elif case.get('topology_schedule', {}).get('schema') == 'original-v016-m1-topology-v1':
        schedule = case['topology_schedule']
        branches = [{'role': str(worker['index']), 'name': f"v016-{case['v016_case']}-{worker['index']}",
            'count': schedule['per_worker_commits'], 'source_role': None, 'source_local': 0}
            for worker in schedule['workers']]
        groups = [[branch['role'] for branch in branches]]
        segments = schedule['segment_ranges']
        total, references = schedule['total_commits'], schedule['graph_root_boundaries']
    else:
        raise ValueError('original committed context topology required')
    roles = [branch['role'] for branch in branches]
    if (not roles or len(set(roles)) != len(roles) or len(roles) > 4
            or sum(branch['count'] for branch in branches) != total
            or references != total + 1 or [role for group in groups for role in group] != roles
            or any(not group or len(group) > 4 for group in groups)):
        raise ValueError('original topology role/count/group geometry differs')
    if segments is not None:
        declared = [step for first, last in segments for step in range(first, last + 1)]
        if declared != list(range(1, branches[0]['count'] + 1)):
            raise ValueError('original concurrent segments must cover every local step exactly once')
    return {'branches': branches, 'groups': groups, 'segments': segments,
            'total': total, 'references': references, 'roles': roles}


def context_bodies(case, prepared):
    plan = fixtures.context_plan(case)
    if plan['roles'] != context_layout(case)['roles']:
        raise ValueError('prepared/context original roles differ')
    result = {}
    for role in plan['roles']:
        declared = plan['original_context_runs'][role]
        sdk = prepared['prepared_context_runs'].get(role, {})
        wanted = {str(step) for step in range(1, plan['local_commits'][role] + 1)}
        if set(declared) != wanted or not set(sdk).issubset(wanted):
            raise ValueError('every original role-local command and only declared SDK replacements required')
        result[role] = {step: '/bin/bash /code/' + sdk.get(step, body)
                        for step, body in declared.items()}
    return result


def context_modes_text(maps, roles):
    if set(maps) != set(roles):
        raise ValueError('actual context mode observations require each original role')
    rows = ['original-context-created-modes-v1', 'role\tpath\tmode']
    for role in roles:
        for path, mode in sorted(maps[role].items()):
            if (not path or any(part in ('', '.', '..') for part in path.split('/'))
                    or any(char.isspace() for char in path) or type(mode) is not int
                    or mode < 0 or mode > 0o777):
                raise ValueError('unsafe actual context directory-mode observation')
            rows.append(f'{role}\t{path}\t{mode:o}')
    return '\n'.join(rows) + '\n'


def context_step(case, role, local):
    if case.get('branch_schedule'):
        matches = [step for step in case['steps'] if step['role'] == role and step['local_index'] == local]
    else:
        matches = [step for step in case['steps'] if step['index'] == local]
    if len(matches) != 1:
        raise ValueError('one exact original role-local step required')
    return matches[0]


def context_overlap(commits):
    """The frozen maximum pair overlap and left-interval coverage count."""
    maximum, covered = 0, 0
    intervals = []
    for record in commits:
        span = record['commit']['span']
        if (span['clock_id'] != 'monotonic' or any(type(span[name]) is not int
                for name in ('start_ns', 'end_ns', 'duration_ns'))
                or span['end_ns'] < span['start_ns']
                or span['duration_ns'] != span['end_ns'] - span['start_ns']):
            raise ValueError('original complete Commit monotonic span required')
        intervals.append((record['role'], span['start_ns'], span['end_ns']))
    for index, (role, start, end) in enumerate(intervals):
        values = [max(0, min(end, other_end) - max(start, other_start))
                  for other_role, other_start, other_end in intervals[index + 1:] if other_role != role]
        maximum = max([maximum, *values])
        covered += int(any(values))
    return {'observed_overlap_ns': maximum, 'overlap_rounds': covered,
            'scope': 'original maximum different-worker public Commit overlap and left-interval coverage; common monotonic origin; no added threshold'}


def context_round(runtime, case, graph, keys, roles, first, last, bodies, modes, output, label, deadline):
    rows = [f"context-round-v1\t{case['v016_case']}"]
    admitted = {}
    for role in roles:
        for local in range(first, last + 1):
            body = bodies[role][str(local)]
            path = script(output, f'{label}-{role}-{local}.sh', body)
            rows.append(f'{role}\t{keys[role]}\t{local}\t{path}')
            admitted[(role, local)] = identity.sha256(path)
    descriptor = script(output, label + '.tsv', '\n'.join(rows) + '\n')
    before = len(runtime.rows)
    finished = context_send(runtime, 'round', label, descriptor, deadline=deadline)
    commands, commits = {}, {}
    for event in runtime.rows[before:]:
        fields = event.get('fields', {})
        if event['event'] not in ('command', 'commit') or fields.get('round') != label:
            continue
        role = fields.get('role')
        local = int(fields.get('local_step', -1))
        pair = (role, local)
        target = commands if event['event'] == 'command' else commits
        if pair not in admitted or pair in target or fields.get('key') != keys[role]:
            raise ValueError('duplicate, undeclared or substituted original concurrent event')
        target[pair] = event
    if set(commands) != set(admitted) or set(commits) != set(admitted):
        raise ValueError('complete original command and Created Commit acknowledgements required')
    records = []
    for role in roles:
        branch = graph['branches'][role]
        for local in range(first, last + 1):
            pair = (role, local)
            command, commit = commands[pair], commits[pair]
            fields = command['fields']
            if (fields.get('exit_code') != '0' or fields.get('registered_execs') != '0'
                    or fields.get('command_sha256') != admitted[pair]):
                raise ValueError('original external worker body/known zero exit/custody differs')
            declared = context_step(case, role, local)
            if declared.get('original_operation_counts'):
                checked = original_operation_counts(command, declared['original_operation_counts'])
            else:
                checked = None
            if case.get('m1_schedule'):
                modes[role] = m1_created_modes(command, modes[role])
            fields = commit['fields']
            previous = branch['commits'][-1]['commit']['fields']['commit_id'] if branch['commits'] else branch['initial_parent']
            if (fields.get('commit_kind') != 'Committed' or fields.get('parent') != previous
                    or fields.get('base_layer') != branch['base_layer'] or fields.get('stack') != branch['stack']):
                raise ValueError('original Created acknowledgement/parent/base/stack differs')
            for name, width in (('commit_id', 66), ('parent', 66), ('root', 64)):
                value = fields[name]
                if name == 'parent' and value == '-':
                    continue
                if not isinstance(value, str) or len(value) != width or any(c not in '0123456789abcdef' for c in value):
                    raise ValueError('exact typed original Commit identity required')
            record = {'role': role, 'index': local, 'command': command, 'commit': commit, 'operation_counts': checked}
            if local != len(branch['commits']) + 1:
                raise ValueError('original role-local order differs')
            branch['commits'].append(record)
            branch.update(final_head=fields['commit_id'], final_root=fields['root'])
            records.append(record)
    return {'label': label, 'descriptor': str(descriptor), 'descriptor_sha256': identity.sha256(descriptor),
            'finished': finished, 'records': records, 'barrier_scope': 'one common original segment-start barrier; no per-stage barrier'}


def context_transcript(case, prepared, graph, modes_file=None):
    selected = {(item['role'], item['index']): item['manifest'] for item in prepared['context_checkpoints']}
    if len(selected) != len(prepared['context_checkpoints']):
        raise ValueError('unique original selected context checkpoints required')
    rows = [f"topology-v1\t{case['v016_case']}"]
    for role, branch in graph['branches'].items():
        columns = ['branch', role, branch['branch_id'], branch['name'], branch['stack'], branch['base_layer'],
            branch['initial_parent'], branch['initial_root'], branch['final_head'], branch['final_root'],
            branch.get('source_role') or '-', str(branch.get('source_local', 0))]
        rows.append('\t'.join(columns))
        for record in branch['commits']:
            fields = record['commit']['fields']
            columns = ['commit', role, str(record['index']), fields['commit_id'], fields['stack'], fields['root'],
                fields['parent'], fields['base_layer'], selected.get((role, record['index']), '-'),
                str(modes_file) if modes_file is not None and (role, record['index']) in selected else '-']
            rows.append('\t'.join(columns))
    return '\n'.join(rows) + '\n'


def context_native_receipt(case, role, index, command, checkpoint, modes_file=None):
    if command['fields'].get('exit_code') != '0':
        raise ValueError('known successful native context verifier required')
    text = Path(command['fields']['stdout']).read_text()
    values = [json.loads(line) for line in text.splitlines()]
    expected = 2 if case.get('m1_schedule') else 1
    if len(values) != expected:
        raise ValueError('exact native contextual proof receipt rows required')
    proof = values[-1]
    if (set(proof) != {'case', 'role', 'step', 'verification_status', 'context_manifest_sha256'}
            or proof['case'] != case['v016_case'] or proof['role'] != role
            or type(proof['step']) is not int or proof['step'] != index
            or proof['verification_status'] != 'pass'
            or proof['context_manifest_sha256'] != checkpoint['manifest_sha256']):
        raise ValueError('native context proof case/role/state/manifest differs')
    if expected == 2:
        selective = values[0]
        if (selective.get('case') != case['v016_case'] or selective.get('step') != index
                or selective.get('seed') != 1 or selective.get('verification_status') != 'pass'
                or selective.get('scope') != 'original-m1-selective-scope-v1'
                or selective.get('created_modes_digest') != identity.sha256(modes_file)):
            raise ValueError('original selective proof must bind exact measured role-mode maps')
    return {'status': 'PASS', 'scope': case['oracle']['scope'], 'rows': values,
            'stdout_sha256': hashlib.sha256(text.encode()).hexdigest()}


def context_deadlines(case, started, *, phase='verification'):
    budget = case['budget']
    if phase == 'performance':
        hard = budget['performance_hard_watchdog_ms']
        reserve = budget.get('performance_cleanup_reserve_ms', 3000)
        if hard != 60000 or reserve != 3000:
            raise ValueError('unchanged original60s execution and3s cleanup reserve required')
        return {'work': started + (hard - reserve) / 1000, 'cleanup': started + hard / 1000}
    work, hard = budget['verifier_ms'], budget['verification_hard_watchdog_ms']
    reserve = budget.get('verification_cleanup_reserve_ms', 3000)
    named = LARGE_ROOT_PROOF_LIMITS.get(case.get('id'))
    if (work, hard) not in ((named,) if named else ((25000, 35000), (30000, 40000), (60000, 70000))) or reserve != 3000:
        raise ValueError('exact original batch5 verification work/hard/reserve required')
    return {'work': started + (work - reserve) / 1000, 'cleanup': started + work / 1000,
            'publication': started + hard / 1000}


def context_end(runtime, key, row, deadline):
    unmount = runtime.send('unmount', key, deadline=deadline)
    cleanup = readiness(runtime, key, min(5, max(0, deadline - time.monotonic())))
    row.setdefault('terminal_mounts', []).append({'key': key, 'unmount': unmount, 'cleanup': cleanup})
    return unmount


def context_history(runtime, role, branch, graph, output, deadline):
    """One explicit SDK page per request, anchored to the actual acknowledged head."""
    expected = []
    current = branch
    while True:
        expected.extend(record['commit']['fields'] for record in reversed(current['commits']))
        source_role = current.get('source_role')
        if source_role is None:
            break
        # Only the inherited prefix, excluding the source Branch later head.
        parent = graph['branches'][source_role]
        current = {**parent, 'commits': parent['commits'][:current['source_local']]}
    records, pages, seen_cursors, cursor = [], [], set(), '-'
    while True:
        request = script(output, f'history-{role}-page-{len(pages) + 1}.tsv',
                         f"{branch['final_head']}\t{cursor}\t32\n")
        before = len(runtime.rows)
        final = context_send(runtime, 'history', role, request, deadline=deadline)
        page = [event['fields'] for event in runtime.rows[before:] if event['event'] == 'history_record']
        if len(page) > 32 or final['fields'].get('records') != len(page):
            raise ValueError('public native bridge exact32-record page count differs')
        records.extend(page)
        pages.append(final)
        if len(records) > len(expected):
            raise ValueError('public History returned undeclared ancestor records')
        path = final['fields'].get('cursor_path')
        if path in (None, '-', ''):
            break
        if not page or len(records) >= len(expected):
            raise ValueError('unexpected or non-progressing History continuation')
        encoded = Path(path).read_bytes()
        if (not encoded or final['fields'].get('cursor_bytes') != len(encoded)
                or final['fields'].get('cursor_sha256') != hashlib.sha256(encoded).hexdigest()
                or encoded in seen_cursors):
            raise ValueError('public opaque History continuation artifact differs or repeats')
        seen_cursors.add(encoded)
        cursor = encoded.hex()
    keys = ('commit_id', 'stack', 'root', 'parent', 'base_layer')
    if len(records) != len(expected) or any(any(left.get(key) != right[key] for key in keys)
                                           for left, right in zip(records, expected)):
        raise ValueError('public SDK History differs from exact role ancestry and acknowledged tuples')
    return {'finished': final, 'pages': pages, 'records': records, 'anchor': branch['final_head'],
            'page_limit': 32, 'page_scope': 'existing native bridge HISTORY_WINDOW32; each continuation is a new anchored SDK page, not a retry'}


def context_fork(runtime, case, specification, graph, output, deadline):
    role = specification['role']
    identifier = '11' + secrets.token_hex(16)
    source = specification['source_role']
    if source is None:
        body = f"layer\t{identifier}\t{specification['name']}\n"
        parent = '-'
        root = graph['branches']['initial']['initial_root']
    else:
        previous = graph['branches'][source]['commits'][specification['source_local'] - 1]['commit']['fields']
        body = f"commit\t{identifier}\t{specification['name']}\t{source}\t{previous['commit_id']}\n"
        parent, root = previous['commit_id'], previous['root']
    request = script(output, f'fork-{role}.tsv', body)
    fork = context_send(runtime, 'fork', role, request, deadline=deadline)
    fields = fork['fields']
    initial = graph['branches']['initial']
    if (fields.get('branch_id') != identifier or fields.get('name') != specification['name']
            or fields.get('head') != parent or fields.get('root') != root
            or fields.get('stack') != initial['stack'] or fields.get('base_layer') != initial['base_layer']):
        raise ValueError('existing public SDK Fork acknowledgement differs from exact selected source')
    graph['branches'][role] = {'branch_id': identifier, 'name': specification['name'],
        'stack': fields['stack'], 'base_layer': fields['base_layer'], 'initial_parent': parent,
        'initial_root': root, 'final_head': parent, 'final_root': root, 'source_role': source,
        'source_local': specification['source_local'], 'commits': [], 'fork': fork}
    return fork


def context_graph_proof(case, prepared, graph, runtime, row, build, output, modes_file, deadline):
    import shutil
    docker = ['docker', '--host', 'unix://' + build['socket']]
    receipts.command([*docker, 'cp', runtime.container + ':/layerfs-store/global', str(output / 'graph-store')],
                     output, 'closed-store-export', operation_deadline(deadline, 15) - time.monotonic())
    raw = output / 'graph-store/store.sqlite'
    normalized = oracle.prepare_closed_store(output / 'graph-store', output / 'census-store/store.sqlite', deadline)
    row['closed_store_normalization'] = normalized
    census_store = Path(normalized['path'])
    (output / 'typed-store').mkdir()
    typed_store = output / 'typed-store/store.sqlite'
    shutil.copy2(census_store, typed_store)
    if identity.sha256(typed_store) != identity.sha256(census_store):
        raise ValueError('public typed proof copy differs from known-Stop normalized export')
    transcript = script(output, 'acknowledged-topology.tsv', context_transcript(case, prepared, graph, modes_file))
    argv = [build['binaries']['runtime']['path'], 'verify-topology', '--socket', build['socket'],
        '--volume', row['clone']['volume'], '--daemon', build['binaries']['daemon']['path'],
        '--manifest', prepared['provision']['manifest'], '--sealed', str(typed_store),
        '--case', case['v016_case'], '--receipt', str(output / 'graph.events.jsonl'),
        '--history-file', str(transcript), '--uid', str(prepared['source_uid']), '--gid', str(prepared['source_gid'])]
    observed = receipts.command(argv, output, 'public-topology-proof', operation_deadline(deadline, 120) - time.monotonic())
    events = [json.loads(line) for line in Path(observed['stdout']).read_text().splitlines()]
    completed = [event for event in events if event['event'] == 'workspace_verified']
    if len(completed) != 1 or events[-1]['event'] != 'finished' or completed[0]['fields'].get('status') != 'PASS':
        raise ValueError('complete independent public topology proof and known exit required')
    fields = completed[0]['fields']
    selected = {(item['role'], item['index']) for item in prepared['context_checkpoints'] if item['index'] > 0}
    roots = [event for event in events if event['event'] == 'topology_root_verified']
    if {(event['fields']['role'], int(event['fields']['local'])) for event in roots} != selected:
        raise ValueError('exact original selected payload checkpoint proof required')
    tuples = [{'commit_id': record['commit']['fields']['commit_id'],
               'layer_stack_id': record['commit']['fields']['stack'], 'root_id': record['commit']['fields']['root'],
               'parent_commit_id': None if record['commit']['fields']['parent'] == '-' else record['commit']['fields']['parent'],
               'base_layer_id': record['commit']['fields']['base_layer']}
              for branch in graph['branches'].values() for record in branch['commits']]
    completion, runtime_events = output / 'closed-store-export.completion.json', output / 'runtime.events.jsonl'
    custody = {'custody': row['custody'], 'container': runtime.container, 'volume': row['clone']['volume'],
        'remote_source': '/layerfs-store/global/store.sqlite', 'local_source': str(raw),
        'source_sha256': identity.sha256(raw), 'source_size': raw.stat().st_size,
        'prepared_manifest': prepared['provision']['manifest'],
        'prepared_manifest_sha256': identity.sha256(prepared['provision']['manifest']),
        'transcript': str(transcript), 'transcript_sha256': identity.sha256(transcript),
        'export_completion': str(completion), 'export_completion_sha256': identity.sha256(completion),
        'runtime_events': str(runtime_events), 'runtime_events_sha256': identity.sha256(runtime_events),
        'normalization': {'receipt': normalized['receipt'], 'receipt_sha256': normalized['receipt_sha256']}}
    census = oracle.graph_commit_census(census_store, tuples, fields, custody)
    if time.monotonic() >= deadline:
        raise TimeoutError('original topology proof deadline reached during global census')
    receipts.write_new(output / 'global-topology-census.json', census)
    row['topology'].update(public_proof=events, global_census=census, transcript=str(transcript),
                           transcript_sha256=identity.sha256(transcript))
    return {'status': 'PASS', 'scope': case['oracle']['scope'], 'selected_roots': roots, 'global_census': census}


def context_observations(runtime, row, build, output, deadline):
    docker = ['docker', '--host', 'unix://' + build['socket']]
    logs = receipts.command([*docker, 'logs', '--timestamps=false', runtime.container], output, 'daemon-logs',
                            operation_deadline(deadline, 15) - time.monotonic())
    groups = {}
    for path in (logs['stdout'], logs['stderr']):
        groups.update(cell_runner.telemetry(path))
    words = lambda value: [int(value[index:index + 16], 16) for index in range(0, 64, 16)]
    scopes = {tuple(words(event['fields']['scope'])) for event in runtime.rows
              if event['event'] == 'control_origin' and event['fields'].get('scope')}
    scopes.add(tuple(words(runtime.scope)))
    if any(tuple(group[0]['daemon']) != tuple(words(runtime.daemon_instance)) or tuple(group[0]['scope']) not in scopes
           for group in groups.values()):
        raise ValueError('context numeric daemon/public channel scope differs from authentication')
    row['numeric_groups'] = list(groups.values())
    row['counts'] = {'requests': 'UNAVAILABLE', 'owner_jobs': 'UNAVAILABLE', 'statements': 'UNAVAILABLE'}
    row['counts_scope'] = 'actual raw numeric groups retained; independent concurrent channel cumulative attribution is not guessed or summed twice'
    try:
        priced = context_numeric_counts(groups, runtime.rows)
        row.update(counts=priced['totals'], phase_counts=priced, counts_scope=priced['scope'])
    except (KeyError, TypeError, ValueError) as error:
        row['numeric_attribution'] = {'status': 'UNAVAILABLE', 'reason': str(error),
            'scope': 'complete raw framing retained; no fabricated zero, interval, duplicated daemon delta or partial-call inference'}
    cell_runner.snapshot_observations(runtime, row['observations'])
    cell_runner.ingest_observations(groups, row['observations'], row['cache'])


def one_context_case(family, case, prepared_folder, build_folder, output, *, preparation_only=False):
    """One exact original graph with real concurrent role-local SDK worker loops."""
    started_ns = time.monotonic_ns()
    current, build = identity.source_identity(), identity.load_build(build_folder)
    layout = context_layout(case)
    prepared = fixtures.load(prepared_folder, case['fixture']['recipe'])
    helper_admission = fixtures.validate_runtime_helpers(case, prepared, build)
    bodies = context_bodies(case, prepared)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    treatment = {'family': family, 'case': case, 'fixture': prepared['fixture']['fixture_sha256'],
        'product': current['product_tree'], 'bodies': bodies, 'helpers': prepared['helpers']['files'],
        'binaries': {name: value['sha256'] for name, value in build['binaries'].items()},
        'engine': identity.sha256(__file__), 'image': identity.IMAGE}
    claim = receipts.sample_claim_key(treatment, current["source_commit"])
    claims = identity.ROOT / 'benchmark-results/fs-bench-pro/claims'
    claims.mkdir(parents=True, exist_ok=True)
    if not preparation_only:
        with (claims / claim).open('x') as stream:
            stream.write(str(output) + '\n')
    row = {'schema': 'fs-bench-pro-workspace-family-v1', 'family': family, 'case': case['id'],
        'source_commit': current['source_commit'], 'product_tree': current['product_tree'], 'identity': current,
        'build': str(Path(build_folder).resolve()), 'prepared': str(Path(prepared_folder).resolve()),
        'daemon_sha256': build['binaries']['daemon']['sha256'], 'runtime_sha256': build['binaries']['runtime']['sha256'],
        'image': identity.IMAGE, 'status': 'NOT_RUN', 'functional_status': 'NOT_RUN', 'proof_status': 'NOT_RUN',
        'counts': {}, 'phases': {'mount_ns': 0, 'command_ns': 0, 'commit_ns': 0, 'unmount_ns': 0}, 'observations': {},
        'cache_class': case['cache_class'], 'cache': {'class': case['cache_class'], 'status': 'INELIGIBLE',
            'declaration': 'original branch/worker graph on fresh independent writable clone; setup and own-write coldness unverified; no warmup or cold claim'},
        'declared_limit_ns': 'N/A' if preparation_only else case['budget']['command_ms'] * 1_000_000,
        'verifier_limit_ns': case['budget']['verifier_ms'] * 1_000_000,
        'global_profile': 'Disposable/WAL/OFF', 'overlay_profile': 'MEMORY/OFF/EXCLUSIVE', 'construction_workers': 1,
        'durable': 'NOT_RUN — disabled by owner until explicit reauthorization', 'claim': claim,
        'attempted_operation_count': 0, 'completed_operation_count': 0, 'sample_count': 0,
        'cleanup': 'UNAVAILABLE', 'proof_only': False, 'performance_mode': 'single original performance attempt',
        'interference': current.get('cross_worktree_interference'), 'helper_admission': helper_admission,
        'topology': {'branches': {}, 'rounds': []}, 'original_graph': layout}
    if preparation_only:
        row.update(schema='fs-bench-pro-prepared-producer-attempt-v1', setup_only=True,
                   performance_mode='setup-only; no performance sample', sample_count=0)
    receipts.write_new(output / 'selection.json', row)
    runtime = None
    active = {}
    modes = {role: {} for role in layout['roles']}
    graph = row['topology']
    proof_start, deadlines = None, None
    try:
        row['clone'] = fixtures.clone(prepared, output / 'clone', build)
        environment = script(output, 'environment.txt', ''.join(name + '=' + value + '\n' for name, value in workloads.ENV.items()))
        argv = [build['binaries']['runtime']['path'], 'serve', '--socket', build['socket'],
            '--volume', row['clone']['volume'], '--daemon', build['binaries']['daemon']['path'],
            '--manifest', prepared['provision']['manifest'], '--receipt', str(output / 'runtime.events.jsonl'),
            '--uid', str(prepared['source_uid']), '--gid', str(prepared['source_gid']),
            '--environment-file', str(environment), '--observation-scope', secrets.token_hex(32), '--case', case['v016_case']]
        runtime = cell_runner.EventProcess(argv, output, 'runtime')
        runtime.event('protocol_ready', time.monotonic() + 15)
        row['container'] = runtime.container
        if runtime.container is None:
            raise ValueError('original context container acknowledgement unavailable')
        row['container_profile'] = history_container_profile(runtime, build, output)
        row['staging'] = fixtures.stage(runtime.container, prepared, output / 'staging', build)
        row['ordinary_resource_guards'] = {'before': ordinary_resource_guard(runtime, build, output, 'ordinary-before'), 'steps': []}
        initial = next(event['fields'] for event in runtime.rows if event['event'] == 'history_initial_root')
        graph['branches']['initial'] = {'branch_id': initial['branch_id'], 'name': initial['name'],
            'stack': initial['stack'], 'base_layer': initial['base_layer'], 'initial_parent': '-',
            'initial_root': initial['root'], 'final_head': '-', 'final_root': initial['root'],
            'source_role': None, 'source_local': 0, 'commits': []}
        row['setup_ns'] = time.monotonic_ns() - started_ns
        performance_start = time.monotonic()
        performance = context_deadlines(case, performance_start, phase='performance')
        row.update(attempted_operation_count=1, sample_count=0 if preparation_only else 1)
        for group_number, roles in enumerate(layout['groups'], 1):
            for role in roles:
                specification = next(branch for branch in layout['branches'] if branch['role'] == role)
                context_fork(runtime, case, specification, graph, output, performance['work'])
                key = secrets.token_hex(32)
                mounted = context_send(runtime, 'mount-branch', key, role, deadline=performance['work'])
                active[role] = key
                row['phases']['mount_ns'] += mounted['span']['duration_ns']
            segments = layout['segments'] or [[1, next(branch['count'] for branch in layout['branches'] if branch['role'] == roles[0])]]
            for segment_number, (first, last) in enumerate(segments, 1):
                round_ = context_round(runtime, case, graph, active, roles, first, last, bodies, modes, output,
                                       f'group-{group_number}-segment-{segment_number}', performance['work'])
                graph['rounds'].append(round_)
                for record in round_['records']:
                    row['phases']['command_ns'] += record['command']['span']['duration_ns']
                    row['phases']['commit_ns'] += record['commit']['span']['duration_ns']
                row['ordinary_resource_guards']['steps'].append(ordinary_resource_guard(runtime, build, output,
                    f'ordinary-group-{group_number}-segment-{segment_number}', row['ordinary_resource_guards']['before'],
                    operation_deadline(performance['work'], 15) - time.monotonic()))
                if layout['segments'] and segment_number == 1 and case['topology_schedule'].get('discard_reopen'):
                    witness = prepared['original_discard_witness']
                    if witness is None or witness['role'] != '0':
                        raise ValueError('authenticated original two-worker discard witness required')
                    body = '/bin/bash /code/workload.sh witness ' + shlex.join([case['v016_case'], '0', witness['path'], witness['hex']])
                    event = runtime.send('command', active['0'], script(output, 'discard-witness.sh', body), deadline=performance['work'])
                    old = active.pop('0')
                    ended = context_end(runtime, old, row, performance['cleanup'])
                    row['phases']['unmount_ns'] += ended['span']['duration_ns']
                    new = secrets.token_hex(32)
                    mounted = context_send(runtime, 'mount-branch', new, '0', deadline=performance['work'])
                    active['0'] = new
                    row['phases']['mount_ns'] += mounted['span']['duration_ns']
                    graph['discard'] = {'witness': event, 'old_key': old, 'new_key': new,
                        'branch_id': graph['branches']['0']['branch_id'], 'at_local': last,
                        'peer_state': 'already committed; no dirty-stage6 hold', 'created_commits': 0}
            for role in roles:
                snapshot = runtime.send('snapshot', active[role], deadline=performance['work'])
                graph['branches'][role]['runtime_snapshot'] = snapshot
                ended = context_end(runtime, active.pop(role), row, performance['cleanup'])
                row['phases']['unmount_ns'] += ended['span']['duration_ns']
        all_commits = [record for branch in graph['branches'].values() for record in branch['commits']]
        if len(all_commits) != layout['total']:
            raise ValueError('every original Created acknowledgement required')
        row['complete_wall_ns'] = row['phases']['command_ns'] + row['phases']['commit_ns']
        row['performance_external_wall_ns'] = int((time.monotonic() - performance_start) * 1e9)
        row['timing_scope'] = 'summed complete current ordinary helper/range-edit commands and public Commits; overlaps counted in the sum as the original pure_call_sum; setup/Fork/mount/observers/teardown excluded; external whole-graph wall separately retained'
        graph['overlap'] = context_overlap(all_commits)
        if case.get('topology_schedule', {}).get('actual_commit_overlap_required') and not graph['overlap']['overlap_rounds']:
            raise ValueError('original concurrent topology has no observed public Commit overlap')
        row['cleanup'] = 'Gone'
        context_observations(runtime, row, build, output, performance['cleanup'])
        proof_start = time.monotonic_ns()
        deadlines = context_deadlines(case, time.monotonic())
        modes_file = script(output, 'observed-context-modes.tsv', context_modes_text(modes, layout['roles'])) if case.get('m1_schedule') else None
        if modes_file:
            receipts.command(['docker', '--host', 'unix://' + build['socket'], 'cp', str(modes_file),
                runtime.container + ':/code/context/observed-modes.tsv'], output, 'created-modes-stage',
                operation_deadline(deadlines['work'], 15) - time.monotonic())
        graph['native_proofs'] = []
        for role in layout['roles']:
            branch = graph['branches'][role]
            graph.setdefault('sdk_history', {})[role] = context_history(runtime, role, branch, graph, output, deadlines['work'])
            index = len(branch['commits'])
            checkpoint = next(item for item in prepared['context_checkpoints'] if item['role'] == role and item['index'] == index)
            key = secrets.token_hex(32)
            context_send(runtime, 'mount-branch', key, role, deadline=deadlines['work'])
            active[role] = key
            body = shlex.join(['/code/writers/recipe', 'verify-context', case['v016_case'], role, str(index), '.',
                              '/code/context/observed-modes.tsv' if modes_file else '-'])
            command = runtime.send('verify', key, script(output, f'native-proof-{role}.sh', body), deadline=deadlines['work'])
            proof = context_native_receipt(case, role, index, command, checkpoint, modes_file)
            graph['native_proofs'].append({'role': role, 'index': index, 'proof': proof})
            context_end(runtime, active.pop(role), row, deadlines['cleanup'])
        row['ordinary_resource_guards']['after_native_proof'] = ordinary_resource_guard(runtime, build, output,
            'ordinary-after-native-proof', row['ordinary_resource_guards']['before'],
            operation_deadline(deadlines['work'], 15) - time.monotonic())
        runtime.send('observe', deadline=deadlines['cleanup'])
        runtime.send('stop', deadline=deadlines['cleanup'])
        runtime.event('finished', deadlines['cleanup'])
        if runtime.process.wait(timeout=operation_deadline(deadlines['cleanup'], 1) - time.monotonic()) != 0:
            raise ValueError('original runtime exit differs after acknowledged Stop')
        row['custody'] = 'KNOWN_STOP'
        row['verification'] = context_graph_proof(case, prepared, graph, runtime, row, build, output, modes_file, deadlines['work'])
        row.update(status='INELIGIBLE', functional_status='PASS', proof_status='PASS', completed_operation_count=1,
                   resource_removal_pending=True, tag='complete original graph, native/public/global census proof and clean close; paid cold inputs and cross-worktree isolation unverified')
    except BaseException as error:
        row.update(status='FAIL', functional_status='FAIL', proof_status='FAIL' if proof_start else 'NOT_RUN',
                   original_failure=str(error), failure_type=type(error).__name__, leaked_mount_keys=dict(active))
        if runtime is None:
            runtime = getattr(error, 'event_process', None)
        if runtime is not None:
            row['retained_host_custody'] = runtime.retain(error)
            row['container'] = runtime.container
    finally:
        if runtime is not None:
            for handle in (runtime.selector, runtime.raw, runtime.stderr, getattr(runtime.process, 'stdin', None), getattr(runtime.process, 'stdout', None)):
                if handle is not None:
                    try:
                        handle.close()
                    except BaseException as error:
                        row.setdefault('independent_close_failures', []).append(str(error))
                        row['status'] = 'FAIL'
        if proof_start is not None:
            row['proof_wall_ns'] = time.monotonic_ns() - proof_start
        row['evidence'] = str(output.relative_to(identity.ROOT.resolve()))
        io_observer.attach(output, row)
        if deadlines is not None:
            if time.monotonic() >= deadlines['cleanup']:
                row.update(status='FAIL', proof_status='FAIL', tag='original complete proof/cleanup deadline reached before publication')
            row.update(receipts.finalize_guarded(output, row, deadlines['publication'], scope=receipts.HISTORY_PUBLICATION_SCOPE))
        else:
            receipts.write_new(output / 'receipt.json', row)
            receipts.manifest(output)
    return row


def prepare_history_producer(producer_family, producer_case, genesis_prepared_folder, build_folder, fresh_output):
    """New original producer setup; it never consumes an earlier measured sample."""
    output = Path(fresh_output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if producer_case.get('branch_schedule'):
        if producer_case['branch_schedule']['kind'] not in ('compact-convergent', 'compact-descendant'):
            raise ValueError('access original compact producer required')
    elif producer_case['id'] not in ('v016-history-boundary-cycle-k100-v1', 'v016-history-namespace-inode-k100-v1'):
        raise ValueError('original access producer is outside the four frozen dependencies')
    row = one_family_case(producer_family, producer_case, genesis_prepared_folder, build_folder,
                          output / 'attempt', preparation_only=True)
    if row.get('publication_guard'):
        receipts.acknowledge_guarded(output / 'attempt', row)
    receipts.verify_manifest(output / 'attempt')
    original = json.loads((output / 'attempt/receipt.json').read_text())
    effective = receipts._publication_overlay(output / 'attempt', original, original)
    if (effective.get('status') == 'FAIL' or effective.get('functional_status') != 'PASS'
            or effective.get('proof_status') != 'PASS' or effective.get('custody') != 'KNOWN_STOP'
            or effective.get('cleanup') != 'Gone' or effective.get('setup_only') is not True
            or effective.get('sample_count') != 0):
        raise RuntimeError('fresh original producer setup failed; exact resources and attempt receipt retained')
    initial_prepared = Path(genesis_prepared_folder).resolve()
    prepared = fixtures.load(initial_prepared, producer_case['fixture']['recipe'])
    if producer_case.get('branch_schedule'):
        graph = row['topology']
        checkpoints = prepared['context_checkpoints']
    else:
        initial = next(json.loads(line)['fields'] for line in (output / 'attempt/runtime.events.jsonl').read_text().splitlines()
                       if json.loads(line)['event'] == 'history_initial_root')
        records = row['history']['commits']
        last = records[-1]['commit']['fields']
        graph = {'branches': {'main': {'branch_id': initial['branch_id'], 'name': initial['name'],
            'stack': initial['stack'], 'base_layer': initial['base_layer'], 'initial_parent': '-',
            'initial_root': initial['root'], 'final_head': last['commit_id'], 'final_root': last['root'],
            'source_role': None, 'source_local': 0, 'commits': records}}}
        checkpoints = [{**state, 'role': 'main'} for state in prepared['history_states']]
    transcript = script(output, 'producer-topology.tsv', context_transcript(producer_case,
        {'context_checkpoints': checkpoints}, graph))
    normalized = row['closed_store_normalization']
    sealed = Path(normalized['path'])
    if any(Path(str(sealed) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('closed producer dependency must be a standalone WAL Store')
    acknowledgements = [{'role': role, 'local': record['index'],
        'commit_id': record['commit']['fields']['commit_id'], 'layer_stack_id': record['commit']['fields']['stack'],
        'root_id': record['commit']['fields']['root'],
        'parent_commit_id': None if record['commit']['fields']['parent'] == '-' else record['commit']['fields']['parent'],
        'base_layer_id': record['commit']['fields']['base_layer']}
        for role, branch in graph['branches'].items() for record in branch['commits']]
    current = row['identity']
    runtime_events, exported = output / 'attempt/runtime.events.jsonl', output / 'attempt/closed-store-export.completion.json'
    record = {'schema': 'fs-bench-pro-closed-history-producer-v1', 'status': 'PASS', 'producer_case': producer_case['id'],
        'producer_family': producer_family, 'source_commit': current['source_commit'], 'source_tree': current['source_tree'],
        'product_tree': current['product_tree'], 'seed': 1, 'setup_only': True, 'sample_count': 0,
        'initial_prepared': str(initial_prepared), 'manifest': prepared['provision']['manifest'],
        'manifest_sha256': identity.sha256(prepared['provision']['manifest']), 'sealed_store': str(sealed),
        'store_sha256': identity.sha256(sealed), 'transcript': str(transcript), 'transcript_sha256': identity.sha256(transcript),
        'graph': graph, 'acknowledgements': acknowledgements,
        'custody': {'state': 'KNOWN_STOP', 'all_workspaces_gone': True, 'active_executions': 0,
            'active_execution_scope': 'explicit stopped container; no live runtime process; ordinary commands were unregistered',
            'container': row['container'], 'volume': row['clone']['volume'],
            'runtime_events': str(runtime_events), 'runtime_events_sha256': identity.sha256(runtime_events),
            'export_completion': str(exported), 'export_completion_sha256': identity.sha256(exported)},
        'raw_export': str(output / 'attempt/graph-store'), 'normalization': normalized, 'helpers': prepared['helpers'],
        'attempt_receipt': str(output / 'attempt/receipt.json'), 'attempt_receipt_sha256': identity.sha256(output / 'attempt/receipt.json'),
        'attempt_manifest': str(output / 'attempt/manifest.json'), 'attempt_manifest_sha256': identity.sha256(output / 'attempt/manifest.json')}
    # Known return and authenticated attempt publication precede administration.
    # Seal the parent dependency after this separate receipt subtree is complete.
    removal = dispose_family_resources(output / 'attempt', row)
    record['resource_removal'] = removal
    record['resource_disposition'] = row.get('resource_disposition', 'UNAVAILABLE')
    summary = output / 'producer-summary.json'
    receipts.write_new(summary, record)
    receipts.manifest(output)
    record.update(receipt=str(summary), receipt_sha256=identity.sha256(summary))
    return record


def context_numeric_counts(groups, events):
    """One daemon interval; exact Resources costs across authenticated channels."""
    decoded = {counts.identity(group): counts.decode(group) for group in groups.values()}
    if len(decoded) != len(groups):
        raise ValueError('duplicate original concurrent numeric identity')
    word_tuple = lambda value: tuple(int(value[index:index + 16], 16) for index in range(0, 64, 16))
    origins = [event for event in events if event['event'] == 'control_origin']
    previous, scopes = {}, {}
    for event in origins:
        fields = event['fields']
        channel, scope = str(fields.get('channel', 0)), fields.get('scope')
        if channel in scopes or scope is None or fields['control_send_records'] != 1:
            raise ValueError('one explicit Hello origin per authenticated context channel required')
        scopes[channel], previous[channel] = word_tuple(scope), 1
    if not scopes or len(set(scopes.values())) != len(scopes):
        raise ValueError('independent concurrent public observation scopes required')
    mapped, correlation = set(), []
    for event in events:
        fields = event.get('fields', {})
        if 'control_send_records_before' not in fields:
            continue
        before, after = fields['control_send_records_before'], fields['control_send_records_after']
        channel = str(fields.get('channel', 0))
        if (channel not in previous or type(before) is not int or type(after) is not int
                or before != previous[channel] or fields.get('scope') is not None
                and word_tuple(fields['scope']) != scopes[channel]):
            raise ValueError('exact per-channel original completed send ranges differ')
        codes = counts.OPERATIONS.get(event['event'])
        if codes is None:
            if event['event'] == 'command':
                receive_before = fields.get('control_receive_records_before')
                receive_after = fields.get('control_receive_records_after')
                if (fields.get('scope') is None or after != before
                        or type(receive_before) is not int or type(receive_after) is not int
                        or receive_before != before or receive_after != after):
                    raise ValueError('authenticated ordinary command must retain an exact empty Control range')
                codes = ()
            else:
                if event['event'] not in ('fork', 'history_finished') or after != before + 1:
                    raise ValueError('unclassified original context control range')
                previous[channel] = after
                continue
        if after - before != len(codes):
            raise ValueError('exact successful facade call geometry differs')
        identities = []
        for call, code in zip(range(before + 1, after + 1), codes):
            matches = [key for key, value in decoded.items() if key[1] == scopes[channel]
                       and key[2] == call and value['operation_tag'] == code]
            if len(matches) != 1 or matches[0] in mapped:
                raise ValueError('original context observed call missing, duplicated or substituted')
            identities.append(matches[0]); mapped.add(matches[0])
        correlated = {'event_sequence': event['sequence'], 'event': event['event'],
                      'key': fields.get('key'), 'channel': channel, 'identities': identities}
        if event['event'] == 'command':
            correlated['control_range'] = {'scope': fields['scope'], 'send': [before, after],
                'receive': [receive_before, receive_after],
                'classification': 'authenticated ordinary command with no Control call'}
        correlation.append(correlated)
        previous[channel] = after
    if mapped != set(decoded):
        raise ValueError('original concurrent numeric groups are not fully acknowledged')
    mounts = [item for item in correlation if item['event'] == 'mount']
    ends = [item for item in correlation if item['event'] == 'workspace_status']
    if not mounts or not ends:
        raise ValueError('prospective whole-graph mount/status counter endpoints unavailable')
    begin, end = mounts[0], ends[-1]
    first, last = decoded[begin['identities'][-1]], decoded[end['identities'][-1]]
    if first['identity'][0] != last['identity'][0] or begin['event_sequence'] >= end['event_sequence']:
        raise ValueError('exact whole-graph daemon/counter endpoint order differs')
    interval = [decoded[key] for item in correlation if begin['event_sequence'] < item['event_sequence'] <= end['event_sequence']
                for key in item['identities']]
    if not interval or any(not row.get('observer', {}).get('completion_available') for row in interval):
        raise ValueError('exact completed Resources cost of every concurrent observer required')
    owner_count = 'jobs' if first.get('service_schema') == 'issue321-direct-workspace' else 'admitted'
    raw_owner = counts.difference(first['owner'], last['owner'], (owner_count,))[owner_count]
    observer_jobs = sum(row['observer']['jobs'] for row in interval) if owner_count == 'jobs' else len(interval)
    sql = [counts.difference(left, right, ('executions',))['executions']
           for left, right in zip(first['sql_foreground'], last['sql_foreground'])]
    observer_sql = sum(row['observer']['sql']['executions'] for row in interval)
    if raw_owner < observer_jobs or sql[0] < observer_sql:
        raise ValueError('exact observer costs exceed original whole-daemon cumulative delta')
    # Kernel counters belong to individual mount connections, not the daemon.
    # Each last acknowledged Unmount snapshot retains that connection's totals.
    kernel = []
    owners = set()
    for item in correlation:
        if item['event'] != 'unmount':
            continue
        value = decoded[item['identities'][-1]]
        native, opcodes = value.get('native'), value.get('opcodes')
        if native is None or opcodes is None or native['owner_id'] in owners:
            raise ValueError('distinct terminal mount opcode snapshots unavailable')
        rows = opcodes['by_opcode']
        if any(type(number) is not int or number == 2**64 - 1 for number in rows):
            raise ValueError('original mount opcode counter saturated/unavailable')
        owners.add(native['owner_id']); kernel.append({'key': item['key'], 'native_owner_id': native['owner_id'], 'requests': sum(rows)})
    if len(kernel) != len(mounts):
        raise ValueError('every measured connection terminal request census required')
    totals = {'requests': sum(row['requests'] for row in kernel), 'owner_jobs': raw_owner - observer_jobs,
              'statements': sum(sql) - observer_sql}
    return {'totals': totals, 'scope': 'one daemon cumulative first-ready to last measured Status interval; every acknowledged channel Resources cost subtracted exactly once; per-connection terminal opcode totals include original witness/reopen',
            'raw': {'owner_jobs': raw_owner, 'statement_executions_by_family': sql},
            'observer': {'jobs': observer_jobs, 'statement_executions': observer_sql},
            'kernel_connections': kernel, 'correlation': correlation,
            'endpoints': {'before': begin, 'end': end}, 'source': counts.SCHEMA_SOURCE}
