"""The required Created/Committed oracle belongs to the actual edit, after Init."""
import copy
import json
from pathlib import Path
import sys
import unittest

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import workspace


class FootprintCommitStep(unittest.TestCase):
    def cases(self):
        return json.loads((BENCH / 'families/store_footprint/family.json').read_text())['cases']

    def test_each_original_two_step_case_selects_its_single_mutation_expectation(self):
        for case in self.cases():
            self.assertNotIn('expected_commit', case)
            self.assertNotIn('expected_commit', case['steps'][0])
            self.assertEqual(workspace.operation_commit_expectation(case, 1), 'Committed')

    def test_missing_duplicate_or_weakened_mutation_declarations_are_refused(self):
        for change in ('missing', 'duplicate', 'up_to_date', 'schedule_disagreement', 'wrong_index'):
            case = copy.deepcopy(self.cases()[0])
            index = 1
            if change == 'missing': del case['steps'][1]['expected_commit']
            if change == 'duplicate': case['steps'].append(copy.deepcopy(case['steps'][1]))
            if change == 'up_to_date': case['steps'][1]['expected_commit'] = 'UpToDate'
            if change == 'schedule_disagreement': case['store_footprint_schedule']['expected_commit'] = 'UpToDate'
            if change == 'wrong_index': index = 2
            with self.subTest(change=change), self.assertRaises(ValueError):
                workspace.operation_commit_expectation(case, index)

    def test_other_family_explicit_step_and_legacy_case_expectations_remain_strict(self):
        self.assertEqual(workspace.operation_commit_expectation({'steps':[{'expected_commit':'Committed'}]}, 1), 'Committed')
        self.assertEqual(workspace.operation_commit_expectation({'steps':[{}], 'expected_commit':'UpToDate'}, 1), 'UpToDate')
        with self.assertRaises(ValueError):
            workspace.operation_commit_expectation({'steps':[{}]}, 1)


if __name__ == '__main__':
    unittest.main()
