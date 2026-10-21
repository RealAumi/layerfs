"""Prospective history uses the exact existing guarded publication obligations."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import receipts


class HistoryPublication(unittest.TestCase):
    def record(self,run):
        row={"schema":"fs-bench-pro-workspace-family-v1","family":"dedup_branch_history",
             "case":"dedup-history-metadata-1","source_commit":"a"*40,"product_tree":"b"*40,
             "image":"pinned","status":"INELIGIBLE","functional_status":"PASS","proof_status":"PASS",
             "proof_wall_ns":123,"cleanup":"Gone","custody":"KNOWN_STOP"}
        receipts.write_new(run/"run.json",{"family":row["family"],"source_commit":row["source_commit"],
            "product_tree":row["product_tree"],"image":row["image"],"cases":[{"id":row["case"]}]})
        return row,run/row["case"]

    def test_history_known_outer_return_required_and_original_bytes_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary);row,folder=self.record(run)
            with patch.object(receipts.time,"monotonic",return_value=9.5):
                result=receipts.finalize_guarded(folder,row,10.,scope=receipts.HISTORY_PUBLICATION_SCOPE)
            self.assertEqual(result["publication_guard"]["scope"],receipts.HISTORY_PUBLICATION_SCOPE)
            original=(folder/"receipt.json").read_bytes();manifest=(folder/"manifest.json").read_bytes()
            _,before=receipts.load_run(run)
            self.assertEqual(before[row["case"]]["proof_status"],"FAIL")
            with patch.object(receipts.time,"monotonic",return_value=12.):
                receipts.acknowledge_guarded(folder,result)
            _,loaded=receipts.load_run(run)
            self.assertEqual(loaded[row["case"]],result)
            self.assertEqual((folder/"receipt.json").read_bytes(),original)
            self.assertEqual((folder/"manifest.json").read_bytes(),manifest)

    def test_history_same_publication_margin_late_failure_and_bound_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary);row,folder=self.record(run)
            with patch.object(receipts.time,"monotonic",return_value=9.75):
                result=receipts.finalize_guarded(folder,row,10.,scope=receipts.HISTORY_PUBLICATION_SCOPE)
            self.assertEqual((result["status"],result["proof_status"]),("FAIL","FAIL"))
            failure=json.loads((folder/"publication-failure.json").read_text())
            self.assertEqual(failure["scope"],receipts.HISTORY_PUBLICATION_SCOPE)
            self.assertEqual(failure["publication_guard_seconds"],.25)
            receipts.acknowledge_guarded(folder,result)
            _,loaded=receipts.load_run(run)
            self.assertEqual(loaded[row["case"]]["proof_status"],"FAIL")

    def test_unknown_scope_is_rejected_and_closed_git_scope_is_unchanged(self):
        original="original Git cumulative verification hard deadline through receipt write, evidence hashing, manifest publication, publication-observation write/hash and guarded completion publication; monotonic host clock; no measured performance interval charged"
        self.assertEqual(receipts.PUBLICATION_SCOPE,original)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/"case"
            with self.assertRaises(ValueError):
                receipts.finalize_guarded(folder,{},10.,scope="weakened scope")
            self.assertFalse(folder.exists())


if __name__=="__main__":unittest.main()
