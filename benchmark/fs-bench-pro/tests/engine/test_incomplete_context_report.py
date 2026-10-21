"""Incomplete concurrent rounds never publish initialized phase totals as timing."""
import copy
from pathlib import Path
import sys
import unittest

BENCH=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BENCH))
from engine import receipts


class IncompleteContextReport(unittest.TestCase):
    def selection(self,family='multi_workspace_development'):
        return {'family':family,'source_commit':'a'*40,'product_tree':'b'*40,
                'cases':[{'id':'original-case','v016_case':'original-case','status':'ported','cache_class':'B'}]}

    def failed(self):
        return {'status':'FAIL','functional_status':'FAIL','proof_status':'NOT_RUN',
                'source_commit':'a'*40,'product_tree':'b'*40,'phases':{'mount_ns':123,'command_ns':0,'commit_ns':0,'unmount_ns':0},
                'original_failure':'original concurrent CREATE EAGAIN','cleanup':'UNAVAILABLE','counts':{},'observations':{}}

    def test_failed_original_context_with_no_complete_round_withholds_every_total(self):
        for family in ('multi_workspace_development','branch_development'):
            with self.subTest(family=family):
                row=self.failed();before=copy.deepcopy(row)
                performance,proof=receipts.result_rows(self.selection(family),{'original-case':row})
                for name in ('mount_ns','command_ns','commit_ns','unmount_ns'):
                    self.assertEqual(performance[0][name],'UNAVAILABLE',name)
                self.assertIn('incomplete original context phase totals',performance[0]['tag'])
                self.assertIn('incomplete original context phase totals',proof[0]['tag'])
                self.assertEqual(row,before)
                self.assertEqual(performance[0]['status'],'FAIL')
                self.assertEqual(proof[0]['proof_status'],'NOT_RUN')

    def test_partial_nonzero_totals_also_stay_raw_and_cannot_be_whole_case_metrics(self):
        row=self.failed();row['phases'].update(command_ns=999,commit_ns=888,unmount_ns=777)
        performance,_=receipts.result_rows(self.selection(),{'original-case':row})
        self.assertEqual([performance[0][name] for name in ('mount_ns','command_ns','commit_ns','unmount_ns')],['UNAVAILABLE']*4)

    def test_completed_work_with_later_proof_failure_preserves_exact_measured_totals(self):
        row=self.failed();row.update(complete_wall_ns=1000,declared_limit_ns=900,proof_status='FAIL')
        performance,proof=receipts.result_rows(self.selection(),{'original-case':row})
        for name,value in row['phases'].items():self.assertEqual(performance[0][name],value)
        self.assertEqual(performance[0]['complete_wall_ns'],1000)
        self.assertEqual(performance[0]['limit_status'],'EXCEEDED')
        self.assertNotIn('incomplete original context phase totals',proof[0]['tag'])

    def test_other_routes_legitimate_zero_and_unrun_context_remain_unchanged(self):
        row=self.failed()
        performance,_=receipts.result_rows(self.selection('file_size_transition'),{'original-case':row})
        self.assertEqual(performance[0]['commit_ns'],0)
        performance,_=receipts.result_rows(self.selection(),{})
        self.assertEqual(performance[0]['status'],'NOT_RUN')
        self.assertNotIn('incomplete original context phase totals',performance[0]['tag'])
        performance,_=receipts.result_rows(self.selection(),{'original-case':{'status':'NOT_RUN','tag':'failed preparation; no case attempt'}})
        self.assertNotIn('incomplete original context phase totals',performance[0]['tag'])


if __name__=='__main__':unittest.main()
