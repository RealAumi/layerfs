"""Public ProjectApi provisioning through the existing release runtime."""
import json
import hashlib
import os
from pathlib import Path
import time

from . import identity, io_observer, receipts


class ParityFailure(ValueError):
    """Failed case guards with complete retained family parity evidence."""
    def __init__(self, result, output):
        self.result = result
        self.output = Path(output)
        first = next(row for row in result["cases"] if row["status"] == "FAIL")
        super().__init__(f"{result['family']} parity failed: {first['reason']}; see {self.output / 'parity.json'}")


def audit_membership(run, build_folder, output):
    """Supplement prior byte proofs with a new census; original exports stay intact."""
    import shutil
    from . import fixtures
    current = identity.source_identity()
    build = identity.load_build(build_folder)
    selection, recorded = receipts.load_run(run)
    if selection["family"] not in fixtures.WORKSPACE_FAMILIES:
        raise ValueError("membership audit needs a complete mounted-family run")
    output = Path(output).resolve()
    if not output.is_relative_to((identity.ROOT / "benchmark-results/fs-bench-pro").resolve()):
        raise ValueError("audit output must be under benchmark-results/fs-bench-pro")
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "fs-bench-pro-membership-audit-v1", "status": "PASS",
              "identity": current, "original_run": str(Path(run).resolve()),
              "original_source_commit": selection["source_commit"], "samples": 0,
              "runtime_sha256": build["binaries"]["runtime"]["sha256"], "cases": []}
    for case in selection["cases"]:
        folder = output / case["id"]
        folder.mkdir()
        row = {"case": case["id"], "status": "FAIL", "samples": 0}
        try:
            old = recorded[case["id"]]
            if old["proof_status"] != "PASS" or old["custody"] != "KNOWN_STOP" or old["cleanup"] != "Gone":
                raise ValueError("original complete byte proof and terminal custody unavailable")
            if old["product_tree"] != current["product_tree"]:
                raise ValueError("membership audit cannot substitute a changed product")
            prepared = fixtures.load(old["prepared"], case["fixture"]["recipe"])
            original = Path(run).resolve() / case["id"]
            sealed = original / "graph-store/store.sqlite"
            before = identity.sha256(sealed)
            copied = folder / "store.sqlite"
            shutil.copy2(sealed, copied)
            if identity.sha256(copied) != before:
                raise ValueError("offline census copy differs from retained closed Store")
            row.update(original_store_sha256=before, acknowledged_root=old["commit"]["fields"]["root"])
            argv = [build["binaries"]["runtime"]["path"], "verify-membership", "--socket", build["socket"],
                    "--volume", "unused-offline-census", "--daemon", build["binaries"]["daemon"]["path"],
                    "--manifest", prepared["provision"]["manifest"], "--sealed", str(copied),
                    "--case", case["v016_case"], "--receipt", str(folder / "census.events.jsonl"),
                    "--uid", str(prepared["source_uid"]), "--gid", str(prepared["source_gid"])]
            row["attempt"] = receipts.command(argv, folder, "membership-census", 120,
                environment={**os.environ, "LAYERFS_CONSTRUCTION_WORKERS": "1"})
            events = [json.loads(line) for line in (folder / "census.events.jsonl").read_text().splitlines()]
            proofs = [event for event in events if event["event"] == "workspace_verified"]
            if len(proofs) != 1 or events[-1]["event"] != "finished" or proofs[0]["fields"]["root"] != row["acknowledged_root"]:
                raise ValueError("offline census root differs from exact original Commit acknowledgement")
            row.update(status="PASS", proof=proofs[0],
                       scope="exhaustive current inode-table census, complete paths/metadata/aliases; prior byte proof reused")
        except BaseException as error:
            row.update(original_failure=str(error), original_failure_type=type(error).__name__)
        finally:
            try:
                receipts.verify_manifest(Path(run) / case["id"])
            except BaseException as error:
                row.update(status="FAIL", independent_original_evidence_failure=str(error))
            receipts.write_new(folder / "audit.json", row)
            receipts.manifest(folder)
            result["cases"].append(row)
            if row["status"] != "PASS":
                result["status"] = "FAIL"
    receipts.write_new(output / "audit.json", result)
    receipts.manifest(output)
    return result


def provision(source, volume, folder, build):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    sealed, manifest = folder / "store.sqlite", folder / "installed.manifest"
    events = folder / "provision.events.jsonl"
    info = Path(source).stat()
    argv = [build["binaries"]["runtime"]["path"], "provision", "--socket", build["socket"],
            "--volume", volume, "--daemon", build["binaries"]["daemon"]["path"],
            "--manifest", str(manifest), "--receipt", str(events),
            "--uid", str(info.st_uid), "--gid", str(info.st_gid),
            "--source-copy", str(Path(source).resolve()), "--sealed", str(sealed),
            "--init-seconds", "120", "--image", identity.IMAGE]
    attempted = receipts.command(argv, folder, "sdk-provision", 120,
                                 environment={**os.environ, "LAYERFS_CONSTRUCTION_WORKERS": "1"})
    with events.open() as stream:
        rows = [json.loads(line) for line in stream]
    stopped = [row for row in rows if row["event"] == "setup_container_stopped"]
    if len(stopped) != 1 or not rows or rows[-1]["event"] != "finished":
        raise ValueError("original successful SDK provisioning/Stop acknowledgements missing")
    container = stopped[0]["value"]
    docker = ["docker", "--host", "unix://" + build["socket"]]
    status = receipts.command([*docker, "inspect", container, "--format", "{{.State.Running}}"],
                              folder, "setup-container-state", 15, allow_failure=True)
    missing = Path(status["stderr"]).read_text().strip()
    absent = {"Error: No such object: " + container, "error: no such object: " + container}
    if (status["exit_code"] != 1 or Path(status["stdout"]).read_text().strip()
            or missing not in absent):
        raise ValueError("acknowledged SDK close lacks exact independent deletion observation: " + container)
    result = {"schema": "fs-bench-pro-provision-v1", "status": "PASS", "volume": volume,
              "source": str(source), "sealed_store": str(sealed), "store_sha256": identity.sha256(sealed),
              "manifest": str(manifest), "manifest_sha256": identity.sha256(manifest),
              "global_profile": "Disposable/WAL/OFF", "overlay_profile": "MEMORY/OFF/EXCLUSIVE",
              "construction_workers": 1, "init_parallel_profile": "supported Project Init profile unchanged",
              "attempt": attempted, "events": str(events), "container": container,
              "container_disposition": "SDK close acknowledged stop/delete; exact container absence independently observed",
              "host_sqlite": "original host_init_setup event", "daemon_sqlite": "original install_setup event"}
    receipts.write_new(folder / "provision.json", result)
    return result



def fresh_init_start(case, prepared, build, output, row, *, deadline, host_rss_limit_bytes):
    """Retain the exact measured SealedProject for one later public install."""
    import uuid
    from . import workspace
    output = Path(output).resolve()
    volume = "layerfs-fsb-sample-" + uuid.uuid4().hex[:16]
    handle = {"runtime": None, "observer": None, "ack": None, "volume": volume,
              "host_manifest": output / "project.manifest", "sealed": output / "store.sqlite",
              "installed_manifest": output / "installed.manifest", "completed": False, "closed": False}
    row["clone"] = {"volume": volume, "clone_method": "fresh empty volume; exact actual measured Init installed once by public SDK"}
    receipts.write_new(output / "init-install-volume.json", {"volume": volume, "created_by_this_run": True,
        "scope": "empty owned sample backing created before imported paid Init launch; no Store/Init during setup",
        "failure_disposition": "retain failed/uncertain owned volume, no retry or inferred removal"})
    try:
        left = min(15, deadline - time.monotonic())
        if left <= 0:
            raise TimeoutError("fresh Init volume admission deadline expired")
        made = receipts.command(["docker", "--host", "unix://" + build["socket"], "volume", "create", volume],
                                output, "init-install-empty-volume", left)
        if Path(made["stdout"]).read_text().strip() != volume:
            raise ValueError("exact fresh owned Init volume acknowledgement differs")
        if time.monotonic() >= deadline:
            raise TimeoutError("fresh Init launch deadline expired")
        if os.environ.get("LAYERFS_CONSTRUCTION_WORKERS") != "1":
            raise ValueError("one explicit construction worker required")
        argv = [build["binaries"]["runtime"]["path"], "init-install", "--socket", build["socket"],
            "--volume", volume, "--daemon", build["binaries"]["daemon"]["path"],
            "--manifest", str(handle["host_manifest"]), "--installed-manifest", str(handle["installed_manifest"]),
            "--source-copy", prepared["source"], "--sealed", str(handle["sealed"]),
            "--case", case["v016_case"], "--init-seconds", "120", "--uid", str(prepared["source_uid"]),
            "--gid", str(prepared["source_gid"]), "--image", identity.IMAGE,
            "--receipt", str(output / "init-install.events.jsonl")]
        receipts.write_new(output / "init-install-attempt.json", {"argv": argv, "attempts": 1,
            "scope": "parent launch-to-project_init acknowledgement paid Init; later original public install distinct"})
        begun = time.monotonic_ns()
        runtime = workspace.cell_runner.EventProcess(argv, output, "init-install")
        handle["runtime"] = runtime
        observer = receipts.HostProcessObserver(runtime.process, output, "init-install", host_rss_limit_bytes)
        handle["observer"] = observer
        ack = runtime.event("project_init", deadline)
        acknowledged = time.monotonic_ns()
        handle.update(ack=ack, init_complete_wall_ns=acknowledged-begun,
                      init_acknowledged_ns=acknowledged)
        # Identity hashing occurs only after the paid acknowledgement boundary.
        observer.check()
        fields = ack["fields"]
        fixture = case["fixture"]
        entries = fixture.get("entries", fixture.get("paths"))
        if entries is None:
            entries = fixture["regular_files"] + fixture["directories_including_root"]
        if (fields.get("case") != case["v016_case"] or fields.get("profile") != "Disposable/WAL/OFF"
                or fields.get("files") != fixture["regular_files"] or fields.get("entries") != entries
                or fields.get("manifest_path") != str(handle["host_manifest"])
                or fields.get("manifest_sha256") != identity.sha256(handle["host_manifest"])
                or fields.get("logical_bytes") != handle["sealed"].stat().st_size
                or fields.get("allocated_bytes") != handle["sealed"].stat().st_blocks * 512
                or any(not isinstance(fields.get(key), str) or len(fields[key]) != length
                    or any(char not in "0123456789abcdef" for char in fields[key])
                    for key, length in (("root", 64), ("stack", 34), ("branch", 34)))):
            raise ValueError("actual fresh Init identity/counts/encoded host manifest differs")
        for suffix in ("-wal", "-shm", "-journal"):
            if Path(str(handle["sealed"])+suffix).exists():
                raise ValueError("actual consuming Init seal left sidecars")
        handle["store_sha256"] = identity.sha256(handle["sealed"])
        return handle
    except BaseException as error:
        if handle["runtime"] is None:
            handle["runtime"] = getattr(error, "event_process", None)
        fresh_init_close(handle, row, error)
        raise


def fresh_init_finish(handle, row, *, deadline):
    """Install the retained exact project once, then require original Stop/wait."""
    if handle.get("install_attempted"):
        raise ValueError("original install already attempted; no resend")
    if time.monotonic() >= deadline:
        raise TimeoutError("original install not sent after expired proof deadline")
    runtime, ack = handle["runtime"], handle["ack"]
    handle["install_attempted"] = True
    if runtime.process.stdin.write(b"install\n") != len(b"install\n"):
        raise RuntimeError("short original install write; outcome uncertain; no resend")
    runtime.process.stdin.flush()
    installed = runtime.event("project_install", deadline)
    handle["install_ack"] = installed
    fields, initial = installed["fields"], ack["fields"]
    cid = fields.get("container")
    if isinstance(cid, str) and len(cid) == 64 and all(char in "0123456789abcdef" for char in cid):
        row.setdefault("additional_containers", []).append(cid)
    else:
        raise ValueError("actual public installer canonical container acknowledgement differs")
    if (any(fields.get(key) != initial.get(key) for key in
            ("root", "stack", "branch", "profile", "host_sqlite", "logical_bytes"))
            or fields.get("profile") != "Disposable/WAL/OFF"
            or not isinstance(fields.get("daemon_sqlite"), str) or not fields["daemon_sqlite"]
            or fields.get("host_manifest_sha256") != initial["manifest_sha256"]
            or identity.sha256(handle["host_manifest"]) != initial["manifest_sha256"]
            or handle["installed_manifest"] == handle["host_manifest"]
            or fields.get("installed_manifest") != str(handle["installed_manifest"])
            or fields.get("installed_manifest_sha256") != identity.sha256(handle["installed_manifest"])
            or identity.sha256(handle["sealed"]) != handle["store_sha256"]
            or handle["sealed"].stat().st_size != initial["logical_bytes"]):
        raise ValueError("actual public installed manifest/Init identity/size binding differs")
    stopped = runtime.event("setup_container_stopped", deadline)
    if stopped.get("value") != cid:
        raise ValueError("actual original installer Stop container differs")
    runtime.event("finished", deadline)
    if any(sum(event.get("event") == name for event in runtime.rows) != 1
           for name in ("project_init", "project_install", "setup_container_stopped", "finished")):
        raise ValueError("exact one original Init/install/Stop/finished acknowledgement required")
    left = min(1, deadline-time.monotonic())
    if left <= 0 or runtime.process.wait(timeout=left) != 0:
        raise ValueError("original Init/install host wait unavailable or not known zero")
    observation = handle["observer"].finish()
    result = {"schema": "fs-bench-pro-public-init-install-v1", "status": "PASS", "volume": handle["volume"],
        "manifest": str(handle["installed_manifest"]), "manifest_sha256": fields["installed_manifest_sha256"],
        "host_manifest": str(handle["host_manifest"]), "host_manifest_sha256": initial["manifest_sha256"],
        "sealed_store": str(handle["sealed"]), "store_sha256": handle["store_sha256"],
        "global_profile": "Disposable/WAL/OFF", "container": cid, "container_disposition": "SDK close acknowledged stop/delete; borrowed shared Store volume retained",
        "events": str(runtime.child_event_receipts[0]) if getattr(runtime, "child_event_receipts", None) else str(runtime.folder / "init-install.events.jsonl"),
        "attempt": {"project_init": ack, "project_install": installed, "setup_container_stopped": stopped},
        "host_observation": observation, "host_sqlite": fields["host_sqlite"], "daemon_sqlite": fields["daemon_sqlite"],
        "scope": "actual retained measured SealedProject installed once through public SDK; no second Init or fabricated daemon metadata"}
    handle["completed"] = True
    row["installation"] = result
    row["clone"].update(store_sha256=handle["store_sha256"])
    return result


def fresh_init_observer_copy(handle, output, row, *, deadline):
    """Keep physical verification writes away from the held immutable SDK source."""
    import shutil
    if time.monotonic() >= deadline:
        raise TimeoutError("original typed Init copy proof deadline expired")
    original = handle["sealed"]
    before = identity.sha256(original)
    if before != handle["store_sha256"]:
        raise ValueError("held actual Init source changed before independent typed copy")
    folder = Path(output) / "typed-init"
    folder.mkdir(exist_ok=False)
    copied = folder / "store.sqlite"
    shutil.copy2(original, copied)
    copied_sha, after = identity.sha256(copied), identity.sha256(original)
    observation = {"source": str(original), "copy": str(copied), "source_sha256_before": before,
        "copy_sha256_before": copied_sha, "source_sha256_after_copy": after,
        "source_size": original.stat().st_size, "copy_size_before": copied.stat().st_size,
        "scope": "exact independent observer byte copy after paid Init ACK; typed proof may physically modify only its copy; copying charged to original proof budget"}
    row["init_observer_copy"] = observation
    receipts.write_new(folder / "copy.json", observation)
    if copied_sha != before or after != before or observation["copy_size_before"] != observation["source_size"]:
        raise ValueError("independent typed Init copy/source identity differs")
    if time.monotonic() >= deadline:
        raise TimeoutError("original typed Init copy exceeded proof work deadline")
    return copied


def fresh_init_close(handle, row, error=None):
    """Fence unknown host custody only; never infer or remove remote resources."""
    if handle.get("closed"):
        return
    handle["closed"] = True
    runtime, observer = handle.get("runtime"), handle.get("observer")
    failures = []
    if runtime is not None and (error is not None or not handle.get("completed")):
        cause = error or RuntimeError("original Init/install completion unknown")
        row["status"] = "FAIL"
        try:
            row["retained_init_install_host_custody"] = runtime.retain(cause)
        except BaseException as retaining:
            failures.append(str(retaining))
        cid = runtime.container
        if (isinstance(cid, str) and len(cid) == 64 and all(char in "0123456789abcdef" for char in cid)
                and cid not in row.setdefault("additional_containers", [])):
            row["additional_containers"].append(cid)
    if observer is not None:
        try:
            row["init_install_host_observation"] = observer.finish()
        except BaseException as observing:
            failures.append(str(observing))
    if runtime is not None:
        for value in (runtime.selector, runtime.raw, runtime.stderr,
                      getattr(runtime.process, "stdin", None), getattr(runtime.process, "stdout", None)):
            if value is not None:
                try:
                    value.close()
                except BaseException as closing:
                    failures.append(str(closing))
    if failures:
        row.update(status="FAIL", proof_status="FAIL")
        row.setdefault("independent_close_failures", []).extend(failures)
        if error is None:
            raise RuntimeError("original Init/install close observation failed: " + "; ".join(failures))


def init_treatment(family, case, prepared, build, current):
    """Exact executed Init scope; legacy namespace identity stays unchanged."""
    from . import fixtures
    treatment = {"family": family, "case": case, "fixture": prepared["fixture"],
                 "product": current["product_tree"], "runtime_sha256": build["binaries"]["runtime"]["sha256"],
                 "execution_files": {name: digest for name, digest in current["files"].items()
                    if name in ("benchmark/fs-bench-pro/engine/project.py", "benchmark/fs-bench-pro/engine/fixtures.py",
                                "benchmark/fs-bench-pro/engine/identity.py", "benchmark/fs-bench-pro/engine/recipes/namespace.rs")},
                 "workload_sha256": identity.sha256(identity.ROOT / "benchmark/fs-bench-pro/families" / family / "workload.sh"),
                 "image": identity.IMAGE}
    if family in fixtures.IMPORT_FAMILIES:
        for path in ("benchmark/fs-bench-pro/engine/workspace.py",
                     "benchmark/fs-bench-pro/engine/receipts.py"):
            treatment["execution_files"][path] = current["files"][path]
    return treatment


def one_init(case, prepared_folder, build_folder, output, *, family="init_namespace"):
    from . import fixtures
    current = identity.source_identity()
    build = identity.load_build(build_folder)
    prepared = fixtures.load(prepared_folder, case["fixture"]["recipe"])
    imported = family in fixtures.IMPORT_FAMILIES
    if family != "init_namespace" and not imported:
        raise ValueError("exact original Init family required")
    if imported:
        definition = {"family": family, "engine": "project"}
        fixtures.validate_import_qualification(case, fixtures.import_plan(definition, case), prepared["source_qualification"])
        if (prepared["family"], prepared["case"], prepared["schema"]) != (family, case["id"], "fs-bench-pro-prepared-native-import-v1"):
            raise ValueError("sealed independent source belongs to another import")
    proof_only = case.get("proof_only") is True
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    treatment = init_treatment(family, case, prepared, build, current)
    key = receipts.sample_claim_key(treatment, current["source_commit"])
    claims = identity.ROOT / "benchmark-results/fs-bench-pro/claims"
    claims.mkdir(parents=True, exist_ok=True)
    with (claims / key).open("x") as stream:
        stream.write(str(output) + "\n")
    row = {"family": family, "case": case["id"], "schema": "fs-bench-pro-project-init-v1",
           "source_commit": current["source_commit"], "product_tree": current["product_tree"], "identity": current,
           "image": identity.IMAGE, "daemon_sha256": build["binaries"]["daemon"]["sha256"],
           "runtime_sha256": build["binaries"]["runtime"]["sha256"], "status": "NOT_RUN",
           "declared_limit_ns": case["budget"]["command_ms"] * 1_000_000 if case["budget"]["command_ms"] is not None else "N/A",
           "verifier_limit_ns": case["budget"]["verifier_ms"] * 1_000_000,
           "phases": {}, "counts": {}, "observations": {}, "proof_status": "NOT_RUN", "cleanup": "UNAVAILABLE",
           "cache_class": "A", "cache": {"status": "INELIGIBLE", "reason": prepared["cache"] + "; host kernel metadata coldness unavailable"},
           "global_profile": "Disposable/WAL/OFF", "overlay_profile": "NOT_USED; host Init only",
           "construction_workers": 1, "init_parallel_profile": "supported public Project Init profile unchanged",
           "durable": "NOT_RUN — disabled by owner until explicit reauthorization",
           "counts_scope": "daemon request/owner-job/statement counts UNAVAILABLE: host Init launches no daemon or FUSE",
           "attempted_operation_count": 0, "completed_operation_count": 0, "sample_count": 0,
           "evidence": str(output.relative_to(identity.ROOT.resolve())), "claim": key,
           "prepared": str(Path(prepared_folder).resolve()), "build": str(Path(build_folder).resolve())}
    if proof_only:
        row.update(proof_only=True, performance_mode="verification-only", verification_attempt_count=1)
    if imported:
        row.update(counts_scope="paid host Init has no daemon/FUSE request, owner-job or statement observations; independent mounted verifier telemetry is separate",
                   overlay_profile="MEMORY/OFF/EXCLUSIVE in independent verifier only; no paid Init overlay",
                   interference=current.get("cross_worktree_interference","shared host/Docker VM/protected and own failed services, unquantified"))
    receipts.write_new(output / "selection.json", row)
    common = ["--socket", build["socket"], "--volume", "unused-host-init", "--daemon", build["binaries"]["daemon"]["path"],
              "--manifest", str(output / "project.manifest"), "--source-copy", prepared["source"],
              "--sealed", str(output / "store.sqlite"), "--case", case["id"], "--init-seconds", "120",
              "--uid", str(os.getuid()), "--gid", str(os.getgid()), "--image", identity.IMAGE]
    environment = {**os.environ, "LAYERFS_CONSTRUCTION_WORKERS": "1"}
    publication_stop = None
    interactive_init = None
    proof_started = time.monotonic_ns() if proof_only else None
    try:
        init_seconds = 41 if imported and proof_only else 120
        row.update(attempted_operation_count=1, sample_count=0 if proof_only else 1)
        if imported:
            interactive_init = fresh_init_start(case, prepared, build, output, row,
                deadline=time.monotonic()+init_seconds, host_rss_limit_bytes=2*1024**3)
            init = {"complete_wall_ns": interactive_init["init_complete_wall_ns"]}
            found = [interactive_init["ack"]]
        else:
            init = receipts.command([build["binaries"]["runtime"]["path"], "init", *common,
                                    "--receipt", str(output / "init.events.jsonl")], output, "public-init", init_seconds, environment=environment,
                                    host_rss_limit_bytes=2*1024**3 if imported else None, host_swap_guard=imported)
            events = [json.loads(line) for line in (output / "init.events.jsonl").read_text().splitlines()]
            found = [item for item in events if item["event"] == "project_init"]
            if len(found) != 1 or events[-1]["event"] != "finished":
                raise ValueError("original known Init/seal completion unavailable")
        row.update(complete_wall_ns=init["complete_wall_ns"], completed_operation_count=1,
                   phases={"command_ns": found[0]["span"]["duration_ns"]}, init=found[0])
        row["observations"] = {"store_" + name: {"status": "AVAILABLE", "value": found[0]["fields"][name],
            "provenance": "sealed Store stat before independent verification; sidecars absent after consuming seal"}
            for name in ("logical_bytes", "allocated_bytes")}
        row["proof_status"] = "FAIL"
        if imported:
            if any(found[0]["fields"][name] > 4*1024**3 for name in ("logical_bytes", "allocated_bytes")):
                raise RuntimeError("original main Store exceeds4GiB guard")
            if proof_started is None:
                proof_started = interactive_init["init_acknowledged_ns"]
            charged_ns = time.monotonic_ns()-proof_started
            from . import workspace
            deadlines = workspace.import_proof_deadlines(case, charged_ns)
            publication_stop = deadlines["publication"]
            row["proof_policy"] = deadlines
            seconds = min(row["verifier_limit_ns"]/1e9, deadlines["work"]-time.monotonic())
            if seconds <= 0:
                raise TimeoutError("original import proof work expired before typed verification")
        else:
            seconds = row["verifier_limit_ns"] / 1_000_000_000
        verification_common = list(common)
        if imported:
            index = verification_common.index("--source-copy")
            del verification_common[index:index+2]
            observer_copy = fresh_init_observer_copy(interactive_init, output, row, deadline=deadlines["work"])
            verification_common[verification_common.index("--sealed")+1] = str(observer_copy)
            seconds = min(row["verifier_limit_ns"]/1e9, deadlines["work"]-time.monotonic())
            if seconds <= 0:
                raise TimeoutError("original import proof expired after independent typed copy")
        verified = receipts.command([build["binaries"]["runtime"]["path"], "verify-init", *verification_common,
                                     "--receipt", str(output / "verify.events.jsonl")], output, "independent-verifier",
                                     seconds, environment=environment)
        events = [json.loads(line) for line in (output / "verify.events.jsonl").read_text().splitlines()]
        proof = [item for item in events if item["event"] == "project_verified"]
        if len(proof) != 1 or proof[0]["fields"]["status"] != "PASS" or events[-1]["event"] != "finished":
            raise ValueError("original independent proof completion unavailable")
        checked_stores = [output / "store.sqlite", observer_copy] if imported else [output / "store.sqlite"]
        sidecars = [str(store)+suffix for store in checked_stores for suffix in ("-wal", "-shm", "-journal")
                    if Path(str(store)+suffix).exists()]
        if sidecars:
            raise ValueError("original consuming Store close left sidecars: " + repr(sidecars))
        if imported:
            observation = row["init_observer_copy"]
            observation.update(source_sha256_after_proof=identity.sha256(interactive_init["sealed"]),
                copy_sha256_after_proof=identity.sha256(observer_copy), copy_size_after_proof=observer_copy.stat().st_size)
            observation["source_unchanged"] = observation["source_sha256_after_proof"] == interactive_init["store_sha256"]
            receipts.write_new(observer_copy.parent / "proof-copy-completion.json", observation)
            if not observation["source_unchanged"]:
                raise ValueError("held actual Init source changed during independent typed proof")
            if proof[0]["fields"].get("root") != found[0]["fields"]["root"]:
                raise ValueError("independent imported root differs from actual Init acknowledgement")
            row["verification"] = {"persisted": proof[0], "scope": case["oracle"]["scope"], "omissions": case["oracle"]["omissions"]}
            fresh_init_finish(interactive_init, row, deadline=deadlines["work"])
            workspace.verify_import_mount(case, prepared, build, output, row, deadlines)
            row.update(proof_status="PASS", proof_wall_ns=time.monotonic_ns()-proof_started,
                       status="PASS" if proof_only else "INELIGIBLE", functional_status="PASS",
                       tag="original full native/public storage proof and clean terminal custody; " + row["cache"]["reason"])
            return row
        row.update(proof_status="PASS", proof_wall_ns=verified["complete_wall_ns"], cleanup="SEALED_CLOSED; no mount",
                   status="INELIGIBLE", functional_status="PASS", tag=row["cache"]["reason"],
                   verification={"scope": case["oracle"]["scope"], "omissions": case["oracle"]["omissions"], "event": proof[0]},
                   custody="KNOWN_HOST_EXIT_AND_SEAL", resource_disposition="closed host sample Store retained as raw evidence; no Docker resources created")
    except BaseException as error:
        row.update(status="FAIL", original_failure_type=type(error).__name__, original_failure=str(error),
                   resource_disposition=row.get("resource_disposition", "original host files and declared independent verifier resources retained; no failed-operation replay"))
        for label, key_name in (("public-init", "complete_wall_ns"), ("independent-verifier", "proof_wall_ns")):
            path = output / (label + ".completion.json")
            if path.exists():
                row[key_name] = json.loads(path.read_text())["complete_wall_ns"]
    finally:
        if interactive_init is not None:
            try:
                fresh_init_close(interactive_init, row, RuntimeError(row.get("original_failure", "failed original proof")) if row["status"] == "FAIL" else None)
            except BaseException as closing:
                row.update(status="FAIL", proof_status="FAIL", original_close_failure=str(closing))
        row["timing_scope"] = ("parent launch-to-project_init acknowledgement; public Init/seal span retained separately as command_ns; empty-volume setup excluded; actual public installation and independent proof separate"
            if imported else "complete host Init child launch-to-exit; public Init/seal span is command_ns; fixture setup and independent verifier separate")
        if imported and proof_started is not None:
            row["proof_wall_ns"] = time.monotonic_ns()-proof_started
            row["proof_wall_scope"] = "independent typed reopen, sealed sample install, public Fork/fresh mounted native proof, original guards, End/Gone/Stop and observations; boundary includes its verification-only Init; publication separately bound"
        io_observer.attach(output, row)
        if imported and publication_stop is not None:
            row.update(receipts.finalize_guarded(output, row, publication_stop, scope=receipts.HISTORY_PUBLICATION_SCOPE))
        else:
            receipts.write_new(output / "receipt.json", row)
            receipts.manifest(output)
    return row


def parity_import(family, prepared_parent, output, build_folder):
    """Complete original native/import/storage scope; no performance sample."""
    from . import fixtures
    if build_folder is None:
        raise ValueError("qualified full native import build required")
    build = identity.load_build(build_folder)
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    registered = identity.reference_catalogue(identity.ROOT/"core/target/fs-bench-pro-catalogue")
    membership = {(row["family"],row["case"]) for row in registered}
    rows = []
    for case in family["cases"]:
        try:
            if (family["family"],case["v016_case"]) not in membership:
                raise ValueError("original import membership differs")
            plan = fixtures.import_plan(family,case)
            prepared = fixtures.load(Path(prepared_parent)/case["fixture"]["recipe"],case["fixture"]["recipe"])
            if (prepared["family"],prepared["case"],prepared["generator_sha256"]) != (family["family"],case["id"],build["binaries"]["workspace-writer"]["sha256"]):
                raise ValueError("exact independent native import helpers required")
            if (prepared["master_volume"] is not None or "provision" in prepared
                    or prepared["original_verification"].get("verification_status")!="pass"
                    or any(prepared["fixture"].get(key)!=plan[key] for key in ("files","entries","logical_bytes"))
                    or prepared["original_verification"].get("fixture_digest")!=prepared["fixture"]["fixture_digest"]):
                raise ValueError("original complete native source/count/bytes/digest with no prior Store required")
            qualification = fixtures.validate_import_qualification(case,plan,prepared["source_qualification"])
            review = case["port_review"]
            if (review["source_commit"]!=identity.git(identity.ROOT,"rev-parse","reference-v0.1.6-final^{commit}")
                    or review["source_tag_object"]!=identity.git(identity.ROOT,"rev-parse","reference-v0.1.6-final")):
                raise ValueError("reviewed original directory-import source pin differs")
            for path,digest in review["files"].items():
                if identity.sha256(identity.ROOT/path)!=digest:
                    raise ValueError("reviewed frozen import definition changed")
            if not case["oracle"].get("mounted_verification") or not case["oracle"].get("storage"):
                raise ValueError("original mounted and typed storage proof scopes required")
            rows.append({"case":case["id"],"status":"PASS","fixture":prepared["fixture"],
                "original_native":prepared["original_verification"],"independent_source_transcripts":qualification,
                "review":review,"oracle":case["oracle"],"differences":case["differences"]})
        except Exception as error:
            rows.append({"case":case["id"],"status":"FAIL","reason":str(error),"error_type":type(error).__name__})
    result = {"schema":"fs-bench-pro-parity-v1","family":family["family"],
        "status":"FAIL" if any(row["status"]!="PASS" for row in rows) else "PASS", "cases":rows,"samples":0,
        "scope":"original membership/source/census/full native bytes/digest and independent source CDC contracts; reviewed one fresh Init plus original fresh mounted verifier and current authenticated storage proof; no case replay"}
    receipts.write_new(output/"parity.json",result); receipts.manifest(output)
    if result["status"]!="PASS":
        raise ParityFailure(result,output)
    return result


def parity_namespace(family, prepared_parent, output):
    from . import fixtures
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    registered = identity.reference_catalogue(identity.ROOT / "core/target/fs-bench-pro-catalogue")
    frozen = {(row["family"], row["case"]): row for row in registered}
    for case in family["cases"]:
        reference = frozen[(family["family"], case["v016_case"])]
        prepared = fixtures.load(Path(prepared_parent) / case["fixture"]["recipe"], case["fixture"]["recipe"])
        fixture = prepared["fixture"]
        if (fixture["files"], fixture["logical_bytes"]) != (int(reference["fixture_files"]), int(reference["fixture_bytes"])):
            raise ValueError("original registry fixture totals differ")
        review = case["port_review"]
        if (review["source_commit"] != identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final^{commit}")
                or review["source_tag_object"] != identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final")):
            raise ValueError("port review source pin differs from retained reference")
        for path, digest in review["files"].items():
            if identity.sha256(identity.ROOT / path) != digest:
                raise ValueError("reviewed frozen operation source changed")
        rows.append({"case": case["id"], "status": "PASS", "fixture": fixture,
                     "original_native_verification": prepared["original_verification"], "review": review,
                     "oracle": case["oracle"], "differences": case["differences"]})
    result = {"schema": "fs-bench-pro-parity-v1", "family": family["family"], "status": "PASS", "cases": rows,
              "samples": 0, "scope": "original membership; exact count/bytes/content digest; agent reviewed operation transcription and original selected-prefix/root-reopen proof coverage"}
    receipts.write_new(output / "parity.json", result)
    receipts.manifest(output)
    return result


def parity_footprint(family,prepared_parent,output,build_folder):
    from . import fixtures
    if family["family"]!="store_footprint" or build_folder is None:
        raise ValueError("original footprint and independently sealed native build required")
    build=identity.load_build(build_folder)
    registered=identity.reference_catalogue(identity.ROOT/"core/target/fs-bench-pro-catalogue")
    membership={(row["family"],row["case"]) for row in registered}
    rows=[]
    for case in family["cases"]:
        try:
            prepared=fixtures.load(Path(prepared_parent)/case["fixture"]["recipe"],case["fixture"]["recipe"])
            if ((family["family"],case["v016_case"]) not in membership
                    or prepared.get("schema")!="fs-bench-pro-prepared-native-footprint-v1"
                    or prepared.get("case")!=case["id"] or prepared.get("master_volume") is not None or "provision" in prepared
                    or prepared.get("generator_sha256")!=build["binaries"]["workload-host"]["sha256"]):
                raise ValueError("exact fresh source-only footprint preparation required")
            fixture,native=prepared["fixture"],prepared["original_verification"]
            if (fixture["regular_files"]!=case["fixture"]["regular_files"] or fixture["logical_bytes"]!=case["fixture"]["logical_bytes"]
                    or fixture["data_directories"]+1!=case["fixture"]["directories_including_root"]
                    or native["tree_digest"]!=fixture["fixture_digest"] or int(native["regular_files"])!=fixture["regular_files"]
                    or int(native["logical_bytes"])!=fixture["logical_bytes"]):
                raise ValueError("original complete footprint fixture count/bytes/digest differs")
            review=case["port_review"]
            if (review["source_commit"]!=identity.git(identity.ROOT,"rev-parse","reference-v0.1.6-final^{commit}")
                    or review["source_tag_object"]!=identity.git(identity.ROOT,"rev-parse","reference-v0.1.6-final")):
                raise ValueError("original footprint source pin differs")
            for path,digest in review["files"].items():
                if identity.sha256(identity.ROOT/path)!=digest:
                    raise ValueError("reviewed frozen footprint definition changed")
            rows.append({"case":case["id"],"status":"PASS","fixture":fixture,"original_native":native,
                "review":review,"oracle":case["oracle"],"differences":case["differences"]})
        except Exception as error:
            rows.append({"case":case["id"],"status":"FAIL","reason":str(error),"error_type":type(error).__name__})
    result={"schema":"fs-bench-pro-parity-v1","family":family["family"],"status":"FAIL" if any(row["status"]!="PASS" for row in rows) else "PASS",
        "cases":rows,"samples":0,"scope":"exact original controls/source/count/bytes/native tree digest; reviewed measured fresh Init/edit/Created Commit and clipped native/public oracle; original physical counter gaps explicitly retained"}
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    receipts.write_new(output/"parity.json",result);receipts.manifest(output)
    if result["status"]!="PASS":raise ParityFailure(result,output)
    return result


def _parity_context(case, prepared, build):
    """Preparation witnesses never substitute for measured contextual proof."""
    from . import fixtures
    plan = fixtures.context_plan(case)
    admitted = fixtures.validate_runtime_helpers(case, prepared, build)
    if admitted.get("status") != "PASS":
        raise ValueError("original contextual prepared helper admission did not pass")
    states, native = prepared["context_checkpoints"], prepared["native_verification"]
    m1 = bool(case.get("m1_schedule"))
    wanted = {"original-context-initial-check"}
    if not m1:
        wanted.update(f"original-context-{s['role']}-{s['index']}-check" for s in states)
    if (set(native) != wanted
            or any(item.get("verification_status") != "pass" for item in native.values())):
        raise ValueError("exact original contextual native verification scope required")
    metadata = prepared["context_native_metadata"]
    if (metadata.get("schema") != "fs-bench-pro-original-context-native-recipes-v1"
            or metadata.get("case") != case["v016_case"]
            or metadata.get("context_binding") != prepared["context_binding"]
            or metadata.get("initial_recipe") != prepared["context_initial_recipe"]
            or metadata.get("context_roles") != prepared["context_roles"]
            or metadata.get("states") != states
            or type(metadata.get("performance_samples")) is not int or metadata["performance_samples"] != 0):
        raise ValueError("exact original contextual recipe witness correspondence required")
    expected = {s["role"]: s["summary"] for s in states
                if s["index"] == plan["local_commits"][s["role"]]}
    if prepared["expectation"] != expected:
        raise ValueError("contextual final recipe expectation correspondence differs")
    scope = "original-m1-selective-scope-v1" if m1 else "complete-original-native-state"
    materialization = ("None mode observations; selected M1 automatic fields are placeholders, not proof"
                       if m1 else "original full compact state")
    if any(s.get("verification_scope") != scope or s.get("materialization_metadata") != materialization for s in states):
        raise ValueError("contextual placeholder/native verification scope differs")
    return {"kind": "contextual-preparation", "helper_admission": admitted, "plan": plan,
            "initial_native_verification": native["original-context-initial-check"],
            "selected_native_verification": {} if m1 else {k: v for k, v in native.items() if k != "original-context-initial-check"},
            "checkpoint_witnesses": [{"role": s["role"], "local": s["index"],
                "recipe_sha256": s["summary"]["recipe_sha256"],
                "native_manifest_sha256": s["native_manifest_sha256"], "scope_sha256": s["manifest_sha256"],
                "qualification_status": "PASS", "qualification_scope": "recipe/source and selective scope only" if m1 else "complete original native state",
                "actual_created_modes": "NOT_OBSERVED_IN_PREPARATION" if m1 else "NOT_APPLICABLE",
                "measured_proof_status": "NOT_RUN"} for s in states],
            "sdk_descriptor_witnesses": [{"role": s["role"], "local": s["index"], "members": s["members"],
                "original_run": s["original_run"], "prepared_run": s["prepared_run"],
                "descriptor_sha256": s["descriptor_sha256"], "generator_sha256": s["generator"]["binary_sha256"]}
                for s in prepared["sdk_context_steps"]],
            "source_binding": prepared["context_binding"], "actual_created_modes": prepared["context_roles"],
            "scope": ("full pristine native input independently verified; exact original roles/local operations/checkpoints and prepared SDK descriptors admitted; "
                      "M1 checkpoint recipes and selective scopes are source evidence with unobserved actual modes; measured native/persisted proofs NOT_RUN"
                      if m1 else "full pristine native input and original selected compact states independently verified; exact original roles/local operations/checkpoints and prepared SDK descriptors admitted; measured native/persisted proofs NOT_RUN")}


def _parity_access(case, prepared, build):
    """Bind closed producer and selected native algebra without reading a mount."""
    from . import fixtures
    plan = fixtures.historical_plan(case)
    admitted = fixtures.validate_runtime_helpers(case, prepared, build)
    if admitted.get("status") != "PASS":
        raise ValueError("original historical prepared helper admission did not pass")
    selected, closed = prepared["historical_selection"], prepared["closed_producer"]
    native = prepared["native_verification"]
    if (set(native) != {"historical_selected"}
            or native["historical_selected"].get("verification_status") != "pass"):
        raise ValueError("exact original historical selected native verification required")
    acknowledgements = closed["acknowledgements"]
    return {"kind": "historical-access-preparation", "helper_admission": admitted, "plan": plan,
            "closed_producer": {"case": plan["producer_case"], "source_commit": closed["source_commit"],
                "receipt_sha256": closed["receipt_sha256"], "transcript_sha256": closed["transcript_sha256"],
                "store_sha256": closed["store_sha256"], "custody": closed["custody"],
                "acknowledgements": acknowledgements, "acknowledgement_count": len(acknowledgements),
                "retained_root_references": len(acknowledgements) + 1,
                "distinct_commit_tuples": len({s["commit_id"] for s in acknowledgements})},
            "selected": {"original_source_role": selected["original_source_role"],
                "source_role": selected["source_role"], "local": selected["local"],
                "acknowledged_commit": selected["acknowledged_commit"], "manifest_sha256": selected["manifest_sha256"],
                "native_verification": native["historical_selected"],
                "read_targets": [{**{k: s[k] for k in ("path", "bytes", "sha256")}, "range": original["range"]}
                                 for s, original in zip(selected["read_targets"], case["historical_access"]["reads"])],
                "absent": selected["absent"]}, "source_binding": prepared["producer_dependency"]["source_binding"],
            "reader_status": "NOT_RUN", "verifier_reader_status": "NOT_RUN", "measured_proof_status": "NOT_RUN",
            "scope": "closed original producer dependency with every typed acknowledgement/fork/head and known Stop; selected role/local native state and independent full read-target bytes/SHA bound; neither original reader pass executed"}


def parity_workspace(family, prepared_parent, output, build_folder=None):
    """Keep every case outcome, then reject any failed original parity guard."""
    from . import fixtures
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    registered = identity.reference_catalogue(identity.ROOT / "core/target/fs-bench-pro-catalogue")
    membership = {(row["family"], row["case"]) for row in registered}
    rows = []
    build = None
    batch5 = family["family"] in ("branch_development", "multi_workspace_development", "historical_access")
    for case in family["cases"]:
        try:
            if (family["family"], case["v016_case"]) not in membership:
                raise ValueError("frozen original case membership differs")
            prepared = fixtures.load(Path(prepared_parent) / case["fixture"]["recipe"], case["fixture"]["recipe"])
            if prepared["case"] != case["id"] or prepared["family"] != family["family"]:
                raise ValueError("original fixture was prepared for another case")
            review = case["port_review"]
            if (review["source_commit"] != identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final^{commit}")
                    or review["source_tag_object"] != identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final")):
                raise ValueError("reviewed operation pin differs")
            for path, digest in review["files"].items():
                if identity.sha256(identity.ROOT / path) != digest:
                    raise ValueError("reviewed original fixture/operation/oracle source changed")
            scoped = batch5 or case.get("branch_schedule") or case.get("topology_schedule") or case.get("historical_access")
            if scoped:
                if build_folder is None:
                    raise ValueError("batch-five prepared parity requires an independently admitted sealed build")
                if build is None:
                    build = identity.load_build(build_folder)
                mechanical = (_parity_access(case, prepared, build) if family["family"] == "historical_access" or case.get("historical_access")
                              else _parity_context(case, prepared, build))
            else:
                if any(item["verification_status"] != "pass" for item in prepared["native_verification"].values()):
                    raise ValueError("original complete native fixture/oracle check not passed")
                mechanical = prepared["native_verification"]
            rows.append({"case": case["id"], "status": "PASS", "fixture": prepared["fixture"],
                         "expectation": prepared["expectation"], "mechanical": mechanical,
                         "review": review, "oracle": case["oracle"], "differences": case["differences"]})
        except Exception as error:
            rows.append({"case": case["id"], "status": "FAIL", "reason": str(error),
                         "error_type": type(error).__name__})
    result = {"schema": "fs-bench-pro-parity-v1", "family": family["family"],
              "status": "FAIL" if any(row["status"] == "FAIL" for row in rows) else "PASS", "cases": rows,
              "samples": 0, "scope": ("original membership and pinned source; independently admitted sealed preparation with case-specific native/recipe/closed-producer scope recorded per row; actual contextual or historical-access proof is not a parity sample"
                  if batch5 or any(case.get("branch_schedule") or case.get("topology_schedule") or case.get("historical_access") for case in family["cases"])
                  else "original membership, full deterministic native fixture/final counts+bytes+content digest; reviewed unchanged ordinary calls and complete native/persisted verification")}
    receipts.write_new(output / "parity.json", result)
    receipts.manifest(output)
    if result["status"] == "FAIL":
        raise ParityFailure(result, output)
    return result




# Repository-history functions are an isolated append-only ownership scope.
def repository_admit(case, prepared, build):
    from .recipes import repository_history as recipe
    if (case['id'] not in recipe.SELECTIONS or case['v016_case'] != case['id']
            or prepared.get('schema') != 'fs-bench-pro-prepared-repository-history-v1'
            or prepared.get('family') != 'repository_history' or prepared.get('case') != case['id']
            or prepared.get('recipe') != case['fixture']['recipe']
            or prepared.get('provision', {}).get('global_profile') != 'Disposable/WAL/OFF'
            or prepared.get('fixture', {}).get('logical_bytes') != 0 or prepared['fixture'].get('files') != 0):
        raise ValueError('exact original repository case and sealed empty Disposable input required')
    inputs = prepared['repository_inputs']
    indices = list(recipe.SELECTIONS[case['id']])
    if (inputs.get('status') != 'PASS' or inputs.get('case') != case['id']
            or inputs.get('manifest_sha256') != recipe.MANIFEST_SHA or inputs.get('source_tip') != recipe.SOURCE_TIP
            or inputs.get('full157_indices') != indices or inputs.get('state_count') != len(indices)
            or case['repository_schedule']['full157_indices'] != indices):
        raise ValueError('repository selected corpus identity/count differs')
    files, states = prepared['helpers']['files'], inputs['states']
    if len(states) != len(indices):
        raise ValueError('repository every selected transition required')
    for local, (state, original) in enumerate(zip(states, indices), 1):
        helper = f'repository/checkpoints/{local}'
        if (state['index'] != local or state['full157_index'] != original
                or state.get('helper_input') != helper or state.get('runtime_input') != f'/input/checkpoint-{local}'
                or state.get('previous_full157_index') != (None if local == 1 else indices[local-2])):
            raise ValueError('repository direct selected transition/ordinal differs')
        expected = {f'{helper}/{name}': digest for name, digest in state['input_seal']['files'].items()
                    if name != 'oracle.json'}
        actual = {name: digest for name, digest in files.items() if name.startswith(helper+'/')}
        if actual != expected or files.get(f'repository/oracles/{local}.json') != state['oracle_sha256']:
            raise ValueError('repository exact prepared helper/full oracle membership differs')
        if identity.sha256(state['oracle']) != state['oracle_sha256']:
            raise ValueError('repository independent sealed oracle changed')
    return {'status': 'PASS', 'indices': indices, 'states': len(states),
            'scope': 'exact selected transitions/helpers/oracles and explicit empty Disposable master; no measured history in setup'}


def repository_runtime(prepared, build, output, clone, label, stop):
    import secrets
    from . import workspace
    folder = Path(output) / label
    folder.mkdir()
    argv = [build['binaries']['runtime']['path'], 'serve', '--socket', build['socket'],
            '--volume', clone['volume'], '--daemon', build['binaries']['daemon']['path'],
            '--manifest', prepared['provision']['manifest'], '--receipt', str(folder/'runtime.events.jsonl'),
            '--case', prepared['case'], '--uid', str(prepared['source_uid']), '--gid', str(prepared['source_gid']),
            '--observation-scope', secrets.token_hex(32)]
    runtime = workspace.cell_runner.EventProcess(argv, folder, label)
    try:
        runtime.host_observer = receipts.HostProcessObserver(runtime.process,folder,label,8*1024**3)
        repository_host_check(runtime)
        runtime.event('protocol_ready', min(stop, workspace.time.monotonic()+15))
        if runtime.container is None:
            raise ValueError('repository original runtime container acknowledgement unavailable')
        receipts.command(['docker','--host','unix://'+build['socket'],'exec','--user','0:0',runtime.container,
                          'install','-d','-m','0755','-o',str(prepared['source_uid']),'-g',str(prepared['source_gid']),'/input'],
                         folder,'native-input-directory',workspace.operation_deadline(stop,15)-workspace.time.monotonic())
    except BaseException as error:
        error.event_process = runtime
        raise
    repository_host_check(runtime)
    return runtime, folder


def repository_host_check(runtime):
    return runtime.host_observer.check()


def repository_mount_root(mount, key):
    """Bind the original helper to the actual acknowledged native mount."""
    fields = mount.get('fields') if isinstance(mount, dict) else None
    namespace = fields.get('workspace_namespace') if isinstance(fields, dict) else None
    if (not isinstance(mount, dict) or mount.get('event') != 'mount'
            or not isinstance(fields, dict) or type(key) is not str or len(key) != 64
            or any(character not in '0123456789abcdef' for character in key)
            or fields.get('key') != key or fields.get('workspace_incarnation') != key
            or type(namespace) is not int or not 0 < namespace < 2**64
            or fields.get('directory') != f'/workspaces/{namespace}'):
        raise ValueError('repository actual mount acknowledgement root/token binding differs')
    return fields['directory']


def repository_helper_body(action, case, index, path, mounted_root):
    import shlex
    return ('LAYERFS_WORKSPACE_ROOT=' + shlex.quote(mounted_root) + ' ' +
            shlex.join(['/bin/bash', '/code/workload.sh', action, case, str(index), path]))


def repository_stop(runtime, stop):
    from . import workspace
    repository_host_check(runtime)
    runtime.send('observe', deadline=stop)
    repository_host_check(runtime)
    runtime.send('stop', deadline=stop)
    runtime.event('finished', stop)
    if runtime.process.wait(timeout=workspace.operation_deadline(stop, 1)-workspace.time.monotonic()) != 0:
        raise ValueError('repository runtime exit differs after known Stop')
    runtime.repository_host_completion = runtime.host_observer.finish()
    return runtime.repository_host_completion


def repository_transcripts(initial, records):
    genesis = f"0\t-\t-\t{initial}\t-\n"
    full, created, unique = genesis, genesis, []
    for record in records:
        fields = record['mapping']
        row = f"{fields['commit_id']}\t{fields['parent']}\t{fields['root']}\t{record['oracle']}\n"
        full += str(record['index'])+'\t'+row
        if record['commit']['fields']['commit_kind'] == 'Committed':
            unique.append(fields)
            created += str(len(unique))+'\t'+row
    return full, created, unique


def repository_graph_proof(case, prepared, build, output, runtime, row, stop):
    import shutil
    from . import oracle, workspace
    folder = Path(output)/'typed-proof'
    folder.mkdir()
    typed = folder/'store.sqlite'
    normalized = row['closed_store_normalization']
    shutil.copy2(normalized['path'], typed)
    if identity.sha256(typed) != normalized['normalized_identity']['sha256']:
        raise ValueError('repository typed copy differs from frozen performance Store')
    full, created, unique = repository_transcripts(row['repository']['initial_root'], row['repository']['records'])
    full_path = workspace.script(folder, 'all-selected.tsv', full)
    created_path = workspace.script(folder, 'created.tsv', created)
    fork = row['repository']['fork']
    receipts.write_new(folder/'fork-event.json', fork)
    fields = fork['fields']
    workspace.script(folder, 'fork.tsv', '\t'.join([fields[k] for k in ('branch_id','name','stack','base_layer','root','head')]
                                                  + [identity.sha256(folder/'fork-event.json')])+'\n')
    events_path = folder/'typed.events.jsonl'
    result = receipts.command([build['binaries']['runtime']['path'], 'verify-repository', '--socket', build['socket'],
            '--volume', row['clone']['volume'], '--daemon', build['binaries']['daemon']['path'],
            '--manifest', prepared['provision']['manifest'], '--history-file', str(full_path),
            '--source-copy', str(folder), '--sealed', str(typed), '--case', case['id'], '--receipt', str(events_path),
            '--uid', str(prepared['source_uid']), '--gid', str(prepared['source_gid'])], folder, 'typed-proof',
            workspace.operation_deadline(stop,120)-workspace.time.monotonic())
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    proofs = [e for e in events if e['event'] == 'workspace_verified']
    derivations = [e for e in events if e['event'] == 'repository_manifest_derived']
    if (len(proofs) != 1 or len(derivations) != 1 or not events or events[-1]['event'] != 'finished'
            or proofs[0]['fields'].get('status') != 'PASS' or derivations[0]['fields'].get('status') != 'PASS'
            or proofs[0]['fields']['repository_acknowledged_transcript_sha256'] != identity.sha256(full_path)
            or proofs[0]['fields']['acknowledged_transcript_sha256'] != identity.sha256(created_path)):
        raise ValueError('repository fullselected/Created-only public proof binding differs')
    derived = derivations[0]['fields']
    if (derived['original_manifest_sha256'] != identity.sha256(prepared['provision']['manifest'])
            or derived['derived_manifest_sha256'] != identity.sha256(derived['derived_manifest'])
            or derived['derivation_receipt_sha256'] != identity.sha256(derived['derivation_receipt'])
            or derived['fork_event_sha256'] != identity.sha256(folder/'fork-event.json')):
        raise ValueError('repository actual Fork/derived manifest custody differs')
    raw = Path(output)/'graph-store/store.sqlite'
    completion = Path(output)/'closed-store-export.completion.json'
    runtime_events = Path(output)/'performance/runtime.events.jsonl'
    custody = {'custody':'KNOWN_STOP','container':runtime.container,'volume':row['clone']['volume'],
        'remote_source':'/layerfs-store/global/store.sqlite','local_source':str(raw),
        'source_sha256':identity.sha256(raw),'source_size':raw.stat().st_size,
        'prepared_manifest':derived['derived_manifest'],'prepared_manifest_sha256':derived['derived_manifest_sha256'],
        'transcript':str(created_path),'transcript_sha256':identity.sha256(created_path),
        'export_completion':str(completion),'export_completion_sha256':identity.sha256(completion),
        'runtime_events':str(runtime_events),'runtime_events_sha256':identity.sha256(runtime_events),
        'normalization':{'receipt':normalized['receipt'],'receipt_sha256':normalized['receipt_sha256']}}
    tuples = [{'commit_id':f['commit_id'],'layer_stack_id':f['stack'],'root_id':f['root'],
               'parent_commit_id':None if f['parent']=='-' else f['parent'],'base_layer_id':f['base_layer']} for f in unique]
    census = oracle.commit_census(normalized['path'], tuples, proofs[0]['fields'], custody)
    receipts.write_new(folder/'global-commit-census.json', census)
    return {'status':'PASS','public_events':events,'global_census':census,'derivation':derived,
            'full_selected_transcript':str(full_path),'created_transcript':str(created_path),'attempt':result}


def one_repository_history(case, prepared_folder, build_folder, output):
    """One exact original history, frozen before fresh mounted same-volume proofs."""
    import secrets
    import time
    from . import fixtures, oracle, workspace
    from .recipes import repository_history as recipe
    begun = time.monotonic_ns()
    stop = begun/1e9+120
    current, build = identity.source_identity(), identity.load_build(build_folder)
    prepared = fixtures.load(prepared_folder, case['fixture']['recipe'])
    admission = repository_admit(case, prepared, build)
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    treatment = {'case':case,'inputs':prepared['repository_inputs']['input_identity'],'product':current['product_tree'],
                 'helpers':prepared['helpers']['files'],'binaries':{k:v['sha256'] for k,v in build['binaries'].items()},
                 'engine':identity.sha256(__file__),'image':identity.IMAGE}
    claim = receipts.sample_claim_key(treatment, current["source_commit"])
    claims = identity.ROOT/'benchmark-results/fs-bench-pro/claims'
    claims.mkdir(parents=True,exist_ok=True)
    with (claims/claim).open('x') as stream:
        stream.write(str(output)+'\n')
    row = {'schema':'fs-bench-pro-repository-history-v1','family':'repository_history','case':case['id'],
        'source_commit':current['source_commit'],'product_tree':current['product_tree'],'identity':current,
        'prepared':str(Path(prepared_folder).resolve()),'build':str(Path(build_folder).resolve()),'image':identity.IMAGE,
        'daemon_sha256':build['binaries']['daemon']['sha256'],'runtime_sha256':build['binaries']['runtime']['sha256'],
        'status':'NOT_RUN','proof_status':'NOT_RUN','cleanup':'UNAVAILABLE','counts':{},'observations':{},'phases':{},
        'cache_class':'C','cache':{'status':'INELIGIBLE','reason':'original sustained history; setup/source and paid own-write backing coldness unqualified'},
        'global_profile':'Disposable/WAL/OFF','overlay_profile':'MEMORY/OFF/EXCLUSIVE','construction_workers':1,
        'durable':'NOT_RUN — disabled by owner until explicit reauthorization','claim':claim,'helper_admission':admission,
        'sample_count':0,'attempted_operation_count':0,'completed_operation_count':0,'verification_attempt_count':0,
        'declared_limit_ns':case['budget']['command_ms']*1000000,'verifier_limit_ns':case['budget']['verifier_ms']*1000000,
        'owner_test_ceiling_ns':120000000000,'repository':{'records':[]},'partial_phases':{},'resource_removal_pending':False,
        'interference':current.get('cross_worktree_interference','shared host/Docker VM/protected and failed services; unquantified'),
        'host_resource_observations':{'status':'PENDING','runtimes':{},
            'scope':'each actual owned native runtime PID sampled current RSS <=8GiB; final zero swaps and CPU/IO use expanded all-reaped harness-child aggregate, never native-specific'}}
    receipts.write_new(output/'selection.json',row)
    runtimes, active = [], {}
    proof_start = None
    try:
        row['clone'] = fixtures.clone(prepared,output/'clone',build)
        runtime, phase = repository_runtime(prepared,build,output,row['clone'],'performance',stop)
        runtimes.append(runtime);row['container']=runtime.container
        workspace.history_container_profile(runtime,build,phase)
        repository_host_check(runtime)
        row['staging'] = fixtures.stage(runtime.container,prepared,phase/'staging',build)
        repository_host_check(runtime)
        initial = next(e['fields'] for e in runtime.rows if e['event']=='history_initial_root')
        graph = {'branches':{'initial':{'initial_root':initial['root'],'stack':initial['stack'],'base_layer':initial['base_layer']}}}
        fork = workspace.context_fork(runtime,case,{'role':'history','source_role':None,'source_local':0,'name':'history'},graph,phase,stop)
        repository_host_check(runtime)
        row['repository'].update(initial_root=initial['root'],fork=fork,branch_id=fork['fields']['branch_id'])
        key = secrets.token_hex(32)
        mount = workspace.context_send(runtime,'mount-branch',key,'history',deadline=stop)
        active[runtime.container]=key
        mounted_root = repository_mount_root(mount, key)
        repository_host_check(runtime)
        guards = {'before':workspace.history_resource_guard(runtime,build,phase,'resources-before'),'steps':[]}
        row['resource_guards']=guards
        row.update(sample_count=1,attempted_operation_count=1)
        sums = {'mount_ns':mount['span']['duration_ns'],'command_ns':0,'commit_ns':0,'unmount_ns':0}
        previous = {'commit_id':'-','parent':'-','root':initial['root'],'stack':initial['stack'],'base_layer':initial['base_layer']}
        for state in prepared['repository_inputs']['states']:
            index = state['index']
            repository_host_check(runtime)
            transfer = receipts.command(['docker','--host','unix://'+build['socket'],'cp',
                str(Path(prepared['helpers']['root'])/state['helper_input']),runtime.container+':'+state['runtime_input']],
                phase,f'transfer-{index}',workspace.operation_deadline(stop,120)-time.monotonic())
            repository_host_check(runtime)
            # Exact admitted own helper bytes; source corpus is never read here.
            body = repository_helper_body('apply', case['id'], index, state['runtime_input'], mounted_root)
            command = runtime.send('command',key,workspace.script(phase,f'step-{index}.sh',body),deadline=stop)
            repository_host_check(runtime)
            commit = runtime.send('commit',key,deadline=stop)
            repository_host_check(runtime)
            fields = commit['fields']
            if fields['commit_kind']=='Committed':
                if fields.get('parent')!=previous['commit_id'] or fields.get('stack')!=initial['stack'] or fields.get('base_layer')!=initial['base_layer']:
                    raise ValueError('repository exact Created ancestry/stack/base differs')
                previous={k:fields[k] for k in previous}
                graph['branches']['history']['commits'].append({'commit':commit})
            elif fields['commit_kind']=='UpToDate' and not case['repository_schedule']['require_created'] and fields['root']==previous['root']:
                pass
            else:
                raise ValueError('repository required Created or exact prior UpToDate mapping differs')
            graph['branches']['history'].update(final_head=previous['commit_id'],final_root=previous['root'])
            record={'index':index,'full157_index':state['full157_index'],'command':command,'commit':commit,
                    'mapping':dict(previous),'transfer':transfer,'oracle':state['oracle'],'oracle_sha256':state['oracle_sha256']}
            row['repository']['records'].append(record)
            sums['command_ns']+=command['span']['duration_ns'];sums['commit_ns']+=commit['span']['duration_ns']
            row['partial_phases']=dict(sums)
            guards['steps'].append(workspace.history_resource_guard(runtime,build,phase,f'resources-{index}',guards['before']))
        repository_host_check(runtime)
        ended=workspace.context_end(runtime,key,row,stop);active.pop(runtime.container)
        repository_host_check(runtime)
        sums['unmount_ns']=ended['span']['duration_ns']
        row.update(phases=sums,complete_wall_ns=sums['command_ns']+sums['commit_ns'],cleanup='Gone')
        row['timing_scope']='original sum of ordinary importer Exec/output drain plus public Commit; setup/Init/Fork/mount/transfers/resource observation/verification excluded; outer wall separately retained'
        workspace.context_observations(runtime,row,build,phase,stop)
        repository_host_check(runtime)
        row['repository']['sdk_history']=workspace.context_history(runtime,'history',graph['branches']['history'],graph,phase,stop)
        repository_host_check(runtime)
        row['host_resource_observations']['runtimes']['performance']=repository_stop(runtime,stop);row['performance_custody']='KNOWN_STOP';row['custody']='KNOWN_STOP'
        export=receipts.command(['docker','--host','unix://'+build['socket'],'cp',runtime.container+':/layerfs-store/global',str(output/'graph-store')],output,'closed-store-export',workspace.operation_deadline(stop,120)-time.monotonic())
        row['performance_store_export']=export
        row['closed_store_normalization']=oracle.prepare_closed_store(output/'graph-store',output/'census-store/store.sqlite',stop)
        row['performance_storage_frozen']={'raw_files':row['closed_store_normalization']['raw_files'],'normalized_sha256':row['closed_store_normalization']['normalized_identity']['sha256']}
        proof_start=time.monotonic_ns();row['verification_attempt_count']=1;row['proof_status']='FAIL'
        row['repository']['typed_proof']=repository_graph_proof(case,prepared,build,output,runtime,row,stop)
        verify, verify_phase=repository_runtime(prepared,build,output,row['clone'],'verification',stop)
        runtimes.append(verify);row['verification_container']=verify.container
        workspace.history_container_profile(verify,build,verify_phase)
        repository_host_check(verify)
        fixtures.stage(verify.container,prepared,verify_phase/'staging',build)
        repository_host_check(verify)
        row['repository']['native_proofs']=[]
        for record in row['repository']['records']:
            repository_host_check(verify)
            index=record['index'];fields=record['mapping'];label=f'verify-{index}';branch_id='11'+secrets.token_hex(16)
            descriptor=(f"layer\t{branch_id}\t{label}\n" if fields['commit_id']=='-' else
                        f"commit\t{branch_id}\t{label}\t@{row['repository']['branch_id']}\t{fields['commit_id']}\n")
            forked=workspace.context_send(verify,'fork',label,workspace.script(verify_phase,f'fork-{index}.tsv',descriptor),deadline=stop)
            if forked['fields']['root']!=fields['root'] or forked['fields']['head']!=fields['commit_id']:
                raise ValueError('repository actual historical Fork root/head differs')
            repository_host_check(verify)
            key=secrets.token_hex(32);mounted=workspace.context_send(verify,'mount-branch',key,label,deadline=stop);active[verify.container]=key
            mounted_root = repository_mount_root(mounted, key)
            repository_host_check(verify)
            observed=f'/input/observed-{index}.tsv'
            native=verify.send('verify',key,workspace.script(verify_phase,f'observe-{index}.sh',
                repository_helper_body('verify', case['id'], index, observed, mounted_root)),deadline=stop)
            repository_host_check(verify)
            local=verify_phase/f'observed-{index}.tsv'
            receipts.command(['docker','--host','unix://'+build['socket'],'cp',verify.container+':'+observed,str(local)],verify_phase,
                             f'observed-copy-{index}',workspace.operation_deadline(stop,120)-time.monotonic())
            repository_host_check(verify)
            proof=recipe.verify_observed(local,record['oracle'])
            workspace.context_end(verify,key,row,stop);active.pop(verify.container)
            repository_host_check(verify)
            row['repository']['native_proofs'].append({'index':index,'mapping':fields,'fork':forked,'command':native,'proof':proof,'observed_sha256':identity.sha256(local)})
            workspace.history_resource_guard(verify,build,verify_phase,f'verifier-resources-{index}')
        row['host_resource_observations']['runtimes']['verification']=repository_stop(verify,stop);row['verification_custody']='KNOWN_STOP'
        row['host_resource_observations']['status']='PASS_CURRENT_RSS_AND_EXPANDED_AGGREGATE_ZERO_SWAPS'
        row.update(status='INELIGIBLE',functional_status='PASS',proof_status='PASS',completed_operation_count=1,
                   resource_removal_pending=True,additional_containers=[verify.container],
                   resource_disposition='both own known-stopped runtime containers and sample volume retained until outer acknowledgement')
    except BaseException as error:
        row.update(status='FAIL',functional_status='FAIL',proof_status='FAIL' if proof_start else 'NOT_RUN',
                   original_failure=str(error),failure_type=type(error).__name__,leaked_mount_keys=dict(active))
        failed = getattr(error,'event_process',None)
        if failed is not None and failed not in runtimes:
            runtimes.append(failed)
        row['retained_containers']=[r.container for r in runtimes]
        row['retained_runtimes']=[r.retain(error) for r in runtimes]
    finally:
        for runtime in runtimes:
            observer=getattr(runtime,'host_observer',None)
            if observer is not None and not hasattr(runtime,'repository_host_completion'):
                try:
                    runtime.repository_host_completion=observer.finish()
                except BaseException as error:
                    row.setdefault('host_observer_close_failures',[]).append(str(error))
                    row['host_resource_observations']['status']='FAIL'
                    row['status']='FAIL';row['resource_removal_pending']=False
                    row.setdefault('retained_host_observers',[]).append({'pid':runtime.process.pid,
                        'samples':str(observer.path),'completion':str(observer.completion_path),
                        'scope':'finite sampler shutdown only; unknown runtime wait never establishes Stop, final swaps or cleanup'})
            for handle in (runtime.selector,runtime.raw,runtime.stderr,getattr(runtime.process,'stdin',None),getattr(runtime.process,'stdout',None)):
                if handle is not None:
                    try: handle.close()
                    except BaseException as error: row.setdefault('independent_close_failures',[]).append(str(error));row['status']='FAIL'
        row['external_driver_wall_ns']=time.monotonic_ns()-begun
        if proof_start is not None:row['proof_wall_ns']=time.monotonic_ns()-proof_start
        row['evidence']=str(output.relative_to(identity.ROOT.resolve()))
        io_observer.attach(output,row)
        row.update(receipts.finalize_guarded(output,row,stop,scope=receipts.HISTORY_PUBLICATION_SCOPE))
    return row


def parity_repository_history(family, prepared_parent, output, build_folder):
    from . import fixtures, workspace
    build=identity.load_build(build_folder);rows=[]
    for case in family['cases']:
        try:
            prepared=fixtures.load(Path(prepared_parent)/case['fixture']['recipe'],case['fixture']['recipe'])
            for path,digest in case['port_review']['files'].items():
                if identity.sha256(identity.ROOT/path)!=digest:raise ValueError('repository frozen source pin changed')
            admission=repository_admit(case,prepared,build)
            rows.append({'case':case['id'],'status':'PASS','admission':admission,'differences':case['differences']})
        except Exception as error:rows.append({'case':case['id'],'status':'FAIL','reason':str(error)})
    result={'schema':'fs-bench-pro-parity-v1','family':'repository_history','status':'FAIL' if any(r['status']=='FAIL' for r in rows) else 'PASS','cases':rows,'samples':0,'scope':'exact selected sealed native transitions and original full oracle; no producer constructed during parity'}
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False);receipts.write_new(output/'parity.json',result);receipts.manifest(output)
    if result['status']=='FAIL':raise ParityFailure(result,output)
    return result
