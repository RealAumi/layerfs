"""Frozen M1 schedule, fixture arithmetic and ordinary shell member order."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/mixed_load_bearing"
SOURCE = "d296981ace76fe751bebf00dee52818fe18a3eef"
TAG = "ae3310fada4a1fe35cb99ab02270b7538a0d03f7"
EPISODES = [f"agent-episodes-{tier}" + ("-compact-v2" if tier <= 10 else "")
            for tier in (1, 100, 500)]
REGULAR = [f"v016-mixed-development-{load}-k{commits}-v1"
           for load in ("100mb-5000", "500mb-30000") for commits in (10, 100)]
EXHAUSTIVE = [f"v016-mixed-exhaustive-{load}-k100-v1"
              for load in ("100mb-5000", "500mb-30000")]


def episode_census(tier):
    """Independent path inventory from the frozen shard/name shape."""
    compact = tier <= 10
    shards, cells = (tier, tier) if compact else (64, 500)
    ordinals = list(range(32)) + list(range(64, 80)) + [128, 199] if compact else range(200)
    paths, directories = set(), {".", "background/dest", "cells", "finished"}
    spine = "/".join(f"d{depth:03}" for depth in range(1, 129))
    for shard in range(shards):
        for ordinal in ordinals:
            if ordinal < 64:
                path = f"background/wide/s{shard:03}-f{ordinal:03}.dat"
            elif ordinal < 199:
                path = f"background/regular/s{shard:03}/f{ordinal:03}.dat"
            else:
                path = f"background/spine/{spine}/s{shard:03}.dat"
            paths.add(path)
    for cell in range(cells):
        for name in ("source.bin", "edit.bin", "replacement.bin", "alias.bin"):
            paths.add(f"cells/e{cell:03}/{name}")
    for path in [*paths, *directories]:
        parent = PurePosixPath(path).parent
        while str(parent) != ".":
            directories.add(str(parent))
            parent = parent.parent
    return paths, directories, shards, cells


class MixedLoadBearing(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FAMILY / "family.json").read_text())

    def test_original_selection_and_independent_fixture_census(self):
        rows = self.document["cases"]
        self.assertEqual(self.document["family"], "mixed_load_bearing")
        self.assertEqual([row["id"] for row in rows], EPISODES + REGULAR + EXHAUSTIVE)
        for row in rows[:len(EPISODES)]:
            tier = int(row["registry"]["tier"])
            paths, directories, shards, cells = episode_census(tier)
            fixture = row["fixture"]
            self.assertEqual(fixture["paths"], len(paths) + len(directories))
            self.assertEqual(fixture["directories"], len(directories))
            self.assertEqual(fixture["hardlink_names"], cells)
            self.assertEqual(fixture["regular_files"], len(paths) - cells)
            self.assertEqual(fixture["logical_bytes"], shards * 1048576 + cells * 32768)
            self.assertEqual(row["operation_model"]["final_paths"], fixture["paths"] + 2 * tier)
            self.assertEqual(row["original_operation_counts"], {"completed_episode_count": tier})
        for row in rows[len(EPISODES):]:
            large = "500mb" in row["id"]
            # Independent frozen class rows: empty, tiny, two medium classes,
            # exact boundary triple, moderate large and anchors.
            classes = ([(284, 0), (23700, 4096), (3736, 22566), (2064, 22567),
                        (1, 131071), (1, 131072), (1, 131073), (195, 1048576), (2, 33554432)]
                       if large else [(34, 0), (3950, 4096), (706, 28146), (244, 28147),
                                      (1, 131071), (1, 131072), (1, 131073), (46, 1048576), (1, 8388608)])
            count = sum(count for count, _ in classes)
            logical = sum(count * length for count, length in classes)
            fixture = row["fixture"]
            self.assertEqual((fixture["regular_files"], fixture["logical_bytes"]), (count, logical))
            self.assertEqual(fixture["directories"], (303 if large else 53) + 2 + 8 + 1)
            self.assertEqual(fixture["paths"], count + fixture["directories"])
            self.assertEqual(fixture["max_non_directory_names"], count + 16)
            self.assertEqual(fixture["max_logical_path_bytes"], logical + 65536)
            self.assertEqual((fixture["max_non_directory_names"], fixture["max_logical_path_bytes"]),
                             (30000, 500000000) if large else (5000, 100000000))

    def test_original_commit_order_selected_roots_and_watchdogs(self):
        for row in self.document["cases"]:
            self.assertEqual(row["status"], "ported")
            self.assertTrue(row["original_ordinary_guards"])
            self.assertEqual(row["fixture"]["recipe"], row["id"])
            self.assertIn("INELIGIBLE under strict H-5", row["cache_contract"]["numeric_result"])
            if row["id"] in EPISODES:
                self.assertEqual(row["cache_class"], "B")
                self.assertEqual(len(row["steps"]), 1)
                self.assertEqual(row["budget"], {"command_ms": 15000, "verifier_ms": 45000,
                                                "operation_watchdog_ms": 120000,
                                                "verification_hard_watchdog_ms": 59000})
                continue
            commits = 100 if "-k100-" in row["id"] else 10
            self.assertEqual(row["cache_class"], "C")
            self.assertEqual(len(row["steps"]), commits)
            self.assertEqual(row["history_schedule"]["commits"], commits)
            self.assertEqual(row["history_schedule"]["state_count"], commits + 1)
            self.assertEqual(row["history_schedule"]["step_base"], 1)
            self.assertIs(row["history_schedule"]["global_commit_census"], True)
            exhaustive = row["id"] in EXHAUSTIVE
            self.assertEqual(row["history_schedule"]["verification_steps"],
                             list(range(5, 101, 5)) if exhaustive else [commits])
            for ordinal, step in enumerate(row["steps"], 1):
                stage = (ordinal - 1) % 5 + 1
                self.assertEqual((step["index"], step["cycle"], step["stage"]),
                                 (ordinal, (ordinal - 1) // 5 + 1, stage))
                self.assertTrue(step["commit"])
                self.assertEqual(step["original_operation_counts"]["m1_stage"], stage)
                self.assertEqual(step["ordinary_edit_members"], 2 if stage == 2 else 0)
                if stage == 2:
                    self.assertEqual(step["original_operation_counts"]["m1_observed_main_edit_targets"], 14)
                    self.assertEqual(step["original_semantic_counts"]["sdk_edit_calls"], 2)
                    self.assertNotIn("sdk_edit_calls", step["original_operation_counts"])
            if exhaustive:
                original = 300000 if "500mb" in row["id"] else 120000
                self.assertTrue(row["proof_only"])
                self.assertIsNone(row["budget"]["command_ms"])
                self.assertEqual(row["budget"]["verifier_ms"], original)
                self.assertEqual(row["owner_test_ceiling_ms"], 275000 if row["id"] == "v016-mixed-exhaustive-500mb-30000-k100-v1" else 120000)
                self.assertIn("VERIFY-ONLY", row["performance_mode"])
            else:
                self.assertEqual(row["budget"]["command_ms"], 15000)
                self.assertEqual(row["budget"]["performance_hard_watchdog_ms"], 60000)
                # Owner direction 2026-10-12 (#319 phase 13): the two named 500 MiB development cases only.
                self.assertEqual((row["budget"]["verifier_ms"], row["budget"]["verification_hard_watchdog_ms"]),
                                 (50000, 60000) if "500mb" in row["id"] else (25000, 35000))
                self.assertEqual(row["budget"]["verification_cleanup_reserve_ms"], 3000)

    def test_recovery_source_hashes_and_ordered_shell_members(self):
        for row in self.document["cases"]:
            review = row["port_review"]
            self.assertEqual((review["source_commit"], review["source_tag_object"]), (SOURCE, TAG))
        for name, digest in self.document["cases"][0]["port_review"]["files"].items():
            current = (ROOT / name).read_bytes()
            frozen = subprocess.check_output(["git", "show", SOURCE + ":" + name], cwd=ROOT)
            self.assertEqual(current, frozen, name)
            self.assertEqual(hashlib.sha256(current).hexdigest(), digest, name)
        with tempfile.TemporaryDirectory(prefix="fsb-mixed-shell-") as temporary:
            path = Path(temporary)
            helper = path / "helper"
            helper.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            helper.chmod(0o755)
            environment = dict(__import__("os").environ, WORKLOAD_WRITER=str(helper), EDIT_WRITER=str(helper))
            environment.update(SDK_STEP_DESCRIPTOR="", SDK_STEP_DESCRIPTOR_SHA256="")
            identity = REGULAR[0]
            for step in (1, 2, 7, 10):
                result = subprocess.run(["bash", str(FAMILY / "workload.sh"), "stage", identity, str(step)],
                                        capture_output=True, text=True, env=environment, check=True, timeout=3)
                invocations = [json.loads(line) for line in result.stdout.splitlines()]
                expected = [["v016-m1-stage", "L100", "1", str((step - 1) // 5 + 1), "0", "branch0", str((step - 1) % 5 + 1)]]
                if step in (2, 7):
                    expected.extend([["apply-sdk-step", identity, str(step), str(member)] for member in (1, 2)])
                self.assertEqual(invocations, expected)
            prepared = dict(environment, SDK_STEP_DESCRIPTOR="/code/history/payloads/step-2/descriptor.tsv",
                            SDK_STEP_DESCRIPTOR_SHA256="a" * 64)
            result = subprocess.run(["bash", str(FAMILY / "workload.sh"), "stage", identity, "2"],
                                    capture_output=True, text=True, env=prepared, check=True, timeout=3)
            self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], [
                ["v016-m1-stage", "L100", "1", "1", "0", "branch0", "2"],
                *[["apply-sdk-step-prepared", identity, "2", prepared["SDK_STEP_DESCRIPTOR"],
                   prepared["SDK_STEP_DESCRIPTOR_SHA256"], str(member)] for member in (1, 2)],
            ])
            for missing in ("SDK_STEP_DESCRIPTOR", "SDK_STEP_DESCRIPTOR_SHA256"):
                incomplete = dict(prepared)
                incomplete[missing] = ""
                rejected = subprocess.run(["bash", str(FAMILY / "workload.sh"), "stage", identity, "2"],
                                          capture_output=True, text=True, env=incomplete, timeout=3)
                self.assertEqual(rejected.returncode, 2)
                self.assertEqual(rejected.stdout, "")
            invalid = subprocess.run(["bash", str(FAMILY / "workload.sh"), "stage", identity, "11"],
                                     capture_output=True, text=True, env=environment, timeout=3)
            self.assertEqual(invalid.returncode, 2)
            self.assertEqual(invalid.stdout, "")


if __name__ == "__main__":
    unittest.main()
