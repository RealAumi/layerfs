"""D-3 admission is confined to the three kept large-check failures."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import workspace

LARGE = {
    'dedup_workspace_reuse': ['dedup-workspace-unique-500'],
    'store_footprint': ['store-footprint-unique-100000', 'store-footprint-metadata-cardinality-100000'],
}


def cases(family):
    return json.loads((BENCH / 'families' / family / 'family.json').read_text())['cases']


class LargeChecks(unittest.TestCase):
    def test_three_kept_large_allowances_are_validated_together_with_deadlines(self):
        for family, selected in LARGE.items():
            for case in cases(family):
                with self.subTest(case=case['id']):
                    trial = copy.deepcopy(case)
                    if case['id'] in selected:
                        trial['budget'].update(verifier_ms=75000, verification_hard_watchdog_ms=89000)
                        expected = {'work':169, 'cleanup':173, 'publication':187}
                    else:
                        expected = {'work':139, 'cleanup':143, 'publication':157}
                    with patch.object(workspace.time, 'monotonic', return_value=100):
                        self.assertEqual(workspace.import_proof_deadlines(trial, 2_000_000_000), expected)
                    trial['budget']['verifier_ms'] += 1
                    with self.assertRaises(ValueError):
                        workspace.import_proof_deadlines(trial)

    def test_small_checks_cannot_acquire_the_large_allowance(self):
        case = copy.deepcopy(cases('dedup_workspace_reuse')[0])
        case['budget'].update(verifier_ms=75000, verification_hard_watchdog_ms=89000)
        with self.assertRaises(ValueError):
            workspace.import_proof_deadlines(case)


ROOT_PROOF = {
    'mixed_load_bearing': {'v016-mixed-development-500mb-30000-k10-v1': (50000, 60000),
                           'v016-mixed-development-500mb-30000-k100-v1': (50000, 60000)},
    'multi_workspace_development': {'v016-workspace-mixed-500mb-30000-k10-v1': (80000, 90000),
                                    'v016-workspace-mixed-500mb-30000-k100-v1': (80000, 90000)},
    'branch_development': {'v016-branch-mixed-500mb-30000-k10-v1': (105000, 115000),
                           'v016-branch-mixed-500mb-30000-k100-v1': (105000, 115000)},
}


class LargeRootProofs(unittest.TestCase):
    """Phase 13 admission is confined to the three kept 500 MiB mixed cases."""

    def deadlines(self, family, case):
        if family == 'mixed_load_bearing':
            return workspace.family_proof_deadlines(case, 2_000_000_000)
        return workspace.context_deadlines(case, 98.0)

    def test_named_set_is_exactly_the_six_cases_with_their_values(self):
        self.assertEqual(workspace.LARGE_ROOT_PROOF_LIMITS,
                         {name: value for rows in ROOT_PROOF.values() for name, value in rows.items()})

    def test_six_allowances_are_validated_together_with_deadlines(self):
        for family, selected in ROOT_PROOF.items():
            seen = set()
            for case in cases(family):
                if case.get('proof_only'):
                    continue
                with self.subTest(case=case['id']):
                    budget = case['budget']
                    limits = (budget['verifier_ms'], budget['verification_hard_watchdog_ms'])
                    if case['id'] in selected:
                        seen.add(case['id'])
                        self.assertEqual(limits, selected[case['id']])
                    else:
                        self.assertIn(limits, ((25000, 35000), (30000, 40000), (45000, 59000), (60000, 70000)))
                    work, hard = limits
                    reserve = 4000 if work == 45000 else 3000
                    with patch.object(workspace.time, 'monotonic', return_value=100):
                        self.assertEqual(self.deadlines(family, case),
                            {'work': 98 + (work - reserve) / 1000, 'cleanup': 98 + work / 1000,
                             'publication': 98 + hard / 1000})
                    for key in ('verifier_ms', 'verification_hard_watchdog_ms'):
                        trial = copy.deepcopy(case)
                        trial['budget'][key] += 1
                        with self.assertRaises(ValueError):
                            self.deadlines(family, trial)
            self.assertEqual(seen, set(selected))

    def test_named_cases_refuse_their_former_limits(self):
        for family, selected in ROOT_PROOF.items():
            for case in cases(family):
                if case['id'] in selected:
                    trial = copy.deepcopy(case)
                    trial['budget'].update(verifier_ms=25000, verification_hard_watchdog_ms=35000)
                    with self.subTest(case=case['id']), self.assertRaises(ValueError):
                        self.deadlines(family, trial)

    def test_other_cases_cannot_acquire_a_named_allowance(self):
        for family, selected in ROOT_PROOF.items():
            for case in cases(family):
                if case['id'] in selected or case.get('proof_only'):
                    continue
                for work, hard in sorted(set(selected.values())):
                    trial = copy.deepcopy(case)
                    trial['budget'].update(verifier_ms=work, verification_hard_watchdog_ms=hard)
                    with self.subTest(case=case['id'], work=work), self.assertRaises(ValueError):
                        self.deadlines(family, trial)

    def test_measured_command_and_performance_limits_are_unchanged(self):
        for family, selected in ROOT_PROOF.items():
            for case in cases(family):
                if case['id'] in selected:
                    with self.subTest(case=case['id']):
                        budget = case['budget']
                        self.assertEqual((budget['command_ms'], budget['operation_watchdog_ms'],
                                          budget['performance_hard_watchdog_ms']), (15000, 60000, 60000))
                        self.assertEqual(budget.get('verification_cleanup_reserve_ms', 3000), 3000)
                        self.assertEqual(budget.get('publication_guard_ms', 250), 250)


class CellCountPins(unittest.TestCase):
    """Phase 14 corrected C10 by one READ; issues 320 and 321 lower statements only; the baseline file is unchanged."""
    NAMES = ('requests', 'owner_jobs', 'statements')
    # Historical issue-321 statement pairs plus the recorded issue-320 C06
    # correction. These are not measurements of the final renamed source.
    STATEMENTS = {'C01': (44004, 21002), 'C02': (46004, 22002), 'C04': (42644, 19612), 'C05': (46637, 20269),
                  'C06': (9766, 4619), 'C07': (23133, 17440), 'C08': (9783, 7185), 'C09': (1055, 517),
                  'C10': (14408, 10773), 'C11': (9760, 7174)}

    def test_baseline_file_is_the_pinned_frozen_source(self):
        self.assertEqual(workspace.identity.sha256(workspace.BASELINE), workspace.BASELINE_SHA256)

    def test_requests_and_owner_jobs_stay_frozen_and_statements_follow_recorded_corrections(self):
        self.assertEqual(set(workspace.CELL_COUNT_CORRECTIONS), set(self.STATEMENTS))
        self.assertEqual(set(workspace.CELL_STATEMENT_RANGES), {'C03', 'C12'})
        for number in range(1, 13):
            cell = f'C{number:02}'
            with self.subTest(cell=cell):
                expected, frozen = workspace.cell_expected_counts(cell, self.NAMES)
                if cell == 'C10':
                    self.assertEqual(frozen, {'requests': 1548, 'owner_jobs': 1547, 'statements': 14408})
                    self.assertEqual([frozen[name] - expected[name] for name in self.NAMES[:2]], [1, 1])
                else:
                    self.assertEqual([expected[name] for name in self.NAMES[:2]], [frozen[name] for name in self.NAMES[:2]])
                if cell in self.STATEMENTS:
                    self.assertEqual((frozen['statements'], expected['statements']), self.STATEMENTS[cell])
                    self.assertLess(expected['statements'], frozen['statements'])
                else:
                    self.assertEqual(expected, frozen)

    def test_a_ranged_cell_keeps_requests_and_owner_jobs_exact(self):
        expected, _ = workspace.cell_expected_counts('C03', self.NAMES)
        good = {**expected, 'statements': 49460}
        self.assertTrue(workspace.cell_counts_reproduced('C03', good, expected))
        self.assertTrue(workspace.cell_counts_reproduced('C03', {**good, 'statements': 49038}, expected))
        for wrong in ({**good, 'statements': 49461}, {**good, 'statements': 49036}, {**good, 'statements': 57040},
                      {**good, 'statements': 82873},
                      {**good, 'requests': good['requests'] + 1}, {**good, 'owner_jobs': good['owner_jobs'] - 1}):
            self.assertFalse(workspace.cell_counts_reproduced('C03', wrong, expected))
        expected, _ = workspace.cell_expected_counts('C12', self.NAMES)
        self.assertTrue(workspace.cell_counts_reproduced('C12', {**expected, 'statements': 10977}, expected))
        for other in (10936, 11018, 19920, 24146):
            self.assertFalse(workspace.cell_counts_reproduced('C12', {**expected, 'statements': other}, expected))
        exact, _ = workspace.cell_expected_counts('C01', self.NAMES)
        self.assertTrue(workspace.cell_counts_reproduced('C01', exact, exact))
        for other in (21001, 21003, 36003):
            self.assertFalse(workspace.cell_counts_reproduced('C01', {**exact, 'statements': other}, exact))

    def test_source_model_read_count_matches_the_plain_read_cell(self):
        # 64 MiB in 128 KiB read windows; frozen C09 reads the same file in 512 READs and 5 other requests.
        reads = (64 * 1024 * 1024) // (128 * 1024)
        self.assertEqual(reads, 512)
        self.assertEqual(workspace.cell_expected_counts('C09', self.NAMES)[1]['requests'], reads + 5)


if __name__ == '__main__':
    unittest.main()
