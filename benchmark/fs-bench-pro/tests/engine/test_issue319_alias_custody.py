"""Single automatic alias timestamp, bound to independent native qualification."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'benchmark/fs-bench-pro'))
from engine.workspace import alias_parent_custody

class AliasCustody(unittest.TestCase):
    def setUp(self):
        definition=json.loads((ROOT/'benchmark/fs-bench-pro/families/file_size_transition/family.json').read_text())
        self.case=next(c for c in definition['cases'] if c.get('automatic_parent_mtime'))
        self.prepared={'native_verification':{'automatic-parent-mtime':{'verification_status':'pass'}}}
        self.body='original-boundary-parent-mtime-v1\ncase\tv016-boundary-alias-roundtrip-v1\nstep\t5\npath\tdata\ninitial\t1700000000\t0\nstarted\t1791700000\t200000000\nfinished\t1791700000\t300000000\nobserved\t1791700000\t250000000\n'

    def call(self,body,prepared=None):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);stdout=root/'stdout';stdout.write_text('original helper receipt\n'+body)
            return alias_parent_custody(self.case, prepared or self.prepared, {'fields':{'stdout':str(stdout),'exit_code':'0'}},root)

    def test_exact_custody(self):
        self.assertEqual(self.call(self.body)['index'],5)

    def test_rejects_substitution_or_missing_qualification(self):
        changes=[self.body+self.body,self.body.replace('path\tdata','path\tdata/file'),self.body.replace('step\t5','step\t4'),self.body.replace('observed\t1791700000\t250000000','observed\t1791700001\t0'),self.body.replace('finished\t1791700000\t300000000','finished\t1791699999\t0'),self.body.replace('250000000','1000000000'),self.body+'extra\n']
        for body in changes:
            with self.subTest(body=body),self.assertRaises(ValueError):self.call(body)
        with self.assertRaises(ValueError):self.call(self.body,{'native_verification':{}})
