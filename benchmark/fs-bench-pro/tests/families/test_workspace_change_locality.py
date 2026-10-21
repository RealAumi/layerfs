"""Original locality membership and independent ordinary-write qualification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/workspace_change_locality"
sys.path.insert(0, str(BENCH))
from engine import identity


class WorkspaceChangeLocality(unittest.TestCase):
    def test_original_membership_control_only_and_frozen_pins(self):
        family = json.loads((FAMILY / "family.json").read_text())
        kinds = ("workspace-clean-commit", "workspace-fixed-move",
                 "workspace-distributed-sdk-edit", "workspace-dense-rewrite")
        expected = [f"{kind}-{tier}-{'compact-v2' if tier <= 10 else 'mixed-v4'}"
                    for kind in kinds for tier in (1, 100, 500)]
        self.assertEqual([row["id"] for row in family["cases"]], expected)
        pinned = subprocess.check_output(["git", "rev-parse", "reference-v0.1.6-final^{commit}"],
                                         cwd=ROOT, text=True).strip()
        for row in family["cases"]:
            clean = row["registry"]["kind"] == "workspace-clean-commit"
            distributed = row["registry"]["kind"] == "workspace-distributed-sdk-edit"
            self.assertEqual(row["status"], "ported")
            self.assertEqual(row["fixture"]["recipe"], row["id"])
            self.assertEqual(row["fixture"]["seed"], 1)
            self.assertEqual(row["control_only"], clean)
            self.assertEqual(row["ordinary_sdk_edits"], distributed)
            self.assertTrue(row["original_ordinary_guards"])
            self.assertEqual(row["steps"], [] if clean else [{"run": "workload.sh apply " + row["id"], "commit": True}])
            self.assertEqual(row["expected_commit"], "UpToDate" if clean else "Committed")
            self.assertEqual(row["budget"], {"command_ms": 15000, "verifier_ms": 45000,
                "operation_watchdog_ms": 120000, "verification_hard_watchdog_ms": 59000})
            self.assertEqual(row["port_review"]["source_commit"], pinned)
            for name, digest in row["port_review"]["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
            if distributed:
                plan = row["port_review"]["sdk_edit_plan"]
                self.assertEqual(plan["members"], int(row["registry"]["tier"]))
                self.assertEqual((plan["offset"], plan["delete_bytes"], plan["replacement_bytes"]), (0, 4096, 4096))

    def test_clean_workload_refuses_exec_before_invoking_any_writer(self):
        result = subprocess.run(["bash", str(FAMILY / "workload.sh"), "apply", "workspace-clean-commit-1-compact-v2"],
            env={**os.environ, "WORKLOAD_WRITER": "/writer-must-never-be-executed"},
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("control_only with no Exec", result.stderr)


@unittest.skipUnless(os.environ.get("FS_BENCH_TEST_BUILD"), "native qualification requires the new committed compiled writer seal")
class NativeDistributedLocality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = identity.load_build(Path(os.environ["FS_BENCH_TEST_BUILD"]))
        cls.binaries = cls.build["binaries"]
        cls.temp = tempfile.TemporaryDirectory(prefix="locality-writer-native-", dir=ROOT / "core/target")
        cls.folder = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def fixture(self, case, name):
        root = self.folder / name
        result = subprocess.run([self.binaries["workspace-writer"]["path"], "fixture", case, str(root)],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return root

    def apply(self, root, case):
        return subprocess.run([self.binaries["edit-host"]["path"], "apply-workspace", case],
                              cwd=root, capture_output=True, text=True, timeout=15)

    def verify(self, root, case):
        return subprocess.run([self.binaries["workload-host"]["path"], "workspace-verify-tree", case, "1", "1"],
                              cwd=root, capture_output=True, text=True, timeout=15)

    def test_original_compact_replacements_keep_identity_suffix_and_background(self):
        for tier in (1,):
            with self.subTest(tier=tier):
                case = f"workspace-distributed-sdk-edit-{tier}-compact-v2"
                root = self.fixture(case, f"tier-{tier}")
                files = {path.relative_to(root): (path.read_bytes(), path.stat())
                         for path in root.rglob("*") if path.is_file()}
                root_mode, root_mtime = root.stat().st_mode, root.stat().st_mtime_ns
                applied = self.apply(root, case)
                self.assertEqual(applied.returncode, 0, applied.stderr)
                self.assertIn(f"ordinary_edit_write_bytes={tier*4096}", applied.stderr)
                self.assertIn("ordinary_edit_truncates=0", applied.stderr)
                self.assertIn("ordinary_edit_reads=0", applied.stderr)
                changed = []
                for relative, (original, metadata) in files.items():
                    path = root / relative
                    actual = path.read_bytes()
                    self.assertEqual(path.stat().st_ino, metadata.st_ino)
                    self.assertEqual(path.stat().st_mode, metadata.st_mode)
                    self.assertEqual(path.stat().st_mtime_ns, metadata.st_mtime_ns)
                    if actual != original:
                        changed.append(relative)
                        self.assertEqual(actual, bytes(value ^ 0x5a for value in original[:4096]) + original[4096:])
                self.assertEqual(len(changed), tier)
                self.assertTrue(all(path.name == "f128.dat" for path in changed))
                self.assertEqual((root.stat().st_mode, root.stat().st_mtime_ns), (root_mode, root_mtime))
                verified = self.verify(root, case)
                self.assertEqual(verified.returncode, 0, verified.stderr)
                self.assertIn("verification_status=pass", verified.stdout)
                corrupted = root / changed[0]
                timestamp = corrupted.stat().st_mtime_ns
                with corrupted.open("r+b") as stream:
                    stream.seek(-1, 2)
                    byte = stream.read(1)
                    stream.seek(-1, 2)
                    stream.write(bytes([byte[0] ^ 1]))
                os.utime(corrupted, ns=(timestamp, timestamp))
                rejected = self.verify(root, case)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn("native content mismatch", rejected.stderr)

    def test_wrong_selected_length_refuses_before_mutation(self):
        case = "workspace-distributed-sdk-edit-1-compact-v2"
        root = self.fixture(case, "bad-selected-length")
        target = root / "regular/s000/f128.dat"
        with target.open("r+b") as stream:
            stream.truncate(target.stat().st_size - 1)
        before = target.read_bytes()
        rejected = self.apply(root, case)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("target fixture length differs", rejected.stderr)
        self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
