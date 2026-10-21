"""The owner's prospective execution exception changes the two kept 500-step histories."""
import json
from pathlib import Path
import unittest

BENCH = Path(__file__).resolve().parents[2]
EXTENDED = frozenset(("dedup-history-distributed-500", "dedup-history-unrelated-500-mixed-v2"))


class HistoryCumulativeBudget(unittest.TestCase):
    def test_exact_two_kept_cumulative_limits_preserve_operations_reporting_and_proof(self):
        cases = json.loads((BENCH / "families/dedup_branch_history/family.json").read_text())["cases"]
        self.assertEqual({case["id"] for case in cases if case["budget"]["performance_hard_watchdog_ms"] == 210000}, EXTENDED)
        for case in cases:
            with self.subTest(case=case["id"]):
                original_v016 = case["id"].startswith("v016-")
                self.assertEqual(case["budget"], {
                    "command_ms": 15000,
                    "performance_hard_watchdog_ms": 210000 if case["id"] in EXTENDED else 60000 if original_v016 else 120000,
                    "operation_watchdog_ms": 60000 if original_v016 else 120000,
                    "verifier_ms": 25000 if original_v016 else 45000,
                    "verification_hard_watchdog_ms": 35000 if original_v016 else 59000,
                    "cleanup_reserve_ms": 3000 if original_v016 else 4000,
                    "publication_guard_ms": 250,
                })


if __name__ == "__main__":
    unittest.main()
