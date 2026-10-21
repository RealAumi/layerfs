"""Exact-source sample custody; no sample execution or product effects."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import receipts

class ClaimScope(unittest.TestCase):
    def test_exact_source_refuses_replay_and_new_source_retains_both_claims(self):
        treatment = {"case": "same-case", "product": "same", "binary": "same"}
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            first = home / receipts.sample_claim_key(treatment, "source-one")
            first.write_text("original sample")
            with self.assertRaises(FileExistsError):
                first.open("x")
            second = home / receipts.sample_claim_key(treatment, "source-two")
            with second.open("x") as stream:
                stream.write("new source sample")
            self.assertEqual(first.read_text(), "original sample")
            self.assertNotEqual(first, second)
            self.assertEqual(receipts.sample_claim_key(treatment, "source-two"), second.name)
