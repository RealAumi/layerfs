"""Freeze source-aware Init and sharing obligations without running a product."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "benchmark/fs-bench-pro/families/dedup_cross_file"
SOURCE = "d296981ace76fe751bebf00dee52818fe18a3eef"
TAG_OBJECT = "ae3310fada4a1fe35cb99ab02270b7538a0d03f7"
KINDS = ("unique", "identical", "mixed")
TIERS = (100,)
MIB = 1048576


def expected_cases():
    return [("dedup-cross-file-anchor-1", "anchor", 1)] + [
        (f"dedup-cross-file-{kind}-{tier}", kind, tier)
        for kind in KINDS for tier in TIERS
    ]


def bases(kind, tier):
    if kind in ("anchor", "identical"):
        return [0] * tier
    if kind == "unique":
        return list(range(tier))
    # Independent group expansion: each complete quartet is the first base
    # twice, then the next two bases; incomplete quartets retain that prefix.
    return [3 * group + item for group in range((tier + 3) // 4)
            for item in (0, 0, 1, 2)][:tier]


class Definition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.family = json.loads((FAMILY / "family.json").read_text())
        cls.cases = cls.family["cases"]

    def test_original_selection_seed_geometry_and_mixed_groups(self):
        original = (ROOT / "benchmark/fs-bench-pro/families/dedup_cross_file/mod.rs").read_text()
        kinds = re.findall(r'\("([^"]+)", "dedup-cross-file-[^"]+"\)', original)
        self.assertEqual(kinds, list(KINDS))
        self.assertIn('.filter(|c| c.tier != 1)', original)
        self.assertEqual(self.family["engine"], "project")
        self.assertEqual([row["id"] for row in self.cases], [row[0] for row in expected_cases()])
        self.assertEqual(len({row["id"] for row in self.cases}), 4)
        mixed_counts = {10: 7, 100: 75, 500: 375}
        for row, (ident, kind, tier) in zip(self.cases, expected_cases()):
            self.assertEqual((row["v016_case"], row["status"]), (ident, "ported"))
            self.assertEqual((row["registry"]["kind"], int(row["registry"]["tier"])), (kind, tier))
            fixture = row["fixture"]
            self.assertEqual((fixture["recipe"], fixture["seed"]), (ident, 1))
            self.assertEqual((fixture["regular_files"], fixture["directories"], fixture["paths"]),
                             (tier, 2, tier + 2))
            self.assertEqual((fixture["file_bytes"], fixture["logical_bytes"]), (MIB, tier * MIB))
            self.assertEqual((fixture["directory_mode"], fixture["file_mode"],
                              fixture["mtime_seconds"], fixture["mtime_nanoseconds"]),
                             (0o750, 0o640, 1700000000, 0))
            ordinals = bases(kind, tier)
            self.assertEqual(fixture["distinct_base_ordinals"], len(set(ordinals)))
            if kind == "mixed":
                self.assertEqual(len(set(ordinals)), mixed_counts[tier])
                self.assertEqual(ordinals[:10], [0,0,1,2,3,3,4,5,6,6])
            recipe = fixture["content_recipe"]
            self.assertEqual((recipe["function"], recipe["family"], recipe["profile"],
                              recipe["seed_label"], recipe["role"], recipe["length"]),
                             ("dedup_workloads::content", "dedup_cross_file", "base",
                              "layerfs-v0.1.3-seed-1", "bytes", MIB))
            self.assertEqual(row["reference"]["release"], "0.1.5")
            self.assertEqual(row["reference"]["row"], ident)

    def test_init_cannot_be_replaced_by_commit_or_fixture_store_setup(self):
        for row in self.cases:
            self.assertEqual(row["steps"], [{"init": row["id"],
                "public_api": "ProjectApi::init", "fresh_store": True}])
            model = row["init_import"]
            self.assertEqual(model["schema"], "original-dedup-import-v1")
            self.assertEqual((model["original_public_api"], model["current_public_api"]),
                             ("Client::initialize_layerstack", "ProjectApi::init"))
            self.assertIn("no prepared Store or previous Init", model["source"])
            self.assertEqual((model["performance_public_calls"], model["performance_mounts"],
                              model["performance_execs"], model["performance_commits"]), (1,0,0,0))
            self.assertEqual(row["original_operation_counts"], {
                "initialize_layerstack": 1, "workspace_create": 0, "fuse_workload": 0,
                "commit": 0, "scanned_files": row["fixture"]["regular_files"],
                "scanned_bytes": row["fixture"]["logical_bytes"]})
            self.assertEqual(model["selected_state"], 0)
            self.assertIn("SHA-bound original recipe before timed", model["pre_admission_input_qualification"])

    def test_complete_original_storage_contract_and_honest_topology_cache_scope(self):
        for row in self.cases:
            oracle = row["oracle"]
            storage = oracle["storage"]
            self.assertIn("every payload byte", oracle["scope"])
            self.assertIn("exhaustive current inode-table membership", oracle["scope"])
            self.assertIn("no Commit rows", oracle["roots"])
            self.assertEqual(storage["complete_regular_file_transcript_cardinality"],
                             row["fixture"]["regular_files"])
            self.assertEqual(storage["distinct_complete_file_count"], row["fixture"]["distinct_base_ordinals"])
            self.assertEqual(storage["independent_chunk_profile"], {
                "minimum_bytes": 8192, "nominal_bytes": 16384, "maximum_bytes": 32768,
                "window_bytes": 32768, "scope": "frozen independent scan; no product CDC invocation in the oracle"})
            for field in ("require_exact_chunk_boundaries_and_payload_bytes", "require_fresh_full_payload_extents",
                          "fresh_payload_length_equals_extent_length", "require_anchor_no_internal_duplicate_chunks",
                          "require_repeated_base_exact_transcripts", "require_disjoint_chunk_ids_across_distinct_bases",
                          "no_numeric_ratio_gate"):
                self.assertIs(storage[field], True, field)
            self.assertEqual((storage["fresh_payload_source_offset"], storage["preexisting_payload_bytes"]), (0,0))
            identical = row["registry"]["kind"] == "identical"
            self.assertIs(storage["require_identical_file_transcripts"], identical)
            self.assertIs(storage["require_identical_file_content_roots"], identical)
            self.assertEqual(row["cache_class"], "A")
            self.assertEqual(row["cache_contract"]["host_metadata_coldness"], "UNAVAILABLE")
            self.assertTrue(row["cache_contract"]["numeric_result"].startswith("INELIGIBLE"))
            self.assertIn("fresh FUSE mount", oracle["mounted_verification"])
            self.assertIn("End/Gone/fences/KnownStop", "\n".join(row["differences"]))
            self.assertIn("retired encoded ObjectId", "\n".join(row["differences"]))
            self.assertIn("selected payload or semantic path is omitted", oracle["omissions"])

    def test_original_resource_watchdogs_and_reporting_target_are_unchanged(self):
        for row in self.cases:
            self.assertEqual(row["budget"], {"command_ms":15000, "verifier_ms":45000,
                "operation_watchdog_ms":120000, "verification_hard_watchdog_ms":59000})
            guards = row["original_resource_guards"]
            self.assertIs(row["original_ordinary_guards"], True)
            self.assertEqual((guards["main_store_logical_bytes_max"], guards["main_store_allocated_bytes_max"]),
                             (4 * 1024**3, 4 * 1024**3))
            self.assertEqual((guards["host_rss_bytes_max"], guards["host_rss_nominal_interval_ns"]),
                             (2 * 1024**3, 10000000))
            self.assertEqual((guards["owned_workspace_spool_logical_bytes_max"],
                              guards["owned_workspace_spool_allocated_bytes_max"],
                              guards["owned_workspace_spool_cleanup_files"]), (2 * 1024**3, 2 * 1024**3, 0))
            self.assertEqual((guards["container_cpus"], guards["container_memory_bytes"],
                              guards["container_memory_swap_bytes"], guards["container_pids_limit"],
                              guards["container_oom_kill_delta"]), (2, 2 * 1024**3, 2 * 1024**3, 256, 0))
            self.assertEqual((guards["verification_worker_work_ms"], guards["verification_cleanup_reserve_ms"],
                              guards["verification_hard_watchdog_ms"], guards["publication_guard_seconds"]),
                             (45000, 4000, 59000, 0.25))
            self.assertLess(row["fixture"]["logical_bytes"], guards["aggregate_fixture_bytes_exclusive_max"])
            self.assertLessEqual(row["fixture"]["file_bytes"], guards["per_file_bytes_max"])

    def test_frozen_source_bytes_match_recovery_tag_and_recorded_seals(self):
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "reference-v0.1.6-final^{commit}"],
                                                cwd=ROOT, text=True).strip(), SOURCE)
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "reference-v0.1.6-final"],
                                                cwd=ROOT, text=True).strip(), TAG_OBJECT)
        review = self.cases[0]["port_review"]
        for name, digest in review["files"].items():
            current = (ROOT / name).read_bytes()
            frozen = subprocess.check_output(["git", "show", SOURCE + ":" + name], cwd=ROOT)
            self.assertEqual(current, frozen, name)
            self.assertEqual(hashlib.sha256(current).hexdigest(), digest, name)
        for row in self.cases:
            self.assertEqual((row["port_review"]["source_commit"], row["port_review"]["source_tag_object"]),
                             (SOURCE, TAG_OBJECT))
            self.assertEqual(row["port_review"]["files"], review["files"])


class NativeShellDispatch(unittest.TestCase):
    def test_only_fresh_fixture_and_exact_original_state_zero_verification_are_dispatched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "sealed-writer"
            fake.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
            fake.chmod(0o755)
            env = {**os.environ, "WORKSPACE_RECIPE": str(fake)}
            native = str(root / "never-materialized")
            for ident, _, _ in expected_cases():
                for mode, args in (("fixture", ["fixture", ident, native]),
                                   ("verify", ["verify-step", ident, "0", native])):
                    checked = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), mode, ident, native],
                                             env=env, text=True, capture_output=True, timeout=5)
                    self.assertEqual(checked.returncode, 0, checked.stderr)
                    self.assertEqual(json.loads(checked.stdout), args)
            self.assertFalse(Path(native).exists())
            refused = [["apply", expected_cases()[0][0], native],
                       ["fixture", "dedup-cross-file-identical-1", native],
                       ["fixture", "dedup-cross-file-mixed-11", native],
                       ["fixture", "dedup-cross-file-unique-100"],
                       ["fixture", "dedup-cross-file-unique-100", native, "extra"]]
            for args in refused:
                checked = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), *args],
                                         env=env, text=True, capture_output=True, timeout=5)
                self.assertNotEqual(checked.returncode, 0)
                self.assertEqual(checked.stdout, "")
            unsealed = {key: value for key, value in env.items() if key != "WORKSPACE_RECIPE"}
            checked = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), "fixture",
                                      expected_cases()[0][0], native],
                                     env=unsealed, text=True, capture_output=True, timeout=5)
            self.assertNotEqual(checked.returncode, 0)
            self.assertEqual(checked.stdout, "")


if __name__ == "__main__":
    unittest.main()
