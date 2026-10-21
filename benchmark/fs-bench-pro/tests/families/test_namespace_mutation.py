"""Frozen namespace-family coverage and native syscall transcript qualification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/namespace_mutation"


class NamespaceMutation(unittest.TestCase):
    def test_original_membership_profiles_and_review_pins(self):
        family = json.loads((FAMILY / "family.json").read_text())
        expected = [
            "namespace-subtree-relocate-delete-1-compact-v2",
            "namespace-subtree-relocate-delete-100-mixed-v4",
            "namespace-subtree-relocate-delete-500-mixed-v4",
        ]
        self.assertEqual([row["id"] for row in family["cases"]], expected)
        pinned = subprocess.check_output(
            ["git", "rev-parse", "reference-v0.1.6-final^{commit}"], cwd=ROOT, text=True
        ).strip()
        for row in family["cases"]:
            self.assertEqual(row["status"], "ported")
            self.assertEqual(row["fixture"]["recipe"], row["v016_case"])
            self.assertEqual(row["fixture"]["seed"], 1)
            self.assertEqual(row["steps"], [{"run": "workload.sh apply " + row["id"], "commit": True}])
            self.assertEqual(row["expected_commit"], "Committed")
            self.assertEqual(row["budget"]["command_ms"], 15000)
            self.assertEqual(row["budget"]["verifier_ms"], 45000)
            self.assertEqual(row["budget"]["verification_hard_watchdog_ms"], 59000)
            self.assertEqual(row["port_review"]["source_commit"], pinned)
            for name, digest in row["port_review"]["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)

    def test_native_transcript_preserves_move_and_deletion_and_rejects_bad_bytes(self):
        build_path = os.environ.get("FS_BENCH_TEST_BUILD")
        self.assertTrue(build_path, "qualification requires the sealed reused build path")
        build = json.loads((Path(build_path) / "build.json").read_text())
        binaries = build["binaries"]
        for name in ("workspace-writer", "workload-host"):
            self.assertEqual(hashlib.sha256(Path(binaries[name]["path"]).read_bytes()).hexdigest(),
                             binaries[name]["sha256"])
        case = "namespace-subtree-relocate-delete-1-compact-v2"
        with tempfile.TemporaryDirectory(prefix="fs-bench-native-namespace-") as temporary:
            root = Path(temporary) / "fixture"
            fixture = subprocess.run([binaries["workspace-writer"]["path"], "fixture", case, str(root)],
                                     capture_output=True, text=True, timeout=10, check=True)
            data = json.loads(fixture.stdout)
            self.assertEqual(data["files"], 250)
            self.assertEqual(data["logical_bytes"], 551200)
            original = (root / "source/tree-a/s000/f000.dat").read_bytes()
            background = (root / "background/d000/f000000.dat").read_bytes()
            environment = {**os.environ, "WORKLOAD_WRITER": binaries["workload-host"]["path"]}
            applied = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), "apply", case],
                                     cwd=root, env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertFalse((root / "source/tree-a").exists())
            self.assertFalse((root / "source/tree-b").exists())
            self.assertEqual((root / "destination/moved-a/s000/f000.dat").read_bytes(), original)
            self.assertEqual((root / "background/d000/f000000.dat").read_bytes(), background)
            proof = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), "verify", case],
                                   cwd=root, env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(proof.returncode, 0, proof.stderr)
            self.assertIn("verification_status=pass", proof.stdout)
            target = root / "destination/moved-a/s000/f000.dat"
            metadata = target.stat()
            target.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            rejected = subprocess.run(["/bin/bash", str(FAMILY / "workload.sh"), "verify", case],
                                      cwd=root, env=environment, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("native content mismatch: destination/moved-a/s000/f000.dat at 0", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
