"""The unchanged local-snapshot sample emits its own exact multiline contract."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(HERE))
from engine import workspace

PATHS=['.','f00000','f00001','f00097','f00194','f12500','f24998','f24999']
OMISSIONS='unselected paths, bytes beyond selected ranges, exhaustive inode/object/reference census, alias and failure injection semantics'
ORIGINAL=('absent_paths=\nfull_file_bytes_verified=false\nfull_namespace_verified=false\n'
          'omissions='+OMISSIONS+'\nsampled_paths='+'\n'.join(PATHS)+'\n'
          'sampled_ranges='+'\n'.join(p+':0..1' for p in PATHS[1:])+'\n')

class NativeReceipt(unittest.TestCase):
    def case(self):
        return json.loads((HERE/'families/local_snapshot/family.json').read_text())['cases'][0]
    def check(self,text,exit_code='0',case=None):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'original.stdout';out.write_text(text)
            return workspace.verify_native_receipt(case or self.case(),{'fields':{'stdout':str(out),'exit_code':exit_code}})
    def test_original_multiline_sample_with_successful_exit_is_preserved(self):
        proof=self.check(ORIGINAL)
        self.assertEqual(proof['sampled_paths'],PATHS)
        self.assertEqual(proof['full_namespace_verified'],False)
        self.assertEqual(proof['full_file_bytes_verified'],False)
        self.assertEqual(proof['original_omissions'],OMISSIONS)
    def test_sample_cannot_claim_different_paths_ranges_scope_or_missing_exit(self):
        for bad in (ORIGINAL.replace('f00097','f00098'),ORIGINAL.replace(':0..1',':0..0'),
                    ORIGINAL.replace('false','true'),ORIGINAL+'verification_status=pass\n',
                    ORIGINAL.replace('absent_paths=','absent_paths=unexpected')):
            with self.subTest(text=bad),self.assertRaises(ValueError):self.check(bad)
        for bad in ('1',None,0):
            with self.subTest(exit=bad),self.assertRaises(ValueError):self.check(ORIGINAL,bad)
    def test_non_snapshot_full_verifier_still_requires_original_pass(self):
        self.assertEqual(self.check('verification_status=pass\n',case={'v016_case':'ordinary'})['verification_status'],'pass')
        with self.assertRaises(ValueError):self.check('verification_status=fail\n',case={'v016_case':'ordinary'})
