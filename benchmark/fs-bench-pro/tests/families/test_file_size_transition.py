"""Freeze the original seven boundary schedules and retain unresolved scope."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "benchmark/fs-bench-pro/families/file_size_transition"


class Definition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition = json.loads((FAMILY / "family.json").read_text())
        cls.cases = cls.definition["cases"]

    def test_all_frozen_cases_and_original_source_seals_are_preserved(self):
        source = ROOT / "benchmark/fs-bench-pro/families/file_size_transition/mod.rs"
        originals = re.findall(r'const [A-Z_]+: &str = "(v016-boundary-[^"]+)";', source.read_text())
        self.assertEqual([case["id"] for case in self.cases], originals)
        self.assertEqual(len(set(originals)), 7)
        for case in self.cases:
            self.assertEqual(case["v016_case"], case["id"])
            self.assertEqual(case["fixture"]["seed"], 1)
            review = case["port_review"]
            self.assertEqual(review["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
            for name, wanted in review["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), wanted)

    def test_exact_operations_lengths_and_commit_topology(self):
        lengths = {"small-control": [4096]*3, "below": [131071]*3,
                   "exact": [131072]*3, "above": [131073]*3,
                   "large-control": [1048576]*3,
                   "roundtrip": [131071,131072,131073,131072,131071],
                   "alias-roundtrip": [131071,131072,131073,131072,131071,131072]}
        for case in self.cases:
            name = case["id"].removeprefix("v016-boundary-").removesuffix("-v1")
            states, steps = case["history_schedule"]["states"], case["steps"]
            self.assertEqual([row["target_bytes"] for row in states], lengths[name])
            self.assertEqual(case["history_schedule"]["commits"], len(lengths[name])-1)
            self.assertEqual(case["history_schedule"]["verification_steps"], list(range(len(lengths[name]))))
            self.assertTrue(case["history_schedule"]["allow_repeated_root_identities"])
            self.assertEqual([row["index"] for row in steps], list(range(1, len(lengths[name]))))
            self.assertTrue(all(row["commit"] and row["expected_commit"] == "Committed" for row in steps))
            if name == "alias-roundtrip":
                self.assertEqual([row["operation"] for row in steps], ["alias-append", "target-append", "alias-truncate", "target-truncate", "atomic-replace"])
                self.assertEqual([row["path"] for row in steps], ["data/alias.bin", "data/target.bin", "data/alias.bin", "data/target.bin", "data/target.bin"])
                self.assertEqual(states[-1]["alias_bytes"], 131071)
                self.assertEqual(steps[-1]["replacement_bytes"], 131072)
            elif name == "roundtrip":
                self.assertEqual([(row["start"], row["delete_len"], row["replacement_bytes"]) for row in steps], [(131071,0,1),(131072,0,1),(131072,1,0),(131071,1,0)])
            else:
                self.assertEqual([(row["start"], row["delete_len"], row["replacement_bytes"]) for row in steps], [(0,256,256),(2048,256,256)])

    def test_frozen_budgets_exact_exclusive_cutoff_and_honest_cache_scope(self):
        for case in self.cases:
            self.assertEqual(case["budget"], {"command_ms":15000, "performance_hard_watchdog_ms":60000,
                "operation_watchdog_ms":60000, "verifier_ms":25000, "verification_hard_watchdog_ms":35000})
            guard = case["original_v016_guards"]
            self.assertEqual((guard["cleanup_reserve_ms"], guard["verification_worker_work_ms"], guard["publication_guard_seconds"]), (3000,22000,0.25))
            self.assertEqual(case["cache_class"], "C")
            self.assertEqual(case["cache_contract"]["independent_own_write_pre_Commit_coldness"], "UNAVAILABLE")
            for state in case["history_schedule"]["states"]:
                self.assertEqual(state["target_representation"], "WholeFile" if state["target_bytes"] < 131072 else "Chunked")
            if case["fixture"]["alias"]:
                self.assertTrue(any("no parent-directory normalization" in row["what"] for row in case["differences"]))
                self.assertIn("parent-mtime incompatibility", case["port_review"]["oracle_coverage"])
                self.assertEqual(case["automatic_parent_mtime"]["native_precision_allowance_ns"], 1_000_000_000)
                self.assertEqual(case["automatic_parent_mtime"]["max_operation_ns"], 60_000_000_000)
            else:
                self.assertNotIn("automatic_parent_mtime", case)


class PreparedRoute(unittest.TestCase):
    def test_original_native_fallback_and_bound_prepared_route_keep_args_and_refuse_missing_seal(self):
        with tempfile.TemporaryDirectory() as temporary:
            writer = Path(temporary) / "writer"
            writer.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
            writer.chmod(0o755)
            environment = {key: value for key, value in os.environ.items()
                           if key not in ("SDK_STEP_DESCRIPTOR", "SDK_STEP_DESCRIPTOR_SHA256")}
            environment.update(EDIT_WRITER=str(writer), WORKLOAD_WRITER=str(writer))
            case = "v016-boundary-roundtrip-v1"
            def invoke(selected_case, env):
                return subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), "apply", selected_case, "2"],
                                      env=env, capture_output=True, text=True, timeout=10)
            native = invoke(case, environment)
            self.assertEqual(native.returncode, 0, native.stderr)
            self.assertEqual(json.loads(native.stdout), ["apply-sdk-step", case, "2"])
            bound = {**environment, "SDK_STEP_DESCRIPTOR": "/code/history/payloads/step-2/descriptor.tsv",
                     "SDK_STEP_DESCRIPTOR_SHA256": "a"*64}
            prepared = invoke(case, bound)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(json.loads(prepared.stdout), ["apply-sdk-step-prepared", case, "2",
                bound["SDK_STEP_DESCRIPTOR"], bound["SDK_STEP_DESCRIPTOR_SHA256"]])
            refused = invoke(case, {**environment, "SDK_STEP_DESCRIPTOR": bound["SDK_STEP_DESCRIPTOR"]})
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(refused.stdout, "")
            alias = invoke("v016-boundary-alias-roundtrip-v1", bound)
            self.assertEqual(alias.returncode, 0, alias.stderr)
            self.assertEqual(json.loads(alias.stdout), ["v016-boundary-alias", "1", "2"])
            wrapped = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), "apply",
                                      "v016-boundary-alias-roundtrip-v1", "5"],
                                     env=bound, capture_output=True, text=True, timeout=10)
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr)
            self.assertEqual(json.loads(wrapped.stdout), ["apply-boundary-alias", "5", str(writer)])
            custody = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), "verify",
                                      "v016-boundary-alias-roundtrip-v1", "5", "/code/history/custody.tsv"],
                                     env=bound, capture_output=True, text=True, timeout=10)
            self.assertEqual(custody.returncode, 0, custody.stderr)
            self.assertEqual(json.loads(custody.stdout), ["verify", "v016-boundary-alias-roundtrip-v1", "5", "/code/history/custody.tsv"])


class NativeAlias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "benchmark/fs-bench-pro"))
        from engine import identity
        build = identity.load_build(Path(os.environ["LAYERFS_EDIT_WRITER_BUILD"]))
        cls.fixture = build["binaries"]["workspace-writer"]["path"]
        cls.workload = build["binaries"]["workload-host"]["path"]
        cls.edit = build["binaries"]["edit-host"]["path"]

    def test_unchanged_alias_schedule_preserves_bytes_classes_and_strict_metadata_refusal(self):
        case = "v016-boundary-alias-roundtrip-v1"
        with tempfile.TemporaryDirectory(prefix="boundary-alias-native-", dir=ROOT / "core/target") as temporary:
            base = Path(temporary); root = base / "actual"; expected = base / "expected"
            fixture = subprocess.run([self.fixture, "fixture", case, str(root)],
                                     capture_output=True, text=True, timeout=15)
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            original = (root / "data/target.bin").stat().st_ino
            witness = (root / "data/witness.bin").read_bytes()
            for step in range(1, 6):
                changed = subprocess.run([self.workload, "v016-boundary-alias", "1", str(step)], cwd=root,
                                         capture_output=True, text=True, timeout=15)
                self.assertEqual(changed.returncode, 0, changed.stderr)
                target, alias = (root / "data/target.bin").stat(), (root / "data/alias.bin").stat()
                self.assertEqual(alias.st_ino, original)
                self.assertEqual((root / "data/witness.bin").read_bytes(), witness)
                verified = subprocess.run([self.edit, "verify", case, str(step)], cwd=root,
                                          capture_output=True, text=True, timeout=15)
                if step < 5:
                    self.assertEqual((target.st_ino, target.st_nlink, alias.st_nlink), (original, 2, 2))
                    self.assertEqual(verified.returncode, 0, verified.stderr)
                else:
                    self.assertNotEqual(target.st_ino, original)
                    self.assertEqual((target.st_nlink, alias.st_nlink, target.st_size, alias.st_size), (1,1,131072,131071))
                    self.assertNotEqual(verified.returncode, 0)
                    self.assertIn("native metadata mismatch: data:", verified.stderr)
            materialized = subprocess.run([self.fixture, "expected-step", case, "5", str(expected)],
                                          capture_output=True, text=True, timeout=15)
            self.assertEqual(materialized.returncode, 0, materialized.stderr)
            for name in ("target.bin", "alias.bin", "witness.bin"):
                actual_file, declared_file = root / "data" / name, expected / "data" / name
                self.assertEqual(actual_file.read_bytes(), declared_file.read_bytes())
                self.assertEqual(actual_file.stat().st_mode & 0o7777, 0o640)
                self.assertEqual(actual_file.stat().st_mtime_ns, 1700000000000000000)
            self.assertFalse((root / "data/.target.bin.tmp").exists())
            self.assertNotEqual((root / "data").stat().st_mtime_ns, (expected / "data").stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
