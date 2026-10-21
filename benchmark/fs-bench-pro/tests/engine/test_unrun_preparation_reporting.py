"""Failed preparation is visible beside an unattempted actual case."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import receipts


class UnrunPreparationReporting(unittest.TestCase):
    def source(self):
        selected = {"family":"repository_history", "source_commit":"source", "product_tree":"product",
                    "image":"image", "cases":[{"id":"deepseek-full", "status":"ported", "proof_only":False}]}
        result = {"schema":"fs-bench-pro-unrun-preparation-closure-v1", "receipt_kind":"unrun-preparation-closure",
                  "status":"FAIL", "family":"repository_history", "case":"deepseek-full", "source_commit":"source",
                  "product_tree":"product", "image":"image", "preparation_source_commit":"source",
                  "functional_status":"NOT_RUN", "proof_status":"NOT_RUN", "sample_count":0,
                  "attempted_operation_count":0, "completed_operation_count":0, "verification_attempt_count":0,
                  "preparation":{"status":"FAIL", "expired":True, "outer_exit_code":124, "wall_stop_seconds":120,
                                 "outer_wall_ns":120027598333, "sealed_prepared_available":False, "resource_claim_available":False},
                  "tag":"actual case NOT_RUN: original preparation FAIL at unchanged120s stop"}
        return selected, result

    def test_original_failed_preparation_keeps_actual_case_not_run_and_metrics_unavailable(self):
        selection, result = self.source()
        performance, verification = receipts.result_rows(selection, {"deepseek-full":result})
        self.assertEqual(performance[0]["status"], "NOT_RUN")
        self.assertEqual(verification[0]["proof_status"], "NOT_RUN")
        self.assertEqual(performance[0]["tag"], result["tag"])
        for axis in ("complete_wall_ns", "mount_ns", "command_ns", "commit_ns", "unmount_ns",
                     "requests", "owner_jobs", "statements", "store_logical_bytes", "store_allocated_bytes"):
            self.assertEqual(performance[0][axis], "UNAVAILABLE", axis)

    def test_attempted_cases_wrong_source_or_claimed_measurements_cannot_be_masked(self):
        changes = [{"sample_count":1}, {"sample_count":False}, {"attempted_operation_count":1},
                   {"completed_operation_count":1}, {"verification_attempt_count":1}, {"functional_status":"PASS"},
                   {"proof_status":"PASS"}, {"source_commit":"other"}, {"product_tree":"other"}, {"image":"other"},
                   {"family":"other"}, {"case":"other"}, {"preparation_source_commit":"other"},
                   {"complete_wall_ns":0}, {"counts":{"requests":0}}, {"observations":{}}, {"phases":{}},
                   {"schema":"other"}, {"status":"PASS"}, {"proof_only":True}]
        for change in changes:
            selection, result = self.source()
            result.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                receipts.result_rows(selection, {"deepseek-full":result})
        for change in ({"status":"PASS"}, {"expired":False}, {"outer_exit_code":0}, {"wall_stop_seconds":121},
                       {"outer_wall_ns":1}, {"sealed_prepared_available":True}, {"resource_claim_available":True}):
            selection, result = self.source()
            result["preparation"].update(change)
            with self.subTest(preparation=change), self.assertRaises(ValueError):
                receipts.result_rows(selection, {"deepseek-full":result})


if __name__ == "__main__":
    unittest.main()
