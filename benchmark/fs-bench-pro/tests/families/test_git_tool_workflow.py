"""Frozen four-case Git operations, configuration, proof topology and budgets."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/git_tool_workflow"


class GitToolWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((FAMILY / "family.json").read_text())["cases"]

    def test_three_kept_cases_fixtures_and_target_counts(self):
        tiers = [1, 100, 500]
        self.assertEqual([row["id"] for row in self.cases], [f"git-tool-{tier}-"+("compact-v2" if tier<=10 else "mixed-v4") for tier in tiers])
        self.assertEqual([row["fixture"]["working_tree_files"] for row in self.cases], [51, 2351, 5351])
        for row, tier in zip(self.cases, tiers):
            self.assertEqual(row["fixture"]["seed"], 1)
            self.assertTrue(row["git_workflow"])
            self.assertTrue(row["original_ordinary_guards"])
            self.assertEqual(row["original_operation_counts"]["completed_target_count"], tier)
            self.assertEqual(row["original_operation_counts"]["git_process_count"], 6)
            self.assertEqual(row["original_operation_counts"]["benchmark_verifier_count"], 0)
            self.assertEqual(row["fixture"]["complete_repository_cap_bytes"], 256*1024**2)
            self.assertEqual(row["expected_commit"], "Committed")
            self.assertEqual(row["fixture"]["root_mode"], 0o750)
            self.assertEqual(row["fixture"]["file_mode"], 0o640)
            self.assertEqual(row["fixture"]["mtime_seconds"], 1700000000)
            self.assertEqual(row["git_definition"]["modify_offset"], 1024)
            self.assertEqual(row["git_definition"]["modify_len"], 10)
            self.assertEqual(row["git_definition"]["modify_xor"], 0x5a)
            self.assertEqual(row["git_definition"]["target_bytes"], 2500)

    def test_original_six_commands_and_fixed_config_are_read_from_frozen_source(self):
        original = (ROOT / "benchmark/fs-bench-pro/workload/ordinary_workloads.rs").read_text()
        commands = [["status","--porcelain=v1","-z"],["diff","--no-ext-diff","--binary","--"],
                    ["add","-A","--"],["diff","--cached","--check"],
                    ["commit","--no-gpg-sign","--no-verify","-m","layerfs v0.1.3 tool workflow"],
                    ["status","--porcelain=v1","-z"]]
        for row in self.cases:
            self.assertEqual(row["git_definition"]["commands"], commands)
            self.assertEqual(len(row["git_definition"]["config"]), 16)
            for name,value in row["git_definition"]["config"]:
                self.assertIn(f'("{name}", "{value}")', original)
            for path,digest in row["port_review"]["files"].items():
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), digest)
            self.assertEqual(row["port_review"]["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")

    def test_performance_qualify_and_fresh_semantic_routes_remain_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "writer"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); fake.chmod(0o755)
            case = self.cases[0]["id"]
            import os
            env = {**os.environ, "WORKLOAD_WRITER": str(fake), "LAYERFS_V013_GIT_REFERENCE": "/qualified-reference"}
            for route, expected in (("apply", ["workspace-apply",case,"1","0","performance"]),
                                    ("qualify", ["workspace-apply",case,"1","0","verify"]),
                                    ("verify", ["workspace-git-verify",case,"1","/qualified-reference"])):
                got = subprocess.run(["/bin/bash",str(FAMILY/"workload.sh"),route,case], env=env,
                                     capture_output=True,text=True,timeout=3,check=True)
                self.assertEqual(got.stdout.splitlines(), expected)

    def test_original_limits_and_all_custody_semantic_obligations_are_declared(self):
        for row in self.cases:
            self.assertEqual(row["budget"], {"command_ms":15000,"verifier_ms":45000,
                "operation_watchdog_ms":120000,"verification_hard_watchdog_ms":59000})
            self.assertEqual(row["steps"], [{"run":"workload.sh apply "+row["id"],"commit":True}])
            self.assertEqual(row["git_qualification"]["run"], "workload.sh qualify "+row["id"])
            for required in ("precommit-to-fresh", "index stat-cache", "HEAD/tree/parent", "fsck", "exactly2Gitcommits", "inode-table census", "mounted intermediate"):
                self.assertIn(required, row["oracle"]["scope"])
            self.assertTrue(any("INELIGIBLE" in value for value in row["differences"]))


if __name__ == "__main__":
    unittest.main()
