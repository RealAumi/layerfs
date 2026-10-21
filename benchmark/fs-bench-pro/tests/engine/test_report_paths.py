"""Parallel reports preserve separate run rows and pre-existing flat reports."""
import csv
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import receipts


class ParallelReportPaths(unittest.TestCase):
    def test_two_families_same_commit_do_not_overwrite_or_collide(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / 'benchmark/fs-bench-pro/baselines'
            reference = baseline / 'v0.1.6/reference.csv'
            reference.parent.mkdir(parents=True)
            shutil.copy2(BENCH / 'baselines/v0.1.6/reference.csv', reference)
            original = baseline / 'core/2026-10-11-149d40bac'
            original.mkdir(parents=True)
            (original / 'performance.csv').write_bytes(b'closed original performance\n')
            (original / 'verification.csv').write_bytes(b'closed original verification\n')
            for family in ('store_footprint', 'dedup_cross_file'):
                selected = dict(date='2026-10-11', source_commit='149d40bac' + '0' * 31,
                    product_tree='a' * 40, family=family, cases=[dict(id='first', status='ported'), dict(id='second', status='ported')])
                with patch.object(receipts, 'ROOT', root), patch.object(receipts, 'load_run', return_value=(selected, {})):
                    result = receipts.report(root / family)
                destination = Path(result['destination'])
                self.assertEqual(destination, original / family)
                for kind in ('performance', 'verification'):
                    with (destination / (kind + '.csv')).open() as stream:
                        rows = list(csv.DictReader(stream))
                    self.assertEqual([row['case'] for row in rows], ['first', 'second'])
                    self.assertTrue(all(row['family'] == family for row in rows))
            self.assertEqual((original / 'performance.csv').read_bytes(), b'closed original performance\n')
            self.assertEqual((original / 'verification.csv').read_bytes(), b'closed original verification\n')


    def test_explicit_destination_keeps_exact_requested_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'closed-layout'
            selected = dict(date='2026-10-11', source_commit='149d40bac' + '0' * 31,
                family='store_footprint', cases=[dict(id='unsampled', status='ported')])
            with patch.object(receipts, 'load_run', return_value=(selected, {})):
                result = receipts.report(Path(temporary) / 'run', destination=target)
            self.assertEqual(Path(result['destination']), target)
            self.assertTrue((target / 'performance.csv').is_file())
            self.assertTrue((target / 'verification.csv').is_file())


if __name__ == '__main__':
    unittest.main()
