"""Frozen reuse geometry, ordinary write routes and storage proof obligations."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/dedup_workspace_reuse"
MIB = 1_048_576


class DedupWorkspaceReuse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((FAMILY / "family.json").read_text())["cases"]

    def test_five_kept_ids_and_separate_compact_fixed_base_controls(self):
        expected = [f"dedup-workspace-{kind}-100" for kind in ("exact", "local", "unique")]
        expected += ["dedup-workspace-unique-500", "dedup-workspace-unique-1-base128-v3"]
        self.assertEqual([row["id"] for row in self.rows], expected)
        self.assertEqual(len({row["id"] for row in self.rows}), 5)
        for row in self.rows:
            case = row["id"]
            self.assertEqual(row["v016_case"], case)
            self.assertEqual(row["status"], "ported")
            self.assertEqual(row["steps"], [{"run": f"workload.sh apply {case}",
                                            "commit": True, "expected_commit": "Committed"}])
            self.assertEqual(row["reference"]["row"], case)
            self.assertEqual(row["reference"]["release"], "0.1.5")
            self.assertEqual(row["expected_commit"], "Committed")

    def test_pristine_and_final_geometry_are_not_confused_with_added_bytes(self):
        for row in self.rows:
            tier = int(row["registry"]["tier"])
            base = tier if row["id"].endswith("-compact-v2") else 128
            fixture, plan = row["fixture"], row["reuse_schedule"]
            self.assertEqual((fixture["files"], fixture["base_files"], fixture["entries"],
                              fixture["directories_including_root"], fixture["logical_bytes"]),
                             (base, base, base + 3, 3, base * MIB))
            self.assertEqual((fixture["seed"], fixture["file_bytes"], fixture["file_mode"],
                              fixture["directory_mode"], fixture["mtime_seconds"], fixture["mtime_nanoseconds"]),
                             (1, MIB, 0o640, 0o750, 1700000000, 0))
            self.assertEqual((plan["addition_files"], plan["addition_logical_bytes"],
                              plan["final_files"], plan["final_entries"], plan["final_logical_bytes"]),
                             (tier, tier * MIB, base + tier, base + tier + 3, (base + tier) * MIB))
            if row["id"].endswith("-compact-v2"):
                self.assertLessEqual(plan["final_logical_bytes"], 50 * MIB)
                self.assertLessEqual(plan["final_files"], 1000)
            self.assertEqual(fixture["paths"], [".", "added", "base"])

    def test_native_full_file_writes_are_not_relabelled_as_sdk_splices(self):
        for row in self.rows:
            tier = int(row["registry"]["tier"])
            plan = row["reuse_schedule"]
            self.assertFalse(row["ordinary_sdk_edits"])
            self.assertEqual((plan["commits"], plan["native_apply_step"], plan["final_state_step"],
                              plan["sdk_edit_calls"]), (1, 0, 1, 0))
            self.assertEqual((plan["full_file_write_count"], plan["successful_write_bytes"],
                              plan["file_sync_count"], plan["directory_sync_count"]), (tier, tier * MIB, tier, 2))
            self.assertFalse(plan["cross_file_atomic_batch"])
            self.assertEqual(plan["native_syscalls"][0], "create_new added file")
            self.assertEqual(plan["native_syscalls"][2], "set file mode and explicit mtime after write")
            if row["registry"]["kind"] == "local":
                self.assertIn("64-byte XOR", plan["content"])
                self.assertIn("65536..983040", plan["content"])
            self.assertTrue(any("not SDK edits" in note for note in row["differences"]))

    def test_original_storage_guards_remain_profile_specific_and_complete(self):
        for row in self.rows:
            kind = row["registry"]["kind"]
            storage = row["oracle"]["storage"]
            self.assertTrue(storage["base_payload_ids_unique_across_occurrences"])
            for key in ("exact_addition_new_regular_payload_bytes_zero", "exact_ordered_mapping_equals_selected_base",
                        "exact_content_root_equals_selected_base"):
                self.assertEqual(storage[key], kind == "exact")
            for key in ("unique_addition_payload_ids_unique_across_occurrences",
                        "unique_addition_payload_ids_disjoint_from_base"):
                self.assertEqual(storage[key], kind == "unique")
            self.assertEqual(storage["local_addition_complete_mapping_identities_distinct"], kind == "local")
            self.assertEqual(row["oracle"]["roots"], [0, 1])
            self.assertEqual(row["reuse_schedule"]["verification_states"], [0, 1])
            self.assertIn("every payload byte", row["oracle"]["scope"])
            self.assertIn("structural reads only", row["reuse_schedule"]["initial_payload_attribution"])
            self.assertIn("NOT_RUN", row["port_review"]["shared_routes"])

    def test_original_budgets_resources_and_missing_cache_evidence_stay_explicit(self):
        for row in self.rows:
            self.assertEqual(row["budget"], {"command_ms": 15000, "performance_hard_watchdog_ms": 120000,
                "operation_watchdog_ms": 120000, "verifier_ms": 75000 if row["id"].endswith("-500") else 45000, "verification_hard_watchdog_ms": 89000 if row["id"].endswith("-500") else 59000,
                "cleanup_reserve_ms": 4000, "publication_guard_ms": 250})
            self.assertTrue(row["original_ordinary_guards"])
            self.assertEqual(row["resource_profile"], {"cpus": 2, "memory_bytes": 2 * 1024**3,
                "memory_swap_bytes": 2 * 1024**3, "pids_limit": 256, "main_store_limit_bytes": 4 * 1024**3,
                "oom_events_allowed": 0, "swap_bytes_allowed": 0})
            self.assertEqual(row["cache_class"], "B")
            self.assertIn("no warmup", row["cache_contract"]["scope"])
            self.assertIn("INELIGIBLE", row["cache_contract"]["numeric_result"])
            self.assertEqual(row["cache_contract"]["independent_own_write_pre_Commit_coldness"], "UNAVAILABLE")

    def test_review_pins_unchanged_frozen_source_and_posix_selector(self):
        for row in self.rows:
            review = row["port_review"]
            self.assertEqual(review["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
            for name, digest in review["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)
        source = (ROOT / "benchmark/fs-bench-pro/workload/dedup_workloads.rs").read_text()
        sdk = source.split("pub(crate) fn is_sdk", 1)[1].split("///", 1)[0]
        self.assertIn('case.family == "dedup_branch_history"', sdk)
        self.assertNotIn("dedup_workspace_reuse", sdk)
        reuse = source.split('"dedup_workspace_reuse" =>', 1)[1].split('"dedup_branch_history"', 1)[0]
        self.assertIn("if step != 0", reuse)
        self.assertIn('Entry::directory("added"), Entry::directory(".")', reuse)

    def test_shell_dispatches_all_original_cases_only_to_unchanged_native_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "writer"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            fake.chmod(0o755)
            env = {**os.environ, "WORKLOAD_WRITER": str(fake), "EDIT_WRITER": "/nonexistent/sdk-writer",
                   "SDK_STEP_DESCRIPTOR": "/unused/descriptor", "SDK_STEP_DESCRIPTOR_SHA256": "a" * 64}
            for row in self.rows:
                case = row["id"]
                for route, expected in (("apply", ["workspace-apply", case, "1", "0", "performance"]),
                                        ("verify", ["workspace-verify-tree", case, "1", "1"])):
                    result = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), route, case],
                                            env=env, capture_output=True, text=True, timeout=2, check=True)
                    self.assertEqual(result.stdout.splitlines(), expected)
            invalid = [("apply", "dedup-workspace-exact-1"), ("apply", "dedup-workspace-local-10"),
                       ("apply", "dedup-workspace-exact-10-base128-v3"), ("apply", "dedup-workspace-unique-200"),
                       ("verify", "unknown"), ("sdk-edit", self.rows[0]["id"]),
                       ("apply", self.rows[0]["id"], "1"), ("apply",)]
            for args in invalid:
                result = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), *args],
                                        env=env, capture_output=True, text=True, timeout=2)
                self.assertEqual(result.returncode, 2, args)


if __name__ == "__main__":
    unittest.main()
