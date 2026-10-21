"""Independent proof catches bytes, namespace and hard-link mistakes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("new_oracle", BENCH / "engine/oracle.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


class Oracle(unittest.TestCase):
    def trees(self, folder):
        roots = [folder / name for name in ("expected-root", "actual-root")]
        for root in roots:
            root.mkdir()
            (root / "a").write_bytes(b"exact bytes")
            (root / "b").hardlink_to(root / "a")
        return roots

    def test_same_tree_passes_and_different_payload_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            expected, actual = self.trees(home)
            oracle.snapshot(expected, "C01", home / "expected")
            oracle.snapshot(actual, "C01", home / "actual")
            self.assertEqual(oracle.compare_recorded(home / "expected", home / "actual", "C01")["status"], "PASS")
            (actual / "a").write_bytes(b"wrong bytes")
            oracle.snapshot(actual, "C01", home / "changed")
            self.assertEqual(oracle.compare_recorded(home / "expected", home / "changed", "C01")["status"], "FAIL")

    def test_missing_alias_and_unexpected_path_are_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            expected, actual = self.trees(home)
            oracle.snapshot(expected, "C01", home / "expected")
            (actual / "b").unlink()
            (actual / "b").write_bytes(b"exact bytes")
            (actual / "unexpected").write_bytes(b"new")
            oracle.snapshot(actual, "C01", home / "actual")
            result = oracle.compare_recorded(home / "expected", home / "actual", "C01")
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any(row.get("reason") == "hard-link equivalence classes" for row in result["comparison"]["differences"]))

    def test_tampered_raw_observation_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            expected, actual = self.trees(home)
            oracle.snapshot(expected, "C01", home / "expected")
            oracle.snapshot(actual, "C01", home / "actual")
            with (home / "actual/tree.jsonl").open("a") as stream:
                stream.write("{}\n")
            with self.assertRaisesRegex(ValueError, "case/hash differs"):
                oracle.compare_recorded(home / "expected", home / "actual", "C01")
