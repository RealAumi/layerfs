"""Source-only parity dispatch; tools are mocked and no native reader executes."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, identity, project, receipts


class BatchFiveParity(unittest.TestCase):
    def review(self, root, case):
        source = root / "reviewed.rs"
        source.write_text("external source pin, not a product/native fixture\n")
        case.update(fixture={"recipe": case["id"]}, oracle={"scope": "unchanged original selected scope"},
                    differences=[{"scope": "declared current route"}],
                    port_review={"source_commit": "commit", "source_tag_object": "tag",
                                 "files": {"reviewed.rs": identity.sha256(source)}})
        return case

    def context(self, root, *, m1=True, topology=False, name="case"):
        case = {"id": name, "v016_case": name}
        count = 5 if m1 else 1
        if topology:
            roles = ["0", "1"]
            case["topology_schedule"] = {"schema": "original-v016-m1-topology-v1", "per_worker_commits": count,
                "workers": [{"index": 0}, {"index": 1}], "total_commits": count * 2,
                "verification_steps_by_worker": {role: [count] for role in roles}}
            case["steps"] = [{"index": index, "run": f"workload.sh stage {name} {index}", "commit": True,
                              "ordinary_edit_members": 2 if index % 5 == 2 else 0} for index in range(1, count + 1)]
        else:
            roles = ["trunk", "a"]
            case["branch_schedule"] = {"schema": "original-branch-development-v1",
                "branches": [{"role": role, "local_commits": count} for role in roles],
                "payload_checkpoints": [{"role": role, "local_index": count} for role in roles]}
            case["steps"] = [{"role": role, "local_index": index, "run": f"workload.sh stage {name} {role} {index}",
                              "commit": True, "ordinary_edit_members": (2 if index % 5 == 2 else 0) if m1 else 1}
                             for role in roles for index in range(1, count + 1)]
        if m1:
            case["m1_schedule"] = {"tier": "L100"}
        self.review(root, case)
        plan = fixtures.context_plan(case)
        binding = {"case_definition_sha256": plan["case_definition_sha256"], "model_files": {"model": "sealed"}}
        states = [{"role": role, "index": count, "summary": {"role": role, "step": count, "recipe_sha256": "a" * 64},
                   "native_manifest_sha256": "b" * 64, "manifest_sha256": "c" * 64,
                   "verification_scope": "original-m1-selective-scope-v1" if m1 else "complete-original-native-state",
                   "materialization_metadata": "None mode observations; selected M1 automatic fields are placeholders, not proof"
                       if m1 else "original full compact state"} for role in roles]
        native = {"original-context-initial-check": {"verification_status": "pass"}}
        if not m1:
            native.update({f"original-context-{role}-{count}-check": {"verification_status": "pass"} for role in roles})
        sdk = [{**row, "prepared_run": f"context/{row['role']}/steps/step-{row['index']}.sh",
                "descriptor_sha256": "d" * 64, "generator": {"binary_sha256": "e" * 64}}
               for row in plan["sdk_steps"]]
        prepared = {"schema": fixtures.CONTEXT_PREPARED_SCHEMA, "context_binding": binding,
                    "context_roles": fixtures.context_role_records(case, plan), "context_checkpoints": states,
                    "context_initial_recipe": {"source_binding": binding}, "sdk_context_steps": sdk,
                    "native_verification": native, "expectation": {state["role"]: state["summary"] for state in states}}
        prepared["context_native_metadata"] = {"schema": "fs-bench-pro-original-context-native-recipes-v1", "case": name,
            "context_binding": binding, "initial_recipe": prepared["context_initial_recipe"],
            "context_roles": prepared["context_roles"], "states": states, "performance_samples": 0}
        family = "multi_workspace_development" if topology else "branch_development"
        self.seal(root, family, case, prepared)
        return {"family": family, "cases": [case]}, prepared

    def seal(self, root, family, case, prepared):
        folder = root / "prepared" / case["id"]
        folder.mkdir(parents=True, exist_ok=True)
        store, manifest = folder / "store", folder / "installed.manifest"
        store.write_bytes(b"external mocked Store bytes; never opened as SQLite")
        manifest.write_bytes(b"external mocked original manifest")
        prepared.update(status="PASS", case=case["id"], family=family, recipe=case["fixture"]["recipe"],
                        fixture={"files": 1, "logical_bytes": 1},
                        provision={"sealed_store": str(store), "store_sha256": identity.sha256(store),
                                   "manifest": str(manifest), "manifest_sha256": identity.sha256(manifest)},
                        helpers=prepared.get("helpers", {"root": str(folder), "files": {}}))
        for name in ("prepared.json", "manifest.json"):
            (folder / name).unlink(missing_ok=True)
        receipts.write_new(folder / "prepared.json", prepared)
        receipts.manifest(folder)

    def parity(self, root, family, *, build="sealed-build", admission=None, build_error=None, build_record=None):
        catalogue = [{"family": family["family"], "case": case["v016_case"]} for case in family["cases"]]
        def git(_root, *arguments):
            return "commit" if arguments[-1].endswith("^{commit}") else "tag"
        with patch.object(identity, "ROOT", root), patch.object(identity, "reference_catalogue", return_value=catalogue), \
                patch.object(identity, "git", side_effect=git), \
                patch.object(identity, "load_build", side_effect=build_error, return_value=build_record or {"sealed": "current"}) as loaded, \
                patch.object(fixtures, "validate_runtime_helpers", side_effect=admission,
                             return_value={"status": "PASS", "scope": "mocked source-only helper admission"}) as validated, \
                patch.object(receipts, "command", side_effect=AssertionError("parity must not execute a reader/native tool")):
            result = project.parity_workspace(family, root / "prepared", root / "parity", build_folder=build)
        return result, loaded, validated

    def failed(self, root, family, **options):
        with self.assertRaises(project.ParityFailure) as raised:
            self.parity(root, family, **options)
        result = json.loads((root / "parity/parity.json").read_text())
        self.assertEqual(raised.exception.result, result)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["samples"], 0)
        self.assertEqual([row["case"] for row in result["cases"]], [case["id"] for case in family["cases"]])
        receipts.verify_manifest(root / "parity")
        return result

    def test_m1_checkpoints_are_recipe_evidence_without_actual_modes_or_final_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); family, prepared = self.context(root)
            result, loaded, validated = self.parity(root, family)
            witness = result["cases"][0]["mechanical"]
            self.assertEqual(witness["selected_native_verification"], {})
            self.assertEqual(witness["initial_native_verification"]["verification_status"], "pass")
            self.assertEqual(witness["plan"], fixtures.context_plan(family["cases"][0]))
            self.assertEqual(witness["actual_created_modes"], prepared["context_roles"])
            self.assertTrue(all(row["actual_created_modes"] == "NOT_OBSERVED_IN_PREPARATION"
                                and row["measured_proof_status"] == "NOT_RUN"
                                and row["qualification_scope"] == "recipe/source and selective scope only"
                                for row in witness["checkpoint_witnesses"]))
            self.assertNotIn("full deterministic native fixture/final", result["scope"])
            loaded.assert_called_once_with("sealed-build")
            validated.assert_called_once()
            receipts.verify_manifest(root / "parity")

    def test_compact_checkpoints_require_every_selected_complete_native_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); family, _ = self.context(root, m1=False)
            result, _, _ = self.parity(root, family)
            witness = result["cases"][0]["mechanical"]
            self.assertEqual(len(witness["selected_native_verification"]), 2)
            self.assertTrue(all(row["qualification_scope"] == "complete original native state"
                                and row["measured_proof_status"] == "NOT_RUN" for row in witness["checkpoint_witnesses"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); family, prepared = self.context(root, m1=False)
            prepared["native_verification"].pop("original-context-a-1-check")
            self.seal(root, family["family"], family["cases"][0], prepared)
            self.assertIn("native verification scope", self.failed(root, family)["cases"][0]["reason"])

    def test_multi_worker_roles_and_exact_local_sdk_member_plan_remain_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); family, prepared = self.context(root, topology=True)
            result, _, validated = self.parity(root, family)
            witness = result["cases"][0]["mechanical"]
            self.assertEqual(witness["plan"]["roles"], ["0", "1"])
            self.assertEqual([(row["role"], row["local"], row["members"]) for row in witness["sdk_descriptor_witnesses"]],
                             [("0", 2, 2), ("1", 2, 2)])
            self.assertEqual(witness["actual_created_modes"], prepared["context_roles"])
            validated.assert_called_once()

    def test_unqualified_or_changed_helpers_and_missing_build_cannot_bypass_admission(self):
        variants = ({"build": None}, {"build_error": ValueError("changed compiled source")},
                    {"admission": ValueError("missing SDK map or stale binary/descriptor/payload seal")},
                    {"admission": lambda *args: {"status": "NOT_APPLICABLE"}})
        for options in variants:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); family, _ = self.context(root)
                result = self.failed(root, family, **options)
                self.assertEqual(result["cases"][0]["status"], "FAIL")

    def test_m1_fake_full_verifier_and_weakened_recipe_witness_are_not_accepted(self):
        for kind in ("fabricated-final-pass", "placeholder-scope", "false-samples", "expectation"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); family, prepared = self.context(root)
                if kind == "fabricated-final-pass":
                    prepared["native_verification"]["original-context-a-5-check"] = {"verification_status": "pass"}
                elif kind == "placeholder-scope":
                    prepared["context_checkpoints"][0]["verification_scope"] = "complete-original-native-state"
                elif kind == "false-samples":
                    prepared["context_native_metadata"]["performance_samples"] = False
                else:
                    prepared["expectation"]["a"] = {"recipe_sha256": "changed"}
                self.seal(root, family["family"], family["cases"][0], prepared)
                self.failed(root, family)

    def test_actual_context_admission_rejects_authenticated_stale_linux_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); family, prepared = self.context(root)
            for relative in fixtures.CONTEXT_SOURCE_FILES:
                path = root / relative; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("external frozen contextual source: " + relative)
            prepared["context_binding"]["model_files"] = {relative: identity.sha256(root / relative)
                                                          for relative in fixtures.CONTEXT_SOURCE_FILES}
            code = root / "code"; (code / "writers").mkdir(parents=True)
            stale = code / "writers/workload"; stale.write_text("authenticated stale helper")
            expected = root / "workload-linux"; expected.write_text("current sealed helper")
            prepared["helpers"] = {"root": str(code), "files": {"writers/workload": identity.sha256(stale)}}
            self.seal(root, family["family"], family["cases"][0], prepared)
            build = {"binaries": {"workload-linux": {"path": str(expected), "sha256": identity.sha256(expected)}}}
            actual_validator = fixtures.validate_runtime_helpers
            result = self.failed(root, family, admission=actual_validator, build_record=build)
            self.assertEqual(result["cases"][0]["reason"], "current contextual helper seal differs: writers/workload")

    def historical(self, root, position):
        case = copy.deepcopy(json.loads((BENCH / "families/historical_access/family.json").read_text())["cases"][position])
        name = case["id"]
        review = self.review(root, {"id": name, "v016_case": name})
        case.update({key: review[key] for key in ("port_review", "oracle", "differences")})
        count = case["historical_access"]["producer_schedule"]["created_commit_acknowledgements"]
        role = case["historical_access"]["producer_branch_role"].lower()
        selected = {"original_source_role": case["historical_access"]["producer_branch_role"], "source_role": role,
                    "local": case["historical_access"]["selected_ordinal"], "acknowledged_commit": {"commit_id": "selected"},
                    "manifest_sha256": "f" * 64, "read_targets": [{**row, "sha256": hashlib.sha256(row["path"].encode()).hexdigest()}
                                                                  for row in case["historical_access"]["reads"]],
                    "absent": case["historical_access"]["absent"]}
        proof = {"verification_status": "pass", "scope": "mocked native selected full-state proof"}
        selected["native_verification"] = proof
        acks = [{"commit_id": f"external-tuple-{index % 15 if count == 30 else index}"} for index in range(count)]
        prepared = {"schema": fixtures.HISTORICAL_PREPARED_SCHEMA, "native_verification": {"historical_selected": proof},
                    "expectation": {"selected": name}, "historical_selection": selected,
                    "producer_dependency": {"source_binding": {"source": "mocked"}},
                    "closed_producer": {"source_commit": "setup-source", "receipt_sha256": "1" * 64,
                        "transcript_sha256": "2" * 64, "store_sha256": "3" * 64,
                        "custody": {"state": "KNOWN_STOP", "all_workspaces_gone": True}, "acknowledgements": acks}}
        self.seal(root, "historical_access", case, prepared)
        plan = {"producer_case": case["historical_access"]["producer"], "selected_local": selected["local"]}
        return {"family": "historical_access", "cases": [case]}, prepared, plan

    def test_historical_typed_ack_references_and_selected_bytes_are_not_reader_attempts(self):
        for position, count in ((0, 100), (4, 30), (5, 40)):
            with self.subTest(position=position), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); family, prepared, plan = self.historical(root, position)
                with patch.object(fixtures, "historical_plan", return_value=plan):
                    result, _, admitted = self.parity(root, family)
                witness = result["cases"][0]["mechanical"]
                producer = witness["closed_producer"]
                self.assertEqual(producer["acknowledgement_count"], count)
                self.assertEqual(producer["retained_root_references"], count + 1)
                self.assertEqual(producer["distinct_commit_tuples"], 15 if count == 30 else count)
                self.assertEqual(witness["selected"]["read_targets"], prepared["historical_selection"]["read_targets"])
                self.assertEqual((witness["reader_status"], witness["verifier_reader_status"], witness["measured_proof_status"]),
                                 ("NOT_RUN", "NOT_RUN", "NOT_RUN"))
                admitted.assert_called_once()

    def test_historical_closed_dependency_selection_and_payload_refusals_remain_failures(self):
        for reason in ("partial producer acknowledgements", "wrong selected role/local", "native read-target SHA differs", "unknown Stop"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); family, _, plan = self.historical(root, 0)
                with patch.object(fixtures, "historical_plan", return_value=plan):
                    result = self.failed(root, family, admission=ValueError(reason))
                self.assertEqual(result["cases"][0]["reason"], reason)

    def test_sealed_load_is_mandatory_and_failed_middle_case_retains_following_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); family, _ = self.context(root, name="case-0")
            for index in (1, 2):
                next_family, _ = self.context(root, name=f"case-{index}")
                family["cases"].extend(next_family["cases"])
            (root / "prepared/case-1/store").write_bytes(b"stale authenticating source")
            result = self.failed(root, family)
            self.assertEqual([row["status"] for row in result["cases"]], ["PASS", "FAIL", "PASS"])
            self.assertEqual(result["cases"][1]["reason"], "retained evidence changed: store")
            self.assertEqual(result["cases"][2]["mechanical"]["checkpoint_witnesses"][0]["measured_proof_status"], "NOT_RUN")
            before = (root / "parity/parity.json").read_bytes()
            with self.assertRaises(FileExistsError):
                self.parity(root, family)
            self.assertEqual((root / "parity/parity.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
