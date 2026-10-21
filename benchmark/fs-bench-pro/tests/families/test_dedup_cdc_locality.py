"""The frozen directory-import topology, source contract and native-only wrapper."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/dedup_cdc_locality"
PROFILES = ("overwrite", "insert", "delete", "common-body", "scattered")
TIERS = (100,)
PERFORMANCE = [f"dedup-cdc-{profile}-{tier}" for profile in PROFILES for tier in TIERS]
PROOF = "dedup-cdc-boundaries-proof"


class CdcDirectoryImport(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FAMILY / "family.json").read_text())

    def test_complete_original_selection_and_single_fresh_import(self):
        self.assertEqual(self.document["engine"], "project")
        self.assertEqual([c["id"] for c in self.document["cases"]], PERFORMANCE + [PROOF])
        for row in self.document["cases"]:
            self.assertEqual(row["id"], row["v016_case"])
            self.assertEqual(row["status"], "ported")
            self.assertTrue(row["project_import"])
            schedule = row["import_schedule"]
            self.assertEqual(schedule["schema"], "original-dedup-directory-import-v1")
            self.assertEqual(schedule["operation"], "ProjectApi::init")
            self.assertEqual((schedule["imports"], schedule["genesis_commits"], schedule["mounted_mutations"]), (1, 0, 0))
            self.assertTrue(schedule["fresh_store"])
            self.assertTrue(schedule["source_only_preparation"])
            self.assertTrue(schedule["same_import_reused_by_independent_verifier"])
            self.assertEqual(len(row["steps"]), 1)
            self.assertFalse(row["steps"][0]["commit"])
            self.assertFalse(row["steps"][0]["mount"])
            self.assertFalse(row["fixture"]["source_store"])
            self.assertEqual(row["fixture"]["recipe"], row["id"])
            self.assertEqual(row["reference"]["row"], row["id"])
            self.assertEqual(row["fixture"]["seed"], 1)
            self.assertEqual(row["cache_class"], "A")
            self.assertIn("INELIGIBLE", row["cache_contract"]["numeric_result"])
            self.assertTrue(row["oracle"]["sharing_metrics_are_diagnostics"])
            self.assertIsNone(row["oracle"]["minimum_sharing_threshold"])
            self.assertIn("P-3", " ".join(row["differences"]))
            self.assertIn("does not apply", " ".join(row["differences"]))

    def test_exact_source_census_boundary_representation_and_budgets(self):
        for row in self.document["cases"]:
            fixture, budget = row["fixture"], row["budget"]
            proof = row["id"] == PROOF
            self.assertEqual(row["proof_only"], proof)
            self.assertEqual(budget["command_ms"], None if proof else 15000)
            self.assertEqual(budget["performance_hard_watchdog_ms"], None if proof else 120000)
            self.assertEqual([budget[k] for k in ("operation_watchdog_ms", "verifier_ms", "verification_hard_watchdog_ms",
                                                   "cleanup_reserve_ms", "publication_guard_ms", "wall_stop_ms")],
                             [120000, 45000, 59000, 4000, 250, 120000])
            self.assertEqual((fixture["root_mode"], fixture["directory_mode"], fixture["file_mode"]), (0o750, 0o750, 0o640))
            self.assertEqual((fixture["mtime_seconds"], fixture["mtime_nanoseconds"]), (1700000000, 0))
            if proof:
                lengths = [0, 1, 8191, 8192, 16384, 32768, 32769]
                contract = row["oracle"]["boundary_contract"]
                self.assertEqual(row["import_schedule"]["fixture_seeds"], [1, 2, 3])
                self.assertEqual(row["import_schedule"]["boundary_lengths"], lengths)
                self.assertEqual((fixture["regular_files"], fixture["directories_including_root"], fixture["entries"]),
                                 (3*(2+6*3), 2+3+3*7, 86))
                self.assertEqual(fixture["logical_bytes"], 3*3*sum(lengths))
                self.assertEqual((contract["current_whole_file_paths"], contract["current_empty_file_paths"]), (54, 6))
                self.assertEqual(contract["max_chunk_bytes"], 32768)
                self.assertEqual(row["reference"]["kind"], "verification")
                self.assertFalse(row["steps"][0]["measured"])
            else:
                tier = int(row["registry"]["tier"])
                profile = row["registry"]["kind"]
                per = 1048576 + (4096 if profile == "insert" else -4096 if profile == "delete" else 0)
                self.assertEqual((fixture["regular_files"], fixture["directories_including_root"], fixture["entries"]),
                                 (tier+1, 2, tier+3))
                self.assertEqual(fixture["logical_bytes"], 1048576 + tier*per)
                self.assertEqual(row["import_schedule"]["variant_ordinals"], [0, tier-1])
                self.assertEqual(row["import_schedule"]["variant_bytes"], per)
                self.assertEqual(row["reference"]["kind"], "performance")
                self.assertTrue(row["steps"][0]["measured"])
            resources = row["resource_profile"]
            self.assertEqual(resources["main_store_limit_bytes"], 4*1024**3)
            self.assertEqual(resources["original_linux_container"],
                             {"cpus": 2, "memory_bytes": 2*1024**3, "memory_swap_bytes": 2*1024**3,
                              "pids_limit": 256, "oom_events_allowed": 0})
            self.assertIn("uncapped", " ".join(row["differences"]))

    def test_reviewed_recipe_operation_and_oracle_sources_are_frozen(self):
        for row in self.document["cases"]:
            self.assertEqual(row["port_review"]["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
            self.assertEqual(row["port_review"]["source_tag_object"], "ae3310fada4a1fe35cb99ab02270b7538a0d03f7")
        review = self.document["cases"][0]["port_review"]
        for path, digest in review["files"].items():
            actual = (ROOT / path).read_bytes()
            frozen = subprocess.check_output(["git", "show", review["source_commit"] + ":" + path], cwd=ROOT)
            self.assertEqual(actual, frozen, path)
            self.assertEqual(hashlib.sha256(actual).hexdigest(), digest, path)
        source = (ROOT / "benchmark/fs-bench-pro/workload/dedup_workloads.rs").read_text()
        self.assertIn('matches!(case.family, "dedup_cross_file" | "dedup_cdc_locality")', source)
        self.assertIn("dedup imports must use public initialize_layerstack, not a filesystem apply", source)

    def test_native_dispatch_and_all_unsupported_operations_refuse_before_helper(self):
        with tempfile.TemporaryDirectory(prefix="fsb-cdc-wrapper-") as directory:
            helper = Path(directory) / "helper"
            helper.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            helper.chmod(0o755)
            environment = dict(os.environ, WORKSPACE_RECIPE=str(helper))
            def invoke(*args):
                return subprocess.run(["bash", str(FAMILY / "workload.sh"), *args], env=environment,
                                      text=True, capture_output=True, timeout=3)
            for case in PERFORMANCE + [PROOF]:
                made = invoke("fixture", case, "/fresh/native")
                self.assertEqual(made.returncode, 0, made.stderr)
                self.assertEqual(json.loads(made.stdout), ["fixture", case, "/fresh/native"])
                checked = invoke("verify-native", case, "/existing/native")
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(json.loads(checked.stdout), ["verify-step", case, "0", "/existing/native"])
            for args in [("apply", PERFORMANCE[0], "/mounted"), ("run", PERFORMANCE[0], "/mounted"),
                         ("fixture", "dedup-cdc-overwrite-01", "/native"),
                         ("fixture", "dedup-cdc-overwrite-extra-1", "/native"),
                         ("fixture", "dedup-cdc-common-body-1000", "/native"),
                         ("fixture", "dedup-cdc-boundaries-proof-extra", "/native"),
                         ("fixture", "dedup-cdc-boundaries-proof", ""),
                         ("fixture", PERFORMANCE[0]), ("verify-native", PERFORMANCE[0], "/native", "1")]:
                checked = invoke(*args)
                self.assertEqual((checked.returncode, checked.stdout), (2, ""), args)


if __name__ == "__main__":
    unittest.main()
