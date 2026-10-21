"""Context fixture/source admission uses mocked tools, never a live Store."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures


def declared(family, position=0):
    return json.loads((BENCH / "families" / family / "family.json").read_text())["cases"][position]


def build(folder):
    # Each synthetic binary archive belongs to this bounded test fixture.
    fixtures.prepared_inputs.CACHE = folder / "input-cache"
    result = {"socket": "mock-socket", "binaries": {}, "flags": "mock sealed inputs", "explicit_rustflags": None}
    for name in ("namespace-writer", "workspace-writer", "workload-host", "edit-host", "workload-linux", "edit-linux", "workspace-linux"):
        path = folder / name
        path.write_text("mocked sealed tool " + name)
        result["binaries"][name] = {"path": str(path), "sha256": fixtures.identity.sha256(path)}
    return result


class ContextFixtures(unittest.TestCase):
    def setUp(self):
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        patcher = patch.object(fixtures.prepared_inputs, "CACHE", Path(cache.name) / "inputs")
        patcher.start(); self.addCleanup(patcher.stop)

    def native_tools(self, case, calls, *, wrong_role=False, bad_payload=False):
        def command(argv, out, label, seconds, **options):
            calls.append((argv, label, seconds, options))
            self.assertLessEqual(seconds, 120)
            output = Path(out) / (label + ".stdout")
            mode = argv[1]
            if mode == "materialize-context":
                _, _, name, role, step, destination = argv
                root = Path(destination); root.mkdir()
                data = (role + step).encode(); (root / "payload.bin").write_bytes(data)
                full = root.with_suffix(".manifest.tsv")
                full.write_text("workspace-independent-manifest-v1\n.\tdirectory\t0\t755\t1700000000\t0\t-\n"
                                + f"payload.bin\tfile\t{len(data)}\t640\t1700000000\t0\t{hashlib.sha256(data).hexdigest()}\n")
                scope = root.with_suffix(".scope.tsv") if case.get("m1_schedule") else full
                if scope != full:
                    scope.write_text("original-m1-selective-scope-v1\n.\tdirectory\t0\t-\t-\t-\t-\t-\n"
                                     + f"payload.bin\tfile\t{len(data)}\t640\t1700000000\t0\t0:{len(data)}\t-\n")
                summary = {"case": name, "role": "a" if wrong_role else role, "step": int(step), "seed": 1,
                           "manifest_sha256": fixtures.identity.sha256(full),
                           "context_manifest_sha256": fixtures.identity.sha256(scope), "recipe_sha256": "a" * 64,
                           "entries": 2, "logical_bytes": len(data)}
                output.write_text(json.dumps(summary))
            elif mode == "verify-context":
                _, _, name, role, step, source, modes = argv
                if case.get("m1_schedule"):
                    self.assertEqual(Path(modes).read_bytes(), b"original-context-created-modes-v1\nrole\tpath\tmode\n")
                else:
                    self.assertEqual(modes, "-")
                output.write_text(json.dumps({"case": name, "role": role, "step": int(step),
                                              "verification_status": "pass"}))
            elif mode == "verify-manifest":
                output.write_text("verification_status=pass\n")
            elif mode == "prepare-context-step":
                _, _, name, role, step, destination = argv
                root = Path(destination); root.mkdir()
                count = 2 if case.get("m1_schedule") else 1
                body = f"original-context-step-payloads-v1\ncase\t{name}\nrole\t{role}\nstep\t{step}\nmembers\t{count}\n"
                for member in range(1, count + 1):
                    data = bytes([member, int(step)])
                    path = root / f"member-{member}.bin"; path.write_bytes(data)
                    digest = hashlib.sha256(data).hexdigest()
                    body += f"{member}\tpayload-{member}.bin\t0\t1\t8\t9\t2\t{digest}\t640\t1700000000\t0\t{path.name}\n"
                descriptor = root / "descriptor.tsv"; descriptor.write_text(body)
                if bad_payload:
                    (root / "member-1.bin").write_bytes(b"changed")
                output.write_text(json.dumps({"case": name, "role": role, "step": int(step), "members": count,
                                              "descriptor_sha256": fixtures.identity.sha256(descriptor)}))
            elif mode == "prepare-context-discard":
                _, _, name, destination = argv
                root = Path(destination); root.mkdir()
                data = bytes(range(256)); target = "d000/f00054"
                descriptor = root / "witness.tsv"
                descriptor.write_text(f"original-context-discard-witness-v1\n{name}\t0\t{target}\t{data.hex()}\n")
                output.write_text(json.dumps({"case": name, "role": "0", "path": target, "bytes": 256,
                                              "payload_sha256": hashlib.sha256(data).hexdigest(),
                                              "descriptor_sha256": fixtures.identity.sha256(descriptor)}))
            elif argv[0] == "docker":
                output.write_text(argv[-1] + "\n")
            else:
                self.fail("undeclared mocked tool invocation " + repr(argv))
            return {"argv": argv, "stdout": str(output), "status": "PASS", "exit_code": 0}
        return command

    def binding(self, case):
        current = {"source_commit": "mock-source", "source_tree": "mock-tree", "product_tree": "mock-product",
                   "files": {path: fixtures.identity.sha256(fixtures.identity.ROOT / path)
                             for path in fixtures.CONTEXT_SOURCE_FILES}}
        return current, fixtures.context_source_binding(case, current)

    def prepared(self, folder, case):
        tools = build(folder); current, _ = self.binding(case); calls = []
        def provision(source, volume, out, admitted):
            out.mkdir(); store = out / "store.sqlite"; manifest = out / "installed.manifest"
            store.write_bytes(b"mocked closed bytes, not SQLite"); manifest.write_bytes(b"mocked binding")
            return {"schema": "mocked-provision-only", "sealed_store": str(store), "manifest": str(manifest),
                    "store_sha256": fixtures.identity.sha256(store), "manifest_sha256": fixtures.identity.sha256(manifest)}
        family = {"family": case["registry"]["family"]}
        with patch.object(fixtures.identity, "load_build", return_value=tools), \
             patch.object(fixtures.identity, "source_identity", return_value=current), \
             patch.object(fixtures.receipts, "command", side_effect=self.native_tools(case, calls)), \
             patch.object(fixtures, "compatible_master", return_value=(None, None)), \
             patch.object(fixtures.project, "provision", side_effect=provision):
            prepared = fixtures.prepare_context_workspace(family, case, folder / "prepared", "mock-build")
        return prepared, tools, calls

    def test_context_plan_preserves_roles_selected_scope_and_exact_sdk_members(self):
        case = declared("branch_development")
        plan = fixtures.context_plan(case)
        self.assertEqual(plan["initial_role"], "trunk")
        self.assertEqual(plan["roles"], ["trunk", "a", "b"])
        self.assertEqual(plan["original_context_runs"]["a"]["1"],
                         "workload.sh stage v016-branch-mixed-100mb-5000-k10-v1 a 1")
        self.assertEqual(plan["checkpoints"], [{"role": role, "index": 10} for role in ("trunk", "a", "b")])
        self.assertEqual([(x["role"], x["index"], x["members"]) for x in plan["sdk_steps"]],
                         [(role, step, 2) for role in ("trunk", "a", "b") for step in (2, 7)])
        self.assertEqual(fixtures.context_role_records(case, plan)["a"]["created_mode_scope_roles"], ["trunk", "a"])
        compact = fixtures.context_plan(declared("branch_development", 5))
        self.assertEqual(compact["roles"], ["trunk", "a", "b", "c"])
        self.assertEqual(len(compact["sdk_steps"]), 40)
        self.assertTrue(all(x["members"] == 1 for x in compact["sdk_steps"]))
        multi = fixtures.context_plan(declared("multi_workspace_development", 4))
        self.assertEqual(multi["initial_role"], "0")
        self.assertEqual(multi["roles"], ["0", "1", "2", "3"])
        self.assertEqual(multi["original_context_runs"]["3"]["100"],
                         "workload.sh stage v016-workspace-four-100mb-5000-k100-v1 100 3")
        self.assertEqual(len(multi["sdk_steps"]), 80)
        self.assertTrue(all(x["original_run"].endswith(" " + x["role"]) for x in multi["sdk_steps"]))

    def test_invalid_checkpoint_role_member_schedule_and_count_are_refused(self):
        case = declared("branch_development")
        variants = []
        for label in ("role", "checkpoint", "member", "missing", "boolean"):
            value = copy.deepcopy(case)
            if label == "role": value["branch_schedule"]["branches"][1]["role"] = "trunk"
            elif label == "checkpoint": value["branch_schedule"]["payload_checkpoints"].append({"role": "a", "local_index": 11})
            elif label == "member": value["steps"][1]["ordinary_edit_members"] = 1
            elif label == "missing": value["steps"].pop()
            else: value["branch_schedule"]["branches"][0]["local_commits"] = True
            variants.append((label, value))
        for label, value in variants:
            with self.subTest(label=label), self.assertRaises(ValueError):
                fixtures.context_plan(value)

    def test_pristine_initial_role_and_only_selected_native_states(self):
        for case in (declared("branch_development"), declared("multi_workspace_development"), declared("branch_development", 4)):
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary); tools = build(folder); _, binding = self.binding(case); calls = []
                with patch.object(fixtures.receipts, "command", side_effect=self.native_tools(case, calls)):
                    initial, _, native, states, _ = fixtures.prepare_context_native(case, folder, tools, binding)
                materialize = [argv for argv, _, _, _ in calls if argv[1] == "materialize-context"]
                expected = [(("trunk" if case.get("branch_schedule") else "0"), 0)]
                expected += [(x["role"], x["index"]) for x in fixtures.context_plan(case)["checkpoints"]]
                observed = [(argv[3], int(argv[4])) for argv in materialize]
                self.assertEqual(observed, expected if observed and observed[0][1] == 0 else expected[1:])
                self.assertEqual(sum(argv[1] == "verify-context" for argv, _, _, _ in calls), 1)
                self.assertEqual(len(states), len(expected) - 1)
                self.assertEqual(initial["role"], expected[0][0])
                self.assertIn("original-context-initial-check", native)
                checks = [argv for argv, _, _, _ in calls if argv[1] == "verify-manifest"]
                self.assertEqual(len(checks), 1 if case.get("m1_schedule") else len(expected))
                for state in states:
                    if case.get("m1_schedule"):
                        self.assertNotEqual(state["manifest_sha256"], state["native_manifest_sha256"])
                        self.assertIn("not proof", state["materialization_metadata"])
                    else:
                        self.assertEqual(state["manifest_sha256"], state["native_manifest_sha256"])

    def test_wrong_native_role_and_tampered_generated_payload_stop_before_provision(self):
        case = declared("branch_development")
        for variant in ("role", "payload"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary); tools = build(folder); _, binding = self.binding(case); calls = []
                with patch.object(fixtures.receipts, "command", side_effect=self.native_tools(case, calls, wrong_role=variant == "role", bad_payload=variant == "payload")), \
                     patch.object(fixtures.project, "provision") as provision, self.assertRaises(ValueError):
                    if variant == "role": fixtures.prepare_context_native(case, folder, tools, binding)
                    else: fixtures.prepare_context_payloads(case, folder, tools, binding)
                provision.assert_not_called()
                self.assertFalse(any(argv[0] == "docker" for argv, _, _, _ in calls))

    def test_prepared_context_schema_staging_and_readonly_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            prepared, tools, calls = self.prepared(Path(temporary), declared("branch_development"))
            case = declared("branch_development")
            self.assertEqual(prepared["schema"], fixtures.CONTEXT_PREPARED_SCHEMA)
            self.assertEqual(set(prepared["prepared_context_runs"]), {"trunk", "a", "b"})
            self.assertEqual(prepared["master_measurement_mounts"], 0)
            self.assertEqual(prepared["global_profile"], "Disposable/WAL/OFF")
            root = Path(prepared["helpers"]["root"])
            before = {str(p): fixtures.identity.sha256(p) for p in Path(temporary).rglob("*") if p.is_file()}
            with patch.object(fixtures.receipts, "command") as effect:
                admitted = fixtures.validate_runtime_helpers(case, prepared, tools)
            effect.assert_not_called(); self.assertEqual(admitted["status"], "PASS")
            self.assertEqual(before, {str(p): fixtures.identity.sha256(p) for p in Path(temporary).rglob("*") if p.is_file()})
            for record in prepared["sdk_context_steps"]:
                script = (root / record["prepared_run"]).read_text()
                self.assertIn("SDK_STEP_DESCRIPTOR=", script)
                self.assertTrue(script.endswith(" " + record["role"] + " " + str(record["index"]) + "\n"))
            self.assertFalse(any("apply-context-step-prepared" in argv for argv, _, _, _ in calls))

    def test_missing_cross_role_extra_or_stale_context_assets_are_refused_without_effect(self):
        variants = ("map", "checkpoint", "role", "source", "initial", "binary", "script", "payload", "extra", "metadata", "scope", "descriptor")
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                prepared, tools, _ = self.prepared(Path(temporary), declared("branch_development"))
                case = declared("branch_development"); bad = copy.deepcopy(prepared); root = Path(bad["helpers"]["root"])
                if variant == "map": bad["prepared_context_runs"]["a"].pop("2")
                elif variant == "checkpoint": bad["context_checkpoints"].pop()
                elif variant == "role": bad["sdk_context_steps"][0]["role"] = "a"
                elif variant == "source": bad["context_binding"]["model_files"][fixtures.CONTEXT_SOURCE_FILES[0]] = "0" * 64
                elif variant == "initial": bad["context_initial_recipe"]["argv"][3] = "a"
                elif variant == "binary":
                    (root / "writers/recipe").chmod(0o644)
                    (root / "writers/recipe").write_text("resealed stale recipe")
                    bad["helpers"]["files"]["writers/recipe"] = fixtures.identity.sha256(root / "writers/recipe")
                elif variant == "script":
                    path = bad["sdk_context_steps"][0]["prepared_run"]; (root / path).chmod(0o644)
                    (root / path).write_text("native fallback\n")
                    bad["helpers"]["files"][path] = fixtures.identity.sha256(root / path)
                elif variant == "payload":
                    path = "context/trunk/payloads/step-2/member-1.bin"; (root / path).chmod(0o644)
                    (root / path).write_bytes(b"changed")
                    bad["helpers"]["files"][path] = fixtures.identity.sha256(root / path)
                elif variant == "extra":
                    path = "context/a/steps/step-3.sh"; (root / path).write_text("undeclared SDK\n")
                    bad["helpers"]["files"][path] = fixtures.identity.sha256(root / path)
                elif variant == "scope":
                    state = bad["context_checkpoints"][0]
                    source = Path(state["manifest"])
                    source.write_text(source.read_text().replace("1700000000", "1800000000"))
                    state["manifest_sha256"] = fixtures.identity.sha256(source)
                    relative = state["staged_manifest"].removeprefix("/code/")
                    (root / relative).chmod(0o644); shutil.copy2(source, root / relative)
                    bad["helpers"]["files"][relative] = state["manifest_sha256"]
                    metadata = root / "context/native-recipes.json"; metadata.chmod(0o644)
                    metadata.write_text(json.dumps(bad["context_native_metadata"]))
                    bad["helpers"]["files"]["context/native-recipes.json"] = fixtures.identity.sha256(metadata)
                elif variant == "descriptor":
                    record = bad["sdk_context_steps"][0]; source = Path(record["descriptor"])
                    source.write_text(source.read_text().replace("payload-1.bin", "other.bin"))
                    digest = fixtures.identity.sha256(source); record["descriptor_sha256"] = digest
                    record["argv"][-1] = digest
                    for argv in record["member_argv"]: argv[-2] = digest
                    relative = record["staged_descriptor"].removeprefix("/code/")
                    (root / relative).chmod(0o644); shutil.copy2(source, root / relative)
                    bad["helpers"]["files"][relative] = digest
                else:
                    path = "context/native-recipes.json"; (root / path).chmod(0o644)
                    (root / path).write_text("{}")
                    bad["helpers"]["files"][path] = fixtures.identity.sha256(root / path)
                with patch.object(fixtures.receipts, "command") as effect, self.assertRaises(ValueError):
                    fixtures.validate_runtime_helpers(case, bad, tools)
                effect.assert_not_called()

    def test_context_closed_master_reuse_and_historical_producer_execution_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); sibling = folder / "closed"; sibling.mkdir()
            good = {"schema": fixtures.CONTEXT_PREPARED_SCHEMA, "status": "PASS", "global_profile": "Disposable/WAL/OFF",
                    "identity": {"product_tree": "product", "files": {}},
                    "store_builder_key": fixtures.prepared_inputs.product_store_key({"files": {}}), "source_uid": 501, "source_gid": 20,
                    "fixture": {"fixture_sha256": "digest"}, "master_volume": "immutable", "provision": {"store_sha256": "seal"}}
            (sibling / "prepared.json").write_text(json.dumps(good)); (sibling / "manifest.json").write_text("sealed")
            with patch.object(fixtures, "load", return_value=good):
                reused, record = fixtures.compatible_master(folder / "next", {"fixture_sha256": "digest"}, {"product_tree": "product", "files": {}}, 501, 20)
            self.assertEqual(reused, good); self.assertIn("closed immutable setup", record["scope"])
            access = {"id": "original-access", "v016_case": "original-access", "fixture": {"recipe": "original-access", "seed": 1,
                       "producer": "original-producer", "producer_family": "dedup_branch_history"}}
            dependency = fixtures.historical_producer_dependency(access)
            self.assertEqual(dependency["status"], "EXECUTION_PENDING_ROOT")
            self.assertIn("mutated measured batch4 sample", dependency["forbidden_reuse"])
            with patch.object(fixtures, "family_case", return_value=({"family": "historical_access"}, access)), \
                 patch.object(fixtures.identity, "load_build") as admitted, patch.object(fixtures.receipts, "command") as effect, \
                 self.assertRaises(NotImplementedError):
                fixtures.prepare_workspace("original-access", folder / "never-created", "build")
            admitted.assert_not_called(); effect.assert_not_called(); self.assertFalse((folder / "never-created").exists())

    def test_original_two_worker_discard_is_prepared_once_and_bound_before_provision(self):
        for case in (declared("multi_workspace_development"), declared("multi_workspace_development", 4), declared("branch_development")):
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as temporary:
                prepared, tools, calls = self.prepared(Path(temporary), case)
                commands = [argv for argv, _, _, _ in calls if argv[1] == "prepare-context-discard"]
                witness = prepared["original_discard_witness"]
                root = Path(prepared["helpers"]["root"])
                if fixtures.context_discard_required(case):
                    self.assertEqual(len(commands), 1)
                    self.assertEqual(witness["role"], "0"); self.assertEqual(witness["bytes"], 256)
                    self.assertEqual(witness["staged_descriptor"], "/code/context/discard-witness.tsv")
                    self.assertEqual((root / "context/discard-witness.tsv").read_bytes(), Path(witness["descriptor"]).read_bytes())
                    self.assertEqual(witness["generator"]["source_binding"], prepared["context_binding"])
                    self.assertEqual(witness["generator"]["binary_sha256"], tools["binaries"]["workspace-writer"]["sha256"])
                    self.assertLess([x[1] for x in calls].index("original-context-discard-witness"),
                                    [x[1] for x in calls].index("master-volume"))
                else:
                    self.assertEqual(commands, []); self.assertIsNone(witness)
                    self.assertFalse((root / "context/discard-witness.tsv").exists())
                with patch.object(fixtures.receipts, "command") as effect:
                    self.assertEqual(fixtures.validate_runtime_helpers(case, prepared, tools)["status"], "PASS")
                effect.assert_not_called()

    def test_missing_cross_case_role_bytes_or_resealed_discard_assets_are_refused(self):
        variants = ("missing", "case", "role", "path", "hex", "payload_sha", "source", "binary", "staged", "receipt", "resealed")
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                case = declared("multi_workspace_development")
                prepared, tools, _ = self.prepared(Path(temporary), case)
                bad = copy.deepcopy(prepared); record = bad["original_discard_witness"]
                root = Path(bad["helpers"]["root"]); staged = root / "context/discard-witness.tsv"
                if variant == "missing": bad["original_discard_witness"] = None
                elif variant == "case": record["case"] = "different-case"
                elif variant == "role": record["role"] = "1"
                elif variant == "path": record["path"] = "../escape"
                elif variant == "hex": record["hex"] = "00" * 255
                elif variant == "payload_sha": record["payload_sha256"] = "0" * 64
                elif variant == "source": record["generator"]["source_binding"] = {}
                elif variant == "binary": record["generator"]["binary_sha256"] = "0" * 64
                elif variant == "staged":
                    staged.chmod(0o644); staged.write_text(staged.read_text().replace("d000/f00054", "d000/other"))
                    bad["helpers"]["files"]["context/discard-witness.tsv"] = fixtures.identity.sha256(staged)
                elif variant == "receipt":
                    receipt = Path(record["generator"]["receipt"])
                    summary = json.loads(receipt.read_text()); summary["role"] = 0
                    receipt.write_text(json.dumps(summary)); record["generator"]["receipt_sha256"] = fixtures.identity.sha256(receipt)
                else:
                    source = Path(record["descriptor"]); body = source.read_text().replace("d000/f00054", "d000/other")
                    source.write_text(body); staged.chmod(0o644); staged.write_text(body)
                    record["path"] = "d000/other"; record["descriptor_sha256"] = fixtures.identity.sha256(source)
                    bad["helpers"]["files"]["context/discard-witness.tsv"] = record["descriptor_sha256"]
                    bad["context_payload_metadata"]["original_discard_witness"] = record
                    metadata = root / "context/payloads.json"; metadata.chmod(0o644)
                    metadata.write_text(json.dumps(bad["context_payload_metadata"]))
                    bad["helpers"]["files"]["context/payloads.json"] = fixtures.identity.sha256(metadata)
                with patch.object(fixtures.receipts, "command") as effect, self.assertRaises(ValueError):
                    fixtures.validate_runtime_helpers(case, bad, tools)
                effect.assert_not_called()
        case = declared("multi_workspace_development", 4)
        malformed = copy.deepcopy(case); malformed["topology_schedule"]["discard_reopen"] = {"worker": 0, "witness_bytes": 256}
        with patch.object(fixtures.receipts, "command") as effect, self.assertRaises(ValueError):
            fixtures.prepare_context_discard(malformed, Path("unused"), {}, {})
        effect.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            prepared, tools, _ = self.prepared(Path(temporary), case)
            prepared["original_discard_witness"] = {"case": case["id"]}
            with patch.object(fixtures.receipts, "command") as effect, self.assertRaises(ValueError):
                fixtures.validate_runtime_helpers(case, prepared, tools)
            effect.assert_not_called()

    def test_discard_descriptor_requires_exact_case_role_safe_path_hex_bytes_and_lf(self):
        case = declared("multi_workspace_development"); name = case["v016_case"]
        value = bytes(range(256)).hex()
        body = f"original-context-discard-witness-v1\n{name}\t0\td000/f00054\t{value}\n"
        variants = (body.replace(name, "different-case"), body.replace("\t0\t", "\t1\t"),
                    body.replace("d000/f00054", "../escape"), body.replace("d000/f00054", "/absolute"),
                    body.replace(value, value[:-2]), body.replace(value, value.upper()),
                    body.replace("\n", "\r\n"), body.rstrip("\n"), body + "extra\n")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "witness.tsv"
            for index, bad in enumerate(variants):
                with self.subTest(index=index):
                    path.write_bytes(bad.encode())
                    with self.assertRaises(ValueError): fixtures.context_discard_descriptor(path, case)


if __name__ == "__main__":
    unittest.main()
