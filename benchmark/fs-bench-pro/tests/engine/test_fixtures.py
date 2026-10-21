"""Preparation is deterministic and cloning cannot reuse a mutated sample."""
import hashlib
import json
import copy
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures


class IsolatedInputs(unittest.TestCase):
    def setUp(self):
        cache = tempfile.TemporaryDirectory(); self.addCleanup(cache.cleanup)
        patcher = patch.object(fixtures.prepared_inputs, "CACHE", Path(cache.name) / "inputs")
        patcher.start(); self.addCleanup(patcher.stop)


class Fixtures(IsolatedInputs):
    def test_master_reuse_crosses_producer_key_directories_in_kept_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "kept-fixtures"
            prior = cache / "first-key" / "first-recipe"
            prior.mkdir(parents=True)
            good = {"schema": "fs-bench-pro-prepared-workspace-v1", "status": "PASS",
                "global_profile": "Disposable/WAL/OFF",
                "store_builder_key": fixtures.prepared_inputs.product_store_key({"files": {}}),
                "source_uid": 501, "source_gid": 20, "fixture": {"fixture_sha256": "same"},
                "master_volume": "one-master", "provision": {"store_sha256": "same-store"}}
            (prior / "prepared.json").write_text(json.dumps(good))
            (prior / "manifest.json").write_text("retained provenance")
            with patch.object(fixtures, "load", return_value=good) as checked:
                reused, record = fixtures.compatible_master(cache / "second-key" / "second-recipe",
                    {"fixture_sha256": "same"}, {"files": {}}, 501, 20)
            checked.assert_called_once_with(prior)
            self.assertEqual(reused["master_volume"], "one-master")
            self.assertEqual(record["prepared"], str(prior.resolve()))

    def test_nested_history_genesis_reuses_the_same_kept_initial_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "kept-fixtures"
            prior = cache / "first-key" / "access" / "genesis"
            prior.mkdir(parents=True)
            good = {"schema": "fs-bench-pro-prepared-workspace-v1", "status": "PASS",
                "global_profile": "Disposable/WAL/OFF",
                "store_builder_key": fixtures.prepared_inputs.product_store_key({"files": {}}),
                "source_uid": 501, "source_gid": 20, "fixture": {"fixture_sha256": "same"},
                "master_volume": "one-master", "provision": {"store_sha256": "same-store"}}
            (prior / "prepared.json").write_text(json.dumps(good))
            (prior / "manifest.json").write_text("retained provenance")
            with patch.object(fixtures, "load", return_value=good) as checked:
                reused, _ = fixtures.compatible_master(cache / "second-key" / "access" / "genesis",
                    {"fixture_sha256": "same"}, {"files": {}}, 501, 20)
            checked.assert_called_once_with(prior)
            self.assertEqual(reused["master_volume"], "one-master")

    def test_master_reuse_requires_exact_input_profile_product_and_identity(self):
        good = {"schema": "fs-bench-pro-prepared-workspace-v1", "status": "PASS",
                "global_profile": "Disposable/WAL/OFF", "store_builder_key": fixtures.prepared_inputs.product_store_key({"files": {}}), "identity": {"product_tree": "product", "files": {}},
                "source_uid": 501, "source_gid": 20, "fixture": {"fixture_sha256": "fixture"},
                "master_volume": "immutable-master", "provision": {"store_sha256": "sealed"}}
        variants = ({}, {"global_profile": "Durable"}, {"store_builder_key": {"changed_product": True}},
                    {"source_uid": 502}, {"source_gid": 21}, {"fixture": {"fixture_sha256": "other"}},
                    {"status": "FAIL"})
        for changed in variants:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                prior = root / "prior"
                prior.mkdir()
                (prior / "prepared.json").write_text(json.dumps({**good, **changed}))
                (prior / "manifest.json").write_text("sealed prior evidence")
                with patch.object(fixtures, "load", return_value=good) as checked:
                    reused, record = fixtures.compatible_master(root / "new", {"fixture_sha256": "fixture"},
                                                               {"product_tree": "product", "files": {}}, 501, 20)
                self.assertEqual(checked.call_count, 0 if changed else 1)
                if changed:
                    self.assertIsNone(reused)
                    self.assertIsNone(record)
                else:
                    self.assertEqual(reused["master_volume"], "immutable-master")
                    self.assertEqual(record["store_sha256"], "sealed")

    def test_a_matching_corrupt_master_is_refused_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prior = root / "prior"
            prior.mkdir()
            (prior / "prepared.json").write_text(json.dumps({"schema": "fs-bench-pro-prepared-workspace-v1",
                "status": "PASS", "global_profile": "Disposable/WAL/OFF", "store_builder_key": fixtures.prepared_inputs.product_store_key({"files": {}}), "identity": {"product_tree": "product", "files": {}},
                "source_uid": 501, "source_gid": 20, "fixture": {"fixture_sha256": "fixture"}}))
            with patch.object(fixtures, "load", side_effect=ValueError("retained evidence changed")):
                with self.assertRaisesRegex(ValueError, "retained evidence changed"):
                    fixtures.compatible_master(root / "new", {"fixture_sha256": "fixture"}, {"product_tree": "product", "files": {}}, 501, 20)

    def test_recipe_is_independent_of_output_path_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            first = fixtures.generate("empty", home / "first")
            second = fixtures.generate("empty", home / "second")
            self.assertEqual(first, second)
            self.assertEqual((first["files"], first["logical_bytes"]), (0, 0))
            self.assertEqual((home / "first").stat().st_mtime_ns, fixtures.MTIME_NS)
            with self.assertRaises(FileExistsError):
                fixtures.generate("empty", home / "first")

    def test_cell_membership_has_exact_empty_and_base_file_recipes(self):
        self.assertEqual(len(fixtures.CELL_RECIPES), 12)
        self.assertEqual([c for c, r in fixtures.CELL_RECIPES.items() if r == "big64m"], ["C09", "C10", "C11"])
        self.assertEqual(fixtures.BIG_BYTES, 67_108_864)

    def test_clone_checks_exact_sealed_bytes_and_retains_a_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "clone"
            prepared = {"master_volume": "new-master", "provision": {"store_sha256": "a" * 64}}
            calls = []
            def command(argv, out, label, seconds, **options):
                calls.append((label, argv))
                path = Path(out) / (label + ".stdout")
                path.write_text("b" * 64 + " /source/global/store.sqlite\n" + "b" * 64 + " /dest/global/store.sqlite\n")
                return {"stdout": str(path), "status": "PASS"}
            with patch.object(fixtures.receipts, "command", side_effect=command):
                with self.assertRaisesRegex(ValueError, "clone differs"):
                    fixtures.clone(prepared, folder, {"socket": "/socket"})
            self.assertFalse(any(label == "copy-remove-passing" for label, _ in calls))
            self.assertTrue((folder / "resource-claim.json").is_file())
            copy = next(argv for label, argv in calls if label == "copy-create")
            self.assertIn("new-master:/source:ro", copy)
            self.assertIn("--reflink=never", copy[-1])
            self.assertIn("--sparse=never", copy[-1])

    def test_helper_seal_matches_every_actual_copied_file(self):
        with tempfile.TemporaryDirectory() as directory:
            result = fixtures.assets(Path(directory) / "code")
            for relative, digest in result["files"].items():
                self.assertEqual(fixtures.identity.sha256(Path(result["root"]) / relative), digest)
            self.assertIn("engine/oracle.py", result["files"])
            self.assertIn("cells/git_index_oracle.py", result["files"])
            self.assertIn("cache/residency.py", result["files"])


class RecipeHistory(IsolatedInputs):
    def case(self, schema, count, selected, mixed=False):
        case = {"id": "original-case", "v016_case": "original-case", "fixture": {"recipe": "original-case", "profile": "mock-history", "seed": 1},
                "history_schedule": {"schema": schema, "commits": count, "verification_steps": selected}}
        if mixed:
            case["m1_schedule"] = {"tier": "L100"}
        return case

    def native_commands(self, calls):
        def command(argv, folder, label, seconds, **options):
            calls.append((argv, label, seconds))
            self.assertLessEqual(seconds, 120)
            mode, case = argv[1:3]
            if mode == "m1-scope":
                output = Path(folder) / (label + ".stdout")
                output.write_text("original-m1-selective-scope-v1\npath\tkind\tlength\tmode\tmtime_seconds\tmtime_nanoseconds\tranges\ttarget\n")
                return {"argv": argv, "stdout": str(output), "status": "PASS", "exit_code": 0}
            if mode == "prepare-sdk-step":
                step, root = int(argv[3]), Path(argv[4])
                root.mkdir()
                body = f"original-sdk-step-payloads-v1\ncase\t{case}\nstep\t{step}\nmembers\t2\n"
                for member in range(1, 3):
                    payload = bytes([member]) * 4
                    name = f"member-{member}.bin"
                    (root / name).write_bytes(payload)
                    body += f"{member}\tdata/member-{member}\t0\t0\t1\t5\t4\t{hashlib.sha256(payload).hexdigest()}\t640\t1700000000\t0\t{name}\n"
                (root / "descriptor.tsv").write_text(body)
                output = Path(folder) / (label + ".stdout")
                output.write_text(json.dumps({"case": case, "step": step, "members": 2,
                    "descriptor_sha256": hashlib.sha256(body.encode()).hexdigest()}))
                return {"argv": argv, "stdout": str(output), "status": "PASS", "exit_code": 0}
            step = 0 if mode == "fixture" else int(argv[3])
            root = Path(argv[3] if mode == "fixture" else argv[4])
            body = f"workspace-independent-manifest-v1\nstate-{step}\n"
            digest = hashlib.sha256(body.encode()).hexdigest()
            if mode in ("fixture", "expected-step"):
                root.mkdir()
                (root / "independent-native-state").write_text(str(step))
                root.with_suffix(".manifest.tsv").write_text(body)
            elif mode == "verify-step":
                self.assertEqual((root / "independent-native-state").read_text(), str(step))
            else:
                self.fail("unexpected native operator " + mode)
            record = {"case": case, "seed": 1, "files": 1, "entries": 2, "logical_bytes": step + 1,
                      "fixture_digest": digest, "recipe_identity": "r" * 64}
            if mode != "fixture":
                record["step"] = step
            if mode == "verify-step":
                record["verification_status"] = "pass"
            output = Path(folder) / (label + ".stdout")
            output.write_text(json.dumps(record))
            return {"argv": argv, "stdout": str(output), "status": "PASS", "exit_code": 0}
        return command

    def build(self, root):
        fixtures.prepared_inputs.CACHE = root / "shared-input-cache"
        binaries = {}
        for name in ("namespace-writer", "workspace-writer", "workload-host", "workspace-linux", "workload-linux", "edit-linux", "edit-host"):
            path = root / name
            path.write_text(name)
            binaries[name] = {"path": str(path), "sha256": fixtures.identity.sha256(path)}
        return {"binaries": binaries, "flags": "mock fixture tools", "explicit_rustflags": None}

    def test_five_hundred_commits_materialize_only_original_selected_states(self):
        selected = [0, 1, 199, 200, 201, 250, 499, 500]
        case = self.case("original-dedup-history-sequence-v1", 500, selected)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            build = self.build(folder)
            calls = []
            with patch.object(fixtures.receipts, "command", side_effect=self.native_commands(calls)):
                initial, final, native, history, original = fixtures.prepare_recipe_history(case, folder, build)
            self.assertIsNone(original)
            self.assertEqual([state["index"] for state in history], selected)
            self.assertEqual([int(argv[3]) for argv, _, _ in calls if argv[1] == "expected-step"], selected[1:])
            self.assertEqual(set(native), {f"state-{step}" for step in selected})
            self.assertEqual((initial["logical_bytes"], final["logical_bytes"]), (1, 501))
            for state in history:
                self.assertEqual(fixtures.identity.sha256(state["manifest"]), state["manifest_sha256"])
                self.assertEqual(state["native_recipe"]["binary_sha256"], build["binaries"]["workspace-writer"]["sha256"])
                self.assertTrue(Path(state["native_root"]).is_dir(), "non-M1 consumers keep their native roots")
            self.assertFalse((folder / "native-states/state-2").exists())

    def test_m1_regular_and_exhaustive_keep_materialization_separate_from_observed_modes(self):
        for selected in ([100], list(range(5, 101, 5))):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                build = self.build(folder)
                case = self.case("original-m1-commit-sequence-v1", 100, selected, mixed=True)
                calls = []
                with patch.object(fixtures.receipts, "command", side_effect=self.native_commands(calls)):
                    _, _, native, history, _ = fixtures.prepare_recipe_history(case, folder, build)
                self.assertEqual([state["index"] for state in history], selected)
                self.assertEqual([int(argv[3]) for argv, _, _ in calls if argv[1] == "expected-step"], selected)
                self.assertEqual(set(native), {"state-0"})
                self.assertFalse((folder / "history-manifests/state-0.tsv").exists())
                for state in history:
                    self.assertEqual(state["verification_scope"], "original-m1-selective-scope-v1")
                    self.assertIn("actual proof requires measured helper modes", state["materialization_metadata"])
                    self.assertTrue(Path(state["manifest"]).read_text().startswith("original-m1-selective-scope-v1\n"))
                    self.assertNotEqual(state["manifest_sha256"], state["native_manifest_sha256"])
                    self.assertEqual(state["scope_recipe"]["binary_sha256"], build["binaries"]["edit-host"]["sha256"])

    def test_m1_checkpoint_payloads_are_released_before_preparation_is_sealed(self):
        outcomes=[]
        for count in (10,20):
            selected=list(range(5,count+1,5))
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary); build=self.build(folder)
                case=self.case("original-m1-commit-sequence-v1",count,selected,mixed=True)
                calls=[]; peaks=[]; native_command=self.native_commands(calls)
                def authored(argv, out, label, seconds, **options):
                    result=native_command(argv,out,label,seconds,**options)
                    if argv[1]=="expected-step":
                        peaks.append(len(list(folder.rglob("independent-native-state"))))
                    return result
                with patch.object(fixtures.receipts,"command",side_effect=authored):
                    initial,final,native,history,_=fixtures.prepare_recipe_history(case,folder,build)
                self.assertEqual((initial["logical_bytes"],final["logical_bytes"]),(1,count+1))
                self.assertEqual(set(native),{"state-0"})
                self.assertEqual([state["index"] for state in history],selected)
                for state in history:
                    self.assertEqual(fixtures.identity.sha256(state["manifest"]),state["manifest_sha256"])
                    self.assertEqual(fixtures.identity.sha256(state["native_manifest"]),state["native_manifest_sha256"])
                    self.assertEqual(state["native_recipe"]["binary_sha256"],build["binaries"]["workspace-writer"]["sha256"])
                    self.assertEqual(state["scope_recipe"]["binary_sha256"],build["binaries"]["edit-host"]["sha256"])
                    self.assertEqual(state["verification_scope"],"original-m1-selective-scope-v1")
                recipes=json.loads((folder/"history-native-recipes.json").read_text())
                self.assertEqual(recipes["states"],history)
                fixtures.receipts.manifest(folder)
                sealed=fixtures.receipts.verify_manifest(folder)
                payload_entries=[name for name in sealed["files"] if name.endswith("independent-native-state")]
                retained=len(list(folder.rglob("independent-native-state")))
                outcomes.append((count,retained,max(peaks),payload_entries))
                self.assertEqual(len(payload_entries), 1)
                self.assertTrue(payload_entries[0].endswith("/source/independent-native-state"))
                self.assertIn("history-native-recipes.json",sealed["files"])
                for step in selected:
                    self.assertIn(f"history-manifests/state-{step}.tsv",sealed["files"])
        for count,retained,peak,payload_entries in outcomes:
            print(json.dumps({"selected_checkpoints":count//5,"retained_payload_roots":retained,"peak_payload_roots":peak,"sealed_payload_entries":len(payload_entries)}))
            with self.subTest(selected_checkpoints=count//5):
                self.assertEqual(retained,1,f"{count//5} generated checkpoints must leave only the pristine source")
                self.assertEqual(peak,2,"source plus one currently-generated checkpoint is the peak")
                self.assertEqual(len(payload_entries), 1)
                self.assertTrue(payload_entries[0].endswith("/source/independent-native-state"))

    def test_m1_checkpoint_cleanup_refuses_foreign_or_existing_outputs(self):
        for variant in ("existing","symlink"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                base=Path(temporary); folder=base/"prepared"; folder.mkdir()
                foreign=base/"foreign"; foreign.mkdir(); (foreign/"keep").write_text("untouched")
                build=self.build(folder); case=self.case("original-m1-commit-sequence-v1",5,[5],mixed=True)
                calls=[]; command=self.native_commands(calls); target=folder/"expected-native"
                if variant=="existing":
                    target.mkdir(); (target/"keep").write_text("pre-existing")
                def author(argv,out,label,seconds,**options):
                    result=command(argv,out,label,seconds,**options)
                    if variant=="symlink" and argv[1]=="expected-step":
                        fixtures.shutil.rmtree(Path(argv[4]))
                        Path(argv[4]).symlink_to(foreign,target_is_directory=True)
                    return result
                with patch.object(fixtures.receipts,"command",side_effect=author):
                    with self.assertRaises(FileExistsError if variant=="existing" else ValueError):
                        fixtures.prepare_recipe_history(case,folder,build)
                self.assertEqual((foreign/"keep").read_text(),"untouched")
                self.assertTrue((fixtures.prepared_inputs.source_path(case, build)/"independent-native-state").is_file())
                self.assertFalse((folder/"history-native-recipes.json").exists())
                if variant=="existing":
                    self.assertEqual((target/"keep").read_text(),"pre-existing")
                    self.assertFalse(any(argv[1]=="expected-step" for argv,_,_ in calls))
                else:
                    self.assertTrue(target.is_symlink())

    def test_m1_cleanup_failure_keeps_original_error_and_does_not_publish_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary); build=self.build(folder)
            case=self.case("original-m1-commit-sequence-v1",5,[5],mixed=True); calls=[]
            with patch.object(fixtures.receipts,"command",side_effect=self.native_commands(calls)), \
                    patch.object(fixtures.shutil,"rmtree",side_effect=OSError("original checkpoint cleanup refusal")) as remove:
                with self.assertRaisesRegex(OSError,"original checkpoint cleanup refusal"):
                    fixtures.prepare_recipe_history(case,folder,build)
                remove.assert_called_once_with(folder/"expected-native")
            self.assertTrue((folder/"expected-native/independent-native-state").is_file())
            self.assertTrue((folder/"expected-native.manifest.tsv").is_file())
            self.assertTrue((folder/"history-manifests/state-5.tsv").is_file())
            self.assertFalse((folder/"history-native-recipes.json").exists())

    def test_m1_invalid_full_manifest_is_not_cleaned_or_admitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary); build=self.build(folder)
            case=self.case("original-m1-commit-sequence-v1",5,[5],mixed=True)
            command=self.native_commands([])
            def corrupted(argv,out,label,seconds,**options):
                result=command(argv,out,label,seconds,**options)
                if argv[1]=="expected-step":
                    Path(argv[4]).with_suffix(".manifest.tsv").write_text("original mismatch retained")
                return result
            with patch.object(fixtures.receipts,"command",side_effect=corrupted), \
                    patch.object(fixtures.shutil,"rmtree",wraps=fixtures.shutil.rmtree) as remove:
                with self.assertRaisesRegex(ValueError,"manifest identity differs"):
                    fixtures.prepare_recipe_history(case,folder,build)
                remove.assert_not_called()
            self.assertTrue((folder/"expected-native/independent-native-state").is_file())
            self.assertFalse((folder/"history-native-recipes.json").exists())

    def test_invalid_checkpoint_scope_refuses_before_native_authoring(self):
        cases = [self.case("unknown", 2, [0, 2]),
                 self.case("original-v016-boundary-sequence-v1", 2, [0, 2]),
                 self.case("original-dedup-history-sequence-v1", 500, [0, 1, 1, 500]),
                 self.case("original-dedup-history-sequence-v1", 500, [0, True, 500]),
                 self.case("original-dedup-history-sequence-v1", 500, [0, 499]),
                 self.case("original-m1-commit-sequence-v1", 100, [0, 100], mixed=True),
                 self.case("original-m1-commit-sequence-v1", 100, [7, 100], mixed=True)]
        with patch.object(fixtures.receipts, "command") as command:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    fixtures.prepare_recipe_history(case, Path("never-authored"), {})
        command.assert_not_called()

    def test_manifest_digest_mismatch_is_retained_and_never_admitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            build = self.build(folder)
            case = self.case("original-v016-boundary-sequence-v1", 2, [0, 1, 2])
            calls = []
            original = self.native_commands(calls)
            def corrupt(argv, out, label, seconds, **options):
                receipt = original(argv, out, label, seconds, **options)
                if argv[1] == "expected-step":
                    Path(argv[4]).with_suffix(".manifest.tsv").write_text("damaged retained expectation")
                return receipt
            with patch.object(fixtures.receipts, "command", side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, "manifest identity differs"):
                    fixtures.prepare_recipe_history(case, folder, build)
            self.assertTrue((folder / "native-states/state-1.manifest.tsv").exists())
            self.assertFalse((folder / "history-native-recipes.json").exists())

    def test_m1_stages_exact_linux_recipe_and_only_selected_manifest_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            build = self.build(base)
            repo = base / "repository"
            shell = repo / "benchmark/fs-bench-pro/families/mixed_load_bearing/workload.sh"
            shell.parent.mkdir(parents=True)
            shell.write_text("original helper wrapper\n")
            folder = base / "prepared"
            case = self.case("original-m1-commit-sequence-v1", 100, [100], mixed=True)
            case["fixture"] = {"recipe": case["id"]}
            case["ordinary_sdk_edits"] = True
            case["steps"] = [{"run": f"workload.sh stage original-case {step}"} for step in range(1, 101)]
            calls = []
            def assets(path):
                path.mkdir()
                return {"root": str(path), "files": {}, "sha256": ""}
            reused = {"master_volume": "sealed-m1-master", "provision": {"store_sha256": "sealed"}}
            with patch.object(fixtures.identity, "ROOT", repo), \
                    patch.object(fixtures.identity, "load_build", return_value=build), \
                    patch.object(fixtures.identity, "source_identity", return_value={"product_tree": "same", "files": {}}), \
                    patch.object(fixtures, "family_case", return_value=({"family": "mixed_load_bearing"}, case)), \
                    patch.object(fixtures, "assets", side_effect=assets), \
                    patch.object(fixtures, "compatible_master", return_value=(reused, {"scope": "closed independent input"})), \
                    patch.object(fixtures.receipts, "command", side_effect=self.native_commands(calls)):
                prepared = fixtures.prepare_workspace(case["id"], folder, "sealed-build")
            files = prepared["helpers"]["files"]
            self.assertEqual(files["writers/recipe"], build["binaries"]["workspace-linux"]["sha256"])
            self.assertEqual(set(path for path in files if path.startswith("history/manifests/")),
                             {"history/manifests/state-100.tsv"})
            self.assertIn("history/native-recipes.json", files)
            self.assertEqual([state["index"] for state in prepared["sdk_steps"]], list(range(2, 100, 5)))
            self.assertEqual(set(prepared["prepared_step_runs"]), {str(step) for step in range(2, 100, 5)})
            for record in prepared["sdk_steps"]:
                self.assertEqual(record["argv"][1], "apply-sdk-step-prepared")
                self.assertEqual(record["argv"][5], record["descriptor_sha256"])
                self.assertEqual(len(record["member_argv"]), 2)
                script = Path(prepared["helpers"]["root"]) / record["prepared_run"]
                self.assertIn("exec /bin/bash /code/" + record["original_run"], script.read_text())
                self.assertEqual(files[record["prepared_run"]], fixtures.identity.sha256(script))
            self.assertEqual(prepared["master_volume"], "sealed-m1-master")
            self.assertIn("actual scoped proof binds measured helper observations", prepared["setup"])

    def test_payload_corruption_refuses_preparation_before_adapter_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            build = self.build(folder)
            case = self.case("original-v016-boundary-sequence-v1", 2, [0, 1, 2])
            case["ordinary_sdk_edits"] = True
            case["steps"] = [{"run": f"workload.sh apply original-case {step}"} for step in (1, 2)]
            calls = []
            original = self.native_commands(calls)
            def corrupt(argv, out, label, seconds, **options):
                receipt = original(argv, out, label, seconds, **options)
                (Path(argv[4]) / "member-1.bin").write_bytes(b"wrong")
                return receipt
            with patch.object(fixtures.receipts, "command", side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, "payload length/hash differs"):
                    fixtures.prepare_sdk_payloads(case, folder, build)
            self.assertTrue((folder / "sdk-payloads/step-1/descriptor.tsv").exists())
            self.assertFalse((folder / "sdk-payloads.json").exists())


class RuntimeHelperAdmission(unittest.TestCase):
    case = RecipeHistory.case
    native_commands = RecipeHistory.native_commands
    build = RecipeHistory.build
    def admission(self, folder, *, mixed=False, kind="boundary", sdk=True):
        schema = "original-m1-commit-sequence-v1" if mixed else "original-v016-boundary-sequence-v1"
        count = 10 if mixed else 2
        case = self.case(schema, count, [count] if mixed else list(range(count+1)), mixed=mixed)
        case["ordinary_sdk_edits"] = sdk
        case["registry"] = {"family":"mixed_load_bearing" if mixed else "file_size_transition", "kind":kind}
        case["steps"] = [{"run":f"workload.sh {'stage' if mixed else 'apply'} original-case {step}"} for step in range(1,count+1)]
        build = self.build(folder)
        with patch.object(fixtures.receipts, "command", side_effect=self.native_commands([])):
            records = fixtures.prepare_sdk_payloads(case, folder, build)
        root = folder / "code"
        root.mkdir()
        files = {}
        def install(origin, relative):
            target = root / relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(origin,target)
            files[relative] = fixtures.identity.sha256(target)
        for name, relative in (("workload-linux","writers/workload"),("edit-linux","writers/edit")):
            install(build["binaries"][name]["path"],relative)
        if mixed:
            install(build["binaries"]["workspace-linux"]["path"],"writers/recipe")
        for record in records:
            base = f"history/payloads/step-{record['index']}"
            install(record["descriptor"],base+"/descriptor.tsv")
            for name in record["payloads"]:
                install(Path(record["descriptor"]).parent/name,base+"/"+name)
            script = root / record["prepared_run"]
            script.parent.mkdir(parents=True,exist_ok=True)
            script.write_text(fixtures.sdk_step_script(record))
            files[record["prepared_run"]] = fixtures.identity.sha256(script)
        prepared = {"helpers":{"root":str(root),"files":files},"sdk_steps":records,
                    "prepared_step_runs":{str(record["index"]):record["prepared_run"] for record in records}}
        return case,prepared,build

    def test_missing_partial_or_fabricated_sdk_map_is_refused_before_native_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            case,prepared,build = self.admission(Path(temporary))
            for variant in ("missing","partial","extra","record-missing","record-order"):
                bad = copy.deepcopy(prepared)
                if variant == "missing": bad.pop("prepared_step_runs")
                elif variant == "partial": bad["prepared_step_runs"].pop("2")
                elif variant == "extra": bad["prepared_step_runs"]["3"]="fabricated.sh"
                elif variant == "record-missing": bad["sdk_steps"].pop()
                else: bad["sdk_steps"].reverse()
                with self.subTest(variant=variant), self.assertRaisesRegex(ValueError,"exact original prepared SDK step indices"):
                    fixtures.validate_runtime_helpers(case,bad,build)

    def test_stale_binary_source_script_and_payload_seals_are_refused(self):
        for variant in ("workload","edit","recipe","generator","script","payload","argv"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                case,prepared,build = self.admission(Path(temporary),mixed=True)
                root = Path(prepared["helpers"]["root"])
                if variant in ("workload","edit","recipe"):
                    relative="writers/"+variant
                    (root/relative).write_text("validly sealed stale binary")
                    prepared["helpers"]["files"][relative]=fixtures.identity.sha256(root/relative)
                elif variant == "generator":
                    prepared["sdk_steps"][0]["generator"]["binary_sha256"]="0"*64
                elif variant == "script":
                    record=prepared["sdk_steps"][0]
                    (root/record["prepared_run"]).write_text("exec /code/writers/edit apply-sdk-step original-case 2\n")
                    prepared["helpers"]["files"][record["prepared_run"]]=fixtures.identity.sha256(root/record["prepared_run"])
                elif variant == "payload":
                    relative="history/payloads/step-2/member-1.bin"
                    (root/relative).write_bytes(b"bad!")
                    prepared["helpers"]["files"][relative]=fixtures.identity.sha256(root/relative)
                else:
                    prepared["sdk_steps"][0]["argv"][-1]="0"*64
                with patch.object(fixtures.receipts,"command") as mutation, self.assertRaises(ValueError):
                    fixtures.validate_runtime_helpers(case,prepared,build)
                mutation.assert_not_called()

    def test_original_m1_hn_and_native_non_sdk_selection_is_preserved(self):
        for mixed,kind,sdk,expected in ((True,"v016-m1-sequential",True,[2,7]),
                                         (False,"namespace-inode",True,[2]),
                                         (False,"metadata",False,[]),
                                         (False,"unrelated",False,[]),
                                         (False,"boundary",False,[])):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                case,prepared,build = self.admission(Path(temporary),mixed=mixed,kind=kind,sdk=sdk)
                before = {str(path):fixtures.identity.sha256(path) for path in Path(temporary).rglob("*") if path.is_file()}
                with patch.object(fixtures.receipts,"command") as mutation:
                    accepted = fixtures.validate_runtime_helpers(case,prepared,build)
                mutation.assert_not_called()
                self.assertEqual(accepted["sdk_step_indices"],expected)
                self.assertEqual(before,{str(path):fixtures.identity.sha256(path) for path in Path(temporary).rglob("*") if path.is_file()})
                if not sdk:
                    bad=copy.deepcopy(prepared)
                    bad["prepared_step_runs"]={"1":"fabricated-p3.sh"}
                    with self.assertRaises(ValueError):fixtures.validate_runtime_helpers(case,bad,build)
