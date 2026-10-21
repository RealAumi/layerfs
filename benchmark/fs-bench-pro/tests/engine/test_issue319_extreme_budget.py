"""Expanded owner authorization: the declared 300s exhaustive proof can run."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'benchmark/fs-bench-pro'))
from engine.workspace import family_proof_deadlines
spec=importlib.util.spec_from_file_location('extreme_driver',ROOT/'core/docs/issues/319/tools/invoke_case.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
CASE='v016-mixed-exhaustive-500mb-30000-k100-v1'

class Extreme(unittest.TestCase):
    def setUp(self):
        self.cases=json.loads((ROOT/'benchmark/fs-bench-pro/families/mixed_load_bearing/family.json').read_text())['cases']
        self.case=copy.deepcopy(next(c for c in self.cases if c['id']==CASE))
    def test_prospective_large_complete_ceiling_matches_existing_proof(self):
        self.case['owner_test_ceiling_ms']=275000
        self.assertIsNotNone(family_proof_deadlines(self.case))
        small=copy.deepcopy(next(c for c in self.cases if c.get('proof_only') and c['id']!=CASE))
        small['owner_test_ceiling_ms']=300000
        with self.assertRaises(ValueError):family_proof_deadlines(small)
    def test_named_run_driver_and_definition(self):
        self.assertEqual(driver.call_policy('run','mixed_load_bearing:'+CASE)['outer_seconds'],300)
        self.assertEqual(self.case['owner_test_ceiling_ms'],275000)
        for c in self.cases:
            if c.get('proof_only') and c['id']!=CASE:self.assertEqual(c['owner_test_ceiling_ms'],120000)
        self.assertEqual(driver.call_policy('run','mixed_load_bearing:'+CASE+'-extra')['outer_seconds'],118)
