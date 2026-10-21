"""Closed native inputs shared across setup cases; never reused as measurements."""
import hashlib
import json
import os
from pathlib import Path

from . import identity, receipts

CACHE = identity.ROOT / "benchmark-results/fs-bench-pro/prepared-inputs"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def input_descriptor(case):
    """Initial input only: operation/Commit cadence is outside native construction."""
    fixture = {key: value for key, value in case["fixture"].items()
               if key not in ("recipe", "definition_source")}
    if case.get("sdk_scenario"):
        # All frozen SDK edits start from the same payload.bin byte generator.
        fixture = {"profile": "sdk-edit-standard-content-v1",
                   "bytes": case["sdk_scenario"]["fixture_bytes"],
                   "sha256": fixture.get("content_sha256", fixture.get("payload_sha256")),
                   "generator_seed": fixture["generator_seed"],
                   "directory_mode": fixture.get("directory_mode", fixture.get("root_mode")), "file_mode": fixture["file_mode"],
                   "mtime_seconds": fixture["mtime_seconds"], "mtime_nanoseconds": fixture["mtime_nanoseconds"]}
    aliases = {"regular_files": "files", "directories": "directories_including_root",
               "directory_mode": "root_mode", "content_sha256": "payload_sha256", "bytes": "logical_bytes"}
    fixture = {aliases.get(key, key): value for key, value in fixture.items()}
    if "profile" not in fixture:
        if case.get("registry", {}).get("kind") == "payload-create":
            fixture = {"profile": "ordinary-empty-native-root", "seed": 1}
        else:
            fixture["complete_case"] = case["id"]
    # Real Git genesis and closed-history producers include additional setup work.
    # They retain a complete case preparation rather than borrowing a mutable input.
    if case.get("git_workflow") or case.get("historical_access"):
        fixture["complete_case"] = case["id"]
    return {"fixture": fixture, "uid": os.getuid(), "gid": os.getgid(), "seed": 1}


def native_key(case, build):
    return {"version": 1, "input": input_descriptor(case),
            "native_binaries": {name: build["binaries"][name]["sha256"]
                                for name in ("namespace-writer", "workspace-writer", "workload-host", "edit-host")},
            "flags": build["flags"], "explicit_rustflags": build.get("explicit_rustflags")}


def source_path(case, build):
    return CACHE / digest(native_key(case, build)) / "source"


def tree_record(root):
    """Complete portable metadata, link identity and byte hashes, without following links."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("closed initial input must be its exact real directory")
    result, links = {}, {}
    for path in [root, *sorted(root.rglob("*"))]:
        stat = path.lstat(); relative = str(path.relative_to(root))
        entry = {"mode": stat.st_mode & 0o7777, "uid": stat.st_uid, "gid": stat.st_gid,
                 "mtime_ns": stat.st_mtime_ns}
        if path.is_symlink():
            entry.update(kind="symlink", target=os.readlink(path))
        elif path.is_dir():
            entry.update(kind="directory")
        elif path.is_file():
            inode = (stat.st_dev, stat.st_ino)
            entry.update(kind="file", bytes=stat.st_size, sha256=identity.sha256(path),
                         link_group=links.setdefault(inode, relative), nlink=stat.st_nlink)
        else:
            raise ValueError("unsupported initial fixture entry: " + relative)
        result[relative] = entry
    return result


def load_source(case, build):
    root = source_path(case, build); summary = root.parent / "input.json"
    if not summary.exists():
        if root.exists():
            raise ValueError("retained incomplete native preparation; never refresh or replay")
        return None
    manifest = receipts.verify_manifest(root.parent)
    result = json.loads(summary.read_text())
    if result["key"] != native_key(case, build) or result["tree"] != tree_record(root):
        raise ValueError("closed native input changed; never refresh or reuse")
    if result["source"] != str(root) or manifest["files"].get("input.json") != identity.sha256(summary):
        raise ValueError("closed native input identity differs")
    return result


def require_context_producer(case, build):
    """A context case shares an initial input only if the context writer made it.

    Its admission binds role, step, scope and recipe to that writer's step-0
    receipt. An ordinary summary carries none of them and the complete manifest
    cannot supply them, so the reverse derivation of make_initial does not
    exist. This only refuses, before any output; load_source still admits.
    """
    summary = source_path(case, build).parent / "input.json"
    if not summary.exists():
        return
    cached = json.loads(summary.read_text())
    argv, fixture = cached["generation"]["argv"], cached["fixture"]
    missing = [field for field in ("role", "step", "manifest_sha256", "recipe_sha256") if field not in fixture]
    if len(argv) == 6 and argv[1] == "materialize-context" and argv[4] == "0" and not missing:
        return
    raise ValueError(
        "shared initial input " + str(summary.parent) + " was first produced by case " + str(cached["producer_case"])
        + " with `" + (argv[1] if len(argv) > 1 else "an undeclared generator") + "`, not by the context writer's"
        " `materialize-context CASE ROLE 0`; its summary lacks " + (", ".join(missing) or "that generation")
        + ". Required order: prepare a context case sharing this input (such as " + case["id"]
        + ") before any ordinary case that shares it. The closed input is retained unchanged and never"
        " refreshed; nothing was created for this request")


def make_initial(case, build, argv, output, label="native-fixture", environment=None):
    """One original generation; each case still pays its independent native oracle."""
    root = source_path(case, build); cached = load_source(case, build)
    if cached is None:
        root.parent.mkdir(parents=True, exist_ok=False)
        before = os.statvfs(identity.ROOT)
        receipts.write_new(root.parent / "preparation-claim.json", {
            "key": native_key(case, build), "producer_case": case["id"], "argv": argv,
            "source": str(root), "host_free_bytes_before": before.f_bavail * before.f_frsize,
            "purpose": "new closed initial input; no product or performance sample"})
        command = receipts.command(argv, root.parent, label, 120, environment=environment)
        fixture = json.loads(Path(command["stdout"]).read_text())
        if (fixture.get("case", case["v016_case"]) != case["v016_case"]
                or fixture.get("control_id", case["v016_case"]) != case["v016_case"]):
            raise ValueError("original initial producer returned another case")
        if len(argv) >= 5 and argv[1] == "materialize-context":
            if fixture.get("role") != argv[3] or fixture.get("step") != 0 or fixture.get("seed") != 1:
                raise ValueError("original initial producer role/step/seed differs")
        cached = {"status": "CLOSED_UNQUALIFIED", "key": native_key(case, build), "producer_case": case["id"],
                  "source": str(root), "fixture": fixture, "tree": tree_record(root),
                  "generation": command, "profile": "closed setup only; no cold claim"}
        receipts.write_new(root.parent / "input.json", cached)
        receipts.manifest(root.parent)
    # Case is a declaration about the already verified identical initial input.
    # Original generator argv/stdout stay immutable under the original producer.
    fixture = dict(cached["fixture"])
    if "fixture_digest" not in fixture and "manifest_sha256" in fixture:
        # Context and ordinary writers declare the same complete initial tree
        # with different summary names. Derive the ordinary view from the
        # retained complete manifest; do not rewrite the producer's receipt.
        manifest = root.with_suffix(".manifest.tsv")
        digest_value = identity.sha256(manifest)
        rows = manifest.read_text().splitlines()
        if digest_value != fixture["manifest_sha256"] or rows[0] != "workspace-independent-manifest-v1":
            raise ValueError("shared context initial manifest differs from its original producer")
        fixture.update(fixture_digest=digest_value, recipe_identity=fixture["recipe_sha256"],
            files=sum(row.split("\t")[1] == "file" for row in rows[1:]))
    if "case" in fixture:
        fixture["case"] = case["v016_case"]
    receipt = {"status": "REUSED_CLOSED_INPUT", "attempts": 0,
               "source": str(root), "input_manifest_sha256": identity.sha256(root.parent / "manifest.json"),
               "producer_case": cached["producer_case"], "requested_case": case["id"],
               "original_generation": cached["generation"],
               "scope": "initial bytes/metadata only; original producer receipt retained; current-case oracle remains required"}
    receipts.write_new(Path(output) / (label + "-input.json"), receipt)
    return fixture


def product_store_key(current):
    """A prepared original contains a Store: include its complete product builder scope."""
    files = current["files"]
    selected = {name: sha for name, sha in files.items()
                if (name.startswith("core/crates/") and ("/src/" in name or "/sql/" in name
                    or name.endswith(("/Cargo.toml", "/build.rs"))))
                or name.startswith(("core/vendor/", ".cargo/", "benchmark/fs-bench-pro/runtime/src/"))
                or name in ("core/Cargo.toml", "core/Cargo.lock",
                            "benchmark/fs-bench-pro/runtime/Cargo.toml",
                            "benchmark/fs-bench-pro/runtime/Cargo.lock")}
    return {"version": 1, "product_builder_files": selected, "image": identity.IMAGE,
            "host_toolchain": "1.85.1", "profile": "locked release with repository ARM64 flags",
            "explicit_rustflags": os.environ.get("RUSTFLAGS"),
            "global_profile": "Disposable/WAL/OFF", "construction_workers": 1}


def preparation_key(recipe, case, current, build):
    """Kept complete case views change only with their actual setup producers."""
    family = case.get("registry", {}).get("family") if case else None
    producer_modules = {"fixtures.py", "prepared_inputs.py", "project.py", "identity.py", "oracle.py"}
    code = {name: sha for name, sha in current["files"].items()
            if (name.startswith("benchmark/fs-bench-pro/engine/") and Path(name).name in producer_modules)
            or name.startswith(("benchmark/fs-bench-pro/engine/recipes/", "benchmark/fs-bench-pro/writers/"))
            or name.startswith(("benchmark/fs-bench-pro/workload/", "benchmark/fs-bench-pro/families/"))
            or name.startswith(("benchmark/cluster-two/cells/", "benchmark/cluster-two/cache/")) and name.endswith(".py")
            or family and name == "benchmark/fs-bench-pro/families/" + family + "/workload.sh"}
    # Runtime setup opens, constructs, seals and installs Stores. Pure native Init
    # inputs have no setup Store; their measured Init is never cached here.
    store = recipe in ("empty", "big64m") or (case is not None and not case.get("project_import")
            and not case.get("store_footprint_schedule") and case.get("registry", {}).get("family") != "init_namespace")
    return {"version": 1, "recipe": recipe, "case": case, "producer_files": code,
            "binaries": {name: value["sha256"] for name, value in build["binaries"].items()
                         if name not in ("runtime", "daemon") or store},
            "store_builder": product_store_key(current) if store else None,
            "profile": "closed prepared fixture only; each case sample is a new independent writable copy"}
