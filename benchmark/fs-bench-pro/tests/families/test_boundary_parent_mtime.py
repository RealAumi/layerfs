"""Native automatic-parent timestamp qualification, independent of Store execution.

The caller builds or selects immutable binaries before this bounded invocation;
these explicit paths also permit the retained pre-fix executable to prove red.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[4]
CASE = "v016-boundary-alias-roundtrip-v1"
SCHEMA = "original-boundary-parent-mtime-v1"


class NativeCustody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = os.environ["LAYERFS_ALIAS_FIXTURE"]
        cls.workload = os.environ["LAYERFS_ALIAS_WORKLOAD"]
        cls.edit = os.environ["LAYERFS_ALIAS_EDIT"]

    def command(self, root, binary, *arguments):
        return subprocess.run([binary, *arguments], cwd=root, capture_output=True,
                              text=True, timeout=15)

    def test_independent_native_replay_qualification_retains_custody_and_removes_test_tree(self):
        sys.path.insert(0, str(ROOT / "benchmark/fs-bench-pro"))
        from engine import fixtures
        with tempfile.TemporaryDirectory(prefix="boundary-native-qualification-", dir=ROOT / "core/target") as temporary:
            folder = Path(temporary)
            binary = lambda path: {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            build = {"binaries": {"workspace-writer": binary(self.fixture),
                                  "workload-host": binary(self.workload), "edit-host": binary(self.edit)}}
            proof = fixtures.qualify_alias_parent({"v016_case": CASE}, folder, build)
            self.assertEqual(proof["verification_status"], "pass")
            custody = Path(proof["custody"])
            self.assertEqual(proof["custody_sha256"], hashlib.sha256(custody.read_bytes()).hexdigest())
            self.assertEqual(proof["parent_mtime_custody_sha256"], proof["custody_sha256"])
            self.assertEqual([path for path in folder.glob("alias-native-replay-*") if path.is_dir()], [])
            declared = folder / "declared"
            made = self.command(ROOT, self.fixture, "expected-step", CASE, "5", str(declared))
            self.assertEqual(made.returncode, 0, made.stderr)
            self.assertEqual((declared / "data").stat().st_mtime_ns, 1_700_000_000_000_000_000)
            self.assertNotEqual((declared / "data").stat().st_mtime_ns,
                                int(custody.read_text().splitlines()[-1].split("\t")[1])*1_000_000_000
                                + int(custody.read_text().splitlines()[-1].split("\t")[2]))

    def test_unchanged_alias_helper_roundtrip_has_exact_parent_timestamp_custody(self):
        with tempfile.TemporaryDirectory(prefix="boundary-custody-", dir=ROOT / "core/target") as temporary:
            folder = Path(temporary)
            root = folder / "tree"
            made = self.command(ROOT, self.fixture, "fixture", CASE, str(root))
            self.assertEqual(made.returncode, 0, made.stderr)
            initial_inode = (root / "data/target.bin").stat().st_ino
            for step in range(1, 5):
                applied = self.command(root, self.workload, "v016-boundary-alias", "1", str(step))
                self.assertEqual(applied.returncode, 0, applied.stderr)
                strict = self.command(root, self.edit, "verify", CASE, str(step))
                self.assertEqual(strict.returncode, 0, strict.stderr)
            applied = self.command(root, self.edit, "apply-boundary-alias", "5", self.workload)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            marker = SCHEMA + "\n"
            self.assertEqual(applied.stdout.count(marker), 1)
            body = marker + applied.stdout.split(marker, 1)[1]
            custody = folder / "parent-mtime.tsv"
            custody.write_text(body)
            observed = body.splitlines()[-1].split("\t")
            self.assertEqual(observed[0], "observed")
            expected_ns = int(observed[1])*1_000_000_000 + int(observed[2])
            self.assertEqual((root / "data").stat().st_mtime_ns, expected_ns)
            strict = self.command(root, self.edit, "verify", CASE, "5")
            self.assertNotEqual(strict.returncode, 0)
            self.assertIn("native metadata mismatch: data:", strict.stderr)
            verified = self.command(root, self.edit, "verify", CASE, "5", str(custody))
            self.assertEqual(verified.returncode, 0, verified.stderr)
            receipt = dict(line.split("=", 1) for line in verified.stdout.splitlines())
            self.assertEqual(receipt["verification_status"], "pass")
            self.assertEqual(receipt["parent_mtime_custody_sha256"], hashlib.sha256(body.encode()).hexdigest())
            target, alias = (root / "data/target.bin").stat(), (root / "data/alias.bin").stat()
            self.assertEqual((alias.st_ino, alias.st_nlink, alias.st_size), (initial_inode, 1, 131071))
            self.assertNotEqual(target.st_ino, initial_inode)
            self.assertEqual((target.st_nlink, target.st_size), (1, 131072))
            self.assertFalse((root / "data/.target.bin.tmp").exists())
            # Exact nanosecond custody must reject even an otherwise-valid automatic timestamp.
            os.utime(root / "data", ns=(expected_ns + 1, expected_ns + 1))
            mismatch = self.command(root, self.edit, "verify", CASE, "5", str(custody))
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("native metadata mismatch: data:", mismatch.stderr)
            os.utime(root / "data", ns=(expected_ns, expected_ns))
            target_path = root / "data/target.bin"
            target_path.chmod(0o600)
            wrong_mode = self.command(root, self.edit, "verify", CASE, "5", str(custody))
            self.assertNotEqual(wrong_mode.returncode, 0)
            self.assertIn("native metadata mismatch: data/target.bin", wrong_mode.stderr)
            target_path.chmod(0o640)
            os.utime(root / "data/witness.bin", ns=(1_700_000_000_000_000_001,)*2)
            wrong_time = self.command(root, self.edit, "verify", CASE, "5", str(custody))
            self.assertNotEqual(wrong_time.returncode, 0)
            self.assertIn("native metadata mismatch: data/witness.bin", wrong_time.stderr)
            os.utime(root / "data/witness.bin", ns=(1_700_000_000_000_000_000,)*2)
            with target_path.open("r+b") as payload:
                byte = payload.read(1)
                payload.seek(0)
                payload.write(bytes([byte[0] ^ 1]))
            os.utime(target_path, ns=(1_700_000_000_000_000_000,)*2)
            corrupted = self.command(root, self.edit, "verify", CASE, "5", str(custody))
            self.assertNotEqual(corrupted.returncode, 0)
            self.assertIn("native content mismatch: data/target.bin", corrupted.stderr)


if __name__ == "__main__":
    unittest.main()
