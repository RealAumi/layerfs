"""Proof-only performance N/A must not hide case inapplicability."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import receipts


class NotApplicableReporting(unittest.TestCase):
    def test_unattempted_proof_keeps_not_applicable_and_original_missing_capability(self):
        selection = {"family":"workspace_reliability", "source_commit":"source", "product_tree":"product",
                     "cases":[{"id":"workspace-lease-lifecycle-compact-v2-proof", "proof_only":True,
                               "status":"not-applicable", "not_applicable_reason":"mandatory exact Workspace physical peak unavailable",
                               "budget":{"verifier_ms":45000}}]}
        performance, verification = receipts.result_rows(selection, {})
        for field in receipts.PROOF_ONLY_PERFORMANCE_COLUMNS:
            self.assertEqual(performance[0][field], "N/A")
        self.assertEqual(verification[0]["proof_status"], "NOT_APPLICABLE")
        self.assertEqual(verification[0]["proof_wall_ns"], "UNAVAILABLE")
        self.assertEqual(verification[0]["declared_limit_ns"], 45000000000)
        self.assertIn("physical peak unavailable", verification[0]["tag"])

    def test_unexpected_failed_receipt_cannot_be_masked_by_na_registration(self):
        selection = {"family":"workspace_reliability", "source_commit":"source", "product_tree":"product",
                     "cases":[{"id":"workspace-lease-lifecycle-compact-v2-proof", "proof_only":True,
                               "status":"not-applicable", "not_applicable_reason":"mandatory physical peak unavailable",
                               "budget":{"verifier_ms":45000}}]}
        _, verification = receipts.result_rows(selection, {selection["cases"][0]["id"]:
            {"status":"FAIL", "original_failure":"unexpected attempted operation failed"}})
        self.assertEqual(verification[0]["proof_status"], "NOT_RUN")
        self.assertIn("original overall result FAIL", verification[0]["tag"])
        self.assertIn("unexpected attempted operation failed", verification[0]["tag"])


if __name__ == "__main__":
    unittest.main()
