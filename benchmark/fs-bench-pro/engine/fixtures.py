"""Rebuild sealed fixture masters and independent byte-copy sample volumes."""
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import tempfile
import uuid

from . import identity, prepared_inputs, project, receipts

MTIME_NS = 1_700_000_000_000_000_000
BIG_BYTES = 64 * 1024 * 1024
CELL_RECIPES = {f"C{n:02}": "big64m" if n in (9, 10, 11) else "empty" for n in range(1, 13)}
NAMESPACE_RECIPES = ("namespace-100-compact-v3", "namespace-10000", "namespace-100000")
IMPORT_FAMILIES = ("dedup_cdc_locality", "dedup_cross_file")
WORKSPACE_FAMILIES = ("payload_create_read", "tiny_file_churn", "namespace_mutation",
                     "edit_length_preserving", "edit_length_changing", "edit_length_changing_capped",
                     "edit_canonical_chunk_count", "small_file_delta_smoke",
                     "directory_construction_traversal", "git_tool_workflow", "local_snapshot",
                     "workspace_change_locality", "file_size_transition",
                     "dedup_branch_history", "mixed_load_bearing", "branch_development",
                     "multi_workspace_development", "historical_access", "dedup_workspace_reuse", "store_footprint", "repository_history")
RECIPE_HISTORY_SCHEMAS = ("original-v016-boundary-sequence-v1", "original-dedup-history-sequence-v1",
                          "original-m1-commit-sequence-v1")
CONTEXT_PREPARED_SCHEMA = "fs-bench-pro-prepared-context-workspace-v1"
CONTEXT_SOURCE_FILES = ("benchmark/fs-bench-pro/engine/recipes/edit_model.rs",
                        "benchmark/fs-bench-pro/engine/recipes/workspace.rs",
                        "benchmark/fs-bench-pro/writers/edit.rs")


def context_plan(case):
    """Read declared roles/checkpoints/member counts, never infer from outputs."""
    branch, topology = case.get("branch_schedule"), case.get("topology_schedule")
    if bool(branch) == bool(topology):
        raise ValueError("exactly one original context schedule required")
    roles, limits, runs, selected = [], {}, {}, []
    if branch:
        if branch.get("schema") != "original-branch-development-v1":
            raise ValueError("original branch context schema required")
        for item in branch["branches"]:
            role = item["role"]
            if role not in ("trunk", "a", "b", "c") or role in limits:
                raise ValueError("original branch context roles differ")
            if type(item.get("local_commits")) is not int or item["local_commits"] < 1:
                raise ValueError("positive original context limits required")
            roles.append(role); limits[role] = item["local_commits"]
        if not roles or roles[0] != "trunk":
            raise ValueError("initial branch fixture requires trunk context")
        for role in roles:
            rows = [step for step in case["steps"] if step.get("role") == role]
            if [step.get("local_index") for step in rows] != list(range(1, limits[role] + 1)):
                raise ValueError("exact original role-local operation sequence required")
            runs[role] = rows
        if sum(limits.values()) != len(case["steps"]):
            raise ValueError("undeclared branch context operations")
        selected = [{"role": item["role"], "index": item["local_index"]}
                    for item in branch["payload_checkpoints"]]
    else:
        if topology.get("schema") != "original-v016-m1-topology-v1":
            raise ValueError("original multi-workspace context schema required")
        count = topology["per_worker_commits"]
        if type(count) is not int or count < 1:
            raise ValueError("positive original context limits required")
        for index, worker in enumerate(topology["workers"]):
            if type(worker.get("index")) is not int or worker["index"] != index or index > 3:
                raise ValueError("original multi-workspace context roles differ")
            role = str(index); roles.append(role); limits[role] = count
            rows = case["steps"]
            if [step.get("index") for step in rows] != list(range(1, count + 1)):
                raise ValueError("exact original worker-local operation sequence required")
            runs[role] = rows
            selected.extend({"role": role, "index": step}
                            for step in topology["verification_steps_by_worker"][role])
        if (len(roles) not in (2, 4) or set(topology["verification_steps_by_worker"]) != set(roles)
                or topology["total_commits"] != sum(limits.values())):
            raise ValueError("original multi-workspace context cardinality differs")
    if any(type(limit) is not int or limit < 1 for limit in limits.values()):
        raise ValueError("positive original context limits required")
    pairs = [(item["role"], item["index"]) for item in selected]
    if (not pairs or len(set(pairs)) != len(pairs)
            or any(role not in limits or type(step) is not int or not 1 <= step <= limits[role]
                   for role, step in pairs)
            or any((role, limits[role]) not in pairs for role in roles)
            or case.get("m1_schedule") and any(step % 5 for _, step in pairs)):
        raise ValueError("exact declared contextual payload checkpoints required")
    sdk, original_runs = [], {role: {} for role in roles}
    for role in roles:
        for index, step in enumerate(runs[role], 1):
            count = step.get("ordinary_edit_members", 0)
            expected = 2 if index % 5 == 2 else 0 if case.get("m1_schedule") else 1
            if not case.get("m1_schedule"):
                expected = 1
            if type(count) is not int or count != expected or not step.get("commit"):
                raise ValueError("original contextual SDK member schedule differs")
            original = step["run"] + (" " + role if topology else "")
            original_runs[role][str(index)] = original
            if count:
                sdk.append({"role": role, "index": index, "members": count, "original_run": original})
    return {"initial_role": roles[0], "roles": roles, "local_commits": limits,
            "checkpoints": selected, "sdk_steps": sdk, "original_context_runs": original_runs,
            "case_definition_sha256": hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()}


def context_source_binding(case, current):
    return {"source_commit": current["source_commit"], "source_tree": current["source_tree"],
            "case_definition_sha256": context_plan(case)["case_definition_sha256"],
            "model_files": {path: current["files"][path] for path in CONTEXT_SOURCE_FILES}}


def context_role_records(case, plan):
    records = {}
    for role in plan["roles"]:
        inherited = ["trunk", role] if case.get("branch_schedule") and role != "trunk" else [role]
        records[role] = {"local_commits": plan["local_commits"][role],
                         "created_modes_schema": "original-context-created-modes-v1" if case.get("m1_schedule") else None,
                         "created_mode_scope_roles": inherited if case.get("m1_schedule") else [],
                         "actual_created_modes": "NOT_OBSERVED_IN_PREPARATION; measured helper maps required"}
    return records


def historical_producer_dependency(case):
    """Support declaration only; Root owns the new closed producer execution."""
    fixture = case["fixture"]
    return {"schema": "fs-bench-pro-historical-producer-dependency-v1", "case": case["v016_case"],
            "producer": fixture.get("producer"), "producer_family": fixture.get("producer_family"),
            "seed": fixture["seed"], "status": "EXECUTION_PENDING_ROOT",
            "required_custody": "new closed preparation with original producer acknowledgements and full history",
            "allowed_reuse": "initial immutable masters, exact recipes and qualified proof identities",
            "forbidden_reuse": "mutated measured batch4 sample or relabelled measurement receipt"}


HISTORICAL_PREPARED_SCHEMA = "fs-bench-pro-prepared-historical-access-v1"
HISTORICAL_SELECTIONS = {
    "v016-access-boundary-before-v1": ("v016-history-boundary-cycle-k100-v1", "main", 48),
    "v016-access-boundary-after-v1": ("v016-history-boundary-cycle-k100-v1", "main", 49),
    "v016-access-inode-before-v1": ("v016-history-namespace-inode-k100-v1", "main", 94),
    "v016-access-inode-after-v1": ("v016-history-namespace-inode-k100-v1", "main", 95),
    "v016-access-fork-point-v1": ("v016-branch-convergent-content-v1", "trunk", 5),
    "v016-access-divergent-head-v1": ("v016-branch-fork-descendant-v1", "B", 10),
}


def historical_plan(case):
    access, fixture = case["historical_access"], case["fixture"]
    expected = HISTORICAL_SELECTIONS.get(case["id"])
    if (access.get("schema") != "original-v016-historical-access-v1" or expected is None
            or (access.get("producer"), access.get("producer_branch_role"), access.get("selected_ordinal")) != expected
            or fixture.get("producer") != expected[0] or case.get("v016_case") != case["id"]
            or type(fixture.get("seed")) is not int or fixture["seed"] != 1
            or type(access.get("selected_ordinal")) is not int
            or access.get("commits") != 0 or access.get("pre_read") is not False
            or access.get("warmup_execs") != 0 or case.get("proof_only") is not True):
        raise ValueError("exact original historical producer/source role/local ordinal required")
    family, producer = family_case(expected[0])
    if (family["family"] != fixture["producer_family"] or producer["v016_case"] != expected[0]
            or producer["fixture"]["seed"] != 1):
        raise ValueError("original historical producer definition/seed differs")
    if producer.get("branch_schedule"):
        rows = producer["branch_schedule"]["branches"]
        roles = [row["role"] for row in rows]; limits = {row["role"]: row["local_commits"] for row in rows}
        sources = {row["role"]: {"role": row["fork_source"].get("source_role"), "local": row["fork_source"].get("local_commit", 0)} for row in rows}
        total = producer["branch_schedule"]["created_commit_acknowledgements"]
        graph_roles = ["initial", *roles]
    else:
        roles = ["main"]; limits = {"main": producer["history_schedule"]["commits"]}
        sources = {"main": {"role": None, "local": 0}}; total = limits["main"]; graph_roles = roles
    role = expected[1].lower() if expected[1] == "B" else expected[1]
    schedule = access["producer_schedule"]
    if (role not in limits or not 1 <= expected[2] <= limits[role] or access["producer_local_commits"] != limits[role]
            or schedule["created_commit_acknowledgements"] != total
            or schedule["retained_root_references"] != total + 1 or access["declared_root_references"] != total + 1
            or [(row["role"], row["commits"]) for row in schedule["execution_order"]] != [(r, limits[r]) for r in roles]):
        raise ValueError("complete original historical producer schedule required")
    return {"producer_family": family["family"], "producer_case": producer["v016_case"], "seed": 1,
            "roles": roles, "graph_roles": graph_roles, "local_commits": limits, "fork_sources": sources,
            "acknowledgements": total, "original_source_role": expected[1], "source_role": role,
            "selected_local": expected[2], "producer_definition_sha256": hashlib.sha256(json.dumps(producer, sort_keys=True).encode()).hexdigest(),
            "access_definition_sha256": hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()}


def history_ack(record, role):
    fields = record["commit"]["fields"]
    return {"role": role, "local": record["index"], "commit_id": fields["commit_id"],
            "layer_stack_id": fields["stack"], "root_id": fields["root"],
            "parent_commit_id": None if fields["parent"] == "-" else fields["parent"], "base_layer_id": fields["base_layer"]}


def historical_fixture_scope(source):
    """Exact producer code; exclude only the reviewed access reuse adapters."""
    module = ast.parse(source)
    adapters = {"historical_fixture_scope", "historical_adapter_scope", "historical_source_admission", "load_closed_history_producer",
                "validate_closed_history_producer", "prepare_historical_workspace", "install_closed_history_store"}
    module.body = [node for node in module.body
                   if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in adapters]
    module.body = [node for node in module.body if not isinstance(node, ast.Import)
                   or [alias.name for alias in node.names] not in (["ast"], ["subprocess"])]
    added_guard = ast.parse('if "source_admission" in dependency and dependency["source_admission"] != admitted["source_admission"]:\n    raise ValueError("historical producer source admission receipt changed")').body[0]
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "validate_historical_helpers":
            node.body = [item for item in node.body if ast.dump(item, include_attributes=False)
                         != ast.dump(added_guard, include_attributes=False)]
    return ast.dump(module, include_attributes=False)


def historical_adapter_scope(source, kind):
    """Only reviewed access-proof/report functions differ; producer stays exact."""
    if kind == "workspace":
        source = source.replace("'performance_mode': 'N/A — original historical-access VERIFY-ONLY'",
                                "'performance_mode': 'verification-only', 'performance_description': 'original historical-access VERIFY-ONLY'")
        adapters = {"access_graph_proof"}
    elif kind == "receipts":
        adapters = {"result_rows"}
    else:
        raise ValueError("unknown historical non-producer adapter scope")
    module = ast.parse(source)
    module.body = [node for node in module.body if not isinstance(node, ast.FunctionDef) or node.name not in adapters]
    return ast.dump(module, include_attributes=False)


def historical_source_admission(closed, attempt, current):
    """Keep original identity and admit only unchanged closed producer execution."""
    original = attempt.get("identity", {})
    if (current.get("source_clean") is not True or original.get("source_clean") is not True
            or original.get("source_commit") != closed["source_commit"]
            or original.get("source_tree") != closed["source_tree"]
            or original.get("product_tree") != closed["product_tree"]
            or attempt.get("source_commit") != closed["source_commit"]
            or closed["product_tree"] != current["product_tree"]):
        raise ValueError("closed producer original clean execution identity required")
    previous, active = original.get("files", {}), current.get("files", {})
    if not previous or set(previous) != set(active):
        raise ValueError("closed producer complete source membership changed")
    prefix = "benchmark/fs-bench-pro/"
    adapters = {prefix + "bench.py", prefix + "engine/fixtures.py", prefix + "engine/workspace.py", prefix + "engine/receipts.py"}
    changed = [path for path in previous if previous[path] != active[path]]
    if any(path not in adapters for path in changed):
        raise ValueError("closed producer execution/model/workload source changed")
    for path in changed:
        if path.endswith("/bench.py"):
            continue  # Setup invokes the controller directly, never this CLI.
        old = subprocess.check_output(["git", "show", closed["source_commit"] + ":" + path],
                                      cwd=identity.ROOT, timeout=15)
        if hashlib.sha256(old).hexdigest() != previous[path]:
            raise ValueError("closed producer original source blob seal differs")
        new = subprocess.check_output(["git", "show", current["source_commit"] + ":" + path],
                                      cwd=identity.ROOT, timeout=15)
        if hashlib.sha256(new).hexdigest() != active[path]:
            raise ValueError("closed producer current source blob seal differs")
        if path.endswith("/fixtures.py"):
            equal = historical_fixture_scope(old.decode()) == historical_fixture_scope(new.decode())
        else:
            kind = "workspace" if path.endswith("/workspace.py") else "receipts"
            equal = historical_adapter_scope(old.decode(), kind) == historical_adapter_scope(new.decode(), kind)
        if not equal:
            raise ValueError("closed producer reviewed adapter-only source scope differs")
    return {"status": "PASS", "original_source_commit": closed["source_commit"],
            "original_source_tree": closed["source_tree"], "current_source_commit": current["source_commit"],
            "current_source_tree": current["source_tree"], "exact_source_files": len(previous) - len(changed),
            "reviewed_adapter_only_changes": changed, "product_tree": current["product_tree"],
            "scope": "unchanged original complete setup producer; original receipts and source identity preserved"}


def load_closed_history_producer(folder, case, build, current):
    """Explicit reuse of a sealed setup dependency, never a measured receipt."""
    prior = load(folder)
    if prior.get("schema") != HISTORICAL_PREPARED_SCHEMA or prior.get("family") != "historical_access":
        raise ValueError("reuse requires a complete historical setup preparation")
    closed = prior["closed_producer"]
    plan = historical_plan(case)
    genesis = historical_genesis(plan, Path(folder), None, build, current, closed["initial_prepared"])
    validate_closed_history_producer(case, closed, genesis, current)
    return closed, genesis


def validate_closed_history_producer(case, closed, genesis, current):
    """Read authenticated setup custody/graph only; never open or repair its Store."""
    plan = historical_plan(case)
    if (closed.get("schema") != "fs-bench-pro-closed-history-producer-v1" or closed.get("status") != "PASS"
            or closed.get("producer_case") != plan["producer_case"] or closed.get("producer_family") != plan["producer_family"]
            or closed.get("product_tree") != current["product_tree"] or type(closed.get("seed")) is not int or closed["seed"] != 1
            or closed.get("setup_only") is not True or type(closed.get("sample_count")) is not int or closed["sample_count"] != 0
            or closed.get("helpers") != genesis["helpers"] or Path(closed["initial_prepared"]).resolve() != Path(genesis["prepared_folder"]).resolve()):
        raise ValueError("new closed setup-only historical producer binding required")
    for path, digest in (("manifest", "manifest_sha256"), ("sealed_store", "store_sha256"),
                         ("transcript", "transcript_sha256"), ("receipt", "receipt_sha256")):
        if not Path(closed[path]).is_absolute() or identity.sha256(closed[path]) != closed[digest]:
            raise ValueError("closed historical producer file seal differs: " + path)
    if closed["manifest_sha256"] != genesis["provision"]["manifest_sha256"]:
        raise ValueError("closed historical producer pristine manifest changed")
    summary = json.loads(Path(closed["receipt"]).read_text())
    if summary != {key: value for key, value in closed.items() if key not in ("receipt", "receipt_sha256")}:
        raise ValueError("closed historical producer summary correspondence differs")
    custody = closed["custody"]
    if (custody.get("state") != "KNOWN_STOP" or custody.get("all_workspaces_gone") is not True
            or type(custody.get("active_executions")) is not int or custody["active_executions"] != 0):
        raise ValueError("closed historical producer requires exact End/Gone/KnownStop custody")
    for path, digest in (("runtime_events", "runtime_events_sha256"), ("export_completion", "export_completion_sha256")):
        if identity.sha256(custody[path]) != custody[digest]:
            raise ValueError("closed historical producer custody evidence changed")
    events = [json.loads(line) for line in Path(custody["runtime_events"]).read_text().splitlines()]
    export = json.loads(Path(custody["export_completion"]).read_text())
    if (not events or events[-1].get("event") != "finished" or export.get("status") != "PASS"
            or export.get("exit_code") != 0 or closed.get("raw_export") is None):
        raise ValueError("closed historical producer runtime/export completion missing")
    normalization = closed.get("normalization", {})
    if (identity.sha256(normalization["receipt"]) != normalization["receipt_sha256"]
            or normalization.get("path") != closed["sealed_store"] or normalization.get("raw_directory") != closed["raw_export"]):
        raise ValueError("closed historical producer exact normalization binding required")
    normalized = json.loads(Path(normalization["receipt"]).read_text())
    if (normalized.get("schema") != "fs-bench-pro-closed-store-normalization-v1" or normalized.get("status") != "PASS"
            or normalized.get("profile") != "Disposable/WAL/OFF" or normalized.get("raw_unchanged") is not True
            or normalized.get("source_closed") is not True or normalized.get("target_closed") is not True
            or normalized.get("path") != closed["sealed_store"] or normalized.get("raw_directory") != closed["raw_export"]
            or normalized.get("raw_files") != normalization.get("raw_files")
            or normalized.get("raw_files_after") != normalization.get("raw_files")
            or normalized.get("copied_files") != normalization.get("raw_files")
            or normalized.get("normalized_identity") != normalization.get("normalized_identity")
            or normalization["normalized_identity"]["sha256"] != closed["store_sha256"]):
        raise ValueError("closed historical producer normalization source/output/profile/closure differs")
    profile = {"source_uri_mode": "ro", "source_query_only": 1, "source_synchronous": 0, "target_synchronous": 0,
               "source_journal_mode": "wal", "target_journal_mode": "wal", "backup_pages_per_step": 128,
               "backup_sleep_seconds": 0, "backup_attempts": 1, "checkpoint": [0, 0, 0]}
    progress = normalized.get("backup_progress", {})
    if (any(normalized.get(key) != value for key, value in profile.items())
            or any(type(normalized.get(key)) is not int for key in ("source_query_only", "source_synchronous", "target_synchronous", "backup_pages_per_step", "backup_sleep_seconds", "backup_attempts"))
            or type(progress.get("calls")) is not int or progress["calls"] < 1
            or progress.get("remaining_pages") != 0 or progress.get("last_status") != 101
            or type(progress.get("total_pages")) is not int or progress["total_pages"] < 1
            or normalized.get("helper_sha256") != identity.sha256(identity.ROOT / "benchmark/fs-bench-pro/engine/oracle.py")):
        raise ValueError("closed historical producer original normalization profile/backup/helper differs")
    raw = Path(closed["raw_export"]); raw_files = normalization["raw_files"]
    if (not raw.is_absolute() or "store.sqlite" not in raw_files
            or {path.name for path in raw.iterdir() if path.is_file()} != set(raw_files)
            or any(name not in ("store.sqlite", "store.sqlite-wal", "store.sqlite-shm", "store.sqlite-journal")
                   or identity.sha256(raw / name) != seal["sha256"] or (raw / name).stat().st_size != seal["size"]
                   for name, seal in raw_files.items())
            or Path(closed["sealed_store"]).stat().st_size != normalization["normalized_identity"]["size"]
            or any(Path(closed["sealed_store"] + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))):
        raise ValueError("closed historical producer unchanged raw export/standalone normalized bytes required")
    with Path(closed["sealed_store"]).open("rb") as stream:
        header = stream.read(100)
    if header[:16] != b"SQLite format 3\0" or header[18:20] != bytes([2, 2]):
        raise ValueError("closed historical producer normalized WAL header required")
    for path, digest in (("attempt_receipt", "attempt_receipt_sha256"), ("attempt_manifest", "attempt_manifest_sha256")):
        if identity.sha256(closed[path]) != closed[digest]:
            raise ValueError("closed historical producer attempt receipt/manifest changed")
    receipts.verify_manifest(Path(closed["attempt_manifest"]).parent)
    attempt = json.loads(Path(closed["attempt_receipt"]).read_text())
    if (attempt.get("setup_only") is not True or type(attempt.get("sample_count")) is not int or attempt["sample_count"] != 0 or attempt.get("status") == "FAIL"
            or attempt.get("functional_status") != "PASS" or attempt.get("proof_status") != "PASS"
            or attempt.get("cleanup") != "Gone" or attempt.get("custody") != "KNOWN_STOP"
            or attempt.get("case") != plan["producer_case"] or attempt.get("source_commit") != closed["source_commit"]
            or attempt.get("product_tree") != current["product_tree"]):
        raise ValueError("original historical producer complete setup attempt and closure required")
    source_admission = historical_source_admission(closed, attempt, current)
    branches = closed["graph"]["branches"]
    if set(branches) != set(plan["graph_roles"]):
        raise ValueError("complete original historical producer branch membership differs")
    expected_acks, by_role, tuples = [], {}, {}
    transcript = ["topology-v1\t" + plan["producer_case"]]
    anchor = branches[plan["graph_roles"][0]]
    for role in plan["graph_roles"]:
        branch = branches[role]
        if branch["stack"] != anchor["stack"] or branch["base_layer"] != anchor["base_layer"]:
            raise ValueError("historical producer branches must retain original shared stack/base")
        count = plan["local_commits"].get(role, 0)
        rows = branch["commits"]
        if [row["index"] for row in rows] != list(range(1, count + 1)) or any(type(row["index"]) is not int for row in rows):
            raise ValueError("every original role-local historical Commit acknowledgement required")
        source = plan["fork_sources"].get(role, {"role": None, "local": 0})
        if branch.get("source_role") != source["role"] or branch.get("source_local", 0) != source["local"]:
            raise ValueError("historical producer original fork point differs")
        parent, root = branch["initial_parent"], branch["initial_root"]
        if source["role"]:
            fork = by_role[source["role"]][source["local"]]
            if parent != fork["commit_id"] or root != fork["root_id"]:
                raise ValueError("historical producer inherited Commit/root differs")
        elif parent != "-":
            raise ValueError("historical producer genesis parent must be absent")
        elif branch["initial_root"] != anchor["initial_root"]:
            raise ValueError("historical producer Layer fork must retain pristine initial root")
        columns = ["branch", role, branch["branch_id"], branch["name"], branch["stack"], branch["base_layer"], parent, root,
                   branch["final_head"], branch["final_root"], source["role"] or "-", str(source["local"])]
        transcript.append(columns); by_role[role] = {}
        for row in rows:
            ack = history_ack(row, role)
            if (ack["parent_commit_id"] != (None if parent == "-" else parent)
                    or ack["layer_stack_id"] != branch["stack"] or ack["base_layer_id"] != branch["base_layer"]):
                raise ValueError("historical producer acknowledged parent/stack/base differs")
            canonical = {key: value for key, value in ack.items() if key not in ("role", "local")}
            if ack["commit_id"] in tuples and tuples[ack["commit_id"]] != canonical:
                raise ValueError("historical producer conflicting canonical Commit tuple")
            tuples[ack["commit_id"]] = canonical; expected_acks.append(ack); by_role[role][row["index"]] = ack
            transcript.append(["commit", role, str(row["index"]), ack["commit_id"], ack["layer_stack_id"], ack["root_id"],
                               ack["parent_commit_id"] or "-", ack["base_layer_id"]])
            parent, root = ack["commit_id"], ack["root_id"]
        if branch["final_head"] != parent or branch["final_root"] != root:
            raise ValueError("historical producer final head/root differs from last ACK")
    if closed.get("acknowledgements") != expected_acks or len(expected_acks) != plan["acknowledgements"]:
        raise ValueError("complete exact historical producer acknowledgement list required")
    actual = Path(closed["transcript"]).read_text().splitlines()
    if len(actual) != len(transcript) or actual[0] != transcript[0]:
        raise ValueError("historical producer transcript membership differs")
    for wanted, line in zip(transcript[1:], actual[1:]):
        fields = line.split("\t")
        if fields[:len(wanted)] != wanted or len(fields) != (12 if wanted[0] == "branch" else 10):
            raise ValueError("historical producer transcript tuple differs")
    return {"plan": plan, "source_admission": source_admission, "selected": by_role[plan["source_role"]][plan["selected_local"]],
            "distinct_commit_tuples": len(tuples), "scope": "all original role-local ACKs/forks/parents/heads and known closed setup custody; equal canonical tuples retained"}


def historical_genesis(plan, folder, build_folder, build, current, supplied=None):
    if supplied is None:
        supplied = folder / "genesis"
        prepare(plan["producer_case"], supplied, build_folder)
    prepared = load(supplied, plan["producer_case"])
    _, producer = family_case(plan["producer_case"])
    if (prepared.get("schema") not in ("fs-bench-pro-prepared-workspace-v1", CONTEXT_PREPARED_SCHEMA)
            or prepared.get("family") != plan["producer_family"] or prepared.get("case") != plan["producer_case"]
            or prepared["identity"]["product_tree"] != current["product_tree"]
            or prepared.get("global_profile") != "Disposable/WAL/OFF"
            or prepared.get("master_measurement_mounts", 0) != 0
            or not prepared.get("native_verification")
            or any(row.get("verification_status") != "pass" for row in prepared["native_verification"].values())):
        raise ValueError("authenticated immutable original producer genesis preparation required")
    validate_runtime_helpers(producer, prepared, build)
    return {**prepared, "prepared_folder": str(Path(supplied).resolve())}


def historical_native_selection(case, plan, folder, build, binding):
    root = folder / "selected-native"; writer = build["binaries"]["workspace-writer"]
    compact = plan["producer_family"] == "branch_development"
    prefix = [plan["producer_case"], plan["source_role"], str(plan["selected_local"])] if compact else [plan["producer_case"], str(plan["selected_local"])]
    argv = [writer["path"], "materialize-context" if compact else "expected-step", *prefix, str(root)]
    made = receipts.command(argv, folder, "historical-selected-native", 120)
    summary = json.loads(Path(made["stdout"]).read_text()); manifest = root.with_suffix(".manifest.tsv")
    digest = identity.sha256(manifest)
    if (summary.get("case") != plan["producer_case"] or type(summary.get("step")) is not int
            or summary["step"] != plan["selected_local"] or type(summary.get("seed")) is not int or summary["seed"] != 1
            or summary.get("manifest_sha256" if compact else "fixture_digest") != digest
            or compact and summary.get("role") != plan["source_role"]
            or manifest.read_text().splitlines()[0] != "workspace-independent-manifest-v1"):
        raise ValueError("independent historical selected native producer/role/local ordinal differs")
    proof_argv = [writer["path"], "verify-context" if compact else "verify-step", *prefix, str(root)] + (["-"] if compact else [])
    checked = receipts.command(proof_argv, folder, "historical-selected-native-check", 120)
    proof = json.loads(Path(checked["stdout"]).read_text())
    if (proof.get("verification_status") != "pass" or proof.get("case") != plan["producer_case"]
            or proof.get("step") != plan["selected_local"] or compact and proof.get("role") != plan["source_role"]):
        raise ValueError("original independent historical selected native verifier failed")
    reads = []
    for target in case["historical_access"]["reads"]:
        path = root / target["path"]; data = path.read_bytes()
        if len(data) != target["bytes"]:
            raise ValueError("original historical declared full read length differs")
        reads.append({"path": target["path"], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "hex": data.hex()})
    absent = case["historical_access"]["absent"]
    if any((root / target).exists() or (root / target).is_symlink() for target in absent):
        raise ValueError("original historical selected alias absence differs")
    return {"original_source_role": plan["original_source_role"], "source_role": plan["source_role"], "local": plan["selected_local"],
            "manifest": str(manifest), "manifest_sha256": digest, "staged_manifest": "/code/access/selected-manifest.tsv",
            "native_root": str(root), "native_summary": summary, "read_targets": reads, "absent": absent,
            "generator": {"argv": argv, "binary_sha256": writer["sha256"], "source_binding": binding,
                          "receipt": str(Path(made["stdout"]).resolve()), "receipt_sha256": identity.sha256(made["stdout"])},
            "native_verification": {"argv": proof_argv, "verification_status": "pass", "result": proof,
                                    "receipt": str(Path(checked["stdout"]).resolve()), "receipt_sha256": identity.sha256(checked["stdout"])}}


def install_closed_history_store(closed, genesis, folder, build, *, deadline=None, sample=False):
    """Setup-only independent byte install of complete closed history; no Init."""
    purpose = ("fresh measured Init byte installation into owned sample volume" if sample else
               "new immutable full historical producer byte copy; never a measured/mutated sample")
    scope = ("complete freshly sealed measured Init copied unchanged into owned sample volume; no additional Init" if sample else
             "complete known-Stop normalized producer copied unchanged, full history preserved, no selected-root Init or pre-read")
    folder.mkdir(); store = folder / "store.sqlite"; manifest = folder / "installed.manifest"
    shutil.copy2(closed["sealed_store"], store); shutil.copy2(closed["manifest"], manifest)
    if identity.sha256(store) != closed["store_sha256"] or identity.sha256(manifest) != closed["manifest_sha256"]:
        raise ValueError("closed historical producer host byte copy differs")
    volume = ("layerfs-fsb-sample-" if sample else "layerfs-fsb-history-master-") + uuid.uuid4().hex[:16]
    container = "layerfs-fsb-history-install-" + uuid.uuid4().hex[:16]
    receipts.write_new(folder / "resource-claim.json", {"volume": volume, "container": container, "created_by_this_run": True,
                       "purpose": purpose,
                       "failure_disposition": "retain failed/uncertain resources, no retry"})
    docker = ["docker", "--host", "unix://" + build["socket"]]
    def call(argv, label):
        import time
        seconds = 15 if deadline is None else min(15, deadline-time.monotonic())
        if seconds <= 0:
            raise TimeoutError("independent sealed Store installation proof deadline expired")
        return receipts.command(argv, folder, label, seconds)
    made = call([*docker, "volume", "create", volume], "historical-master-volume")
    if Path(made["stdout"]).read_text().strip() != volume:
        raise ValueError("closed historical master volume acknowledgement differs")
    uid, gid = genesis["source_uid"], genesis["source_gid"]
    if type(uid) is not int or type(gid) is not int or uid < 0 or gid < 0:
        raise ValueError("original producer genesis ownership required")
    body = ("set -eu; test ! -e /dest/global; printf '%s\\n' " + shlex.quote(closed["store_sha256"] + "  /input.sqlite") +
            " | sha256sum --check -; mkdir -m 700 /dest/global; cp --reflink=never --sparse=never --preserve=mode,timestamps /input.sqlite /dest/global/store.sqlite; "
            "cmp /input.sqlite /dest/global/store.sqlite; chown 0:0 /dest/global /dest/global/store.sqlite; "
            "chmod 600 /dest/global/store.sqlite; stat -c 'backing_directory=%u:%g:%a' /dest/global; "
            "stat -c 'backing_store=%u:%g:%a' /dest/global/store.sqlite; sha256sum /dest/global/store.sqlite")
    call([*docker, "create", "--name", container, "--user", "0:0", "--network", "none", "-v", volume + ":/dest",
          identity.IMAGE, "/bin/bash", "-euo", "pipefail", "-c", body], "historical-master-create")
    call([*docker, "cp", "--archive", str(store), container + ":/input.sqlite"], "historical-master-input")
    installed = call([*docker, "start", "--attach", container], "historical-master-install")
    lines = Path(installed["stdout"]).read_text().splitlines()
    if (lines[-3:-1] != ["backing_directory=0:0:700", "backing_store=0:0:600"]
            or [line.split()[0] for line in lines[-1:]] != [closed["store_sha256"]]):
        raise ValueError("independent closed full historical Store installation differs")
    call([*docker, "rm", container], "historical-master-remove-passing")
    result = {"schema": "fs-bench-pro-installed-history-store-v1", "status": "PASS", "volume": volume,
              "sealed_store": str(store), "store_sha256": identity.sha256(store), "manifest": str(manifest),
              "manifest_sha256": identity.sha256(manifest), "global_profile": "Disposable/WAL/OFF",
              "construction_workers": 1, "attempt": installed, "source": closed["sealed_store"],
              "backing_owner": "0:0", "backing_directory_mode": "0700", "backing_store_mode": "0600",
              "scope": scope}
    receipts.write_new(folder / "installed-history.json", result)
    return volume, result


def prepare_historical_workspace(family, case, folder, build_folder, genesis_prepared_folder=None, closed_producer_folder=None):
    from . import workspace
    plan = historical_plan(case)
    build, current = identity.load_build(build_folder), identity.source_identity()
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=False)
    shared = None
    cache = next((parent for parent in folder.parents if parent.name == "kept-fixtures"), None)
    if closed_producer_folder is None and genesis_prepared_folder is None and cache is not None:
        for candidate in sorted(cache.glob("*/*/prepared.json")):
            prior = json.loads(candidate.read_text())
            producer = prior.get("closed_producer", {})
            if (prior.get("schema") == HISTORICAL_PREPARED_SCHEMA and prior.get("status") == "PASS"
                    and prior.get("identity", {}).get("source_commit") == current["source_commit"]
                    and prior.get("store_builder_key") == prepared_inputs.product_store_key(current)
                    and (prior.get("source_uid"), prior.get("source_gid")) == (os.getuid(), os.getgid())
                    and producer.get("producer_case") == plan["producer_case"]
                    and producer.get("producer_family") == plan["producer_family"]):
                shared = load(candidate.parent)
                closed_producer_folder = candidate.parent
                break
    if closed_producer_folder is None:
        genesis = historical_genesis(plan, folder, build_folder, build, current, genesis_prepared_folder)
        _, producer = family_case(plan["producer_case"])
        closed = workspace.prepare_history_producer(plan["producer_family"], producer, genesis["prepared_folder"], build_folder, folder / "producer")
    else:
        if genesis_prepared_folder is not None:
            raise ValueError("closed producer supplies its exact original genesis")
        closed, genesis = load_closed_history_producer(closed_producer_folder, case, build, current)
    admitted = validate_closed_history_producer(case, closed, genesis, current)
    binding = {"source_commit": current["source_commit"], "source_tree": current["source_tree"],
               "producer_definition_sha256": plan["producer_definition_sha256"], "access_definition_sha256": plan["access_definition_sha256"],
               "model_files": {path: current["files"][path] for path in CONTEXT_SOURCE_FILES}}
    selected = historical_native_selection(case, plan, folder, build, binding)
    selected["acknowledged_commit"] = admitted["selected"]
    dependency = {**historical_producer_dependency(case), "status": "PASS", "plan": plan,
                  "initial_prepared": genesis["prepared_folder"], "initial_prepared_manifest_sha256": identity.sha256(Path(genesis["prepared_folder"]) / "manifest.json"),
                  "source_binding": binding, "source_admission": admitted["source_admission"],
                  "reused_closed_producer": str(Path(closed_producer_folder).resolve()) if closed_producer_folder is not None else None,
                  "closed_producer_receipt_sha256": closed["receipt_sha256"]}
    code = folder / "code"; code.mkdir(); (code / "writers").mkdir(); (code / "access").mkdir()
    copies = [(build["binaries"]["workload-linux"]["path"], "writers/workload"),
              (identity.ROOT / "benchmark/fs-bench-pro/families/historical_access/workload.sh", "workload.sh"),
              (selected["manifest"], "access/selected-manifest.tsv")]
    for origin, relative in copies:
        shutil.copy2(origin, code / relative); (code / relative).chmod(0o555 if relative in ("workload.sh", "writers/workload") else 0o444)
    metadata = {"producer_dependency": dependency, "historical_selection": selected}
    receipts.write_new(code / "access/dependency.json", metadata); (code / "access/dependency.json").chmod(0o444)
    helpers = {"root": str(code), "files": {str(path.relative_to(code)): identity.sha256(path) for path in sorted(code.rglob("*")) if path.is_file()}}
    helpers["sha256"] = hashlib.sha256(json.dumps(helpers["files"], sort_keys=True).encode()).hexdigest()
    result = {"schema": HISTORICAL_PREPARED_SCHEMA, "status": "PASS", "family": family["family"], "case": case["id"],
              "recipe": case["fixture"]["recipe"], "identity": current, "fixture": {**genesis["fixture"], "recipe": case["fixture"]["recipe"]},
              "expectation": selected["native_summary"], "native_verification": {"historical_selected": selected["native_verification"]},
              "helpers": helpers, "closed_producer": closed, "producer_dependency": dependency, "historical_selection": selected,
              "initial_prepared": genesis["prepared_folder"], "source_uid": genesis["source_uid"], "source_gid": genesis["source_gid"],
              "master_measurement_mounts": 0, "global_profile": "Disposable/WAL/OFF", "overlay_profile": "MEMORY/OFF/EXCLUSIVE",
              "construction_workers": 1, "setup": "explicit reused full closed setup-only producer" if closed_producer_folder is not None else "new full closed setup-only producer",
              "setup_scope": "original complete history; independent immutable byte copy; no pre-read or warmup",
              "cache": "uncontrolled OS cache; original two-pass reader/verifier on same mount; verification only, no performance or cold claim"}
    validate_historical_helpers(case, result, build, genesis=genesis)
    if shared is None:
        result["master_volume"], result["provision"] = install_closed_history_store(closed, genesis, folder / "project", build)
    else:
        result["master_volume"], result["provision"] = shared["master_volume"], shared["provision"]
        result["closed_master_reuse"] = {"prepared": str(closed_producer_folder.resolve()),
            "prepared_manifest_sha256": identity.sha256(closed_producer_folder / "manifest.json"),
            "store_sha256": closed["store_sha256"],
            "scope": "complete sealed original history and installed master; current-case selected native oracle remains independent"}
    seal_prepared(folder, result, build_folder)
    return result


def validate_historical_helpers(case, prepared, build, genesis=None):
    plan = historical_plan(case); dependency = prepared["producer_dependency"]
    if (prepared.get("schema") != HISTORICAL_PREPARED_SCHEMA or prepared.get("case") != case["id"]
            or prepared.get("family") != "historical_access" or dependency.get("status") != "PASS"
            or dependency.get("plan") != plan or dependency.get("initial_prepared") != prepared["initial_prepared"]
            or identity.sha256(Path(prepared["initial_prepared"]) / "manifest.json") != dependency["initial_prepared_manifest_sha256"]):
        raise ValueError("exact historical access/producer preparation dependency required")
    if genesis is None:
        genesis = {**load(prepared["initial_prepared"], plan["producer_case"]), "prepared_folder": prepared["initial_prepared"]}
    admitted = validate_closed_history_producer(case, prepared["closed_producer"], genesis, prepared["identity"])
    if "source_admission" in dependency and dependency["source_admission"] != admitted["source_admission"]:
        raise ValueError("historical producer source admission receipt changed")
    binding = dependency["source_binding"]
    if (binding.get("producer_definition_sha256") != plan["producer_definition_sha256"]
            or binding.get("access_definition_sha256") != plan["access_definition_sha256"]
            or any(binding.get("model_files", {}).get(path) != identity.sha256(identity.ROOT / path) for path in CONTEXT_SOURCE_FILES)
            or dependency.get("closed_producer_receipt_sha256") != prepared["closed_producer"]["receipt_sha256"]):
        raise ValueError("historical producer/native model source binding changed")
    selected = prepared["historical_selection"]
    compact = plan["producer_family"] == "branch_development"
    prefix = [plan["producer_case"], plan["source_role"], str(plan["selected_local"])] if compact else [plan["producer_case"], str(plan["selected_local"])]
    generator, proof = selected["generator"], selected["native_verification"]
    argv = generator["argv"]; root = Path(selected["native_root"])
    if (selected.get("acknowledged_commit") != admitted["selected"] or selected.get("source_role") != plan["source_role"]
            or selected.get("original_source_role") != plan["original_source_role"] or selected.get("local") != plan["selected_local"]
            or argv[1:] != ["materialize-context" if compact else "expected-step", *prefix, str(root)]
            or generator.get("source_binding") != binding or generator.get("binary_sha256") != build["binaries"]["workspace-writer"]["sha256"]
            or identity.sha256(argv[0]) != generator["binary_sha256"]
            or identity.sha256(generator["receipt"]) != generator["receipt_sha256"]
            or json.loads(Path(generator["receipt"]).read_text()) != selected["native_summary"]
            or Path(selected["manifest"]) != root.with_suffix(".manifest.tsv")
            or identity.sha256(selected["manifest"]) != selected["manifest_sha256"]
            or selected["native_summary"].get("manifest_sha256" if compact else "fixture_digest") != selected["manifest_sha256"]
            or selected["native_summary"].get("case") != plan["producer_case"]
            or selected["native_summary"].get("step") != plan["selected_local"]
            or compact and selected["native_summary"].get("role") != plan["source_role"]
            or proof["argv"] != [argv[0], "verify-context" if compact else "verify-step", *prefix, str(root)] + (["-"] if compact else [])
            or proof.get("verification_status") != "pass" or proof["result"].get("verification_status") != "pass"
            or proof["result"].get("case") != plan["producer_case"] or proof["result"].get("step") != plan["selected_local"]
            or compact and proof["result"].get("role") != plan["source_role"]
            or identity.sha256(proof["receipt"]) != proof["receipt_sha256"] or json.loads(Path(proof["receipt"]).read_text()) != proof["result"]):
        raise ValueError("historical selected Commit/native state/receipt binding differs")
    if prepared.get("native_verification") != {"historical_selected": proof} or prepared.get("expectation") != selected["native_summary"]:
        raise ValueError("historical native fixture/parity correspondence differs")
    lines = Path(selected["manifest"]).read_text().splitlines()
    if lines[0] != "workspace-independent-manifest-v1":
        raise ValueError("original complete historical native manifest required")
    rows = [line.split("\t") for line in lines[1:]]
    if any(len(row) != 7 for row in rows) or len({row[0] for row in rows}) != len(rows):
        raise ValueError("historical native manifest membership malformed")
    entries = {row[0]: row for row in rows}
    targets = selected["read_targets"]
    if ([(row.get("path"), row.get("bytes")) for row in targets] != [(row["path"], row["bytes"]) for row in case["historical_access"]["reads"]]
            or selected.get("absent") != case["historical_access"]["absent"] or any(path in entries for path in selected["absent"])):
        raise ValueError("original historical read/absent target membership differs")
    for target in targets:
        entry = entries[target["path"]]
        if entry[1] == "hardlink":
            entry = entries[bytes.fromhex(entry[6]).decode("utf-8")]
        data = bytes.fromhex(target["hex"])
        if (entry[1] != "file" or int(entry[2]) != target["bytes"] or len(data) != target["bytes"]
                or hashlib.sha256(data).hexdigest() != target["sha256"] or entry[6] != target["sha256"]):
            raise ValueError("original historical full payload bytes/SHA differs from independent native algebra")
    root = Path(prepared["helpers"]["root"]); seals = prepared["helpers"]["files"]
    wanted = {"writers/workload": build["binaries"]["workload-linux"]["sha256"],
              "workload.sh": identity.sha256(identity.ROOT / "benchmark/fs-bench-pro/families/historical_access/workload.sh"),
              "access/selected-manifest.tsv": selected["manifest_sha256"],
              "access/dependency.json": seals.get("access/dependency.json")}
    if (set(seals) != set(wanted) or {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()} != set(wanted)
            or selected.get("staged_manifest") != "/code/access/selected-manifest.tsv"
            or any(seals[path] != digest or identity.sha256(root / path) != digest for path, digest in wanted.items())
            or json.loads((root / "access/dependency.json").read_text()) != {"producer_dependency": dependency, "historical_selection": selected}):
        raise ValueError("exact original historical reader/scoped oracle staged helper seal required")
    return {"schema": "fs-bench-pro-historical-helper-admission-v1", "status": "PASS", "selected_commit": admitted["selected"],
            "scope": "fresh closed original producer dependency; exact local selected Commit, independent full read targets and unchanged reader; no Store open, mutation, regeneration or pre-read"}


def prepare_context_native(case, folder, build, binding):
    """Initial full native input; only declared role-specific payload checkpoints."""
    plan = context_plan(case); writer = build["binaries"]["workspace-writer"]
    manifests = folder / "context-manifests"; manifests.mkdir()
    native, checkpoints, expectation = {}, [], {}
    def materialize(role, step, root, label):
        root.parent.mkdir(parents=True, exist_ok=True)
        argv = [writer["path"], "materialize-context", case["v016_case"], role, str(step), str(root)]
        made = receipts.command(argv, folder, label, 120)
        summary = json.loads(Path(made["stdout"]).read_text())
        full = root.with_suffix(".manifest.tsv")
        scope = root.with_suffix(".scope.tsv") if case.get("m1_schedule") else full
        if (summary.get("case") != case["v016_case"] or summary.get("role") != role
                or type(summary.get("step")) is not int or summary["step"] != step
                or type(summary.get("seed")) is not int or summary["seed"] != 1
                or summary.get("manifest_sha256") != identity.sha256(full)
                or summary.get("context_manifest_sha256") != identity.sha256(scope)
                or not isinstance(summary.get("recipe_sha256"), str) or len(summary["recipe_sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in summary["recipe_sha256"])
                or type(summary.get("entries")) is not int or summary["entries"] < 1
                or type(summary.get("logical_bytes")) is not int or summary["logical_bytes"] < 0
                or full.read_text().splitlines()[0] != "workspace-independent-manifest-v1"
                or scope.read_text().splitlines()[0] != ("original-m1-selective-scope-v1" if case.get("m1_schedule") else "workspace-independent-manifest-v1")):
            raise ValueError("original contextual native source/role/step/manifest binding differs")
        summary.update(fixture_digest=identity.sha256(full), recipe_identity=summary["recipe_sha256"],
                       files=sum(row.split("\t")[1] == "file" for row in full.read_text().splitlines()[1:]))
        recipe = {"argv": argv, "binary_sha256": writer["sha256"], "source_binding": binding,
                  "receipt": str(Path(made["stdout"]).resolve()), "receipt_sha256": identity.sha256(made["stdout"])}
        return summary, full, scope, recipe
    def verify_full(root, manifest, label):
        proof = receipts.command([build["binaries"]["edit-host"]["path"], "verify-manifest", str(manifest)],
                                 folder, label, 120, cwd=root)
        result = dict(line.split("=", 1) for line in Path(proof["stdout"]).read_text().splitlines())
        if result.get("verification_status") != "pass":
            raise ValueError("original contextual full native input verification failed")
        native[label] = result
    prepared_inputs.require_context_producer(case, build)
    source = prepared_inputs.source_path(case, build)
    argv = [writer["path"], "materialize-context", case["v016_case"], plan["initial_role"], "0", str(source)]
    fixture = prepared_inputs.make_initial(case, build, argv, folder, "native-context-initial")
    cached = prepared_inputs.load_source(case, build)
    initial_manifest = source.with_suffix(".manifest.tsv")
    scope = source.with_suffix(".scope.tsv") if case.get("m1_schedule") else initial_manifest
    fixture.update(role=plan["initial_role"], fixture_digest=identity.sha256(initial_manifest),
        recipe_identity=fixture["recipe_sha256"],
        files=sum(row.split("\t")[1] == "file" for row in initial_manifest.read_text().splitlines()[1:]))
    initial_recipe = {"argv": cached["generation"]["argv"], "binary_sha256": writer["sha256"],
        "source_binding": binding, "receipt": cached["generation"]["stdout"],
        "receipt_sha256": identity.sha256(cached["generation"]["stdout"]),
        "input_reuse": {"key": cached["key"], "producer_case": cached["producer_case"],
                        "requested_case": case["id"], "requested_role": plan["initial_role"],
                        "manifest_sha256": identity.sha256(source.parent / "manifest.json")}}
    verify_full(source, initial_manifest, "original-context-initial-check")
    modes = folder / "initial-created-modes.tsv"
    modes.write_bytes(b"original-context-created-modes-v1\nrole\tpath\tmode\n")
    qualifier = receipts.command([writer["path"], "verify-context", case["v016_case"],
        plan["initial_role"], "0", str(source), str(modes) if case.get("m1_schedule") else "-"],
        folder, "current-case-shared-initial-check", 120)
    checks = [json.loads(line) for line in Path(qualifier["stdout"]).read_text().splitlines()]
    if not checks or any(row.get("verification_status") != "pass" for row in checks):
        raise ValueError("shared input lacks current-case original context qualification")
    initial_recipe["current_case_qualification"] = qualifier
    initial_recipe["current_case_qualification_sha256"] = identity.sha256(qualifier["stdout"])
    for selected in plan["checkpoints"]:
        role, step = selected["role"], selected["index"]
        root = folder / "context-native" / role / f"state-{step}"
        summary, full, scope, recipe = materialize(role, step, root, f"native-context-{role}-{step}")
        if not case.get("m1_schedule"):
            verify_full(root, full, f"original-context-{role}-{step}-check")
        destination = manifests / role / f"state-{step}.tsv"; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(scope, destination)
        checkpoints.append({"role": role, "index": step, "native_root": str(root), "summary": summary,
                            "native_manifest": str(full), "native_manifest_sha256": identity.sha256(full),
                            "manifest": str(destination), "manifest_sha256": identity.sha256(destination),
                            "staged_manifest": f"/code/context/{role}/manifests/state-{step}.tsv",
                            "native_recipe": recipe, "verification_scope": "original-m1-selective-scope-v1" if case.get("m1_schedule") else "complete-original-native-state",
                            "materialization_metadata": "None mode observations; selected M1 automatic fields are placeholders, not proof" if case.get("m1_schedule") else "original full compact state"})
        if step == plan["local_commits"][role]:
            expectation[role] = summary
    return fixture, expectation, native, checkpoints, initial_recipe


def context_descriptor(path, case, selected):
    rows = Path(path).read_text().splitlines(); role, step, count = selected["role"], selected["index"], selected["members"]
    if rows[:5] != ["original-context-step-payloads-v1", "case\t" + case["v016_case"],
                   "role\t" + role, f"step\t{step}", f"members\t{count}"] or len(rows) != count + 5:
        raise ValueError("original contextual descriptor case/role/step/member binding differs")
    payloads = {}
    for member, row in enumerate(rows[5:], 1):
        fields = row.split("\t"); name = f"member-{member}.bin"
        if len(fields) != 12 or fields[0] != str(member) or fields[11] != name:
            raise ValueError("original contextual member order/path differs")
        target = fields[1]
        if not target or any(part in ("", ".", "..") for part in target.split("/")) or any(c in target for c in "\0\\\r\n"):
            raise ValueError("unsafe original contextual SDK target")
        start, deleted, before, after, size = [int(value) for value in fields[2:7]]
        mode, seconds, nanos = int(fields[8], 8), int(fields[9]), int(fields[10])
        payload = Path(path).parent / name
        if (any(value < 0 or value > 2**64-1 for value in (start, deleted, before, after, size))
                or start+deleted > before or before-deleted+size != after or mode < 0 or mode & ~0o7777
                or not -(2**63) <= seconds < 2**63 or not 0 <= nanos < 1_000_000_000
                or payload.stat().st_size != size or identity.sha256(payload) != fields[7]):
            raise ValueError("original contextual payload/geometry/metadata differs")
        payloads[name] = {"sha256": fields[7], "bytes": size}
    return payloads


def prepare_context_payloads(case, folder, build, binding):
    records = []; writer = build["binaries"]["edit-host"]
    for selected in context_plan(case)["sdk_steps"]:
        role, step = selected["role"], selected["index"]
        output = folder / "context-payloads" / role / f"step-{step}"; output.parent.mkdir(parents=True, exist_ok=True)
        argv = [writer["path"], "prepare-context-step", case["v016_case"], role, str(step), str(output)]
        made = receipts.command(argv, folder, f"original-context-payloads-{role}-{step}", 120)
        summary = json.loads(Path(made["stdout"]).read_text()); descriptor = output / "descriptor.tsv"
        if (summary.get("case") != case["v016_case"] or summary.get("role") != role or type(summary.get("step")) is not int
                or summary["step"] != step or type(summary.get("members")) is not int or summary["members"] != selected["members"]
                or summary.get("descriptor_sha256") != identity.sha256(descriptor)):
            raise ValueError("original contextual SDK generator identity differs")
        staged = f"/code/context/{role}/payloads/step-{step}/descriptor.tsv"
        operator = ["/code/writers/edit", "apply-context-step-prepared", case["v016_case"], role, str(step), staged, identity.sha256(descriptor)]
        records.append({**selected, "generator": {"argv": argv, "binary_sha256": writer["sha256"],
                                                 "source_binding": binding, "receipt": str(Path(made["stdout"]).resolve()),
                                                 "receipt_sha256": identity.sha256(made["stdout"])},
                        "descriptor": str(descriptor), "descriptor_sha256": identity.sha256(descriptor),
                        "payloads": context_descriptor(descriptor, case, selected), "staged_descriptor": staged,
                        "operator": "apply-context-step-prepared", "argv": operator,
                        "member_argv": [operator + [str(member)] for member in range(1, selected["members"] + 1)],
                        "prepared_run": f"context/{role}/steps/step-{step}.sh"})
    return records


def context_discard_required(case):
    topology = case.get("topology_schedule")
    if not topology:
        return False
    discard = topology.get("discard_reopen")
    concurrent = topology.get("topology") == "concurrent"
    if concurrent:
        if (len(topology["workers"]) != 2 or not isinstance(discard, dict)
                or type(discard.get("worker")) is not int or discard["worker"] != 0
                or type(discard.get("witness_bytes")) is not int or discard["witness_bytes"] != 256):
            raise ValueError("original two-worker discard witness declaration differs")
    elif discard is not None:
        raise ValueError("undeclared original contextual discard witness")
    return concurrent


def context_discard_descriptor(path, case):
    body = Path(path).read_bytes().decode("utf-8"); rows = body.splitlines()
    if len(rows) != 2 or rows[0] != "original-context-discard-witness-v1":
        raise ValueError("original contextual discard witness header differs")
    fields = rows[1].split("\t")
    if len(fields) != 4 or fields[:2] != [case["v016_case"], "0"]:
        raise ValueError("original contextual discard witness case/role differs")
    target, value = fields[2:]
    if (not target or any(part in ("", ".", "..") for part in target.split("/"))
            or any(char in target for char in "\0\\\r\n")
            or len(value) != 512 or any(char not in "0123456789abcdef" for char in value)
            or body != "\n".join(rows) + "\n"):
        raise ValueError("original contextual discard witness path/bytes differ")
    return {"case": case["v016_case"], "role": "0", "path": target, "hex": value,
            "bytes": 256, "payload_sha256": hashlib.sha256(bytes.fromhex(value)).hexdigest()}


def context_discard_receipt(summary, record):
    if (any(summary.get(key) != record[key] for key in ("case", "role", "path", "payload_sha256", "descriptor_sha256"))
            or type(summary.get("bytes")) is not int or summary["bytes"] != 256):
        raise ValueError("original contextual discard witness source receipt differs")


def prepare_context_discard(case, folder, build, binding):
    if not context_discard_required(case):
        return None
    output = folder / "context-discard"; writer = build["binaries"]["workspace-writer"]
    argv = [writer["path"], "prepare-context-discard", case["v016_case"], str(output)]
    made = receipts.command(argv, folder, "original-context-discard-witness", 120)
    descriptor = output / "witness.tsv"
    record = {**context_discard_descriptor(descriptor, case), "descriptor": str(descriptor),
              "descriptor_sha256": identity.sha256(descriptor), "staged_descriptor": "/code/context/discard-witness.tsv",
              "generator": {"argv": argv, "binary_sha256": writer["sha256"], "source_binding": binding,
                            "receipt": str(Path(made["stdout"]).resolve()), "receipt_sha256": identity.sha256(made["stdout"])}}
    context_discard_receipt(json.loads(Path(made["stdout"]).read_text()), record)
    return record


def validate_context_discard(case, prepared, build, binding, helper):
    record = prepared.get("original_discard_witness")
    if not context_discard_required(case):
        if record is not None:
            raise ValueError("undeclared original contextual discard witness asset")
        return set()
    if not isinstance(record, dict):
        raise ValueError("original two-worker discard witness asset required")
    descriptor = Path(record["descriptor"]); relative = "context/discard-witness.tsv"
    generator = record["generator"]; argv = generator["argv"]
    if (not descriptor.is_absolute() or descriptor.name != "witness.tsv"
            or record.get("staged_descriptor") != "/code/" + relative
            or argv[1:] != ["prepare-context-discard", case["v016_case"], str(descriptor.parent)]
            or generator.get("source_binding") != binding
            or generator.get("binary_sha256") != build["binaries"]["workspace-writer"]["sha256"]
            or identity.sha256(argv[0]) != generator["binary_sha256"]
            or identity.sha256(descriptor) != record["descriptor_sha256"]
            or identity.sha256(generator["receipt"]) != generator["receipt_sha256"]):
        raise ValueError("original contextual discard witness generator/source/staged binding differs")
    source = context_discard_descriptor(descriptor, case)
    if (any(record.get(key) != value for key, value in source.items())
            or context_discard_descriptor(helper(relative, record["descriptor_sha256"]), case) != source):
        raise ValueError("original contextual discard witness staged/source bytes differ")
    context_discard_receipt(json.loads(Path(generator["receipt"]).read_text()), record)
    return {relative}


def validate_context_helpers(case, prepared, build):
    plan = context_plan(case); binding = prepared.get("context_binding", {})
    if (prepared.get("schema") != CONTEXT_PREPARED_SCHEMA or prepared.get("case") != case["id"]
            or prepared.get("context_roles") != context_role_records(case, plan)
            or binding.get("case_definition_sha256") != plan["case_definition_sha256"]):
        raise ValueError("exact prepared contextual case/source/role binding required")
    for path in CONTEXT_SOURCE_FILES:
        if binding.get("model_files", {}).get(path) != identity.sha256(identity.ROOT / path):
            raise ValueError("prepared contextual model source changed")
    root = Path(prepared["helpers"]["root"]); seals = prepared["helpers"]["files"]
    def helper(relative, wanted):
        if seals.get(relative) != wanted or identity.sha256(root / relative) != wanted:
            raise ValueError("current contextual helper seal differs: " + relative)
        return root / relative
    binaries = {"writers/workload": "workload-linux", "writers/edit": "edit-linux", "writers/recipe": "workspace-linux"}
    for relative, binary in binaries.items():
        helper(relative, build["binaries"][binary]["sha256"])
    helper("workload.sh", identity.sha256(identity.ROOT / "benchmark/fs-bench-pro/families" / case["registry"]["family"] / "workload.sh"))
    initial = prepared.get("context_initial_recipe", {}); initial_argv = initial.get("argv", [])
    reuse = initial.get("input_reuse")
    initial_case, initial_role = case["v016_case"], plan["initial_role"]
    if reuse:
        cached = prepared_inputs.load_source(case, build)
        original = cached["fixture"]
        if (reuse["key"] != prepared_inputs.native_key(case, build)
                or reuse["producer_case"] != cached["producer_case"] or reuse["requested_case"] != case["id"]
                or reuse["requested_role"] != plan["initial_role"]
                or initial_argv != cached["generation"]["argv"]
                or reuse["manifest_sha256"] != identity.sha256(Path(cached["source"]).parent / "manifest.json")):
            raise ValueError("exact shared initial producer/current-case input binding required")
        initial_case, initial_role = original["case"], original["role"]
        qualification = initial["current_case_qualification"]
        if (qualification["exit_code"] != 0
                or qualification["argv"][1:6] != ["verify-context", case["v016_case"], plan["initial_role"], "0", cached["source"]]
                or identity.sha256(qualification["stdout"]) != initial["current_case_qualification_sha256"]):
            raise ValueError("current-case independent shared-input qualification changed")
        checked = [json.loads(line) for line in Path(qualification["stdout"]).read_text().splitlines()]
        if not checked or any(row.get("verification_status") != "pass" for row in checked):
            raise ValueError("current-case shared initial oracle did not pass")
    if (len(initial_argv) != 6 or initial_argv[1:5] != ["materialize-context", initial_case, initial_role, "0"]
            or initial.get("source_binding") != binding
            or initial.get("binary_sha256") != build["binaries"]["workspace-writer"]["sha256"]
            or identity.sha256(initial_argv[0]) != initial["binary_sha256"]
            or identity.sha256(initial["receipt"]) != initial["receipt_sha256"]):
        raise ValueError("exact pristine initial contextual fixture binding required")
    initial_summary = json.loads(Path(initial["receipt"]).read_text())
    initial_digest = identity.sha256(Path(initial_argv[-1]).with_suffix(".manifest.tsv"))
    if (initial_summary.get("case") != initial_case or initial_summary.get("role") != initial_role
            or type(initial_summary.get("step")) is not int or initial_summary["step"] != 0
            or type(initial_summary.get("seed")) is not int or initial_summary["seed"] != 1
            or initial_summary.get("manifest_sha256") != initial_digest
            or prepared.get("fixture", {}).get("fixture_digest") != initial_digest):
        raise ValueError("pristine contextual fixture source receipt differs")
    states = prepared.get("context_checkpoints", [])
    if (not isinstance(states, list) or any(not isinstance(s, dict) for s in states)
            or [{"role": s.get("role"), "index": s.get("index")} for s in states] != plan["checkpoints"]):
        raise ValueError("exact original contextual native checkpoints required")
    manifests = set()
    for state in states:
        role, step = state["role"], state["index"]; relative = f"context/{role}/manifests/state-{step}.tsv"
        if (state.get("staged_manifest") != "/code/" + relative
                or identity.sha256(state["manifest"]) != state["manifest_sha256"]
                or identity.sha256(state["native_manifest"]) != state["native_manifest_sha256"]
                or state["native_recipe"].get("source_binding") != binding
                or state["native_recipe"].get("binary_sha256") != build["binaries"]["workspace-writer"]["sha256"]
                or identity.sha256(state["native_recipe"]["receipt"]) != state["native_recipe"]["receipt_sha256"]):
            raise ValueError("contextual native/scoped/source/binary seals differ")
        native_argv = state["native_recipe"]["argv"]
        if (native_argv[1:] != ["materialize-context", case["v016_case"], role, str(step), state["native_root"]]
                or identity.sha256(native_argv[0]) != state["native_recipe"]["binary_sha256"]):
            raise ValueError("contextual native generator correspondence differs")
        summary = json.loads(Path(state["native_recipe"]["receipt"]).read_text())
        if (summary.get("case") != case["v016_case"] or summary.get("role") != role
                or type(summary.get("step")) is not int or summary["step"] != step
                or summary.get("manifest_sha256") != state["native_manifest_sha256"]
                or summary.get("context_manifest_sha256") != state["manifest_sha256"]
                or summary.get("recipe_sha256") != state.get("summary", {}).get("recipe_sha256")):
            raise ValueError("contextual native/scoped source receipt differs")
        helper(relative, state["manifest_sha256"]); manifests.add(relative)
    records, runs = prepared.get("sdk_context_steps", []), prepared.get("prepared_context_runs", {})
    if (not isinstance(records, list) or not isinstance(runs, dict) or any(not isinstance(item, dict) for item in records)
            or [{k: item.get(k) for k in ("role", "index", "members", "original_run")} for item in records] != plan["sdk_steps"]
            or set(runs) != set(plan["roles"])):
        raise ValueError("exact original contextual SDK role/step/member map required")
    payload_assets, scripts = set(), set()
    for role in plan["roles"]:
        if not isinstance(runs[role], dict) or set(runs[role]) != {str(item["index"]) for item in records if item["role"] == role}:
            raise ValueError("exact original contextual prepared run map required")
    for record in records:
        role, step = record["role"], record["index"]; relative = f"context/{role}/payloads/step-{step}/descriptor.tsv"
        staged = "/code/" + relative; run = f"context/{role}/steps/step-{step}.sh"
        descriptor = Path(record["descriptor"]); wanted = record["descriptor_sha256"]
        expected = ["/code/writers/edit", "apply-context-step-prepared", case["v016_case"], role, str(step), staged, wanted]
        generator = record["generator"]; source_argv = generator["argv"]
        if (record.get("prepared_run") != run or runs[role][str(step)] != run or record.get("staged_descriptor") != staged
                or record.get("operator") != "apply-context-step-prepared" or record.get("argv") != expected
                or record.get("member_argv") != [expected + [str(i)] for i in range(1, record["members"] + 1)]
                or not descriptor.is_absolute() or descriptor.name != "descriptor.tsv"
                or source_argv[1:] != ["prepare-context-step", case["v016_case"], role, str(step), str(descriptor.parent)]
                or generator.get("source_binding") != binding or generator.get("binary_sha256") != build["binaries"]["edit-host"]["sha256"]
                or identity.sha256(source_argv[0]) != generator["binary_sha256"] or identity.sha256(descriptor) != wanted
                or identity.sha256(generator["receipt"]) != generator["receipt_sha256"]):
            raise ValueError("original contextual SDK operator/generator/run binding differs")
        actual = helper(relative, wanted); payloads = context_descriptor(actual, case, record)
        summary = json.loads(Path(generator["receipt"]).read_text())
        if (summary.get("case") != case["v016_case"] or summary.get("role") != role
                or type(summary.get("step")) is not int or summary["step"] != step
                or type(summary.get("members")) is not int or summary["members"] != record["members"]
                or summary.get("descriptor_sha256") != wanted):
            raise ValueError("original contextual SDK source receipt differs")
        if payloads != record["payloads"] or payloads != context_descriptor(descriptor, case, record):
            raise ValueError("original contextual staged/source payload seals differ")
        payload_assets.add(relative)
        for name, seal in payloads.items():
            relative_payload = f"context/{role}/payloads/step-{step}/{name}"
            helper(relative_payload, seal["sha256"]); payload_assets.add(relative_payload)
        body = sdk_step_script(record); helper(run, hashlib.sha256(body.encode()).hexdigest()); scripts.add(run)
    discard_assets = validate_context_discard(case, prepared, build, binding, helper)
    wanted_assets = manifests | payload_assets | scripts | discard_assets | {"context/native-recipes.json", "context/payloads.json"}
    if {path for path in seals if path.startswith("context/")} != wanted_assets:
        raise ValueError("undeclared contextual payload/script/manifest helper asset")
    for path, field in (("context/native-recipes.json", "context_native_metadata"), ("context/payloads.json", "context_payload_metadata")):
        if json.loads(helper(path, seals[path]).read_text()) != prepared.get(field):
            raise ValueError("contextual helper metadata correspondence differs")
    return {"schema": "fs-bench-pro-context-helper-admission-v1", "status": "PASS",
            "context_roles": plan["roles"], "sdk_context_pairs": [[item["role"], item["index"]] for item in records],
            "scope": "exact original case/role/step/native/source/binary/descriptor/member/script seals; no mutation or regeneration"}


def prepare_context_workspace(family, case, folder, build_folder):
    """New closed contextual setup; ordinary sample cloning remains unchanged."""
    plan = context_plan(case)
    build, current = identity.load_build(build_folder), identity.source_identity()
    binding = context_source_binding(case, current)
    # An input made first by the ordinary writer is refused before this folder exists.
    prepared_inputs.require_context_producer(case, build)
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=False)
    fixture, expectation, native, checkpoints, initial_recipe = prepare_context_native(case, folder, build, binding)
    source = prepared_inputs.source_path(case, build)
    fixture.update(recipe=case["fixture"]["recipe"], fixture_sha256=fixture["fixture_digest"])
    sdk = prepare_context_payloads(case, folder, build, binding)
    discard = prepare_context_discard(case, folder, build, binding)
    helpers = assets(folder / "code"); code = Path(helpers["root"])
    copies = [(Path(build["binaries"][binary]["path"]), relative)
              for binary, relative in (("workload-linux", "writers/workload"), ("edit-linux", "writers/edit"),
                                       ("workspace-linux", "writers/recipe"))]
    copies.append((identity.ROOT / "benchmark/fs-bench-pro/families" / family["family"] / "workload.sh", "workload.sh"))
    for origin, relative in copies:
        destination = code / relative; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination); destination.chmod(0o555)
        helpers["files"][relative] = identity.sha256(destination)
    context = code / "context"; context.mkdir()
    if discard:
        shutil.copy2(discard["descriptor"], context / "discard-witness.tsv")
    for state in checkpoints:
        destination = code / state["staged_manifest"].removeprefix("/code/")
        destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(state["manifest"], destination)
    for record in sdk:
        destination = code / record["staged_descriptor"].removeprefix("/code/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record["descriptor"], destination)
        for name in record["payloads"]:
            shutil.copy2(Path(record["descriptor"]).parent / name, destination.parent / name)
        script = code / record["prepared_run"]; script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(sdk_step_script(record))
    roles = context_role_records(case, plan)
    native_metadata = {"schema": "fs-bench-pro-original-context-native-recipes-v1", "case": case["v016_case"],
                       "context_binding": binding, "initial_recipe": initial_recipe,
                       "context_roles": roles, "states": checkpoints, "performance_samples": 0,
                       "scope": "only declared contextual payload checkpoints; actual created modes are not preparation evidence"}
    payload_metadata = {"schema": "fs-bench-pro-original-context-sdk-payloads-v1", "case": case["v016_case"],
                        "context_binding": binding, "steps": sdk, "original_discard_witness": discard, "performance_samples": 0}
    receipts.write_new(context / "native-recipes.json", native_metadata)
    receipts.write_new(context / "payloads.json", payload_metadata)
    for path in sorted(context.rglob("*")):
        if path.is_file():
            path.chmod(0o444); helpers["files"][str(path.relative_to(code))] = identity.sha256(path)
    helpers["sha256"] = hashlib.sha256(json.dumps(helpers["files"], sort_keys=True).encode()).hexdigest()
    context_fields = {"schema": CONTEXT_PREPARED_SCHEMA, "case": case["id"], "fixture": fixture, "context_binding": binding,
                      "context_roles": roles, "context_initial_recipe": initial_recipe, "context_checkpoints": checkpoints,
                      "sdk_context_steps": sdk, "original_discard_witness": discard,
                      "context_native_metadata": native_metadata, "context_payload_metadata": payload_metadata,
                      "prepared_context_runs": {role: {str(record["index"]): record["prepared_run"]
                                               for record in sdk if record["role"] == role} for role in plan["roles"]}, "helpers": helpers}
    validate_context_helpers(case, context_fields, build)
    reused, reuse = compatible_master(folder, fixture, current, source.stat().st_uid, source.stat().st_gid)
    if reused is None:
        volume = "layerfs-fsb-master-" + family["family"].replace("_", "-") + "-" + uuid.uuid4().hex[:16]
        receipts.write_new(folder / "resource-claim.json", {"volume": volume, "created_by_this_run": True,
                           "purpose": "new immutable contextual preparation; never measure directly"})
        docker = ["docker", "--host", "unix://" + build["socket"]]
        made = receipts.command([*docker, "volume", "create", volume], folder, "master-volume", 15)
        if Path(made["stdout"]).read_text().strip() != volume:
            raise ValueError("original contextual master volume acknowledgement differs")
        provisioned = project.provision(source, volume, folder / "project", build)
    else:
        volume, provisioned = reused["master_volume"], reused["provision"]
        receipts.write_new(folder / "resource-claim.json", {"volume": volume, "created_by_this_run": False,
                           "purpose": "exact initial immutable master reused; independent sample byte copy only", "reuse": reuse})
    result = {**context_fields, "status": "PASS", "family": family["family"], "build": str(Path(build_folder).resolve()),
              "recipe": case["fixture"]["recipe"], "identity": current, "fixture": fixture, "expectation": expectation,
              "native_verification": native, "context_binding": binding, "context_roles": roles,
              "context_initial_recipe": initial_recipe, "context_checkpoints": checkpoints, "sdk_context_steps": sdk,
              "context_native_metadata": native_metadata, "context_payload_metadata": payload_metadata,
              "prepared_context_runs": {role: {str(record["index"]): record["prepared_run"]
                                       for record in sdk if record["role"] == role} for role in plan["roles"]},
              "helpers": helpers, "master_volume": volume, "provision": provisioned, "master_reuse": reuse,
              "source": str(source), "source_uid": source.stat().st_uid, "source_gid": source.stat().st_gid, "master_measurement_mounts": 0,
              "global_profile": "Disposable/WAL/OFF", "overlay_profile": "MEMORY/OFF/EXCLUSIVE", "construction_workers": 1,
              "setup": "full pristine initial native input independently verified; role-scoped original checkpoints/descriptors sealed; selected M1 metadata placeholders are not actual proof; one closed Init/master, independent sample byte clones",
              "cache": "setup/native materialization warmth explicit; cloning establishes no cold paid-phase claim"}
    seal_prepared(folder, result, build_folder)
    return result


def family_case(recipe):
    for path in sorted((identity.ROOT / "benchmark/fs-bench-pro/families").glob("*/family.json")):
        family = json.loads(path.read_text())
        for case in family["cases"]:
            if case["fixture"].get("recipe") == recipe and case["status"] == "ported":
                return family, case
    raise ValueError("no committed ported case defines fixture recipe " + recipe)


def generate(recipe, root):
    root = Path(root)
    if recipe not in ("empty", "big64m"):
        raise ValueError("fixture recipe is not registered: " + recipe)
    root.mkdir(mode=0o755, parents=True, exist_ok=False)
    content_sha = None
    if recipe == "big64m":
        value = hashlib.sha256()
        block = bytes(65536)
        with (root / "big").open("xb") as stream:
            for _ in range(BIG_BYTES // len(block)):
                if stream.write(block) != len(block):
                    raise OSError("short original fixture write; no resend")
                value.update(block)
        (root / "big").chmod(0o644)
        os.utime(root / "big", ns=(MTIME_NS, MTIME_NS))
        content_sha = value.hexdigest()
    root.chmod(0o755)
    os.utime(root, ns=(MTIME_NS, MTIME_NS))
    semantic = {"recipe": recipe, "seed": 1, "root_mode": 0o755, "mtime_ns": MTIME_NS,
                "uid": root.stat().st_uid, "gid": root.stat().st_gid,
                "files": 1 if recipe == "big64m" else 0,
                "logical_bytes": BIG_BYTES if recipe == "big64m" else 0,
                "content_sha256": content_sha, "profile": "complete native tree; full written bytes, no sparse substitute"}
    semantic["fixture_sha256"] = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
    return semantic


def assets(folder):
    """Copy committed helper bytes; only the seal is reused in sample setup."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    copies = [(identity.ROOT / "benchmark/fs-bench-pro/engine/oracle.py", "engine/oracle.py")]
    copies += [(identity.ROOT / "benchmark/cluster-two/cells" / name, "cells/" + name)
               for name in ("oracle.py", "git_index_oracle.py", "git_queries.py", "workloads.py")]
    copies += [(identity.ROOT / "benchmark/cluster-two/cache" / name, "cache/" + name)
               for name in ("residency.py", "stream_manifest.py", "generate_manifest.py")]
    copies += [(identity.ROOT / "benchmark/fs-bench-pro/engine/recipes/git-default-policy.json",
                "git-default-policy.json")]
    hashes = {}
    for source, relative in copies:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)
        path.chmod(0o444)
        hashes[relative] = identity.sha256(path)
    return {"root": str(folder), "files": hashes,
            "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def native_oracles(recipe, source, helpers, folder, build):
    """One independent native expected state per cell; no product or N/P arm."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    cells = [cell for cell, wanted in CELL_RECIPES.items() if wanted == recipe]
    token = uuid.uuid4().hex[:16]
    container = "layerfs-fsb-oracle-" + token
    docker = ["docker", "--host", "unix://" + build["socket"]]
    inside = "/tmp/layerfs-r7-fsb-oracle-" + token
    commands = ["set -eu", "mkdir -m 700 " + inside]
    for cell in cells:
        commands.append("python3 -B /code/engine/oracle.py prepare --case " + cell +
                        " --root /native-" + cell + " --output " + inside + "/" + cell +
                        " --helpers /code/cells --policy /code/git-default-policy.json")
    info = Path(source).stat()
    create = receipts.command([*docker, "create", "--name", container, "--network", "none",
                               "--user", f"{info.st_uid}:{info.st_gid}", "-e", "PYTHONDONTWRITEBYTECODE=1",
                               identity.IMAGE, "/bin/bash", "-c", "\n".join(commands)], folder, "native-create", 15)
    receipts.command([*docker, "cp", "--archive", helpers["root"] + "/.", container + ":/code"],
                     folder, "native-code", 15)
    for cell in cells:
        receipts.command([*docker, "cp", "--archive", str(source) + "/.", container + ":/native-" + cell],
                         folder, "native-input-" + cell, 15)
    authored = receipts.command([*docker, "start", "--attach", container], folder, "native-author", 120)
    destination = folder / "expected"
    receipts.command([*docker, "cp", container + ":" + inside, str(destination)], folder, "native-export", 15)
    expected = {}
    for cell in cells:
        path = destination / cell
        if not (path / "observation.json").is_file():
            raise ValueError("original native oracle missing: " + cell)
        record = json.loads((path / "observation.json").read_text())
        if record["case"] != cell:
            raise ValueError("original native oracle case differs")
        expected[cell] = {"path": str(path), "observation_sha256": identity.sha256(path / "observation.json"),
                          "tree_sha256": identity.sha256(path / "tree.jsonl")}
    receipts.command([*docker, "rm", container], folder, "native-remove-passing", 15)
    result = {"schema": "fs-bench-pro-native-oracles-v1", "status": "PASS", "recipe": recipe,
              "cases": expected, "container": container, "container_disposition": "completed native author, exported, removed",
              "create": create, "author": authored, "performance_samples": 0,
              "scope": "untimed independently generated native expectations; no product, N/P measurement or old /tmp inputs"}
    receipts.write_new(folder / "oracles.json", result)
    return result


def prepare(recipe, folder, build_folder):
    if recipe in NAMESPACE_RECIPES:
        return prepare_namespace(recipe, folder, build_folder)
    if recipe not in ("empty", "big64m"):
        family, case = family_case(recipe)
        if family["family"] in IMPORT_FAMILIES:
            return prepare_import(family, case, folder, build_folder)
        if family["family"]=="repository_history":
            return prepare_repository_history(family,case,folder,build_folder)
        if family["family"]=="store_footprint":
            return prepare_footprint(family,case,folder,build_folder)
        return prepare_workspace(recipe, folder, build_folder)
    build = identity.load_build(build_folder)
    current = identity.source_identity()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    fixture = generate(recipe, folder / "source")
    helpers = assets(folder / "code")
    volume = "layerfs-fsb-master-" + recipe + "-" + uuid.uuid4().hex[:16]
    docker = ["docker", "--host", "unix://" + build["socket"]]
    receipts.write_new(folder / "resource-claim.json", {"volume": volume, "purpose": "new immutable fixture master",
                       "failure_disposition": "retained; never reused as a mutated sample", "created_by_this_run": True})
    created = receipts.command([*docker, "volume", "create", volume], folder, "master-volume", 15)
    if Path(created["stdout"]).read_text().strip() != volume:
        raise ValueError("original master volume acknowledgement differs")
    provisioned = project.provision(folder / "source", volume, folder / "project", build)
    oracles = native_oracles(recipe, folder / "source", helpers, folder / "oracle", build)
    result = {"schema": "fs-bench-pro-prepared-fixture-v1", "status": "PASS", "recipe": recipe,
              "identity": current, "fixture": fixture, "helpers": helpers, "master_volume": volume,
              "provision": provisioned, "oracles": oracles, "build": str(Path(build_folder).resolve()),
              "source_uid": (folder / "source").stat().st_uid, "source_gid": (folder / "source").stat().st_gid,
              "global_profile": "Disposable/WAL/OFF", "overlay_profile": "MEMORY/OFF/EXCLUSIVE",
              "construction_workers": 1, "master_measurement_mounts": 0,
              "durable": "NOT_RUN — disabled by owner until explicit reauthorization"}
    seal_prepared(folder, result, build_folder)
    return result


def prepare_repository_history(family,case,folder,build_folder):
    """Authenticated immutable corpus transitions and an empty setup Store."""
    import time
    from .recipes import repository_history
    if family["family"]!="repository_history" or case["id"] not in repository_history.SELECTIONS:
        raise ValueError("one exact original repository-history selection required")
    build,current = identity.load_build(build_folder),identity.source_identity()
    folder = Path(folder).resolve(); folder.mkdir(parents=True,exist_ok=False)
    inputs = repository_history.authenticate_and_prepare(Path(case["fixture"]["source_corpus"]),case["v016_case"],
                                                        folder/"repository-inputs",time.monotonic()+120)
    source = folder/"source"
    empty_fixture = generate("empty",source)
    helpers = assets(folder/"code")
    for origin,relative in ((Path(build["binaries"]["workload-linux"]["path"]),"writers/workload"),
        (identity.ROOT/"benchmark/fs-bench-pro/families/repository_history/workload.sh","workload.sh")):
        target = Path(helpers["root"])/relative
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(origin,target); target.chmod(0o555)
        helpers["files"][relative] = identity.sha256(target)
    for state in inputs["states"]:
        index = state["index"]
        relative = f"repository/checkpoints/{index}"
        target = Path(helpers["root"])/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.mkdir()
        for name in state["input_seal"]["files"]:
            if name=="oracle.json":
                continue
            copied=target/name;copied.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(Path(state["input"])/name,copied)
        state["helper_input"],state["runtime_input"] = relative,f"/input/checkpoint-{index}"
        for name,digest in state["input_seal"]["files"].items():
            if name=="oracle.json":
                continue
            if identity.sha256(target/name)!=digest:
                raise ValueError("exact repository transition helper copy differs")
            helpers["files"][relative+"/"+name] = digest
        oracle_relative = f"repository/oracles/{index}.json"
        oracle = Path(helpers["root"])/oracle_relative
        oracle.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(state["oracle"],oracle)
        if identity.sha256(oracle)!=state["oracle_sha256"]:
            raise ValueError("original complete repository helper oracle copy differs")
        helpers["files"][oracle_relative] = state["oracle_sha256"]
        state["helper_oracle"] = oracle_relative
    helpers["sha256"] = hashlib.sha256(json.dumps(helpers["files"],sort_keys=True).encode()).hexdigest()
    volume = "layerfs-fsb-master-repository-history-"+uuid.uuid4().hex[:16]
    docker = ["docker","--host","unix://"+build["socket"]]
    receipts.write_new(folder/"resource-claim.json",{"volume":volume,"created_by_this_run":True,
        "purpose":"untimed immutable empty original repository input Store; complete selected history remains measured",
        "failure_disposition":"retain exact resources; no retry or existing volume mutation"})
    created = receipts.command([*docker,"volume","create",volume],folder,"master-volume",15)
    if Path(created["stdout"]).read_text().strip()!=volume:
        raise ValueError("original repository empty master acknowledgement differs")
    provision = project.provision(source,volume,folder/"project",build)
    fixture = {"recipe":case["fixture"]["recipe"],"fixture_sha256":inputs["input_identity"],
        "logical_bytes":0,"files":0,"repository_logical_bytes":sum(state["logical_bytes"] for state in inputs["states"]),
        "path_states":sum(state["full_entries"] for state in inputs["states"]),"states":inputs["state_count"],
        "initial_fixture":empty_fixture,"scope":"complete exact selected original repository transitions; empty initial Store has no imported historical state"}
    result = {"schema":"fs-bench-pro-prepared-repository-history-v1","status":"PASS","family":family["family"],
        "case":case["id"],"recipe":case["fixture"]["recipe"],"identity":current,"build":str(Path(build_folder).resolve()),
        "repository_inputs":inputs,"source":str(source),"source_uid":source.stat().st_uid,"source_gid":source.stat().st_gid,
        "fixture":fixture,"helpers":helpers,"master_volume":volume,"provision":provision,
        "setup_method":"exact source-only native transitions; one independent empty public Disposable Init/seal/install setup; never pre-Commit selected history",
        "global_profile":"Disposable/WAL/OFF","overlay_profile":"MEMORY/OFF/EXCLUSIVE","construction_workers":1,
        "cache":"immutable input authentication and cloning are setup reuse; all paid backing/metadata/SQLite/own-write coldness unqualified",
        "durable":"NOT_RUN — disabled by owner until explicit reauthorization"}
    seal_prepared(folder, result, build_folder)
    return result


def prepare_footprint(family,case,folder,build_folder):
    """Exact native control tree; the original Init remains a measured operation."""
    if (family["family"]!="store_footprint" or case.get("store_footprint_schedule",{}).get("schema")!="original-store-footprint-init-edit-v1"
            or case["fixture"].get("source_only_preparation") is not True):
        raise ValueError("original fresh Store-footprint import/edit declaration required")
    build,current = identity.load_build(build_folder),identity.source_identity()
    folder = Path(folder).resolve(); folder.mkdir(parents=True,exist_ok=False)
    source = prepared_inputs.source_path(case, build)
    shell = identity.ROOT/"benchmark/fs-bench-pro/families/store_footprint/workload.sh"
    env = {**os.environ,"WORKLOAD_WRITER":build["binaries"]["workload-host"]["path"]}
    fixture = prepared_inputs.make_initial(case, build,
        ["/bin/bash",str(shell),"fixture",case["v016_case"],str(source)],folder,environment=env)
    checked = receipts.command(["/bin/bash",str(shell),"verify-source",case["v016_case"],str(source)],
                               folder,"original-native-source-digest",120,environment=env)
    native = dict(line.split("=",1) for line in Path(checked["stdout"]).read_text().splitlines())
    if (fixture.get("schema")!="fs-bench-pro-store-footprint-fixture-v1" or fixture.get("control_id")!=case["v016_case"]
            or fixture.get("regular_files")!=case["fixture"]["regular_files"]
            or fixture.get("logical_bytes")!=case["fixture"]["logical_bytes"]
            or fixture.get("data_directories")+1!=case["fixture"]["directories_including_root"]
            or int(native["regular_files"])!=fixture["regular_files"] or int(native["logical_bytes"])!=fixture["logical_bytes"]
            or native["tree_digest"]!=fixture["fixture_digest"]):
        raise ValueError("original complete Store-footprint fixture/digest differs")
    fixture.update(recipe=case["fixture"]["recipe"],fixture_sha256=fixture["fixture_digest"])
    helpers = assets(folder/"code")
    for origin,relative in ((Path(build["binaries"]["workload-linux"]["path"]),"writers/workload"),(shell,"workload.sh")):
        target=Path(helpers["root"])/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(origin,target);target.chmod(0o555);helpers["files"][relative]=identity.sha256(target)
    helpers["sha256"]=hashlib.sha256(json.dumps(helpers["files"],sort_keys=True).encode()).hexdigest()
    result = {"schema":"fs-bench-pro-prepared-native-footprint-v1","status":"PASS","family":family["family"],"case":case["id"],
        "recipe":case["fixture"]["recipe"],"identity":current,"build":str(Path(build_folder).resolve()),"source":str(source),
        "source_uid":source.stat().st_uid,"source_gid":source.stat().st_gid,"fixture":fixture,"helpers":helpers,
        "original_verification":native,"generator_sha256":build["binaries"]["workload-host"]["sha256"],
        "master_volume":None,"setup_method":"fresh complete original native control, no Store/Init before measured operation",
        "cache":"setup generated/wrote/read every original source byte; all paid source/backing/metadata coldness unavailable",
        "global_profile":"Disposable/WAL/OFF selected by future measured Init; no setup Store", "construction_workers":1}
    seal_prepared(folder, result, build_folder)
    return result


def import_plan(family, case):
    """Only frozen fresh-directory imports may use native-only setup."""
    if family["family"] not in IMPORT_FAMILIES or family["engine"] != "project":
        raise ValueError("exact original directory-import family required")
    plan = case.get("import_schedule") or case.get("init_import")
    if not plan or plan.get("schema") not in ("original-dedup-directory-import-v1", "original-dedup-import-v1"):
        raise ValueError("original directory-import schedule required")
    if (case["status"] != "ported" or case["id"] != case["v016_case"]
            or case["fixture"]["seed"] != 1 or case["fixture"]["recipe"] != case["id"]
            or len(case["steps"]) != 1 or case["steps"][0].get("public_api") != "ProjectApi::init"
            or case["steps"][0].get("fresh_store") is not True
            or any(case["steps"][0].get(key) for key in ("commit", "mount", "run"))):
        raise ValueError("one original fresh Init, exact fixture and no measured mutation required")
    fixture = case["fixture"]
    files = fixture["regular_files"]
    directories = fixture.get("directories_including_root", fixture.get("directories"))
    entries = fixture.get("entries", fixture.get("paths"))
    if (any(type(n) is not int or n < 0 for n in (files, directories, entries, fixture["logical_bytes"]))
            or directories < 1 or entries != files + directories):
        raise ValueError("complete original import fixture census required")
    return {"files": files, "directories": directories, "entries": entries,
            "logical_bytes": fixture["logical_bytes"], "state": 0}


def prepare_import(family, case, folder, build_folder):
    """One original native source and independent qualification; no Store."""
    plan = import_plan(family, case)
    build, current = identity.load_build(build_folder), identity.source_identity()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    source = prepared_inputs.source_path(case, build)
    writer = build["binaries"]["workspace-writer"]["path"]
    fixture = prepared_inputs.make_initial(case, build,
        [writer, "fixture", case["v016_case"], str(source)], folder)
    checked = receipts.command([writer, "verify-step", case["v016_case"], "0", str(source)],
                               folder, "original-native-fixture-check", 120)
    native = json.loads(Path(checked["stdout"]).read_text())
    if any(fixture.get(key) != plan[key] for key in ("files", "logical_bytes")):
        raise ValueError("original import fixture census differs")
    if native.get("verification_status") != "pass":
        raise ValueError("complete original native source verifier did not pass")
    qualified = receipts.command([writer, "import-qualified", case["v016_case"], "0", str(source)],
                                 folder, "independent-source-transcripts", 120)
    qualification = json.loads(Path(qualified["stdout"]).read_text())
    validate_import_qualification(case, plan, qualification)
    fixture.update(recipe=case["fixture"]["recipe"], fixture_sha256=fixture["fixture_digest"])
    result = {"schema": "fs-bench-pro-prepared-native-import-v1", "status": "PASS",
              "family": family["family"], "case": case["id"], "recipe": case["fixture"]["recipe"],
              "source": str(source), "source_uid": source.stat().st_uid, "source_gid": source.stat().st_gid,
              "fixture": fixture, "identity": current, "build": str(Path(build_folder).resolve()),
              "generator_sha256": build["binaries"]["workspace-writer"]["sha256"],
              "original_verification": native, "source_qualification": qualification,
              "master_volume": None, "setup_method": "fresh exact native input; no prior Store or Init",
              "cache": "setup generated/wrote/read every original source byte; host coldness unavailable",
              "global_profile": "Disposable/WAL/OFF selected by future Init; no Store during preparation",
              "construction_workers": 1, "durable": "NOT_RUN — disabled by owner until explicit reauthorization"}
    seal_prepared(folder, result, build_folder)
    return result


def validate_import_qualification(case, plan, qualification):
    if (qualification.get("schema") != "fs-bench-pro-independent-dedup-input-v1"
            or qualification.get("status") != "PASS" or qualification.get("case") != case["v016_case"]
            or qualification.get("step") != 0
            or qualification.get("regular_files") != plan["files"]
            or qualification.get("logical_bytes") != plan["logical_bytes"]
            or len(qualification.get("transcript_sha256", "")) != 64
            or len(qualification.get("transcripts", {})) != plan["files"]):
        raise ValueError("complete independent frozen input qualification required")
    digest = hashlib.sha256()
    total = 0
    for path, chunks in sorted(qualification["transcripts"].items()):
        if (not path or path.startswith("/") or any(part in ("", ".", "..") for part in path.split("/"))
                or any(char in path for char in "\x00\r\n") or not isinstance(chunks, list)):
            raise ValueError("canonical complete independent transcript path required")
        digest.update(path.encode()+b"\x00")
        offset = 0
        for chunk in chunks:
            if (set(chunk)!={"logical_start","len","raw_sha256"} or type(chunk["logical_start"]) is not int
                    or type(chunk["len"]) is not int or chunk["logical_start"]!=offset or not 0<chunk["len"]<=32768
                    or not isinstance(chunk["raw_sha256"],str) or len(chunk["raw_sha256"])!=64
                    or any(char not in "0123456789abcdef" for char in chunk["raw_sha256"])):
                raise ValueError("exact contiguous frozen bounded chunk transcript required")
            digest.update(offset.to_bytes(8,"little")); digest.update(chunk["len"].to_bytes(8,"little"))
            digest.update(chunk["raw_sha256"].encode()); offset += chunk["len"]
        total += offset
    if total!=plan["logical_bytes"] or digest.hexdigest()!=qualification["transcript_sha256"]:
        raise ValueError("original transcript bytes/digest binding differs")
    return qualification


def prepare_namespace(recipe, folder, build_folder):
    build = identity.load_build(build_folder)
    current = identity.source_identity()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    _, case = family_case(recipe)
    source = prepared_inputs.source_path(case, build)
    shell = identity.ROOT / "benchmark/fs-bench-pro/families/init_namespace/workload.sh"
    fixture = prepared_inputs.make_initial(case, build,
        ["/bin/bash", str(shell), recipe, str(source)], folder,
        environment={**os.environ, "NAMESPACE_WRITER": build["binaries"]["namespace-writer"]["path"]})
    verified = receipts.command([build["binaries"]["workload-host"]["path"], "namespace-verify", str(source), recipe],
                                folder, "original-native-fixture-verifier", 120)
    fields = dict(line.split("=", 1) for line in Path(verified["stdout"]).read_text().splitlines())
    if (int(fields["regular_files"]), int(fields["logical_bytes"]), fields["namespace_digest"]) != (
            fixture["files"], fixture["logical_bytes"], fixture["fixture_digest"]):
        raise ValueError("original fixture count/byte/content digest differs from transcription")
    fixture.update(recipe=recipe, fixture_sha256=fixture["fixture_digest"])
    result = {"schema": "fs-bench-pro-prepared-native-init-v1", "status": "PASS", "recipe": recipe,
              "source": str(source), "fixture": fixture, "identity": current,
              "generator_sha256": build["binaries"]["namespace-writer"]["sha256"],
              "original_verifier_sha256": build["binaries"]["workload-host"]["sha256"],
              "master_volume": None, "setup_method": "fresh native input; no prior Store or Init",
              "original_verification": fields,
              "cache": "setup generated/wrote/read all native bytes; source warmth retained; no cold admission claimed",
              "global_profile": "Disposable/WAL/OFF selected by the future Init; no Store executed during preparation"}
    seal_prepared(folder, result, build_folder)
    return result


def compatible_master(folder, fixture, current, uid, gid):
    """Reuse only a sealed setup with the identical complete input tree."""
    folder = Path(folder)
    candidates = set(folder.parent.glob("*/prepared.json"))
    # Producer-key directories contain case views, rather than sibling views.
    # Search only this worktree's declared kept cache, never other campaigns.
    cache = next((parent for parent in folder.parents if parent.name == "kept-fixtures"), None)
    if cache is not None:
        candidates.update(cache.glob("*/*/prepared.json"))
        candidates.update(cache.glob("*/*/genesis/prepared.json"))
    for candidate in sorted(candidates):
        if candidate.parent == Path(folder):
            continue
        summary = json.loads(candidate.read_text())
        if (summary.get("schema") not in ("fs-bench-pro-prepared-workspace-v1", CONTEXT_PREPARED_SCHEMA)
                or summary.get("status") != "PASS"
                or summary.get("global_profile") != "Disposable/WAL/OFF"
                or summary.get("store_builder_key") != prepared_inputs.product_store_key(current)
                or (summary.get("source_uid"), summary.get("source_gid")) != (uid, gid)
                or summary.get("fixture", {}).get("fixture_sha256") != fixture["fixture_sha256"]):
            continue
        prepared = load(candidate.parent)
        return prepared, {"prepared": str(candidate.parent.resolve()),
                          "prepared_manifest_sha256": identity.sha256(candidate.parent / "manifest.json"),
                          "master_volume": prepared["master_volume"],
                          "store_sha256": prepared["provision"]["store_sha256"],
                          "input_fixture_sha256": fixture["fixture_sha256"],
                          "scope": "closed immutable setup only; case-specific expected tree/helpers remain new; independent sample byte copy; no cold claim"}
    return None, None


def prepare_ordered_fixture(case, folder, build):
    """Frozen native history builder, independent complete SHA manifests per state."""
    import importlib.util
    path = identity.ROOT / case["fixture"]["history_recipe"]
    if identity.sha256(path) != case["port_review"]["files"][case["fixture"]["history_recipe"]]:
        raise ValueError("original native history recipe changed")
    spec = importlib.util.spec_from_file_location("frozen_history_fixture", path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    built = original.build(folder / "original")[case["v016_case"]]
    states = list(original.states())
    if len(states) != len(case["history_schedule"]["states"]):
        raise ValueError("original retained-state cardinality differs")
    source = folder / "source"
    shutil.copytree(Path(built["input"]) / "initial", source, copy_function=shutil.copy2)
    native, history = {}, []
    manifests = folder / "history-manifests"
    manifests.mkdir()
    expected = folder / "expected-native"
    for step, files in enumerate(states):
        seal = case["history_schedule"]["states"][step]
        oracle = Path(built["input"]) / f"oracle-{step}.json"
        if json.loads(oracle.read_text()) != original.oracle(files) or identity.sha256(oracle) != seal["original_oracle_sha256"]:
            raise ValueError("independent original history oracle differs")
        body = "workspace-independent-manifest-v1\n.\tdirectory\t0\t755\t1000000000\t0\t-\n"
        for name, data in sorted(files.items()):
            body += f"{name}\tfile\t{len(data)}\t644\t1000000000\t0\t{hashlib.sha256(data).hexdigest()}\n"
        manifest = manifests / f"state-{step}.tsv"
        manifest.write_text(body)
        if identity.sha256(manifest) != seal["manifest_sha256"]:
            raise ValueError("frozen independent state manifest differs")
        if step == 0:
            root = source
        else:
            root = expected if step == len(states)-1 else folder / "native-states" / f"state-{step}"
            root.mkdir(parents=True)
            for name, data in files.items():
                item = root / name
                item.write_bytes(data)
                item.chmod(0o644)
                os.utime(item, ns=(1_000_000_000_000_000_000,) * 2)
            root.chmod(0o755)
            os.utime(root, ns=(1_000_000_000_000_000_000,) * 2)
        proof = receipts.command([build["binaries"]["edit-host"]["path"], "verify-manifest", str(manifest)],
                                 folder, f"original-state-{step}-check", 120, cwd=root)
        checked = dict(line.split("=", 1) for line in Path(proof["stdout"]).read_text().splitlines())
        if checked.get("verification_status") != "pass":
            raise ValueError("original complete native history verification failed")
        native[f"state-{step}"] = checked
        history.append({"index": step, "manifest": str(manifest), "manifest_sha256": identity.sha256(manifest),
                        "original_oracle_sha256": identity.sha256(oracle), "logical_bytes": sum(map(len, files.values()))})
    def summary(step):
        return {"case": case["id"], "files": len(states[step]), "entries": len(states[step])+1,
                "logical_bytes": history[step]["logical_bytes"], "fixture_digest": history[step]["manifest_sha256"],
                "recipe_identity": history[step]["original_oracle_sha256"], "seed": 1}
    return summary(0), summary(len(states)-1), native, history, built


def snapshot_manifest(step):
    """Independent transcription of the frozen25k/97*j/one-byte equations."""
    if step not in range(4):
        raise ValueError("original local snapshot states are0..3")
    body = "workspace-independent-manifest-v1\n.\tdirectory\t0\t755\t1700000000\t0\t-\n"
    if step:
        edited = {97*j for j in range(256)} if step == 2 else set()
        for ordinal in range(25000):
            byte = (ordinal + (ordinal in edited)) % 251
            body += f"f{ordinal:05}\tfile\t1\t644\t1700000000\t0\t{hashlib.sha256(bytes([byte])).hexdigest()}\n"
    return body


def prepare_snapshot_fixture(case, folder, build):
    """Existing frozen Rust generator plus independent equations/native all-state proof."""
    if case["v016_case"] != "local-snapshot-create-25000-onebyte-v1":
        raise ValueError("original local snapshot case required")
    source, final = prepared_inputs.source_path(case, build), folder / "expected-native"
    fixture = prepared_inputs.make_initial(case, build,
        [build["binaries"]["workspace-writer"]["path"], "fixture", case["id"], str(source)], folder)
    state1 = folder / "native-states" / "state-1"
    state1.parent.mkdir()
    made = receipts.command([build["binaries"]["workspace-writer"]["path"], "expected", case["id"], str(state1)],
                            folder, "native-state-1", 120)
    expectation = json.loads(Path(made["stdout"]).read_text())
    if source.with_suffix(".manifest.tsv").read_text() != snapshot_manifest(0) or state1.with_suffix(".manifest.tsv").read_text() != snapshot_manifest(1):
        raise ValueError("independent snapshot equations differ from original Rust fixture/state")
    state2 = folder / "native-states" / "state-2"
    shutil.copytree(state1, state2, copy_function=shutil.copy2)
    for ordinal in (97*j for j in range(256)):
        path = state2 / f"f{ordinal:05}"
        path.write_bytes(bytes([(ordinal+1) % 251]))
        os.utime(path, ns=(MTIME_NS, MTIME_NS))
    os.utime(state2, ns=(MTIME_NS, MTIME_NS))
    shutil.copytree(state1, final, copy_function=shutil.copy2)
    manifests = folder / "history-manifests"
    manifests.mkdir()
    history, native = [], {}
    for step, root in enumerate((source, state1, state2, final)):
        body = snapshot_manifest(step)
        wanted = case["history_schedule"]["states"][step]["manifest_sha256"]
        if hashlib.sha256(body.encode()).hexdigest() != wanted:
            raise ValueError("original snapshot state registration changed")
        manifest = manifests / f"state-{step}.tsv"
        manifest.write_text(body)
        checked = receipts.command([build["binaries"]["workload-host"]["path"], "workspace-verify-tree", case["id"], "1", str(step)],
                                   folder, f"original-state-{step}-check", 120, cwd=root)
        native[f"state-{step}"] = dict(line.split("=", 1) for line in Path(checked["stdout"]).read_text().splitlines())
        history.append({"index": step, "manifest": str(manifest), "manifest_sha256": wanted, "logical_bytes": 25000 if step else 0})
    return fixture, expectation, native, history, None


def history_verification_steps(case):
    """Select only declared proof checkpoints; transcript census is separate."""
    schedule = case["history_schedule"]
    steps, count = schedule.get("verification_steps"), schedule.get("commits")
    if (schedule.get("schema") not in RECIPE_HISTORY_SCHEMAS
            or type(count) is not int or count < 1
            or not isinstance(steps, list) or not steps
            or any(type(step) is not int or not 0 <= step <= count for step in steps)
            or steps != sorted(set(steps)) or steps[-1] != count):
        raise ValueError("original history verification checkpoint selection differs")
    if schedule["schema"] == "original-v016-boundary-sequence-v1" and steps != list(range(count + 1)):
        raise ValueError("original boundary requires every retained state")
    if schedule["schema"] == "original-dedup-history-sequence-v1" and steps[0] != 0:
        raise ValueError("original dedup requires its declared initial checkpoint")
    if schedule["schema"] == "original-m1-commit-sequence-v1" and any(step == 0 or step % 5 for step in steps):
        raise ValueError("original M1 proof selects only declared cycle-end roots")
    return steps


def prepare_recipe_history(case, folder, build):
    """Independent original native recipes at selected states, never all K+1."""
    steps = history_verification_steps(case)
    writer = build["binaries"]["workspace-writer"]
    source, final = prepared_inputs.source_path(case, build), folder / "expected-native"
    fixture = prepared_inputs.make_initial(case, build,
        [writer["path"], "fixture", case["v016_case"], str(source)], folder)
    manifests = folder / "history-manifests"
    manifests.mkdir()
    native, history, expectation = {}, [], None
    def check(root, step):
        checked = receipts.command([writer["path"], "verify-step", case["v016_case"], str(step), str(root)],
                                   folder, f"original-state-{step}-check", 120)
        record = json.loads(Path(checked["stdout"]).read_text())
        if record.get("verification_status") != "pass" or record.get("case") != case["v016_case"]:
            raise ValueError("independent original native history verification failed")
        native[f"state-{step}"] = record
    # Initial-tree qualification is untimed setup, not an extra M1 selected
    # retained-root payload proof. The actual transcript still binds genesis.
    check(source, 0)
    if case.get("automatic_parent_mtime"):
        native["automatic-parent-mtime"] = qualify_alias_parent(case, folder, build)
    for step in steps:
        if step == 0:
            root, summary = source, fixture
            argv = [writer["path"], "fixture", case["v016_case"], str(source)]
        else:
            root = final if step == case["history_schedule"]["commits"] else folder / "native-states" / f"state-{step}"
            root.parent.mkdir(parents=True, exist_ok=True)
            if case.get("m1_schedule") and (root.exists() or root.is_symlink()):
                raise FileExistsError("original M1 checkpoint output must be fresh")
            argv = [writer["path"], "expected-step", case["v016_case"], str(step), str(root)]
            authored = receipts.command(argv, folder, f"native-state-{step}", 120)
            summary = json.loads(Path(authored["stdout"]).read_text())
            if summary.get("step") != step:
                raise ValueError("original native expected-state index differs")
            if not case.get("m1_schedule"):
                check(root, step)
        original = root.with_suffix(".manifest.tsv")
        digest = identity.sha256(original)
        if (summary.get("case") != case["v016_case"] or summary.get("seed") != 1
                or summary.get("fixture_digest") != digest):
            raise ValueError("independent original history manifest identity differs")
        manifest = manifests / f"state-{step}.tsv"
        scope_recipe = None
        if case.get("m1_schedule"):
            scope_writer = build["binaries"]["edit-host"]
            scope_argv = [scope_writer["path"], "m1-scope", case["v016_case"], str(step)]
            scoped = receipts.command(scope_argv, folder, f"native-scope-{step}", 120)
            scope = Path(scoped["stdout"])
            if scope.read_text().splitlines()[0] != "original-m1-selective-scope-v1":
                raise ValueError("original M1 selective scope header differs")
            shutil.copy2(scope, manifest)
            scope_recipe = {"binary_sha256": scope_writer["sha256"], "argv": scope_argv,
                            "observations": "None; actual created modes are measured helper evidence"}
        else:
            shutil.copy2(original, manifest)
        manifest_digest = identity.sha256(manifest)
        record = {"index": step, "manifest": str(manifest), "manifest_sha256": digest,
                  "staged_manifest": f"/code/history/manifests/state-{step}.tsv",
                  "native_root": str(root), "summary": summary,
                  "native_manifest": str(original), "native_manifest_sha256": digest,
                  "logical_bytes": summary["logical_bytes"], "native_recipe": {
                      "binary_sha256": writer["sha256"], "argv": argv,
                      "source": "original frozen definition plus product-neutral committed expected-state adapter"},
                  "scope_recipe": scope_recipe,
                  "verification_scope": "original-m1-selective-scope-v1" if case.get("m1_schedule") else "complete-original-native-state",
                  "materialization_metadata": "None created-mode observations; actual proof requires measured helper modes" if case.get("m1_schedule") else "original declared metadata"}
        record["manifest_sha256"] = manifest_digest
        history.append(record)
        if step == case["history_schedule"]["commits"]:
            expectation = summary
        if case.get("m1_schedule"):
            # The full manifest and selective scope above retain this expectation.
            # Actual byte/mode proofs read measured Workspace and Store roots.
            if root.is_symlink() or not root.is_dir():
                raise ValueError("original M1 checkpoint must be its owned generated directory")
            shutil.rmtree(root)
            record["materialization_metadata"] += "; generated payload removed after manifest/scope authoring; recorded native_root is its former path"
    if expectation is None:
        raise ValueError("original selected final expected-state absent")
    receipts.write_new(folder / "history-native-recipes.json", {
        "schema": "fs-bench-pro-original-history-native-recipes-v1", "case": case["v016_case"],
        "verification_steps": steps, "states": history, "initial_tree_verified": True,
        "performance_samples": 0,
        "scope": "only declared native checkpoints; M1 materialization is not actual created-mode or automatic-metadata proof; every acknowledgement is checked separately"})
    return fixture, expectation, native, history, None


def qualify_alias_parent(case, folder, build):
    """Replay the unchanged helper on one independent native tree, then remove it.

    The algebraic manifests remain deterministic. Native replay qualifies only
    the automatic-field rule; its timestamp never predicts the measured run.
    """
    if case["v016_case"] != "v016-boundary-alias-roundtrip-v1":
        raise ValueError("automatic parent mtime is only the original alias case")
    workload, edit, fixture = (build["binaries"][key] for key in
                              ("workload-host", "edit-host", "workspace-writer"))
    with tempfile.TemporaryDirectory(prefix="alias-native-replay-", dir=folder) as temporary:
        root = Path(temporary) / "tree"
        receipts.command([fixture["path"], "fixture", case["v016_case"], str(root)],
                         folder, "alias-native-replay-fixture", 15)
        for step in range(1, 5):
            receipts.command([workload["path"], "v016-boundary-alias", "1", str(step)],
                             folder, f"alias-native-replay-step-{step}", 15, cwd=root)
            receipts.command([edit["path"], "verify", case["v016_case"], str(step)],
                             folder, f"alias-native-replay-verify-{step}", 15, cwd=root)
        applied = receipts.command([edit["path"], "apply-boundary-alias", "5", workload["path"]],
                                   folder, "alias-native-replay-step-5", 15, cwd=root)
        text = Path(applied["stdout"]).read_text()
        marker = "original-boundary-parent-mtime-v1\n"
        if text.count(marker) != 1:
            raise ValueError("independent native alias custody missing or duplicate")
        body = marker + text.split(marker, 1)[1]
        custody = folder / "alias-native-parent-mtime.tsv"
        with custody.open("x") as output:
            output.write(body)
        checked = receipts.command([edit["path"], "verify", case["v016_case"], "5", str(custody)],
                                   folder, "alias-native-replay-verify-5", 15, cwd=root)
        proof = dict(line.split("=", 1) for line in Path(checked["stdout"]).read_text().splitlines())
        if proof.get("verification_status") != "pass" or proof.get("parent_mtime_custody_sha256") != identity.sha256(custody):
            raise ValueError("independent native alias automatic timestamp qualification refused")
    return {**proof, "custody": str(custody), "custody_sha256": identity.sha256(custody),
            "helper_stdout_sha256": identity.sha256(applied["stdout"]),
            "qualification_stdout_sha256": identity.sha256(checked["stdout"]),
            "helper_sha256": workload["sha256"], "observer_sha256": edit["sha256"],
            "scope": "unchanged native helper once per step; only state5 data mtime is automatic; exact other metadata, bytes and link classes; replay tree removed"}


def sdk_step_indices(case):
    """Original declared P-3 steps; never infer them from prepared records."""
    if not case.get("ordinary_sdk_edits") or case.get("history_schedule", {}).get("schema") not in RECIPE_HISTORY_SCHEMAS:
        return []
    count = case["history_schedule"]["commits"]
    if type(count) is not int or count < 1 or len(case["steps"]) != count:
        raise ValueError("original ordered SDK operation schedule differs")
    selected = list(range(1, count + 1))
    if case.get("m1_schedule") or case.get("registry", {}).get("kind") == "namespace-inode":
        selected = [step for step in selected if step % 5 == 2]
    return selected


def sdk_step_script(record):
    parts = shlex.split(record["original_run"])
    if not parts or Path(parts[0]).is_absolute() or ".." in Path(parts[0]).parts:
        raise ValueError("original staged workload path differs")
    body = "#!/bin/bash\nset -euo pipefail\n"
    body += "export SDK_STEP_DESCRIPTOR=" + shlex.quote(record["staged_descriptor"]) + "\n"
    body += "export SDK_STEP_DESCRIPTOR_SHA256=" + shlex.quote(record["descriptor_sha256"]) + "\n"
    return body + "exec /bin/bash " + shlex.join(["/code/" + parts[0], *parts[1:]]) + "\n"


def validate_runtime_helpers(case, prepared, build):
    if case.get("historical_access"):
        return validate_historical_helpers(case, prepared, build)
    """Fail before claims/clones if original P-3 placement or helper seals differ."""
    if case.get("branch_schedule") or case.get("topology_schedule"):
        return validate_context_helpers(case, prepared, build)
    if case.get("reuse_schedule"):
        if (case["reuse_schedule"].get("schema")!="original-dedup-workspace-reuse-v1"
                or prepared.get("family")!="dedup_workspace_reuse" or prepared.get("case")!=case["id"]
                or prepared.get("generator_sha256")!=build["binaries"]["workspace-writer"]["sha256"]
                or prepared.get("sdk_steps") or prepared.get("history_states") is not None):
            raise ValueError("exact original single ordinary reuse preparation required")
        for step,key in ((0,"initial"),(1,"final")):
            q = prepared.get("independent_dedup_inputs",{}).get(key,{})
            if (q.get("schema")!="fs-bench-pro-independent-dedup-input-v1" or q.get("status")!="PASS"
                    or q.get("case")!=case["v016_case"] or q.get("step")!=step
                    or q.get("regular_files")!=(case["fixture"]["files"] if step==0 else case["reuse_schedule"]["final_files"])
                    or q.get("logical_bytes")!=(case["fixture"]["logical_bytes"] if step==0 else case["reuse_schedule"]["final_logical_bytes"])
                    or q.get("receipt",{}).get("dedup_transcript_status")!="pass"):
                raise ValueError("complete independent pristine/final reuse source contracts required")
        for path,wanted in (("writers/workload",build["binaries"]["workload-linux"]["sha256"]),
                            ("workload.sh",identity.sha256(identity.ROOT/"benchmark/fs-bench-pro/families/dedup_workspace_reuse/workload.sh"))):
            if (prepared["helpers"]["files"].get(path)!=wanted
                    or identity.sha256(Path(prepared["helpers"]["root"])/path)!=wanted):
                raise ValueError("original ordinary reuse runtime helper differs")
        return {"status":"PASS","scope":"exact initial/final native CDC/reuse contracts; unchanged single original ordinary helper and case; no SDK edits or history checkpoints"}
    history = case.get("history_schedule", {}).get("schema") in RECIPE_HISTORY_SCHEMAS
    if not history and case.get("registry", {}).get("family") != "mixed_load_bearing":
        return {"status": "NOT_APPLICABLE", "scope": "existing non-batch4 helper admission unchanged"}
    root = Path(prepared["helpers"]["root"])
    seals = prepared["helpers"]["files"]
    def digest(value):
        return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)
    def helper(path, wanted):
        if not digest(wanted) or seals.get(path) != wanted or identity.sha256(root / path) != wanted:
            raise ValueError("current runtime helper seal differs: " + path)
        return root / path
    bindings = {"writers/workload": build["binaries"]["workload-linux"]["sha256"]}
    if history:
        bindings["writers/edit"] = build["binaries"]["edit-linux"]["sha256"]
    if case.get("m1_schedule"):
        bindings["writers/recipe"] = build["binaries"]["workspace-linux"]["sha256"]
    for path, wanted in bindings.items():
        helper(path, wanted)
    indices = sdk_step_indices(case)
    records, runs = prepared.get("sdk_steps", []), prepared.get("prepared_step_runs", {})
    if (not isinstance(records, list) or not isinstance(runs, dict)
            or any(not isinstance(record, dict) or type(record.get("index")) is not int for record in records)
            or [record["index"] for record in records] != indices
            or set(runs) != {str(index) for index in indices}):
        raise ValueError("exact original prepared SDK step indices required; native fallback forbidden")
    assets, scripts = set(), set()
    for record in records:
        index = record["index"]
        relative = f"history/payloads/step-{index}/descriptor.tsv"
        staged = "/code/" + relative
        run = f"history/steps/step-{index}.sh"
        wanted = record.get("descriptor_sha256")
        original_run = case["steps"][index-1]["run"]
        argv = ["/code/writers/edit", "apply-sdk-step-prepared", case["v016_case"], str(index), staged, wanted]
        descriptor = Path(record.get("descriptor", ""))
        generator = record.get("generator", {})
        source_argv = generator.get("argv", [])
        if (record.get("original_run") != original_run or record.get("prepared_run") != run
                or runs[str(index)] != run or record.get("staged_descriptor") != staged
                or record.get("operator") != "apply-sdk-step-prepared" or record.get("argv") != argv
                or not descriptor.is_absolute() or descriptor.name != "descriptor.tsv"
                or len(source_argv) != 5 or source_argv[1:] != ["prepare-sdk-step", case["v016_case"], str(index), str(descriptor.parent)]
                or generator.get("binary_sha256") != build["binaries"]["edit-host"]["sha256"]
                or identity.sha256(source_argv[0]) != generator.get("binary_sha256")):
            raise ValueError("original prepared SDK operator/generator/run binding differs")
        staged_file = helper(relative, wanted)
        if identity.sha256(descriptor) != wanted:
            raise ValueError("original prepared SDK descriptor source seal differs")
        rows = staged_file.read_text().splitlines()
        payloads = record.get("payloads", {})
        if not isinstance(payloads, dict):
            raise ValueError("original prepared SDK payload records required")
        count = len(payloads)
        if (not count or len(rows) != count+4
                or rows[:4] != ["original-sdk-step-payloads-v1", "case\t"+case["v016_case"], f"step\t{index}", f"members\t{count}"]
                or record.get("member_argv") != [argv+[str(member)] for member in range(1,count+1)]
                or set(payloads) != {f"member-{member}.bin" for member in range(1,count+1)}):
            raise ValueError("original prepared SDK descriptor/member cardinality differs")
        assets.add(relative); scripts.add(run)
        for member, row in enumerate(rows[4:], 1):
            fields, name = row.split("\t"), f"member-{member}.bin"
            if len(fields) != 12 or fields[0] != str(member) or fields[11] != name:
                raise ValueError("original prepared SDK member path/order differs")
            path = fields[1]
            if (not path or any(part in ("", ".", "..") for part in path.split("/"))
                    or any(char in path for char in "\0\\\t\r\n")):
                raise ValueError("unsafe original prepared SDK target")
            values = [int(value) for value in fields[2:7]]
            start, deleted, before, after, size = values
            mode, seconds, nanos = int(fields[8],8), int(fields[9]), int(fields[10])
            payload = payloads[name]
            relative_payload = f"history/payloads/step-{index}/{name}"
            actual = helper(relative_payload, fields[7])
            if (any(value < 0 or value > 2**64-1 for value in values)
                    or start+deleted > before or before-deleted+size != after
                    or mode < 0 or mode & ~0o7777 or not -(2**63) <= seconds < 2**63 or not 0 <= nanos < 1_000_000_000
                    or payload != {"sha256":fields[7],"bytes":size} or actual.stat().st_size != size
                    or identity.sha256(descriptor.parent / name) != fields[7]):
                raise ValueError("original prepared SDK payload/geometry/metadata differs")
            assets.add(relative_payload)
        script_path = helper(run, hashlib.sha256(sdk_step_script(record).encode()).hexdigest())
        if script_path.read_text() != sdk_step_script(record):
            raise ValueError("original prepared SDK script correspondence differs")
    if ({path for path in seals if path.startswith("history/payloads/")} != assets
            or {path for path in seals if path.startswith("history/steps/")} != scripts):
        raise ValueError("undeclared SDK payload or script helper asset")
    return {"schema":"fs-bench-pro-runtime-helper-admission-v1", "status":"PASS",
            "sdk_step_indices":indices, "helper_binary_seals":bindings,
            "scope":"original untimed generator and prepared operator/member/source seals; native fallback only on original non-SDK steps; no mutation or regeneration"}


def prepare_sdk_payloads(case, folder, build):
    """Original generators run outside measurement; operators read sealed bytes."""
    selected = sdk_step_indices(case)
    if not selected:
        return []
    writer = build["binaries"]["edit-host"]
    base = folder / "sdk-payloads"
    base.mkdir()
    records = []
    for step in selected:
        output = base / f"step-{step}"
        argv = [writer["path"], "prepare-sdk-step", case["v016_case"], str(step), str(output)]
        made = receipts.command(argv, folder, f"original-sdk-payloads-{step}", 120)
        summary = json.loads(Path(made["stdout"]).read_text())
        descriptor = output / "descriptor.tsv"
        digest = identity.sha256(descriptor)
        if (summary.get("case") != case["v016_case"] or summary.get("step") != step
                or summary.get("descriptor_sha256") != digest):
            raise ValueError("untimed original SDK descriptor identity differs")
        rows = descriptor.read_text().splitlines()
        if (len(rows) < 4 or rows[:3] != ["original-sdk-step-payloads-v1", "case\t" + case["v016_case"], f"step\t{step}"]
                or rows[3] != f"members\t{summary['members']}" or len(rows[4:]) != summary["members"]):
            raise ValueError("untimed original SDK descriptor cardinality differs")
        payloads = {}
        for index, row in enumerate(rows[4:], 1):
            fields = row.split("\t")
            name = f"member-{index}.bin"
            if len(fields) != 12 or fields[0] != str(index) or fields[11] != name:
                raise ValueError("untimed original SDK member binding differs")
            payload = output / name
            if payload.stat().st_size != int(fields[6]) or identity.sha256(payload) != fields[7]:
                raise ValueError("untimed original SDK payload length/hash differs")
            payloads[name] = {"sha256": fields[7], "bytes": int(fields[6])}
        staged = f"/code/history/payloads/step-{step}/descriptor.tsv"
        prepared_argv = ["/code/writers/edit", "apply-sdk-step-prepared", case["v016_case"], str(step), staged, digest]
        original_run = case["steps"][step - 1]["run"]
        script = f"history/steps/step-{step}.sh"
        records.append({"index": step, "generator": {"argv": argv, "binary_sha256": writer["sha256"]},
                        "descriptor": str(descriptor), "descriptor_sha256": digest, "payloads": payloads,
                        "staged_descriptor": staged, "operator": "apply-sdk-step-prepared", "argv": prepared_argv,
                        "member_argv": [prepared_argv + [str(member)] for member in range(1, summary["members"] + 1)],
                        "original_run": original_run, "prepared_run": script,
                        "scope": "untimed original sdk_step generation; timed descriptor/payload read and SHA overhead declared; original member order retained"})
    receipts.write_new(folder / "sdk-payloads.json", {"schema": "fs-bench-pro-original-sdk-payloads-v1",
                       "case": case["v016_case"], "steps": records, "performance_samples": 0})
    return records


def prepare_workspace(recipe, folder, build_folder):
    family, case = family_case(recipe)
    if case.get("branch_schedule") or case.get("topology_schedule"):
        return prepare_context_workspace(family, case, folder, build_folder)
    if family["family"] == "historical_access":
        if not case.get("historical_access"):
            raise NotImplementedError("original historical access declaration required before producer execution")
        return prepare_historical_workspace(family, case, folder, build_folder)
    if family["family"] not in WORKSPACE_FAMILIES:
        raise ValueError("this family's workspace fixture port is not implemented yet")
    build = identity.load_build(build_folder)
    current = identity.source_identity()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    owned_input = case.get("git_workflow") or (case.get("history_schedule")
        and case["history_schedule"]["schema"] not in (*RECIPE_HISTORY_SCHEMAS, "original-ordinary-commit-sequence-v1"))
    source = folder / "source" if owned_input else prepared_inputs.source_path(case, build)
    expected = folder / "expected-native"
    history = None
    if case.get("history_schedule", {}).get("schema") == "original-ordinary-commit-sequence-v1":
        fixture, expectation, native, history, original_history = prepare_snapshot_fixture(case, folder, build)
    elif case.get("history_schedule", {}).get("schema") in RECIPE_HISTORY_SCHEMAS:
        fixture, expectation, native, history, original_history = prepare_recipe_history(case, folder, build)
    elif case.get("history_schedule"):
        fixture, expectation, native, history, original_history = prepare_ordered_fixture(case, folder, build)
    else:
        writer = build["binaries"]["workspace-writer"]["path"]
        if case.get("git_workflow"):
            made = receipts.command([writer, "fixture", case["v016_case"], str(source)], folder, "native-fixture", 120)
            fixture = json.loads(Path(made["stdout"]).read_text())
        else:
            fixture = prepared_inputs.make_initial(case, build,
                [writer, "fixture", case["v016_case"], str(source)], folder)
        authored = receipts.command([writer, "expected", case["v016_case"], str(expected)], folder, "native-expected", 120)
        expectation = json.loads(Path(authored["stdout"]).read_text())
    def original_check(root, step, label):
        argv = ([build["binaries"]["edit-host"]["path"], "verify", case["v016_case"], str(step)]
                if case.get("sdk_scenario") else
                [build["binaries"]["workload-host"]["path"], "workspace-verify-tree", case["v016_case"], "1", str(step)])
        proof = receipts.command(argv,
                                 folder, label, 120, cwd=root)
        return dict(line.split("=", 1) for line in Path(proof["stdout"]).read_text().splitlines())
    if history is None:
        native = {"fixture": original_check(source, 0, "original-fixture-check"),
                  "expected": original_check(expected, 1, "original-expected-check")}
    if any(item.get("verification_status") != "pass" for item in native.values()):
        raise ValueError("original native fixture/expectation check failed")
    dedup_inputs = None
    if case.get("reuse_schedule"):
        dedup_inputs = {}
        for step,root,key in ((0,source,"initial"),(1,expected,"final")):
            checked = receipts.command([build["binaries"]["workspace-writer"]["path"],"import-qualified",case["v016_case"],str(step),str(root)],
                                       folder,"independent-reuse-"+key,120)
            dedup_inputs[key] = json.loads(Path(checked["stdout"]).read_text())
    git_reference = None
    if case.get("git_workflow"):
        fixture, git_reference, git_native = prepare_git_fixture(case, folder, build)
        native.update(git_native)
    fixture.update(recipe=recipe, fixture_sha256=fixture["fixture_digest"])
    sdk_steps = prepare_sdk_payloads(case, folder, build)
    helpers = assets(folder / "code")
    copies = [(Path(build["binaries"]["workload-linux"]["path"]), "writers/workload"),
              (identity.ROOT / "benchmark/fs-bench-pro/families" / family["family"] / "workload.sh", "workload.sh")]
    if case.get("sdk_scenario") or case.get("ordinary_sdk_edits") or history is not None:
        copies.append((Path(build["binaries"]["edit-linux"]["path"]), "writers/edit"))
    if case.get("m1_schedule"):
        copies.append((Path(build["binaries"]["workspace-linux"]["path"]), "writers/recipe"))
    for origin, relative in copies:
        target = Path(helpers["root"]) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
        target.chmod(0o555)
        helpers["files"][relative] = identity.sha256(target)
    if history is not None:
        base = Path(helpers["root"]) / "history"
        shutil.copytree(folder / "history-manifests", base / "manifests")
        if (folder / "history-native-recipes.json").exists():
            shutil.copy2(folder / "history-native-recipes.json", base / "native-recipes.json")
        if sdk_steps:
            shutil.copytree(folder / "sdk-payloads", base / "payloads")
            shutil.copy2(folder / "sdk-payloads.json", base / "payloads.json")
            (base / "steps").mkdir()
            for record in sdk_steps:
                (Path(helpers["root"]) / record["prepared_run"]).write_text(sdk_step_script(record))
        for state in original_history["states"] if original_history is not None else ():
            shutil.copytree(state["input"], base / "checkpoints" / f"step-{state['index']}")
        for path in sorted(base.rglob("*")):
            if path.is_file():
                path.chmod(0o444)
                helpers["files"][str(path.relative_to(helpers["root"]))] = identity.sha256(path)
    if git_reference is not None:
        base = Path(helpers["root"]) / "git-reference"
        shutil.copytree(folder / "git-reference", base)
        for path in sorted(base.rglob("*")):
            if path.is_file():
                path.chmod(0o444)
                helpers["files"][str(path.relative_to(helpers["root"]))] = identity.sha256(path)
    helpers["sha256"] = hashlib.sha256(json.dumps(helpers["files"], sort_keys=True).encode()).hexdigest()
    reused, reuse = compatible_master(folder, fixture, current, source.stat().st_uid, source.stat().st_gid)
    if reused is None:
        volume = "layerfs-fsb-master-" + family["family"].replace("_", "-") + "-" + uuid.uuid4().hex[:16]
        docker = ["docker", "--host", "unix://" + build["socket"]]
        receipts.write_new(folder / "resource-claim.json", {"volume": volume, "created_by_this_run": True,
                           "purpose": "new immutable SDK-provisioned workspace input; never sample directly"})
        made_volume = receipts.command([*docker, "volume", "create", volume], folder, "master-volume", 15)
        if Path(made_volume["stdout"]).read_text().strip() != volume:
            raise ValueError("original master volume acknowledgement differs")
        provisioned = project.provision(source, volume, folder / "project", build)
    else:
        volume, provisioned = reused["master_volume"], reused["provision"]
        receipts.write_new(folder / "resource-claim.json", {"volume": volume, "created_by_this_run": False,
                           "purpose": "compatible closed prepared master reused; never a mutated sample", "reuse": reuse})
    result = {"schema": "fs-bench-pro-prepared-workspace-v1", "status": "PASS", "recipe": recipe, "build": str(Path(build_folder).resolve()),
              "family": family["family"], "case": case["id"], "identity": current, "fixture": fixture,
              "expectation": expectation, "native_verification": native, "helpers": helpers,
              "history_states": history,
              "sdk_steps": sdk_steps,
              "prepared_step_runs": {str(record["index"]): record["prepared_run"] for record in sdk_steps},
              "git_reference": git_reference,
              "independent_dedup_inputs": dedup_inputs,
              "generator_sha256": build["binaries"]["workspace-writer"]["sha256"],
              "source": str(source), "master_volume": volume, "provision": provisioned, "source_uid": source.stat().st_uid,
              "master_reuse": reuse,
              "source_gid": source.stat().st_gid, "global_profile": "Disposable/WAL/OFF",
              "overlay_profile": "MEMORY/OFF/EXCLUSIVE", "construction_workers": 1,
              "setup": ("initial native fixture independently verified; selected M1 native expectations materialized with None mode observations and payloads removed after manifest/scope authoring; actual scoped proof binds measured helper observations; public Init/seal/install once; independent sample byte clone"
                        if case.get("m1_schedule") else "native fixture and independent algebraic selected states fully verified; public Init/seal/install once; sample uses independent closed byte clone"),
              "cache": "explicit setup source/Store warmth; class B additionally requires warm terminal cleanup and actual zero source demands"}
    seal_prepared(folder, result, build_folder)
    return result


def prepare_git_fixture(case, folder, build):
    """Original Linux Git setup/reference, full initial .git imported by Init."""
    if not case.get("git_workflow") or not case["v016_case"].startswith("git-tool-"):
        raise ValueError("explicit frozen Git workflow case required")
    folder = Path(folder)
    source, expected = folder / "source", folder / "expected-native"
    token = uuid.uuid4().hex[:16]
    container = "layerfs-fsb-git-native-" + token
    inside = "/tmp/layerfs-fsb-git-native-" + token
    docker = ["docker", "--host", "unix://" + build["socket"]]
    writer = "/writer"
    case_arg = shlex.quote(case["v016_case"])
    body = ["set -eu", "printf '%s\\n' " + shlex.quote(build["binaries"]["workload-linux"]["sha256"] + "  /writer") + " | sha256sum -c -",
            "mkdir -m 700 " + inside,
            writer + " workspace-git-prepare /source 1 > " + inside + "/prepare.txt",
            writer + " workspace-git-reference " + inside + "/reference-build " + case_arg + " 1 > " + inside + "/reference.txt",
            "mkdir " + inside + "/reference " + inside + "/receipts",
            "cp --preserve=mode,timestamps " + inside + "/reference-build/{identity,normalization.tsv,expected-first-status,expected-diff,expected-head,expected-tree,expected-parent} " + inside + "/reference/",
            "cp -a " + inside + "/reference-build/repository/.git /expected-native/.git",
            "touch -d @1700000000 /expected-native",
            "cd /expected-native; " + writer + " workspace-git-verify " + case_arg + " 1 " + inside + "/reference > " + inside + "/receipts/qualification.txt",
            "cp " + inside + "/prepare.txt " + inside + "/reference.txt " + inside + "/receipts/"]
    receipts.write_new(folder / "git-native-resource-claim.json", {"container": container, "created_by_this_run": True,
        "purpose": "untimed pinned Linux native Git preparation and independent reference; no Store or mount",
        "failure_disposition": "retain exact container; no retry or inferred completion"})
    receipts.command([*docker, "create", "--name", container, "--network", "none",
                      "--cpus", "2", "--memory", "2g", "--memory-swap", "2g", "--pids-limit", "256",
                      "--user", f"{source.stat().st_uid}:{source.stat().st_gid}",
                      "-e", "LAYERFS_CONSTRUCTION_WORKERS=1", identity.IMAGE,
                      "/bin/bash", "-euo", "pipefail", "-c", "\n".join(body)], folder, "git-native-create", 15)
    inspected = receipts.command([*docker, "inspect", container, "--format", "{{json .HostConfig}}"],
                                 folder, "git-native-profile", 15)
    actual = json.loads(Path(inspected["stdout"]).read_text())
    profile = {"NanoCpus": 2_000_000_000, "Memory": 2 * 1024**3, "MemorySwap": 2 * 1024**3, "PidsLimit": 256}
    if any(actual.get(name) != value for name, value in profile.items()):
        raise ValueError("original native Git 2CPU/2GiB/no-swap/256PID profile differs")
    receipts.command([*docker, "cp", "--archive", build["binaries"]["workload-linux"]["path"], container + ":/writer"],
                     folder, "git-native-code", 15)
    for path, name in ((source, "source"), (expected, "expected-native")):
        receipts.command([*docker, "cp", "--archive", str(path), container + ":/" + name],
                         folder, "git-native-input-" + name, 15)
    receipts.command([*docker, "start", "--attach", container], folder, "git-native-author", 120)
    receipts.command([*docker, "cp", "--archive", container + ":/source/.git", str(source / ".git")],
                     folder, "git-initial-repository-export", 30)
    # Copying .git changes the existing host directory's mtime, as in the frozen driver.
    source.chmod(0o750)
    os.utime(source, ns=(MTIME_NS, MTIME_NS))
    receipts.command([*docker, "cp", "--archive", container + ":" + inside + "/reference", str(folder / "git-reference")],
                     folder, "git-reference-export", 30)
    receipts.command([*docker, "cp", container + ":" + inside + "/receipts", str(folder / "git-native-receipts")],
                     folder, "git-native-receipts-export", 15)
    fields = lambda name: dict(line.split("=", 1) for line in (folder / "git-native-receipts" / name).read_text().splitlines())
    preparation, reference, qualification = fields("prepare.txt"), fields("reference.txt"), fields("qualification.txt")
    if qualification.get("verification_status") != "pass" or qualification.get("git_semantic_verification_status") != "pass":
        raise ValueError("original independent native Git semantic/complete-source qualification failed")
    bundle = folder / "git-reference"
    identity_rows = (bundle / "identity").read_text().splitlines()
    if (identity_rows != [case["v016_case"], "1", preparation["git_version"]]
            or reference.get("reference_case") != case["v016_case"] or reference.get("reference_seed") != "1"
            or reference["git_genesis_head"] != preparation["git_genesis_head"]
            or (bundle / "expected-parent").read_text().strip() != preparation["git_genesis_head"]
            or reference["git_effective_config"] != preparation["git_effective_config"]
            or int(reference["git_repository_transient_bound_bytes"]) > 256 * 1024**2):
        raise ValueError("independent Git reference identity/genesis/config/transient bound differs")
    checked = receipts.command([build["binaries"]["workspace-writer"]["path"], "git-fixture-check", case["v016_case"], str(source)],
                               folder, "git-complete-initial-fixture-check", 120)
    fixture = json.loads(Path(checked["stdout"]).read_text())
    if fixture.get("verification_status") != "pass":
        raise ValueError("original complete source plus prepared Git fixture failed")
    witness = {"schema": "fs-bench-pro-original-git-reference-v1", "status": "PASS", "case": case["v016_case"],
               "seed": 1, "image": identity.IMAGE, "container": container, "git_version": preparation["git_version"],
               "resource_profile": {name: actual[name] for name in profile},
               "git_effective_config": preparation["git_effective_config"], "genesis_head": preparation["git_genesis_head"],
               "transient_bound_bytes": int(reference["git_repository_transient_bound_bytes"]),
               "files": {path.name: identity.sha256(path) for path in sorted(bundle.iterdir())},
               "initial_manifest": str(source.with_suffix(".git.manifest.tsv")),
               "scope": "native initial real .git and independent final-source-derived Git semantic identities; no measured editor replay; index stat bytes are measured custody only"}
    receipts.command([*docker, "rm", container], folder, "git-native-remove-passing", 15)
    receipts.write_new(folder / "git-reference.json", witness)
    return fixture, witness, {"git_initial_complete": {"verification_status": "pass", "fixture_digest": fixture["fixture_digest"]},
                              "git_independent_reference": qualification}


def seal_prepared(folder, result, build_folder=None):
    if build_folder is not None:
        result["build"] = str(Path(build_folder).resolve())
    build = identity.load_build(result["build"]) if result.get("build") else None
    if build is not None:
        _, case = family_case(result["recipe"]) if result["recipe"] not in ("empty", "big64m") else (None, None)
        result["preparation_key"] = prepared_inputs.preparation_key(result["recipe"], case, result["identity"], build)
    if result.get("provision"):
        result["store_builder_key"] = prepared_inputs.product_store_key(result["identity"])
    source = result.get("source")
    if source and Path(source).is_relative_to(prepared_inputs.CACHE):
        home = Path(source).parent
        receipts.verify_manifest(home)
        result["initial_input"] = {"source": source,
            "metadata": str(home / "input.json"), "metadata_sha256": identity.sha256(home / "input.json"),
            "manifest": str(home / "manifest.json"), "manifest_sha256": identity.sha256(home / "manifest.json")}
    receipts.write_new(Path(folder) / "prepared.json", result)
    receipts.manifest(folder)


def load(folder, recipe=None):
    folder = Path(folder)
    receipts.verify_manifest(folder)
    result = json.loads((folder / "prepared.json").read_text())
    if result.get("initial_input"):
        pointer = result["initial_input"]
        home = Path(pointer["source"]).parent
        if (identity.sha256(pointer["metadata"]) != pointer["metadata_sha256"]
                or identity.sha256(pointer["manifest"]) != pointer["manifest_sha256"]):
            raise ValueError("shared initial input pointer changed")
        receipts.verify_manifest(home)
        cached = json.loads(Path(pointer["metadata"]).read_text())
        if cached["tree"] != prepared_inputs.tree_record(pointer["source"]):
            raise ValueError("shared initial input bytes/metadata/link classes changed")
    if result["status"] != "PASS" or recipe is not None and result["recipe"] != recipe:
        raise ValueError("sealed fixture recipe/status differs")
    if result["schema"] in ("fs-bench-pro-prepared-native-init-v1", "fs-bench-pro-prepared-native-import-v1", "fs-bench-pro-prepared-native-footprint-v1"):
        for relative,wanted in result.get("helpers",{}).get("files",{}).items():
            if identity.sha256(Path(result["helpers"]["root"])/relative)!=wanted:
                raise ValueError("sealed native-input helper changed: "+relative)
        return result
    if identity.sha256(result["provision"]["sealed_store"]) != result["provision"]["store_sha256"]:
        raise ValueError("sealed host Store changed")
    if identity.sha256(result["provision"]["manifest"]) != result["provision"]["manifest_sha256"]:
        raise ValueError("sealed installed manifest changed")
    for relative, wanted in result["helpers"]["files"].items():
        if identity.sha256(Path(result["helpers"]["root"]) / relative) != wanted:
            raise ValueError("sealed executable helper changed: " + relative)
    return result


def clone(prepared, folder, build):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    volume = "layerfs-fsb-sample-" + uuid.uuid4().hex[:16]
    container = "layerfs-fsb-copy-" + uuid.uuid4().hex[:16]
    docker = ["docker", "--host", "unix://" + build["socket"]]
    receipts.write_new(folder / "resource-claim.json", {"volume": volume, "container": container,
                       "master": prepared["master_volume"], "created_by_this_run": True,
                       "failed_or_uncertain": "retain; no guessed removal"})
    receipts.command([*docker, "volume", "create", volume], folder, "sample-volume", 15)
    body = "test ! -e /dest/global; test ! -s /source/global/store.sqlite-wal; test ! -s /source/global/store.sqlite-journal; mkdir -m 700 /dest/global; cp --reflink=never --sparse=never --preserve=mode,ownership,timestamps /source/global/store.sqlite /dest/global/store.sqlite; cmp /source/global/store.sqlite /dest/global/store.sqlite; chmod --reference=/source/global /dest/global; chown --reference=/source/global /dest/global; touch -r /source/global /dest/global; sha256sum /source/global/store.sqlite /dest/global/store.sqlite"
    receipts.command([*docker, "create", "--name", container, "--network", "none",
                      "-v", prepared["master_volume"] + ":/source:ro", "-v", volume + ":/dest",
                      identity.IMAGE, "/bin/bash", "-euo", "pipefail", "-c", body], folder, "copy-create", 15)
    copied = receipts.command([*docker, "start", "--attach", container], folder, "copy", 15)
    hashes = [line.split()[0] for line in Path(copied["stdout"]).read_text().splitlines()]
    if hashes != [prepared["provision"]["store_sha256"]] * 2:
        raise ValueError("original independent Store clone differs from its sealed master")
    receipts.command([*docker, "rm", container], folder, "copy-remove-passing", 15)
    result = {"schema": "fs-bench-pro-sample-clone-v1", "status": "PASS", "volume": volume,
              "master": prepared["master_volume"], "store_sha256": hashes[1],
              "clone_method": "closed independent byte copy; cp --reflink=never --sparse=never; compared bytes and SHA-256",
              "cache_contract": "clone is not cold; phase cache precondition is enforced separately",
              "receipt": copied}
    receipts.write_new(folder / "clone.json", result)
    return result


def stage(container, prepared, folder, build, *, deadline=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    remote_manifest = "/code/.fs-bench-pro-helpers.sha256"
    lines = []
    for path, digest in prepared["helpers"]["files"].items():
        if (type(path) is not str or not path or path.startswith("/") or any(char in path for char in "\x00\r\n")
                or PurePosixPath(path).as_posix() != path or any(part in (".", "..") for part in PurePosixPath(path).parts)
                or not PurePosixPath(path).parts or PurePosixPath(path).parts[0] == remote_manifest.rsplit("/", 1)[1]
                or type(digest) is not str or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise ValueError("exact relative helper path and SHA-256 required for complete staging manifest")
        lines.append(digest + "  /code/" + path)
    if not lines:
        raise ValueError("complete helper staging manifest cannot be empty")
    manifest = folder / "helper-checksums.sha256"
    with manifest.open("x") as stream:
        stream.write("\n".join(lines) + "\n")
    manifest_sha = identity.sha256(manifest)
    docker = ["docker", "--host", "unix://" + build["socket"]]
    def call(argv, label):
        import time
        seconds = 15 if deadline is None else min(15, deadline-time.monotonic())
        if seconds <= 0:
            raise TimeoutError("original verifier helper-staging deadline expired")
        return receipts.command(argv, folder, label, seconds)
    call([*docker, "cp", "--archive", prepared["helpers"]["root"] + "/.", container + ":/code"], "stage-code")
    for cell, record in prepared.get("oracles", {}).get("cases", {}).items():
        call([*docker, "cp", "--archive", record["path"], container + ":/code/expected-" + cell], "stage-oracle-" + cell)
    call([*docker, "cp", str(manifest), container + ":" + remote_manifest], "stage-code-checksum-manifest")
    # Authenticate the full file before GNU's unchanged complete-file checker.
    # One digest/path line stays in argv regardless of the number of helpers.
    script = ("printf '%s\\n' " + shlex.quote(manifest_sha + "  " + remote_manifest) +
              " | sha256sum --check -\nsha256sum --check " + remote_manifest)
    checked = call([*docker, "exec", "--user", "0:0", container,
                    "/bin/bash", "-euo", "pipefail", "-c", script], "stage-code-check")
    return {"status": "PASS", "container": container, "actual_helper_byte_check": checked,
            "helper_checksum_manifest": {"path": str(manifest.resolve()), "sha256": manifest_sha,
                                         "remote": remote_manifest, "files": len(lines),
                                         "scope": "exact original ordered helper paths/hashes; remote full manifest authenticated before unchanged sha256sum --check semantics; setup only"}}
