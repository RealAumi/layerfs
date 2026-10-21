"""Frozen historical forks, canonical identity collapse and ordered wrappers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/branch_development"
M1 = [f"v016-branch-mixed-{load}-k{k}-v1"
      for load in ("100mb-5000", "500mb-30000") for k in (10, 100)]
COMPACT = ["v016-branch-convergent-content-v1", "v016-branch-fork-descendant-v1"]


class BranchDevelopment(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FAMILY / "family.json").read_text())

    def test_frozen_selection_fork_parents_checkpoints_and_limits(self):
        rows = self.document["cases"]
        self.assertEqual([c["id"] for c in rows], M1 + COMPACT)
        for c in rows:
            cid = c["id"]
            schedule = c["branch_schedule"]
            roles = schedule["branches"]
            self.assertEqual(c["status"], "ported")
            self.assertTrue(c["original_ordinary_guards"])
            self.assertTrue(schedule["global_commit_census"])
            self.assertFalse(schedule["discard_probe"])
            self.assertEqual((c["fixture"]["recipe"], c["fixture"]["seed"]), (cid, 1))
            self.assertEqual(c["cache_class"], "C")
            self.assertIn("INELIGIBLE under strict H-5", c["cache_contract"]["numeric_result"])
            # Owner direction 2026-10-12 (#319 phase 13): the two named 500 MiB mixed cases only.
            verifier = 105000 if cid.startswith("v016-branch-mixed-500mb") else 25000
            self.assertEqual(c["budget"]["command_ms"], 15000)
            self.assertEqual(c["budget"]["performance_hard_watchdog_ms"], 60000)
            self.assertEqual(c["budget"]["performance_cleanup_reserve_ms"], 3000)
            self.assertEqual(c["budget"]["verifier_ms"], verifier)
            self.assertEqual(c["budget"]["verification_hard_watchdog_ms"], verifier + 10000)
            self.assertEqual(c["budget"]["verification_cleanup_reserve_ms"], 3000)
            self.assertEqual(roles[0]["fork_source"]["kind"], "Layer")
            self.assertIsNone(roles[0]["expected_initial_parent"])
            for role in roles[1:]:
                source = "a" if role["role"] == "c" else "trunk"
                self.assertEqual(role["fork_source"], {"kind": "Commit", "source_role": source, "local_commit": 5})
                self.assertEqual(role["expected_initial_parent"], {"role": source, "local_commit": 5})
            if cid in M1:
                k = 100 if "-k100-" in cid else 10
                self.assertEqual(schedule["execution_groups"], [["trunk"], ["a", "b"]])
                self.assertTrue(schedule["children_common_start_barrier"])
                self.assertEqual(schedule["maximum_live_workspaces"], 2)
                self.assertEqual([r["local_commits"] for r in roles], [10, k, k])
                self.assertEqual([(r["branch_tag"], r["branch_salt"], r["cycle_start"]) for r in roles],
                                 [(0, "branch0", 1), (1, "branch1", 2), (2, "branch2", 2)])
                self.assertEqual(schedule["payload_checkpoints"],
                                 [{"role": "trunk", "local_index": 10}, {"role": "a", "local_index": k},
                                  {"role": "b", "local_index": k}])
                self.assertEqual((schedule["created_commit_acknowledgements"], schedule["retained_root_references"],
                                  schedule["longest_ancestry"]), (10 + 2*k, 11 + 2*k, 5 + k))
                self.assertTrue(schedule["distinct_commit_ids"])
                self.assertIn("H-17", " ".join(c["differences"]))
            else:
                descendant = cid == COMPACT[1]
                names = ["trunk", "a", "b"] + (["c"] if descendant else [])
                self.assertEqual(schedule["execution_groups"], [[r] for r in names])
                self.assertEqual(schedule["maximum_live_workspaces"], 1)
                self.assertFalse(schedule["distinct_commit_ids"])
                self.assertIn("collapse", schedule["distinct_commit_policy"])
                self.assertEqual([r["name"] for r in roles], [f"v0.1.6-compact-{cid}-{r}" for r in names])
                self.assertEqual(schedule["payload_checkpoints"], [{"role": "trunk", "local_index": 5}] +
                                 [{"role": r, "local_index": 10} for r in names])
                self.assertEqual((schedule["created_commit_acknowledgements"], schedule["retained_root_references"],
                                  schedule["longest_ancestry"]), (40, 41, 20) if descendant else (30, 31, 15))
            self.assertEqual(len(c["steps"]), schedule["created_commit_acknowledgements"])

    def test_independent_fixture_census_and_original_step_geometry(self):
        for c in self.document["cases"]:
            fixture = c["fixture"]
            if c["id"] in COMPACT:
                # S: eight tiny, two medium, threshold triple, two 1MiB, witness.
                self.assertEqual((fixture["regular_files"], fixture["logical_bytes"], fixture["directories"]),
                                 (8 + 2 + 3 + 2 + 1, 8*4096 + 2*65536 + 131071 + 131072 + 131073 + 2*1048576 + 4096, 6))
            else:
                large = "500mb" in c["id"]
                classes = ([(284, 0), (23700, 4096), (3736, 22566), (2064, 22567), (1, 131071),
                            (1, 131072), (1, 131073), (195, 1048576), (2, 33554432)] if large else
                           [(34, 0), (3950, 4096), (706, 28146), (244, 28147), (1, 131071),
                            (1, 131072), (1, 131073), (46, 1048576), (1, 8388608)])
                self.assertEqual(fixture["regular_files"], sum(count for count, _ in classes))
                self.assertEqual(fixture["logical_bytes"], sum(count*length for count, length in classes))
                self.assertEqual(fixture["directories"], (303 if large else 53) + 2 + 8 + 1)
            for row in c["steps"]:
                self.assertTrue(row["commit"])
                self.assertEqual(row["expected_commit"], "Committed")
                if c["id"] in M1:
                    cycle = (row["local_index"]-1)//5 + (1 if row["role"] == "trunk" else 2)
                    stage = (row["local_index"]-1)%5 + 1
                    self.assertEqual((row["cycle"], row["stage"]), (cycle, stage))
                    self.assertEqual(row["ordinary_edit_members"], 2 if stage == 2 else 0)
                    if stage == 2:
                        self.assertEqual(row["original_operation_counts"]["m1_observed_main_edit_targets"], 14)
                        self.assertEqual(row["original_semantic_counts"]["sdk_edit_calls"], 2)
                else:
                    base = 0 if row["role"] == "trunk" else 10 if row["role"] == "c" else 5
                    j = base + row["local_index"]
                    self.assertEqual(row["ancestral_ordinal"], j)
                    geometry = row["edit_geometry"]
                    self.assertEqual((geometry["start"], geometry["delete_len"], geometry["replacement_len"]),
                                     (4096*((j-1)%2), 256, 256))
                    self.assertEqual(geometry["payload_value"], "B" if ((j-1)//2)%2 else "A")

    def test_frozen_source_hashes(self):
        for c in self.document["cases"]:
            self.assertEqual(c["port_review"]["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
        for path, digest in self.document["cases"][0]["port_review"]["files"].items():
            content = (ROOT / path).read_bytes()
            frozen = subprocess.check_output(["git", "show", "d296981ace76fe751bebf00dee52818fe18a3eef:" + path], cwd=ROOT)
            self.assertEqual(content, frozen, path)
            self.assertEqual(hashlib.sha256(content).hexdigest(), digest, path)

    def test_shell_roles_order_descriptor_guards_and_native_scope_dispatch(self):
        with tempfile.TemporaryDirectory(prefix="fsb-branch-shell-") as temporary:
            helper = Path(temporary) / "helper"
            helper.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            helper.chmod(0o755)
            env = dict(os.environ, WORKLOAD_WRITER=str(helper), EDIT_WRITER=str(helper), WORKSPACE_RECIPE=str(helper),
                       SDK_STEP_DESCRIPTOR="/code/contexts/a/step-97/descriptor.tsv", SDK_STEP_DESCRIPTOR_SHA256="a"*64)
            def invoke(*args, environment=env):
                return subprocess.run(["bash", str(FAMILY / "workload.sh"), *args], env=environment,
                                      text=True, capture_output=True, timeout=3)
            result = invoke("stage", M1[1], "a", "97")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], [
                ["v016-m1-stage", "L100", "1", "21", "1", "branch1", "2"],
                *[["apply-context-step-prepared", M1[1], "a", "97", env["SDK_STEP_DESCRIPTOR"],
                   env["SDK_STEP_DESCRIPTOR_SHA256"], str(member)] for member in (1, 2)]])
            result = invoke("stage", M1[0], "b", "3")
            self.assertEqual(json.loads(result.stdout), ["v016-m1-stage", "L100", "1", "2", "2", "branch2", "3"])
            result = invoke("stage", COMPACT[1], "c", "10")
            self.assertEqual(json.loads(result.stdout), ["apply-context-step-prepared", COMPACT[1], "c", "10",
                                                       env["SDK_STEP_DESCRIPTOR"], env["SDK_STEP_DESCRIPTOR_SHA256"], "1"])
            result = invoke("verify-step", COMPACT[0], "trunk", "5", "/proof/root", "-")
            self.assertEqual(json.loads(result.stdout), ["verify-context", COMPACT[0], "trunk", "5", "/proof/root", "-"])
            result = invoke("verify-step", M1[0], "a", "10", "/proof/root", "/proof/modes.tsv")
            self.assertEqual(json.loads(result.stdout), ["verify-context", M1[0], "a", "10", "/proof/root", "/proof/modes.tsv"])
            for missing in ("SDK_STEP_DESCRIPTOR", "SDK_STEP_DESCRIPTOR_SHA256"):
                broken = dict(env); broken[missing] = ""
                result = invoke("stage", M1[0], "a", "2", environment=broken)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
            for args in [("stage", M1[0], "c", "1"), ("stage", COMPACT[0], "c", "1"),
                         ("stage", M1[0], "trunk", "11"), ("stage", M1[0], "a", "0"),
                         ("stage", M1[0], "a", "0002"), ("stage", M1[0], "a", "18446744073709551617")]:
                result = invoke(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""), args)


if __name__ == "__main__":
    unittest.main()
