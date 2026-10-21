"""Freeze selected producer provenance and the verification-only access route."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "benchmark/fs-bench-pro/families/historical_access"
SOURCE = ROOT / "benchmark/fs-bench-pro/families/historical_access/mod.rs"
EXPECTED_IDS = ["v016-access-" + name + "-v1" for name in (
    "boundary-before", "boundary-after", "inode-before", "inode-after",
    "fork-point", "divergent-head")]


class HistoricalAccess(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FAMILY / "family.json").read_text())

    def test_all_six_original_selections_and_source_seals(self):
        constants = dict(re.findall(r'const (\w+): &str = "([^"]+)";', SOURCE.read_text()))
        producers = {}
        for path in ("families/dedup_branch_history/mod.rs", "workload/v016_stages.rs"):
            producers.update(re.findall(r'const (\w+): &str = "([^"]+)";',
                                        (ROOT / "benchmark/fs-bench-pro" / path).read_text()))
        frozen = re.findall(
            r'AccessCase \{\s*id: (\w+),\s*producer: \w+::(\w+),\s*ordinal: (\d+),'
            r'\s*roots: (\d+),\s*branch: ProducerBranch::(\w+),\s*plan: ReadPlan::(\w+),'
            r'\s*declared_bytes: ([\d_]+),', SOURCE.read_text())
        self.assertEqual(len(frozen), 6)
        self.assertEqual([row["id"] for row in self.document["cases"]], EXPECTED_IDS)
        for row, original in zip(self.document["cases"], frozen):
            name, producer, ordinal, roots, branch, plan, length = original
            selected = row["historical_access"]
            self.assertEqual((row["id"], selected["producer"], selected["selected_ordinal"],
                              selected["declared_root_references"], selected["producer_branch_role"],
                              selected["read_plan"], selected["declared_full_read_bytes"]),
                             (constants[name], producers[producer], int(ordinal), int(roots),
                              {"Main": "main", "Trunk": "trunk", "B": "B"}[branch],
                              plan, int(length.replace("_", ""))))
            self.assertEqual(row["v016_case"], row["id"])
            self.assertEqual(row["fixture"]["seed"], 1)
            self.assertEqual(row["fixture"]["recipe"], row["id"])
            review = row["port_review"]
            self.assertEqual(review["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
            self.assertEqual(review["source_tag_object"], "ae3310fada4a1fe35cb99ab02270b7538a0d03f7")
            for path, digest in review["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_independent_read_geometry_and_local_ancestry_plan(self):
        # Frozen fixture S: eight tiny, two medium, three boundary, two large,
        # one witness; one root plus five child directories.
        sizes = [4096]*8 + [65536]*2 + [131071, 131072, 131073] + [1048576]*2 + [4096]
        paths = [[("boundary/below.dat", 131071)], [("boundary/below.dat", 131072)],
                 [("tiny-moved/t4.dat", 4096), ("tiny-moved/a4.dat", 4096)],
                 [("tiny-moved/t4.dat", 4096)], [("medium/m0.dat", 65536)],
                 [("medium/m0.dat", 65536)]]
        local_counts = [100, 100, 100, 100, 10, 10]
        for index, row in enumerate(self.document["cases"]):
            selected, fixture = row["historical_access"], row["fixture"]
            self.assertEqual((fixture["regular_files"], fixture["logical_bytes"], fixture["paths"],
                              fixture["directories"]), (len(sizes), sum(sizes), len(sizes)+6, 6))
            self.assertEqual([(read["path"], read["bytes"]) for read in selected["reads"]], paths[index])
            self.assertEqual(selected["verified_full_read_bytes"], 2*sum(size for _, size in paths[index]))
            self.assertEqual(selected["producer_local_commits"], local_counts[index])
            self.assertGreater(selected["selected_ordinal"], 0)
            self.assertLessEqual(selected["selected_ordinal"], local_counts[index])
            self.assertEqual(selected["absent"], ["tiny-moved/a4.dat"] if index == 3 else [])
            relations = selected["required_relations"]
            self.assertIs(relations["inode_pair_dev_ino_equal_and_nlink2"], index == 2)
            self.assertIs(relations["alias_enoent_both_passes"], index == 3)
            for key in ("same_mount_reader_verifier_inode", "all_producer_heads_unchanged",
                        "global_commit_census_unchanged", "no_access_commit"):
                self.assertIs(relations[key], True)
        descendant = self.document["cases"][-1]["historical_access"]
        schedule = descendant["producer_schedule"]["execution_order"]
        self.assertEqual([(branch["role"], branch["commits"]) for branch in schedule],
                         [("trunk", 10), ("a", 10), ("b", 10), ("c", 10)])
        self.assertEqual(schedule[-1]["fork"], {"branch_role": "a", "local_ordinal": 5})
        self.assertEqual(descendant["producer_branch_name"],
                         "v0.1.6-compact-v016-branch-fork-descendant-v1-b")
        # Original implementation itself forks an access Branch. P-2 must not
        # turn that existing topology into a false newly introduced difference.
        driver = (ROOT / "benchmark/fs-bench-pro/src/v016_access.rs").read_text()
        self.assertIn("let selected = client.fork_branch(", driver)
        self.assertIn("LocalForkSource::Branch {\n            branch_id: branch,\n            commit_id: commit,", driver)

    def test_proof_only_watchdogs_and_cache_scope_never_create_a_performance_sample(self):
        for row in self.document["cases"]:
            self.assertIs(row["proof_only"], True)
            self.assertEqual(row["samples"], 0)
            self.assertEqual(row["steps"], [])
            self.assertIsNone(row["budget"]["command_ms"])
            self.assertEqual(row["budget"]["verifier_ms"], 25000)
            self.assertEqual(row["budget"]["verification_hard_watchdog_ms"], 35000)
            guard = row["original_v016_guards"]
            self.assertEqual((guard["verification_worker_work_ms"], guard["cleanup_reserve_ms"],
                              guard["publication_guard_seconds"], guard["owner_test_invocation_ceiling_ms"]),
                             (22000, 3000, 0.25, 120000))
            access = row["historical_access"]
            self.assertEqual(access["phases"], ["reader", "verifier"])
            self.assertEqual((access["commits"], access["mounts"], access["live_workspaces"],
                              access["warmup_execs"], access["pre_read"]), (0, 1, 1, 0, False))
            self.assertEqual(access["reader_profile"],
                             "fresh-session-application-cold;uncontrolled-os-cache;no-pre-read")
            self.assertEqual(row["cache_contract"]["all_paid_backing_metadata_sqlite_phase_evidence"], "UNAVAILABLE")
            self.assertIn("INELIGIBLE", row["cache_contract"]["numeric_result"])
            self.assertIn("distinct rows+1<=references", access["producer_schedule"]["distinct_commit_rows"])

    def test_thin_read_wrapper_preserves_original_argv_and_refuses_unselected_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = Path(temporary) / "helper"
            helper.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
            helper.chmod(0o755)
            environment = {**os.environ, "WORKLOAD_HELPER": str(helper)}
            for case in EXPECTED_IDS:
                for phase in ("reader", "verifier"):
                    result = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), phase, case],
                                            env=environment, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), ["v016-access-read", case, "1", phase])
            for arguments in (("apply", EXPECTED_IDS[0]), ("reader", "ha-old-v2"),
                              ("verifier", EXPECTED_IDS[0], "2"), ("reader",)):
                result = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), *arguments],
                                        env=environment, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
