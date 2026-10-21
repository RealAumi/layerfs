"""Frozen history registry, selected proof scope, operation routes and limits."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/dedup_branch_history"


class DedupBranchHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((FAMILY / "family.json").read_text())["cases"]

    def test_original_registry_and_all_ordered_commits(self):
        ids = [f"dedup-history-{kind}-{n}" + ("-mixed-v2" if kind == "unrelated" and n > 10 else "")
               for kind in ("distributed", "hotset", "recurring", "metadata", "unrelated")
               for n in ((1, 100, 500) if kind in ("distributed", "unrelated") else (1, 100))]
        ids += [f"v016-history-{kind}-k{n}-v1"
                for kind in ("large-hotset", "namespace-inode", "boundary-cycle") for n in (10, 100)]
        self.assertEqual([row["id"] for row in self.rows], ids)
        self.assertEqual(sum(len(row["steps"]) for row in self.rows), 1835)
        for row in self.rows:
            n = int(row["registry"]["tier"])
            self.assertEqual(row["history_schedule"]["commits"], n)
            self.assertTrue(row["history_schedule"]["global_commit_census"])
            self.assertEqual(row["history_schedule"]["step_base"], 1)
            for step, item in enumerate(row["steps"], 1):
                self.assertEqual(item, {"index": step, "run": f"workload.sh apply {row['id']} {step}",
                                        "commit": True, "expected_commit": "Committed"})

    def test_frozen_checkpoint_boundary_and_alias_coverage(self):
        by_id = {row["id"]: row for row in self.rows}
        expected = {
            "dedup-history-distributed-500": [0, 1, 199, 200, 201, 250, 499, 500],
            "dedup-history-hotset-100": [0, 1, 7, 8, 9, 50, 99, 100],
            "dedup-history-metadata-100": [0, 1, 2, 49, 50, 99, 100],
            "v016-history-namespace-inode-k100-v1": [0, 1, 2, 49, 50, 94, 95, 99, 100],
            "v016-history-boundary-cycle-k100-v1": [0, 1, 2, 49, 50, 99, 100],
        }
        for key, checkpoints in expected.items():
            self.assertEqual(by_id[key]["history_schedule"]["verification_steps"], checkpoints)
            self.assertEqual(by_id[key]["oracle"]["roots"], checkpoints)
        for row in self.rows:
            if int(row["registry"]["tier"]) <= 10:
                self.assertEqual(row["history_schedule"]["verification_steps"], list(range(len(row["steps"])+1)))
        source = (ROOT / "benchmark/fs-bench-pro/families/dedup_branch_history/mod.rs").read_text()
        self.assertIn("vec![0, 1, 199, 200, 201, n / 2, n - 1, n]", source)
        self.assertIn("n - 6, n - 5", source)

    def test_exact_fixture_envelopes_and_recurrence_declarations(self):
        for row in self.rows:
            fixture = row["fixture"]
            v016, mixed = row["id"].startswith("v016-"), row["id"].endswith("-mixed-v2")
            self.assertEqual((fixture["files"], fixture["directories_including_root"], fixture["entries"], fixture["logical_bytes"]),
                             (16, 6, 22, 2658304) if v016 else (10, 2, 12, 1048576) if mixed else (200, 134, 334, 1048576))
            self.assertEqual((fixture["seed"], fixture["root_mode"], fixture["file_mode"], fixture["mtime_seconds"], fixture["mtime_nanoseconds"]),
                             (1, 0o750, 0o640, 1700000000, 0))
            kind = row["registry"]["kind"]
            self.assertEqual(row["history_schedule"]["metadata_content_root_stability"], kind == "metadata")
            self.assertEqual(row["history_schedule"]["recurring_file_root_parity"], kind == "recurring")
            if mixed:
                self.assertEqual(row["native_verifier"]["sampled_ranges"], {"mixed/f000.dat": [[0, 65536], [327680, 65536], [589824, 65536]]})
                self.assertIn("bypasses the fast", row["native_verifier"]["historical_checkpoint_scope"])
                self.assertTrue(any("additional stronger coverage" in value for value in row["differences"]))
            if kind == "namespace-inode":
                self.assertEqual(row["history_schedule"]["maximum_names"], 18)
                self.assertEqual(row["history_schedule"]["maximum_logical_path_bytes"], 2666496)

    def test_original_distinct_budgets_resource_profile_and_unknown_cache(self):
        for row in self.rows:
            v016 = row["id"].startswith("v016-")
            self.assertEqual(row["budget"], {"command_ms": 15000, "performance_hard_watchdog_ms": 210000 if row["id"] in {"dedup-history-distributed-500", "dedup-history-unrelated-500-mixed-v2"} else 60000 if v016 else 120000,
                "operation_watchdog_ms": 60000 if v016 else 120000, "verifier_ms": 25000 if v016 else 45000,
                "verification_hard_watchdog_ms": 35000 if v016 else 59000, "cleanup_reserve_ms": 3000 if v016 else 4000,
                "publication_guard_ms": 250})
            self.assertTrue(row["original_ordinary_guards"])
            self.assertEqual(row["cache_class"], "C")
            self.assertEqual(row["resource_profile"], {"cpus": 2, "memory_bytes": 2*1024**3, "memory_swap_bytes": 2*1024**3,
                "pids_limit": 256, "main_store_limit_bytes": 4*1024**3, "oom_events_allowed": 0, "swap_bytes_allowed": 0})
            self.assertTrue(any("INELIGIBLE" in value for value in row["differences"]))
            self.assertTrue(any("unselected" in value for value in row["differences"]))

    def test_port_review_pins_frozen_source_and_declares_mechanism_change(self):
        for row in self.rows:
            self.assertEqual(row["port_review"]["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
            for path, digest in row["port_review"]["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
            sdk = row["registry"]["kind"] not in ("metadata", "unrelated")
            self.assertEqual(row["ordinary_sdk_edits"], sdk)
            self.assertEqual(any(value.startswith("P-3:") for value in row["differences"]), sdk)

    def test_shell_routes_preserve_posix_helpers_and_two_write_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "writer"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); fake.chmod(0o755)
            env = {**os.environ, "WORKLOAD_WRITER": str(fake), "EDIT_WRITER": str(fake)}
            cases = [("dedup-history-distributed-500", 201, ["apply-sdk-step", "dedup-history-distributed-500", "201"]),
                     ("dedup-history-metadata-100", 2, ["workspace-apply", "dedup-history-metadata-100", "1", "1", "performance"]),
                     ("dedup-history-unrelated-100-mixed-v2", 100, ["workspace-apply", "dedup-history-unrelated-100-mixed-v2", "1", "99", "performance"]),
                     ("v016-history-boundary-cycle-k10-v1", 2, ["apply-sdk-step", "v016-history-boundary-cycle-k10-v1", "2"])]
            hn = "v016-history-namespace-inode-k100-v1"
            for stage in range(1, 6):
                step = 90+stage
                expected = ["apply-sdk-step", hn, str(step)] if stage == 2 else ["v016-hn-stage", "1", "19", str(stage)]
                cases.append((hn, step, expected))
            for case, step, expected in cases:
                got = subprocess.run(["/bin/bash", str(FAMILY/"workload.sh"), "apply", case, str(step)],
                                     env=env, capture_output=True, text=True, timeout=3, check=True)
                self.assertEqual(got.stdout.splitlines(), expected)
            got = subprocess.run(["/bin/bash", str(FAMILY/"workload.sh"), "verify", hn, "94"],
                                 env=env, capture_output=True, text=True, timeout=3, check=True)
            self.assertEqual(got.stdout.splitlines(), ["workspace-verify-tree", hn, "1", "94"])
            descriptor, digest = "/code/history/payloads/step-92/descriptor.tsv", "a"*64
            for case, step in ((hn, 92), ("dedup-history-distributed-500", 201),
                               ("v016-history-boundary-cycle-k10-v1", 2)):
                prepared_env = {**env, "SDK_STEP_DESCRIPTOR": descriptor, "SDK_STEP_DESCRIPTOR_SHA256": digest}
                got = subprocess.run(["/bin/bash", str(FAMILY/"workload.sh"), "apply", case, str(step)],
                                     env=prepared_env, capture_output=True, text=True, timeout=3, check=True)
                self.assertEqual(got.stdout.splitlines(), ["apply-sdk-step-prepared", case, str(step), descriptor, digest])
            for missing in ("SDK_STEP_DESCRIPTOR", "SDK_STEP_DESCRIPTOR_SHA256"):
                partial = dict(prepared_env); partial.pop(missing)
                got = subprocess.run(["/bin/bash", str(FAMILY/"workload.sh"), "apply", hn, "92"],
                                     env=partial, capture_output=True, text=True, timeout=3)
                self.assertEqual(got.returncode, 2)
            for route, case, step in [("apply", hn, "0"), ("apply", hn, "101"), ("apply", hn, "02"),
                                      ("verify", "unknown", "1"), ("verify", hn, "-1")]:
                got = subprocess.run(["/bin/bash", str(FAMILY/"workload.sh"), route, case, step],
                                     env=env, capture_output=True, text=True, timeout=3)
                self.assertEqual(got.returncode, 2)


if __name__ == "__main__":
    unittest.main()
