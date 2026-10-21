import csv
import importlib.util
import json
from pathlib import Path
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
spec = importlib.util.spec_from_file_location("receipts", BENCH / "engine/receipts.py")
receipts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipts)


class ReferenceHarvest(unittest.TestCase):
    def test_all_source_rows_and_fields_are_preserved(self):
        with (BENCH / "baselines/v0.1.6/reference.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows, list(receipts.released_references(ROOT)))
        self.assertEqual(len(rows), 461)
        for source, count in zip(receipts.REFERENCE_SOURCES, (36, 198, 227)):
            selected = [row for row in rows if row["source_file"] == source]
            self.assertEqual(len(selected), count)
            with (ROOT / source).open(newline="") as stream:
                original = list(csv.DictReader(stream))
            self.assertEqual([json.loads(row["source_row_json"]) for row in selected], original)

    def test_missing_values_remain_missing_and_clocks_stay_distinct(self):
        rows = list(receipts.released_references(ROOT))
        unavailable = [row for row in rows if not row["source_value"]]
        self.assertTrue(unavailable)
        self.assertTrue(all(row["value_ns"] == "" for row in unavailable))
        self.assertTrue(any(row["timer"] == "complete_wall_seconds" for row in rows))
        self.assertTrue(any(row["timer"] == "pure_call_sum_ns" for row in rows))
        self.assertTrue(any(row["kind"] == "verification" for row in rows))


if __name__ == "__main__":
    unittest.main()
