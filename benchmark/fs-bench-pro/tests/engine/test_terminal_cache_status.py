"""A declared cache miss must retain INELIGIBLE and allow the full proof."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import workspace


class TerminalCacheStatus(unittest.TestCase):
    def observe(self, code, body, cache_class="A"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.stdout"
            path.write_text(json.dumps(body))
            def command(argv, folder, label, seconds, *, allow_failure=False):
                if code and not allow_failure:
                    raise RuntimeError(f"cache-observation failed with exit {code}")
                return {"exit_code": code, "stdout": str(path), "status": "PASS" if code == 0 else "FAIL"}
            runtime = SimpleNamespace(container="original-container")
            with patch.object(workspace, "readiness", return_value=[{"fields":{"state":"Gone"}}]), \
                    patch.object(workspace.receipts, "command", side_effect=command):
                return workspace.terminal_cache_observation(runtime, "original-key", {"socket":"/socket"}, directory, cache_class)

    def test_actual_ineligible_a_observation_retains_miss_and_completed_cleanup(self):
        body = {"cache_class":"A", "status":"INELIGIBLE", "resident_pages":8,
                "attempts":0, "exploratory":True, "admission_eligible":False, "payload_bytes_read":0}
        cleaned, observed = self.observe(3, body)
        self.assertEqual(cleaned, [{"fields":{"state":"Gone"}}])
        self.assertEqual(observed, body)
        self.assertFalse(observed["admission_eligible"])

    def test_observer_errors_and_forged_miss_are_still_refused(self):
        good = {"cache_class":"A", "status":"INELIGIBLE", "resident_pages":8,
                "attempts":0, "exploratory":True, "admission_eligible":False, "payload_bytes_read":0}
        for code, change, declared in (
                (4, {}, "A"), (1, {}, "A"), (3, {"status":"ELIGIBLE"}, "A"),
                (3, {"cache_class":"B"}, "A"), (3, {}, "B"),
                (3, {"resident_pages":0}, "A"), (3, {"resident_pages":True}, "A"),
                (3, {"attempts":1}, "A"), (3, {"exploratory":False}, "A"),
                (3, {"admission_eligible":True}, "A"), (3, {"payload_bytes_read":1}, "A")):
            with self.subTest(code=code, change=change, declared=declared), self.assertRaises((ValueError, RuntimeError)):
                self.observe(code, {**good, **change}, declared)

    def test_original_unavailable_a_observation_retains_error_without_cold_credit(self):
        body = {"cache_class":"A", "status":"UNAVAILABLE", "attempts":0,
                "errno":38, "error":"file identity changed during residency attestation"}
        cleaned, observed = self.observe(4, body)
        self.assertEqual(cleaned, [{"fields":{"state":"Gone"}}])
        self.assertEqual(observed, body)
        self.assertNotIn("resident_pages", observed)
        self.assertEqual(workspace.cache.validate("A", {"residency":observed}), "INELIGIBLE")

    def test_malformed_unavailable_records_cannot_bypass_observer_failure(self):
        good = {"cache_class":"A", "status":"UNAVAILABLE", "attempts":0,
                "errno":38, "error":"file identity changed during residency attestation"}
        for change in ({"status":"ELIGIBLE"}, {"cache_class":"B"}, {"attempts":True},
                {"attempts":1}, {"errno":None}, {"errno":True}, {"errno":-1},
                {"error":""}, {"error":None}, {"admission_eligible":True}):
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError)):
                self.observe(4, {**good, **change})


if __name__ == "__main__":
    unittest.main()
