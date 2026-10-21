"""Original parallel M1 graph cardinalities and contextual shell dispatch."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/multi_workspace_development"
IDS = [f"v016-workspace-mixed-{load}-k{count}-v1"
       for load in ("100mb-5000", "500mb-30000") for count in (10, 100)]
IDS.append("v016-workspace-four-100mb-5000-k100-v1")
SOURCE = "d296981ace76fe751bebf00dee52818fe18a3eef"


class MultiWorkspaceDevelopment(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads((FAMILY / "family.json").read_text())["cases"]

    def test_original_graph_and_source_discrepancies_remain_explicit(self):
        self.assertEqual([row["id"] for row in self.rows], IDS)
        for row in self.rows:
            four = "workspace-four" in row["id"]
            k = 100 if "-k100-" in row["id"] else 10
            workers = 4 if four else 2
            topology = row["topology_schedule"]
            self.assertEqual(topology["schema"], "original-v016-m1-topology-v1")
            self.assertEqual((topology["per_worker_commits"], topology["total_commits"],
                              topology["graph_root_boundaries"], topology["longest_ancestry"]),
                             (k, workers * k, 1 + workers * k, k))
            self.assertEqual(topology["simultaneous_workspaces"], workers)
            self.assertEqual((topology["daemon_count"], topology["container_count"]), (1, 1))
            self.assertIs(topology["shared_store"], True)
            self.assertEqual(topology["verification_steps_by_worker"],
                             {str(i): [k] for i in range(workers)})
            for index, worker in enumerate(topology["workers"]):
                self.assertEqual((worker["index"], worker["branch_tag"], worker["branch_salt"],
                                  worker["cycle_start"], worker["fork_source"]),
                                 (index, index, f"branch{index}", 1, "initial-layer"))
            self.assertTrue(topology["all_commit_ids_and_parent_edges"])
            self.assertTrue(topology["global_commit_census"])
            self.assertTrue(topology["actual_commit_overlap_required"])
            self.assertFalse(topology["per_stage_barrier"])
            self.assertFalse(topology["pre_commit_barrier"])
            if four:
                self.assertEqual(topology["segment_ranges"], [[1, 100]])
                self.assertIsNone(topology["discard_reopen"])
            else:
                self.assertEqual(topology["segment_ranges"], [[1, k // 2], [k // 2 + 1, k]])
                discard = topology["discard_reopen"]
                self.assertEqual((discard["worker"], discard["after_local_commit"],
                                  discard["witness_bytes"], discard["extra_created_commits"]),
                                 (0, k // 2, 256, 0))
                self.assertIn("already committed", discard["peer_state"])
            notes = " ".join(row["differences"])
            self.assertIn("roadmap requires fixed5/dirtyBstage6/pre-Commit barrier", notes)
            self.assertIn("H17", notes)
            self.assertIn("no automatic normalization", notes)
            self.assertEqual(row["status"], "ported")
            self.assertNotIn("not-applicable", row["status"])

    def test_original_cycle_counters_fixture_bounds_and_gate_scope(self):
        for row in self.rows:
            large = "500mb" in row["id"]
            k = 100 if "-k100-" in row["id"] else 10
            four = "workspace-four" in row["id"]
            self.assertEqual(row["cache_class"], "C")
            self.assertIn("INELIGIBLE under strict H-5", row["cache_contract"]["numeric_result"])
            self.assertEqual(row["construction_workers"], 1)
            self.assertEqual(row["fixture"]["seed"], 1)
            self.assertEqual((row["fixture"]["max_non_directory_names"],
                              row["fixture"]["max_logical_path_bytes"]),
                             (30000, 500000000) if large else (5000, 100000000))
            self.assertEqual(row["budget"], {"command_ms": 15000,
                              "operation_watchdog_ms": 60000, "performance_hard_watchdog_ms": 60000,
                              # Owner direction 2026-10-12 (#319 phase 13): the two named 500 MiB mixed cases only.
                              "verifier_ms": 60000 if four else 80000 if row["id"].startswith("v016-workspace-mixed-500mb") else 25000,
                              "verification_hard_watchdog_ms": 70000 if four else 90000 if row["id"].startswith("v016-workspace-mixed-500mb") else 35000})
            self.assertEqual(len(row["steps"]), k)
            for ordinal, step in enumerate(row["steps"], 1):
                self.assertEqual(step["index"], ordinal)
                self.assertEqual(step["run"], f"workload.sh stage {row['id']} {ordinal}")
                self.assertTrue(step["commit"])
                self.assertEqual(step["expected_commit"], "Committed")
                self.assertIn("required topology worker", step["worker_argument"])
            self.assertEqual(row["m1_schedule"]["native_stage2_targets"], 14)
            self.assertEqual(row["m1_schedule"]["ordered_ordinary_stage2_members"], 2)
            self.assertFalse(row["m1_schedule"]["cross_file_atomic_batch"])
            self.assertIn("No exhaustive Phase1 or all-intermediate-payload claim", row["oracle"]["scope"])
            self.assertIn("root identities may repeat", row["oracle"]["roots"])

    def test_review_pins_frozen_contract_including_failed_attribute_assertion(self):
        for row in self.rows:
            review = row["port_review"]
            self.assertEqual(review["source_commit"], SOURCE)
            self.assertEqual(review["source_tag_object"], "ae3310fada4a1fe35cb99ab02270b7538a0d03f7")
            self.assertIn("NOT_RUN", review["qualification"])
            for path, expected in review["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)
        helper = (ROOT / "benchmark/fs-bench-pro/workload/v016_m1.rs").read_text()
        frozen = subprocess.check_output(["git", "show", SOURCE + ":benchmark/fs-bench-pro/workload/v016_m1.rs"], cwd=ROOT)
        self.assertEqual(helper.encode(), frozen)

    def invoke(self, *arguments, descriptor=False):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            log = folder / "calls.jsonl"
            for name in ("workload", "edit", "recipe"):
                tool = folder / name
                tool.write_text("#!/usr/bin/env python3\nimport os,sys,json\n"
                                "with open(os.environ['CALL_LOG'],'a') as f:\n"
                                " f.write(json.dumps([os.path.basename(sys.argv[0]),*sys.argv[1:]])+'\\n')\n")
                tool.chmod(0o755)
            env = {**os.environ, "WORKLOAD_WRITER": str(folder / "workload"),
                   "EDIT_WRITER": str(folder / "edit"), "WORKSPACE_RECIPE": str(folder / "recipe"),
                   "CALL_LOG": str(log)}
            env.pop("SDK_STEP_DESCRIPTOR", None)
            env.pop("SDK_STEP_DESCRIPTOR_SHA256", None)
            if descriptor:
                env.update(SDK_STEP_DESCRIPTOR="/code/history/worker-1/step-2.tsv",
                           SDK_STEP_DESCRIPTOR_SHA256="a" * 64)
            result = subprocess.run(["bash", str(FAMILY / "workload.sh"), *arguments],
                                    env=env, capture_output=True, text=True, timeout=5)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls

    def test_two_and_four_worker_context_and_ordered_stage2_members(self):
        for worker in range(4):
            case = IDS[4] if worker >= 2 else IDS[1]
            result, calls = self.invoke("stage", case, "2", str(worker), descriptor=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls[0], ["workload", "v016-m1-stage", "L100", "1", "1",
                                        str(worker), f"branch{worker}", "2"])
            self.assertEqual([call[-1] for call in calls[1:]], ["1", "2"])
            self.assertTrue(all(call[1:5] == ["apply-context-step-prepared", case, str(worker), "2"]
                                for call in calls[1:]))
        result, calls = self.invoke("stage", IDS[3], "99", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["workload", "v016-m1-stage", "L500", "1", "20", "1", "branch1", "4"]])
        result, calls = self.invoke("verify-step", IDS[4], "100", "modes.tsv", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["recipe", "verify-context", IDS[4], "3", "100", ".", "modes.tsv"]])

    def test_discard_witness_and_invalid_selection_do_not_launch_helpers(self):
        result, calls = self.invoke("witness", IDS[0], "0", "d001/f00000", "ab" * 256)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [["workload", "v016-m1-witness", "d001/f00000", "ab" * 256]])
        for arguments in [("stage", IDS[0], "2", "0"),
                          ("stage", IDS[0], "11", "0"), ("stage", IDS[0], "2", "2"),
                          ("stage", IDS[4], "1", "4"), ("stage", IDS[0], "0", "0"),
                          ("stage", IDS[0], "1"), ("stage", "wrong", "1", "0"),
                          ("witness", IDS[0], "0", "path", "ab" * 255),
                          ("witness", IDS[0], "0", "path", "az" * 256),
                          ("witness", IDS[0], "1", "path", "ab" * 256),
                          ("witness", IDS[4], "0", "path", "ab" * 256)]:
            result, calls = self.invoke(*arguments)
            self.assertEqual(result.returncode, 2, arguments)
            self.assertEqual(calls, [], arguments)


if __name__ == "__main__":
    unittest.main()
