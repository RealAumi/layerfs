"""Tooling failure evidence must remain exact and append-only."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BENCH = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("receipts", BENCH / "engine/receipts.py")
receipts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipts)


class ReceiptCustody(unittest.TestCase):
    def test_nonzero_child_keeps_exact_failure_and_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "exit 7"):
                receipts.command([sys.executable, "-c", "import sys; print('original'); sys.exit(7)"],
                                 folder, "original", 2)
            row = json.loads((folder / "original.completion.json").read_text())
            self.assertEqual((row["status"], row["exit_code"], row["attempts"]), ("FAIL", 7, 1))
            self.assertEqual((folder / "original.stdout").read_text(), "original\n")
            with self.assertRaises(FileExistsError):
                receipts.command([sys.executable, "-c", "raise SystemExit(0)"], folder, "original", 2)

    def test_timeout_preserves_original_exception_and_no_remote_cancellation_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaises(subprocess.TimeoutExpired):
                receipts.command([sys.executable, "-c", "import time; time.sleep(30)"],
                                 folder, "bounded", 0.1)
            row = json.loads((folder / "bounded.completion.json").read_text())
            self.assertTrue(row["timeout"])
            self.assertEqual(row["original_failure_type"], "TimeoutExpired")
            self.assertIn("NOT_ESTABLISHED", row["remote_cancellation"])

    def test_known_checker_refusal_remains_a_failure_record(self):
        with tempfile.TemporaryDirectory() as directory:
            row = receipts.command([sys.executable, "-c", "raise SystemExit(1)"],
                                   directory, "checker", 2, allow_failure=True)
            self.assertEqual((row["status"], row["exit_code"]), ("FAIL", 1))

    def test_manifest_detects_retained_evidence_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "raw").write_bytes(b"original")
            receipts.manifest(folder)
            receipts.verify_manifest(folder)
            (folder / "raw").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "retained evidence changed"):
                receipts.verify_manifest(folder)
            with self.assertRaises(FileExistsError):
                receipts.manifest(folder)
