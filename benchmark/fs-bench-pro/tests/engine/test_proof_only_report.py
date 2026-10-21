"""Proof-only cases keep real verification evidence and no numeric performance."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import receipts


class ProofOnlyReport(unittest.TestCase):
    def selection(self):
        return {"family":"mixed_load_bearing","source_commit":"a"*40,"product_tree":"b"*40,
                "date":"2026-10-10","image":"pinned","cases":[{"id":"exhaustive","v016_case":"original",
                "status":"ported","proof_only":True,"budget":{"command_ms":None,"verifier_ms":300000}}]}

    def record(self):
        return {"family":"mixed_load_bearing","case":"exhaustive","source_commit":"a"*40,"product_tree":"b"*40,
                "image":"pinned","status":"INELIGIBLE","functional_status":"PASS","proof_status":"PASS",
                "proof_only":True,"performance_mode":"verification-only","sample_count":0,"verification_attempt_count":1,
                "complete_wall_ns":123456789,"proof_wall_ns":987654321,"declared_limit_ns":None,
                "verifier_limit_ns":300000000000,"owner_wall_stop_ns":120000000000,"cache_class":"C",
                "counts":{"requests":11,"owner_jobs":17,"statements":19},"phases":{"mount_ns":1,"command_ns":2,"commit_ns":3,"unmount_ns":4},
                "observations":{"store_logical_bytes":{"status":"AVAILABLE","value":4096},
                                "store_allocated_bytes":{"status":"AVAILABLE","value":8192}},
                "cleanup":"Gone","evidence":"raw/example","tag":"original diagnostic row",
                "verification":{"scope":"all declared retained states","omissions":"retired format"}}

    def test_performance_all_na_proof_actual_limits_and_raw_metrics_preserved(self):
        row=self.record();original=copy.deepcopy(row)
        performance,proof=receipts.result_rows(self.selection(),{"exhaustive":row})
        for name in receipts.PROOF_ONLY_PERFORMANCE_COLUMNS:self.assertEqual(performance[0][name],"N/A",name)
        self.assertEqual(proof[0]["proof_status"],"PASS")
        self.assertEqual(proof[0]["proof_wall_ns"],987654321)
        self.assertEqual(proof[0]["declared_limit_ns"],300000000000)
        self.assertEqual(performance[0]["source_commit"],row["source_commit"])
        self.assertEqual(performance[0]["cleanup"],"Gone")
        self.assertIn("verification-only",performance[0]["tag"])
        self.assertEqual(row,original)

    def test_failed_and_unrun_proof_are_visible_without_fabricated_speed(self):
        failed={**self.record(),"status":"FAIL","proof_status":"FAIL","tag":"original owner120s cap reached"}
        performance,proof=receipts.result_rows(self.selection(),{"exhaustive":failed})
        self.assertEqual(performance[0]["status"],"N/A")
        self.assertEqual(proof[0]["proof_status"],"FAIL")
        self.assertIn("owner120s cap",proof[0]["tag"])
        performance,proof=receipts.result_rows(self.selection(),{})
        self.assertEqual(performance[0]["status"],"N/A")
        self.assertEqual(proof[0]["proof_status"],"NOT_RUN")
        self.assertEqual(proof[0]["declared_limit_ns"],300000000000)
        self.assertEqual(proof[0]["proof_wall_ns"],"UNAVAILABLE")

    def test_generated_two_csvs_keep_proof_only_na_and_actual_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=Path(temporary);selection=self.selection();row=self.record()
            receipts.write_new(run/"run.json",selection)
            folder=run/"exhaustive";folder.mkdir()
            receipts.write_new(folder/"receipt.json",row);receipts.manifest(folder)
            seal=(folder/"receipt.json").read_bytes()
            receipts.report(run,run/"csv")
            with (run/"csv/performance.csv").open(newline="") as stream:performance=next(csv.DictReader(stream))
            with (run/"csv/verification.csv").open(newline="") as stream:proof=next(csv.DictReader(stream))
            self.assertEqual(performance["complete_wall_ns"],"N/A")
            self.assertEqual(performance["requests"],"N/A")
            self.assertEqual(proof["proof_status"],"PASS")
            self.assertEqual(proof["proof_wall_ns"],"987654321")
            self.assertEqual((folder/"receipt.json").read_bytes(),seal)

    def test_raw_flag_cannot_hide_a_performance_case(self):
        selection=self.selection();selection["cases"][0].pop("proof_only")
        with self.assertRaisesRegex(ValueError,"mode differs"):
            receipts.result_rows(selection,{"exhaustive":self.record()})

    def test_overall_close_failure_remains_visible_beside_passing_semantic_proof(self):
        row={**self.record(),"status":"FAIL","independent_close_failures":["retained output close failed"]}
        performance,proof=receipts.result_rows(self.selection(),{"exhaustive":row})
        self.assertEqual(performance[0]["status"],"N/A")
        self.assertEqual(proof[0]["proof_status"],"PASS")
        self.assertIn("original overall result FAIL",proof[0]["tag"])
        self.assertIn("retained output close failed",proof[0]["tag"])


if __name__=="__main__":unittest.main()
